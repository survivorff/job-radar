"""Plaintext bilingual preview of the current top matches.

Run from repo root:
    uv run python skills/job-radar/scripts/show_top.py [--limit 20] [--tier high]
"""

from __future__ import annotations

import argparse

from job_radar.channels.digest import load_digest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--tier", choices=["high", "med", "low", "all"], default="all")
    ap.add_argument("--kind", choices=["daily", "weekly"], default="daily")
    args = ap.parse_args()

    d = load_digest(args.kind)

    def _bucket(name: str, items):
        if not items:
            return
        print(f"\n=== {name} · {len(items)} ===")
        for item in items[: args.limit]:
            remote = " · Remote" if item.is_remote else ""
            print(f"\n[{item.score}] {item.company} — {item.title}")
            print(f"    {item.location or '—'}{remote}")
            if item.explanation:
                print(f"    EN: {item.explanation}")
            if item.explanation_zh:
                print(f"    ZH: {item.explanation_zh}")
            dims = item.dims or {}
            if dims:
                print(
                    "    dims: tech={t} scenario={s} seniority={sr} company={c}".format(
                        t=dims.get("tech_stack", 0),
                        s=dims.get("scenario", 0),
                        sr=dims.get("seniority", 0),
                        c=dims.get("company_fit", 0),
                    )
                )
            if item.matched_keywords:
                print(f"    kw: {', '.join(item.matched_keywords)}")
            if item.reasons or item.reasons_zh:
                for r in item.reasons:
                    print(f"    ✓ {r}")
                for r in item.reasons_zh:
                    print(f"    ✓ {r}")
            if item.risks or item.risks_zh:
                for r in item.risks:
                    print(f"    ⚠ {r}")
                for r in item.risks_zh:
                    print(f"    ⚠ {r}")
            if item.suggested_resume_version:
                print(f"    → resume: {item.suggested_resume_version}")
            print(f"    {item.apply_url}")

    print(
        f"Job Radar — {args.kind} · {d.generated_at:%Y-%m-%d %H:%M UTC} · "
        f"{d.counts['high']} high / {d.counts['med']} med / {d.counts['low']} low "
        f"(total new {d.total_new})"
    )

    if args.tier in ("high", "all"):
        _bucket("🔴 High · 首投", d.high)
    if args.tier in ("med", "all"):
        _bucket("🟡 Medium · 精投", d.med)
    if args.tier in ("low", "all"):
        _bucket("🟢 Candidates · 候选", d.low)


if __name__ == "__main__":
    main()
