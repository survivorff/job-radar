"""remoteok.com — large remote board with JSON API (no auth).

Endpoint: https://remoteok.com/api
Returns an array; first element is the legal disclaimer, rest are jobs.
We filter server-side to crypto / ai tags by post-filtering.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from loguru import logger

from job_radar.http import client
from job_radar.models import RawJob
from job_radar.text import strip_html

URL = "https://remoteok.com/api"

# RemoteOK is general-purpose. We keep ALL senior backend / fullstack /
# AI / crypto posts and let the downstream track + LLM do the narrowing.
TAGS_OF_INTEREST = {
    # Crypto
    "crypto", "web3", "blockchain", "defi", "dex", "nft", "solana",
    "ethereum", "bitcoin", "solidity",
    # AI / ML
    "ai", "ml", "llm", "agent", "agents", "langchain", "rag",
    # Eng levels / stacks
    "senior", "staff", "principal", "lead", "architect", "cto",
    "founding", "co-founder",
    "engineering", "dev", "developer",
    "backend", "back-end", "full-stack", "fullstack", "full stack",
    # Languages
    "python", "java", "go", "golang", "rust", "typescript",
    "node.js", "nodejs",
    # Role type
    "software", "infrastructure", "platform", "devops", "sre",
    "distributed", "database", "api", "microservices",
}


def fetch() -> Iterable[RawJob]:
    try:
        with client() as c:
            resp = c.get(URL, headers={"Accept": "application/json"})
    except Exception as exc:  # noqa: BLE001
        logger.warning("remoteok fetch failed: {}", exc)
        return
    if resp.status_code >= 400:
        logger.warning("remoteok status {}", resp.status_code)
        return
    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("remoteok bad json: {}", exc)
        return

    for item in data:
        if not isinstance(item, dict) or not item.get("id"):
            continue  # skip the disclaimer element
        try:
            tags = [t.lower() for t in (item.get("tags") or [])]
            if not any(t in TAGS_OF_INTEREST for t in tags):
                continue
            job = _parse(item)
            if job:
                yield job
        except Exception as exc:  # noqa: BLE001
            logger.debug("remoteok parse failed: {}", exc)


def _parse(j: dict) -> RawJob | None:
    title = (j.get("position") or j.get("title") or "").strip()
    company = (j.get("company") or "Unknown").strip()
    if not title or not company:
        return None
    apply_url = j.get("apply_url") or j.get("url") or ""
    location = j.get("location") or "Remote"
    description = strip_html(j.get("description") or "")

    posted_at: datetime | None = None
    if j.get("date"):
        try:
            posted_at = datetime.fromisoformat(str(j["date"]).replace("Z", "+00:00"))
        except ValueError:
            pass
    elif j.get("epoch"):
        try:
            posted_at = datetime.fromtimestamp(int(j["epoch"]))
        except (ValueError, TypeError, OSError):
            pass

    salary_text = None
    if j.get("salary_min") or j.get("salary_max"):
        lo = j.get("salary_min") or "?"
        hi = j.get("salary_max") or "?"
        salary_text = f"${lo}-${hi}"

    return RawJob(
        source="remoteok",
        external_id=str(j.get("id")),
        company=company,
        title=title,
        location=location,
        description=description,
        apply_url=apply_url,
        posted_at=posted_at,
        salary_text=salary_text,
        raw={"tags": j.get("tags") or []},
    )
