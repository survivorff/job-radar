"""HN 'Who is hiring?' monthly thread (Algolia HN API, no auth needed).

Each month at the start, someone posts a stickied thread. Top-level comments
are job postings. Density of remote crypto/AI roles is extremely high here.

To keep noise down we pre-filter comments at ingest time — we only yield
posts whose first line mentions at least one word we care about.

Parsing is best-effort: HN posters don't follow a rigid format, so we use
the comment author as the default company and fall back to any obvious
"Company | Title" splits. Upstream LLM scoring then cleans up the messy
cases.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime

from loguru import logger

from job_radar.http import client
from job_radar.models import RawJob
from job_radar.text import strip_html

SEARCH_URL = "https://hn.algolia.com/api/v1/search"
ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"

# Only keep comments whose first line contains at least one of these (case
# insensitive). Expanded to reflect Frank's broader 6-track profile.
HEADLINE_KEYWORDS = [
    # AI
    "ai", "ml", "llm", "rag", "agent", "agents", "langchain", "langgraph",
    "mcp", "vector", "embedding",
    # Crypto / web3
    "crypto", "web3", "blockchain", "defi", "dex", "cex", "exchange",
    "wallet", "solana", "ethereum", "evm", "solidity",
    # Backend
    "backend", "infrastructure", "infra", "platform", "distributed",
    "python", "java", "go", "rust", "kubernetes", "typescript",
    # Seniority signal
    "senior", "staff", "principal", "lead",
]


def _find_latest_thread_id() -> int | None:
    try:
        with client() as c:
            resp = c.get(
                SEARCH_URL,
                params={
                    "query": "Ask HN: Who is hiring?",
                    "tags": "story,author_whoishiring",
                    "hitsPerPage": 3,
                },
            )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        if not hits:
            return None
        return int(hits[0]["objectID"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("hn hiring: thread lookup failed: {}", exc)
        return None


def _fetch_thread(thread_id: int) -> dict | None:
    try:
        with client() as c:
            resp = c.get(ITEM_URL.format(id=thread_id))
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("hn hiring: thread fetch failed: {}", exc)
        return None


# Heuristic: REMOTE | Company | Role
_HEADER_RE = re.compile(
    r"^\s*([\w .&+\-@/]+?)\s*(?:\||·|—|-|:)\s*(.+?)\s*$",
    flags=re.MULTILINE,
)


def _parse_comment(c: dict) -> RawJob | None:
    text = strip_html(c.get("text") or "")
    if not text.strip():
        return None

    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if not first_line or len(first_line) > 250:
        return None

    # Pre-filter: keep only comments that mention a headline keyword.
    first_lower = first_line.lower()
    if not any(kw in first_lower for kw in HEADLINE_KEYWORDS):
        return None

    # Company / title heuristic — HN "Who is hiring" format is very loose.
    # Common patterns we see in practice:
    #   "Coinbase (YC S12) | Remote | Senior Backend Eng"
    #   "CompanyX — Senior Engineer — Remote"
    #   "Senior Engineer at Foobar Inc. (Remote)"
    #   "Anthropic | San Francisco or REMOTE | Software Engineer"
    #
    # We try (in order): pipe split, dash split, "at" split, then default.
    company = "HN Listing"
    title = first_line[:200]

    pipe_parts = [p.strip() for p in first_line.split("|") if p.strip()]
    if len(pipe_parts) >= 2:
        # First part is usually company (possibly with YC / funding tag)
        company = re.sub(r"\(.*?\)", "", pipe_parts[0]).strip() or pipe_parts[0]
        # Title = last part that looks job-titley (has "Engineer"/"Developer"/etc.)
        for part in pipe_parts[1:]:
            if re.search(r"\b(Engineer|Developer|Architect|Lead|Manager|Scientist|Analyst)\b", part, flags=re.IGNORECASE):
                title = part
                break
        else:
            title = pipe_parts[-1]
    else:
        m = re.search(r"^(.+?)\s+at\s+(.+)$", first_line)
        if m:
            title = m.group(1).strip()
            company = m.group(2).strip()
        else:
            m2 = re.match(r"^(.+?)\s*(?:—|–|-)\s*(.+)$", first_line)
            if m2:
                # Ambiguous — could be "Company - Title" or "Title - Location".
                # If left side has "Engineer", assume it's title-first.
                if re.search(r"\b(Engineer|Developer|Architect|Lead|Manager)\b", m2.group(1), flags=re.IGNORECASE):
                    title = m2.group(1).strip()
                    company = m2.group(2).strip()
                else:
                    company = m2.group(1).strip()
                    title = m2.group(2).strip()

    # Clean stray marketing
    company = re.sub(r"\s+", " ", company).strip()[:120]
    title = re.sub(r"\s+", " ", title).strip()[:220]

    # Reject if parsing failed and we got garbage
    if not title or title.lower() in {"remote", "no remote", "onsite"}:
        return None
    if len(company) > 80 and " " in company:  # probably ate the whole line
        company = "HN Listing"

    # URL: first http(s) link in body
    url_m = re.search(r"https?://[^\s)]+", text)
    apply_url = url_m.group(0) if url_m else f"https://news.ycombinator.com/item?id={c.get('id')}"

    # Location clues
    is_remote = bool(re.search(r"\bremote\b", first_line, flags=re.IGNORECASE))
    location = "Remote" if is_remote else ""
    loc_m = re.search(r"\b(SF|NYC|NY|London|Berlin|Singapore|Tokyo|APAC|EMEA|US|EU|UK)\b", first_line)
    if loc_m:
        location = (location + " · " + loc_m.group(1)) if location else loc_m.group(1)

    created = c.get("created_at")
    posted_at = None
    if created:
        try:
            posted_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            posted_at = None

    return RawJob(
        source="hn.whoishiring",
        external_id=str(c.get("id")),
        company=company[:120],
        title=title[:220],
        location=location,
        description=text,
        apply_url=apply_url,
        posted_at=posted_at,
        raw={"parent": c.get("parent_id"), "author": c.get("author")},
    )


def fetch() -> Iterable[RawJob]:
    thread_id = _find_latest_thread_id()
    if not thread_id:
        return
    root = _fetch_thread(thread_id)
    if not root:
        return
    # Top-level children are the job posts
    for child in root.get("children") or []:
        # Ignore deleted or empty
        if not child or child.get("deleted"):
            continue
        try:
            job = _parse_comment(child)
            if job:
                yield job
        except Exception as exc:  # noqa: BLE001
            logger.debug("hn hiring comment parse failed: {}", exc)
