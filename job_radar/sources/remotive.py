"""Remotive — public JSON API, 100% remote jobs.

Endpoint: https://remotive.com/api/remote-jobs?category=software-dev
Returns: {"job-count": N, "jobs": [ {id, url, title, company_name, ...} ]}
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from loguru import logger

from job_radar.http import client
from job_radar.models import RawJob
from job_radar.text import strip_html

URL_TEMPLATES = [
    # These return different slices; we union them for broader coverage.
    "https://remotive.com/api/remote-jobs?category=software-dev",
    "https://remotive.com/api/remote-jobs?category=devops",
    "https://remotive.com/api/remote-jobs?category=data",
    "https://remotive.com/api/remote-jobs?search=blockchain",
    "https://remotive.com/api/remote-jobs?search=crypto",
    "https://remotive.com/api/remote-jobs?search=llm",
    "https://remotive.com/api/remote-jobs?search=ai%20agent",
]


def fetch() -> Iterable[RawJob]:
    seen: set[int] = set()
    for url in URL_TEMPLATES:
        try:
            yield from _fetch_one(url, seen)
        except Exception as exc:
            logger.warning("remotive {} failed: {}", url, exc)


def _fetch_one(url: str, seen: set[int]) -> Iterable[RawJob]:
    with client() as c:
        resp = c.get(url, headers={"Accept": "application/json"})
    if resp.status_code >= 400:
        logger.warning("remotive {} status {}", url, resp.status_code)
        return
    data = resp.json()
    jobs = data.get("jobs") or []
    for j in jobs:
        try:
            jid = int(j.get("id") or 0)
        except Exception:
            continue
        if jid in seen:
            continue
        seen.add(jid)
        try:
            yield _parse(j)
        except Exception as exc:
            logger.debug("remotive parse failed: {}", exc)


def _parse(j: dict) -> RawJob:
    posted_at = None
    if j.get("publication_date"):
        try:
            posted_at = datetime.fromisoformat(str(j["publication_date"]).replace("Z", "+00:00"))
        except ValueError:
            pass
    return RawJob(
        source="remotive",
        external_id=str(j.get("id")),
        company=(j.get("company_name") or "Unknown").strip(),
        title=(j.get("title") or "").strip(),
        location=j.get("candidate_required_location") or "Remote",
        description=strip_html(j.get("description") or ""),
        apply_url=j.get("url") or "",
        posted_at=posted_at,
        salary_text=j.get("salary"),
        raw={"tags": j.get("tags") or [], "job_type": j.get("job_type")},
    )
