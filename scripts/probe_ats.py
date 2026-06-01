"""Probe which ATS a company uses. Useful when adding seed entries.

Usage:
    uv run python skills/job-radar/scripts/probe_ats.py okx anthropic coinbase
"""

from __future__ import annotations

import argparse
import time
from typing import Literal

import httpx

USER_AGENT = "job-radar-probe/0.1"

Provider = Literal["lever", "greenhouse", "ashby"]


def _url(provider: Provider, slug: str) -> str:
    if provider == "lever":
        return f"https://api.lever.co/v0/postings/{slug}?mode=json"
    if provider == "greenhouse":
        return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    return f"https://api.ashbyhq.com/posting-api/job-board/{slug}"


def probe(slug: str) -> dict[str, int]:
    result: dict[str, int] = {}
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(timeout=10.0, headers=headers, follow_redirects=True) as client:
        for provider in ("lever", "greenhouse", "ashby"):
            try:
                resp = client.get(_url(provider, slug))
                result[provider] = resp.status_code
            except Exception as exc:  # noqa: BLE001
                result[provider] = -1
                print(f"  {provider}: error {exc}")
            time.sleep(0.3)
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slugs", nargs="+", help="Candidate slugs to probe")
    args = ap.parse_args()

    print(f"{'slug':<25} {'lever':<8} {'greenhouse':<12} {'ashby':<6}")
    print("-" * 55)
    for slug in args.slugs:
        r = probe(slug)
        print(
            f"{slug:<25} {r.get('lever', '?'):<8} {r.get('greenhouse', '?'):<12} "
            f"{r.get('ashby', '?'):<6}"
        )


if __name__ == "__main__":
    main()
