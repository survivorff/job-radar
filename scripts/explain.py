"""Explain a specific match in depth.

Usage:
    uv run python skills/job-radar/scripts/explain.py --match-id 42
    uv run python skills/job-radar/scripts/explain.py --company OKX --title-contains "AI Agent"
"""

from __future__ import annotations

import argparse
import json

from sqlalchemy import and_, or_, select

from job_radar.db import JobRow, MatchRow, session_scope


def _print(match: MatchRow, job: JobRow) -> None:
    print(f"\n── Match #{match.id} ──")
    print(f"{job.company} — {job.title}")
    print(f"Location: {job.location or '—'}  Remote: {job.is_remote}")
    print(f"Source: {job.source}  ({job.apply_url})")
    print(f"\nScore: {match.stage3_overall} · tier={match.tier} · stage={match.stage}")
    if match.stage3_dims:
        print("Dims:")
        for k, v in match.stage3_dims.items():
            print(f"  {k:<12} {v:>3}  {_bar(v)}")
    if match.matched_keywords:
        print(f"\nMatched keywords ({len(match.matched_keywords)}):")
        for kw in match.matched_keywords:
            print(f"  · {kw}")
    if match.matched_tracks:
        print(f"\nMatched tracks: {', '.join(match.matched_tracks)}")
    if match.explanation:
        print(f"\nEN: {match.explanation}")
    if match.explanation_zh:
        print(f"ZH: {match.explanation_zh}")
    if match.stage3_reasons or match.stage3_reasons_zh:
        print("\nWhy · 匹配原因:")
        for r in match.stage3_reasons or []:
            print(f"  ✓ {r}")
        for r in match.stage3_reasons_zh or []:
            print(f"  ✓ {r}")
    if match.stage3_risks or match.stage3_risks_zh:
        print("\nVerify · 需要验证:")
        for r in match.stage3_risks or []:
            print(f"  ⚠ {r}")
        for r in match.stage3_risks_zh or []:
            print(f"  ⚠ {r}")
    if match.suggested_resume_version:
        print(f"\nSuggested resume: {match.suggested_resume_version}")
    print("\nJD preview (first 800 chars):")
    print(job.description[:800] + ("..." if len(job.description) > 800 else ""))


def _bar(v: int, width: int = 20) -> str:
    filled = int(round(v / 100 * width))
    return "█" * filled + "░" * (width - filled)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--match-id", type=int)
    ap.add_argument("--company")
    ap.add_argument("--title-contains")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of human-readable")
    args = ap.parse_args()

    if not (args.match_id or args.company or args.title_contains):
        ap.error("provide --match-id, or --company / --title-contains")

    with session_scope() as sess:
        stmt = select(MatchRow, JobRow).join(JobRow, MatchRow.job_id == JobRow.id)
        if args.match_id:
            stmt = stmt.where(MatchRow.id == args.match_id)
        else:
            conds = []
            if args.company:
                conds.append(JobRow.company.ilike(f"%{args.company}%"))
            if args.title_contains:
                conds.append(JobRow.title.ilike(f"%{args.title_contains}%"))
            stmt = stmt.where(and_(*conds)).order_by(MatchRow.stage3_overall.desc()).limit(5)

        rows = sess.execute(stmt).all()
        if not rows:
            print("No match found.")
            return

        if args.json:
            payload = [
                {
                    "match_id": m.id,
                    "company": j.company,
                    "title": j.title,
                    "location": j.location,
                    "is_remote": j.is_remote,
                    "score": m.stage3_overall,
                    "tier": m.tier,
                    "dims": m.stage3_dims,
                    "matched_keywords": m.matched_keywords,
                    "reasons_en": m.stage3_reasons,
                    "reasons_zh": m.stage3_reasons_zh,
                    "risks_en": m.stage3_risks,
                    "risks_zh": m.stage3_risks_zh,
                    "explanation_en": m.explanation,
                    "explanation_zh": m.explanation_zh,
                    "apply_url": j.apply_url,
                    "source": j.source,
                }
                for m, j in rows
            ]
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        else:
            for match, job in rows:
                _print(match, job)


if __name__ == "__main__":
    main()
