"""Bigger ATS probe — 150+ candidate companies."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

UA = "job-radar-probe/0.1"

# ---- candidate slugs, grouped ----
CANDIDATES = {
    # Crypto / DeFi / DEX
    "crypto": [
        "uniswap", "1inch", "paraswap", "0x", "dydx", "dydxfoundation",
        "aave", "ethena", "ethenalabs", "ondofinance", "ondo", "pendle",
        "synthetix", "perp-protocol", "perpprotocol", "flashbots",
        "morpho", "morpholabs", "spark-protocol", "gearbox",
        "jupiter", "jupiterexchange", "jupiteraggregator", "raydium",
        "pancakeswap", "curvefi", "sushiswap", "balancer", "lido",
        "eigenlayer", "eigenlabs", "renzo", "kelpdao", "etherfi",
        "frax", "fraxfinance", "compoundlabs", "compound",
        # wallet
        "phantom", "trustwallet", "rabby", "rainbow", "metamask",
        "argent", "zerion", "ledger", "tangem", "fireblocks",
        # chains / rollups
        "solana", "solana-foundation", "solanafoundation", "solanalabs",
        "polygon", "polygon-labs", "polygonlabs", "avalabs",
        "near", "aptos", "aptoslabs", "sui", "suifoundation", "mystenlabs",
        "starkware", "matter-labs", "zksync", "scroll-tech", "scrolllabs",
        "layerzero", "layerzerolabs", "wormhole", "wormholefoundation",
        "celestia", "celestiaorg", "optimism", "base", "arbitrum",
        "mantle", "linea", "manta-network", "immutable",
        # infra / data
        "alchemy", "alchemy-inc", "quicknode", "helius", "heliuslabs",
        "syndica", "triton", "infura", "thegraph", "the-graph",
        "chainlink", "chainlinklabs", "api3", "pyth-network",
        "dune", "messari", "nansen", "arkham", "coingecko",
        "chainalysis", "trmlabs", "elliptic", "lookonchain",
        # CEX / trading
        "coinbase", "kraken", "geminitrust", "gemini",
        "bitgo", "bybit", "htx", "mexc-global", "hashkey",
        "bitmart", "cryptocom", "crypto-com", "kucoin",
        # market makers
        "jumpcrypto", "jumptrading", "wintermute", "gsr", "gsrmarkets",
        "flowtraders", "tower-research-capital", "cumberland",
    ],
    "ai": [
        "openai", "anthropic", "cohere", "perplexity", "perplexityai",
        "xai", "deepmind", "stabilityai",
        "mistral", "mistralai",
        "togetherai", "together-ai", "fireworksai", "fireworks-ai",
        "runway", "runwayml", "sunoai", "suno-ai", "elevenlabs",
        "databricks", "scaleai", "scale", "huggingface",
        "langchain", "langchainai", "llamaindex",
        "replicate", "modal", "modal-labs", "banana",
        "mem0", "lindy", "crewai",
        "character-ai", "characterai", "inflection-ai", "inflectionai",
        "anyscale", "nomic-ai", "nomicai", "baseten", "truss",
        "cerebrascloud", "cerebras", "lambda-labs", "lambdalabs",
    ],
    "dev_tools": [
        "vercel", "supabase", "netlify", "cloudflare", "github",
        "gitlab", "bitbucket",
        "linear", "notion", "airtable", "figma", "retool",
        "posthog", "mixpanel", "amplitude", "segment",
        "sentry", "datadog", "grafana", "new-relic",
        "sourcegraph", "codeium", "cursor-sh", "cursor",
        "mintlify", "swimm", "readme-io",
        "temporal", "temporalio", "restate", "inngest",
        "turso", "planetscale", "neon",
    ],
    "remote_friendly_saas": [
        "stripe", "shopify", "twilio", "zapier", "automattic",
        "mongodb", "elastic", "elastic-co", "confluent",
        "hashicorp", "snowflake",
        "doordash", "instacart", "coinbase",
        "airtable", "stripe", "block",
    ],
}


PROVIDERS = {
    "lever": "https://api.lever.co/v0/postings/{s}?mode=json",
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{s}/jobs",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{s}",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{s}",
}


def probe_one(slug: str) -> tuple[str, dict[str, str]]:
    out = {}
    with httpx.Client(
        headers={"User-Agent": UA}, timeout=8.0, follow_redirects=True
    ) as c:
        for prov, tmpl in PROVIDERS.items():
            try:
                r = c.get(tmpl.format(s=slug))
                if r.status_code == 200 and len(r.content) > 300:
                    out[prov] = f"200/{len(r.content)}"
            except Exception:
                pass
            time.sleep(0.1)
    return slug, out


def main() -> None:
    all_slugs = set()
    for lst in CANDIDATES.values():
        all_slugs.update(lst)
    print(f"Probing {len(all_slugs)} candidate slugs on 4 ATS providers...")

    alive: list[tuple[str, str, str]] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(probe_one, s): s for s in all_slugs}
        for fut in as_completed(futures):
            slug, r = fut.result()
            for prov, code in r.items():
                alive.append((prov, slug, code))

    # Group output
    print("\n=== ALIVE (provider, slug, size) ===")
    for prov in ("lever", "greenhouse", "ashby", "workable"):
        hits = [(s, c) for p, s, c in alive if p == prov]
        if not hits:
            continue
        print(f"\n## {prov} ({len(hits)} hits)")
        for s, c in sorted(hits):
            print(f"  {s:<30} {c}")


if __name__ == "__main__":
    main()
