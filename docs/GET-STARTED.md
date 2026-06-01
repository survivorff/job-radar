# Get Started

A 10-minute setup from clone to first digest.

## 1. Install

```bash
git clone https://github.com/survivorff/job-radar.git
cd job-radar
uv sync                # needs https://docs.astral.sh/uv/
```

## 2. Configure

```bash
cp .env.example .env
cp profile/example.yaml profile/me.yaml
```

Edit `profile/me.yaml` to describe the roles you want (see the comments in the file).
Optionally drop your resume at `./resume.md` for resume-aware LLM scoring.

## 3. Email channel

job-radar emails you the digest. Pick one:

**Resend (recommended — HTTPS, works anywhere incl. cloud servers)**
1. Sign up at https://resend.com/signup (free 100 emails/day)
2. Create an API key
3. In `.env`:
   ```
   RESEND_API_KEY=re_xxx
   SMTP_TO=you@example.com
   ```

**Gmail SMTP (works on personal machines; many clouds block it)**
1. Create an app password at https://myaccount.google.com/apppasswords
2. In `.env`:
   ```
   SMTP_USER=you@example.com
   SMTP_PASS=your-16-char-app-password
   SMTP_TO=you@example.com
   ```

Verify it:
```bash
uv run job-radar test-email
```

## 4. LLM scoring (optional but recommended)

Any Anthropic-compatible endpoint works (Claude, DeepSeek, proxies). In `.env`:
```
ANTHROPIC_API_KEY=sk-...
ANTHROPIC_API_BASE=https://api.anthropic.com   # or your provider/proxy
JOB_RADAR_SCORER_MODEL=anthropic/claude-3-5-haiku-latest
```

No LLM key? Set `JOB_RADAR_LLM=off` to use the free keyword-based scorer.

## 5. Run

```bash
uv run job-radar run                       # collect + filter + score
uv run job-radar digest --daily --dry-run  # preview without sending
uv run job-radar digest --daily            # send the email
```

## 6. Schedule (optional)

cron runs in your local timezone:

```cron
5 * * * * cd /path/to/job-radar && uv run job-radar run            >> logs/cron.log 2>&1
0 9 * * * cd /path/to/job-radar && uv run job-radar digest --daily >> logs/cron.log 2>&1
0 21 * * 0 cd /path/to/job-radar && uv run job-radar digest --weekly >> logs/cron.log 2>&1
```

Or install it as an agent skill so Claude/openclaw can run it for you:
```bash
./install.sh
```

## 7. Tune

If you see roles you don't want:
```bash
job-radar exclude "Sales Manager"     # never show this title
job-radar block-company "SomeCorp"    # block a company
job-radar add-keyword backend "Rust"  # widen a track
```
Then re-run `job-radar run`.
