"""CLI entrypoints.

Commands:
  run            collect all sources, filter + score, store in SQLite
  digest         build + email the daily/weekly digest from what's in SQLite
  test-email     send a minimal email to verify SMTP config
  stats          print a quick summary
"""

from __future__ import annotations

import sys
from typing import Optional

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from job_radar.config import get_settings, load_profile
from job_radar.db import FeedbackRow, JobRow, MatchRow, PushRow, init_db, session_scope
from job_radar.logging_ import setup_logging
from job_radar.trace import finish_run, start_run

app = typer.Typer(add_completion=False, rich_markup_mode="rich")
console = Console()


@app.callback()
def _bootstrap() -> None:
    """Runs before any command."""
    setup_logging()
    get_settings().ensure_dirs()
    init_db()


@app.command()
def run(
    profile_path: Optional[str] = typer.Option(None, "--profile", help="Path to profile YAML"),
) -> None:
    """Collect, normalize, filter, score. Does NOT send email."""
    from job_radar.pipeline.orchestrator import run_collect_and_score

    profile = load_profile(None if profile_path is None else _resolve_profile(profile_path))
    console.print(f"[cyan]Profile:[/] {profile.name}  tracks: {[t.id for t in profile.tracks]}")

    start_run("collect")
    err: str | None = None
    try:
        summary = run_collect_and_score(profile)
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
        logger.exception("collect run failed")
        raise
    finally:
        path = finish_run(error=err)
        if path:
            console.print(f"[dim]trace → {path}[/]")

    _print_summary(summary)


@app.command()
def digest(
    daily: bool = typer.Option(False, "--daily"),
    weekly: bool = typer.Option(False, "--weekly"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print HTML instead of sending"),
) -> None:
    """Build the digest and email it."""
    if daily == weekly:
        console.print("[red]Specify exactly one of --daily / --weekly[/]")
        raise typer.Exit(2)

    kind = "daily" if daily else "weekly"
    from job_radar.channels import router
    from job_radar.channels.digest import (
        load_digest,
        render_digest_html,
        render_digest_subject,
    )

    start_run(f"digest:{kind}")
    err: str | None = None
    try:
        d = load_digest(kind)
        console.print(
            f"[cyan]{kind} digest[/]: high={len(d.high)} med={len(d.med)} low={len(d.low)}"
        )
        if dry_run:
            console.rule("Subject")
            console.print(render_digest_subject(d))
            console.rule("HTML (first 2000 chars)")
            html = render_digest_html(d)
            console.print(html[:2000] + ("..." if len(html) > 2000 else ""))
            return
        if not d.has_content:
            console.print("[yellow]Nothing to send.[/]")
            return
        res = router.send_digest(d)
        if res.ok:
            console.print(f"[green]Sent via {router.pick_sender_name()}[/] ({res.message_id})")
        else:
            console.print(f"[red]Send failed:[/] {res.error}")
            raise typer.Exit(1)
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        finish_run(error=err)


@app.command(name="test-email")
def test_email() -> None:
    """Send a minimal email to verify the configured channel (Resend or SMTP)."""
    from datetime import datetime

    from job_radar.channels import router

    name = router.pick_sender_name()
    if name == "preview":
        console.print(
            "[red]No email channel configured.[/] Set RESEND_API_KEY (recommended) "
            "or SMTP_USER/SMTP_PASS in ~/.job-radar/.env"
        )
        raise typer.Exit(2)

    subject = f"✅ Job Radar test email ({datetime.utcnow().strftime('%H:%M:%S')} UTC)"
    html = (
        f"<h3>Hello from Job Radar</h3>"
        f"<p>If you see this, the <b>{name}</b> email channel is working.</p>"
        f"<p>Next: run <code>job-radar run</code> then <code>job-radar digest --daily</code>.</p>"
    )
    res = router.send_email(subject, html)
    s = get_settings()
    if res.ok:
        console.print(f"[green]Sent via {name} to {s.smtp_to}[/]")
    else:
        console.print(f"[red]Failed:[/] {res.error}")
        raise typer.Exit(1)


@app.command()
def stats(days: int = typer.Option(7, "--days", help="Window in days")) -> None:
    """Print a quick pipeline dashboard."""
    from datetime import datetime, timedelta

    from sqlalchemy import and_, select

    since = datetime.utcnow() - timedelta(days=days)

    with session_scope() as sess:
        crawled = sess.execute(
            select(JobRow).where(JobRow.first_seen_at >= since)
        ).scalars().all()
        passed = sess.execute(
            select(MatchRow).where(
                and_(MatchRow.scored_at >= since, MatchRow.stage1_passed.is_(True))
            )
        ).scalars().all()
        by_tier: dict[str, int] = {}
        for m in passed:
            by_tier[m.tier or "?"] = by_tier.get(m.tier or "?", 0) + 1
        pushes = sess.execute(
            select(PushRow).where(PushRow.sent_at >= since)
        ).scalars().all()
        feedback = sess.execute(
            select(FeedbackRow).where(FeedbackRow.at >= since)
        ).scalars().all()

    table = Table(title=f"Radar stats — last {days} days")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Crawled", str(len(crawled)))
    table.add_row("Passed hard filter", str(len(passed)))
    for tier in ("high", "med", "low", "drop"):
        if tier in by_tier:
            table.add_row(f"  tier={tier}", str(by_tier[tier]))
    table.add_row("Pushes sent", str(len(pushes)))
    table.add_row("Feedback received", str(len(feedback)))
    console.print(table)


# -------------------- evaluation -------------------- #


@app.command(name="label")
def label_cmd(
    tier: Optional[str] = typer.Option(None, help="Label only one tier (high/med/low)"),
    kind: str = typer.Option("daily", help="Window: daily or weekly"),
) -> None:
    """Walk through recent matches and record want/applied/maybe/reject/noise."""
    from job_radar.eval.labeler import label_recent

    stats = label_recent(tier=tier, kind=kind, console=console)
    if stats.total == 0:
        console.print("[yellow]No labels recorded.[/]")
    else:
        console.print(f"[green]Recorded {stats.total} labels:[/] {stats.counts}")


@app.command(name="eval")
def eval_cmd(days: int = typer.Option(7, help="Lookback window in days")) -> None:
    """Compute precision / noise rate from feedback labels."""
    from job_radar.eval.metrics import compute, render_report

    report = compute(days=days)
    if report.total_labeled == 0:
        console.print(
            "[yellow]No labels yet.[/] Run `job-radar label` first to record your verdicts."
        )
        raise typer.Exit(2)
    console.print(render_report(report))


# -------------------- personalization -------------------- #


@app.command(name="block-company")
def block_company_cmd(name: str = typer.Argument(...)) -> None:
    """Add a company to the block list (hard filter)."""
    from job_radar import profile_mutator as pm

    changed, path = pm.block_company(name)
    if changed:
        console.print(f"[green]Blocked[/] '{name}' → {path}")
        console.print("[dim]Run `job-radar run` to re-score.[/]")
    else:
        console.print(f"[yellow]'{name}' already blocked[/]")


@app.command(name="unblock-company")
def unblock_company_cmd(name: str = typer.Argument(...)) -> None:
    """Remove a company from the block list."""
    from job_radar import profile_mutator as pm

    changed, path = pm.unblock_company(name)
    if changed:
        console.print(f"[green]Unblocked[/] '{name}' → {path}")
    else:
        console.print(f"[yellow]'{name}' was not on the block list[/]")


@app.command(name="boost-company")
def boost_company_cmd(name: str = typer.Argument(...)) -> None:
    """Add a company to the boost list (+15 to company_fit)."""
    from job_radar import profile_mutator as pm

    changed, path = pm.boost_company(name)
    if changed:
        console.print(f"[green]Boosted[/] '{name}' → {path}")
    else:
        console.print(f"[yellow]'{name}' already boosted[/]")


@app.command(name="exclude")
def exclude_cmd(keyword: str = typer.Argument(...)) -> None:
    """Add a keyword to exclude_keywords (hard filter)."""
    from job_radar import profile_mutator as pm

    changed, path = pm.exclude_keyword(keyword)
    if changed:
        console.print(f"[green]Excluded[/] '{keyword}' → {path}")
    else:
        console.print(f"[yellow]'{keyword}' already excluded[/]")


@app.command(name="add-keyword")
def add_keyword_cmd(
    track: str = typer.Argument(..., help="Track id (e.g. crypto_ai, web3_backend, senior_backend)"),
    keyword: str = typer.Argument(..., help="Keyword to add to include_keywords"),
) -> None:
    """Add a keyword to a track's include_keywords list."""
    from job_radar import profile_mutator as pm

    changed, path = pm.add_track_keyword(track, keyword)
    if changed:
        console.print(f"[green]Added[/] '{keyword}' to track '{track}' → {path}")
        console.print("[dim]Run `job-radar run` to re-score with the new keyword.[/]")
    else:
        console.print(f"[yellow]'{keyword}' already in track '{track}'[/]")


@app.command(name="remove-keyword")
def remove_keyword_cmd(
    track: str = typer.Argument(..., help="Track id"),
    keyword: str = typer.Argument(..., help="Keyword to remove"),
) -> None:
    """Remove a keyword from a track's include_keywords list."""
    from job_radar import profile_mutator as pm

    changed, path = pm.remove_track_keyword(track, keyword)
    if changed:
        console.print(f"[green]Removed[/] '{keyword}' from track '{track}' → {path}")
    else:
        console.print(f"[yellow]'{keyword}' not found in track '{track}'[/]")


@app.command(name="show-profile")
def show_profile_cmd() -> None:
    """Print current profile tracks and keywords."""
    from job_radar.config import load_profile

    p = load_profile()
    console.print(f"[bold]Profile:[/] {p.name}  remote_only={p.remote_only}")
    console.print(f"[bold]Employment types:[/] {p.employment_types}")
    console.print()
    for t in p.tracks:
        console.print(f"[cyan]Track: {t.id}[/] (priority={t.priority}, resume={t.resume_version})")
        console.print(f"  {t.description}")
        console.print(f"  include_keywords ({len(t.include_keywords)}):")
        for kw in t.include_keywords:
            console.print(f"    · {kw}")
        if t.required_any:
            console.print(f"  required_any: {t.required_any}")
        console.print()
    if p.exclude_keywords:
        console.print(f"[red]Exclude keywords ({len(p.exclude_keywords)}):[/]")
        for kw in p.exclude_keywords:
            console.print(f"  ✗ {kw}")
    if p.blocked_companies:
        console.print(f"\n[red]Blocked companies:[/] {p.blocked_companies}")
    if p.boost_companies:
        console.print(f"\n[green]Boosted companies:[/] {p.boost_companies}")


@app.command(name="disable-source")
def disable_source_cmd(name: str = typer.Argument(...)) -> None:
    """Disable a source by name (from sources/registry.py)."""
    from job_radar import profile_mutator as pm

    changed, path = pm.disable_source(name)
    if changed:
        console.print(f"[green]Disabled source[/] '{name}' → {path}")
    else:
        console.print(f"[yellow]Source '{name}' already disabled[/]")


@app.command(name="enable-source")
def enable_source_cmd(name: str = typer.Argument(...)) -> None:
    """Re-enable a previously disabled source."""
    from job_radar import profile_mutator as pm

    changed, path = pm.enable_source(name)
    if changed:
        console.print(f"[green]Enabled source[/] '{name}' → {path}")
    else:
        console.print(f"[yellow]Source '{name}' was not disabled[/]")


@app.command(name="sources")
def sources_cmd() -> None:
    """List all registered sources and their status."""
    from job_radar.config import load_profile
    from job_radar.sources.registry import REGISTRY

    profile = load_profile()
    disabled = {d.lower() for d in (profile.disabled_sources or [])}
    table = Table(title="Registered sources")
    table.add_column("Name")
    table.add_column("Status")
    for entry in REGISTRY:
        if entry.name.lower() in disabled:
            status = "[red]disabled[/]"
        elif entry.enabled:
            status = "[green]enabled[/]"
        else:
            status = "[dim]off[/]"
        table.add_row(entry.name, status)
    console.print(table)


# -------------------- helpers -------------------- #


def _resolve_profile(path: str):
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        console.print(f"[red]Profile not found:[/] {path}")
        raise typer.Exit(2)
    return p


def _print_summary(summary) -> None:
    table = Table(title="Collect summary")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Total fetched", str(summary.total_fetched))
    table.add_row("New jobs (first-seen)", str(summary.total_new))
    table.add_row("Passed hard filter", str(summary.hard_filter_in))
    table.add_row("Dropped by hard filter", str(summary.hard_filter_out))
    table.add_row("Scored", str(summary.scored))
    if getattr(summary, "scored_llm", 0):
        table.add_row("  by LLM", str(summary.scored_llm))
    if getattr(summary, "scored_heuristic", 0):
        table.add_row("  by heuristic (fallback)", str(summary.scored_heuristic))
    if getattr(summary, "llm_cost_cny", 0):
        table.add_row("LLM cost this run", f"¥{summary.llm_cost_cny:.3f}")
    for tier, count in summary.tier_counts.items():
        table.add_row(f"  tier={tier}", str(count))
    console.print(table)

    src_table = Table(title="Per source")
    src_table.add_column("Source")
    src_table.add_column("Fetched", justify="right")
    src_table.add_column("Errors")
    for s in summary.per_source:
        src_table.add_row(s.name, str(s.fetched), "; ".join(s.errors) or "-")
    console.print(src_table)


if __name__ == "__main__":
    app()
