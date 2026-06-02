"""Ashby ATS adapter.

Ashby exposes a public JSON board per company:

  https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true

Example org slugs: langchain, replicate, cohere.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from loguru import logger

from job_radar.http import client
from job_radar.models import RawJob
from job_radar.text import strip_html


@dataclass(frozen=True)
class AshbySlug:
    slug: str
    company_name: str


ASHBY_SEEDS: list[AshbySlug] = [
    # === AI labs / foundation ===
    AshbySlug("openai", "OpenAI"),
    AshbySlug("cohere", "Cohere"),
    AshbySlug("perplexity", "Perplexity"),
    AshbySlug("mistral", "Mistral AI"),
    AshbySlug("elevenlabs", "ElevenLabs"),
    AshbySlug("runway", "Runway"),
    # === AI dev-stack & agents ===
    AshbySlug("langchain", "LangChain"),
    AshbySlug("llamaindex", "LlamaIndex"),
    AshbySlug("mem0", "Mem0"),
    AshbySlug("modal", "Modal"),
    AshbySlug("baseten", "Baseten"),
    AshbySlug("anyscale", "Anyscale"),
    AshbySlug("lindy", "Lindy"),
    AshbySlug("cursor", "Cursor"),
    # === Web3 data / on-chain infra ===
    AshbySlug("alchemy", "Alchemy"),
    AshbySlug("dune", "Dune"),
    AshbySlug("elliptic", "Elliptic"),
    AshbySlug("helius", "Helius"),
    AshbySlug("quicknode", "QuickNode"),
    AshbySlug("syndica", "Syndica"),
    # === DeFi / Chains / wallet ===
    AshbySlug("uniswap", "Uniswap"),
    AshbySlug("0x", "0x"),
    AshbySlug("morpho", "Morpho"),
    AshbySlug("compound", "Compound"),
    AshbySlug("phantom", "Phantom"),
    AshbySlug("ledger", "Ledger"),
    AshbySlug("polygon-labs", "Polygon Labs"),
    AshbySlug("base", "Base"),
    AshbySlug("mystenlabs", "Mysten Labs / Sui"),
    # === Infra / databases / observability ===
    AshbySlug("supabase", "Supabase"),
    AshbySlug("neon", "Neon"),
    AshbySlug("snowflake", "Snowflake"),
    AshbySlug("confluent", "Confluent"),
    AshbySlug("sentry", "Sentry"),
    AshbySlug("posthog", "PostHog"),
    AshbySlug("linear", "Linear"),
    AshbySlug("notion", "Notion"),
    AshbySlug("mintlify", "Mintlify"),
    AshbySlug("zapier", "Zapier"),
    AshbySlug("inngest", "Inngest"),
    AshbySlug("restate", "Restate"),
    # === Exchange / custody ===
    AshbySlug("kraken", "Kraken"),
    AshbySlug("blockstream", "Blockstream"),
    # === Other ===
    AshbySlug("solanalabs", "Solana Labs"),
]


def fetch_slug(slug: AshbySlug) -> list[RawJob]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug.slug}?includeCompensation=true"
    with client() as c:
        resp = c.get(url)
    if resp.status_code in (404, 400):
        logger.warning("ashby slug not found: {}", slug.slug)
        return []
    resp.raise_for_status()
    data = resp.json()
    jobs = data.get("jobs") or []
    out: list[RawJob] = []
    for j in jobs:
        try:
            out.append(_parse(slug, j))
        except Exception as exc:  # noqa: BLE001
            logger.warning("ashby parse failed {}/{}: {}", slug.slug, j.get("id"), exc)
    return out


def fetch_all(slugs: list[AshbySlug] | None = None) -> Iterable[RawJob]:
    for s in slugs or ASHBY_SEEDS:
        try:
            yield from fetch_slug(s)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ashby source {} failed: {}", s.slug, exc)


def _parse(slug: AshbySlug, j: dict) -> RawJob:
    posted_raw = j.get("publishedAt") or j.get("updatedAt")
    posted_at = None
    if posted_raw:
        try:
            posted_at = datetime.fromisoformat(posted_raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    location = j.get("locationName") or ""
    if not location:
        sec = j.get("secondaryLocations") or []
        if sec:
            location = ", ".join(s.get("locationName", "") for s in sec if s.get("locationName"))
    return RawJob(
        source=f"ashby:{slug.slug}",
        external_id=str(j.get("id")),
        company=slug.company_name,
        title=(j.get("title") or "").strip(),
        location=location,
        department=j.get("teamName") or j.get("department"),
        description=strip_html(j.get("descriptionHtml")) or (j.get("descriptionPlain") or ""),
        apply_url=j.get("jobUrl") or j.get("applyUrl", ""),
        posted_at=posted_at,
        raw=j,
    )


def fetch() -> Iterable[RawJob]:
    yield from fetch_all()
