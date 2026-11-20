# Travel Agent Implementation Roadmap

## Completed

- Python CLI with single-date and range scans.
- ZIPAIR Standard and Full-Flat calendar collection.
- Official JAL Economy and Premium Economy calendar collection.
- Cached and live ANA collection paths.
- ANA/JAL-filtered Google Flights collection.
- SQLite history with Alembic migrations.
- Read-only multi-provider, cross-year fare dashboard.
- Safe provider parser fixtures and sanitizer tests.

## Next: Saved Watches

- Add `TripWatch` and `WatchRun` models with a non-destructive migration.
- Create, list, disable, and run saved watches.
- Record provider errors, fare counts, and cheapest observations.
- Preserve existing search and fare history.

## Next: Change Detection

- Compare the latest successful run with the previous successful run.
- Detect price drops, price increases, newly available cabins, and no-fare days.
- Produce stable sanitized comparison JSON.

## Later: Scheduling and Notifications

- Document non-interactive cron or task-scheduler execution.
- Add a local log/CLI notifier first.
- Keep external notification integrations optional.

## Deferred

- Round-trip official JAL scanning.
- Automatic booking or account login.
- Anti-bot bypasses.
