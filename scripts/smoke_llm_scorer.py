"""Run the LLM scorer on 3 real jobs from the DB and print the verdict.

Picks the top 3 matches by heuristic score, rescores with LLM, shows side-by-side.
"""

from __future__ import annotations

from sqlalchemy import desc, select

from job_radar.config import load_profile
from job_radar.db import JobRow, MatchRow, session_scope
from job_radar.pipeline import llm_scorer


def main() -> None:
    profile = load_profile()
    budget = llm_scorer.BudgetGuard()
    print(f"Daily budget: ¥{budget.limit_cny}   spent today: ¥{budget.today_spend():.4f}\n")

    with session_scope() as sess:
        rows = sess.execute(
            select(MatchRow, JobRow)
            .join(JobRow, MatchRow.job_id == JobRow.id)
            .where(MatchRow.tier == "high")
            .order_by(desc(MatchRow.stage3_overall))
            .limit(3)
        ).all()

    for match, job in rows:
        from job_radar.pipeline.normalize import normalize  # noqa

        class _JobShim:
            pass

        j = _JobShim()
        j.company = job.company
        j.title = job.title
        j.location = job.location
        j.is_remote = bool(job.is_remote)
        j.source = job.source
        j.description = job.description
        j.posted_at = job.posted_at

        print("=" * 80)
        print(f"{job.company} — {job.title}")
        print(f"  heuristic: {match.stage3_overall}  (tier={match.tier})")
        print(f"  {job.location}  remote={j.is_remote}")

        result = llm_scorer.score(j, profile, match.matched_tracks or [], budget=budget)
        if result.score is None:
            print(f"  LLM ERROR: {result.error}")
            continue
        s = result.score
        print(f"  LLM:       {s.overall}  (tier={s.tier})  cost=¥{result.cost_cny:.4f}")
        print(f"  dims: {s.dims}")
        print(f"  EN: {s.explanation}")
        print(f"  ZH: {s.explanation_zh}")
        print("  reasons:")
        for r in s.reasons:
            print(f"    ✓ {r}")
        for r in s.reasons_zh:
            print(f"    ✓ {r}")
        print("  risks:")
        for r in s.risks:
            print(f"    ⚠ {r}")
        for r in s.risks_zh:
            print(f"    ⚠ {r}")
        print(f"  suggested resume: {s.suggested_resume_version}")
        print()

    print(f"\nAfter test: spent ¥{budget.today_spend():.4f} today")


if __name__ == "__main__":
    main()
