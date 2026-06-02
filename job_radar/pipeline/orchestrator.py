"""One-run pipeline orchestration.

Public entry:
  run_collect_and_score(profile, sources) -> CollectSummary

Stages:
  1. collect raw jobs from each source (sequential, failure-isolated)
  2. normalize + upsert + hard_filter (sequential; cheap CPU)
  3. score passed matches (parallel via ThreadPoolExecutor when LLM is on)
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger
from sqlalchemy import select

from job_radar.config import Profile
from job_radar.db import JobRow, MatchRow, SourceRun, session_scope, upsert_job
from job_radar.models import RawJob
from job_radar.pipeline import hard_filter, heuristic_scorer, llm_scorer, normalize
from job_radar.sources.registry import SourceEntry, enabled
from job_radar.trace import set_summary, span


@dataclass
class SourceStats:
    name: str
    fetched: int = 0
    new_jobs: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class CollectSummary:
    total_fetched: int = 0
    total_new: int = 0
    hard_filter_in: int = 0
    hard_filter_out: int = 0
    scored: int = 0
    scored_llm: int = 0
    scored_heuristic: int = 0
    tier_counts: dict[str, int] = field(default_factory=dict)
    per_source: list[SourceStats] = field(default_factory=list)
    llm_cost_cny: float = 0.0


def run_collect_and_score(
    profile: Profile,
    sources: list[SourceEntry] | None = None,
) -> CollectSummary:
    sources = sources or enabled(profile.disabled_sources)
    summary = CollectSummary()

    use_llm = os.environ.get("JOB_RADAR_LLM", "on").lower() not in {"off", "0", "false"}
    llm_budget = llm_scorer.BudgetGuard() if use_llm else None
    if use_llm:
        logger.info(
            "LLM scoring enabled (today spent ¥{:.3f} of ¥{:.2f})",
            llm_budget.today_spend(),
            llm_budget.limit_cny,
        )

    all_raw: list[RawJob] = []

    # Stage 0: collect per-source (failure-isolated)
    for entry in sources:
        stats = SourceStats(name=entry.name)
        with span(f"source:{entry.name}"):
            try:
                items = list(entry.fn())
                stats.fetched = len(items)
                all_raw.extend(items)
                _record_source(entry.name, success=True)
            except Exception as exc:
                stats.errors.append(f"{type(exc).__name__}: {exc}")
                logger.warning("source {} failed: {}", entry.name, exc)
                _record_source(entry.name, success=False, error=str(exc))
        summary.per_source.append(stats)
    summary.total_fetched = sum(s.fetched for s in summary.per_source)

    # Stage 1: normalize + upsert + hard_filter (single session)
    with session_scope() as sess, span("normalize_and_filter", count=len(all_raw)):
        passed: list[tuple[MatchRow, JobRow, list[str]]] = []  # to score next
        new_count = 0
        # Rescore threshold — in hours. If a match was scored less recently than this
        # AND the job hasn't materially changed, we skip re-LLM-scoring.
        rescore_hours = float(os.environ.get("JOB_RADAR_RESCORE_HOURS", "72"))
        rescore_cutoff = datetime.utcnow().timestamp() - rescore_hours * 3600
        for raw in all_raw:
            try:
                # Use a savepoint so one job's IntegrityError doesn't poison the session
                with sess.begin_nested():
                    job = normalize.normalize(raw)
                    row = normalize.to_row(job, raw.raw)
                    persisted, is_new = _upsert(sess, row)
                    if is_new:
                        new_count += 1

                    fr = hard_filter.hard_filter(job, profile)
                    # Reuse an existing match row if present and still fresh
                    existing_match = sess.execute(
                        select(MatchRow).where(MatchRow.job_id == persisted.id)
                    ).scalar_one_or_none()

                    if not fr.passed:
                        if existing_match:
                            existing_match.stage1_passed = False
                            existing_match.stage1_reason = fr.reason
                            existing_match.tier = "drop"
                            existing_match.stage = "hard_filter"
                            existing_match.scored_at = datetime.utcnow()
                        else:
                            sess.add(
                                MatchRow(
                                    job_id=persisted.id,
                                    stage1_passed=False,
                                    stage1_reason=fr.reason,
                                    matched_tracks=fr.matched_tracks,
                                    tier="drop",
                                    stage="hard_filter",
                                    scored_at=datetime.utcnow(),
                                )
                            )
                        continue

                    summary.hard_filter_in += 1

                    if (
                        existing_match
                        and existing_match.stage3_overall is not None
                        and existing_match.stage == "llm"
                        and existing_match.scored_at
                        and existing_match.scored_at.timestamp() > rescore_cutoff
                        and not is_new
                    ):
                        summary.tier_counts[existing_match.tier or "?"] = (
                            summary.tier_counts.get(existing_match.tier or "?", 0) + 1
                        )
                        summary.scored += 1
                        summary.scored_llm += 1
                        continue

                    if existing_match:
                        existing_match.stage1_passed = True
                        existing_match.stage1_reason = ""
                        existing_match.matched_tracks = fr.matched_tracks
                        match = existing_match
                    else:
                        match = MatchRow(
                            job_id=persisted.id,
                            stage1_passed=True,
                            matched_tracks=fr.matched_tracks,
                            scored_at=datetime.utcnow(),
                        )
                        sess.add(match)
                    sess.flush()
                    passed.append((match, persisted, fr.matched_tracks))
            except Exception as exc:
                logger.warning(
                    "pipeline pre-score failed on {}/{}: {}",
                    raw.source,
                    raw.external_id,
                    exc,
                )
        summary.total_new = new_count

    # Stage 2: score (parallel when LLM on; sequential otherwise)
    # We reopen a session per worker since SQLAlchemy sessions aren't thread-safe.
    if use_llm and passed:
        _score_parallel(passed, profile, summary, llm_budget)
    else:
        _score_sequential(passed, profile, summary, llm_budget)

    summary.hard_filter_out = summary.total_fetched - summary.hard_filter_in
    set_summary(**_summary_dict(summary))
    return summary


# -------------------- scoring --------------------


def _score_sequential(
    passed: list[tuple[MatchRow, JobRow, list[str]]],
    profile: Profile,
    summary: CollectSummary,
    llm_budget,
) -> None:
    with session_scope() as sess:
        for match_row, job_row, tracks in passed:
            m = sess.get(MatchRow, match_row.id)
            if m is None:
                continue
            # We need a Job model object (not JobRow); rebuild minimal one.
            job = _job_from_row(job_row)
            sc, stage_used, cost = _score_one(job, profile, tracks, llm_budget)
            _apply_score(m, sc, stage_used)
            summary.scored += 1
            summary.llm_cost_cny += cost
            if stage_used == "llm":
                summary.scored_llm += 1
            else:
                summary.scored_heuristic += 1
            summary.tier_counts[sc.tier] = summary.tier_counts.get(sc.tier, 0) + 1


def _score_parallel(
    passed: list[tuple[MatchRow, JobRow, list[str]]],
    profile: Profile,
    summary: CollectSummary,
    llm_budget,
) -> None:
    max_workers = int(os.environ.get("JOB_RADAR_LLM_CONCURRENCY", "6"))
    # Precompute inputs so workers can stay thread-local
    jobs_to_score = [(mr.id, _job_from_row(jr), tracks) for mr, jr, tracks in passed]

    results: dict[int, tuple] = {}  # match_id -> (Score, stage, cost)
    # Persist in batches so an early exit (budget hit / signal) still saves progress
    batch_size = 50
    with span("llm_score_parallel", count=len(jobs_to_score), workers=max_workers):
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_score_one, job, profile, tracks, llm_budget): match_id
                for match_id, job, tracks in jobs_to_score
            }
            done = 0
            batch: dict[int, tuple] = {}
            for fut in as_completed(futures):
                match_id = futures[fut]
                try:
                    sc, stage_used, cost = fut.result()
                    results[match_id] = (sc, stage_used, cost)
                    batch[match_id] = (sc, stage_used, cost)
                except Exception as exc:
                    logger.warning("worker failed for match {}: {}", match_id, exc)
                done += 1
                if done % 20 == 0:
                    logger.info(
                        "scored {}/{} (spent ¥{:.3f} / ¥{:.2f})",
                        done,
                        len(jobs_to_score),
                        llm_budget.today_spend() if llm_budget else 0,
                        llm_budget.limit_cny if llm_budget else 0,
                    )
                if len(batch) >= batch_size:
                    _persist_batch(batch, summary)
                    batch.clear()
            # flush remainder
            if batch:
                _persist_batch(batch, summary)


def _persist_batch(batch: dict, summary: CollectSummary) -> None:
    """Flush a batch of match_id -> (score, stage, cost) to the DB."""
    with session_scope() as sess:
        for match_id, (sc, stage_used, cost) in batch.items():
            m = sess.get(MatchRow, match_id)
            if m is None:
                continue
            _apply_score(m, sc, stage_used)
            summary.scored += 1
            summary.llm_cost_cny += cost
            if stage_used == "llm":
                summary.scored_llm += 1
            else:
                summary.scored_heuristic += 1
            summary.tier_counts[sc.tier] = summary.tier_counts.get(sc.tier, 0) + 1


def _score_one(job, profile, matched_tracks, llm_budget):
    """Returns (score, stage_used, cost_cny)."""
    if llm_budget is not None and llm_budget.can_spend(0.01):
        try:
            result = llm_scorer.score(job, profile, matched_tracks, budget=llm_budget)
            if result.score is not None:
                return result.score, "llm", result.cost_cny
        except Exception as exc:
            logger.warning("llm score exc for {}: {}", job.title, exc)
    sc = heuristic_scorer.score(job, profile, matched_tracks)
    return sc, "heuristic", 0.0


def _apply_score(match: MatchRow, sc, stage_used: str) -> None:
    match.stage3_overall = sc.overall
    match.stage3_dims = sc.dims
    match.stage3_reasons = sc.reasons
    match.stage3_reasons_zh = sc.reasons_zh
    match.stage3_risks = sc.risks
    match.stage3_risks_zh = sc.risks_zh
    match.matched_keywords = sc.matched_keywords
    match.explanation = sc.explanation
    match.explanation_zh = sc.explanation_zh
    match.suggested_resume_version = sc.suggested_resume_version
    match.tier = sc.tier
    match.stage = stage_used


def _job_from_row(row: JobRow):
    """Lightweight shim so scorers (which expect a Job-like object) can read attrs."""
    from dataclasses import dataclass

    @dataclass
    class _JobView:
        company: str
        title: str
        location: str
        is_remote: bool
        source: str
        description: str
        posted_at: datetime | None

    return _JobView(
        company=row.company,
        title=row.title,
        location=row.location or "",
        is_remote=bool(row.is_remote),
        source=row.source,
        description=row.description or "",
        posted_at=row.posted_at,
    )


def _upsert(sess, row: JobRow) -> tuple[JobRow, bool]:
    stmt = select(JobRow).where(JobRow.fingerprint == row.fingerprint)
    existing = sess.execute(stmt).scalar_one_or_none()
    is_new = existing is None
    persisted = upsert_job(sess, row)
    sess.flush()
    return persisted, is_new


def _record_source(name: str, success: bool, error: str | None = None) -> None:
    try:
        with session_scope() as sess:
            stmt = select(SourceRun).where(SourceRun.name == name)
            row = sess.execute(stmt).scalar_one_or_none()
            if row is None:
                row = SourceRun(name=name)
                sess.add(row)
            row.last_run_at = datetime.utcnow()
            if success:
                row.last_success_at = datetime.utcnow()
                row.consecutive_failures = 0
                row.last_error = None
            else:
                row.consecutive_failures = (row.consecutive_failures or 0) + 1
                row.last_error = error
    except Exception as exc:
        logger.warning("failed to record source run {}: {}", name, exc)


def _summary_dict(s: CollectSummary) -> dict:
    return {
        "total_fetched": s.total_fetched,
        "total_new": s.total_new,
        "hard_filter_in": s.hard_filter_in,
        "hard_filter_out": s.hard_filter_out,
        "scored": s.scored,
        "scored_llm": s.scored_llm,
        "scored_heuristic": s.scored_heuristic,
        "llm_cost_cny": round(s.llm_cost_cny, 4),
        "tier_counts": s.tier_counts,
        "per_source": [
            {"name": x.name, "fetched": x.fetched, "errors": x.errors}
            for x in s.per_source
        ],
    }


__all__ = ["run_collect_and_score", "CollectSummary", "SourceStats"]
