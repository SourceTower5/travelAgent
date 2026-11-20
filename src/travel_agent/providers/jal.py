from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from travel_agent.providers.base import FareOption, ProviderSearchError, SearchQuery

JAL_BOOK_URL = "https://www.jal.co.jp/en-jp/book.html"
JAL_RESULTS_HOST = "book-i.jal.co.jp"
CHROME_CDP_URL = os.getenv("CHROME_CDP_URL", "http://127.0.0.1:9222")
DEFAULT_TIMEOUT_MS = 30_000
BAY_AREA_AIRPORTS = {"SFO", "SJC"}
JAPAN_AIRPORTS = {"HND", "NRT", "KIX"}
RESULT_ROUTE_MARKERS = {
    "SFO": "San Francisco",
    "SJC": "San Jose",
    "HND": "Haneda",
    "NRT": "Narita",
    "KIX": "Kansai",
}
_PRICE_PATTERN = re.compile(r"([\d,]+(?:\.\d+)?)")
_CURRENCY_BY_TITLE = {
    "US Dollar": "USD",
    "Japanese Yen": "JPY",
}
_CABIN_FORM_LABELS = {
    "Economy": "Economy Class",
    "Premium Economy": "Premium Economy Class",
}


class _JalCalendarParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, str]] = []
        self._depth = 0
        self._price_depth: int | None = None
        self._row: dict[str, str] | None = None
        self._price_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if self._row is None:
            if attributes.get("role") != "radio":
                return
            self._row = {}
            self._depth = 1
        else:
            self._depth += 1

        if tag == "time" and attributes.get("datetime"):
            self._row["date"] = attributes["datetime"] or ""
        classes = set((attributes.get("class") or "").split())
        if "base-price" in classes:
            self._price_depth = self._depth
            self._price_parts = []
        if tag == "abbr" and attributes.get("title"):
            self._row["currency_title"] = attributes["title"] or ""

    def handle_data(self, data: str) -> None:
        if self._price_depth is not None:
            self._price_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._row is None:
            return
        if self._price_depth == self._depth:
            self._row["price"] = " ".join(" ".join(self._price_parts).split())
            self._price_depth = None
            self._price_parts = []
        self._depth -= 1
        if self._depth == 0:
            self.rows.append(self._row)
            self._row = None


class JalProvider:
    """Collect official JAL one-way fares from its adjacent-date calendar."""

    name = "jal"

    def __init__(
        self,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        cabin: str = "Economy",
    ) -> None:
        if cabin not in _CABIN_FORM_LABELS:
            supported = ", ".join(_CABIN_FORM_LABELS)
            raise ValueError(f"Unsupported JAL cabin: {cabin}; expected one of: {supported}")
        self.timeout_ms = timeout_ms
        self.cabin = cabin

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
        anchor_date = min(start_date + timedelta(days=7), end_date)

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(
                    CHROME_CDP_URL, timeout=self.timeout_ms
                )
                if not browser.contexts:
                    raise ProviderSearchError(
                        "Connected to Chrome, but no browser context was found"
                    )
                default_context = browser.contexts[0]
                for page in default_context.pages:
                    if JAL_RESULTS_HOST not in page.url:
                        continue
                    page.set_default_timeout(self.timeout_ms)
                    try:
                        self._require_results_route(page, origin, destination)
                        self._require_results_cabin(page)
                    except ProviderSearchError:
                        continue
                    calendar_dates = self._calendar_dates(page)
                    if not (
                        calendar_dates
                        and min(calendar_dates) <= start_date <= max(calendar_dates)
                    ):
                        continue
                    return self._scan_calendar(
                        page, origin, destination, start_date, end_date
                    )

                page = default_context.new_page()
                page.set_default_timeout(self.timeout_ms)
                page.set_default_navigation_timeout(self.timeout_ms)
                self._open_results(page, origin, destination, anchor_date)
                return self._scan_calendar(
                    page, origin, destination, start_date, end_date
                )
        except ProviderSearchError:
            raise
        except PlaywrightTimeoutError as exc:
            raise ProviderSearchError(
                "JAL one-way fare calendar timed out before fares could be read"
            ) from exc
        except PlaywrightError as exc:
            raise ProviderSearchError(f"JAL browser search failed: {exc}") from exc

    def _open_results(
        self, page: Page, origin: str, destination: str, departure_date: date
    ) -> None:
        page.goto(JAL_BOOK_URL, wait_until="domcontentloaded", timeout=self.timeout_ms)
        page.get_by_text("One-way trip", exact=True).click()
        self._select_airport(page, "From", origin)
        self._select_airport(page, "To", destination)
        self._select_date(page, departure_date)
        self._select_cabin(page)

        nearby = page.locator("[data-testid=fare-nearby-checkbox]")
        nearby.check(force=True)
        page.get_by_label("One-way trip").get_by_role(
            "button", name="Search", exact=True
        ).click()

        language_confirm = page.get_by_role("button", name="Confirm", exact=True)
        try:
            language_confirm.wait_for(state="visible", timeout=3_000)
        except PlaywrightTimeoutError:
            pass
        else:
            page.get_by_role("radio", name="English", exact=True).first.click()
            language_confirm.click()

        page.wait_for_url(
            re.compile(rf"https://{re.escape(JAL_RESULTS_HOST)}/"),
            timeout=self.timeout_ms,
        )
        page.locator("table.calendar [role=radio]").first.wait_for(
            state="visible", timeout=self.timeout_ms
        )
        self._require_results_route(page, origin, destination)
        page.locator("body").evaluate(
            "(body, cabin) => body.dataset.travelAgentCabin = cabin",
            self.cabin,
        )

    def _select_cabin(self, page: Page) -> None:
        form_label = _CABIN_FORM_LABELS[self.cabin]
        class_button = page.get_by_role(
            "button", name=re.compile(r"^Class\s*:", re.I)
        ).first
        class_button.click()
        option = page.get_by_role("radio", name=form_label, exact=True)
        option.wait_for(state="visible")
        option.click()
        page.get_by_role("button", name="Confirm", exact=True).click()
        if form_label not in " ".join(class_button.inner_text().split()):
            raise ProviderSearchError(
                f"JAL search form did not retain {self.cabin} class"
            )

    def _select_airport(self, page: Page, label: str, airport: str) -> None:
        airport_input = page.get_by_label(label, exact=True).first
        airport_input.fill(airport)
        option = page.locator(
            f'[role=option][data-airport-id="{airport}"]:visible'
        ).first
        option.wait_for(state="visible")
        option.click()

    def _select_date(self, page: Page, departure_date: date) -> None:
        page.locator("button.date-selection-trigger").first.click()
        dialog = page.get_by_role("dialog", name="Boarding Date")
        label = departure_date.strftime("%A, %B %-d, %Y")
        for _ in range(24):
            target = dialog.locator(f'button[aria-label*="{label}"]')
            if target.count():
                target.click()
                dialog.get_by_role("button", name="Confirm", exact=True).click()
                return
            date_labels = dialog.locator(
                'button[aria-label*=","][aria-label]:not([aria-label="Previous month"]):not([aria-label="Next month"])'
            ).evaluate_all(
                "els => els.filter(el => el.offsetParent).map(el => el.getAttribute('aria-label'))"
            )
            visible_months = []
            for date_label in date_labels:
                match = re.match(
                    r"^[A-Z][a-z]+, ([A-Z][a-z]+ \d{1,2}, \d{4})",
                    date_label or "",
                )
                if match:
                    visible_months.append(
                        datetime.strptime(match.group(1), "%B %d, %Y").date()
                    )
            if not visible_months:
                break
            direction = "Previous month" if departure_date < min(visible_months) else "Next month"
            navigation = dialog.get_by_role("button", name=direction, exact=True)
            if navigation.is_disabled():
                break
            navigation.click()
            page.wait_for_timeout(1_000)
        raise ProviderSearchError(
            f"JAL date picker did not expose {departure_date.isoformat()}"
        )

    def _scan_calendar(
        self,
        page: Page,
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
    ) -> list[FareOption]:
        observed_at = datetime.now(timezone.utc)
        fares: dict[date, FareOption] = {}

        for _ in range(60):
            calendar_dates = self._calendar_dates(page)
            if not calendar_dates or min(calendar_dates) <= start_date:
                break
            previous = page.locator("#previousButton-0")
            if previous.count() == 0 or previous.is_disabled():
                break
            self._shift_week(page, previous, calendar_dates[0])

        seen_windows: set[tuple[date, ...]] = set()
        recoveries = 0
        for _ in range(80):
            try:
                self._require_results_route(page, origin, destination)
                self._require_results_cabin(page)
            except (ProviderSearchError, PlaywrightError):
                if fares and recoveries < 12:
                    recoveries += 1
                    try:
                        page = self._resume_results(
                            page, origin, destination, max(fares) + timedelta(days=7)
                        )
                    except (ProviderSearchError, PlaywrightTimeoutError, PlaywrightError):
                        break
                    else:
                        continue
                raise
            window_dates = tuple(self._calendar_dates(page))
            if not window_dates or window_dates in seen_windows:
                break
            seen_windows.add(window_dates)

            for departure_date, price, currency in self._calendar_fares(page):
                if start_date <= departure_date <= end_date:
                    fares[departure_date] = FareOption(
                        provider=self.name,
                        origin=origin,
                        destination=destination,
                        departure_date=departure_date,
                        cabin=self.cabin,
                        price=price,
                        currency=currency,
                        available_seats=None,
                        observed_at=observed_at,
                        booking_url=JAL_BOOK_URL,
                        trip_type="one_way",
                        price_kind="calendar_lowest",
                        source_freshness=f"Live JAL {self.cabin} adjacent-date fare calendar",
                    )

            if max(window_dates) >= end_date:
                break
            next_week = page.locator("#nextButton-0")
            if next_week.count() == 0 or next_week.is_disabled():
                break
            try:
                self._shift_week(page, next_week, window_dates[0])
            except (ProviderSearchError, PlaywrightTimeoutError, PlaywrightError):
                if fares and recoveries < 12:
                    recoveries += 1
                    try:
                        page = self._resume_results(
                            page, origin, destination, max(fares) + timedelta(days=7)
                        )
                    except (ProviderSearchError, PlaywrightTimeoutError, PlaywrightError):
                        break
                    else:
                        continue
                raise

        return [fares[key] for key in sorted(fares)]

    def _calendar_dates(self, page: Page) -> list[date]:
        values = page.locator(
            "table.calendar [role=radio] time[datetime]"
        ).evaluate_all("els => els.map(el => el.getAttribute('datetime'))")
        return sorted({date.fromisoformat(value) for value in values if value})

    def _calendar_fares(self, page: Page) -> list[tuple[date, float, str]]:
        fragments = page.locator("table.calendar [role=radio]").evaluate_all(
            "elements => elements.map(element => element.outerHTML)"
        )
        return parse_jal_calendar_fares("".join(fragments))

    def _shift_week(self, page: Page, button, old_first_date: date) -> None:
        button.click()
        page.wait_for_function(
            """oldDate => {
                const value = document.querySelector(
                    'table.calendar [role="radio"] time[datetime]'
                )?.getAttribute('datetime');
                return (value && value !== oldDate)
                    || document.title === 'Access Denied';
            }""",
            arg=old_first_date.isoformat(),
            timeout=min(self.timeout_ms, 10_000),
        )
        if page.locator("table.calendar").count() == 0:
            raise ProviderSearchError("JAL booking session expired during pagination")
        page.wait_for_timeout(1_200)

    def _resume_results(
        self,
        expired_page: Page,
        origin: str,
        destination: str,
        anchor_date: date,
    ) -> Page:
        expired_page.wait_for_timeout(10_000)
        page = expired_page.context.new_page()
        page.set_default_timeout(self.timeout_ms)
        page.set_default_navigation_timeout(self.timeout_ms)
        self._open_results(page, origin, destination, anchor_date)
        return page

    @staticmethod
    def _require_results_route(page: Page, origin: str, destination: str) -> None:
        origin_location = page.locator("#originLocation-0")
        destination_location = page.locator("#destinationLocation-0")
        if origin_location.count() == 0 or destination_location.count() == 0:
            raise ProviderSearchError(
                f"JAL result route could not be verified as {origin} → {destination}"
            )
        origin_text = " ".join(origin_location.inner_text().split())
        destination_text = " ".join(destination_location.inner_text().split())
        if (
            RESULT_ROUTE_MARKERS[origin] not in origin_text
            or RESULT_ROUTE_MARKERS[destination] not in destination_text
        ):
            raise ProviderSearchError(
                f"JAL result route could not be verified as {origin} → {destination}"
            )

    def _require_results_cabin(self, page: Page) -> None:
        cabin = page.locator("body").get_attribute("data-travel-agent-cabin")
        if cabin != self.cabin:
            raise ProviderSearchError(
                f"JAL result cabin could not be verified as {self.cabin}"
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
        supported = (
            origin in BAY_AREA_AIRPORTS and destination in JAPAN_AIRPORTS
        ) or (
            origin in JAPAN_AIRPORTS and destination in BAY_AREA_AIRPORTS
        )
        if not supported:
            raise ProviderSearchError(
                "JAL routes must be between SFO/SJC and HND/NRT/KIX"
            )
        if end_date < start_date:
            raise ProviderSearchError(
                "JAL scan end date must be on or after its start date"
            )
        if start_date < date.today():
            raise ProviderSearchError("JAL departure date cannot be in the past")
        if passengers != 1:
            raise ProviderSearchError("JAL search currently supports exactly one adult")
        return origin, destination


def parse_jal_calendar_fares(html: str) -> list[tuple[date, float, str]]:
    parser = _JalCalendarParser()
    parser.feed(html)
    parsed: list[tuple[date, float, str]] = []
    for row in parser.rows:
        date_value = row.get("date")
        price_match = _PRICE_PATTERN.search(row.get("price", ""))
        if not date_value or price_match is None:
            continue
        currency = _CURRENCY_BY_TITLE.get(row.get("currency_title", ""), "USD")
        parsed.append(
            (
                date.fromisoformat(date_value),
                float(price_match.group(1).replace(",", "")),
                currency,
            )
        )
    return parsed
