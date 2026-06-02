"""Career pages publishing JSON-LD JobPosting structured data.

Many large engineering companies embed Schema.org JobPosting JSON in their
official careers page HTML for Google Jobs SEO. This scrapes that JSON —
which is legal (it's designed to be crawled) and far more reliable than
parsing custom HTML.

We ship a small seed list; adding a company is one line.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from loguru import logger

from job_radar.http import client
from job_radar.models import RawJob
from job_radar.text import strip_html


@dataclass(frozen=True)
class CareerPage:
    company_name: str
    url: str  # /careers or /jobs page
    browser_ua: bool = True  # whether to send a browser-like UA (for CF-protected sites)


CAREER_PAGES: list[CareerPage] = [
    # Add company careers pages here. Each must serve JSON-LD JobPosting blocks.
    # We skip known-Cloudflare-protected ones unless a browser UA works.
]


_JSONLD_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    flags=re.DOTALL | re.IGNORECASE,
)


def fetch_page(page: CareerPage) -> list[RawJob]:
    headers = {"Accept": "text/html"}
    if page.browser_ua:
        headers["User-Agent"] = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
        )
    try:
        with client() as c:
            resp = c.get(page.url, headers=headers)
    except Exception as exc:
        logger.warning("careers {} fetch failed: {}", page.company_name, exc)
        return []
    if resp.status_code >= 400:
        logger.warning("careers {} status {}", page.company_name, resp.status_code)
        return []

    out: list[RawJob] = []
    for m in _JSONLD_RE.finditer(resp.text):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        for item in _flatten(data):
            if not isinstance(item, dict):
                continue
            t = item.get("@type")
            types = [t] if isinstance(t, str) else list(t) if isinstance(t, list) else []
            if "JobPosting" not in types:
                continue
            try:
                out.append(_parse(page, item))
            except Exception as exc:
                logger.debug("careers {} parse failed: {}", page.company_name, exc)
    return out


def _flatten(x) -> list:
    if isinstance(x, dict):
        if "@graph" in x and isinstance(x["@graph"], list):
            return x["@graph"]
        return [x]
    if isinstance(x, list):
        out = []
        for item in x:
            out.extend(_flatten(item))
        return out
    return []


def fetch() -> Iterable[RawJob]:
    for page in CAREER_PAGES:
        try:
            yield from fetch_page(page)
        except Exception as exc:
            logger.warning("careers page {} failed: {}", page.company_name, exc)


def _parse(page: CareerPage, item: dict) -> RawJob:
    title = (item.get("title") or "").strip()
    desc = strip_html(item.get("description") or "")
    apply_url = item.get("url") or item.get("hiringOrganization", {}).get("sameAs") or page.url

    location = ""
    loc = item.get("jobLocation")
    if isinstance(loc, dict):
        addr = loc.get("address") or {}
        parts = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
        location = ", ".join(p for p in parts if p)
    elif isinstance(loc, list) and loc:
        first = loc[0]
        if isinstance(first, dict):
            addr = first.get("address") or {}
            parts = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
            location = ", ".join(p for p in parts if p)

    is_remote = bool(item.get("jobLocationType") == "TELECOMMUTE")

    posted_at = None
    raw_posted = item.get("datePosted")
    if raw_posted:
        try:
            posted_at = datetime.fromisoformat(str(raw_posted).replace("Z", "+00:00"))
        except ValueError:
            pass

    return RawJob(
        source=f"careers:{page.url.split('/')[2]}",
        external_id=(apply_url or title)[:200],
        company=page.company_name,
        title=title,
        location=location or ("Remote" if is_remote else ""),
        description=desc,
        apply_url=apply_url,
        posted_at=posted_at,
        raw=item,
    )
