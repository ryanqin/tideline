"""Native gloss — render a term in the user's first language.

This is the *generation* half of ②b-2, and unlike source-language detection it
genuinely needs the model: there's no deterministic shortcut for "what does
ラーメン mean in Chinese" — that's translation. The gloss is the third language
in a learning row (source 日 / target 英 / native 中 = 拉面), produced only when
neither source nor target is already the user's first language.

Same shared-prompt shape as the other intelligence atoms: a future gloss bench
imports SYSTEM_PROMPT / build_prompt from here so it measures the production
prompt.
"""

from __future__ import annotations

from tideline.format import build_prompt as _build_turn_prompt
from tideline.format import make_turn
from tideline.runtime import ModelRuntime


SYSTEM_PROMPT = (
    "You translate a single word or short phrase into the requested language. "
    "Respond with only the translation — no preamble, no quotes, no explanation."
)

# A gloss is a headword — a word or short phrase, not a sentence. Anything
# longer is the model ignoring output discipline (or a stub echoing the prompt
# back, which runs ~40+ chars) — reject it rather than store a sentence.
_MAX_GLOSS_LEN = 30
_STRIP = "\"'“”‘’「」 \t.,;:。，"

# Languages we model by the script their gloss should be written in. A small
# on-device model sometimes echoes the source term untranslated; for a Chinese
# user that surfaces as 'corazón' where 拉面 belongs. Requiring the gloss to
# carry the native script turns those misses into "no gloss" (a tolerable empty
# garnish) instead of a wrong one. Languages we don't model aren't constrained.
_LATIN_LANGS = frozenset(
    {"English", "French", "German", "Spanish", "Italian", "Portuguese",
     "Dutch", "Vietnamese"}
)


def build_prompt(term: str, native_lang: str) -> str:
    return f"Translate '{term}' into {native_lang}."


def _in_native_script(text: str, native_lang: str) -> bool:
    """Does `text` carry a character from `native_lang`'s writing system?"""
    has_han = any(0x4E00 <= ord(c) <= 0x9FFF for c in text)
    has_kana = any(0x3040 <= ord(c) <= 0x30FF for c in text)
    has_hangul = any(0xAC00 <= ord(c) <= 0xD7A3 for c in text)
    if native_lang == "Chinese":
        return has_han
    if native_lang == "Japanese":
        return has_han or has_kana
    if native_lang == "Korean":
        return has_hangul
    if native_lang in _LATIN_LANGS:
        return any("a" <= c.lower() <= "z" for c in text)
    return True  # a language we don't model — don't second-guess the gloss


def parse_response(response: str, native_lang: str | None = None) -> str | None:
    """Pull a clean gloss out of the reply, or None if it doesn't look like one:
    empty, a whole sentence / echoed prompt past the headword cap, or (when
    native_lang is given) text not even written in the native script.

    We deliberately do *not* reject a gloss merely for equaling the input term:
    for CJK-shared vocabulary the correct native gloss is legitimately identical
    (寿司 is 寿司 in both Japanese and Chinese). The script check is what tells
    that apart from an untranslated foreign echo like 'corazón'."""
    if not response or not response.strip():
        return None
    text = response.strip().splitlines()[0].strip(_STRIP).strip()
    if not text or len(text) > _MAX_GLOSS_LEN:
        return None
    if native_lang is not None and not _in_native_script(text, native_lang):
        return None
    return text


def generate(
    term: str, native_lang: str, runtime: ModelRuntime
) -> str | None:
    """Generate a native-language gloss for `term`, or None on a poor reply."""
    history = [
        make_turn("system", SYSTEM_PROMPT),
        make_turn("user", build_prompt(term, native_lang)),
    ]
    response = runtime.generate(_build_turn_prompt(history)).strip()
    return parse_response(response, native_lang)
