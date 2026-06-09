"""
Pure-function markdown → feed-item parser for the geodo.ai Intelligence Feed.
No Streamlit dependency — safe to import in tests.
"""
from __future__ import annotations

import html
import re

_CAT_MAP: list[tuple[tuple[str, ...], str, str]] = [
    (("buyer", "persona", "segment", "institution", "community bank", "credit union"),
     "BUYER INTEL", "#5fd0e0"),
    (("regulatory", "fincen", "occ", "sar", "penalty", "consent order", "enforcement",
      "citation", "cited"),
     "REGULATORY", "#ff5468"),
    (("pain", "challenge", "struggle", "miss", "false positive", "manual", "burden",
      "legacy"),
     "PAIN SIGNAL", "#f7b733"),
    (("why now", "urgent", "mandate", "2024", "2025", "2026", "examination", "next cycle",
      "peer filing"),
     "WHY NOW", "#34d6a4"),
]
_DEFAULT_CAT = ("INTELLIGENCE", "#8ab4ff")

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"\*(.+?)\*")
_HEADING_RE = re.compile(r"^#{1,3}\s+(.+)$")
_BULLET_RE = re.compile(r"^[-*•]\s*(.+)$")


def _classify(text: str) -> tuple[str, str]:
    lower = text.lower()
    for keywords, cat, color in _CAT_MAP:
        if any(k in lower for k in keywords):
            return cat, color
    return _DEFAULT_CAT


def _strip_markdown(text: str) -> str:
    text = _BOLD_RE.sub(r"\1", text)
    text = _ITALIC_RE.sub(r"\1", text)
    return text.strip()


def parse_research_feed(text: str | None, max_items: int = 6) -> list[dict]:
    """
    Parse markdown research text into structured feed items.

    Returns a list of dicts:
      {"category": str, "color": str, "text": str (HTML-escaped), "delay": float}

    Guarantees:
    - Never raises on any input.
    - Returns [] for None, empty, or whitespace-only input.
    - Caps output at max_items (default 6).
    - All text values are HTML-escaped (no XSS).
    - Items with < 15 chars of content are silently dropped.
    - delay is monotonically increasing starting at 0.0.
    """
    if not text or not text.strip():
        return []
    if max_items <= 0:
        return []

    items: list[dict] = []
    current_section = ""
    buffer: list[str] = []

    def commit(section: str, raw_lines: list[str]) -> None:
        joined = " ".join(l.strip() for l in raw_lines if l.strip())
        cleaned = _strip_markdown(joined)
        if len(cleaned) < 15:
            return
        escaped = html.escape(cleaned)
        combined = (section + " " + cleaned).lower()
        cat, color = _classify(combined)
        items.append({"category": cat, "color": color, "text": escaped})

    for line in text.split("\n"):
        stripped = line.strip()

        if not stripped:
            if buffer:
                commit(current_section, buffer)
                buffer = []
            continue

        heading_m = _HEADING_RE.match(stripped)
        if heading_m:
            if buffer:
                commit(current_section, buffer)
                buffer = []
            current_section = heading_m.group(1)
            continue

        bullet_m = _BULLET_RE.match(stripped)
        if bullet_m:
            if buffer:
                commit(current_section, buffer)
                buffer = []
            commit(current_section, [bullet_m.group(1)])
            continue

        buffer.append(stripped)

    if buffer:
        commit(current_section, buffer)

    result = items[:max_items]
    for i, item in enumerate(result):
        item["delay"] = round(i * 0.09, 2)
    return result
