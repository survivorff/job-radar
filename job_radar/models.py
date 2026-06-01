"""Pydantic domain models.

Three concepts you see a lot:
- RawJob   : whatever a source returns before we normalize it.
- Job      : the normalized, deduplicated row we store in `jobs`.
- Score    : the pipeline's verdict on a Job for the current profile.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Tier = Literal["high", "med", "low", "drop"]


class RawJob(BaseModel):
    """Unnormalized job coming out of a Source adapter."""

    model_config = ConfigDict(extra="allow")

    source: str  # e.g. "lever:okx" / "greenhouse:coinbase"
    external_id: str  # source-specific id (ATS job id, url, etc)
    company: str
    title: str
    location: str = ""
    department: str | None = None
    description: str = ""  # plaintext (HTML stripped)
    apply_url: str
    posted_at: datetime | None = None
    salary_text: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class Job(BaseModel):
    """Normalized Job persisted in SQLite."""

    fingerprint: str
    source: str
    external_id: str
    company: str
    title: str
    location: str
    is_remote: bool
    department: str | None
    description: str
    apply_url: str
    posted_at: datetime | None
    salary_text: str | None
    first_seen_at: datetime
    last_seen_at: datetime

    @staticmethod
    def compute_fingerprint(company: str, title: str, location: str) -> str:
        normalized = f"{company.strip().lower()}|{title.strip().lower()}|{location.strip().lower()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


class FilterResult(BaseModel):
    """Stage 1 output. `matched_tracks` drives downstream track-specific logic."""

    passed: bool
    reason: str = ""
    matched_tracks: list[str] = Field(default_factory=list)


class Score(BaseModel):
    """Unified score output (Stage 2 cosine or Stage 3 LLM)."""

    overall: int = Field(ge=0, le=100)
    dims: dict[str, int] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list, max_length=5)
    reasons_zh: list[str] = Field(default_factory=list, max_length=5)
    risks: list[str] = Field(default_factory=list, max_length=5)
    risks_zh: list[str] = Field(default_factory=list, max_length=5)
    matched_keywords: list[str] = Field(default_factory=list, max_length=20)
    explanation: str = ""  # 一句话 EN summary
    explanation_zh: str = ""  # 一句话中文 summary
    suggested_resume_version: Literal["V1", "V2", "V3"] | None = None
    cover_letter_angle: str | None = None
    stage: Literal["heuristic", "embed", "llm"] = "heuristic"

    @property
    def tier(self) -> Tier:
        if self.overall >= 90:
            return "high"
        if self.overall >= 75:
            return "med"
        if self.overall >= 60:
            return "low"
        return "drop"


class Match(BaseModel):
    """A (Job, Score) pair, what we actually push."""

    job: Job
    score: Score
    matched_tracks: list[str]
