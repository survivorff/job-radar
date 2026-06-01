"""Diagnostic query over the jobs/matches DB.

Usage:
    uv run python skills/job-radar/scripts/query.py --company OKX
    uv run python skills/job-radar/scripts/query.py --title-contains "AI Agent"
    uv run python skills/job-radar/scripts/query.py --passed-only
"""

from __future__ import annotations

import argparse

from sqlalchemy import and_, select

from job_radar.db import JobRow, MatchRow, session_scope


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company")
    ap.add_argument("--title-contains")
    ap.add_argument("--passed-only", action="store_true")
    ap.add_argument("--tier", choices=["high", "med", "low", "drop"])
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args()

    with session_scope() as sess:
        stmt = select(MatchRow, JobRow).join(JobRow, MatchRow.job_id == JobRow.id)
        conds = []
        if args.company:
            conds.append(JobRow.company.ilike(f"%{args.company}%"))
        if args.title_contains:
            conds.append(JobRow.title.ilike(f"%{args.title_contains}%"))
        if args.passed_only:
            conds.append(MatchRow.stage1_passed.is_(True))
        if args.tier:
            conds.append(MatchRow.tier == args.tier)
        if conds:
            stmt = stmt.where(and_(*conds))
        stmt = stmt.order_by(MatchRow.stage3_overall.desc().nulls_last()).limit(args.limit)

        rows = sess.execute(stmt).all()
        if not rows:
            print("No rows.")
            return

        print(f"{'#':<5} {'tier':<5} {'score':<6} {'company':<20} {'title':<60} {'reason'}")
        print("-" * 120)
        for match, job in rows:
            reason = match.stage1_reason if not match.stage1_passed else ""
            print(
                f"{match.id:<5} {(match.tier or '-'):<5} "
                f"{(str(match.stage3_overall) if match.stage3_overall is not None else '-'):<6} "
                f"{job.company[:19]:<20} {job.title[:59]:<60} {reason}"
            )


if __name__ == "__main__":
    main()
