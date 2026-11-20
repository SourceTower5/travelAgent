from __future__ import annotations

import base64
import os
import re
from datetime import date, datetime, timezone
from urllib.parse import urlencode

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from travel_agent.providers.base import FareOption, ProviderSearchError, SearchQuery

CHROME_CDP_URL = os.getenv("CHROME_CDP_URL", "http://127.0.0.1:9222")
GOOGLE_FLIGHTS_URL = "https://www.google.com/travel/flights/search"
DEFAULT_TIMEOUT_MS = 30_000
SUPPORTED_ROUTES = {
    ("SFO", "NRT"),
    ("NRT", "SFO"),
    ("SFO", "HND"),
    ("HND", "SFO"),
}
_CARRIERS = {
    "ANA": ("NH", "ana-google"),
    "JAL": ("JL", "jal-google"),
}
_CABINS = {
    "Economy": 1,
    "Premium Economy": 2,
}
_PRICE_PATTERN = re.compile(r"([\d,]+(?:\.\d+)?)")
_THROTTLE_MARKERS = (
    "our systems have detected unusual traffic",
    "not a robot",
    "verify you are human",
    "sorry, you have been blocked",
)


class GoogleFlightsProvider:
    """Collect airline-filtered one-way fares from Google Flights price graphs."""

    def __init__(self, carrier: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> None:
        normalized = carrier.strip().upper()
        if normalized not in _CARRIERS:
            raise ValueError(f"Unsupported Google Flights carrier: {carrier}")
        self.carrier = normalized
        self.carrier_code, self.name = _CARRIERS[normalized]
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
        observed_at = datetime.now(timezone.utc)
        fares: list[FareOption] = []

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(
                    CHROME_CDP_URL, timeout=self.timeout_ms
                )
                if not browser.contexts:
                    raise ProviderSearchError(
                        "Connected to Chrome, but no browser context was found"
                    )
                page = browser.contexts[0].new_page()
                page.set_default_timeout(self.timeout_ms)
                page.set_default_navigation_timeout(self.timeout_ms)
                for cabin in _CABINS:
                    cabin_fares = self._collect_cabin(
                        page,
                        origin,
                        destination,
                        start_date,
                        end_date,
                        cabin,
                        observed_at,
                    )
                    fares.extend(cabin_fares)
                return fares
        except ProviderSearchError:
            raise
        except PlaywrightTimeoutError as exc:
            raise ProviderSearchError(
                f"Google Flights timed out while collecting {self.carrier} fares"
            ) from exc
        except PlaywrightError as exc:
            raise ProviderSearchError(
                f"Google Flights browser collection failed: {exc}"
            ) from exc

    def _collect_cabin(
        self,
        page: Page,
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
        cabin: str,
        observed_at: datetime,
    ) -> list[FareOption]:
        booking_url = _build_search_url(
            origin,
            destination,
            start_date,
            self.carrier_code,
        )
        page.goto(
            booking_url, wait_until="domcontentloaded", timeout=self.timeout_ms
        )
        page.wait_for_timeout(4_000)
        self._raise_if_throttled(page)

        if cabin == "Premium Economy":
            economy = page.get_by_role("combobox").filter(has_text="Economy").first
            if economy.count() == 0:
                raise ProviderSearchError(
                    "Google Flights Economy cabin selector was not found"
                )
            economy.click()
            page.get_by_role(
                "option", name="Premium economy", exact=True
            ).click()
            page.wait_for_timeout(4_000)
            self._raise_if_throttled(page)

        self._require_search_state(page, origin, destination, cabin)
        price_graph = page.get_by_role("button", name="Price graph", exact=True)
        if price_graph.count() == 0 or not price_graph.first.is_visible():
            return []
        price_graph.first.click()
        graph = page.locator('[role="region"][aria-label="Price graph"]')
        try:
            graph.wait_for(state="visible", timeout=self.timeout_ms)
            graph.locator("path.ZMv3u[data-id]").first.wait_for(
                state="attached", timeout=self.timeout_ms
            )
        except PlaywrightTimeoutError:
            self._raise_if_throttled(page)
            return []

        prices = self._read_graph(page, graph, start_date, end_date)
        cancel = page.get_by_role("button", name="Cancel", exact=True)
        if cancel.count() and cancel.first.is_visible():
            cancel.first.click()

        return [
            FareOption(
                provider=self.name,
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                cabin=cabin,
                price=price,
                currency="USD",
                available_seats=None,
                observed_at=observed_at,
                booking_url=booking_url,
                trip_type="one_way",
                price_kind="from",
                source_freshness=(
                    f"Google Flights {self.carrier}-only price graph"
                ),
            )
            for departure_date, price in sorted(prices.items())
        ]

    def _read_graph(
        self, page: Page, graph, start_date: date, end_date: date
    ) -> dict[date, float]:
        prices: dict[date, float] = {}
        seen_windows: set[tuple[str, ...]] = set()

        for _ in range(4):
            date_values = tuple(
                graph.locator("path.ZMv3u[data-id]").evaluate_all(
                    "els => els.map(el => el.getAttribute('data-id'))"
                )
            )
            if not date_values or date_values in seen_windows:
                break
            seen_windows.add(date_values)

            for value in date_values:
                if not value:
                    continue
                departure_date = date.fromisoformat(value)
                if departure_date < start_date or departure_date > end_date:
                    continue
                bar = graph.locator(f'path.ZMv3u[data-id="{value}"]')
                bar.hover(force=True)
                expected_tooltip_date = departure_date.strftime("%a, %b %-d")
                page.wait_for_function(
                    """expected => {
                        return [...document.querySelectorAll(
                            '.aJF3Zd .D11z6e .hDLiAd'
                        )].some(element => element.textContent?.trim() === expected);
                    }""",
                    arg=expected_tooltip_date,
                    timeout=2_000,
                )
                tooltip_container = page.locator(
                    ".aJF3Zd .D11z6e"
                ).filter(has_text=expected_tooltip_date).first
                price_match = _PRICE_PATTERN.search(
                    tooltip_container.locator(".YMlIz").inner_text()
                )
                if price_match is not None:
                    prices[departure_date] = float(
                        price_match.group(1).replace(",", "")
                    )

            if date_values and date.fromisoformat(date_values[-1]) >= end_date:
                break
            forward = page.get_by_role("button", name="Scroll forward", exact=True)
            if forward.count() == 0 or forward.first.is_disabled():
                break
            previous_last = date_values[-1]
            forward.first.click()
            page.wait_for_function(
                """oldLast => {
                    const bars = document.querySelectorAll(
                        '[role="region"][aria-label="Price graph"] path.ZMv3u[data-id]'
                    );
                    return bars.length && bars[bars.length - 1].getAttribute('data-id') !== oldLast;
                }""",
                arg=previous_last,
                timeout=self.timeout_ms,
            )
            page.wait_for_timeout(300)

        return prices

    def _require_search_state(
        self, page: Page, origin: str, destination: str, cabin: str
    ) -> None:
        from_input = page.get_by_role("combobox", name=re.compile("Where from"))
        to_input = page.get_by_role("combobox", name=re.compile("Where to"))
        if (
            from_input.count() == 0
            or origin not in (from_input.first.get_attribute("aria-label") or "")
            or to_input.count() == 0
            or destination not in (to_input.first.get_attribute("aria-label") or "")
        ):
            raise ProviderSearchError(
                f"Google Flights route could not be verified as {origin} → {destination}"
            )

        selected_cabins = [
            " ".join(element.inner_text().split())
            for element in page.get_by_role("combobox").all()
            if element.is_visible()
        ]
        expected_cabin = (
            "Premium economy" if cabin == "Premium Economy" else "Economy"
        )
        if expected_cabin not in selected_cabins:
            raise ProviderSearchError(
                f"Google Flights cabin could not be verified as {cabin}"
            )

        buttons = [
            element.get_attribute("aria-label") or ""
            for element in page.get_by_role("button").all()
            if element.is_visible()
        ]
        if not any(
            label.startswith(self.carrier) and "Airlines, Selected" in label
            for label in buttons
        ):
            raise ProviderSearchError(
                f"Google Flights {self.carrier}-only filter was not retained"
            )

    @staticmethod
    def _raise_if_throttled(page: Page) -> None:
        title = page.title().lower()
        body = page.locator("body").inner_text(timeout=5_000).lower()
        if "sorry" == title.strip() or any(
            marker in body for marker in _THROTTLE_MARKERS
        ):
            raise ProviderSearchError(
                "Google Flights throttled or challenged this browser; stopping collection"
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
        if (origin, destination) not in SUPPORTED_ROUTES:
            raise ProviderSearchError(
                "Google Flights routes must be SFO ↔ NRT or SFO ↔ HND"
            )
        if end_date < start_date:
            raise ProviderSearchError(
                "Google Flights scan end date must be on or after its start date"
            )
        if passengers != 1:
            raise ProviderSearchError(
                "Google Flights collection currently supports exactly one adult"
            )
        return origin, destination


def _build_search_url(
    origin: str,
    destination: str,
    departure_date: date,
    carrier_code: str,
) -> str:
    slice_message = b"".join(
        (
            _bytes_field(2, departure_date.isoformat().encode()),
            _bytes_field(6, carrier_code.encode()),
            _bytes_field(13, _airport_message(origin)),
            _bytes_field(14, _airport_message(destination)),
        )
    )
    request = b"".join(
        (
            _varint_field(1, 28),
            _varint_field(2, 2),
            _bytes_field(3, slice_message),
            _varint_field(8, 1),
            _varint_field(9, 1),
            _varint_field(14, 1),
            _bytes_field(16, b"\x08" + b"\xff" * 9 + b"\x01"),
            _varint_field(19, 2),
        )
    )
    tfs = base64.urlsafe_b64encode(request).decode().rstrip("=")
    query = urlencode(
        {
            "tfs": tfs,
            "tfu": "EgIIACIA",
            "hl": "en",
            "gl": "US",
            "curr": "USD",
        }
    )
    return f"{GOOGLE_FLIGHTS_URL}?{query}"


def _airport_message(code: str) -> bytes:
    return _varint_field(1, 1) + _bytes_field(2, code.encode())


def _bytes_field(field: int, value: bytes) -> bytes:
    return _varint((field << 3) | 2) + _varint(len(value)) + value


def _varint_field(field: int, value: int) -> bytes:
    return _varint(field << 3) + _varint(value)


def _varint(value: int) -> bytes:
    encoded = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        encoded.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(encoded)
