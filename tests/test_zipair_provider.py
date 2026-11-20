from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from travel_agent.providers import ProviderSearchError, SearchQuery
from travel_agent.providers.zipair import (
    ZipairProvider,
    _route_evidence_matches,
    parse_zipair_fares,
)


def test_parse_zipair_fares_from_fixture() -> None:
    html = Path("tests/fixtures/zipair_results.html").read_text(encoding="utf-8")
    query = SearchQuery(origin="SFO", destination="NRT", departure_date=date(2027, 3, 20))
    observed_at = datetime(2026, 11, 19, 18, 0, tzinfo=timezone.utc)

    fares = parse_zipair_fares(html, query, observed_at)

    assert len(fares) == 2
    assert fares[0].provider == "zipair"
    assert fares[0].origin == "SFO"
    assert fares[0].destination == "NRT"
    assert fares[0].departure_date == date(2027, 3, 20)
    assert fares[0].cabin == "Standard"
    assert fares[0].price == 621.50
    assert fares[0].currency == "USD"
    assert fares[0].available_seats == 5
    assert fares[0].observed_at == observed_at
    assert fares[0].booking_url is None

    assert fares[1].cabin == "ZIP Full-Flat"
    assert fares[1].price == 1725.0
    assert fares[1].available_seats == 2


def test_zipair_block_detection_raises_clear_error() -> None:
    html = "<html><title>Attention Required! | Cloudflare</title><h1>Sorry, you have been blocked</h1></html>"

    try:
        ZipairProvider._raise_if_blocked(html)
    except Exception as exc:
        assert "blocked automated access" in str(exc)
    else:
        raise AssertionError("Expected blocked access error")


def test_zipair_accepts_reverse_routes() -> None:
    query = SearchQuery(origin="NRT", destination="SJC", departure_date=date(2027, 3, 20))

    ZipairProvider._validate_query(query)


def test_zipair_accepts_2027_cherry_blossom_window() -> None:
    for departure_date in (date(2027, 3, 20), date(2027, 4, 12)):
        query = SearchQuery(origin="SFO", destination="NRT", departure_date=departure_date)

        ZipairProvider._validate_query(query)


def test_zipair_rejects_reversed_date_range_before_opening_browser() -> None:
    provider = ZipairProvider()

    with pytest.raises(ProviderSearchError, match="end date must be on or after"):
        provider.search_range("SFO", "NRT", date(2027, 4, 12), date(2027, 3, 20))


def test_zipair_route_evidence_is_directional() -> None:
    assert _route_evidence_matches("Tokyo NRT → San Jose SJC", "NRT", "SJC")
    assert not _route_evidence_matches("Tokyo NRT → San Jose SJC", "SJC", "NRT")


def test_zipair_route_evidence_requires_explicit_airport_codes() -> None:
    assert not _route_evidence_matches(
        "Tokyo and San Jose appear elsewhere on this page",
        "NRT",
        "SJC",
    )
