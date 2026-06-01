"""Run-level trace recorder.

Adapted from showcase-a's agent/trace.py. Each `run` writes one JSON
under runs/ so we can diagnose "why did this JD not get pushed" without
digging through the log file.
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from job_radar.config import get_settings


@dataclass
class _Span:
    name: str
    started_at: str
    ended_at: str | None = None
    duration_ms: float | None = None
    attrs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class _Run:
    run_id: str
    started_at: str
    started_monotonic: float
    kind: str  # "collect" / "digest" / "ad-hoc"
    spans: list[_Span] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


_ACTIVE: ContextVar[_Run | None] = ContextVar("active_run", default=None)


def start_run(kind: str) -> _Run:
    run = _Run(
        run_id=str(uuid.uuid4()),
        started_at=_now_iso(),
        started_monotonic=time.monotonic(),
        kind=kind,
    )
    _ACTIVE.set(run)
    return run


def finish_run(error: str | None = None) -> Path | None:
    run = _ACTIVE.get()
    if run is None:
        return None
    _ACTIVE.set(None)
    run.error = error
    ended_at = _now_iso()
    payload = {
        "run_id": run.run_id,
        "kind": run.kind,
        "started_at": run.started_at,
        "ended_at": ended_at,
        "duration_ms": round((time.monotonic() - run.started_monotonic) * 1000, 3),
        "spans": [_span_to_dict(s) for s in run.spans],
        "summary": run.summary,
        "error": run.error,
    }
    out_dir = get_settings().runs_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = run.started_at.replace(":", "-").replace("+00:00", "Z")
    rid = run.run_id[:8]
    out = out_dir / f"{ts}_{rid}.json"
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return out


@contextmanager
def span(name: str, **attrs: Any):
    run = _ACTIVE.get()
    started_iso = _now_iso()
    started_mono = time.monotonic()
    entry = _Span(name=name, started_at=started_iso, attrs=dict(attrs))
    try:
        yield entry
    except Exception as exc:
        entry.error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        entry.ended_at = _now_iso()
        entry.duration_ms = round((time.monotonic() - started_mono) * 1000, 3)
        if run is not None:
            run.spans.append(entry)


def set_summary(**kwargs: Any) -> None:
    run = _ACTIVE.get()
    if run is None:
        return
    run.summary.update(kwargs)


def _span_to_dict(s: _Span) -> dict[str, Any]:
    return {
        "name": s.name,
        "started_at": s.started_at,
        "ended_at": s.ended_at,
        "duration_ms": s.duration_ms,
        "attrs": s.attrs,
        "error": s.error,
    }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")
