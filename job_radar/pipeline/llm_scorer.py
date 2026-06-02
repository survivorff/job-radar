"""Stage 3 — LLM-based JD scorer.

Wraps the Anthropic-compatible proxy. Cheaper than it looks: we truncate
JD to 3000 chars and resume to 2500 chars, expect <800 output tokens per
scoring, so each JD costs <¥0.01.

Cost budget is enforced via `BudgetGuard` (reads JOB_RADAR_DAILY_LLM_BUDGET).
When exhausted, the caller should fall back to heuristic_scorer.

Fail-open: any LLM error returns None; the caller then falls back.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from threading import Lock

from loguru import logger

from job_radar.config import Profile, get_settings
from job_radar.llm import LLMError, chat, estimate_cost_cny, parse_json_object
from job_radar.models import Job, Score

_SPEND_FILE_LOCK = Lock()

# -------------------- prompt (built dynamically from the profile) --------------------


def _build_system_prompt(profile: Profile) -> str:
    """Construct the scorer's system prompt from the user's profile + resume.

    Keeping this profile-driven (instead of hardcoded for one person) is what
    makes job-radar reusable by anyone.
    """
    resume = _load_resume(profile)

    # Describe the user's tracks, sorted by priority.
    tracks_sorted = sorted(profile.tracks, key=lambda t: t.priority)
    track_lines = []
    for t in tracks_sorted:
        kws = ", ".join(t.include_keywords[:12])
        track_lines.append(
            f"- (priority {t.priority}) `{t.id}` — {t.description or t.id}. "
            f"Signals: {kws}"
        )
    tracks_block = "\n".join(track_lines)

    remote_rule = (
        "The user is REMOTE-ONLY. On-site-only roles → overall ≤ 40. "
        "Acceptable: Remote / Worldwide / Global / Anywhere / Distributed, or any city "
        "label if the role explicitly allows fully-remote."
        if profile.remote_only
        else "The user accepts remote and on-site roles in their allowed locations."
    )
    employment = ", ".join(profile.employment_types) if profile.employment_types else "full-time"
    seniority_ok = ", ".join(profile.seniority_allowlist) or "Senior, Staff, Principal, Lead"
    seniority_no = ", ".join(profile.seniority_blocklist) or "Junior, Intern, Graduate"
    excludes = ", ".join(profile.exclude_keywords[:30]) or "(none)"

    # Valid resume-version labels come from the profile's tracks.
    versions = sorted({t.resume_version for t in profile.tracks if t.resume_version})
    versions_str = " | ".join(f'"{v}"' for v in versions) if versions else '"default"'

    return f"""You are an expert job matcher for a candidate named "{profile.name}".
Given the candidate's resume and a single job description, output a JSON verdict.

<candidate_resume>
{resume}
</candidate_resume>

The candidate is looking for roles in these tracks (priority 1 = most wanted):
{tracks_block}

SCORING BY PRIORITY (this is the most important rule):
- A JD matching a priority-1 track deserves overall 85-100 (if seniority + location also fit).
- Each lower priority number caps the ceiling: priority 2 → up to ~92, priority 3 → up to ~85,
  priority 4 → up to ~78. The candidate's edge is the priority-1 tracks; generic roles score lower
  even at famous companies.

HARD REQUIREMENTS (set overall=0 and verdict="no" if any fail):
- Seniority must be one of: {seniority_ok}. Reject: {seniority_no}.
- Employment type acceptable to candidate: {employment}. Reject internships / trainee "accelerator"
  programs unless explicitly senior.
- {remote_rule}
- Must be an engineering / architecture / technical-leadership role. Reject pure: research scientist,
  frontend-only, product manager, sales, marketing, UX/design, HR/recruiter, customer support,
  compliance/AML/KYC analyst, operations.
- Titles containing any of these are auto-reject: {excludes}

TRACK MATCHING (be strict — matched_tracks must reflect genuine fit, not keyword overlap):
- Only include a track id in matched_tracks if the role is genuinely that kind of work.
- If nothing truly fits, return matched_tracks=[] and verdict="no". Do NOT pad the list.

Output JSON ONLY with this exact schema:
{{
  "dims": {{
    "tech_stack": int 0-100,
    "scenario": int 0-100,
    "seniority": int 0-100,
    "company_fit": int 0-100
  }},
  "overall": int 0-100,
  "matched_tracks": [string],   // subset of the track ids above
  "reasons": [string],          // 2-4 concrete reasons in English, each ≤ 20 words
  "reasons_zh": [string],       // same reasons in Chinese
  "risks": [string],            // 1-3 things to verify / worry about, English
  "risks_zh": [string],         // same in Chinese
  "explanation": string,        // one sentence ≤ 30 words, English
  "explanation_zh": string,     // one sentence ≤ 30 words, Chinese
  "suggested_resume_version": {versions_str},  // which resume variant to send
  "verdict": "strong_yes" | "yes" | "maybe" | "no"
}}

Calibration: strong_yes → overall ≥ 88 ; yes → 75-87 ; maybe → 60-74 ; no → < 60.
"""

USER_TEMPLATE = """<resume>
{resume}
</resume>

<job>
Company: {company}
Title: {title}
Location: {location}  (remote={is_remote})
Source: {source}
Posted: {posted}

{description}
</job>

<hint>
profile.blocked_companies hint (already filtered upstream): {blocked}
profile.boost_companies hint (prefer these): {boosts}
</hint>

Output JSON only.
"""


# -------------------- budget guard --------------------


class BudgetGuard:
    """Tracks daily LLM spend in a small JSON file and refuses over budget."""

    def __init__(self) -> None:
        s = get_settings()
        self.limit_cny = float(s.daily_llm_budget or 5.0)
        self.path: Path = s.data_dir / "llm_spend.json"

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.path)

    def today_spend(self) -> float:
        d = self._load()
        return float(d.get(date.today().isoformat(), 0.0))

    def can_spend(self, estimated: float = 0.01) -> bool:
        return self.today_spend() + estimated <= self.limit_cny

    def record(self, amount_cny: float) -> None:
        with _SPEND_FILE_LOCK:
            d = self._load()
            key = date.today().isoformat()
            d[key] = float(d.get(key, 0.0)) + amount_cny
            # keep only last 14 days
            if len(d) > 14:
                for k in sorted(d.keys())[:-14]:
                    d.pop(k, None)
            self._save(d)


# -------------------- scorer --------------------


_RESUME_CACHE: str | None = None


def _load_resume(profile: Profile) -> str:
    global _RESUME_CACHE
    if _RESUME_CACHE is not None:
        return _RESUME_CACHE
    if not profile.resume_path:
        _RESUME_CACHE = "(resume not provided)"
        return _RESUME_CACHE
    from job_radar.config import ROOT, _home

    # Try several locations
    for base in (_home(), ROOT, Path(".")):
        candidate = Path(profile.resume_path)
        if not candidate.is_absolute():
            candidate = (base / candidate).resolve()
        if candidate.exists():
            _RESUME_CACHE = candidate.read_text(encoding="utf-8")[:2500]
            return _RESUME_CACHE
    _RESUME_CACHE = "(resume file not found)"
    return _RESUME_CACHE


_VERDICT_TO_TIER = {"strong_yes": "high", "yes": "med", "maybe": "low", "no": "drop"}


@dataclass
class LLMScoreResult:
    score: Score | None
    cost_cny: float
    error: str | None = None


def score(
    job: Job,
    profile: Profile,
    matched_tracks: list[str],
    *,
    budget: BudgetGuard | None = None,
) -> LLMScoreResult:
    budget = budget or BudgetGuard()
    if not budget.can_spend(0.01):
        return LLMScoreResult(score=None, cost_cny=0.0, error="budget_exhausted")

    resume = _load_resume(profile)
    description = (job.description or "")[:3000]
    system_prompt = _build_system_prompt(profile)
    prompt = USER_TEMPLATE.format(
        resume=resume,
        company=job.company,
        title=job.title,
        location=job.location or "—",
        is_remote=bool(job.is_remote),
        source=job.source,
        posted=str(job.posted_at or "unknown"),
        description=description,
        blocked=", ".join(profile.blocked_companies or []) or "(none)",
        boosts=", ".join(profile.boost_companies or []) or "(none)",
    )

    try:
        resp = chat(
            system=system_prompt,
            user=prompt,
            max_tokens=700,
            temperature=0.1,
        )
    except LLMError as exc:
        logger.warning("llm error for {} — falling back: {}", job.title, exc)
        return LLMScoreResult(score=None, cost_cny=0.0, error=str(exc))

    cost = estimate_cost_cny(resp)
    budget.record(cost)

    try:
        data = parse_json_object(resp.text)
    except Exception as exc:
        logger.warning("llm json parse failed for {}: {}", job.title, exc)
        return LLMScoreResult(score=None, cost_cny=cost, error=f"parse: {exc}")

    try:
        dims = data.get("dims") or {}
        overall = int(data.get("overall", 0))
        # Coerce floats to ints safely
        dims_norm = {k: int(v) for k, v in dims.items() if isinstance(v, (int, float))}
        # Verdict can override tier if mismatch
        verdict = data.get("verdict") or ""
        suggested = data.get("suggested_resume_version")
        valid_versions = {t.resume_version for t in profile.tracks if t.resume_version}
        if suggested not in valid_versions:
            suggested = None

        s = Score(
            overall=max(0, min(100, overall)),
            dims=dims_norm,
            reasons=_clean_list(data.get("reasons")),
            reasons_zh=_clean_list(data.get("reasons_zh")),
            risks=_clean_list(data.get("risks")),
            risks_zh=_clean_list(data.get("risks_zh")),
            matched_keywords=[],  # LLM scorer doesn't surface keywords — leave for heuristic overlay
            explanation=(data.get("explanation") or "")[:400],
            explanation_zh=(data.get("explanation_zh") or "")[:400],
            suggested_resume_version=suggested,
            stage="llm",
        )
        # If LLM's verdict implies a different tier than our numeric thresholds,
        # honour the verdict (clamp the score so the Score.tier property aligns).
        forced = _VERDICT_TO_TIER.get(verdict)
        if forced == "high" and s.overall < 90:
            s.overall = 90
        elif forced == "drop":
            s.overall = 0

        return LLMScoreResult(score=s, cost_cny=cost)
    except Exception as exc:
        logger.warning("llm shape error for {}: {}", job.title, exc)
        return LLMScoreResult(score=None, cost_cny=cost, error=f"shape: {exc}")


def _clean_list(val) -> list[str]:
    if not isinstance(val, list):
        return []
    return [str(x)[:200] for x in val if x][:5]
