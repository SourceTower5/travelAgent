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
uv run travel-agent check --provider mock --origin SFO --destination NRT --date 2026-10-15
```

ZIPAIR provider:

```bash
uv run travel-agent check --provider zipair --origin SFO --destination NRT --date YYYY-MM-DD
```

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
cd /home/jimmyphan/travelAgent
CHROME_CDP_URL=http://127.0.0.1:9222 uv run travel-agent check \
  --provider zipair --origin SFO --destination NRT \
  --date 2026-10-15
```

The provider reuses the existing Chrome context and ZIPAIR tab, selects the route and default one-adult passenger automatically, and leaves Chrome open when it disconnects. Add `--interactive` only when you need one pause for a normal public access interaction before automation continues.

Scan both requested Bay Area origins from today through the end of the year,
keeping both standard/economy and ZIP Full-Flat fares:

```bash
uv run travel-agent scan --provider zipair --origins SFO,SJC --destination NRT
```

To scan all supported directions through December 31 using the attached Chrome tab:

```bash
CHROME_CDP_URL=http://127.0.0.1:9222 uv run travel-agent scan \
  --provider zipair \
  --routes SFO-NRT,SJC-NRT,NRT-SJC,NRT-SFO \
  --start-date 2026-07-30 \
  --end-date 2026-12-31
```

The scan selects every route, accepts the default one-adult passenger, opens each calendar, and captures Standard and ZIP Full-Flat fares automatically. Available observations are saved in the local SQLite database. The default path is `travel_agent.sqlite` in the project directory; set `TRAVEL_AGENT_DB` to use another persistent path.

Scans are quiet by default. Add `--json` only when you want the complete fare payload printed in the terminal.

## Local fare dashboard

Start the read-only TypeScript dashboard:

```bash
cd /home/jimmyphan/travelAgent
npm run dashboard
```

Open `http://127.0.0.1:4173` in your regular Chrome browser. The dashboard reads `travel_agent.sqlite` directly and displays the latest complete scan snapshot for each route. To use a different database:

```bash
TRAVEL_AGENT_DB=/path/to/travel_agent.sqlite npm run dashboard
```

The ZIPAIR provider uses Playwright against the public site only. It does not log in, does not use credentials, and does not send raw HTML to any LLM. If ZIPAIR blocks automation or changes its page structure, the command exits with a clear provider error instead of returning scraped private or unsafe data.

Use a custom database path:

```bash
TRAVEL_AGENT_DB=data/travel_agent.sqlite uv run travel-agent check --provider mock --origin SFO --destination NRT --date 2026-10-15
```

## Tests

```bash
uv run pytest
```

## Database Migrations

Search history is stored in SQLite through SQLAlchemy models and Alembic migrations. The app upgrades the configured database to the latest migration during `travel-agent check`.

Run migrations manually:

```bash
TRAVEL_AGENT_DB=data/travel_agent.sqlite uv run alembic upgrade head
```

## Architecture

Providers implement `TravelProvider` and return structured `FareOption` values. Browser automation, cookies, auth files, and raw HTML stay inside provider implementations.

The sanitizer converts provider results into minimal JSON-safe fare summaries. `LLMSummarizer` accepts only sanitized fare JSON and uses LiteLLM fallback order:

1. Gemini Flash
2. Groq
3. Ollama/Qwen local fallback

SQLite stores search runs and fare options for local history. SQLAlchemy owns the table models and Alembic owns schema changes.

## Later Scheduling

Cron example:

```cron
0 8 * * * cd /path/to/travelAgent && uv run travel-agent check --provider mock --origin SFO --destination NRT --date 2026-10-15 >> logs/travel-agent.log 2>&1
```

Windows Task Scheduler can run the same command from the project directory.
