"""weworkremotely.com — categories RSS feeds.

Two feeds give us the best signal:
  - remote-programming-jobs: backend/AI engineers
  - remote-devops-sysadmin-jobs: infra
"""

from __future__ import annotations

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Iterable

from loguru import logger

from job_radar.http import client
from job_radar.models import RawJob
from job_radar.text import strip_html

FEEDS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
]


def fetch() -> Iterable[RawJob]:
    for url in FEEDS:
        try:
            yield from _fetch(url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("wwr feed {} failed: {}", url, exc)


def _fetch(url: str) -> Iterable[RawJob]:
    with client() as c:
        resp = c.get(url, headers={"Accept": "application/rss+xml, */*"})
    if resp.status_code >= 400:
        logger.warning("wwr status {} for {}", resp.status_code, url)
        return
    for item_xml in re.findall(r"<item>(.*?)</item>", resp.text, flags=re.DOTALL):
        try:
            job = _parse(item_xml, url)
            if job:
                yield job
        except Exception as exc:  # noqa: BLE001
            logger.debug("wwr item parse failed: {}", exc)


def _tag(xml: str, name: str) -> str:
    m = re.search(
        rf"<{name}(?:\s[^>]*)?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{name}>",
        xml,
        flags=re.DOTALL,
    )
    return (m.group(1).strip() if m else "")


def _parse(xml: str, feed_url: str) -> RawJob | None:
    title_raw = _tag(xml, "title")
    link = _tag(xml, "link")
    desc = strip_html(_tag(xml, "description"))
    pub = _tag(xml, "pubDate")
    region = _tag(xml, "region")

    if not title_raw or not link:
        return None

    # WWR title format: "Company: Job Title"
    company = "Unknown"
    title = title_raw
    if ":" in title_raw:
        parts = title_raw.split(":", 1)
        company = parts[0].strip()
        title = parts[1].strip()

    location = region or "Remote"
    if "remote" in title_raw.lower() or "remote" in desc.lower():
        location = "Remote" if not region else f"Remote · {region}"

    posted_at: datetime | None = None
    if pub:
        try:
            posted_at = parsedate_to_datetime(pub)
        except (TypeError, ValueError):
            pass

    return RawJob(
        source="weworkremotely",
        external_id=link.rsplit("/", 1)[-1] or link,
        company=company,
        title=title,
        location=location,
        description=desc,
        apply_url=link,
        posted_at=posted_at,
        raw={"feed": feed_url},
    )
