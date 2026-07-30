from __future__ import annotations

import logging
from datetime import datetime, timezone

from travel_agent.providers.base import FareOption, SearchQuery

logger = logging.getLogger(__name__)


class MockProvider:
    name = "mock"

    def search(self, query: SearchQuery) -> list[FareOption]:
        logger.info(
            "Generating mock fares for %s-%s on %s",
            query.origin,
            query.destination,
            query.departure_date.isoformat(),
        )
        observed_at = datetime.now(timezone.utc)
        return [
            FareOption(
                provider=self.name,
                origin=query.origin.upper(),
                destination=query.destination.upper(),
                departure_date=query.departure_date,
                cabin="economy",
                price=640.00,
                currency="USD",
                available_seats=7,
                observed_at=observed_at,
                booking_url=None,
            ),
            FareOption(
                provider=self.name,
                origin=query.origin.upper(),
                destination=query.destination.upper(),
                departure_date=query.departure_date,
                cabin="premium_economy",
                price=1180.00,
                currency="USD",
                available_seats=3,
                observed_at=observed_at,
                booking_url=None,
            ),
        ]
