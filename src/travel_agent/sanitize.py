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
            "cabin": fare.cabin,
            "price": fare.price,
            "currency": fare.currency,
            "available_seats": fare.available_seats,
            "observed_at": fare.observed_at.isoformat(),
        }
        for fare in fares
    ]
