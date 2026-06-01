"""Greenhouse ATS adapter.

Public endpoint per company:

  https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true

`content=true` makes Greenhouse include the full HTML description, which we
strip.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from loguru import logger

from job_radar.http import client
from job_radar.models import RawJob
from job_radar.text import strip_html


@dataclass(frozen=True)
class GreenhouseSlug:
    slug: str
    company_name: str


# Verified live as of 2026-05. Grouped by category for readability.
GH_SEEDS: list[GreenhouseSlug] = [
    # === CEX / Exchange ===
    GreenhouseSlug("okx", "OKX"),
    GreenhouseSlug("bybit", "Bybit"),
    GreenhouseSlug("bitgo", "BitGo"),
    GreenhouseSlug("gemini", "Gemini"),
    GreenhouseSlug("ripple", "Ripple"),
    # === DeFi / DEX / wallet / L1 / L2 ===
    GreenhouseSlug("aptoslabs", "Aptos Labs"),
    GreenhouseSlug("fireblocks", "Fireblocks"),
    GreenhouseSlug("layerzerolabs", "LayerZero Labs"),
    GreenhouseSlug("nansen", "Nansen"),
    # === Market makers / quant ===
    GreenhouseSlug("jumpcrypto", "Jump Crypto"),
    GreenhouseSlug("jumptrading", "Jump Trading"),
    GreenhouseSlug("gsrmarkets", "GSR"),
    GreenhouseSlug("flowtraders", "Flow Traders"),
    # === AI labs / AI infra ===
    GreenhouseSlug("anthropic", "Anthropic"),
    GreenhouseSlug("deepmind", "Google DeepMind"),
    GreenhouseSlug("databricks", "Databricks"),
    GreenhouseSlug("scaleai", "Scale AI"),
    GreenhouseSlug("fireworksai", "Fireworks AI"),
    GreenhouseSlug("togetherai", "Together AI"),
    GreenhouseSlug("xai", "xAI"),
    GreenhouseSlug("inflectionai", "Inflection AI"),
    GreenhouseSlug("stabilityai", "Stability AI"),
    # === Dev tools / infra (remote-friendly) ===
    GreenhouseSlug("vercel", "Vercel"),
    GreenhouseSlug("netlify", "Netlify"),
    GreenhouseSlug("cloudflare", "Cloudflare"),
    GreenhouseSlug("gitlab", "GitLab"),
    GreenhouseSlug("elastic", "Elastic"),
    GreenhouseSlug("mongodb", "MongoDB"),
    GreenhouseSlug("datadog", "Datadog"),
    GreenhouseSlug("planetscale", "PlanetScale"),
    GreenhouseSlug("amplitude", "Amplitude"),
    GreenhouseSlug("mixpanel", "Mixpanel"),
    GreenhouseSlug("figma", "Figma"),
    GreenhouseSlug("airtable", "Airtable"),
    # === Payments / fintech ===
    GreenhouseSlug("stripe", "Stripe"),
    GreenhouseSlug("block", "Block"),
    GreenhouseSlug("twilio", "Twilio"),
    # === Food / ops (remote options) ===
    GreenhouseSlug("instacart", "Instacart"),
]


def fetch_slug(slug: GreenhouseSlug) -> list[RawJob]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug.slug}/jobs?content=true"
    with client() as c:
        resp = c.get(url)
    if resp.status_code == 404:
        logger.warning("greenhouse slug 404: {}", slug.slug)
        return []
    resp.raise_for_status()
    data = resp.json()
    out: list[RawJob] = []
    for j in data.get("jobs", []):
        try:
            out.append(_parse(slug, j))
        except Exception as exc:  # noqa: BLE001
            logger.warning("greenhouse parse failed {}/{}: {}", slug.slug, j.get("id"), exc)
    return out


def fetch_all(slugs: list[GreenhouseSlug] | None = None) -> Iterable[RawJob]:
    for s in slugs or GH_SEEDS:
        try:
            yield from fetch_slug(s)
        except Exception as exc:  # noqa: BLE001
            logger.warning("greenhouse source {} failed: {}", s.slug, exc)


def _parse(slug: GreenhouseSlug, j: dict) -> RawJob:
    posted_raw = j.get("updated_at") or j.get("first_published")
    posted_at = None
    if posted_raw:
        try:
            posted_at = datetime.fromisoformat(posted_raw.replace("Z", "+00:00"))
        except ValueError:
            posted_at = None
    location = (j.get("location") or {}).get("name", "")
    description = strip_html(j.get("content"))

    # Greenhouse sometimes exposes offices list
    offices = j.get("offices") or []
    if offices and not location:
        location = ", ".join(o.get("name", "") for o in offices if o.get("name"))

    return RawJob(
        source=f"greenhouse:{slug.slug}",
        external_id=str(j.get("id")),
        company=slug.company_name,
        title=(j.get("title") or "").strip(),
        location=location,
        department=(j.get("departments") or [{}])[0].get("name") if j.get("departments") else None,
        description=description,
        apply_url=j.get("absolute_url", ""),
        posted_at=posted_at,
        raw=j,
    )


def fetch() -> Iterable[RawJob]:
    yield from fetch_all()
