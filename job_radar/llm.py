"""Thin LLM client for the Anthropic-compatible proxy.

The proxy at llm.chudian.site accepts Anthropic Messages API shape and
routes to deepseek-v4-pro (or similar). We call it via plain httpx to keep
the dep footprint tiny — LiteLLM would work too but adds a big dep.

Also returns usage for cost tracking.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from job_radar.config import get_settings


@dataclass
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class LLMError(RuntimeError):
    pass


def _endpoint() -> str:
    s = get_settings()
    base = (s.anthropic_api_base or "https://api.anthropic.com").rstrip("/")
    return f"{base}/v1/messages"


def _model() -> str:
    s = get_settings()
    # The scorer_model may be prefixed like "anthropic/deepseek-v4-pro"; strip it.
    raw = s.scorer_model or "deepseek-v4-pro"
    if "/" in raw:
        raw = raw.split("/", 1)[1]
    return raw


def chat(
    system: str,
    user: str,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    timeout: float = 45.0,
) -> LLMResponse:
    s = get_settings()
    if not s.anthropic_api_key:
        raise LLMError("ANTHROPIC_API_KEY not configured")

    payload = {
        "model": _model(),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "x-api-key": s.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    url = _endpoint()

    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    except Exception as exc:
        raise LLMError(f"http error: {exc}") from exc

    if resp.status_code >= 400:
        raise LLMError(f"{resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    # Anthropic format: content is a list of {type,text} blocks
    content = data.get("content") or []
    text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
    text = "".join(text_parts).strip()

    usage = data.get("usage") or {}
    return LLMResponse(
        text=text,
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        model=data.get("model", _model()),
    )


def parse_json_object(text: str) -> dict:
    """Extract the first JSON object from an LLM response.

    Models often wrap JSON in ```json fences or preambles. We look for the
    first `{` and parse with progressive balance-matching.
    """
    text = text.strip()
    if not text:
        raise LLMError("empty response")

    # Strip code fences
    if text.startswith("```"):
        # drop first line + trailing ```
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Fast path
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the first balanced { ... } object
    start = text.find("{")
    if start < 0:
        raise LLMError(f"no JSON object found in response: {text[:200]}")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blob = text[start : i + 1]
                return json.loads(blob)
    raise LLMError(f"unterminated JSON: {text[:200]}")


# Cheap CNY cost estimate. deepseek-v4-pro via the proxy is not metered
# strictly, so we use a conservative universal rate. Override via env if needed.
INPUT_CNY_PER_1K = 0.002
OUTPUT_CNY_PER_1K = 0.008


def estimate_cost_cny(usage: LLMResponse) -> float:
    return (
        usage.input_tokens / 1000.0 * INPUT_CNY_PER_1K
        + usage.output_tokens / 1000.0 * OUTPUT_CNY_PER_1K
    )
