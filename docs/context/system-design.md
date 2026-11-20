# Travel Agent System Design

## Architecture

- `travel_agent.cli`: `check` and `scan` command parsing and provider dispatch.
- `travel_agent.providers.base`: shared fare types and provider protocols.
- `travel_agent.providers.zipair`: ZIPAIR homepage-to-calendar Playwright flow.
- `travel_agent.providers.jal`: official JAL Economy and Premium Economy flow.
- `travel_agent.providers.ana`: cached public ANA round-trip deals.
- `travel_agent.providers.ana_live`: official ANA one-way date-strip fares.
- `travel_agent.providers.google_flights`: airline-filtered price-graph fares.
- `travel_agent.storage` and `travel_agent.models`: SQLite history through
  SQLAlchemy and Alembic.
- `travel_agent.sanitize`: minimal JSON-safe fare summaries.
- `web/server.ts`: read-only SQLite API and static dashboard server.
- `web/public/app.ts`: provider, route, cabin, and cross-year calendar display.

## Collection Flow

```text
CLI arguments
  -> provider.search() or provider.search_range()
  -> structured FareOption values
  -> SearchHistoryStore.save_search()
  -> SQLite searches and fares
  -> GET /api/fares
  -> local dashboard
```

Range-capable providers collect a route window in one browser flow. The CLI
persists observations by route and departure date. Scans are quiet unless
`--json` is requested.

## Provider Scope

ZIPAIR supports SFO/SJC to NRT and reverse routes. It collects one-way Standard
and ZIP Full-Flat fares for dates exposed by the live calendar, without a fixed
calendar-year cap.

Official JAL supports SFO/SJC and HND/NRT/KIX in either direction. Economy and
Premium Economy use separate one-way scans. The provider verifies route and
cabin state before storing calendar-lowest observations.

Cached ANA deals are round-trip "fares from," not live inventory. They retain a
return date, price qualifier, and public freshness text. Other live providers
currently produce one-way observations.

## Safety Boundary

Browser automation, raw pages, cookies, and session state remain inside local
provider execution. The repository must not contain browser profiles, auth
state, databases, secrets, or private page captures. LLM summarization accepts
sanitized fare JSON only.

## Persistence

`Search` records the provider query. `Fare` records provider, route, departure
and optional return date, cabin, price, currency, availability, observation
time, trip type, price kind, and public freshness text. Alembic owns schema
changes; local databases are ignored by Git.

## Testing

- Parser fixtures for ZIPAIR, JAL, and cached ANA.
- CLI tests for routes, date windows, and cabin groups.
- Storage and migration compatibility tests.
- Sanitizer boundary tests.
- Live provider verification remains manual because it requires public sites
  and a local Chrome CDP session.
