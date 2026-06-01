"""Text helpers: HTML strip, normalize, remote detection."""

from __future__ import annotations

import re
from html.parser import HTMLParser

REMOTE_MARKERS = {
    "remote",
    "worldwide",
    "global",
    "anywhere",
    "distributed",
    "work from anywhere",
    "fully remote",
    "远程",
    "远端",
}


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "li", "div", "tr", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def text(self) -> str:
        return "".join(self._parts)


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    stripper = _HTMLStripper()
    try:
        stripper.feed(s)
    except Exception:
        return s
    text = stripper.text()
    # collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def is_remote(*parts: str | None) -> bool:
    s = " ".join(p.lower() for p in parts if p)
    return any(m in s for m in REMOTE_MARKERS)


def contains_any(text: str, keywords: list[str]) -> bool:
    """Case-insensitive contains-any."""
    if not text or not keywords:
        return False
    lower = text.lower()
    return any(kw.lower() in lower for kw in keywords)


def count_keyword_hits(text: str, keywords: list[str]) -> int:
    if not text or not keywords:
        return 0
    lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in lower)
