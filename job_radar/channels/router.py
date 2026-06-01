"""Picks the right email channel based on what's configured.

Priority:
  1. RESEND_API_KEY set → Resend (HTTPS, works behind alicloud firewalls)
  2. SMTP_USER + SMTP_PASS set → Gmail/Outlook SMTP
  3. Else → preview-only (write HTML to disk)
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from job_radar.channels import email_resend, email_smtp
from job_radar.channels.email_smtp import SendResult
from job_radar.config import get_settings


def pick_sender_name() -> str:
    if email_resend.is_configured():
        return "resend"
    if get_settings().smtp_configured:
        return "smtp"
    return "preview"


def send_email(subject: str, html: str, text: str | None = None) -> SendResult:
    name = pick_sender_name()
    if name == "resend":
        return email_resend.send_email(subject, html, text)
    if name == "smtp":
        return email_smtp.send_email(subject, html, text)
    # preview fallback: write the rendered HTML to disk so the user can open it
    out = get_settings().logs_dir / "last_email.html"
    out.write_text(html, encoding="utf-8")
    logger.warning("no email channel configured; preview written to {}", out)
    return SendResult(ok=False, error=f"no email channel configured (preview at {out})")


def send_digest(digest) -> SendResult:
    name = pick_sender_name()
    if name == "resend":
        return email_resend.send_digest(digest)
    if name == "smtp":
        return email_smtp.send_digest(digest)
    # preview fallback
    from job_radar.channels.digest import render_digest_html, render_digest_subject

    out = get_settings().logs_dir / "last_digest.html"
    out.write_text(render_digest_html(digest), encoding="utf-8")
    logger.warning(
        "no email channel configured; digest preview written to {} (subject: {})",
        out,
        render_digest_subject(digest),
    )
    return SendResult(ok=False, error=f"no email channel configured (preview at {out})")
