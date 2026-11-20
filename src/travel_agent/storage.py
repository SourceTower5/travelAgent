from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from travel_agent.models import Fare, Search
from travel_agent.providers.base import FareOption, SearchQuery

logger = logging.getLogger(__name__)


def _sqlite_url(database_path: str) -> str:
    return f"sqlite:///{Path(database_path).expanduser().resolve()}"


class SearchHistoryStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        self.engine = create_engine(_sqlite_url(database_path), future=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def initialize(self) -> None:
        db_path = Path(self.database_path)
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)

        alembic_config = self._alembic_config()
        unversioned_revision = self._unversioned_history_revision(self.engine)
        if unversioned_revision is not None:
            command.stamp(alembic_config, unversioned_revision)
        command.upgrade(alembic_config, "head")
        logger.info("Initialized SQLite history at %s", self.database_path)

    def save_search(self, provider: str, query: SearchQuery, fares: list[FareOption]) -> int:
        created_at = datetime.now(timezone.utc).isoformat()

        with self.session_factory() as session:
            search = Search(
                provider=provider,
                origin=query.origin.upper(),
                destination=query.destination.upper(),
                departure_date=query.departure_date.isoformat(),
                passengers=query.passengers,
                created_at=created_at,
            )
            search.fares = [
                Fare(
                    provider=fare.provider,
                    origin=fare.origin,
                    destination=fare.destination,
                    departure_date=fare.departure_date.isoformat(),
                    cabin=fare.cabin,
                    price=fare.price,
                    currency=fare.currency,
                    available_seats=fare.available_seats,
                    observed_at=fare.observed_at.isoformat(),
                    booking_url=fare.booking_url,
                    return_date=fare.return_date.isoformat() if fare.return_date else None,
                    trip_type=fare.trip_type,
                    price_kind=fare.price_kind,
                    source_freshness=fare.source_freshness,
                )
                for fare in fares
            ]
            session.add(search)
            session.commit()
            search_id = search.id

        logger.info("Saved search %s with %s fare(s)", search_id, len(fares))
        return search_id

    def count_searches(self) -> int:
        return self._count(Search)

    def count_fares(self) -> int:
        return self._count(Fare)

    def _count(self, model: type[Search] | type[Fare]) -> int:
        with self.session_factory() as session:
            count = session.scalar(select(func.count()).select_from(model))
        return int(count or 0)

    def _alembic_config(self) -> Config:
        package_dir = Path(__file__).resolve().parent
        project_dir = package_dir.parents[1]
        config = Config(str(project_dir / "alembic.ini"))
        config.set_main_option("script_location", str(package_dir / "migrations"))
        config.set_main_option("sqlalchemy.url", _sqlite_url(self.database_path))
        return config

    @staticmethod
    def _unversioned_history_revision(engine: Engine) -> str | None:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        if not {"searches", "fares"}.issubset(table_names) or "alembic_version" in table_names:
            return None

        fare_columns = {column["name"] for column in inspector.get_columns("fares")}
        round_trip_columns = {"return_date", "trip_type", "price_kind", "source_freshness"}
        if round_trip_columns.issubset(fare_columns):
            return "20260730_0002"
        return "20260709_0001"
