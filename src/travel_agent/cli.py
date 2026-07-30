from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from typing import Iterable

from travel_agent.config import load_settings
from travel_agent.logging_config import configure_logging
from travel_agent.providers import MockProvider, ProviderSearchError, SearchQuery, TravelProvider, ZipairProvider
from travel_agent.sanitize import sanitize_fares
from travel_agent.storage import SearchHistoryStore

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="travel-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="Check travel availability")
    check.add_argument("--provider", choices=["mock", "zipair"], required=True)
    check.add_argument("--origin", required=True)
    check.add_argument("--destination", required=True)
    check.add_argument("--date", required=True, help="Departure date in YYYY-MM-DD format")
    check.add_argument("--passengers", type=int, default=1)
    check.add_argument(
        "--interactive",
        action="store_true",
        help="Open a visible browser and pause for a normal public access challenge",
    )
    check.add_argument("--summarize", action="store_true", help="Summarize sanitized fare JSON with LiteLLM")

    scan = subparsers.add_parser("scan", help="Scan a date range for travel availability")
    scan.add_argument("--provider", choices=["mock", "zipair"], required=True)
    scan.add_argument("--routes", help="Comma-separated routes, e.g. SFO-NRT,SJC-NRT,NRT-SJC,NRT-SFO")
    scan.add_argument("--origins", help="Comma-separated origin airport codes (legacy single-destination mode)")
    scan.add_argument("--destination", help="Destination for --origins")
    scan.add_argument("--start-date", default=date.today().isoformat(), help="YYYY-MM-DD; defaults to today")
    scan.add_argument(
        "--end-date",
        default=date(date.today().year, 12, 31).isoformat(),
        help="YYYY-MM-DD; defaults to December 31 of the current year",
    )
    scan.add_argument("--passengers", type=int, default=1)
    scan.add_argument(
        "--cabins",
        default="economy,full-flat",
        help="Comma-separated cabin groups to retain: economy, full-flat",
    )
    scan.add_argument("--fail-fast", action="store_true", help="Stop after the first provider failure")
    scan.add_argument(
        "--interactive",
        action="store_true",
        help="Pause once for normal public access interaction before automated route scans",
    )
    scan.add_argument("--json", action="store_true", help="Print full scan results after persisting them")
    return parser


def get_provider(name: str, *, interactive: bool = False) -> TravelProvider:
    if name == "mock":
        return MockProvider()
    if name == "zipair":
        return ZipairProvider(interactive=interactive)
    raise ValueError(f"Unsupported provider: {name}")


def run_check(args: argparse.Namespace) -> int:
    settings = load_settings()
    provider = get_provider(args.provider, interactive=getattr(args, "interactive", False))
    query = SearchQuery(
        origin=args.origin.upper(),
        destination=args.destination.upper(),
        departure_date=date.fromisoformat(args.date),
        passengers=args.passengers,
    )

    try:
        fares = provider.search(query)
    except ProviderSearchError as exc:
        logger.error("%s", exc)
        print(json.dumps({"error": str(exc), "provider": provider.name}, indent=2), file=sys.stderr)
        return 1

    sanitized = sanitize_fares(fares)

    store = SearchHistoryStore(settings.database_path)
    store.initialize()
    search_id = store.save_search(provider.name, query, fares)

    result = {
        "search_id": search_id,
        "fare_count": len(fares),
        "fares": sanitized,
    }
    print(json.dumps(result, indent=2, sort_keys=True))

    if args.summarize:
        from travel_agent.llm import LLMSummarizer

        summary = LLMSummarizer(settings.ollama_model).summarize(sanitized)
        print("\nSummary:")
        print(summary)

    logger.info("Completed provider check")
    return 0


def run_scan(args: argparse.Namespace) -> int:
    settings = load_settings()
    routes = _parse_scan_routes(args.routes, args.origins, args.destination)

    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    if end_date < start_date:
        raise ValueError("--end-date must be on or after --start-date")

    cabin_groups = _parse_cabin_groups(args.cabins)
    provider = get_provider(args.provider, interactive=args.interactive)
    store = SearchHistoryStore(settings.database_path)
    store.initialize()

    fares = []
    failures: list[dict[str, str]] = []
    search_ids: list[int] = []
    if isinstance(provider, ZipairProvider):
        for origin, destination in routes:
            try:
                route_fares = provider.search_range(
                    origin=origin,
                    destination=destination,
                    start_date=start_date,
                    end_date=end_date,
                    passengers=args.passengers,
                )
            except ProviderSearchError as exc:
                failure = {
                    "origin": origin,
                    "destination": destination,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "error": str(exc),
                }
                failures.append(failure)
                logger.warning("Skipping failed ZIPAIR range scan: %s", failure)
                if args.fail_fast:
                    break
                continue

            selected_fares = [fare for fare in route_fares if _matches_cabin_group(fare.cabin, cabin_groups)]
            fares.extend(selected_fares)
            fares_by_date: dict[date, list] = {}
            for fare in selected_fares:
                fares_by_date.setdefault(fare.departure_date, []).append(fare)
            for departure_date, daily_fares in sorted(fares_by_date.items()):
                query = SearchQuery(origin, destination, departure_date, args.passengers)
                search_ids.append(store.save_search(provider.name, query, daily_fares))

        result = {
            "search_ids": search_ids,
            "fare_count": len(fares),
            "fares": sanitize_fares(fares),
            "failures": failures,
        }
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if fares or not failures else 1

    for departure_date in _dates_between(start_date, end_date):
        for origin, destination in routes:
            query = SearchQuery(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                passengers=args.passengers,
            )
            try:
                route_fares = provider.search(query)
            except ProviderSearchError as exc:
                failure = {
                    "origin": query.origin,
                    "destination": query.destination,
                    "departure_date": query.departure_date.isoformat(),
                    "error": str(exc),
                }
                failures.append(failure)
                logger.warning("Skipping failed scan: %s", failure)
                if args.fail_fast:
                    print(json.dumps({"fares": [], "failures": failures}, indent=2, sort_keys=True), file=sys.stderr)
                    return 1
                continue

            selected_fares = [fare for fare in route_fares if _matches_cabin_group(fare.cabin, cabin_groups)]
            fares.extend(selected_fares)
            search_ids.append(store.save_search(provider.name, query, selected_fares))

    result = {
        "search_ids": search_ids,
        "fare_count": len(fares),
        "fares": sanitize_fares(fares),
        "failures": failures,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if fares or not failures else 1


def _parse_airports(value: str) -> list[str]:
    return [airport.strip().upper() for airport in value.split(",") if airport.strip()]


def _parse_scan_routes(routes: str | None, origins: str | None, destination: str | None) -> list[tuple[str, str]]:
    if routes:
        parsed: list[tuple[str, str]] = []
        for route in routes.split(","):
            parts = [part.strip().upper() for part in route.split("-")]
            if len(parts) != 2 or not all(parts):
                raise ValueError(f"Invalid route {route!r}; expected ORIGIN-DESTINATION")
            parsed.append((parts[0], parts[1]))
        return parsed
    if not origins or not destination:
        raise ValueError("Provide --routes or both --origins and --destination")
    return [(origin, destination.upper()) for origin in _parse_airports(origins)]


def _parse_cabin_groups(value: str) -> set[str]:
    groups = {group.strip().lower() for group in value.split(",") if group.strip()}
    supported = {"economy", "full-flat"}
    unknown = groups - supported
    if unknown:
        raise ValueError(f"Unsupported cabin group(s): {', '.join(sorted(unknown))}")
    return groups


def _matches_cabin_group(cabin: str, groups: set[str]) -> bool:
    normalized = " ".join(cabin.lower().replace("_", " ").replace("-", " ").split())
    if "full flat" in normalized:
        return "full-flat" in groups
    return "economy" in groups


def _dates_between(start_date: date, end_date: date) -> Iterable[date]:
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def main() -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "check":
            return run_check(args)
        if args.command == "scan":
            return run_scan(args)
    except ValueError as exc:
        parser.error(str(exc))

    parser.error("Unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
