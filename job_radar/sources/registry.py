"""Registry of all data sources.

CLI `run` calls this to iterate every adapter. Adding a source = adding
one line here + one module.

`disabled_sources` in profile.yaml can turn individual sources off by name.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from job_radar.models import RawJob
from job_radar.sources import (
    ashby,
    careers_jsonld,
    cryptojobslist,
    decentrajobs,
    dejob,
    gmail_api,
    greenhouse,
    hn_hiring,
    jobicy,
    lever,
    linkedin_email,
    remoteok,
    remotive,
    web3_career,
    weworkremotely,
    workable,
)


@dataclass
class SourceEntry:
    name: str
    fn: Callable[[], Iterable[RawJob]]
    enabled: bool = True


REGISTRY: list[SourceEntry] = [
    # ATS — highest signal, lowest noise
    SourceEntry("lever", lever.fetch),
    SourceEntry("greenhouse", greenhouse.fetch),
    SourceEntry("ashby", ashby.fetch),
    SourceEntry("workable", workable.fetch),
    # Aggregators — remote-focused
    SourceEntry("remoteok", remoteok.fetch),
    SourceEntry("remotive", remotive.fetch),
    SourceEntry("weworkremotely", weworkremotely.fetch),
    SourceEntry("jobicy", jobicy.fetch),
    SourceEntry("hn.whoishiring", hn_hiring.fetch),
    # Crypto-specific boards
    SourceEntry("dejob.ai", dejob.fetch),
    SourceEntry("decentrajobs", decentrajobs.fetch),
    # Career pages (JSON-LD structured data)
    SourceEntry("careers", careers_jsonld.fetch),
    # LinkedIn via Gmail REST API (HTTPS, works on cloud servers)
    SourceEntry("gmail.linkedin", gmail_api.fetch),
    # LinkedIn via IMAP (blocked on aliyun — disabled by default)
    SourceEntry("linkedin.email", linkedin_email.fetch, enabled=False),
    # Cloudflare-protected, off by default (need playwright)
    SourceEntry("cryptojobslist", cryptojobslist.fetch, enabled=False),
    SourceEntry("web3.career", web3_career.fetch, enabled=False),
]


def enabled(disabled: list[str] | None = None) -> list[SourceEntry]:
    disabled_set = {d.lower() for d in (disabled or [])}
    return [s for s in REGISTRY if s.enabled and s.name.lower() not in disabled_set]
