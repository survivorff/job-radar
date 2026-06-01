"""Resend.com HTTP API email sender.

Why this exists: Chinese cloud providers (aliyun/腾讯云/etc.) block outbound
SMTP to Gmail, so the deployed skill on a cloud box can't use Gmail SMTP.
Resend is HTTPS, free for <100 emails/day, and works out of the box with the
sandbox sender `onboarding@resend.dev` — no domain verification required.

Signup: https://resend.com/signup → API Keys → new key → paste into .env
"""

from __future__ import annotations

import os
from datetime import datetime

import httpx
from loguru import logger

from job_radar.channels.email_smtp import SendResult
from job_radar.config import get_settings

API_URL = "https://api.resend.com/emails"
SANDBOX_FROM = "Job Radar <onboarding@resend.dev>"


def is_configured() -> bool:
    return bool(_get_key())


def _get_key() -> str | None:
    """Fetch the Resend key from either os.environ or the .env-backed Settings."""
    from job_radar.config import get_settings

    key = os.environ.get("RESEND_API_KEY")
    if key:
        return key
    s = get_settings()
    return getattr(s, "resend_api_key", None)


def send_email(subject: str, html: str, text: str | None = None) -> SendResult:
    key = _get_key()
    if not key:
        return SendResult(ok=False, error="RESEND_API_KEY not set")

    s = get_settings()
    to = s.smtp_to
    if not to:
        return SendResult(ok=False, error="SMTP_TO not set (used as recipient)")

    sender = s.smtp_from or SANDBOX_FROM
    # Resend requires verified domain for custom `from`. If user hasn't set
    # SMTP_FROM or it looks like a non-verified address, fall back to sandbox.
    if "@resend.dev" not in sender and not getattr(s, "resend_domain_verified", False):
        sender = SANDBOX_FROM

    payload = {
        "from": sender,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = httpx.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30.0,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"resend {resp.status_code}: {resp.text[:400]}")
            data = resp.json()
            logger.info("resend email sent: {} (id={})", subject, data.get("id"))
            return SendResult(ok=True, message_id=data.get("id"))
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("resend attempt {} failed: {}", attempt + 1, exc)
            import time

            time.sleep(1.5 * (attempt + 1))
    return SendResult(ok=False, error=f"{type(last_exc).__name__}: {last_exc}")


def send_digest(digest) -> SendResult:
    from job_radar.channels.digest import render_digest_html, render_digest_subject
    from job_radar.db import PushRow, session_scope

    subject = render_digest_subject(digest)
    html = render_digest_html(digest)
    res = send_email(subject, html)
    if res.ok:
        with session_scope() as sess:
            for bucket in (digest.high, digest.med, digest.low):
                for item in bucket:
                    sess.add(
                        PushRow(
                            match_id=item.match_id,
                            channel="resend",
                            tier=item.tier,
                            kind=digest.kind,
                            sent_at=datetime.utcnow(),
                            external_ref=res.message_id or "",
                        )
                    )
    return res
