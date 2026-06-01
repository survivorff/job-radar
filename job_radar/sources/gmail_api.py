"""Gmail REST API adapter — reads LinkedIn Job Alert emails via HTTPS.

Why this exists: IMAP is blocked by many cloud firewalls (aliyun/Tencent).
Gmail's REST API is served over HTTPS (api.googleapis.com:443) so it works
from any egress-restricted host.

Auth flow (one-time OAuth2):
  1. User runs `job-radar gmail-auth` locally
  2. Browser opens, user grants scope `https://www.googleapis.com/auth/gmail.readonly`
  3. Refresh token is saved to ~/.job-radar/gmail_token.json
  4. Server can then run forever using the refresh token to get short-lived access tokens

Env required:
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET
  (token in ~/.job-radar/gmail_token.json)

We parse the same LinkedIn email format as linkedin_email.py.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import httpx
from loguru import logger

from job_radar.config import get_settings
from job_radar.models import RawJob
from job_radar.sources.linkedin_email import _extract_jobs_from_html, _external_id, _guess_location
from job_radar.text import strip_html

SENDER = "jobalerts-noreply@linkedin.com"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _token_file() -> Path:
    s = get_settings()
    return s.data_dir.parent / "gmail_token.json"


def _load_token() -> dict | None:
    p = _token_file()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _save_token(data: dict) -> None:
    p = _token_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def _access_token() -> str | None:
    """Get a valid access token, refreshing if needed."""
    token = _load_token()
    if not token:
        return None

    # Check expiry
    expires_at = token.get("_expires_at", 0)
    if datetime.utcnow().timestamp() < expires_at - 60:
        return token.get("access_token")

    client_id = os.environ.get("GOOGLE_CLIENT_ID") or token.get("client_id")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET") or token.get("client_secret")
    refresh_token = token.get("refresh_token")
    if not (client_id and client_secret and refresh_token):
        logger.warning("gmail: cannot refresh — missing client_id/secret/refresh_token")
        return None

    try:
        resp = httpx.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("gmail token refresh failed: {}", exc)
        return None

    access = data.get("access_token")
    expires_in = int(data.get("expires_in", 3600))
    token["access_token"] = access
    token["_expires_at"] = int(datetime.utcnow().timestamp()) + expires_in
    token.setdefault("client_id", client_id)
    token.setdefault("client_secret", client_secret)
    _save_token(token)
    return access


def _is_configured() -> bool:
    return _load_token() is not None


def fetch() -> Iterable[RawJob]:
    if not _is_configured():
        logger.debug("gmail_api: token not configured; skip. Run `job-radar gmail-auth` locally first.")
        return
    try:
        yield from _fetch()
    except Exception as exc:
        logger.warning("gmail_api failed: {}", exc)


def _fetch() -> Iterable[RawJob]:
    access = _access_token()
    if not access:
        return

    days = int(os.environ.get("JOB_RADAR_LINKEDIN_LOOKBACK", "3"))
    after = (datetime.utcnow() - timedelta(days=days)).strftime("%Y/%m/%d")
    q = f'from:{SENDER} after:{after}'

    headers = {"Authorization": f"Bearer {access}"}
    with httpx.Client(headers=headers, timeout=30.0) as c:
        # List message ids
        resp = c.get(f"{API_BASE}/messages", params={"q": q, "maxResults": 30})
        if resp.status_code >= 400:
            logger.warning("gmail list messages {}: {}", resp.status_code, resp.text[:300])
            return
        msgs = resp.json().get("messages") or []
        logger.info("gmail_api: {} messages matching '{}'", len(msgs), q)
        for ref in msgs:
            mid = ref.get("id")
            if not mid:
                continue
            try:
                msg_resp = c.get(f"{API_BASE}/messages/{mid}", params={"format": "full"})
                msg_resp.raise_for_status()
                yield from _parse_message(msg_resp.json())
            except Exception as exc:
                logger.debug("gmail_api message {} failed: {}", mid, exc)


def _parse_message(msg: dict) -> Iterable[RawJob]:
    payload = msg.get("payload", {})
    internal_ms = int(msg.get("internalDate") or 0)
    posted_at = datetime.utcfromtimestamp(internal_ms / 1000) if internal_ms else None

    html = _find_html(payload)
    if not html:
        return

    for title, company, url, snippet in _extract_jobs_from_html(html):
        if not title:
            continue
        yield RawJob(
            source="gmail.linkedin",
            external_id=_external_id(url),
            company=company or "Unknown",
            title=title,
            location=_guess_location(snippet),
            description=strip_html(snippet)[:1500],
            apply_url=url,
            posted_at=posted_at,
            raw={"gmail_id": msg.get("id")},
        )


def _find_html(part: dict) -> str:
    """Walk MIME parts and return the first text/html body."""
    mime = part.get("mimeType", "")
    body = part.get("body", {})
    data = body.get("data")
    if mime == "text/html" and data:
        return _decode_b64(data)
    for sub in part.get("parts") or []:
        html = _find_html(sub)
        if html:
            return html
    return ""


def _decode_b64(s: str) -> str:
    # Gmail uses URL-safe base64
    s += "=" * (-len(s) % 4)
    try:
        return base64.urlsafe_b64decode(s).decode("utf-8", errors="replace")
    except Exception:
        return ""
