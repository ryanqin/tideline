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


# B6 for SCENE TYPES (2026-06-14). A theme is now a KIND of place clustered
# across visits (拉面店 / 车站), not one remembered occasion — so its name wants
# a warm, place-typed caption, not a "the night..." single-event frame. The
# scene_label stays the key; this is only the title that surfaces on the shore.
SCENE_SYSTEM_PROMPT = (
    "Give a warm 3-6 character Chinese name to a KIND of place a learner keeps "
    "returning to. It should evoke the place and its mood, keep the place "
    "recognizable, and read as a recurring kind of spot — NOT a one-time event "
    "('the night...', 'one Sunday') and NOT a bare category label. Output only "
    "the name."
)


def build_scene_prompt(scene_label: str, items: list[dict], native_lang: str) -> str:
    """Render a scene-type theme into a B6 naming prompt.

    `scene_label` is the model's short place-type label (拉面店); `items` are
    the words met there. The name is written in `native_lang` (the reader's
    first language) and should embellish the place type without losing it.
    """
    if not scene_label or not scene_label.strip():
        raise ValueError("build_scene_prompt requires a scene_label")
    if not native_lang or not native_lang.strip():
        raise ValueError("build_scene_prompt requires a native_lang")
    words = "、".join(item["term"] for item in items[:8])
    return (
        f"这是一类反复去的地方,类型是「{scene_label}」,在这里遇到过这些词:"
        f"{words}。请给它起一个温暖、有韵味的 {native_lang} 短名(3-6 字),"
        "既能让人认出是哪类地方,又带一点情绪;不要写成'那一夜'式的单次事件,"
        "也不要只是干巴巴的类别词。只输出名字。"
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
