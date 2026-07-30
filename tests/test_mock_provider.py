from __future__ import annotations

from datetime import date

from travel_agent.providers import MockProvider, SearchQuery


def test_mock_provider_returns_fake_fares() -> None:
    provider = MockProvider()
    query = SearchQuery(origin="sfo", destination="nrt", departure_date=date(2026, 10, 15))

    fares = provider.search(query)

    assert len(fares) == 2
    assert fares[0].provider == "mock"
    assert fares[0].origin == "SFO"
    assert fares[0].destination == "NRT"
    assert fares[0].price > 0
