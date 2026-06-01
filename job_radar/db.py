"""SQLAlchemy models + session. SQLite by default.

Five tables as designed in docs/04-architecture.md:
  sources / jobs / matches / pushes / feedback
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from job_radar.config import get_settings


class Base(DeclarativeBase):
    pass


class SourceRun(Base):
    __tablename__ = "sources"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    last_run_at = Column(DateTime)
    last_success_at = Column(DateTime)
    consecutive_failures = Column(Integer, default=0)
    last_error = Column(Text)


class JobRow(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    fingerprint = Column(String(32), unique=True, index=True, nullable=False)
    source = Column(String(100), nullable=False, index=True)
    external_id = Column(String(200), nullable=False)
    company = Column(String(200), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    location = Column(String(200), default="")
    is_remote = Column(Boolean, default=False)
    department = Column(String(200))
    description = Column(Text, default="")
    apply_url = Column(String(500), nullable=False)
    posted_at = Column(DateTime)
    salary_text = Column(String(200))
    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)
    raw = Column(JSON)

    matches = relationship("MatchRow", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_externalid"),)


class MatchRow(Base):
    __tablename__ = "matches"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    stage1_passed = Column(Boolean, default=False)
    stage1_reason = Column(String(200))
    matched_tracks = Column(JSON)  # list[str]
    stage2_cosine = Column(Float)
    stage3_overall = Column(Integer)
    stage3_dims = Column(JSON)
    stage3_reasons = Column(JSON)
    stage3_reasons_zh = Column(JSON)
    stage3_risks = Column(JSON)
    stage3_risks_zh = Column(JSON)
    matched_keywords = Column(JSON)
    explanation = Column(Text)
    explanation_zh = Column(Text)
    suggested_resume_version = Column(String(10))
    cover_letter_angle = Column(Text)
    tier = Column(String(10))  # high / med / low / drop
    stage = Column(String(20))  # heuristic / embed / llm
    scored_at = Column(DateTime, default=datetime.utcnow)
    cost_cny = Column(Float, default=0.0)

    job = relationship("JobRow", back_populates="matches")


class PushRow(Base):
    __tablename__ = "pushes"
    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    channel = Column(String(30), nullable=False)  # email / github_issue / telegram
    tier = Column(String(10))
    kind = Column(String(20), default="realtime")  # realtime / daily / weekly
    sent_at = Column(DateTime, default=datetime.utcnow)
    external_ref = Column(String(500))  # e.g. issue url, tg message id
    error = Column(Text)


class FeedbackRow(Base):
    __tablename__ = "feedback"
    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id"))
    push_id = Column(Integer, ForeignKey("pushes.id"))
    action = Column(String(20), nullable=False)  # want / applied / maybe / reject / noise
    at = Column(DateTime, default=datetime.utcnow)
    note = Column(Text)


# ----------------------------- session mgmt ---------------------------------


_engine = None
_Session = None


def init_db() -> None:
    """Create engine + schema if needed."""
    global _engine, _Session
    if _engine is not None:
        return
    s = get_settings()
    _engine = create_engine(s.db_url, future=True)
    Base.metadata.create_all(_engine)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    init_db()
    assert _Session is not None
    sess = _Session()
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()


# ----------------------------- helpers --------------------------------------


def upsert_job(sess: Session, job_row: JobRow) -> JobRow:
    """Upsert by fingerprint. Updates last_seen_at + re-saves description."""
    stmt = select(JobRow).where(JobRow.fingerprint == job_row.fingerprint)
    existing = sess.execute(stmt).scalar_one_or_none()
    now = datetime.utcnow()
    if existing is None:
        job_row.first_seen_at = now
        job_row.last_seen_at = now
        sess.add(job_row)
        sess.flush()
        return job_row
    existing.last_seen_at = now
    # Keep latest description / salary / apply_url in case the posting updates.
    existing.description = job_row.description or existing.description
    existing.salary_text = job_row.salary_text or existing.salary_text
    existing.apply_url = job_row.apply_url or existing.apply_url
    existing.location = job_row.location or existing.location
    existing.is_remote = job_row.is_remote
    return existing
