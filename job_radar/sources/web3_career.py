"""web3.career (HTML-backed).

The public JSON API now requires a token, so we parse the main listing page
directly. We only look at the AI-filtered listing to stay relevant; this
also keeps our request volume minimal (one page load per run).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime, timedelta
from urllib.parse import urljoin

from loguru import logger

from job_radar.http import client
from job_radar.models import RawJob
from job_radar.text import strip_html

LISTING_URL = "https://web3.career/remote-ai-jobs"


def fetch() -> Iterable[RawJob]:
    try:
        with client() as c:
            resp = c.get(LISTING_URL, headers={"Accept": "text/html"})
    except Exception as exc:  # noqa: BLE001
        logger.warning("web3.career fetch failed: {}", exc)
        return

    if resp.status_code >= 400:
        logger.warning("web3.career status {}", resp.status_code)
        return

    # Rows are <tr class="table_row"> with data-* attributes. Rather than
    # pulling a full HTML parser, regex the fields we need; the site is
    # templated and stable.
    html = resp.text
    rows = re.findall(
        r'<tr[^>]*class="[^"]*table_row[^"]*"[^>]*>(.*?)</tr>',
        html,
        flags=re.DOTALL,
    )
    if not rows:
        logger.debug("web3.career: no table_row matches — layout may have changed")
        return

    for row in rows:
        try:
            job = _parse_row(row)
            if job:
                yield job
        except Exception as exc:  # noqa: BLE001
            logger.debug("web3.career row parse failed: {}", exc)


def _parse_row(row_html: str) -> RawJob | None:
    # Anchor to job detail page
    href_m = re.search(r'href="(/[^"]+)"', row_html)
    if not href_m:
        return None
    apply_url = urljoin("https://web3.career", href_m.group(1))
    slug = href_m.group(1).strip("/").split("/")[-1]

    # Title: first plain-text inside the link
    title_m = re.search(
        r'<a[^>]+href="/[^"]+"[^>]*>\s*<span[^>]*>([^<]+)</span>',
        row_html,
    )
    if not title_m:
        # fallback — strip all HTML
        title_m = re.search(r"<h2[^>]*>([^<]+)</h2>", row_html)
    title = (title_m.group(1) if title_m else "").strip()
    if not title:
        return None

    # Company: second <a> usually carries company name
    company_m = re.search(
        r'<a[^>]*href="/company/[^"]+"[^>]*>\s*<h3[^>]*>([^<]+)</h3>',
        row_html,
    )
    if not company_m:
        company_m = re.search(r'company/[^"]+"[^>]*>\s*([^<]+)\s*<', row_html)
    company = (company_m.group(1) if company_m else "Unknown").strip()

    # Location: anything that looks like "Remote" or city name in a <td>
    location = ""
    loc_m = re.search(
        r"<td[^>]*class=\"[^\"]*job-location-mobile[^\"]*\"[^>]*>(.*?)</td>",
        row_html,
        flags=re.DOTALL,
    )
    if loc_m:
        location = strip_html(loc_m.group(1))
    if not location and "remote" in row_html.lower():
        location = "Remote"

    # Salary
    salary = None
    sal_m = re.search(r"\$[\d,]+k?\s*[-–]\s*\$?[\d,]+k?", row_html, flags=re.IGNORECASE)
    if sal_m:
        salary = sal_m.group(0)

    posted_at = _parse_relative_time(row_html)

    # Description: we only have the row preview on the listing. The full JD
    # is on the detail page; skipping to respect rate limit. The row text
    # contains tags which still carry signal for keyword matching.
    desc_bits = strip_html(row_html)
    desc_bits = re.sub(r"\s+", " ", desc_bits).strip()

    return RawJob(
        source="web3.career",
        external_id=slug,
        company=company,
        title=title,
        location=location,
        description=desc_bits,
        apply_url=apply_url,
        posted_at=posted_at,
        salary_text=salary,
        raw={"html_row": row_html[:2000]},
    )


_REL_RE = re.compile(r"(\d+)\s*(day|week|month|hour)s?\s+ago", flags=re.IGNORECASE)


def _parse_relative_time(blob: str) -> datetime | None:
    m = _REL_RE.search(blob)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    now = datetime.utcnow()
    if unit == "hour":
        return now - timedelta(hours=n)
    if unit == "day":
        return now - timedelta(days=n)
    if unit == "week":
        return now - timedelta(weeks=n)
    if unit == "month":
        return now - timedelta(days=n * 30)
    return None
