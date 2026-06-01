"""dejob.ai — Chinese Web3 remote job board.

API: GET https://dejob.ai/api/worker/topics?page=1&pageSize=50
Returns: {"data": {"page": {...}, "results": [...]}}
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from loguru import logger

from job_radar.http import client
from job_radar.models import RawJob

URL = "https://dejob.ai/api/worker/topics"
PAGES_TO_FETCH = 3


def fetch() -> Iterable[RawJob]:
    seen: set[int] = set()
    for page in range(1, PAGES_TO_FETCH + 1):
        try:
            yield from _fetch_page(page, seen)
        except Exception as exc:
            logger.warning("dejob page {} failed: {}", page, exc)


def _fetch_page(page: int, seen: set[int]) -> Iterable[RawJob]:
    with client() as c:
        resp = c.get(URL, params={"page": page, "pageSize": 50})
    if resp.status_code >= 400:
        logger.warning("dejob status {}", resp.status_code)
        return
    data = resp.json().get("data", {})
    results = data.get("results") or []
    for item in results:
        tid = item.get("topicId")
        if not tid or tid in seen:
            continue
        seen.add(tid)
        try:
            job = _parse(item)
            if job:
                yield job
        except Exception as exc:
            logger.debug("dejob parse failed: {}", exc)


def _parse(item: dict) -> RawJob | None:
    title = (item.get("positionName") or "").strip()
    if not title:
        return None
    content = item.get("content") or ""
    content2 = item.get("content2") or ""
    content3 = item.get("content3") or ""
    description = f"{content}\n\n要求：\n{content2}\n\n福利：\n{content3}".strip()
    user = item.get("user") or {}
    company = (user.get("nickname") or "DeJob Listing").split("@")[0].strip()
    content5 = item.get("content5") or ""
    if content5:
        company = content5.strip()[:80]
    location = "Remote" if ("远程" in description or "remote" in description.lower()) else ""
    salary_text = content3.strip()[:100] if content3 else None
    posted_at = None
    create_time = item.get("createTime")
    if isinstance(create_time, int) and create_time > 1_000_000_000_000:
        try:
            posted_at = datetime.fromtimestamp(create_time / 1000)
        except (ValueError, OSError):
            pass
    apply_url = f"https://dejob.ai/jobs/{item.get('topicId')}"
    return RawJob(
        source="dejob.ai",
        external_id=str(item.get("topicId")),
        company=company,
        title=title,
        location=location,
        description=description,
        apply_url=apply_url,
        posted_at=posted_at,
        salary_text=salary_text,
        raw={
            "telegram": item.get("telegram") or "",
            "wechat": item.get("wechat") or "",
            "email": item.get("email") or "",
        },
    )
