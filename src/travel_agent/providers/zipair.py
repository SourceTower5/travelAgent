from __future__ import annotations

import logging
import os
import re
from contextlib import contextmanager
from datetime import date, datetime, timezone
from html import escape
from html.parser import HTMLParser
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from travel_agent.providers.base import FareOption, ProviderSearchError, SearchQuery

logger = logging.getLogger(__name__)

ZIPAIR_SEARCH_URL = "https://www.zipair.net/en/"
DEFAULT_TIMEOUT_MS = 15_000
CHROME_CDP_URL = os.getenv("CHROME_CDP_URL", "http://127.0.0.1:9222")
ZIPAIR_ROUTES = {
    ("SFO", "NRT"),
    ("SJC", "NRT"),
    ("NRT", "SFO"),
    ("NRT", "SJC"),
}
ZIPAIR_AIRPORT_NAMES = {
    "NRT": "Tokyo",
    "SFO": "San Francisco",
    "SJC": "San Jose",
}


def find_zipair_page(pages: list[Page]) -> Page:
    for page in pages:
        if "zipair.net" in page.url:
            return page
    raise ProviderSearchError(
        "No open ZIPAIR tab was found. Start Google Chrome with remote debugging, "
        "open https://www.zipair.net/en/, then run this command again."
    )


def is_access_denied(page: Page) -> bool:
    try:
        body_text = page.locator("body").inner_text(timeout=5_000).lower()
    except Exception:
        return True
    denial_phrases = (
        "403 forbidden",
        "access denied",
        "request blocked",
        "you don't have permission",
    )
    return any(phrase in body_text for phrase in denial_phrases)


def page_http_status(page: Page) -> int | None:
    """Read a status exposed by the existing page without navigating it."""
    try:
        status = page.evaluate(
            """() => {
                const entry = performance.getEntriesByType('navigation')[0];
                return entry && 'responseStatus' in entry ? entry.responseStatus : null;
            }"""
        )
    except Exception:
        return None
    return status if isinstance(status, int) else None


class ZipairProvider:
    name = "zipair"

    def __init__(self, search_url: str = ZIPAIR_SEARCH_URL, timeout_ms: int = DEFAULT_TIMEOUT_MS, interactive: bool = False) -> None:
        self.search_url = search_url
        self.timeout_ms = timeout_ms
        self.interactive = interactive
        self._access_verified = False

    def search(self, query: SearchQuery) -> list[FareOption]:
        logger.info(
            "Searching ZIPAIR fares for %s-%s on %s",
            query.origin,
            query.destination,
            query.departure_date.isoformat(),
        )
        observed_at = datetime.now(timezone.utc)

        html = self._search_html(query)

        fares = parse_zipair_fares(html, query, observed_at)
        if not fares:
            raise ProviderSearchError(
                "ZIPAIR page loaded, but no structured fare data was found. "
                "The page structure may have changed."
            )
        return fares

    def search_range(
        self,
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
        passengers: int = 1,
    ) -> list[FareOption]:
        if end_date < start_date:
            raise ProviderSearchError("ZIPAIR scan end date must be on or after its start date")
        self._validate_query(SearchQuery(origin, destination, start_date, passengers))

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(CHROME_CDP_URL, timeout=self.timeout_ms)
                if not browser.contexts:
                    raise ProviderSearchError(
                        "Connected to Chrome, but no browser context was found. "
                        "Start Google Chrome with remote debugging and open ZIPAIR first."
                    )
                page = find_zipair_page(browser.contexts[0].pages)
                page.set_default_timeout(self.timeout_ms)
                page.set_default_navigation_timeout(self.timeout_ms)
                print(f"Attached to ZIPAIR tab: {page.url} | title {page.title()!r}")
                if self.interactive and not self._access_verified:
                    input("Complete any normal ZIPAIR access interaction in Chrome, then press Enter: ")
                    self._access_verified = True
                if is_access_denied(page):
                    raise ProviderSearchError("ZIPAIR shows an access-denied page; the calendar scan cannot continue")
                query = SearchQuery(origin, destination, start_date, passengers)
                self._open_calendar(page, query)
                return self._extract_calendar_range(page, origin, destination, start_date, end_date)
        except ProviderSearchError:
            raise
        except PlaywrightTimeoutError as exc:
            raise ProviderSearchError("ZIPAIR calendar scan timed out before fares could be read") from exc
        except PlaywrightError as exc:
            raise ProviderSearchError(f"ZIPAIR CDP calendar scan failed: {exc}") from exc

    def _search_html(self, query: SearchQuery) -> str:
        self._validate_query(query)
        try:
            with _no_timeout():
                with sync_playwright() as playwright:
                    browser = playwright.chromium.connect_over_cdp(CHROME_CDP_URL, timeout=self.timeout_ms)
                    if not browser.contexts:
                        raise ProviderSearchError(
                            "Connected to Chrome, but no browser context was found. "
                            "Start Google Chrome with remote debugging and open ZIPAIR first."
                        )
                    context = browser.contexts[0]
                    page = find_zipair_page(context.pages)
                    page.set_default_timeout(self.timeout_ms)
                    page.set_default_navigation_timeout(self.timeout_ms)
                    print(
                        f"Attached to ZIPAIR tab: HTTP {page_http_status(page) or 'unknown'} "
                        f"| URL {page.url} | title {page.title()!r}"
                    )
                    if self.interactive:
                        input("Complete any normal ZIPAIR interaction in Chrome, then press Enter to continue: ")
                        print(
                            f"ZIPAIR tab after manual step: HTTP {page_http_status(page) or 'unknown'} "
                            f"| URL {page.url} | title {page.title()!r}"
                        )
                    if is_access_denied(page):
                        raise ProviderSearchError(
                            "ZIPAIR still shows an access-denied page after the manual step. "
                            "The calendar flow cannot continue."
                        )
                    if (
                        "/booking/calendar" not in page.url
                        or not self._calendar_matches_route(page, query.origin, query.destination)
                    ):
                        try:
                            self._open_calendar(page, query)
                        except (PlaywrightTimeoutError, ProviderSearchError):
                            if not self.interactive:
                                raise
                            print(
                                "ZIPAIR's live form controls did not match the current selectors. "
                                "Complete the requested one-way route, one-adult, and date selection "
                                "and submit it manually in the attached Chrome tab."
                            )
                            input("After the calendar page is open in Chrome, press Enter to continue: ")
                    page.wait_for_load_state("domcontentloaded", timeout=self.timeout_ms)
                    page.wait_for_timeout(500)
                    if is_access_denied(page):
                        raise ProviderSearchError(
                            "ZIPAIR shows an access-denied page on the calendar. "
                            "Fare extraction cannot continue."
                        )
                    return self._extract_calendar_fares_html(page, query)
        except ProviderSearchError:
            raise
        except PlaywrightTimeoutError as exc:
            raise ProviderSearchError("ZIPAIR search timed out before fares could be read") from exc
        except PlaywrightError as exc:
            raise ProviderSearchError(f"ZIPAIR browser automation failed: {exc}") from exc


    def _open_calendar(self, page: Page, query: SearchQuery) -> None:
        if (
            "/booking/calendar" in page.url
            and self._calendar_matches_route(page, query.origin, query.destination)
        ):
            return

        page.goto(self.search_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        page.wait_for_timeout(1_000)
        if is_access_denied(page):
            raise ProviderSearchError(
                "ZIPAIR shows an access-denied homepage; automated route selection cannot continue"
            )
        self._fill_search_form(page, query)
        self._advance_to_calendar(page)
        page.wait_for_load_state("domcontentloaded", timeout=self.timeout_ms)
        page.wait_for_timeout(1_500)
        if not self._calendar_matches_route(page, query.origin, query.destination):
            raise ProviderSearchError(
                f"ZIPAIR opened a calendar that does not match {query.origin} → {query.destination}"
            )

    def _fill_search_form(self, page: Page, query: SearchQuery) -> None:
        origin = query.origin.upper()
        destination = query.destination.upper()
        self._click_if_present(page, r"one.?way|one way")
        self._select_airport(page, r"origin|from|departure", origin)
        self._select_airport(page, r"destination|to|arrival", destination)

        search_button = page.get_by_role("button", name=re.compile(r"search|find flights?|show flights?", re.I))
        if search_button.count() == 0:
            search_button = page.get_by_role("link", name=re.compile(r"search flight", re.I))
        if search_button.count() == 0:
            search_button = page.locator("button.button", has_text=re.compile(r"search flight", re.I))
        if search_button.count() == 0:
            raise ProviderSearchError("ZIPAIR search form could not be submitted: search button was not found")
        try:
            search_button.first.click(timeout=min(self.timeout_ms, 3_000))
        except PlaywrightTimeoutError:
            if page.locator(".app-popup:visible").count() == 0:
                raise

    def _advance_to_calendar(self, page: Page) -> None:
        for _ in range(6):
            if "/booking/calendar" in page.url:
                return

            passport_dialog = page.locator(".app-popup:visible")
            if passport_dialog.count() > 0:
                next_button = passport_dialog.get_by_role("button", name="Next", exact=True)
                if next_button.count() == 0:
                    raise ProviderSearchError("ZIPAIR opened an unexpected pre-calendar dialog")
                next_button.first.click(timeout=self.timeout_ms)
                page.wait_for_timeout(750)
                continue

            if "/booking/people" in page.url:
                adult_control = page.get_by_role("button", name="Decrease Adult", exact=True)
                try:
                    adult_control.first.wait_for(state="visible", timeout=self.timeout_ms)
                except PlaywrightTimeoutError:
                    raise ProviderSearchError("ZIPAIR passenger page did not expose the adult controls")
                next_button = page.get_by_role("button", name="Next", exact=True)
                if next_button.count() == 0:
                    raise ProviderSearchError("ZIPAIR passenger page did not expose its Next button")
                next_button.first.click(timeout=self.timeout_ms)
                page.wait_for_url(re.compile(r"/booking/calendar", re.I), timeout=self.timeout_ms)
                return

            page.wait_for_timeout(750)

        raise ProviderSearchError(
            f"ZIPAIR did not advance from route selection to the calendar; current URL: {page.url}"
        )

    def _extract_calendar_fares_html(self, page: Page, query: SearchQuery) -> str:
        self._require_calendar_route(page, query.origin, query.destination)
        fare_cards: list[str] = []
        departure_date = query.departure_date.isoformat()
        for cabin in ("Standard", "ZIP Full-Flat"):
            self._require_calendar_route(page, query.origin, query.destination)
            cabin_button = page.get_by_role("button", name=cabin, exact=True)
            if cabin_button.count() == 0:
                logger.warning("ZIPAIR calendar did not expose the %s cabin selector", cabin)
                continue
            cabin_locator = cabin_button.first
            if "-active" not in (cabin_locator.get_attribute("class") or ""):
                cabin_locator.click(timeout=self.timeout_ms)
                page.wait_for_timeout(1_500)
            if "-active" not in (cabin_locator.get_attribute("class") or ""):
                logger.warning("ZIPAIR calendar did not activate the %s cabin", cabin)
                continue

            date_button = page.locator(f'button[data-fulldate="{departure_date}"]')
            if date_button.count() == 0:
                continue
            text = date_button.first.inner_text(timeout=self.timeout_ms)
            aria_label = date_button.first.get_attribute("aria-label") or ""
            if not aria_label.lower().startswith(cabin.lower()):
                logger.warning("ZIPAIR calendar did not finish switching to the %s cabin", cabin)
                continue
            price_match = re.search(r"(?:US\$|¥)\s*([\d,.]+)", text)
            if price_match is None:
                continue
            price = float(price_match.group(1).replace(",", ""))
            currency = "USD" if "US$" in text else "JPY" if "¥" in text else "USD"
            fare_cards.append(
                '<article data-testid="fare-card" '
                f'data-origin="{escape(query.origin.upper())}" '
                f'data-destination="{escape(query.destination.upper())}" '
                f'data-cabin="{escape(cabin)}" '
                f'data-price="{price}" '
                f'data-currency="{currency}"></article>'
            )
        return "<html><body>" + "".join(fare_cards) + "</body></html>"

    def _extract_calendar_range(
        self,
        page: Page,
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
    ) -> list[FareOption]:
        self._require_calendar_route(page, origin, destination)
        observed_at = datetime.now(timezone.utc)
        fares: list[FareOption] = []
        for cabin in ("Standard", "ZIP Full-Flat"):
            self._require_calendar_route(page, origin, destination)
            if not self._activate_cabin(page, cabin):
                continue
            self._require_calendar_route(page, origin, destination)
            self._wait_for_calendar_dates(page)
            for date_button in page.locator("button[data-fulldate]").all():
                date_value = date_button.get_attribute("data-fulldate")
                if not date_value:
                    continue
                departure_date = date.fromisoformat(date_value)
                if departure_date < start_date or departure_date > end_date:
                    continue
                text = date_button.inner_text(timeout=self.timeout_ms)
                price_match = re.search(r"(?:US\$|¥)\s*([\d,.]+)", text)
                if price_match is None:
                    continue
                fares.append(
                    FareOption(
                        provider=self.name,
                        origin=origin.upper(),
                        destination=destination.upper(),
                        departure_date=departure_date,
                        cabin=cabin,
                        price=float(price_match.group(1).replace(",", "")),
                        currency="USD" if "US$" in text else "JPY",
                        available_seats=None,
                        observed_at=observed_at,
                        booking_url=None,
                    )
                )
        return fares

    def _wait_for_calendar_dates(self, page: Page) -> None:
        dates = page.locator("button[data-fulldate]")
        previous_signature: tuple[int, str | None] | None = None
        stable_passes = 0
        page.wait_for_timeout(2_000)
        for _ in range(10):
            count = dates.count()
            last_date = dates.last.get_attribute("data-fulldate") if count else None
            signature = (count, last_date)
            stable_passes = stable_passes + 1 if signature == previous_signature else 0
            if stable_passes >= 3:
                return
            previous_signature = signature
            if count:
                dates.last.scroll_into_view_if_needed(timeout=self.timeout_ms)
            page.wait_for_timeout(1_000)

    def _activate_cabin(self, page: Page, cabin: str) -> bool:
        cabin_button = page.get_by_role("button", name=cabin, exact=True)
        if cabin_button.count() == 0:
            logger.warning("ZIPAIR calendar did not expose the %s cabin selector", cabin)
            return False
        locator = cabin_button.first
        if "-active" not in (locator.get_attribute("class") or ""):
            locator.click(timeout=self.timeout_ms)
            page.wait_for_timeout(1_500)
        if "-active" not in (locator.get_attribute("class") or ""):
            logger.warning("ZIPAIR calendar did not activate the %s cabin", cabin)
            return False
        return True

    @classmethod
    def _calendar_matches_route(cls, page: Page, origin: str, destination: str) -> bool:
        """Require directional route evidence from controls or a compact summary.

        The whole page body is deliberately not considered. ZIPAIR renders airport
        names in menus and navigation, so body-text ordering can make a stale
        forward calendar appear to match a reverse request.
        """
        normalized_origin = origin.upper()
        normalized_destination = destination.upper()
        try:
            origin_control = page.get_by_role(
                "button", name=re.compile(r"Origin \(Country, Region\)", re.I)
            )
            destination_control = page.get_by_role(
                "button", name=re.compile(r"Destination \(Country, Region\)", re.I)
            )
            if origin_control.count() and destination_control.count():
                origin_text = origin_control.first.inner_text(timeout=5_000)
                destination_text = destination_control.first.inner_text(timeout=5_000)
                return (
                    _contains_airport_code(origin_text, normalized_origin)
                    and _contains_airport_code(destination_text, normalized_destination)
                )

            route_names = page.locator(
                ".booking-header .route .head-content, "
                ".booking-header .route-content .head-content"
            ).evaluate_all(
                """elements => elements
                    .map(element => (element.innerText || "").replace(/\\s+/g, " ").trim())
                    .filter(Boolean)"""
            )
            if any(
                _route_name_evidence_matches(text, normalized_origin, normalized_destination)
                for text in route_names
            ):
                return True

            candidates = page.locator(
                '[data-testid*="route" i], [data-testid*="flight" i], '
                '[class*="route" i], [class*="calendar-header" i], '
                '[class*="flight-info" i], main h1, main h2, main h3'
            ).evaluate_all(
                """elements => elements
                    .filter(element => {
                        const style = window.getComputedStyle(element);
                        return style.visibility !== "hidden" && style.display !== "none";
                    })
                    .map(element => (element.innerText || "").replace(/\\s+/g, " ").trim())
                    .filter(text => text.length > 0 && text.length <= 250)"""
            )
        except PlaywrightError:
            return False
        return any(
            _route_evidence_matches(text, normalized_origin, normalized_destination)
            for text in candidates
        )

    @classmethod
    def _require_calendar_route(cls, page: Page, origin: str, destination: str) -> None:
        if not cls._calendar_matches_route(page, origin, destination):
            raise ProviderSearchError(
                f"ZIPAIR calendar route could not be verified as "
                f"{origin.upper()} → {destination.upper()}; no fares were recorded"
            )

    @staticmethod
    def _validate_query(query: SearchQuery) -> None:
        route = (query.origin.upper(), query.destination.upper())
        if route not in ZIPAIR_ROUTES:
            raise ProviderSearchError(
                "ZIPAIR monitoring is restricted to SFO/SJC ↔ NRT"
            )
        if query.passengers != 1:
            raise ProviderSearchError("ZIPAIR workflow currently supports exactly one adult passenger")
        if query.departure_date < date.today():
            raise ProviderSearchError("ZIPAIR departure date cannot be in the past")

    def _click_if_present(self, page: Any, pattern: str) -> None:
        locator = page.get_by_role("tab", name=re.compile(pattern, re.I))
        if locator.count() == 0:
            locator = page.get_by_role("radio", name=re.compile(pattern, re.I))
        if locator.count() == 0:
            locator = page.get_by_text(re.compile(pattern, re.I), exact=False)
        if locator.count() > 0:
            locator.first.click(timeout=self.timeout_ms)

    def _select_airport(self, page: Any, field_pattern: str, airport: str) -> None:
        accessible_name = r"Origin \(Country, Region\)" if "origin" in field_pattern else r"Destination \(Country, Region\)"
        field = page.get_by_role("button", name=re.compile(accessible_name, re.I))
        if field.count() == 0:
            field = page.get_by_label(re.compile(field_pattern, re.I))
        if field.count() == 0:
            field = page.get_by_role("combobox", name=re.compile(field_pattern, re.I))
        if field.count() == 0:
            raise ProviderSearchError(f"ZIPAIR search form could not find {field_pattern} airport selector")
        field.first.click(timeout=self.timeout_ms)
        airport_names = {
            "SFO": r"^San Francisco\s+SFO\b",
            "SJC": r"^San Jose\s+SJC\b",
            "NRT": r"^Tokyo\s+NRT\b",
        }
        option = page.get_by_role("button", name=re.compile(airport_names[airport], re.I))
        if option.count() == 0:
            option = page.locator("button.destination-item:visible").filter(has_text=re.compile(rf"\b{airport}\b"))
        if option.count() == 0:
            raise ProviderSearchError(f"ZIPAIR airport option {airport} was not found")
        option.first.click(timeout=self.timeout_ms)

    def _set_passengers(self, page: Any, passengers: int) -> None:
        passenger = page.get_by_text(re.compile(r"passenger|adult", re.I), exact=False)
        if passenger.count() > 0:
            passenger.first.click(timeout=self.timeout_ms)
            for _ in range(max(0, passengers - 1)):
                plus = page.get_by_role("button", name=re.compile(r"plus|add|increase", re.I))
                if plus.count() == 0:
                    break
                plus.first.click(timeout=self.timeout_ms)
            done = page.get_by_role("button", name=re.compile(r"done|apply|confirm", re.I))
            if done.count() > 0:
                done.first.click(timeout=self.timeout_ms)

    def _set_departure_date(self, page: Any, departure_date: date) -> None:
        date_field = page.get_by_label(re.compile(r"departure date|departing|date", re.I))
        if date_field.count() == 0:
            date_field = page.locator("input[type='date']")
        if date_field.count() > 0:
            date_field.first.fill(departure_date.isoformat(), timeout=self.timeout_ms)
            return
        calendar = page.get_by_text(re.compile(r"departure date|select date", re.I), exact=False)
        if calendar.count() == 0:
            raise ProviderSearchError("ZIPAIR search form could not find departure date selector")
        calendar.first.click(timeout=self.timeout_ms)
        day = page.get_by_role("button", name=re.compile(rf"{departure_date.day}\b", re.I))
        if day.count() == 0:
            raise ProviderSearchError(f"ZIPAIR calendar did not expose {departure_date.isoformat()}")
        day.last.click(timeout=self.timeout_ms)

    def _fill_first_available(self, page: Any, labels: list[str], value: str) -> None:
        for label in labels:
            locator = page.get_by_label(re.compile(label, re.I))
            if locator.count() > 0:
                locator.first.fill(value, timeout=self.timeout_ms)
                return

            placeholder = page.get_by_placeholder(re.compile(label, re.I))
            if placeholder.count() > 0:
                placeholder.first.fill(value, timeout=self.timeout_ms)
                return

        raise ProviderSearchError(
            "ZIPAIR search form could not be filled. "
            f"No matching field found for labels: {', '.join(labels)}."
        )

    @staticmethod
    def _raise_if_blocked(html: str) -> None:
        lowered = html.lower()
        block_markers = [
            "attention required",
            "cloudflare",
            "sorry, you have been blocked",
            "access denied",
            "request blocked",
            "you don't have permission",
        ]
        if any(marker in lowered for marker in block_markers):
            raise ProviderSearchError(
                "ZIPAIR blocked automated access before fares could be read. "
                "Try again later or inspect the public site manually."
            )


def _contains_airport_code(value: str, airport: str) -> bool:
    return re.search(rf"(?<![A-Z]){re.escape(airport.upper())}(?![A-Z])", value.upper()) is not None


def _route_evidence_matches(value: str, origin: str, destination: str) -> bool:
    """Match two explicit IATA codes in directional order within one small UI element."""
    normalized = " ".join(value.upper().split())
    origin_match = re.search(rf"(?<![A-Z]){re.escape(origin)}(?![A-Z])", normalized)
    if origin_match is None:
        return False
    destination_match = re.search(
        rf"(?<![A-Z]){re.escape(destination)}(?![A-Z])",
        normalized[origin_match.end() :],
    )
    return destination_match is not None


def _route_name_evidence_matches(value: str, origin: str, destination: str) -> bool:
    origin_name = ZIPAIR_AIRPORT_NAMES.get(origin)
    destination_name = ZIPAIR_AIRPORT_NAMES.get(destination)
    if origin_name is None or destination_name is None:
        return False
    normalized = " ".join(value.casefold().split())
    origin_index = normalized.find(origin_name.casefold())
    destination_index = normalized.find(destination_name.casefold(), origin_index + len(origin_name))
    return origin_index >= 0 and destination_index > origin_index


class _ZipairFareHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.fares: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value for key, value in attrs if value is not None}
        test_id = attributes.get("data-testid", "")
        if test_id not in {"fare-card", "zipair-fare"}:
            return

        required = ["data-cabin", "data-price", "data-currency"]
        if all(key in attributes for key in required):
            self.fares.append(attributes)


def parse_zipair_fares(
    html: str,
    query: SearchQuery,
    observed_at: datetime | None = None,
) -> list[FareOption]:
    """Parse structured fare data from ZIPAIR result HTML.

    This parser intentionally extracts only public fare attributes. It does not
    return raw HTML, cookies, credentials, or private account data.
    """
    parser = _ZipairFareHTMLParser()
    parser.feed(html)
    timestamp = observed_at or datetime.now(timezone.utc)

    fares: list[FareOption] = []
    for item in parser.fares:
        price = _parse_price(item["data-price"])
        if price is None:
            continue

        fares.append(
            FareOption(
                provider="zipair",
                origin=item.get("data-origin", query.origin).upper(),
                destination=item.get("data-destination", query.destination).upper(),
                departure_date=query.departure_date,
                cabin=item["data-cabin"].strip(),
                price=price,
                currency=item["data-currency"].strip().upper(),
                available_seats=_parse_optional_int(item.get("data-available-seats")),
                observed_at=timestamp,
                booking_url=None,
            )
        )

    return fares


def _parse_price(value: str) -> float | None:
    match = re.search(r"[\d,.]+", value)
    if not match:
        return None
    return float(match.group(0).replace(",", ""))


def _parse_optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


@contextmanager
def _no_timeout():
    yield
