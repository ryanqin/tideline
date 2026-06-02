"""B6 — Generate an episodic title for a group of translations.

The atomic primitive for Tier B cluster naming. Given a list of
translations encountered together, ask the model for a 3-7 word title
that anchors to place / time / activity, not generic taxonomy
(DESIGN.md §3.2 episodic anchoring).

The atom bench (`bench/atoms/b6_episodic_title.py`) and the cluster
naming engine (`tideline.cluster.name_clusters`) both import
`SYSTEM_PROMPT`, `build_prompt`, and `parse_response` from here so the
benchmark measures the exact prompts the production engine uses.
"""

from __future__ import annotations

import re


SYSTEM_PROMPT = (
    "Generate a 3-7 word episodic title for a group of translations — "
    "a memory caption framing them as one remembered event, not as a "
    "list of items. Lead with a place, a time marker ('the night', "
    "'one Sunday'), or a possessive ('your', 'our'). Avoid category "
    "labels ('vocabulary', 'words', '<language> X') and itemized "
    "field lists. Output only the title, no preamble."
)


_PREFIX_RE = re.compile(
    r"^\s*(title|episodic title|cluster|name)\s*[:\-]\s*",
    re.IGNORECASE,
)

_MAX_TITLE_WORDS = 12


def build_prompt(items: list[dict], native_lang: str) -> str:
    """Render a group of translations into a B6 prompt.

    `items` is a list of dicts with keys `term` and `context` (context
    may be empty). `native_lang` is the reader's first language: the title
    must be written in it, even though the terms are in other languages —
    Tideline surfaces everything in your language, never the source. The
    bench cases and the production caller both pass this same shape so the
    prompt construction is identical.
    """
    if not items:
        raise ValueError("build_prompt requires at least one item")
    if not native_lang or not native_lang.strip():
        raise ValueError("build_prompt requires a native_lang")
    lines = []
    for item in items:
        term = item["term"]
        context = item.get("context") or ""
        if context:
            lines.append(f"  - '{term}' — encountered: {context}")
        else:
            lines.append(f"  - '{term}'")
    items_text = "\n".join(lines)
    return (
        "These translations were encountered together. Generate a 3-7 word "
        "title that captures their shared episodic moment (place, time, "
        f"activity). Write the title in {native_lang} — the reader's first "
        "language — even though the terms below are in other languages:"
        f"\n{items_text}"
    )


def parse_response(response: str) -> str | None:
    """Extract a clean title from a model response.

    Returns None for empty / unparseable responses. Otherwise returns the
    first non-empty line, with common preambles ('Title:', 'Cluster:',
    etc.) stripped, surrounding quotes/asterisks removed, and length
    capped at _MAX_TITLE_WORDS words.
    """
    if not response:
        return None
    first_line = ""
    for line in response.splitlines():
        stripped = line.strip()
        if stripped:
            first_line = stripped
            break
    if not first_line:
        return None
    cleaned = _PREFIX_RE.sub("", first_line)
    cleaned = cleaned.strip(" \t\"'`*#.")
    if not cleaned:
        return None
    words = cleaned.split()
    if len(words) > _MAX_TITLE_WORDS:
        cleaned = " ".join(words[:_MAX_TITLE_WORDS])
    return cleaned
