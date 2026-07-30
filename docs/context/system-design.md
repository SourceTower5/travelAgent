# Travel Agent System Design

Date: 2026-07-29
Runtime repo: /home/jimmyphan/travelAgent

## Existing Architecture
- 	ravel_agent.cli: argparse CLI entry point with check command.
- 	ravel_agent.providers.base: provider protocol plus SearchQuery, FareOption, and provider error type.
- 	ravel_agent.providers.mock: deterministic test/demo provider.
- 	ravel_agent.providers.zipair: Playwright-based ZIPAIR provider that currently needs to be aligned to the real homepage and booking calendar flow.
- 	ravel_agent.sanitize: removes booking URL/raw implementation detail before LLM use.
- 	ravel_agent.llm: LiteLLM fallback summarizer over sanitized fare JSON.
- 	ravel_agent.storage: SQLAlchemy/Alembic SQLite search history store.
- 	ravel_agent.models: Search and Fare ORM models.

## ZIPAIR Flow To Implement
ZIPAIR should be treated as a browser-driven public-page provider, not a plain HTTP scraper.

Target flow:

1. Open https://www.zipair.net/en.
2. Select one-way trip mode.
3. Select origin airport SFO, then destination NRT.
4. Select one adult passenger.
5. Navigate/search into https://www.zipair.net/en/booking/calendar.
6. Iterate available calendar dates from the run date through 2026-12-31.
7. Repeat the same workflow for origin SJC to destination NRT.
8. Extract fare rows for economy/standard and full-flat cabins when available.
9. Return structured FareOption values only.

If ZIPAIR changes selectors, blocks automation, or does not expose structured fare data, the provider should raise ProviderSearchError with a clear local-only message.

## Safety Boundary
Provider code may touch browser automation, public pages, and raw page content. Sanitizer and LLM layers must never receive credentials, cookies, browser storage, auth files, raw HTML, screenshots of private pages, or private account data. Any future provider requiring auth should keep auth local and expose only structured public-safe result objects.

## Recommended Next Architecture
Add a ZIPAIR monitor layer above provider checks:

- TripWatch: persisted user intent: provider, origin, destination, date window, passenger count, cabin preferences, max price, enabled flag, notes.
- WatchRun: execution record for a watch: started_at, status, provider error, fare_count, cheapest fare, summary.
- FareObservation: reuse or extend current Fare model for individual observed fare options.
- ChangeDetector: compares latest sanitized fares with the previous successful run.
- Notifier protocol: starts with CLI output; later supports Notion, email, desktop, or Linear updates.

## CLI Shape
Proposed commands:

`ash
travel-agent check --provider zipair --origin SFO --destination NRT --date 2026-10-15
travel-agent zipair scan --origins SFO,SJC --destination NRT --start-date today --end-date 2026-12-31 --cabins standard,full-flat
travel-agent watch add --provider zipair --origin SFO --destination NRT --start-date today --end-date 2026-12-31 --cabins standard,full-flat
travel-agent watch list
travel-agent watch run <watch-id>
travel-agent watch run-all
travel-agent watch disable <watch-id>
`

## Data Model Sketch
- watches: id, provider, origin, destination, start_date, end_date, passengers, cabins, max_price, currency, enabled, created_at, updated_at, notes.
- watch_runs: id, watch_id, status, started_at, completed_at, provider_error, fare_count, cheapest_price, summary_json.
- ares: keep current fields and add nullable watch_run_id, or keep search_id and add a relation from search to watch.

Prefer a migration that preserves existing searches and ares history. Avoid destructive schema rewrites.

## Implementation Constraints
- Keep Python 3.12 and uv.
- Continue using SQLite, SQLAlchemy, Alembic, pytest, and Playwright.
- Continue parser fixture tests for every provider.
- Do not add a web UI in the next milestone.
- Run and test inside WSL Ubuntu, not the Windows workspace or a duplicate copy.
- Do not use plain HTTP scraping as the primary ZIPAIR strategy if direct fetch returns 403 Forbidden.

## Test Strategy
- Unit tests for date-window generation from today through 2026-12-31.
- Unit tests for watch model serialization and validation.
- Storage tests for creating watches, recording runs, and preserving previous search history.
- CLI tests for watch add/list/run using the mock provider.
- ZIPAIR parser fixture tests for economy/standard and full-flat fare cards.
- Change detection tests for price drops, price rises, no fares, and provider errors.
- Sanitizer tests proving no unsafe fields cross into LLM summaries.
