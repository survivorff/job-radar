"""jobicy.com — remote-focused RSS feed.

Filter server-side by category/region for relevance.
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

# Jobicy's feed URL supports category filters. We hit multiple buckets to
# catch everything Frank would consider.
FEEDS = [
    "https://jobicy.com/?feed=job_feed&job_categories=dev&job_types=full-time",
    "https://jobicy.com/?feed=job_feed&job_categories=dev&job_types=part-time",
    "https://jobicy.com/?feed=job_feed&job_categories=dev&job_types=contract",
    "https://jobicy.com/?feed=job_feed&job_categories=data-science&job_types=full-time",
    "https://jobicy.com/?feed=job_feed&job_categories=technical-support&job_types=full-time",
    "https://jobicy.com/?feed=job_feed&search_region=worldwide",
]


def fetch() -> Iterable[RawJob]:
    for url in FEEDS:
        try:
            yield from _fetch(url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("jobicy feed {} failed: {}", url, exc)


def _fetch(url: str) -> Iterable[RawJob]:
    with client() as c:
        resp = c.get(url, headers={"Accept": "application/rss+xml, */*"})
    if resp.status_code >= 400:
        logger.warning("jobicy status {} for {}", resp.status_code, url)
        return
    for item_xml in re.findall(r"<item>(.*?)</item>", resp.text, flags=re.DOTALL):
        try:
            job = _parse(item_xml)
            if job:
                yield job
        except Exception as exc:  # noqa: BLE001
            logger.debug("jobicy item parse failed: {}", exc)


def _tag(xml: str, name: str) -> str:
    m = re.search(
        rf"<{name}(?:\s[^>]*)?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{name}>",
        xml,
        flags=re.DOTALL,
    )
    return (m.group(1).strip() if m else "")


def _parse(xml: str) -> RawJob | None:
    title = _tag(xml, "title")
    link = _tag(xml, "link")
    desc = strip_html(_tag(xml, "description"))
    pub = _tag(xml, "pubDate")
    company = _tag(xml, "job_listing:company")
    location = _tag(xml, "job_listing:location") or "Remote"
    region = _tag(xml, "job_listing:region")

    if not title or not link:
        return None

    if not company:
        # some items stringify "Role at Company" in title
        m = re.match(r"^(.*?)\s+at\s+(.+)$", title)
        if m:
            title = m.group(1).strip()
            company = m.group(2).strip()
    company = company or "Unknown"

    if region and region.lower() not in location.lower():
        location = f"{location} · {region}"

    posted_at: datetime | None = None
    if pub:
        try:
            posted_at = parsedate_to_datetime(pub)
        except (TypeError, ValueError):
            pass

    return RawJob(
        source="jobicy",
        external_id=link.rsplit("/", 2)[-2] if link.endswith("/") else link.rsplit("/", 1)[-1],
        company=company,
        title=title,
        location=location,
        description=desc,
        apply_url=link,
        posted_at=posted_at,
        raw={},
    )
