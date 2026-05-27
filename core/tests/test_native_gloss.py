"""Native-gloss generation — render a term in the user's first language.

Generation needs the model; here a stub runtime stands in. The parse guards
(short-phrase length cap, echo rejection) are what keep a chatty reply — or a
mock echoing the prompt — from landing a sentence in the gloss column.
"""

from __future__ import annotations

from tideline.intelligence import native_gloss as ng
from tideline.runtime import ModelRuntime


class _Fixed(ModelRuntime):
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def generate(self, prompt: str) -> str:
        return self._reply


def test_build_prompt_names_term_and_target_language():
    p = ng.build_prompt("ラーメン", "Chinese")
    assert "ラーメン" in p and "Chinese" in p


def test_parse_response_clean_gloss():
    assert ng.parse_response("拉面") == "拉面"


def test_parse_response_strips_quotes_and_trailing_punctuation():
    assert ng.parse_response('"拉面"') == "拉面"
    assert ng.parse_response("拉面。") == "拉面"


def test_parse_response_takes_first_line():
    assert ng.parse_response("拉面\n(a noodle dish)") == "拉面"


def test_parse_response_rejects_sentence():
    # A whole sentence is the model ignoring output discipline, not a gloss.
    assert ng.parse_response("Sure! The translation of this word is 拉面 in Chinese.") is None


def test_parse_response_rejects_mock_echo():
    assert ng.parse_response("[mock] echo: Translate 'ラーメン' into Chinese.") is None


def test_parse_response_rejects_empty():
    assert ng.parse_response("") is None
    assert ng.parse_response("   ") is None


def test_parse_response_keeps_gloss_equal_to_term():
    # CJK-shared vocab: the correct native gloss can equal the source term
    # (寿司 is 寿司 in both Japanese and Chinese). Must not be rejected.
    assert ng.parse_response("寿司") == "寿司"


def test_parse_response_rejects_foreign_script_for_native():
    # The model echoed the source untranslated — 'corazón' is no Chinese gloss.
    assert ng.parse_response("corazón", "Chinese") is None
    # A CJK gloss passes, even one identical to the source term.
    assert ng.parse_response("寿司", "Chinese") == "寿司"
    assert ng.parse_response("拉面", "Chinese") == "拉面"


def test_parse_response_keeps_latin_gloss_for_latin_native():
    assert ng.parse_response("butter", "English") == "butter"


def test_generate_roundtrip_with_model():
    assert ng.generate("ラーメン", "Chinese", _Fixed("拉面")) == "拉面"


def test_generate_none_on_mock_echo():
    echo = "[mock] echo: Translate 'x' into Chinese."
    assert ng.generate("x", "Chinese", _Fixed(echo)) is None
