"""Gmail / SMTP sender. Plaintext + HTML, TLS on 587."""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from loguru import logger
from sqlalchemy import select

from job_radar.channels.digest import Digest
from job_radar.config import get_settings
from job_radar.db import MatchRow, PushRow, session_scope


@dataclass
class SendResult:
    ok: bool
    error: str | None = None
    message_id: str | None = None


def send_email(subject: str, html: str, text: str | None = None) -> SendResult:
    s = get_settings()
    if not s.smtp_configured:
        return SendResult(ok=False, error="SMTP not configured (check .env)")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("Job Radar", s.smtp_from or s.smtp_user or ""))
    msg["To"] = s.smtp_to or ""
    mid = make_msgid(domain="job-radar.local")
    msg["Message-ID"] = mid
    msg.set_content(text or _html_to_text_fallback(html))
    msg.add_alternative(html, subtype="html")

    # Up to 3 attempts — Gmail SMTP occasionally drops mid-handshake.
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(s.smtp_user or "", s.smtp_pass or "")
                smtp.send_message(msg)
            logger.info("email sent: {}", subject)
            return SendResult(ok=True, message_id=mid)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("SMTP attempt {} failed: {}", attempt + 1, exc)
            import time

            time.sleep(1.5 * (attempt + 1))
    logger.error("SMTP send failed after 3 attempts: {}", last_exc)
    return SendResult(ok=False, error=f"{type(last_exc).__name__}: {last_exc}")


def send_digest(digest: Digest) -> SendResult:
    from job_radar.channels.digest import render_digest_html, render_digest_subject

    subject = render_digest_subject(digest)
    html = render_digest_html(digest)
    res = send_email(subject, html)
    if res.ok:
        _record_pushes(digest, res.message_id)
    return res


def _record_pushes(digest: Digest, message_id: str | None) -> None:
    with session_scope() as sess:
        for bucket in (digest.high, digest.med, digest.low):
            for item in bucket:
                sess.add(
                    PushRow(
                        match_id=item.match_id,
                        channel="email",
                        tier=item.tier,
                        kind=digest.kind,
                        sent_at=datetime.utcnow(),
                        external_ref=message_id or "",
                    )
                )


def _html_to_text_fallback(html: str) -> str:
    import re

    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
