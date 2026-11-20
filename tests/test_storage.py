from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from alembic import command

from travel_agent.providers import FareOption, MockProvider, SearchQuery
from travel_agent.storage import SearchHistoryStore


def test_storage_initializes_and_saves_search(tmp_path) -> None:
    db_path = tmp_path / "history.sqlite"
    store = SearchHistoryStore(str(db_path))
    provider = MockProvider()
    query = SearchQuery(origin="SFO", destination="NRT", departure_date=date(2026, 10, 15))
    fares = provider.search(query)

    store.initialize()
    search_id = store.save_search(provider.name, query, fares)

    assert search_id == 1
    assert store.count_searches() == 1
    assert store.count_fares() == 2


def test_storage_stamps_legacy_schema(tmp_path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    schema_path = Path(__file__).parents[1] / "src" / "travel_agent" / "schema.sql"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))

    store = SearchHistoryStore(str(db_path))
    store.initialize()

    with sqlite3.connect(db_path) as conn:
        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()

    assert revision == ("20260730_0002",)


def test_storage_upgrades_versioned_v1_schema(tmp_path) -> None:
    db_path = tmp_path / "versioned-v1.sqlite"
    store = SearchHistoryStore(str(db_path))
    command.upgrade(store._alembic_config(), "20260709_0001")

    store.initialize()

    with sqlite3.connect(db_path) as conn:
        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        columns = {row[1] for row in conn.execute("PRAGMA table_info(fares)")}

    assert revision == ("20260730_0002",)
    assert {"return_date", "trip_type", "price_kind", "source_freshness"} <= columns


def test_storage_upgrades_unversioned_v1_schema(tmp_path) -> None:
    db_path = tmp_path / "unversioned-v1.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                departure_date TEXT NOT NULL,
                passengers INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE fares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                departure_date TEXT NOT NULL,
                cabin TEXT NOT NULL,
                price REAL NOT NULL,
                currency TEXT NOT NULL,
                available_seats INTEGER,
                observed_at TEXT NOT NULL,
                booking_url TEXT,
                FOREIGN KEY (search_id) REFERENCES searches (id)
            );
            """
        )

    store = SearchHistoryStore(str(db_path))
    store.initialize()

    with sqlite3.connect(db_path) as conn:
        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        columns = {row[1] for row in conn.execute("PRAGMA table_info(fares)")}

    assert revision == ("20260730_0002",)
    assert {"return_date", "trip_type", "price_kind", "source_freshness"} <= columns


def test_storage_saves_round_trip_fare_fields(tmp_path) -> None:
    db_path = tmp_path / "ana.sqlite"
    store = SearchHistoryStore(str(db_path))
    query = SearchQuery("SFO", "NRT", date(2026, 8, 26))
    fare = FareOption(
        provider="ana",
        origin="SFO",
        destination="NRT",
        departure_date=date(2026, 8, 26),
        return_date=date(2026, 9, 8),
        trip_type="round_trip",
        cabin="Economy",
        price=1058.0,
        price_kind="from",
        currency="USD",
        available_seats=None,
        observed_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        source_freshness="Viewed 1 day ago",
    )

    store.initialize()
    store.save_search("ana", query, [fare])

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT return_date, trip_type, price_kind, source_freshness FROM fares"
        ).fetchone()

    assert row == ("2026-09-08", "round_trip", "from", "Viewed 1 day ago")
