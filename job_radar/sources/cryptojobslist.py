"""cryptojobslist.com (RSS).

RSS includes title/link/description/pubDate per job; we filter to AI-adjacent
titles to keep the volume sane.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime
from email.utils import parsedate_to_datetime

from loguru import logger

from job_radar.http import client
from job_radar.models import RawJob
from job_radar.text import strip_html

# CJL publishes separate feeds per tag. AI / ML / Data are the ones we want.
FEEDS = [
    "https://cryptojobslist.com/tags/ai-jobs.rss",
    "https://cryptojobslist.com/tags/machine-learning.rss",
    "https://cryptojobslist.com/engineering.rss",  # backend/infra overlap
]


def fetch() -> Iterable[RawJob]:
    for url in FEEDS:
        try:
            yield from _fetch_feed(url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cryptojobslist feed {} failed: {}", url, exc)


def _fetch_feed(url: str) -> Iterable[RawJob]:
    with client() as c:
        resp = c.get(url, headers={"Accept": "application/rss+xml, */*"})
    if resp.status_code >= 400:
        logger.warning("cryptojobslist status {} for {}", resp.status_code, url)
        return

    xml = resp.text
    items = re.findall(r"<item>(.*?)</item>", xml, flags=re.DOTALL)
    for item in items:
        try:
            job = _parse_item(item, url)
            if job:
                yield job
        except Exception as exc:  # noqa: BLE001
            logger.debug("cryptojobslist item parse failed: {}", exc)


def _tag(item: str, tag: str) -> str:
    m = re.search(
        rf"<{tag}(?:\s[^>]*)?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>",
        item,
        flags=re.DOTALL,
    )
    return (m.group(1).strip() if m else "")


def _parse_item(item: str, feed_url: str) -> RawJob | None:
    title = _tag(item, "title")
    link = _tag(item, "link")
    desc = strip_html(_tag(item, "description"))
    pub = _tag(item, "pubDate")
    category = _tag(item, "category")

    if not title or not link:
        return None

    # Title is typically "<Title> at <Company> | Crypto Jobs List"
    company = "Unknown"
    clean_title = title
    m = re.match(r"^(.*?)\s+at\s+(.+?)(\s*\|\s*Crypto Jobs List.*)?$", title)
    if m:
        clean_title = m.group(1).strip()
        company = m.group(2).strip()

    # Location: try to extract common markers from description
    location = "Remote" if re.search(r"\bremote\b", desc, flags=re.IGNORECASE) else ""

    posted_at: datetime | None = None
    if pub:
        try:
            posted_at = parsedate_to_datetime(pub)
        except (TypeError, ValueError):
            posted_at = None

    return RawJob(
        source="cryptojobslist",
        external_id=link.rsplit("/", 1)[-1] or link,
        company=company,
        title=clean_title,
        location=location,
        description=desc,
        apply_url=link,
        posted_at=posted_at,
        raw={"feed": feed_url, "category": category},
    )
