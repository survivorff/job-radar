"""Convert RawJob → Job (with dedup fingerprint + is_remote flag)."""

from __future__ import annotations

from datetime import datetime

from job_radar.db import JobRow
from job_radar.models import Job, RawJob
from job_radar.text import is_remote


def normalize(raw: RawJob) -> Job:
    fingerprint = Job.compute_fingerprint(raw.company, raw.title, raw.location)
    remote_flag = is_remote(raw.location, raw.title)
    now = datetime.utcnow()
    return Job(
        fingerprint=fingerprint,
        source=raw.source,
        external_id=raw.external_id,
        company=raw.company,
        title=raw.title,
        location=raw.location,
        is_remote=remote_flag,
        department=raw.department,
        description=raw.description,
        apply_url=raw.apply_url,
        posted_at=raw.posted_at,
        salary_text=raw.salary_text,
        first_seen_at=now,
        last_seen_at=now,
    )


def to_row(job: Job, raw: dict | None = None) -> JobRow:
    return JobRow(
        fingerprint=job.fingerprint,
        source=job.source,
        external_id=job.external_id,
        company=job.company,
        title=job.title,
        location=job.location,
        is_remote=job.is_remote,
        department=job.department,
        description=job.description,
        apply_url=job.apply_url,
        posted_at=job.posted_at,
        salary_text=job.salary_text,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
        raw=raw or {},
    )
