"""A3 source-language identification — deterministic script + model fallback.

The deterministic half (detect_script) carries non-Latin scripts with no model;
the model half is exercised here with a stub runtime so the orchestration is
verified without a real model. Real-model accuracy is the atom bench's job.
"""

from __future__ import annotations

from tideline.intelligence import source_language as sl
from tideline.runtime import ModelRuntime


class _Fixed(ModelRuntime):
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def generate(self, prompt: str) -> str:
        return self._reply


# --- deterministic script detection (load-bearing, no model) -------------


def test_detect_script_japanese_from_kana():
    assert sl.detect_script("ラーメン") == "Japanese"
    assert sl.detect_script("お会計をお願いします") == "Japanese"  # kana + kanji mix


def test_detect_script_han_only_is_ambiguous():
    # A bare CJK run could be Chinese or kanji-only Japanese — defer to model.
    assert sl.detect_script("合同") is None
    assert sl.detect_script("我们什么时候开会") is None


def test_detect_script_korean_from_hangul():
    assert sl.detect_script("한국어") == "Korean"


def test_detect_script_kana_wins_over_kanji():
    # A string mixing kana and kanji is Japanese, not Chinese.
    assert sl.detect_script("駅です") == "Japanese"


def test_detect_script_latin_is_ambiguous():
    assert sl.detect_script("beurre") is None
    assert sl.detect_script("hello world") is None
    assert sl.detect_script("") is None


# --- parse_response canonicalization -------------------------------------


def test_parse_response_extracts_language_name():
    assert sl.parse_response("French") == "French"
    assert sl.parse_response("It is French.") == "French"
    assert sl.parse_response("japanese") == "Japanese"


def test_parse_response_folds_mandarin_to_chinese():
    assert sl.parse_response("Mandarin") == "Chinese"


def test_parse_response_none_when_no_language():
    assert sl.parse_response("ramen") is None
    assert sl.parse_response("") is None


# --- normalize_language: canonicalize what the agent reports --------------


def test_normalize_language_maps_iso_codes_to_names():
    assert sl.normalize_language("ja") == "Japanese"
    assert sl.normalize_language("en") == "English"
    assert sl.normalize_language("DE") == "German"   # case-insensitive


def test_normalize_language_passes_through_full_names():
    assert sl.normalize_language("Japanese") == "Japanese"
    assert sl.normalize_language("Mandarin") == "Chinese"


def test_normalize_language_iso_match_is_exact_not_substring():
    # "it" is the Italian code, but a chatty "It is French." must resolve to
    # French via the name parser — never be swallowed as Italian by a substring.
    assert sl.normalize_language("it") == "Italian"
    assert sl.normalize_language("It is French.") == "French"


def test_normalize_language_none_for_empty_or_unknown():
    assert sl.normalize_language(None) is None
    assert sl.normalize_language("") is None
    assert sl.normalize_language("ramen") is None


# --- detect orchestration (script-first, then model) ---------------------


def test_detect_uses_script_without_model():
    assert sl.detect("すし") == "Japanese"  # kana, no runtime needed


def test_detect_falls_back_to_model_for_latin():
    assert sl.detect("beurre", _Fixed("French")) == "French"


def test_detect_latin_without_runtime_is_none():
    assert sl.detect("beurre") is None


def test_detect_script_takes_priority_over_model():
    # A clear script wins; the (wrong) model is never consulted.
    assert sl.detect("ラーメン", _Fixed("Klingon")) == "Japanese"


# --- shared-prompt contract (never two prompts for one atom) -------------


def test_a3_atom_shares_intelligence_prompt():
    from tideline.bench.atoms import a3_source_language_id as a3

    assert a3.SYSTEM_PROMPT is sl.SYSTEM_PROMPT
    assert a3.build_prompt({"text": "ラーメン"}) == sl.build_prompt("ラーメン")
