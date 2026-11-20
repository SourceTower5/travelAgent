# Historical Codex Handoff

The original ZIPAIR implementation handoff has been completed and is retained
only as a status marker.

Current capabilities:

- ZIPAIR one-way Standard and ZIP Full-Flat range scans.
- Official JAL one-way Economy and Premium Economy range scans.
- Configurable future date windows, including cross-year dashboard rendering.
- SQLite persistence, migrations, sanitization, and a read-only local dashboard.

Use [README.md](../../README.md) for current setup and commands. New work should
preserve the local-only browser safety boundary and add safe parser fixtures for
provider changes.
