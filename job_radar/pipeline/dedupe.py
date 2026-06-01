"""Cross-posting deduplication.

The `fingerprint` column catches *exact* dupes (same company+title+location
from multiple ATS, e.g. Binance is on Lever and Greenhouse). But we also see:

- LangChain "Solutions Architect (Remote)" / "(Dallas)" / "(NYC)" … 6 cities
- OKX "Senior Staff Engineer, AI Platform" in "Singapore" and "Hong Kong"

These are logically one opening. We collapse them in the digest layer so
the user sees one card with merged locations instead of 6 near-identical cards.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# Pattern: strip trailing "(City)" / "(Remote)" / " - City" / " (US/EU)"
_LOCATION_SUFFIX = re.compile(
    r"\s*(?:[\-–—]\s*[^\-\n]+|\([^)]+\))\s*$",
)


def canonical_title(title: str) -> str:
    """Strip trailing location suffixes until stable."""
    prev = title
    for _ in range(3):  # at most 3 peels (nested parens are rare)
        stripped = _LOCATION_SUFFIX.sub("", prev).strip()
        if stripped == prev or not stripped:
            break
        prev = stripped
    return prev


def canonical_key(company: str, title: str) -> str:
    return f"{company.strip().lower()}|{canonical_title(title).strip().lower()}"


@dataclass
class MergedGroup:
    """A deduped group — we keep the primary (highest-scoring) and collect the rest."""

    primary_match_id: int
    primary_score: int
    dup_match_ids: list[int]
    locations: list[str]
    apply_urls: list[str]


def group_by_canonical(items: Iterable) -> dict[str, list]:
    """items: iterable of objects with .company, .title, .score, .match_id, .location, .apply_url."""
    groups: dict[str, list] = {}
    for item in items:
        key = canonical_key(item.company, item.title)
        groups.setdefault(key, []).append(item)
    return groups
