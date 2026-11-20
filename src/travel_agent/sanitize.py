from __future__ import annotations

from typing import Any

from travel_agent.providers.base import FareOption


def sanitize_fares(fares: list[FareOption]) -> list[dict[str, Any]]:
    """Return minimal fare JSON safe to send to an LLM."""
    return [
        {
            "provider": fare.provider,
            "origin": fare.origin,
            "destination": fare.destination,
            "departure_date": fare.departure_date.isoformat(),
            "return_date": fare.return_date.isoformat() if fare.return_date else None,
            "trip_type": fare.trip_type,
            "cabin": fare.cabin,
            "price": fare.price,
            "price_kind": fare.price_kind,
            "currency": fare.currency,
            "available_seats": fare.available_seats,
            "observed_at": fare.observed_at.isoformat(),
            "source_freshness": fare.source_freshness,
        }
        for fare in fares
    ]
