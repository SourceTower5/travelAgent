from __future__ import annotations

from datetime import date

from travel_agent.cli import _dates_between, _matches_cabin_group, _parse_airports, _parse_cabin_groups, build_parser


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
    assert _matches_cabin_group("Standard", {"economy"})
    assert not _matches_cabin_group("ZIP Full-Flat", {"economy"})
    assert _matches_cabin_group("ZIP Full-Flat", {"full-flat"})
    assert list(_dates_between(date(2026, 12, 30), date(2026, 12, 31))) == [
        date(2026, 12, 30),
        date(2026, 12, 31),
    ]
