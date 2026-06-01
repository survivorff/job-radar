from datetime import datetime

from job_radar.config import Profile, Track
from job_radar.models import Job
from job_radar.pipeline.heuristic_scorer import score


def _profile() -> Profile:
    return Profile(
        name="t",
        tracks=[
            Track(
                id="crypto_ai",
                priority=1,
                resume_version="V3",
                include_keywords=["LLM", "RAG", "Agent", "Crypto", "LangChain", "MCP"],
                required_any=["Agent", "RAG"],
                prefer_remote_overseas=True,
            ),
        ],
    )


def _job(title: str, desc: str, company: str = "OKX", location: str = "Remote", is_remote: bool = True) -> Job:
    return Job(
        fingerprint=Job.compute_fingerprint(company, title, location),
        source="test",
        external_id="1",
        company=company,
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


def test_remote_crypto_senior_scores_high():
    j = _job(
        "Senior AI Agent Engineer",
        "Design LLM-powered agents with RAG, LangChain, MCP for a Crypto exchange.",
    )
    s = score(j, _profile(), ["crypto_ai"])
    assert s.tier in ("high", "med")
    assert s.overall >= 80
    assert s.suggested_resume_version == "V3"


def test_non_remote_non_crypto_scores_lower():
    j = _job(
        "AI Engineer",
        "Build LLM agent applications.",
        company="UnknownCo",
        location="Paris",
        is_remote=False,
    )
    s = score(j, _profile(), ["crypto_ai"])
    assert s.overall < 90
