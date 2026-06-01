"""Digest query + rendering (bilingual, with cross-posting dedup)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import and_, desc, or_, select

from job_radar.db import JobRow, MatchRow, PushRow, session_scope
from job_radar.pipeline.dedupe import canonical_key

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


@dataclass
class DigestItem:
    match_id: int
    score: int
    tier: str
    dims: dict[str, int]
    company: str
    title: str
    location: str
    is_remote: bool
    apply_url: str
    matched_keywords: list[str]
    reasons: list[str]
    reasons_zh: list[str]
    risks: list[str]
    risks_zh: list[str]
    explanation: str
    explanation_zh: str
    matched_tracks: list[str]
    suggested_resume_version: str | None
    source: str
    posted_at: datetime | None
    # Dedup metadata — populated by `_dedupe_items`
    dup_count: int = 0  # 0 = no dupes merged
    extra_locations: list[str] = field(default_factory=list)
    extra_sources: list[str] = field(default_factory=list)


@dataclass
class Digest:
    kind: str
    window_hours: int
    generated_at: datetime
    high: list[DigestItem]
    med: list[DigestItem]
    low: list[DigestItem]
    total_scored: int
    total_new: int
    dedup_savings: int = 0  # how many dupes we collapsed

    @property
    def has_content(self) -> bool:
        return bool(self.high or self.med or self.low)

    @property
    def counts(self) -> dict[str, int]:
        return {"high": len(self.high), "med": len(self.med), "low": len(self.low)}


def _dedupe_items(items: list[DigestItem]) -> tuple[list[DigestItem], int]:
    """Collapse items with the same (company, canonical_title) into one.

    Keep the highest-scoring as primary. Collect the rest's locations and
    sources as extras so we don't lose info.
    """
    groups: dict[str, list[DigestItem]] = {}
    for it in items:
        groups.setdefault(canonical_key(it.company, it.title), []).append(it)

    result: list[DigestItem] = []
    saved = 0
    for key, group in groups.items():
        if len(group) == 1:
            result.append(group[0])
            continue
        group.sort(key=lambda x: x.score, reverse=True)
        primary = group[0]
        saved += len(group) - 1

        # collect extra locations + sources from the duplicates
        extra_locs: list[str] = []
        extra_srcs: list[str] = []
        for dup in group[1:]:
            if dup.location and dup.location != primary.location and dup.location not in extra_locs:
                extra_locs.append(dup.location)
            if dup.source and dup.source != primary.source and dup.source not in extra_srcs:
                extra_srcs.append(dup.source)

        primary.dup_count = len(group) - 1
        primary.extra_locations = extra_locs[:5]
        primary.extra_sources = extra_srcs[:3]
        result.append(primary)

    # Preserve original tier ordering (by score desc)
    result.sort(key=lambda x: x.score, reverse=True)
    return result, saved


def load_digest(kind: str) -> Digest:
    assert kind in ("daily", "weekly")
    hours = 24 if kind == "daily" else 24 * 7
    since = datetime.utcnow() - timedelta(hours=hours)

    with session_scope() as sess:
        already_sent_ids = set(
            sess.execute(
                select(PushRow.match_id).where(
                    and_(
                        PushRow.kind.in_(("daily", "weekly", "realtime")),
                        PushRow.sent_at >= since,
                    )
                )
            ).scalars()
        )

        stmt = (
            select(MatchRow, JobRow)
            .join(JobRow, MatchRow.job_id == JobRow.id)
            .where(
                and_(
                    MatchRow.tier != "drop",
                    MatchRow.stage3_overall.is_not(None),
                    or_(
                        MatchRow.scored_at >= since,
                        JobRow.first_seen_at >= since,
                    ),
                )
            )
            .order_by(desc(MatchRow.stage3_overall), desc(MatchRow.scored_at))
            .limit(300)
        )

        high: list[DigestItem] = []
        med: list[DigestItem] = []
        low: list[DigestItem] = []

        for match, job in sess.execute(stmt).all():
            if match.id in already_sent_ids:
                continue
            item = DigestItem(
                match_id=match.id,
                score=int(match.stage3_overall or 0),
                tier=match.tier or "drop",
                dims=dict(match.stage3_dims or {}),
                company=job.company,
                title=job.title,
                location=job.location or "",
                is_remote=bool(job.is_remote),
                apply_url=job.apply_url,
                matched_keywords=list(match.matched_keywords or []),
                reasons=list(match.stage3_reasons or []),
                reasons_zh=list(match.stage3_reasons_zh or []),
                risks=list(match.stage3_risks or []),
                risks_zh=list(match.stage3_risks_zh or []),
                explanation=match.explanation or "",
                explanation_zh=match.explanation_zh or "",
                matched_tracks=list(match.matched_tracks or []),
                suggested_resume_version=match.suggested_resume_version,
                source=job.source,
                posted_at=job.posted_at,
            )
            if match.tier == "high":
                high.append(item)
            elif match.tier == "med":
                med.append(item)
            elif match.tier == "low":
                low.append(item)

        total_saved = 0
        high, saved = _dedupe_items(high)
        total_saved += saved
        med, saved = _dedupe_items(med)
        total_saved += saved
        low, saved = _dedupe_items(low)
        total_saved += saved

        med = med[:15]
        low = low[:20]

        return Digest(
            kind=kind,
            window_hours=hours,
            generated_at=datetime.utcnow(),
            high=high,
            med=med,
            low=low,
            total_scored=sum(
                1 for _ in sess.execute(select(MatchRow.id).where(MatchRow.tier != "drop"))
            ),
            total_new=sum(
                1
                for _ in sess.execute(
                    select(JobRow.id).where(JobRow.first_seen_at >= since)
                )
            ),
            dedup_savings=total_saved,
        )


def render_digest_html(digest: Digest) -> str:
    return _env.get_template("digest.html.j2").render(d=digest)


def render_digest_text(digest: Digest) -> str:
    return _env.get_template("digest.txt.j2").render(d=digest)


def render_digest_subject(digest: Digest) -> str:
    icon = "🎯"
    c = digest.counts
    date_str = digest.generated_at.strftime("%Y-%m-%d")
    if not digest.has_content:
        return f"{icon} Job Radar {digest.kind} — {date_str} (nothing new)"
    kind_zh = "日报" if digest.kind == "daily" else "周报"
    return (
        f"{icon} Job Radar {kind_zh} — {date_str} "
        f"({c['high']} 高 / {c['med']} 中 / {c['low']} 候选)"
    )
