# profile/

Your matching profile lives here. It is the single source of truth for what
job-radar shows you.

## Setup

```bash
cp profile/example.yaml profile/me.yaml
```

Then edit `profile/me.yaml`. `me.yaml` is gitignored — your real preferences never
get committed. Only `example.yaml` (the template) ships with the repo.

## What's in it

- **tracks** — groups of keywords describing the roles you want. A track matches a JD
  when at least one `include_keyword` and one `required_any` keyword appear.
- **exclude_keywords** — titles containing these are dropped immediately.
- **remote_only** — when `true`, non-remote roles are filtered out.
- **blocked_companies / boost_companies** — per-company block / score boost.
- **thresholds / budget** — scoring cutoffs and the daily LLM spend cap.

## Resume-aware scoring

Put your resume at `./resume.md` (repo root) or set `resume_path` in your profile.
The LLM scorer reads it so it can judge fit against *your* actual background, not
just keywords.

## Editing from the CLI

You rarely need to hand-edit YAML:

```bash
job-radar add-keyword <track> "<keyword>"
job-radar remove-keyword <track> "<keyword>"
job-radar exclude "<title keyword>"
job-radar block-company "<name>"
job-radar boost-company "<name>"
job-radar show-profile
```

## Ideal-JD anchors (optional)

`profile/ideal_jds/*.md` are natural-language descriptions of your dream roles, used
as anchors for vector recall. Optional but improves matching.
