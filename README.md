# job-radar

> Stop drowning in job-board noise. Let an LLM read your resume, score every JD across
> 15+ sources, and email you the best matches — with bilingual reasons for each.

**job-radar** is a personal job-discovery engine that you run yourself. It scrapes public
job sources (official ATS APIs + remote job boards), filters against your profile, scores
each role with an LLM that has actually read your resume, and sends you a clean daily digest.

It ships as a standalone CLI **and** as a [Claude / openclaw Skill](#use-as-an-agent-skill),
so an AI agent can operate it for you.

```
collect (15+ sources) → hard filter → LLM score (with your resume) → dedup → email digest
```

---

## Why this exists

- **LinkedIn / job-board alerts** match on keywords. They can't read your resume, so you get noise.
- **job-radar** sends each JD + your resume to an LLM and asks: *"is this actually a fit, and why?"*
- You get a ranked, deduplicated, bilingual (EN/中文) digest of only the roles worth your time.

## Features

- **15+ data sources** out of the box:
  - Official ATS APIs: Lever, Greenhouse, Ashby, Workable (80+ companies pre-seeded)
  - Remote boards: RemoteOK, Remotive, WeWorkRemotely, Jobicy
  - Crypto/Web3: dejob.ai, decentrajobs
  - HN "Who is hiring?", JSON-LD career pages, LinkedIn (via Gmail API)
- **LLM scoring** with your resume as context — 4 dimensions + reasons + risks, bilingual
- **Hard filters**: keywords, seniority, location, remote-only, per-company block/boost
- **Cross-posting dedup** (same role across cities/sources collapses to one)
- **Budget-aware** LLM spend with a daily cap and graceful fallback to free heuristic scoring
- **Email digests** via Resend (HTTPS, works behind cloud firewalls) or SMTP
- **Bring your own LLM**: any Anthropic-compatible endpoint (Claude, DeepSeek, proxies…)

---

## Quick start

```bash
git clone https://github.com/survivorff/job-radar.git
cd job-radar
uv sync                                  # install deps (needs astral.sh/uv)

cp .env.example .env                     # add your LLM + email keys
cp profile/example.yaml profile/me.yaml  # describe the roles you want
# (optional) put your resume at ./resume.md for resume-aware scoring

uv run job-radar run                     # collect + filter + score
uv run job-radar digest --daily --dry-run   # preview the digest (no email)
uv run job-radar digest --daily          # send it
```

See [`docs/GET-STARTED.md`](docs/GET-STARTED.md) for the full walkthrough.

---

## Configure your profile

Everything is driven by `profile/me.yaml`. A **track** is a group of keywords describing a
kind of role you want. You can have several. See [`profile/example.yaml`](profile/example.yaml)
for an annotated template.

Tune it from the CLI without editing YAML:

```bash
job-radar add-keyword backend "Rust"      # add a keyword to a track
job-radar exclude "Sales Manager"         # never show titles containing this
job-radar block-company "SomeCorp"        # hard-block a company
job-radar boost-company "Anthropic"       # +15 to a company you love
job-radar disable-source remoteok         # turn a source off
job-radar show-profile                    # print current config
job-radar sources                         # list all data sources + status
```

---

## Commands

| Command | What it does |
|---|---|
| `job-radar run` | Collect from all sources, filter, score, store in SQLite |
| `job-radar digest --daily` | Build + email the daily digest (`--dry-run` to preview) |
| `job-radar digest --weekly` | Weekly digest (7-day window) |
| `job-radar test-email` | Verify your email channel works |
| `job-radar stats` | Pipeline dashboard for the last N days |
| `job-radar label` | Interactively label matches (want/applied/maybe/reject/noise) |
| `job-radar eval` | Precision / noise-rate report from your labels |
| `job-radar sources` | List data sources and their status |

---

## Use as an agent Skill

job-radar ships a `SKILL.md` so [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/skills),
Claude Desktop, or openclaw can run it for you ("refresh my job radar", "why did this score
high?", "stop showing me QA roles").

```bash
./install.sh   # symlinks into ~/.claude/skills and ~/.openclaw/skills,
               # puts your data in ~/.job-radar, and adds a `job-radar` wrapper to PATH
```

---

## Scheduling

Run it on a timer with cron (uses local timezone):

```cron
5 * * * * /usr/local/bin/job-radar run        >> ~/.job-radar/logs/cron.log 2>&1
0 9 * * * /usr/local/bin/job-radar digest --daily >> ~/.job-radar/logs/cron.log 2>&1
```

---

## Architecture

```
job_radar/
├── sources/      # one adapter per job source (add yours here)
├── pipeline/     # hard_filter → embed_recall → llm_scorer → dedupe
├── channels/     # email (resend / smtp), digest rendering
├── eval/         # labeling + precision metrics
├── cli.py        # typer CLI
└── config.py     # .env + profile.yaml loading
```

Design docs live in [`docs/`](docs/). Start with [`docs/00-design.md`](docs/00-design.md).

---

## Adding a data source

Create `job_radar/sources/<name>.py` with a `fetch() -> Iterable[RawJob]`, then register it
in `job_radar/sources/registry.py`. See [`CONTRIBUTING.md`](CONTRIBUTING.md) and any existing
adapter (e.g. `lever.py`) for the pattern. PRs adding sources are very welcome.

---

## Privacy

Your resume, profile, scraped data, and credentials stay **local** (under `~/.job-radar/` or the
repo, all gitignored). job-radar makes no outbound calls except to the job sources, your chosen
LLM endpoint, and your email provider.

---

## License

MIT — see [LICENSE](LICENSE).
