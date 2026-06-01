"""Shared HTTP client with sane defaults."""

from __future__ import annotations

import httpx

USER_AGENT = (
    "job-radar/0.1 (+personal use; https://github.com/survivorff/job-radar)"
)


def client(timeout: float = 20.0) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, */*"},
        timeout=timeout,
        follow_redirects=True,
    )
