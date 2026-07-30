# Codex Handoff: ZIPAIR Calendar Monitoring

Use this as the starting prompt for an implementation Codex thread.

## Source Of Truth
Work in the WSL Ubuntu repo:

`ash
cd /home/jimmyphan/travelAgent
`

Do not use or recreate the deleted Windows duplicate folder. The app should run and be tested in Linux/WSL.

## Goal
Implement ZIPAIR calendar monitoring for the existing Python 	ravel-agent CLI.

## Concrete ZIPAIR Search Intent
- Start page: https://www.zipair.net/en
- Calendar page: https://www.zipair.net/en/booking/calendar
- Origins: SFO and SJC
- Destination: NRT
- Trip type: one-way
- Passengers: 1 adult
- Cabins to capture: economy/standard and full-flat
- Date window: from the run date through 2026-12-31

## Current App Summary
The app already has:
- Python 3.12 project managed by uv.
- CLI entry point 	ravel-agent in src/travel_agent/cli.py.
- Provider protocol in src/travel_agent/providers/base.py.
- Mock and ZIPAIR providers.
- SQLite storage with SQLAlchemy and Alembic.
- Sanitizer that strips unsafe fields before LLM use.
- LiteLLM summarizer that accepts sanitized fare JSON only.
- Tests under 	ests/.

## Required Build
Update the ZIPAIR implementation around the real public page flow:

1. Use Playwright from WSL to open https://www.zipair.net/en.
2. Select one-way trip mode.
3. Select origin and destination airports for SFO -> NRT and SJC -> NRT.
4. Set 1 adult passenger.
5. Navigate/search into https://www.zipair.net/en/booking/calendar.
6. Iterate or collect calendar fares from the run date through 2026-12-31.
7. Capture economy/standard and full-flat fare options when available.
8. Return structured FareOption values only.
9. Persist observations locally and keep the existing check command working.

If saved watches are implemented in the same pass, use this default watch scope:

`	ext
provider: zipair
origins: SFO,SJC
destination: NRT
trip_type: one-way
passengers: 1
cabins: standard,full-flat
start_date: today
end_date: 2026-12-31
`

## Safety Requirements
- Do not send credentials, cookies, browser storage, raw HTML, private account data, screenshots of private pages, or Playwright auth files to any LLM.
- Keep browser automation inside provider modules.
- LLM summaries may receive only sanitized fare or comparison JSON.
- Do not introduce automatic booking or account login.
- Do not attempt anti-bot bypasses. If ZIPAIR blocks automation, return a clear provider error.

## Verification
Run inside WSL:

`ash
uv run pytest
uv run travel-agent check --provider mock --origin SFO --destination NRT --date 2026-10-15
uv run travel-agent check --provider zipair --origin SFO --destination NRT --date 2026-10-15
uv run travel-agent check --provider zipair --origin SJC --destination NRT --date 2026-10-15
`

If a scan command is added, verify:

`ash
uv run travel-agent zipair scan --origins SFO,SJC --destination NRT --start-date today --end-date 2026-12-31 --cabins standard,full-flat
`

## Preferred Style
Keep changes small, idiomatic to the existing code, and covered by focused tests. Favor clear provider workflow helpers and parser fixtures over a broad framework refactor.
