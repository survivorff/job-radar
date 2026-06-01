from datetime import datetime

from job_radar.config import Profile, Thresholds, Track
from job_radar.models import Job
from job_radar.pipeline.hard_filter import hard_filter


def _profile() -> Profile:
    return Profile(
        name="test",
        tracks=[
            Track(
                id="crypto_ai",
                priority=1,
                resume_version="V3",
                include_keywords=["LLM", "RAG", "Agent", "Crypto", "LangChain"],
                required_any=["Agent", "RAG", "LLM"],
                prefer_remote_overseas=True,
            ),
        ],
        exclude_keywords=["算法研究员", "intern"],
        seniority_blocklist=["junior"],
        location_allowlist=["Remote", "Singapore", "Asia", "北京"],
        thresholds=Thresholds(),
    )


def _job(title: str, desc: str = "", location: str = "", is_remote: bool = False) -> Job:
    return Job(
        fingerprint=Job.compute_fingerprint("Co", title, location),
        source="test",
        external_id="x",
        company="Co",
        title=title,
        location=location,
        is_remote=is_remote,
        department=None,
        description=desc,
        apply_url="http://example.com",
        posted_at=None,
        salary_text=None,
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
    )


def test_exclude_kills_intern():
    j = _job("Intern AI Engineer", "We build LLM and Agent systems with Crypto data")
    r = hard_filter(j, _profile())
    assert r.passed is False
    assert "excluded" in r.reason or "seniority" in r.reason


def test_track_matched_remote_passes():
    j = _job(
        "Senior AI Engineer",
        "Build LLM agents with RAG for a Crypto exchange; LangChain a plus.",
        "Remote",
        is_remote=True,
    )
    r = hard_filter(j, _profile())
    assert r.passed, r.reason
    assert "crypto_ai" in r.matched_tracks


def test_no_track_match_blocked():
    j = _job("Frontend Engineer", "React / Vue / CSS", "Remote", is_remote=True)
    r = hard_filter(j, _profile())
    assert r.passed is False


def test_location_not_in_list_blocked_unless_remote():
    j = _job(
        "Senior AI Engineer",
        "Build LLM agents with RAG for a Crypto exchange; LangChain a plus.",
        "Paris, France",
        is_remote=False,
    )
    r = hard_filter(j, _profile())
    assert r.passed is False
    assert "location" in r.reason
