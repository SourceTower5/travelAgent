# Travel Agent Product Brief

Date: 2026-07-29
Source of truth repo: /home/jimmyphan/travelAgent

## Vision
Build a local-first personal travel agent that monitors ZIPAIR trips you care about, finds meaningful fare or availability changes, summarizes tradeoffs safely, and prepares clear next actions without leaking credentials, cookies, raw HTML, browser storage, or private account pages to cloud models.

## Current State
The project is a Python 3.12 CLI app named 	ravel-agent. It can run provider checks, store search history in SQLite, sanitize fare data, and optionally summarize sanitized fare JSON with LiteLLM. ZIPAIR support exists as a public-page provider, but the current implementation still uses generic form filling and needs to be rebuilt around ZIPAIR's actual homepage-to-calendar flow.

## Target Search Intent
The first real monitoring workflow is ZIPAIR Tokyo travel:

- Start page: https://www.zipair.net/en
- Calendar page: https://www.zipair.net/en/booking/calendar
- Origins: SFO and SJC
- Destination: NRT
- Trip type: one-way
- Passengers: 1 adult
- Cabins to capture: economy/standard and full-flat
- Date window: from the run date through 2026-12-31

## Target User
A technical solo user who wants dependable travel monitoring from a local WSL Ubuntu environment first, with the option to automate later via cron or another local scheduler.

## Jobs To Be Done
- Track ZIPAIR fares from both Bay Area origins to Tokyo Narita.
- Search a rolling/programmatic date window through the end of 2026.
- Compare economy and full-flat availability without forcing a booking decision.
- Store fare observations locally by route, date, cabin, price, currency, availability, and observed time.
- Summarize cheapest options, premium-cabin opportunities, and changes from previous observations.
- Keep sensitive browsing/session data local.

## Non-Goals For The Next Build
- No automatic purchasing or account login.
- No cloud storage of credentials, cookies, browser state, or raw HTML.
- No full web app until the local workflow is stable.
- No unsupported scraping bypasses or anti-bot evasion.

## Product Principles
- Local-first: private collection and storage happen on the user's machine.
- Provider isolation: provider modules own browser automation and parsing details.
- Sanitized AI boundary: LLMs receive only minimal structured summaries.
- Inspectable history: every recommendation should trace back to stored observations.
- Small increments: each provider or workflow should be independently testable.

## MVP Upgrade
The next useful milestone is ZIPAIR calendar monitoring:

- Add a ZIPAIR calendar workflow that starts from the public homepage, selects airports, one-way trip, one passenger, and searches through 2026-12-31.
- Search both SFO -> NRT and SJC -> NRT.
- Capture economy/standard and full-flat fares when available.
- Persist every observation and detect changes from previous observations.
- Generate a safe text summary from sanitized comparison data.
- Keep tests focused around parser fixtures, schema, sanitizer boundaries, and provider failure modes.

## Open Questions
- What default run cadence should be used: daily, twice daily, or manual until stable?
- Should notifications eventually be Notion updates, Linear comments, email, desktop notifications, or CLI/log output only?
- Should the app search beyond 2026-12-31 automatically once the calendar rolls into 2027?
