from __future__ import annotations

from datetime import date, datetime, timezone

from travel_agent.providers import FareOption
from travel_agent.sanitize import sanitize_fares


def test_sanitize_fares_excludes_private_fields_and_urls() -> None:
    fare = FareOption(
        provider="mock",
        origin="SFO",
        destination="NRT",
        departure_date=date(2026, 10, 15),
        cabin="economy",
        price=640.0,
        currency="USD",
        available_seats=7,
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        booking_url="https://example.com/private-booking",
    )

    sanitized = sanitize_fares([fare])

    assert sanitized == [
        {
            "provider": "mock",
            "origin": "SFO",
            "destination": "NRT",
            "departure_date": "2026-10-15",
            "return_date": None,
            "trip_type": "one_way",
            "cabin": "economy",
            "price": 640.0,
            "price_kind": "displayed",
            "currency": "USD",
            "available_seats": 7,
            "observed_at": "2026-01-01T00:00:00+00:00",
            "source_freshness": None,
        }
    ]
    assert "booking_url" not in sanitized[0]
