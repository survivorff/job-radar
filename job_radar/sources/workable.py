"""Workable ATS adapter.

Workable is another very common ATS (used by e.g. Ledger, 1inch variants,
mid-size crypto/AI startups). Its public widget endpoint is:
  https://apply.workable.com/api/v1/widget/accounts/{slug}
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from loguru import logger

from job_radar.http import client
from job_radar.models import RawJob
from job_radar.text import strip_html


@dataclass(frozen=True)
class WorkableSlug:
    slug: str
    company_name: str


# Verified live as of 2026-05
WORKABLE_SEEDS: list[WorkableSlug] = []  # (none confirmed yet; enable when a slug is found)


def fetch_slug(s: WorkableSlug) -> list[RawJob]:
    url = f"https://apply.workable.com/api/v1/widget/accounts/{s.slug}"
    with client() as c:
        resp = c.get(url)
    if resp.status_code >= 400:
        logger.warning("workable {} status {}", s.slug, resp.status_code)
        return []
    data = resp.json()
    jobs = data.get("jobs") or []
    out: list[RawJob] = []
    for j in jobs:
        try:
            out.append(_parse(s, j))
        except Exception as exc:
            logger.warning("workable parse failed {}/{}: {}", s.slug, j.get("id"), exc)
    return out


def fetch() -> Iterable[RawJob]:
    for s in WORKABLE_SEEDS:
        try:
            yield from fetch_slug(s)
        except Exception as exc:
            logger.warning("workable source {} failed: {}", s.slug, exc)


def _parse(s: WorkableSlug, j: dict) -> RawJob:
    posted_at = None
    if j.get("published_on"):
        try:
            posted_at = datetime.fromisoformat(str(j["published_on"]).replace("Z", "+00:00"))
        except ValueError:
            pass
    location = ""
    loc = j.get("location") or {}
    if isinstance(loc, dict):
        city = loc.get("city") or ""
        country = loc.get("country") or ""
        location = ", ".join(p for p in (city, country) if p)
    return RawJob(
        source=f"workable:{s.slug}",
        external_id=str(j.get("shortcode") or j.get("id")),
        company=s.company_name,
        title=(j.get("title") or "").strip(),
        location=location,
        description=strip_html(j.get("description")) or (j.get("description_plain") or ""),
        apply_url=j.get("url") or j.get("application_url") or "",
        posted_at=posted_at,
        raw=j,
    )
