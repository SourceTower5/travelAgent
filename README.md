# Travel Agent

Small personal travel availability checker. It is designed to run manually first, then later from cron or Windows Task Scheduler.

## Safety Boundary

- Credentials, cookies, raw HTML, browser storage, and private account pages must stay local.
- Browser automation and login belong inside local provider/tool functions only.
- Cloud LLM calls must receive sanitized JSON summaries only.
- `.env`, local databases, browser sessions, Playwright auth/cookie files, and logs are ignored by git.
- `.env.example` is safe to commit.

## Setup

Install Python 3.12 and `uv`, then run:

```bash
uv sync --dev
uv run playwright install
cp .env.example .env
```

Edit `.env` with any API keys you choose to use. Do not put real secrets in source files.

## Run

Mock provider:

```bash
uv run travel-agent check --provider mock --origin SFO --destination NRT --date 2027-03-20
```

ZIPAIR provider:

```bash
uv run travel-agent check --provider zipair --origin SFO --destination NRT --date YYYY-MM-DD
```

ANA cached-deal provider:

```bash
uv run travel-agent check --provider ana --origin SFO --destination NRT --date YYYY-MM-DD

uv run travel-agent scan \
  --provider ana \
  --origins SFO,SJC \
  --destination JP \
  --start-date YYYY-MM-DD \
  --end-date YYYY-MM-DD \
  --cabins economy
```

For ANA, `JP` (or `JAPAN`) retains Tokyo Narita (NRT) and Tokyo Haneda (HND)
from either Bay Area origin. For SFO it also retains any Osaka result ANA
publishes: the Osaka metropolitan code (OSA), Osaka Itami (ITM), or Osaka
Kansai (KIX). Other Japan destinations are ignored.

The ANA provider reads public, server-rendered deal pages without login or
browser automation. ANA describes these results as round-trip economy "fares
from" collected within the previous 48 hours, and warns that they may no longer
be available at booking time. The provider stores the outbound date, return
date, ANA's displayed freshness text, and the time this app scraped the page.
Treat every result as a lead to verify directly with ANA, not live inventory.
Scanning once per day is appropriate.

## ZIPAIR with an existing Google Chrome tab (WSL)

Check which Google Chrome executable is installed:

```bash
which google-chrome
which google-chrome-stable
google-chrome --version || google-chrome-stable --version
```

Start the installed executable with CDP enabled (use `google-chrome-stable` if that is the available command):

```bash
mkdir -p "$HOME/.config/travelagent-chrome"

google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.config/travelagent-chrome" \
  "https://www.zipair.net/en/"
```

Verify that CDP is reachable:

```bash
curl http://127.0.0.1:9222/json/version
```

Then, in another WSL terminal, attach to the already-open ZIPAIR tab:

```bash
cd /path/to/travelAgent
CHROME_CDP_URL=http://127.0.0.1:9222 uv run travel-agent check \
  --provider zipair --origin SFO --destination NRT \
  --date 2027-03-20
```

The provider reuses the existing Chrome context and ZIPAIR tab, selects the route and default one-adult passenger automatically, and leaves Chrome open when it disconnects. Add `--interactive` only when you need one pause for a normal public access interaction before automation continues.

Scan both requested Bay Area origins through a specific date window, keeping
both standard/economy and ZIP Full-Flat fares:

```bash
uv run travel-agent scan \
  --provider zipair \
  --routes SFO-NRT,SJC-NRT \
  --start-date 2027-03-20 \
  --end-date 2027-04-12 \
  --cabins economy,full-flat
```

The ZIPAIR provider accepts future dates exposed by the live booking calendar;
it is not capped to a particular calendar year.

## Official JAL with an existing Google Chrome session

The official JAL provider uses the same Chrome CDP connection. It collects
one-way adjacent-date calendar fares for one adult. Run Economy and Premium
Economy as separate scans:

```bash
CHROME_CDP_URL=http://127.0.0.1:9222 uv run travel-agent scan \
  --provider jal \
  --routes SFO-HND,SFO-NRT,SJC-HND,SJC-NRT \
  --start-date 2027-03-20 \
  --end-date 2027-04-12 \
  --cabins economy

CHROME_CDP_URL=http://127.0.0.1:9222 uv run travel-agent scan \
  --provider jal \
  --routes SFO-HND,SFO-NRT,SJC-HND,SJC-NRT \
  --start-date 2027-03-20 \
  --end-date 2027-04-12 \
  --cabins premium-economy
```

Scans accept the default one-adult passenger and save available observations
to the local SQLite database. The default path is `travel_agent.sqlite` in the
project directory; set `TRAVEL_AGENT_DB` to use another persistent path.

Scans are quiet by default. Add `--json` only when you want the complete fare payload printed in the terminal.

## Local fare dashboard

Start the read-only TypeScript dashboard:

```bash
cd /path/to/travelAgent
npm run dashboard
```

Open `http://127.0.0.1:4173` in your regular Chrome browser. The dashboard
reads `travel_agent.sqlite` directly and displays the latest stored ZIPAIR,
official JAL, and airline-filtered Google Flights observations. Cached ANA
round-trip "fares from" are stored but are not included in the current dashboard
query. To use a different database:

```bash
TRAVEL_AGENT_DB=/path/to/travel_agent.sqlite npm run dashboard
```

The ZIPAIR provider uses Playwright against the public site only. It does not log in, does not use credentials, and does not send raw HTML to any LLM. If ZIPAIR blocks automation or changes its page structure, the command exits with a clear provider error instead of returning scraped private or unsafe data.

Use a custom database path:

```bash
TRAVEL_AGENT_DB=data/travel_agent.sqlite uv run travel-agent check --provider mock --origin SFO --destination NRT --date 2027-03-20
```

## Tests

```bash
uv run pytest
```

## Database Migrations

Search history is stored in SQLite through SQLAlchemy models and Alembic migrations. The app upgrades the configured database to the latest migration during `travel-agent check` and `travel-agent scan`.

Run migrations manually:

```bash
TRAVEL_AGENT_DB=data/travel_agent.sqlite uv run alembic upgrade head
```

## Architecture

Providers implement `TravelProvider` and return structured `FareOption` values.
Providers with efficient calendar or deal-page retrieval also implement the
range-search protocol. Browser automation, cookies, auth files, and raw HTML
stay inside provider implementations.

The sanitizer converts provider results into minimal JSON-safe fare summaries. `LLMSummarizer` accepts only sanitized fare JSON and uses LiteLLM fallback order:

1. Gemini Flash
2. Groq
3. Ollama/Qwen local fallback

SQLite stores search runs and fare options for local history. SQLAlchemy owns the table models and Alembic owns schema changes.

## Later Scheduling

Cron example:

```cron
0 8 * * * cd /path/to/travelAgent && uv run travel-agent check --provider mock --origin SFO --destination NRT --date 2027-03-20 >> logs/travel-agent.log 2>&1
```

Windows Task Scheduler can run the same command from the project directory.
