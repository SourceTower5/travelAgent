# Travel Agent Implementation Roadmap

Date: 2026-07-29

## Phase 1: Planning Baseline
Status: updated with concrete ZIPAIR search intent.

Artifacts:
- docs/context/product-brief.md
- docs/context/system-design.md
- docs/context/implementation-roadmap.md
- docs/context/codex-handoff.md

## Phase 2: ZIPAIR Calendar Discovery
Goal: understand and stabilize the real public ZIPAIR homepage-to-calendar browser flow.

Tasks:
- Use Playwright in WSL to open https://www.zipair.net/en.
- Identify selectors for one-way mode, origin, destination, passenger count, and calendar submission.
- Confirm whether SFO -> NRT and SJC -> NRT are both accepted by the public form.
- Confirm how economy/standard and full-flat fares appear in the calendar/result DOM.
- Capture safe local fixtures that do not include credentials, cookies, private account data, or raw session storage.

Acceptance criteria:
- Provider can reach the calendar page locally or fail with a clear ProviderSearchError.
- Tests cover parser behavior from saved safe fixtures.
- No private/session data is committed or sent to LLMs.

## Phase 3: Date Window Scan
Goal: scan from the run date through 2026-12-31.

Tasks:
- Add date-window generation.
- Support origins SFO and SJC, destination NRT, one-way, 1 adult.
- Capture economy/standard and full-flat fares.
- Store results by route, departure date, cabin, price, currency, availability, and observed time.

Acceptance criteria:
- A single command can scan both origins through 2026-12-31.
- Results are deterministic JSON at the CLI boundary.
- Provider failures are explicit and do not look like empty fare results.

## Phase 4: Saved Watches
Goal: make trip monitoring a first-class concept.

Tasks:
- Add SQLAlchemy models and Alembic migration for watches and watch runs.
- Add storage methods: create/list/get/disable watch, record watch run.
- Add CLI commands under watch.
- Reuse existing provider lookup and sanitizer.
- Add mock-provider CLI tests for watch workflows.

Acceptance criteria:
- User can add a watch from CLI.
- User can list enabled watches.
- User can run one watch or all watches.
- Watch runs persist status, fare count, cheapest fare, and errors.
- Existing check command still works.

## Phase 5: Change Detection And Summaries
Goal: tell the user what changed, not just what was observed.

Tasks:
- Implement comparison against the previous successful watch run.
- Add summary JSON with cheapest fare, threshold match, cabin availability, and price delta.
- Pass only sanitized comparison JSON to LLM summarizer.
- Add tests for price drop, no change, price increase, no fares, and provider error.

Acceptance criteria:
- CLI output includes stable machine-readable JSON.
- Human summary is optional and safe.
- No raw HTML, credentials, cookies, or browser state enter summaries.

## Phase 6: Scheduling And Notification
Goal: make monitoring useful without manual retyping.

Tasks:
- Document cron commands for watch run-all in WSL.
- Add notification protocol with a CLI/log implementation first.
- Consider Notion, Linear, email, or desktop notifications after local reliability is proven.

Acceptance criteria:
- A scheduled command can run without interactive prompts.
- Failures are logged clearly.
- Notification integrations remain optional.
