# Travel Agent Product Brief

## Vision

Build a local-first personal travel agent that monitors public fare calendars,
stores inspectable observations, and keeps browser sessions, cookies, raw HTML,
and credentials out of cloud models.

## Current State

The Python 3.12 `travel-agent` CLI supports single-date checks and date-range
scans. It stores fare history in SQLite through SQLAlchemy and Alembic and serves
a read-only local dashboard.

Implemented collection paths include:

- ZIPAIR one-way Standard and ZIP Full-Flat calendar fares.
- Official JAL one-way Economy and Premium Economy adjacent-date fares.
- Cached ANA round-trip public deals.
- Official ANA one-way fares and ANA/JAL-filtered Google Flights fares.

Browser providers reuse a local Chrome session over CDP. They do not log in,
book travel, bypass access controls, or send browser state to an LLM.

## Current Search Intent

- Origins: SFO and SJC.
- Destinations: NRT and HND where supported.
- Passengers: one adult.
- Date windows: supplied explicitly by the user.
- Current cherry-blossom window: 2027-03-20 through 2027-04-12.
- ZIPAIR cabins: Standard and ZIP Full-Flat.
- Official JAL cabins: Economy and Premium Economy, scanned separately.
- Trip type: one-way for ZIPAIR and official JAL.

## Product Principles

- Local-first collection and storage.
- Provider modules own browser automation and parsing details.
- LLMs receive only sanitized structured summaries.
- Every displayed fare traces back to a stored observation.
- Provider failures are explicit and never masquerade as empty results.
- Each provider parser has safe, session-free fixture coverage.

## Next Milestones

- Persist saved watches and watch-run status.
- Compare observations against the previous successful run.
- Add optional local notifications and scheduling.
- Consider round-trip JAL collection as a separate provider workflow.
