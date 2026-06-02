"""decentrajobs.com — curated crypto/web3 job board with public JSON API.

API: GET https://decentrajobs.com/api/jobs
Returns: {"jobs": [{...}, ...]}
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from loguru import logger

from job_radar.http import client
from job_radar.models import RawJob
from job_radar.text import strip_html

URL = "https://decentrajobs.com/api/jobs"


def fetch() -> Iterable[RawJob]:
    try:
        with client() as c:
            resp = c.get(URL, headers={"Accept": "application/json"})
    except Exception as exc:
        logger.warning("decentrajobs fetch failed: {}", exc)
        return
    if resp.status_code >= 400:
        logger.warning("decentrajobs status {}", resp.status_code)
        return
    data = resp.json()
    jobs = data.get("jobs") or []
    logger.info("decentrajobs: {} jobs fetched", len(jobs))
    for j in jobs:
        try:
            raw = _parse(j)
            if raw:
                yield raw
        except Exception as exc:
            logger.debug("decentrajobs parse failed: {}", exc)


def _parse(j: dict) -> RawJob | None:
    title = (j.get("title") or "").strip()
    if not title:
        return None
    company_obj = j.get("company") or {}
    company = (company_obj.get("name") or "Unknown").strip()
    loc = j.get("location") or {}
    parts = [loc.get("city"), loc.get("state"), loc.get("country")]
    location = ", ".join(p for p in parts if p and p != "null") or "Remote"
    description = strip_html(j.get("description") or "")
    salary = j.get("salary") or {}
    salary_text = None
    if salary.get("minAmount") or salary.get("maxAmount"):
        lo = salary.get("minAmount") or "?"
        hi = salary.get("maxAmount") or "?"
        cur = salary.get("currency") or "USD"
        salary_text = f"{cur} {lo}-{hi}"
    posted_at = None
    oid = j.get("_id") or ""
    if len(oid) == 24:
        try:
            posted_at = datetime.fromtimestamp(int(oid[:8], 16))
        except (ValueError, OSError):
            pass
    apply_url = f"https://decentrajobs.com/jobs/{company_obj.get('slug', '')}/{oid}"
    return RawJob(
        source="decentrajobs",
        external_id=oid or title[:50],
        company=company,
        title=title,
        location=location,
        description=description,
        apply_url=apply_url,
        posted_at=posted_at,
        salary_text=salary_text,
        raw={"jobType": j.get("jobType"), "category": j.get("category")},
    )
