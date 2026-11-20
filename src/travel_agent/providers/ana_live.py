from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta, timezone

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from travel_agent.providers.base import FareOption, ProviderSearchError, SearchQuery

ANA_HOME_URL = "https://www.ana.co.jp/en/us/"
ANA_RESULTS_PATH = "/webapps/reservation/roundtrip-flight-availability-international"
CHROME_CDP_URL = os.getenv("CHROME_CDP_URL", "http://127.0.0.1:9222")
DEFAULT_TIMEOUT_MS = 30_000
BAY_AREA_AIRPORTS = {"SFO", "SJC"}
JAPAN_AIRPORTS = {"NRT", "HND", "KIX"}
AIRPORT_NAMES = {
    "SFO": "San Francisco",
    "SJC": "San Jose",
    "NRT": "Tokyo (Narita)",
    "HND": "Tokyo (Haneda)",
    "KIX": "Osaka (Kansai)",
}
_DATE_PRICE_PATTERN = re.compile(
    r"\b([A-Z][a-z]{2})\s+(\d{1,2})\b.*?\bFrom\s+([A-Z]{3})\s*([\d,]+(?:\.\d+)?)",
    re.S,
)


class AnaLiveProvider:
    """Collect official ANA one-way date-strip fares through a regular Chrome session."""

    name = "ana-live"

    def __init__(self, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> None:
        self.timeout_ms = timeout_ms

    def search(self, query: SearchQuery) -> list[FareOption]:
        return self.search_range(
            query.origin,
            query.destination,
            query.departure_date,
            query.departure_date,
            query.passengers,
        )

    def search_range(
        self,
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
        passengers: int = 1,
    ) -> list[FareOption]:
        origin, destination = self._validate_search(
            origin, destination, start_date, end_date, passengers
        )
        anchor_date = min(start_date + timedelta(days=3), end_date)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(
                    CHROME_CDP_URL, timeout=self.timeout_ms
                )
                if not browser.contexts:
                    raise ProviderSearchError(
                        "Connected to Chrome, but no browser context was found"
                    )
                for existing_context in browser.contexts:
                    for existing_page in existing_context.pages:
                        if ANA_RESULTS_PATH not in existing_page.url:
                            continue
                        existing_page.set_default_timeout(self.timeout_ms)
                        try:
                            self._require_results_route(
                                existing_page, origin, destination
                            )
                        except ProviderSearchError:
                            continue
                        return self._scan_date_strip(
                            existing_page,
                            origin,
                            destination,
                            start_date,
                            end_date,
                            anchor_date,
                        )

                context = browser.new_context()
                try:
                    page = context.new_page()
                    page.set_default_timeout(self.timeout_ms)
                    page.set_default_navigation_timeout(self.timeout_ms)
                    self._open_results(page, origin, destination, anchor_date)
                    return self._scan_date_strip(
                        page, origin, destination, start_date, end_date, anchor_date
                    )
                finally:
                    context.close()
        except ProviderSearchError:
            raise
        except PlaywrightTimeoutError as exc:
            raise ProviderSearchError(
                "ANA live one-way search timed out before fares could be read"
            ) from exc
        except PlaywrightError as exc:
            raise ProviderSearchError(f"ANA live browser search failed: {exc}") from exc

    def _open_results(
        self, page: Page, origin: str, destination: str, departure_date: date
    ) -> None:
        page.goto(ANA_HOME_URL, wait_until="domcontentloaded", timeout=self.timeout_ms)
        page.wait_for_timeout(2_000)
        consent_cancel = page.locator("#ensModalWrapper button", has_text="Cancel")
        if consent_cancel.count() and consent_cancel.first.is_visible():
            consent_cancel.first.click()

        form = page.locator("form.be-wws-reserve-ticket__form--overseas").first
        if form.count() == 0:
            raise ProviderSearchError("ANA public one-way search form was not found")
        self._select_airport(
            page,
            form.locator(".be-wws-reserve-ticket-departure-airport__button"),
            origin,
        )
        self._select_airport(
            page,
            form.locator(".be-wws-reserve-ticket-arrival-airport__button"),
            destination,
        )
        form.get_by_text("One Way", exact=True).click()
        self._select_date(page, form, departure_date)

        values = {
            name: form.locator(f'input[name="{name}"]').input_value()
            for name in ("trip", "origin", "destination", "departureDate")
        }
        expected = {
            "trip": "onewayOrMulticity",
            "origin": origin,
            "destination": destination,
            "departureDate": departure_date.isoformat(),
        }
        if values != expected:
            raise ProviderSearchError(
                f"ANA search form did not retain the requested {origin} → {destination} route and date"
            )

        form.locator('button[type="submit"]').click()
        page.wait_for_url(re.compile(re.escape(ANA_RESULTS_PATH)), timeout=self.timeout_ms)
        page.locator(".c-result-date-navi__btn-price").first.wait_for(
            state="visible", timeout=self.timeout_ms
        )
        self._require_results_route(page, origin, destination)

    def _select_airport(self, page: Page, button, airport: str) -> None:
        button.click()
        dialog = page.locator(".be-dialog:visible")
        search = dialog.locator("input.be-list-with-search__searchbox-input")
        search.fill(airport)
        option = dialog.locator(f'li[data-value="{airport}"]:visible')
        option.wait_for(state="visible")
        option.click()

    def _select_date(self, page: Page, form, departure_date: date) -> None:
        form.locator(".be-wws-reserve-ticket-departure-date__button").click()
        dialog = page.locator(".be-dialog:visible")
        target_prefix = (
            f"{departure_date.year}/{departure_date.month}/{departure_date.day}"
        )
        for _ in range(18):
            target = dialog.locator(f'button[aria-label^="{target_prefix}"]')
            if target.count():
                target.click()
                dialog.get_by_role("button", name="Confirm Selection").click()
                return
            next_button = dialog.get_by_role("button", name="Next", exact=True)
            if next_button.count() == 0:
                break
            next_button.click()
            page.wait_for_timeout(150)
        raise ProviderSearchError(
            f"ANA date picker did not expose {departure_date.isoformat()}"
        )

    def _scan_date_strip(
        self,
        page: Page,
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
        anchor_date: date,
    ) -> list[FareOption]:
        observed_at = datetime.now(timezone.utc)
        booking_url = page.url
        cabin = self._results_cabin(page)
        fares: dict[date, FareOption] = {}

        for _ in range(80):
            try:
                self._require_results_route(page, origin, destination)
            except ProviderSearchError:
                if fares:
                    break
                raise
            buttons = page.locator(
                ".c-result-date-navi__btn:not(.c-result-date-navi__btn--change-week)"
            )
            texts = buttons.all_inner_texts()
            displayed_dates: list[date] = []
            for text in texts:
                parsed = _parse_date_strip_fare(text, anchor_date)
                if parsed is None:
                    continue
                departure_date, price, currency = parsed
                displayed_dates.append(departure_date)
                if start_date <= departure_date <= end_date:
                    fares[departure_date] = FareOption(
                        provider=self.name,
                        origin=origin,
                        destination=destination,
                        departure_date=departure_date,
                        cabin=cabin,
                        price=price,
                        currency=currency,
                        available_seats=None,
                        observed_at=observed_at,
                        booking_url=booking_url,
                        trip_type="one_way",
                        price_kind="from",
                        source_freshness="Live ANA availability search",
                    )
            if displayed_dates and max(displayed_dates) >= end_date:
                break

            first_text = texts[0] if texts else ""
            next_week = page.locator("#next-week-btn-0")
            if next_week.count() == 0 or next_week.is_disabled():
                break
            try:
                next_week.click()
                page.wait_for_function(
                    """oldText => {
                        const first = document.querySelector(
                          '.c-result-date-navi__btn:not(.c-result-date-navi__btn--change-week)'
                        );
                        return first && first.innerText !== oldText;
                    }""",
                    arg=first_text,
                    timeout=self.timeout_ms,
                )
            except (PlaywrightTimeoutError, PlaywrightError):
                if fares:
                    break
                raise
            page.wait_for_timeout(300)

        return [fares[key] for key in sorted(fares)]

    @staticmethod
    def _results_cabin(page: Page) -> str:
        marker = page.locator("#cabinclass-btn .p-result-function__btn-text")
        if marker.count() == 0:
            raise ProviderSearchError("ANA result cabin could not be verified")
        value = " ".join(marker.first.inner_text().split())
        cabins = {
            "Economy Class": "Economy",
            "Premium Economy": "Premium Economy",
        }
        if value not in cabins:
            raise ProviderSearchError(f"Unsupported ANA result cabin: {value}")
        return cabins[value]

    @staticmethod
    def _require_results_route(page: Page, origin: str, destination: str) -> None:
        expected = f"{AIRPORT_NAMES[origin]} to {AIRPORT_NAMES[destination]}"
        route = page.locator(".p-flight-bound__fromto")
        if route.count() == 0 or " ".join(route.first.inner_text().split()) != expected:
            raise ProviderSearchError(
                f"ANA result route could not be verified as {origin} → {destination}"
            )

    @staticmethod
    def _validate_search(
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
        passengers: int,
    ) -> tuple[str, str]:
        origin = origin.strip().upper()
        destination = destination.strip().upper()
        is_supported = (
            origin in BAY_AREA_AIRPORTS
            and destination in JAPAN_AIRPORTS
        ) or (
            origin in JAPAN_AIRPORTS
            and destination in BAY_AREA_AIRPORTS
        )
        if not is_supported:
            raise ProviderSearchError(
                "ANA live routes must be between SFO/SJC and NRT/HND/KIX"
            )
        if end_date < start_date:
            raise ProviderSearchError("ANA live scan end date must be on or after its start date")
        if start_date < date.today():
            raise ProviderSearchError("ANA live departure date cannot be in the past")
        if passengers != 1:
            raise ProviderSearchError("ANA live search currently supports exactly one adult")
        return origin, destination


def _parse_date_strip_fare(
    value: str, reference_date: date
) -> tuple[date, float, str] | None:
    match = _DATE_PRICE_PATTERN.search(" ".join(value.split()))
    if match is None:
        return None
    month_name, day_value, currency, price_value = match.groups()
    parsed = datetime.strptime(f"{month_name} {day_value}", "%b %d")
    candidates = [
        date(year, parsed.month, parsed.day)
        for year in (
            reference_date.year - 1,
            reference_date.year,
            reference_date.year + 1,
        )
    ]
    departure_date = min(
        candidates, key=lambda candidate: abs((candidate - reference_date).days)
    )
    return departure_date, float(price_value.replace(",", "")), currency
