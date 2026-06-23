"""Translation guard — did a real foreign → your-language translation happen?

Tideline only translates INTO your first language (DESIGN §3.3); a "same-
language" translation isn't a real use case. When the model hits its edge — the
source was already your language, or it just echoed the source without
translating it — there's no useful result to show. Rather than surface a wrong /
no-op "translation", judge it here so the caller can say, honestly, that this
one was beyond reach — and skip sedimenting it, so the emergence loop is never
fed garbage. Mirrors the Android shell's TranslationGuard and the engineering-
vs-reasoning stance: fail empty, never fail with a wrong answer.

Known limit: a source in Han characters the model labels as Japanese yet leaves
untranslated (国産茶 → 国産茶) can't be caught by script — Japanese kanji and
Chinese share glyphs, so there's no signal that "茶葉" is unrendered Japanese
rather than Chinese. The guard catches the cases the model itself flags (source
read as the native language) and plain echoes.

Pure function (no I/O, no model) so the judgement is unit-tested on both ends
with the same cases. The language folding (`_canon_lang`) is kept self-contained
— separate from `intelligence.source_language.normalize_language` on purpose,
exactly as the two ends already are: that one canonicalizes ONE reported
language for bucketing; this one only asks "are these two language names the
same?" and must also fold native-script spellings ("中文") and fall back to a raw
match for a language it doesn't know.
"""

from __future__ import annotations

from enum import Enum


class TranslationOutcome(Enum):
    """The verdict on whether a real foreign → native translation landed."""

    #: A real foreign → native translation; show it and let it sediment.
    TRANSLATED = "translated"
    #: The source is (or was read as) the reader's own language — nothing to do.
    SAME_AS_NATIVE = "same_as_native"
    #: The model echoed the source; no translation landed.
    NOT_TRANSLATED = "not_translated"


def judge_translation(
    source: str | None,
    translated: str,
    reported_lang: str | None,
    native_lang: str,
) -> TranslationOutcome:
    """Judge whether a real translation into ``native_lang`` happened.

    ``source`` is the input we have text for (typed text / audio transcript;
    None for an image, whose "source" is pixels). ``reported_lang`` is the
    model's reported source language (an image / audio LANGUAGE line, or the
    agent-reported source_lang; None when unavailable, e.g. plain typed text on
    a path that reports no language).
    """
    if not translated.strip():
        return TranslationOutcome.NOT_TRANSLATED
    # 1. The model says the source is already the reader's language.
    if reported_lang is not None and _same_language(reported_lang, native_lang):
        return TranslationOutcome.SAME_AS_NATIVE
    # 2. The output still essentially IS the input — the model echoed it.
    if source is not None and _looks_untranslated(source, translated):
        return TranslationOutcome.NOT_TRANSLATED
    return TranslationOutcome.TRANSLATED


def _same_language(a: str, b: str) -> bool:
    na = _canon_lang(a)
    return bool(na) and na == _canon_lang(b)


def _canon_lang(s: str) -> str:
    """Fold common spellings of a language to one token, so the model's
    "Chinese" / "中文" / "zh" all match the native-language setting. Mirrors the
    Android guard's canonLang; a language we don't recognize falls back to its
    lowercased spelling so two identical unknown names still match."""
    t = s.strip().lower()
    if (
        any(k in t for k in ("chinese", "mandarin", "中文", "汉语"))
        or t == "zh"
        or t.startswith("zh-")
    ):
        return "chinese"
    if "japanese" in t or "日本" in t or t == "ja":
        return "japanese"
    if "korean" in t or "한국" in t or t == "ko":
        return "korean"
    if "english" in t or t == "en":
        return "english"
    if "french" in t or "français" in t or t == "fr":
        return "french"
    return t


def _looks_untranslated(source: str, translated: str) -> bool:
    """The translation still mostly IS the source — the model echoed it instead
    of translating. Compares on letters/digits only (punctuation and spacing
    don't count), so "非常口 非常口" vs "非常口非常口" still reads as an echo."""
    a = _normalize_for_compare(source)
    b = _normalize_for_compare(translated)
    # Require a few characters before calling it an echo, so a short same-glyph
    # word (寿司 is identical in Japanese and Chinese — a legit term) is never
    # mistaken for a non-translation.
    if len(a) < 4 or not b:
        return False
    if a == b:
        return True
    # One fully contains the other's content (a longer echo with extra noise —
    # the "Premium 高级" half-translation, where the foreign word rode along).
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) >= 4 and shorter in longer


def _normalize_for_compare(s: str) -> str:
    return "".join(ch.lower() for ch in s if ch.isalnum())
