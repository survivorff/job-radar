"""LinkedIn Job Alert via Gmail IMAP.

LinkedIn doesn't let us scrape their listings (ToS + bot protection). The
work-around is:
  1. User sets up a LinkedIn Job Alert that emails them matches daily.
  2. They allow us to read those emails via Gmail IMAP app password.
  3. This adapter parses the HTML emails into jobs.

Required env:
  IMAP_HOST  (default: imap.gmail.com)
  IMAP_PORT  (default: 993)
  IMAP_USER
  IMAP_PASS        ← Gmail "App password" (16 chars, 1 of 16 for job-radar)
  IMAP_FOLDER      (default: INBOX)

We search for emails from `jobalerts-noreply@linkedin.com` in the last N days.
"""

from __future__ import annotations

import email
import imaplib
import os
import re
from datetime import datetime, timedelta
from email.utils import parseaddr, parsedate_to_datetime
from typing import Iterable
from urllib.parse import parse_qs, urlparse

from loguru import logger

from job_radar.models import RawJob
from job_radar.text import strip_html


LINKEDIN_SENDER = "jobalerts-noreply@linkedin.com"
LOOKBACK_DAYS = int(os.environ.get("JOB_RADAR_LINKEDIN_LOOKBACK", "2"))


def _get(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key) or default


def _configured() -> bool:
    return bool(os.environ.get("IMAP_USER") and os.environ.get("IMAP_PASS"))


def fetch() -> Iterable[RawJob]:
    if not _configured():
        logger.debug("linkedin_email: IMAP not configured, skipping")
        return
    try:
        yield from _fetch_imap()
    except Exception as exc:
        logger.warning("linkedin_email failed: {}", exc)


def _fetch_imap() -> Iterable[RawJob]:
    host = _get("IMAP_HOST", "imap.gmail.com")
    port = int(_get("IMAP_PORT", "993"))
    user = _get("IMAP_USER") or ""
    pwd = _get("IMAP_PASS") or ""
    folder = _get("IMAP_FOLDER", "INBOX")

    since = (datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")
    logger.info("linkedin_email: searching since {}", since)

    try:
        M = imaplib.IMAP4_SSL(host, port, timeout=20)
    except Exception as exc:
        logger.warning("IMAP connect failed: {}", exc)
        return

    try:
        M.login(user, pwd)
        M.select(folder)
        # IMAP SEARCH — case-insensitive contains
        typ, data = M.search(
            None,
            f'(FROM "{LINKEDIN_SENDER}" SINCE {since})',
        )
        if typ != "OK":
            return
        msg_ids = data[0].split()
        logger.info("linkedin_email: {} matching messages", len(msg_ids))

        for num in msg_ids[-30:]:  # latest 30 max
            typ, msg_data = M.fetch(num, "(RFC822)")
            if typ != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            yield from _parse_message(msg)
    finally:
        try:
            M.close()
        except Exception:
            pass
        M.logout()


def _parse_message(msg) -> Iterable[RawJob]:
    # Sender sanity
    _, from_addr = parseaddr(msg.get("From", ""))
    if LINKEDIN_SENDER not in from_addr.lower():
        return

    subject = msg.get("Subject", "")
    date = msg.get("Date", "")
    posted_at = None
    if date:
        try:
            posted_at = parsedate_to_datetime(date)
        except Exception:
            pass

    html = _extract_html(msg)
    if not html:
        return

    # LinkedIn wraps each job in a reasonably consistent block. Rather than
    # parse their Byzantine markup, extract every job-view link and the text
    # around it; LLM will handle the rest.
    for title, company, url, snippet in _extract_jobs_from_html(html):
        if not title:
            continue
        yield RawJob(
            source="linkedin.email",
            external_id=_external_id(url),
            company=company or "Unknown",
            title=title,
            location=_guess_location(snippet),
            description=strip_html(snippet)[:1500],
            apply_url=url,
            posted_at=posted_at,
            raw={"subject": subject},
        )


def _extract_html(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset("utf-8"), errors="replace"
                    )
                except Exception:
                    continue
    else:
        if msg.get_content_type() == "text/html":
            try:
                return msg.get_payload(decode=True).decode(
                    msg.get_content_charset("utf-8"), errors="replace"
                )
            except Exception:
                return ""
    return ""


_JOB_LINK_RE = re.compile(
    r'<a[^>]+href="(https?://www\.linkedin\.com/comm/jobs/view/[^"]+)"[^>]*>(.*?)</a>',
    flags=re.DOTALL | re.IGNORECASE,
)


def _extract_jobs_from_html(html: str) -> list[tuple[str, str, str, str]]:
    """Return list of (title, company, url, surrounding_snippet)."""
    out: list[tuple[str, str, str, str]] = []
    seen_urls: set[str] = set()
    for m in _JOB_LINK_RE.finditer(html):
        url = m.group(1)
        title = strip_html(m.group(2)).strip()
        # Dedup by job-view id
        jid = _external_id(url)
        if jid in seen_urls or not title:
            continue
        seen_urls.add(jid)
        # Take ~600 chars of surrounding context
        start = max(0, m.start() - 300)
        end = min(len(html), m.end() + 600)
        snippet = html[start:end]
        company = _guess_company(snippet)
        out.append((title, company, url, snippet))
    return out


_COMPANY_RE = re.compile(r"<strong[^>]*>\s*([^<]+?)\s*</strong>")


def _guess_company(snippet: str) -> str:
    m = _COMPANY_RE.search(snippet)
    return (m.group(1).strip() if m else "")[:120]


def _guess_location(snippet: str) -> str:
    # LinkedIn often emits the location right after the company in its own <p>
    text = strip_html(snippet)
    m = re.search(r"\b([A-Z][a-zA-Z\s,]+?(?:Remote|China|India|United States|United Kingdom|Singapore|Hong Kong|Japan|Korea|Germany|France|Canada))\b", text)
    return (m.group(1).strip() if m else "")[:120]


def _external_id(url: str) -> str:
    try:
        # URL form: https://www.linkedin.com/comm/jobs/view/{ID}?refId=...
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if "view" in parts:
            return parts[parts.index("view") + 1]
    except Exception:
        pass
    return url[:80]
