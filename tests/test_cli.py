from __future__ import annotations

from datetime import date

from travel_agent.cli import (
    _dates_between,
    _matches_cabin_group,
    _normalize_destination,
    _parse_airports,
    _parse_cabin_groups,
    build_parser,
    get_provider,
)
from travel_agent.providers.jal import JalProvider


def test_scan_defaults_to_today_through_year_end() -> None:
    args = build_parser().parse_args(
        ["scan", "--provider", "mock", "--origins", "SFO,SJC", "--destination", "NRT"]
    )

    assert args.start_date == date.today().isoformat()
    assert args.end_date == date(date.today().year, 12, 31).isoformat()
    assert args.cabins == "economy,full-flat"


def test_scan_helpers_normalize_requested_values() -> None:
    assert _parse_airports("sfo, SJC, ") == ["SFO", "SJC"]
    assert _parse_cabin_groups("economy, full-flat") == {"economy", "full-flat"}
    assert _parse_cabin_groups("premium-economy") == {"premium-economy"}
    assert _matches_cabin_group("Standard", {"economy"})
    assert _matches_cabin_group("Premium Economy", {"premium-economy"})
    assert not _matches_cabin_group("Premium Economy", {"economy"})
    assert not _matches_cabin_group("ZIP Full-Flat", {"economy"})
    assert _matches_cabin_group("ZIP Full-Flat", {"full-flat"})
    assert list(_dates_between(date(2026, 12, 30), date(2026, 12, 31))) == [
        date(2026, 12, 30),
        date(2026, 12, 31),
    ]


def test_ana_provider_and_japan_country_scope_are_accepted() -> None:
    args = build_parser().parse_args(
        ["scan", "--provider", "ana", "--origins", "SFO,SJC", "--destination", "JAPAN"]
    )

    assert args.provider == "ana"
    assert _normalize_destination(args.destination) == "JP"


def test_jal_premium_economy_provider_is_selected() -> None:
    provider = get_provider("jal", cabin_groups={"premium-economy"})

    assert isinstance(provider, JalProvider)
    assert provider.cabin == "Premium Economy"
