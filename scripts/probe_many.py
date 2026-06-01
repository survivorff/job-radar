"""Probe a big list of candidate ATS slugs to see which are alive.

Usage: uv run python scripts/probe_many.py
"""

from __future__ import annotations

import time

import httpx

UA = "job-radar-probe/0.1"

CRYPTO_CANDIDATES = [
    # DEX / DeFi
    "uniswap", "jupiterexchange", "jupiteraggregator", "aave", "dydx", "dydxfoundation",
    "1inch", "sushiswap", "balancer", "curve", "pancakeswap", "ondofinance",
    "lido", "renzo", "eigenlabs", "ethenalabs", "ethenalabsusde",
    "pendle", "compoundlabs", "morphoorg", "synthetix", "paxos", "maker",
    # Wallet / Custody
    "phantom", "rabbywallet", "metamask", "trustwallet", "ledger", "ledger-3",
    "fireblocks", "bitwave", "utilachain", "tangem",
    # Exchange / CEX / derivatives
    "coinbasecareers", "coinbase-careers", "cbcareers",
    "htx", "htxoffice", "mexc-global", "mexc", "kucoin",
    "bitmart", "bingx", "hashkey", "cryptocom", "crypto-com",
    # Infrastructure / chains / rollups
    "solana", "solana-foundation", "solanafoundation", "polygon-labs", "polygonlabs",
    "avalabs", "near", "layerzero", "starknet", "starkware", "zksync", "matter-labs",
    "flare", "immutable", "aleo", "celestiaofficial", "celestia", "manta-network",
    "eigenlayer", "fuel-labs", "scroll-tech",
    # Market maker / quant
    "jumpcrypto", "jumptrading", "wintermute", "gsrmarkets", "gsr",
    "alphalabcapital", "flowtraders",
    # Research / adjacent
    "messari", "dune", "alchemy-inc", "alchemyinc", "alchemy", "thegraph",
    "chainalysis", "trmlabs", "ellipticcoltd", "elliptic", "nansen-ai", "nansen",
    "helius", "heliuslabs", "quicknode", "syndica", "pyth-network",
    # AI labs
    "anthropic", "openai", "cohere", "perplexityai", "perplexity", "xai",
    "mistral", "togetherai", "together-ai", "runwayml", "runway",
    "databricks", "scale", "scaleai", "huggingface",
    # AI infra adjacent
    "fireworksai", "fireworks-ai", "modalcom", "modal", "replicate", "mem0",
    "langchain", "lindyai", "lindy",
]

PROVIDERS = {
    "lever": "https://api.lever.co/v0/postings/{s}?mode=json",
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{s}/jobs",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{s}",
}


def probe(slug: str) -> dict[str, str]:
    out = {}
    with httpx.Client(
        headers={"User-Agent": UA},
        timeout=8.0,
        follow_redirects=True,
    ) as c:
        for prov, tmpl in PROVIDERS.items():
            try:
                r = c.get(tmpl.format(s=slug))
                if r.status_code < 400:
                    # Sanity: confirm non-empty
                    size = len(r.content)
                    out[prov] = f"{r.status_code}/{size}"
                else:
                    out[prov] = f"{r.status_code}"
            except Exception as exc:
                out[prov] = f"err:{type(exc).__name__}"
            time.sleep(0.15)
    return out


def main() -> None:
    header = f"{'slug':<28} {'lever':<14} {'greenhouse':<14} {'ashby':<12}"
    print(header)
    print("-" * len(header))
    alive = []
    for slug in CRYPTO_CANDIDATES:
        r = probe(slug)
        lv = r.get("lever", "?")
        gh = r.get("greenhouse", "?")
        ab = r.get("ashby", "?")
        print(f"{slug:<28} {lv:<14} {gh:<14} {ab:<12}")
        for prov, code in r.items():
            if "/" in code and int(code.split("/")[0]) == 200 and int(code.split("/")[1]) > 200:
                alive.append((slug, prov, code))
    print()
    print("ALIVE (status 200, non-empty body):")
    for slug, prov, code in alive:
        print(f"  {prov:<12} {slug:<25} {code}")


if __name__ == "__main__":
    main()
