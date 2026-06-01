"""Stage 3 — LLM-based JD scorer.

Wraps the Anthropic-compatible proxy. Cheaper than it looks: we truncate
JD to 3000 chars and resume to 2500 chars, expect <800 output tokens per
scoring, so each JD costs <¥0.01.

Cost budget is enforced via `BudgetGuard` (reads JOB_RADAR_DAILY_LLM_BUDGET).
When exhausted, the caller should fall back to heuristic_scorer.

Fail-open: any LLM error returns None; the caller then falls back.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from threading import Lock

from loguru import logger

from job_radar.config import Profile, get_settings
from job_radar.llm import LLMError, chat, estimate_cost_cny, parse_json_object
from job_radar.models import Job, Score

_SPEND_FILE_LOCK = Lock()

# -------------------- prompt --------------------

SYSTEM_PROMPT = """You are an expert job matcher for Frank. Given Frank's resume and a job description, you produce a JSON verdict.

Frank's 真实背景 (based on his 10-year resume, not just aspirational framing):
- 10+ years Java backend engineer, currently Tech Lead at a top-20 crypto exchange
- Deep Crypto / Web3 experience: CEX backend, Meme trading platforms, Solana aggregator (Rust), copy-trading system, smart-contract wallet (Echooo)
- Full Java / Spring Cloud / microservices / high concurrency / JVM / Kafka stack
- Proficient Python / TypeScript / Go; learning / already writing Rust for on-chain work
- AI工程化实践者: daily Cursor + Claude Code + self-built Agent Workflows
- Currently pivoting AI identity: building LangGraph-based on-chain agent + open-source Agent Eval platform as representative works

Frank considers these tracks (priority 1 = top, 4 = fallback):
1. crypto_ai      — AI Agent / RAG / MCP at crypto/web3/exchange (uses his new AI work directly)
1. crypto_exchange — CEX / trading-engine / matching / market-data / derivatives backend
1. web3_backend   — DEX / wallet / aggregator / multichain / copy-trading / meme platform / smart-contract backend
2. leadership     — CTO / co-founder / VP Eng / founding engineer at a remote startup
3. ai_app_arch    — AI application architect at big internet companies
3. ai_infra       — AI platform / LLM infra / gateway / vector / inference
4. senior_backend — general Java/distributed/high-concurrency backend (tier 4 = only if role is senior+ at a name-brand company)
4. fullstack      — full-stack engineer (tier 4 = fallback)

CRITICAL SCORING RULE based on priority:
- Priority 1 tracks (crypto_ai, crypto_exchange, web3_backend): these are Frank's CORE. If a JD matches ANY priority-1 track, it deserves overall 85-100 (assuming seniority + remote match).
- Priority 2 (leadership): CTO/co-founder at a funded remote startup → 85-95.
- Priority 3 (ai_app_arch, ai_infra): good but NOT Frank's primary focus right now. Cap at 85 unless the company is truly exceptional (Anthropic, OpenAI, Stripe AI team).
- Priority 4 (senior_backend, fullstack): cap at 78. These are fallback — Frank's edge is crypto, not generic Java.

In other words: a remote Senior Backend Engineer at GitLab (priority 4) should score LOWER than a remote Backend Engineer at Uniswap (priority 1), even if GitLab is a bigger brand.

Hard requirements (zero overall + verdict=no if any fail):
- Seniority: Senior / Staff / Principal / Tech Lead / Architect. Reject Junior / Intern / Associate / Fellow / Graduate.
- Employment type: Frank accepts full-time, part-time, contract, co-founder / technical-partner, consulting. He does NOT accept internships or "Accelerator Program" style trainee tracks unless explicitly Senior+.
- Frank is REMOTE-ONLY right now. Acceptable locations: "Remote", "Worldwide", "Global", "Anywhere", "Distributed", or any city label if the role explicitly allows fully-remote. On-site-only roles → overall ≤ 40 regardless of other signals.
- NOT interested: pure research scientist, pure frontend, product manager, compliance / AML / KYC analyst, sales, marketing, UX, graphic, customer-service, HR, recruiter, operations, listing/partnership manager, solutions engineer (unless it's explicitly an architecture/engineering role).
- Must be an engineering role (or engineering manager / tech lead / staff eng).

Track-matching logic (STRICT — matched_tracks must reflect what Frank actually would work on, not just what keywords appear):
- Each track requires a GENUINE role match, not just overlapping keywords in a different context
- `crypto_ai` = crypto context AND AI agent/LLM/RAG engineering work
- `crypto_exchange` = builds the exchange itself (matching engine, order book, market data, derivatives, spot, perps, liquidity)
- `web3_backend` = backend for DEX / wallet / aggregator / copy-trading / smart-contract. NOT generic "mentions blockchain"
- `ai_app_arch` = builds LLM-powered products. NOT "uses AI tools occasionally"
- `ai_infra` = platform/infra for LLM serving, vector DBs, gateways, inference. NOT generic Kafka/Redis/K8s
- `senior_backend` = non-crypto senior Java/distributed backend. Mark this ONLY if the role is clearly generic backend (not at a crypto/AI company)
- A Product Designer / Product Manager / Sales / Marketing / Ops / Analyst role matches ZERO tracks. Return matched_tracks=[] and verdict="no".
- Set empty matched_tracks=[] if nothing truly fits. Do NOT pad matched_tracks to look comprehensive.

Output JSON ONLY with this schema:
{
  "dims": {
    "tech_stack": int 0-100,
    "scenario": int 0-100,
    "seniority": int 0-100,
    "company_fit": int 0-100
  },
  "overall": int 0-100,
  "matched_tracks": [string],
  "reasons": [string],             // 2-4 concrete reasons in English, each ≤ 20 words
  "reasons_zh": [string],          // same 2-4 reasons in Chinese
  "risks": [string],
  "risks_zh": [string],
  "explanation": string,            // ≤ 30 words English
  "explanation_zh": string,         // ≤ 30 words Chinese
  "suggested_resume_version": "V1" | "V2" | "V3",
  "verdict": "strong_yes" | "yes" | "maybe" | "no"
}

Calibration:
- strong_yes → overall ≥ 88
- yes        → 75–87
- maybe      → 60–74
- no         → < 60

Calibration notes for tier-stretching:
- A remote-first senior/staff role at a top AI or crypto company on Frank's radar (Alchemy, LangChain, Anthropic, OpenAI, Cohere, Databricks, Stripe, Helius, Polygon, Uniswap, Ethena, Fireblocks, LayerZero, Jump, GitLab, Vercel, Supabase, Sentry, Linear, Notion, GitHub, etc.) with tech stack 80%+ match → push to strong_yes even without crypto_ai track
- Technical co-founder / founding engineer / CTO roles at a well-funded startup (remote) → push to strong_yes if Frank could realistically lead the engineering
- Generic Senior Backend at a random non-Crypto, non-AI company → cap at 80 (yes at best)

Track bonuses (apply AFTER computing base dims):
- If `crypto_ai` in matched_tracks AND role is remote: add +8 to overall (capped at 100)
- If `crypto_exchange` or `web3_backend` in matched_tracks AND company is a top crypto brand (OKX / Binance / Bybit / Coinbase / Kraken / Chainlink / Circle / Ripple / Polygon / Consensys / Gemini / Bitget / HTX / Bitmart / MEXC / Uniswap / Jupiter / Raydium / LayerZero / dYdX / Aave / Alchemy / Helius / Phantom / Ledger / Ethena / Nansen / Dune): add +5 to overall
- If `ai_infra` or `ai_app_arch` at a top-3 AI lab / infra (Anthropic, OpenAI, Cohere, Mistral, Perplexity, Databricks, Stripe, Scale AI, LangChain, Anyscale, Baseten, Modal, Fireworks, Together): add +5 to overall BUT still cap at 85 unless it's truly exceptional
- If `leadership` (CTO / Co-founder / VP Eng / Founding) at a well-funded remote startup: add +6 to overall
- If only `senior_backend` or `fullstack` matched (no priority-1 or priority-2 track): cap overall at 78
- If only `ai_app_arch` or `ai_infra` matched (no priority-1 track): cap overall at 85

Resume version hint:
- V1 = AI Application Architect
- V2 = AI Infra / Platform
- V3 = Crypto × AI (also use this for pure crypto_exchange / web3_backend roles)
"""

USER_TEMPLATE = """<resume>
{resume}
</resume>

<job>
Company: {company}
Title: {title}
Location: {location}  (remote={is_remote})
Source: {source}
Posted: {posted}

{description}
</job>

<hint>
profile.blocked_companies hint (already filtered upstream): {blocked}
profile.boost_companies hint (prefer these): {boosts}
</hint>

Output JSON only.
"""


# -------------------- budget guard --------------------


class BudgetGuard:
    """Tracks daily LLM spend in a small JSON file and refuses over budget."""

    def __init__(self) -> None:
        s = get_settings()
        self.limit_cny = float(s.daily_llm_budget or 5.0)
        self.path: Path = s.data_dir / "llm_spend.json"

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.path)

    def today_spend(self) -> float:
        d = self._load()
        return float(d.get(date.today().isoformat(), 0.0))

    def can_spend(self, estimated: float = 0.01) -> bool:
        return self.today_spend() + estimated <= self.limit_cny

    def record(self, amount_cny: float) -> None:
        with _SPEND_FILE_LOCK:
            d = self._load()
            key = date.today().isoformat()
            d[key] = float(d.get(key, 0.0)) + amount_cny
            # keep only last 14 days
            if len(d) > 14:
                for k in sorted(d.keys())[:-14]:
                    d.pop(k, None)
            self._save(d)


# -------------------- scorer --------------------


_RESUME_CACHE: str | None = None


def _load_resume(profile: Profile) -> str:
    global _RESUME_CACHE
    if _RESUME_CACHE is not None:
        return _RESUME_CACHE
    if not profile.resume_path:
        _RESUME_CACHE = "(resume not provided)"
        return _RESUME_CACHE
    from job_radar.config import ROOT, _home

    # Try several locations
    for base in (_home(), ROOT, Path(".")):
        candidate = Path(profile.resume_path)
        if not candidate.is_absolute():
            candidate = (base / candidate).resolve()
        if candidate.exists():
            _RESUME_CACHE = candidate.read_text(encoding="utf-8")[:2500]
            return _RESUME_CACHE
    _RESUME_CACHE = "(resume file not found)"
    return _RESUME_CACHE


_VERDICT_TO_TIER = {"strong_yes": "high", "yes": "med", "maybe": "low", "no": "drop"}


@dataclass
class LLMScoreResult:
    score: Score | None
    cost_cny: float
    error: str | None = None


def score(
    job: Job,
    profile: Profile,
    matched_tracks: list[str],
    *,
    budget: BudgetGuard | None = None,
) -> LLMScoreResult:
    budget = budget or BudgetGuard()
    if not budget.can_spend(0.01):
        return LLMScoreResult(score=None, cost_cny=0.0, error="budget_exhausted")

    resume = _load_resume(profile)
    description = (job.description or "")[:3000]
    prompt = USER_TEMPLATE.format(
        resume=resume,
        company=job.company,
        title=job.title,
        location=job.location or "—",
        is_remote=bool(job.is_remote),
        source=job.source,
        posted=str(job.posted_at or "unknown"),
        description=description,
        blocked=", ".join(profile.blocked_companies or []) or "(none)",
        boosts=", ".join(profile.boost_companies or []) or "(none)",
    )

    try:
        resp = chat(
            system=SYSTEM_PROMPT,
            user=prompt,
            max_tokens=700,
            temperature=0.1,
        )
    except LLMError as exc:
        logger.warning("llm error for {} — falling back: {}", job.title, exc)
        return LLMScoreResult(score=None, cost_cny=0.0, error=str(exc))

    cost = estimate_cost_cny(resp)
    budget.record(cost)

    try:
        data = parse_json_object(resp.text)
    except Exception as exc:
        logger.warning("llm json parse failed for {}: {}", job.title, exc)
        return LLMScoreResult(score=None, cost_cny=cost, error=f"parse: {exc}")

    try:
        dims = data.get("dims") or {}
        overall = int(data.get("overall", 0))
        # Coerce floats to ints safely
        dims_norm = {k: int(v) for k, v in dims.items() if isinstance(v, (int, float))}
        # Verdict can override tier if mismatch
        verdict = data.get("verdict") or ""
        suggested = data.get("suggested_resume_version")
        if suggested not in ("V1", "V2", "V3"):
            suggested = None

        s = Score(
            overall=max(0, min(100, overall)),
            dims=dims_norm,
            reasons=_clean_list(data.get("reasons")),
            reasons_zh=_clean_list(data.get("reasons_zh")),
            risks=_clean_list(data.get("risks")),
            risks_zh=_clean_list(data.get("risks_zh")),
            matched_keywords=[],  # LLM scorer doesn't surface keywords — leave for heuristic overlay
            explanation=(data.get("explanation") or "")[:400],
            explanation_zh=(data.get("explanation_zh") or "")[:400],
            suggested_resume_version=suggested,
            stage="llm",
        )
        # If LLM's verdict implies a different tier than our numeric thresholds,
        # honour the verdict (clamp the score so the Score.tier property aligns).
        forced = _VERDICT_TO_TIER.get(verdict)
        if forced == "high" and s.overall < 90:
            s.overall = 90
        elif forced == "drop":
            s.overall = 0

        return LLMScoreResult(score=s, cost_cny=cost)
    except Exception as exc:
        logger.warning("llm shape error for {}: {}", job.title, exc)
        return LLMScoreResult(score=None, cost_cny=cost, error=f"shape: {exc}")


def _clean_list(val) -> list[str]:
    if not isinstance(val, list):
        return []
    return [str(x)[:200] for x in val if x][:5]
