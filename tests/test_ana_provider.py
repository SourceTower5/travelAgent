from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from travel_agent.providers import ProviderSearchError, SearchQuery
from travel_agent.providers.ana import AnaProvider, parse_ana_fares


FIXTURE = Path("tests/fixtures/ana_deals.html").read_text(encoding="utf-8")


def test_parse_ana_round_trip_deals_from_fixture() -> None:
    observed_at = datetime(2026, 7, 30, 21, 0, tzinfo=timezone.utc)

    fares = parse_ana_fares(FIXTURE, observed_at, "https://flights.ana.co.jp/example")

    assert len(fares) == 4
    assert fares[0].provider == "ana"
    assert fares[0].origin == "SFO"
    assert fares[0].destination == "NRT"
    assert fares[0].departure_date == date(2026, 8, 26)
    assert fares[0].return_date == date(2026, 9, 8)
    assert fares[0].trip_type == "round_trip"
    assert fares[0].cabin == "Economy"
    assert fares[0].price == 1058.0
    assert fares[0].price_kind == "from"
    assert fares[0].currency == "USD"
    assert fares[0].available_seats is None
    assert fares[0].observed_at == observed_at
    assert fares[0].source_freshness == "Viewed 1 day ago"

    assert fares[1].destination == "KIX"
    assert fares[1].departure_date == date(2026, 9, 22)
    assert fares[1].return_date == date(2026, 10, 14)
    assert fares[1].price == 1232.0


def test_ana_range_fetches_once_and_filters_country_deals() -> None:
    fetched_urls: list[str] = []

    def fetch(url: str) -> str:
        fetched_urls.append(url)
        return FIXTURE

    provider = AnaProvider(fetch_html=fetch)
    fares = provider.search_range("sfo", "japan", date(2026, 9, 1), date(2026, 9, 30))

    assert fetched_urls == [
        "https://flights.ana.co.jp/en-us/flights-from-san-francisco-to-japan"
    ]
    assert [fare.destination for fare in fares] == ["KIX", "HND", "OSA"]


def test_ana_single_date_search_filters_specific_airport() -> None:
    provider = AnaProvider(fetch_html=lambda _: FIXTURE)
    query = SearchQuery("SFO", "NRT", date(2026, 8, 26))

    fares = provider.search(query)

    assert len(fares) == 1
    assert fares[0].destination == "NRT"


def test_ana_rejects_unsupported_passenger_count() -> None:
    provider = AnaProvider(fetch_html=lambda _: FIXTURE)

    with pytest.raises(ProviderSearchError, match="exactly one passenger"):
        provider.search_range("SFO", "JP", date(2026, 8, 1), date(2026, 9, 30), passengers=2)


def test_ana_rejects_sjc_osaka_route() -> None:
    provider = AnaProvider(fetch_html=lambda _: FIXTURE)

    with pytest.raises(ProviderSearchError, match="HND, NRT"):
        provider.search_range("SJC", "OSA", date(2026, 8, 1), date(2026, 9, 30))


def test_ana_raises_clear_error_when_deal_markup_changes() -> None:
    provider = AnaProvider(fetch_html=lambda _: "<html><body>No deals</body></html>")

    with pytest.raises(ProviderSearchError, match="page structure may have changed"):
        provider.search_range("SFO", "JP", date(2026, 8, 1), date(2026, 9, 30))
