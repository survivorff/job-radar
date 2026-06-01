# Contributing to job-radar

Thanks for helping make job-radar better. The most valuable contributions are
**new data sources** and **bug fixes for existing adapters** (job boards change their
markup/APIs constantly).

## Dev setup

```bash
uv sync
uv run pytest        # all tests must pass
uv run ruff check .  # lint
```

## Adding a data source

This is the #1 way to contribute. Each source is one self-contained module.

1. Create `job_radar/sources/<name>.py` exposing:

   ```python
   from typing import Iterable
   from job_radar.models import RawJob

   def fetch() -> Iterable[RawJob]:
       ...
   ```

2. Map the source's fields onto `RawJob` (see `job_radar/models.py`). At minimum:
   `source`, `external_id`, `company`, `title`, `apply_url`. Fill `location`,
   `description`, `posted_at`, `salary_text` when available.

3. Register it in `job_radar/sources/registry.py`:

   ```python
   SourceEntry("<name>", <name>.fetch),
   ```

4. Be a good citizen:
   - Send a clear `User-Agent` (see `job_radar/http.py`).
   - Respect rate limits; don't hammer. Keep request volume minimal.
   - Only use public/official endpoints (ATS JSON APIs, RSS, documented APIs).
   - **Do not** scrape behind logins or bypass bot protection.
   - Fail gracefully: a dead source must log a warning and return nothing, never crash the run.

5. Add a parser test in `tests/` using a captured sample payload (no live network in tests).

### Finding a source's ATS

Many companies use Lever / Greenhouse / Ashby / Workable. Probe a slug:

```bash
uv run python scripts/probe_ats.py <company-slug>
```

If it returns `200`, add the slug to the relevant `*_SEEDS` list.

## Code style

- Python 3.11+, type hints, `ruff` formatting.
- Keep adapters dependency-light (prefer `httpx` + stdlib over heavy parsers).
- Pure functions in `pipeline/` should have unit tests.

## What we won't merge

- Sources that require scraping authenticated pages or defeating CAPTCHAs.
- Anything that ships personal data, secrets, or a specific person's profile/resume.
- Auto-apply / mass-submission features (out of scope: job-radar discovers, humans apply).

## Reporting bugs

Open an issue with: the command you ran, the source involved, and the log output
(`~/.job-radar/logs/radar.log` or repo `logs/`). Redact any keys.
