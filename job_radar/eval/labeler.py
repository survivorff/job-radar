"""Interactive labeler: walk through recent matches and record verdicts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from sqlalchemy import and_, desc, select

from job_radar.db import FeedbackRow, JobRow, MatchRow, session_scope

Action = Literal["want", "applied", "maybe", "reject", "noise", "skip", "quit"]

_ACTION_MAP = {
    "w": "want",
    "a": "applied",
    "m": "maybe",
    "r": "reject",
    "n": "noise",
    "s": "skip",
    "q": "quit",
}


@dataclass
class LabelStats:
    counts: dict[str, int]
    total: int


def label_recent(
    tier: str | None = None,
    kind: str = "daily",
    console: Console | None = None,
) -> LabelStats:
    """Walk through recent matches in given tier(s) and prompt the user."""
    console = console or Console()
    hours = 24 if kind == "daily" else 24 * 7
    since = datetime.utcnow() - timedelta(hours=hours)

    with session_scope() as sess:
        # Already-labeled matches in window (so we don't re-prompt)
        already = set(
            sess.execute(
                select(FeedbackRow.match_id).where(FeedbackRow.at >= since)
            ).scalars()
        )
        stmt = (
            select(MatchRow, JobRow)
            .join(JobRow, MatchRow.job_id == JobRow.id)
            .where(
                and_(
                    MatchRow.tier != "drop",
                    MatchRow.stage3_overall.is_not(None),
                    MatchRow.scored_at >= since,
                )
            )
            .order_by(desc(MatchRow.stage3_overall))
        )
        if tier:
            stmt = stmt.where(MatchRow.tier == tier)

        rows = [(m, j) for m, j in sess.execute(stmt).all() if m.id not in already]
        console.print(f"[cyan]To label: {len(rows)} matches[/] (tier={tier or 'all'}, window={hours}h)")

        counts: dict[str, int] = {}
        for idx, (match, job) in enumerate(rows, 1):
            header = (
                f"[bold]{idx}/{len(rows)}[/]  [{match.tier}] "
                f"[bold]{match.stage3_overall}[/]  "
                f"{job.company} — {job.title}"
            )
            meta = (
                f"[dim]{job.location or '—'}"
                f"{'  · Remote' if job.is_remote else ''}"
                f"  · {job.source}  · match#{match.id}[/]"
            )
            reasons = "\n".join(f"  ✓ {r}" for r in (match.stage3_reasons or []))
            risks = "\n".join(f"  ⚠ {r}" for r in (match.stage3_risks or []))
            body = []
            if match.explanation:
                body.append(match.explanation)
            if match.matched_keywords:
                body.append("kw: " + ", ".join(match.matched_keywords[:8]))
            body_str = "\n".join(body)
            console.print(
                Panel(
                    f"{meta}\n\n{body_str}\n\n{reasons}\n{risks}\n\n[dim]{job.apply_url}[/]",
                    title=header,
                    border_style="cyan",
                )
            )

            resp = Prompt.ask(
                "[w]ant  [a]pplied  [m]aybe  [r]eject  [n]oise  [s]kip  [q]uit",
                default="s",
            ).strip().lower()
            action = _ACTION_MAP.get(resp, "skip")

            if action == "quit":
                break
            if action == "skip":
                continue

            counts[action] = counts.get(action, 0) + 1
            sess.add(
                FeedbackRow(
                    match_id=match.id,
                    action=action,
                    at=datetime.utcnow(),
                )
            )
            sess.flush()

    return LabelStats(counts=counts, total=sum(counts.values()))
