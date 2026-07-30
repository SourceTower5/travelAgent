from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class SearchQuery:
    origin: str
    destination: str
    departure_date: date
    passengers: int = 1


@dataclass(frozen=True)
class FareOption:
    provider: str
    origin: str
    destination: str
    departure_date: date
    cabin: str
    price: float
    currency: str
    available_seats: int | None
    observed_at: datetime
    booking_url: str | None = None


class ProviderSearchError(RuntimeError):
    """Raised when a provider cannot complete a public availability search."""


class TravelProvider(Protocol):
    name: str

    def search(self, query: SearchQuery) -> list[FareOption]:
        """Return structured fare data without exposing credentials or raw pages."""
