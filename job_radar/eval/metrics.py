"""Compute precision / recall / noise metrics from feedback labels."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import and_, select

from job_radar.db import FeedbackRow, JobRow, MatchRow, session_scope

POSITIVE = {"want", "applied"}
POSITIVE_OR_NEUTRAL = POSITIVE | {"maybe"}
NOISE = {"noise"}


@dataclass
class TierStats:
    tier: str
    total: int = 0
    labeled: int = 0
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def p_strict(self) -> float | None:
        if not self.labeled:
            return None
        pos = sum(self.counts.get(k, 0) for k in POSITIVE)
        return pos / self.labeled

    @property
    def p_lax(self) -> float | None:
        if not self.labeled:
            return None
        pos = sum(self.counts.get(k, 0) for k in POSITIVE_OR_NEUTRAL)
        return pos / self.labeled

    @property
    def noise_rate(self) -> float | None:
        if not self.labeled:
            return None
        return sum(self.counts.get(k, 0) for k in NOISE) / self.labeled


@dataclass
class Report:
    window_hours: int
    tiers: dict[str, TierStats]
    total_labeled: int
    overall_noise: float | None

    @property
    def satisfied(self) -> bool:
        """Our definition of done for this iteration."""
        high = self.tiers.get("high")
        med = self.tiers.get("med")
        if not high or not med or not high.labeled or not med.labeled:
            return False
        if (high.p_strict or 0) < 0.80:
            return False
        if (med.p_lax or 0) < 0.60:
            return False
        if (self.overall_noise or 0) > 0.10:
            return False
        return True


def compute(days: int = 7) -> Report:
    since = datetime.utcnow() - timedelta(days=days)
    stats = {t: TierStats(tier=t) for t in ("high", "med", "low")}

    with session_scope() as sess:
        # all scored matches in window
        rows = sess.execute(
            select(MatchRow).where(
                and_(MatchRow.tier != "drop", MatchRow.scored_at >= since)
            )
        ).scalars().all()
        for m in rows:
            ts = stats.get(m.tier or "?")
            if ts is not None:
                ts.total += 1

        # feedback rows in window
        fb = sess.execute(
            select(FeedbackRow, MatchRow)
            .join(MatchRow, FeedbackRow.match_id == MatchRow.id)
            .where(FeedbackRow.at >= since)
        ).all()
        for f, m in fb:
            ts = stats.get(m.tier or "?")
            if ts is None:
                continue
            ts.labeled += 1
            ts.counts[f.action] = ts.counts.get(f.action, 0) + 1

    total_labeled = sum(t.labeled for t in stats.values())
    total_noise = sum(t.counts.get("noise", 0) for t in stats.values())
    overall_noise = (total_noise / total_labeled) if total_labeled else None
    return Report(
        window_hours=days * 24,
        tiers=stats,
        total_labeled=total_labeled,
        overall_noise=overall_noise,
    )


def render_report(report: Report) -> str:
    from rich.table import Table
    from rich.console import Console
    from io import StringIO

    buf = StringIO()
    con = Console(file=buf, force_terminal=False, width=100)
    table = Table(title=f"Quality report — last {report.window_hours // 24} days")
    table.add_column("Tier")
    table.add_column("Total", justify="right")
    table.add_column("Labeled", justify="right")
    table.add_column("P (strict)", justify="right")
    table.add_column("P (lax)", justify="right")
    table.add_column("Noise", justify="right")
    table.add_column("Breakdown")
    for tier in ("high", "med", "low"):
        t = report.tiers[tier]
        breakdown = ", ".join(f"{k}={v}" for k, v in sorted(t.counts.items())) or "—"
        table.add_row(
            tier,
            str(t.total),
            str(t.labeled),
            f"{t.p_strict:.0%}" if t.p_strict is not None else "—",
            f"{t.p_lax:.0%}" if t.p_lax is not None else "—",
            f"{t.noise_rate:.0%}" if t.noise_rate is not None else "—",
            breakdown,
        )
    con.print(table)
    if report.overall_noise is not None:
        con.print(
            f"Overall noise: [red]{report.overall_noise:.0%}[/]  "
            f"(target ≤ 10%)  "
            f"Satisfied: {'[green]YES[/]' if report.satisfied else '[yellow]NO[/]'}"
        )
    return buf.getvalue()
