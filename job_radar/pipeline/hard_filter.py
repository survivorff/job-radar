"""Stage 1: hard rules from profile.yaml."""

from __future__ import annotations

from job_radar.config import Profile
from job_radar.models import FilterResult, Job
from job_radar.text import contains_any, count_keyword_hits


def hard_filter(job: Job, profile: Profile) -> FilterResult:
    text_blob = f"{job.title}\n{job.description}"

    # 0. blocked companies (per-company block list)
    if profile.blocked_companies:
        company_lower = job.company.lower()
        hit = next(
            (c for c in profile.blocked_companies if c.lower() in company_lower),
            None,
        )
        if hit:
            return FilterResult(passed=False, reason=f"blocked company: {hit}")

    # 1. Title-only exclusions (these words in the TITLE mean "not for Frank")
    #    Checking title only avoids killing a Backend Engineer JD just because
    #    its body mentions "Sales team uses our API".
    title_lower = job.title.lower()
    for kw in profile.exclude_keywords or []:
        if kw.lower() in title_lower:
            return FilterResult(passed=False, reason=f"excluded keyword (title): {kw}")

    # 2. seniority blocklist (title only)
    if profile.seniority_blocklist and contains_any(job.title, profile.seniority_blocklist):
        hit = next(
            (kw for kw in profile.seniority_blocklist if kw.lower() in job.title.lower()),
            "?",
        )
        return FilterResult(passed=False, reason=f"seniority blocked: {hit}")

    # 3. track match — ≥1 include-keyword hit + required_any match (OR) in text.
    #    Loosened from ≥2 to ≥1 so generic-but-senior roles aren't all dropped.
    matched: list[str] = []
    for track in profile.tracks:
        hits = count_keyword_hits(text_blob, track.include_keywords)
        if hits >= 1 and (
            not track.required_any or contains_any(text_blob, track.required_any)
        ):
            matched.append(track.id)
    if not matched:
        return FilterResult(passed=False, reason="no track matched")

    # 4. remote-only preference (hard filter if set)
    if profile.remote_only and not job.is_remote:
        # Allow JDs whose location string explicitly says Remote / Worldwide etc.
        # (is_remote is computed from title+location combined — trust it)
        return FilterResult(passed=False, reason="non-remote (profile: remote_only=true)", matched_tracks=matched)

    # 5. location allowlist (only if JD declares a location; empty = let through).
    if job.location and profile.location_allowlist and not job.is_remote:
        loc_lower = job.location.lower()
        if not any(loc.lower() in loc_lower for loc in profile.location_allowlist):
            return FilterResult(
                passed=False,
                reason=f"location not allowed: {job.location}",
                matched_tracks=matched,
            )

    return FilterResult(passed=True, matched_tracks=matched)
