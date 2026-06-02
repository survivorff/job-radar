"""Stage 3 placeholder for M1/M2: deterministic scorer with bilingual reasons.

Produces:
  - overall + 4 dims (tech_stack / scenario / seniority / company_fit)
  - matched_keywords (evidence, listed in email)
  - reasons / risks in EN + ZH
  - explanation: one-sentence summary (EN + ZH)

M3 replaces this with the real LLM scorer. Keeping the shape identical so
downstream code (digest, templates) doesn't need to change.
"""

from __future__ import annotations

from job_radar.config import Profile
from job_radar.models import Job, Score
from job_radar.text import contains_any

AGENT_SIGNALS = ["agent", "rag", "llm", "mcp", "langgraph", "langchain", "vector", "embedding"]
CRYPTO_SIGNALS = [
    "crypto",
    "web3",
    "blockchain",
    "defi",
    "dex",
    "cex",
    "exchange",
    "solana",
    "ethereum",
    "evm",
    "smart contract",
    "wallet",
    "token",
    "onchain",
    "on-chain",
]
CRYPTO_BRANDS = [
    "okx",
    "binance",
    "coinbase",
    "chainlink",
    "kraken",
    "ripple",
    "polygon",
    "circle",
    "bybit",
    "bitget",
    "consensys",
    "gemini",
    "bitgo",
    "blockstream",
    "solana",
    "uniswap",
    "jupiter",
    "raydium",
    "layerzero",
    "dydx",
    "aave",
    "bitmart",
    "mexc",
]
AI_BRANDS = [
    "anthropic",
    "openai",
    "deepseek",
    "moonshot",
    "langchain",
    "stripe",
    "cohere",
    "mem0",
    "replicate",
    "databricks",
]

SENIOR_MARKERS = [
    "senior",
    "staff",
    "principal",
    "lead",
    "manager",
    "architect",
    "expert",
    "资深",
    "高级",
    "专家",
]

ASIA_EMEA_MARKERS = [
    "singapore",
    "tokyo",
    "hong kong",
    "taipei",
    "london",
    "dubai",
    "berlin",
    "lisbon",
    "seoul",
    "apac",
    "emea",
]


def _collect_matched_keywords(text: str, keywords: list[str]) -> list[str]:
    lower = text.lower()
    seen: list[str] = []
    for kw in keywords:
        if kw.lower() in lower and kw not in seen:
            seen.append(kw)
    return seen


def _dimension_reasons(
    job: Job,
    matched_tracks: list[str],
    matched_kw: list[str],
    dims: dict[str, int],
) -> tuple[list[str], list[str]]:
    """Emit EN + ZH reason bullets describing why this JD scored well."""
    en: list[str] = []
    zh: list[str] = []

    if "crypto_ai" in matched_tracks and job.is_remote:
        en.append("Remote crypto × AI — your top priority track")
        zh.append("远程 Crypto × AI — 你的首推方向")
    elif "crypto_ai" in matched_tracks:
        en.append("Crypto × AI role — priority track")
        zh.append("Crypto × AI 岗 — 优先方向")
    elif "crypto_exchange" in matched_tracks:
        en.append("Exchange backend — directly leverages your CEX experience")
        zh.append("交易所后端 — 直接复用你 CEX 经验")
    elif "web3_backend" in matched_tracks:
        en.append("Web3 backend — aligned with your DEX / wallet / multichain work")
        zh.append("Web3 后端 — 契合你 DEX / 钱包 / 多链经验")
    elif "ai_infra" in matched_tracks:
        en.append("AI infra role — leverages your Java + distributed background")
        zh.append("AI Infra — 契合你 Java + 分布式背景")
    elif "ai_app_arch" in matched_tracks:
        en.append("AI application role — matches your AI workflow practice")
        zh.append("AI 应用 — 匹配你的 AI Workflow 实践")

    if matched_kw:
        preview = ", ".join(matched_kw[:6])
        more = f" (+{len(matched_kw) - 6} more)" if len(matched_kw) > 6 else ""
        en.append(f"Hits your keywords: {preview}{more}")
        zh.append(f"命中关键词：{preview}{more}")

    if dims["seniority"] >= 85:
        en.append("Seniority matches (Senior/Staff/Principal/Lead)")
        zh.append("职级匹配（Senior / Staff / Principal / Lead）")

    company_lower = job.company.lower()
    if any(b in company_lower for b in CRYPTO_BRANDS + AI_BRANDS):
        en.append(f"{job.company} is on your high-signal company list")
        zh.append(f"{job.company} 在你的高价值公司清单里")

    return en[:4], zh[:4]


def _risks(job: Job, matched_kw_lower: set[str]) -> tuple[list[str], list[str]]:
    """Emit EN + ZH risk bullets."""
    en: list[str] = []
    zh: list[str] = []
    text_lower = f"{job.title} {job.description}".lower()

    if "typescript" in text_lower and "typescript" not in matched_kw_lower:
        en.append("Requires TypeScript — lighter on your resume")
        zh.append("要求 TypeScript — 你简历上偏弱项")
    if " phd " in text_lower or "ph.d." in text_lower:
        en.append("Mentions PhD — may lean research")
        zh.append("要求博士学历 — 可能偏研究岗")
    if "on-site" in text_lower and not job.is_remote:
        en.append("On-site requirement — verify remote eligibility")
        zh.append("要求 on-site — 需确认远程可能性")
    if "rust" in text_lower and "rust" not in matched_kw_lower:
        en.append("Prefers Rust — add-on skill for you")
        zh.append("偏好 Rust — 你的加分项而非强项")
    if "compliance" in text_lower or "aml" in text_lower:
        en.append("Heavy compliance context — may not match your eng focus")
        zh.append("合规/AML 重 — 可能与你的工程方向不完全契合")
    return en[:3], zh[:3]


def _explanation(job: Job, matched_tracks: list[str], matched_kw: list[str], overall: int) -> tuple[str, str]:
    """One-line summary, EN + ZH."""
    remote = "remote " if job.is_remote else ""
    track_label = {
        "crypto_ai": "Crypto×AI",
        "ai_app_arch": "AI App",
        "ai_infra": "AI Infra",
        "crypto_exchange": "CEX Backend",
        "web3_backend": "Web3 Backend",
        "senior_backend": "Senior Backend",
    }
    tracks_en = " + ".join(track_label.get(t, t) for t in matched_tracks)
    track_label_zh = {
        "crypto_ai": "Crypto×AI",
        "ai_app_arch": "AI 应用架构",
        "ai_infra": "AI Infra",
        "crypto_exchange": "交易所后端",
        "web3_backend": "Web3 后端",
        "senior_backend": "资深后端",
    }
    tracks_zh = " + ".join(track_label_zh.get(t, t) for t in matched_tracks)
    top_kw = ", ".join(matched_kw[:3]) if matched_kw else "—"
    en = (
        f"{job.company} — {remote}{tracks_en} role scoring {overall}. "
        f"Strongest signals: {top_kw}."
    )
    zh = (
        f"{job.company} 的{('远程' if job.is_remote else '')}{tracks_zh}岗位，匹配 {overall}。"
        f"核心命中：{top_kw}。"
    )
    return en, zh


def score(job: Job, profile: Profile, matched_tracks: list[str]) -> Score:
    text_blob = f"{job.title}\n{job.description}"

    # 1) gather ALL relevant keywords across matched tracks
    relevant_keywords: list[str] = []
    for t in profile.tracks:
        if t.id in matched_tracks:
            for kw in t.include_keywords:
                if kw not in relevant_keywords:
                    relevant_keywords.append(kw)

    matched_kw = _collect_matched_keywords(text_blob, relevant_keywords)
    hits = len(matched_kw)

    # 2) dims
    tech_stack = min(100, hits * 10 + 30)

    scenario = 50
    if "crypto_ai" in matched_tracks:
        scenario += 15
    if contains_any(text_blob, AGENT_SIGNALS):
        scenario += 15
    scenario = min(100, scenario)

    seniority = 70
    if contains_any(job.title, SENIOR_MARKERS):
        seniority += 20
    seniority = min(100, seniority)

    company_lower = job.company.lower()
    company_fit = 60
    if any(b in company_lower for b in CRYPTO_BRANDS):
        company_fit += 15
    if any(b in company_lower for b in AI_BRANDS):
        company_fit += 15
    # Apply user's boost list
    if profile.boost_companies:
        if any(b.lower() in company_lower for b in profile.boost_companies):
            company_fit = min(100, company_fit + 15)
    company_fit = min(100, company_fit)

    dims = {
        "tech_stack": tech_stack,
        "scenario": scenario,
        "seniority": seniority,
        "company_fit": company_fit,
    }

    base = 0.3 * tech_stack + 0.3 * scenario + 0.2 * seniority + 0.2 * company_fit

    # 3) remote bonus (crypto_ai only)
    bonus = 0
    if "crypto_ai" in matched_tracks:
        if job.is_remote:
            bonus = 8
        elif contains_any(job.location, ASIA_EMEA_MARKERS):
            bonus = 4
    elif "crypto_exchange" in matched_tracks or "web3_backend" in matched_tracks:
        if job.is_remote:
            bonus = 5
        elif contains_any(job.location, ASIA_EMEA_MARKERS):
            bonus = 3
    # senior_backend-only cap: don't let pure Java roles score like crypto roles
    if matched_tracks == ["senior_backend"]:
        base = min(base, 80)

    overall = min(100, int(round(base + bonus)))

    # 4) reasons / risks / explanation, bilingual
    reasons_en, reasons_zh = _dimension_reasons(job, matched_tracks, matched_kw, dims)
    matched_kw_lower = {kw.lower() for kw in matched_kw}
    risks_en, risks_zh = _risks(job, matched_kw_lower)
    explanation_en, explanation_zh = _explanation(job, matched_tracks, matched_kw, overall)

    # 5) suggested resume: crypto_ai always wins if present
    suggested = None
    for t in profile.tracks:
        if t.id in matched_tracks:
            suggested = t.resume_version
            break
    if "crypto_ai" in matched_tracks:
        for t in profile.tracks:
            if t.id == "crypto_ai":
                suggested = t.resume_version
                break

    return Score(
        overall=overall,
        dims=dims,
        reasons=reasons_en,
        reasons_zh=reasons_zh,
        risks=risks_en,
        risks_zh=risks_zh,
        matched_keywords=matched_kw[:12],
        explanation=explanation_en,
        explanation_zh=explanation_zh,
        suggested_resume_version=suggested,
        stage="heuristic",
    )
