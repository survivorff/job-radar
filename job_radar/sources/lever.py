"""Lever ATS adapter.

Lever exposes a public JSON API for every company's board:

  https://api.lever.co/v0/postings/{slug}?mode=json

One shared adapter can ingest OKX / Binance / Chainlink / Kraken / LangChain
/ ... just by varying the slug.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable

from loguru import logger

from job_radar.http import client
from job_radar.models import RawJob
from job_radar.text import strip_html


@dataclass(frozen=True)
class LeverSlug:
    """One company on Lever. `company_name` overrides whatever Lever puts in the payload."""

    slug: str
    company_name: str


# Seed list. Verified live as of 2026-05. Each adapter degrades gracefully
# if a slug starts returning 404 (logged, skipped, no crash).
LEVER_SEEDS: list[LeverSlug] = [
    # === CEX / exchange (dedup by fingerprint against greenhouse) ===
    LeverSlug("binance", "Binance"),
    # === Crypto / DeFi ===
    LeverSlug("1inch", "1inch"),
    LeverSlug("ethena", "Ethena Labs"),
    LeverSlug("celestia", "Celestia"),
    LeverSlug("immutable", "Immutable"),
    LeverSlug("ledger", "Ledger"),
    LeverSlug("zerion", "Zerion"),
    LeverSlug("coingecko", "CoinGecko"),
    # === AI ===
    LeverSlug("mistral", "Mistral AI"),
    LeverSlug("anyscale", "Anyscale"),
    # === Infra ===
    LeverSlug("neon", "Neon"),
]


def fetch_slug(slug: LeverSlug) -> list[RawJob]:
    """Fetch postings for one company."""
    url = f"https://api.lever.co/v0/postings/{slug.slug}?mode=json"
    with client() as c:
        resp = c.get(url)
    if resp.status_code == 404:
        logger.warning("lever slug 404, probably not on Lever: {}", slug.slug)
        return []
    resp.raise_for_status()
    data = resp.json()
    out: list[RawJob] = []
    for p in data:
        try:
            out.append(_parse(slug, p))
        except Exception as exc:  # noqa: BLE001
            logger.warning("lever parse failed for {}/{}: {}", slug.slug, p.get("id"), exc)
    return out


def fetch_all(slugs: list[LeverSlug] | None = None) -> Iterable[RawJob]:
    for s in slugs or LEVER_SEEDS:
        try:
            yield from fetch_slug(s)
        except Exception as exc:  # noqa: BLE001
            logger.warning("lever source {} failed: {}", s.slug, exc)


def _parse(slug: LeverSlug, p: dict) -> RawJob:
    cats = p.get("categories") or {}
    posted = p.get("createdAt")
    posted_at = (
        datetime.fromtimestamp(int(posted) / 1000, tz=UTC) if isinstance(posted, int) else None
    )
    description = p.get("descriptionPlain") or strip_html(p.get("description"))
    # Lever stitches multiple `lists` sections for responsibilities etc.
    for lst in p.get("lists") or []:
        description += "\n\n" + (lst.get("text") or "") + "\n" + strip_html(lst.get("content"))
    description += "\n\n" + strip_html(p.get("additionalPlain") or p.get("additional"))

    return RawJob(
        source=f"lever:{slug.slug}",
        external_id=str(p.get("id") or p.get("hostedUrl") or ""),
        company=slug.company_name,
        title=p.get("text", "").strip(),
        location=(cats.get("location") or cats.get("allLocations", [""])[0] or "").strip()
        if cats.get("location") is not None or cats.get("allLocations")
        else "",
        department=cats.get("team") or cats.get("department"),
        description=description.strip(),
        apply_url=p.get("hostedUrl", ""),
        posted_at=posted_at,
        raw=p,
    )


# Convenience name matching docs/ROADMAP wording.
def fetch() -> Iterable[RawJob]:
    yield from fetch_all()
