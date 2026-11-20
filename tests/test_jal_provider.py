from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from travel_agent.providers import ProviderSearchError
from travel_agent.providers.jal import JalProvider, parse_jal_calendar_fares


FIXTURE = Path("tests/fixtures/jal_calendar.html").read_text(encoding="utf-8")


def test_parse_jal_calendar_fares_from_fixture() -> None:
    assert parse_jal_calendar_fares(FIXTURE) == [
        (date(2027, 3, 20), 1841.0, "USD"),
        (date(2027, 3, 21), 275500.0, "JPY"),
    ]


def test_jal_supports_economy_and_premium_economy() -> None:
    assert JalProvider(cabin="Economy").cabin == "Economy"
    assert JalProvider(cabin="Premium Economy").cabin == "Premium Economy"

    with pytest.raises(ValueError, match="Unsupported JAL cabin"):
        JalProvider(cabin="Business")


def test_jal_accepts_2027_cherry_blossom_window() -> None:
    assert JalProvider._validate_search(
        "SFO", "HND", date(2027, 3, 20), date(2027, 4, 12), 1
    ) == ("SFO", "HND")


def test_jal_rejects_reversed_date_range() -> None:
    with pytest.raises(ProviderSearchError, match="end date must be on or after"):
        JalProvider._validate_search(
            "SFO", "HND", date(2027, 4, 12), date(2027, 3, 20), 1
        )
