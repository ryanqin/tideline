"""A3 — Identify the source language of a snippet.

The work splits along a "detect vs generate" line, per the engineering-vs-
reasoning stance: identifying a language is *detection*, and for non-Latin
scripts it's deterministic and free — kana is Japanese, hangul is Korean, a
bare CJK run is Chinese. No model needed, and it's the case where the user
often can't even type the language. Only Latin script (en/fr/de/es/it/…) is
genuinely ambiguous; that's where the model earns its keep as a fallback.

`detect_script` is the deterministic load-bearing path. `detect` layers the
model fallback on top for the ambiguous remainder. The atom bench
(`bench/atoms/a3_source_language_id.py`) imports `SYSTEM_PROMPT` and
`build_prompt` from here so the benchmark measures the same prompt the product
runs — never two prompts for one atom.
"""

from __future__ import annotations

from tideline.format import build_prompt as _build_turn_prompt
from tideline.format import make_turn
from tideline.runtime import ModelRuntime


SYSTEM_PROMPT = (
    "You are a precise language identifier. Respond with only the language "
    "name in English, no preamble."
)


def build_prompt(text: str) -> str:
    return f"What language is this text written in? '{text}'"


def detect_script(text: str) -> str | None:
    """Deterministic language id from an *unambiguous* script: kana → Japanese,
    hangul → Korean. Returns None for everything else.

    We only claim a language when the script alone settles it. Kana and hangul
    do (no other language uses them). Latin is shared across many languages, and
    a bare CJK run is genuinely ambiguous between Chinese and kanji-only Japanese
    (駅, 寿司) — guessing there would make the "reliable" path unreliable, so both
    defer to the model instead. The backbone stays trustworthy; the model picks
    up the ambiguous remainder."""
    for ch in text:
        cp = ord(ch)
        if 0x3040 <= cp <= 0x30FF:  # hiragana + katakana → Japanese
            return "Japanese"
        if 0xAC00 <= cp <= 0xD7A3:  # hangul syllables → Korean
            return "Korean"
    return None


# Canonical name ← any alias the model might emit. First match wins; "Mandarin"
# folds into "Chinese" so buckets stay consistent with the rest of the app.
_LANG_ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("Japanese", ("japanese",)),
    ("Chinese", ("chinese", "mandarin")),
    ("Korean", ("korean",)),
    ("French", ("french",)),
    ("Spanish", ("spanish", "castilian")),
    ("German", ("german",)),
    ("Italian", ("italian",)),
    ("Portuguese", ("portuguese",)),
    ("Russian", ("russian",)),
    ("Arabic", ("arabic",)),
    ("Thai", ("thai",)),
    ("Dutch", ("dutch",)),
    ("Vietnamese", ("vietnamese",)),
    ("English", ("english",)),
]


def parse_response(response: str) -> str | None:
    """Map a model reply to a canonical language name, or None if it names no
    language we recognize. Tolerant of chatty replies ('It is French.')."""
    low = response.lower()
    for canonical, aliases in _LANG_ALIASES:
        if any(alias in low for alias in aliases):
            return canonical
    return None


def detect(text: str, runtime: ModelRuntime | None = None) -> str | None:
    """Identify the source language: deterministic script first (free,
    reliable), then the model for ambiguous Latin-script text if a runtime is
    given. Returns None when undetermined (no script match, no/又failed model)."""
    script = detect_script(text)
    if script is not None:
        return script
    if runtime is None:
        return None
    history = [make_turn("system", SYSTEM_PROMPT), make_turn("user", build_prompt(text))]
    response = runtime.generate(_build_turn_prompt(history)).strip()
    return parse_response(response)
