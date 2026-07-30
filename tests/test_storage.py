from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from travel_agent.providers import MockProvider, SearchQuery
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

    assert revision == ("20260709_0001",)
