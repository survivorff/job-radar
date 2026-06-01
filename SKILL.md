---
name: job-radar
description: Personal JD radar. Scrape AI / Crypto×AI job listings from public ATS (Lever / Greenhouse / Ashby), filter against a user profile, score with bilingual explanations, and email a daily digest. Use this skill when the user asks to find AI jobs, update their job search, preview matches, explain a specific match, or tune their matching profile.
version: 0.1.0
license: MIT
---

# job-radar

You are operating the **job-radar** skill: a personal JD radar for Frank (and anyone who configures a profile). This skill is a Python CLI plus a small set of helper scripts in the skill folder.

## When to use this skill

Invoke this skill whenever the user wants to:

- **Refresh the radar**: fetch new job postings and rescore them ("扫一次岗位" / "run the radar" / "抓新的 JD")
- **Send a digest**: email the daily or weekly digest ("发日报" / "send digest")
- **Preview results without sending**: render the digest HTML and/or dump the current top matches to text ("先看一下今天有什么岗位")
- **Explain a specific JD**: given a company/title or match_id, produce a deep explanation of why it matched and what to prepare for
- **Tune the profile**: add/remove keywords, change tracks, adjust thresholds in `profile/me.yaml`
- **Check stats / diagnose**: inspect why a JD did or did not pass filtering using the run trace

Do NOT use this skill for: generic job search advice, resume rewriting, cover letter drafts. Use the user's own career docs for those.

## Prerequisites (first-time setup only)

The skill ships with an installer. When properly installed it uses this layout:

```
~/.agents/skills/job-radar/          ← this folder (code, upgradeable)
~/.job-radar/                        ← user data (never overwritten)
   ├── .env                          ← email channel + LLM credentials
   ├── profile.yaml                  ← matching rules
   ├── data/radar.sqlite             ← scraped jobs + scores
   └── runs/ logs/
```

Check installation status:
1. `test -f ~/.job-radar/.env` → must exist
2. `test -f ~/.job-radar/profile.yaml` → must exist
3. `command -v job-radar` → wrapper on PATH

If any step is missing, run the installer:
```bash
cd ~/.agents/skills/job-radar && ./install.sh
```
Then guide the user to edit `~/.job-radar/.env` and re-run the failing step.

### Email channel selection

The skill automatically picks a channel based on `~/.job-radar/.env`:

| Condition | Channel | When to use |
|---|---|---|
| `RESEND_API_KEY` is set | Resend HTTPS API | **Recommended for cloud servers** (aliyun/Tencent/AWS). Works through any firewall, free 100 emails/day, sandbox sender works without domain verification. |
| `SMTP_USER` + `SMTP_PASS` set | Gmail/Outlook SMTP | Works on personal machines. May be blocked by cloud-provider egress firewalls. |
| Neither | Preview-only | `digest` writes HTML to `~/.job-radar/logs/last_digest.html` instead of sending. |

If the user is on a mainland-China cloud VM and Gmail SMTP fails with `Network is unreachable`, recommend Resend:
1. Sign up at https://resend.com/signup (free, GitHub/Google sign-in)
2. Go to API Keys → Create → copy
3. `echo 'RESEND_API_KEY=re_xxx' >> ~/.job-radar/.env`
4. `job-radar test-email`

## Core commands

After installation, a `job-radar` wrapper is on PATH that injects `JOB_RADAR_HOME=~/.job-radar` automatically. Always prefer the wrapper; fall back only if it's missing.

### Refresh the radar
```bash
job-radar run
```
Collects from all enabled sources, filters, scores, stores in SQLite. Does NOT send email. Typical runtime: 30-120 seconds.

### Preview today's digest (no email)
```bash
uv run --project ~/.agents/skills/job-radar \
  python ~/.agents/skills/job-radar/scripts/show_top.py --limit 20
```

### Send digest
```bash
job-radar digest --daily
# or
job-radar digest --weekly
```

### Test the email channel
```bash
job-radar test-email
```

### Stats
```bash
job-radar stats --days 7
```

### Explain a specific match
```bash
uv run --project ~/.agents/skills/job-radar \
  python ~/.agents/skills/job-radar/scripts/explain.py --match-id 42
# OR by company/title
uv run --project ~/.agents/skills/job-radar \
  python ~/.agents/skills/job-radar/scripts/explain.py --company OKX --title-contains "AI Agent"
```

## Operating patterns

### Pattern 1 — "Refresh and summarize"

User says: "刷一下今天的岗位" or "run the radar".

1. Run `job-radar run`
2. Read its stdout summary table (total fetched, passed filter, tier counts)
3. Run `uv run --project ~/.agents/skills/job-radar python ~/.agents/skills/job-radar/scripts/show_top.py --limit 10`
4. Present the top 5 high-tier matches in the user's preferred language, highlighting:
   - Score + dimensions (tech / scenario / seniority / company_fit)
   - Which keywords matched
   - The single-sentence bilingual explanation
   - The suggested resume version and Apply URL

Do NOT send the email automatically; ask the user before `digest --daily`.

### Pattern 2 — "Why did this score X?"

User asks about a specific JD (by match_id or by company+title).

1. Run `explain.py` with the given identifiers
2. Interpret the output: keyword hits, dimension breakdown, risks
3. Offer concrete next steps: which of the user's showcases to emphasize, what risk to clarify during the application

### Pattern 3 — "Stop showing me X kind of jobs"

User reports false positives (e.g. "我不想看 QA 岗" or "不要 OKX 的合规岗").

Three types of blocks, pick the right one:

| User intent | Command | Effect |
|---|---|---|
| Block a keyword (title / description match) | `job-radar exclude "QA Engineer"` | Hard filter, drops anything mentioning it |
| Block a specific company | `job-radar block-company "Coinbase"` | Hard filter, drops any JD from that company |
| Boost a company | `job-radar boost-company "LangChain"` | +15 on company_fit dimension |
| Disable a whole data source | `job-radar disable-source "remoteok"` | Skip that source next run |

After any change, re-run `job-radar run` so scores reflect it. Show the user the top 10 afterwards for confirmation.

To see current state: `job-radar sources` (list of data sources with status) or `cat ~/.job-radar/profile.yaml` (full rules).

Never silently edit `~/.job-radar/profile.yaml`; prefer the CLI mutators. If direct YAML editing is unavoidable, show the diff first.

### Pattern 4 — "Add a company to watch"

User names a company they want tracked.

1. Probe which ATS it uses:
   ```bash
   uv run --project ~/.agents/skills/job-radar \
     python ~/.agents/skills/job-radar/scripts/probe_ats.py <slug-candidates>
   ```
2. Based on the output (which endpoint returned 200), add a seed entry in the matching `~/.agents/skills/job-radar/job_radar/sources/<lever|greenhouse|ashby>.py` `*_SEEDS` list
3. Run `job-radar run`, confirm the new source appears in the per-source table
4. If the user wants extra emphasis on this company, also run `job-radar boost-company "<Name>"`

Always show the user the diff of the SEED list change before saving.

### Pattern 4b — "What sources are you pulling from?"

```bash
job-radar sources
```

Explains which data sources are active vs disabled. If the user wants a specific source off/on, use `disable-source` / `enable-source`.

### Pattern 5 — "Diagnose a missed JD"

User says "why didn't X get pushed?"

1. Query the database:
   ```bash
   uv run --project ~/.agents/skills/job-radar \
     python ~/.agents/skills/job-radar/scripts/query.py \
     --company "<name>" --title-contains "<fragment>"
   ```
2. The output shows: stage1_passed, stage1_reason, tier, matched_tracks, dims, matched_keywords
3. If `stage1_passed=false`, explain the hard filter rule that rejected it (from `stage1_reason`)
4. If tier is too low, explain which dimension is weakest and suggest profile/keyword tweaks

### Pattern 6 — "质量评估 / Quality check"

User wants to know if the radar is actually getting better.

1. Ask the user to run `job-radar label --tier high` (interactive, walks through today's high-tier matches with 5 verdict options).
2. After labels are in, run `job-radar eval --days 7`.
3. Interpret the report:
   - `P@high ≥ 80%` and `P@med ≥ 60%` and `noise ≤ 10%` → satisfied ✅
   - Otherwise find the weak link:
     - Lots of `reject` in `high` → profile is too permissive; suggest exclude_keywords
     - Lots of `noise` → a specific class of role slipping through; propose exclude or block-company
     - Very few `want` → tracks are too narrow; suggest adding include_keywords

Satisfied definition: **3 consecutive days of P@high ≥ 80%, P@med ≥ 60%, noise ≤ 10%**.

### Pattern 7 — "LLM scoring is slow / expensive"

User worried about cost or throughput.

- Cost: each LLM call ~¥0.005 via deepseek-v4-pro. Budget is ¥5/day (env `JOB_RADAR_DAILY_LLM_BUDGET`).
- First full run: ~¥1.2 for 260 matches. Subsequent hourly runs: ~¥0 because we skip rescoring matches fresher than `JOB_RADAR_RESCORE_HOURS` (default 72h).
- Concurrency: `JOB_RADAR_LLM_CONCURRENCY` (default 6). Tune if the proxy rate-limits.
- Disable LLM entirely and use heuristic scorer only: `export JOB_RADAR_LLM=off`

## Important rules

- **Never expose secrets**: `.env` contains SMTP passwords and API keys. Never echo them in responses.
- **Commands are idempotent**: `run` can be called any number of times; it upserts by fingerprint. Safe to re-run on errors.
- **Profile changes need re-run**: after editing `~/.job-radar/profile.yaml`, the user must re-run `job-radar run` for scores to reflect the new rules.
- **DB schema changes**: if the skill upgrades include column changes, delete `~/.job-radar/data/radar.sqlite` and re-run. Warn the user before deletion.
- **Network failures are expected**: individual sources can 404 / time-out. The pipeline is failure-isolated; proceed with whatever data we have.
- **Respect rate limits**: do not increase concurrency or remove the per-source sleep. This is a personal tool, not a scraper.

## File map for debugging

### Skill source (upgradeable, safe to re-sync)
| Path | Purpose |
|---|---|
| `~/.agents/skills/job-radar/job_radar/cli.py` | CLI entry, typer commands |
| `~/.agents/skills/job-radar/job_radar/sources/{lever,greenhouse,ashby}.py` | ATS adapters + seed lists |
| `~/.agents/skills/job-radar/job_radar/pipeline/hard_filter.py` | Stage 1 rules |
| `~/.agents/skills/job-radar/job_radar/pipeline/heuristic_scorer.py` | Stage 3 (M1/M2 deterministic scorer) |
| `~/.agents/skills/job-radar/job_radar/channels/digest.py` | Builds the digest from DB |
| `~/.agents/skills/job-radar/job_radar/channels/email_smtp.py` | Gmail SMTP sender |
| `~/.agents/skills/job-radar/job_radar/templates/digest.html.j2` | Bilingual HTML template |
| `~/.agents/skills/job-radar/docs/00-design.md` | Overall design doc |

### User data (preserved across upgrades; contains secrets)
| Path | Purpose |
|---|---|
| `~/.job-radar/.env` | SMTP password + LLM API keys |
| `~/.job-radar/profile.yaml` | Matching rules (include / exclude keywords, tracks) |
| `~/.job-radar/data/radar.sqlite` | Persistent state (jobs, matches, pushes, feedback) |
| `~/.job-radar/runs/*.json` | Per-run trace for debugging |
| `~/.job-radar/logs/radar.log` | Runtime log |

## Language handling

Respond in the user's language. Always render the digest in bilingual mode (EN + ZH). When the user writes in Chinese, prefer the Chinese side of bilingual outputs; when in English, prefer EN but include ZH on request.

## Not in scope for M1 / M2

- LLM-based scoring (M3, uses the `ANTHROPIC_API_BASE` config in `.env`)
- Telegram bot (M4)
- GitHub Actions hosting (M5)

If the user asks about these, explain the roadmap is in `ROADMAP.md` and offer to implement the next milestone.
