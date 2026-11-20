from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from travel_agent.providers.base import FareOption, ProviderSearchError, SearchQuery

logger = logging.getLogger(__name__)

ANA_ORIGIN_PAGES = {
    "SFO": "https://flights.ana.co.jp/en-us/flights-from-san-francisco-to-japan",
    "SJC": "https://flights.ana.co.jp/en-us/flights-from-san-jose-to-japan",
}
DEFAULT_TIMEOUT_SECONDS = 20
MAX_PAGE_BYTES = 5_000_000
JAPAN_DESTINATIONS = {"JP", "JAPAN"}
ANA_TOKYO_DESTINATIONS = {"HND", "NRT"}
ANA_SFO_OSAKA_DESTINATIONS = {"ITM", "KIX", "OSA"}

_ROW_FIELDS = {
    "origin-col",
    "destination-col",
    "fare-type-col",
    "dates-col",
    "price-col",
    "last-seen",
}
_AIRPORT_PATTERN = re.compile(r"\(([A-Z]{3})\)\s*$")
_PRICE_PATTERN = re.compile(r"([\d,]+(?:\.\d+)?)\s*([A-Z]{3})\b")


class _AnaDealsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, str]] = []
        self._row_depth = 0
        self._row: dict[str, list[str]] = {}
        self._captures: list[tuple[str, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if self._row_depth == 0:
            if tag != "tr":
                return
            self._row_depth = 1
            self._row = {}
            self._captures = []
        else:
            self._row_depth += 1

        field = attributes.get("data-test")
        if field in _ROW_FIELDS:
            self._row.setdefault(field, [])
            self._captures.append((field, self._row_depth))

    def handle_endtag(self, tag: str) -> None:
        if self._row_depth == 0:
            return

        while self._captures and self._captures[-1][1] == self._row_depth:
            self._captures.pop()
        self._row_depth -= 1

        if self._row_depth == 0:
            normalized = {
                field: " ".join(" ".join(parts).split())
                for field, parts in self._row.items()
            }
            required = {"origin-col", "destination-col", "fare-type-col", "dates-col", "price-col"}
            if required.issubset(normalized):
                self.rows.append(normalized)
            self._row = {}
            self._captures = []

    def handle_data(self, data: str) -> None:
        for field, _ in self._captures:
            self._row[field].append(data)


class AnaProvider:
    """Read ANA's public, cached AirTRFX deal pages.

    These pages publish round-trip "fares from" collected within the previous
    48 hours. Results are observations, not live inventory or booking quotes.
    """

    name = "ana"

    def __init__(
        self,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        fetch_html: Callable[[str], str] | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._fetch_html_override = fetch_html

    def search(self, query: SearchQuery) -> list[FareOption]:
        return self.search_range(
            origin=query.origin,
            destination=query.destination,
            start_date=query.departure_date,
            end_date=query.departure_date,
            passengers=query.passengers,
        )

    def search_range(
        self,
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
        passengers: int = 1,
    ) -> list[FareOption]:
        normalized_origin, normalized_destination = self._validate_search(
            origin,
            destination,
            start_date,
            end_date,
            passengers,
        )
        page_url = ANA_ORIGIN_PAGES[normalized_origin]
        logger.info(
            "Reading cached ANA deals for %s-%s from %s through %s",
            normalized_origin,
            normalized_destination,
            start_date.isoformat(),
            end_date.isoformat(),
        )
        html = self._fetch_html(page_url)
        observed_at = datetime.now(timezone.utc)
        fares = parse_ana_fares(html, observed_at=observed_at, booking_url=page_url)
        if not fares:
            raise ProviderSearchError(
                "ANA's public deal page loaded, but no structured fare rows were found. "
                "The page structure may have changed."
            )

        target_destinations = self._target_destinations(normalized_origin)
        return [
            fare
            for fare in fares
            if start_date <= fare.departure_date <= end_date
            and (
                fare.destination in target_destinations
                if normalized_destination == "JP"
                else fare.destination == normalized_destination
            )
        ]

    def _fetch_html(self, url: str) -> str:
        if self._fetch_html_override is not None:
            return self._fetch_html_override(url)

        request = Request(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "travel-agent/0.1 (personal fare monitor)",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    raise ProviderSearchError(f"ANA deal page returned HTTP {status}")
                payload = response.read(MAX_PAGE_BYTES + 1)
                if len(payload) > MAX_PAGE_BYTES:
                    raise ProviderSearchError("ANA deal page exceeded the safe response-size limit")
                charset = response.headers.get_content_charset() or "utf-8"
                html = payload.decode(charset)
        except ProviderSearchError:
            raise
        except HTTPError as exc:
            raise ProviderSearchError(f"ANA deal page returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            reason = getattr(exc, "reason", str(exc))
            raise ProviderSearchError(f"ANA deal page could not be fetched: {reason}") from exc
        except UnicodeDecodeError as exc:
            raise ProviderSearchError("ANA deal page did not contain readable HTML") from exc

        lowered = html.lower()
        if any(phrase in lowered for phrase in ("access denied", "request blocked", "403 forbidden")):
            raise ProviderSearchError("ANA blocked access to its public deal page")
        return html

    @staticmethod
    def _validate_search(
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
        passengers: int,
    ) -> tuple[str, str]:
        normalized_origin = origin.strip().upper()
        normalized_destination = destination.strip().upper()
        if normalized_origin not in ANA_ORIGIN_PAGES:
            supported = ", ".join(sorted(ANA_ORIGIN_PAGES))
            raise ProviderSearchError(f"ANA origin must be one of: {supported}")
        if normalized_destination in JAPAN_DESTINATIONS:
            normalized_destination = "JP"
        elif normalized_destination not in AnaProvider._target_destinations(normalized_origin):
            supported = ", ".join(sorted(AnaProvider._target_destinations(normalized_origin)))
            raise ProviderSearchError(
                f"ANA destination must be JP, JAPAN, or one of: {supported}"
            )
        if end_date < start_date:
            raise ProviderSearchError("ANA scan end date must be on or after its start date")
        if passengers != 1:
            raise ProviderSearchError("ANA cached deal pages currently support exactly one passenger")
        return normalized_origin, normalized_destination

    @staticmethod
    def _target_destinations(origin: str) -> set[str]:
        destinations = set(ANA_TOKYO_DESTINATIONS)
        if origin == "SFO":
            destinations.update(ANA_SFO_OSAKA_DESTINATIONS)
        return destinations


def parse_ana_fares(
    html: str,
    observed_at: datetime,
    booking_url: str | None = None,
) -> list[FareOption]:
    """Convert ANA's public deal table into structured round-trip fare observations."""

    parser = _AnaDealsParser()
    parser.feed(html)
    fares: list[FareOption] = []
    seen: set[tuple[str, str, date, date, str, float, str]] = set()

    for row in parser.rows:
        origin_match = _AIRPORT_PATTERN.search(row["origin-col"])
        destination_match = _AIRPORT_PATTERN.search(row["destination-col"])
        dates = _parse_date_range(row["dates-col"])
        price_match = _PRICE_PATTERN.search(row["price-col"])
        if origin_match is None or destination_match is None or dates is None or price_match is None:
            logger.warning("Skipping an ANA deal row with incomplete public fare fields")
            continue

        fare_type = row["fare-type-col"]
        trip_type = "round_trip" if "round trip" in fare_type.lower() else "unknown"
        cabin_parts = [part.strip() for part in fare_type.split("/") if part.strip()]
        cabin = cabin_parts[-1] if len(cabin_parts) > 1 else "Economy"
        departure_date, return_date = dates
        price = float(price_match.group(1).replace(",", ""))
        currency = price_match.group(2).upper()
        origin = origin_match.group(1)
        destination = destination_match.group(1)
        identity = (origin, destination, departure_date, return_date, cabin, price, currency)
        if identity in seen:
            continue
        seen.add(identity)

        fares.append(
            FareOption(
                provider="ana",
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date,
                trip_type=trip_type,
                cabin=cabin,
                price=price,
                price_kind="from",
                currency=currency,
                available_seats=None,
                observed_at=observed_at,
                booking_url=booking_url,
                source_freshness=row.get("last-seen") or None,
            )
        )

    return fares


def _parse_date_range(value: str) -> tuple[date, date] | None:
    parts = [part.strip() for part in value.split(" - ", maxsplit=1)]
    if len(parts) != 2:
        return None
    try:
        departure_date = datetime.strptime(parts[0], "%a %b %d, %Y").date()
        return_date = datetime.strptime(parts[1], "%a %b %d, %Y").date()
        return departure_date, return_date
    except ValueError:
        return None
