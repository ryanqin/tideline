"""Step 2 verification: Gemma format parser + serializer.

Each test exercises a different parser dimension, ordered by difficulty so
that a failure clearly points at which capability regressed (per the design
of the gemma_outputs fixtures — see tests/fixtures/gemma_outputs.py).
"""

from __future__ import annotations

from tests.fixtures.gemma_outputs import (
    NL_PLUS_TOOL,
    NOOP_CALL,
    TRANSLATE_CALL,
    WEATHER_CALL,
)
from tideline.format import (
    parse_response,
    serialize_tool_declaration,
    serialize_tool_response,
)


def test_parse_noop_no_args():
    """Empty body: smallest possible tool call."""
    response = parse_response(NOOP_CALL)
    assert response.finish_reason == "tool_calls"
    assert len(response.tool_calls) == 1
    tc = response.tool_calls[0]
    assert tc.name == "noop"
    assert tc.args == {}


def test_parse_weather_string_with_comma():
    """String boundary recognition: 'Tokyo, JP' must NOT split on its comma."""
    response = parse_response(WEATHER_CALL)
    assert response.finish_reason == "tool_calls"
    tc = response.tool_calls[0]
    assert tc.name == "get_current_weather"
    assert tc.args == {"location": "Tokyo, JP"}


def test_parse_translate_mixed_types():
    """Type heterogeneity: strings AND numbers in the same body."""
    response = parse_response(TRANSLATE_CALL)
    tc = response.tool_calls[0]
    assert tc.name == "translate"
    assert tc.args == {
        "text": "こんにちは",
        "target_lang": "zh",
        "temperature": 0.3,
    }
    assert isinstance(tc.args["temperature"], float)


def test_parse_nl_plus_tool_split():
    """Natural-language preamble must split cleanly from the tool call."""
    response = parse_response(NL_PLUS_TOOL)
    assert response.finish_reason == "tool_calls"
    assert response.text == "I'll check the weather for you."
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "get_current_weather"


def test_parse_plain_text_is_stop():
    """No tool_call markers → finish_reason 'stop' and text passes through."""
    response = parse_response("Hello, world.")
    assert response.finish_reason == "stop"
    assert response.text == "Hello, world."
    assert response.tool_calls == []


def test_serialize_tool_declaration_empty_schema():
    out = serialize_tool_declaration("noop", {})
    assert out == "<|tool>declaration:noop{}<tool|>"


def test_serialize_tool_declaration_with_string_param():
    out = serialize_tool_declaration("get_current_weather", {"location": "string"})
    assert out == '<|tool>declaration:get_current_weather{location:<|"|>string<|"|>}<tool|>'


def test_serialize_tool_response():
    out = serialize_tool_response("noop", "noop done")
    assert out == '<|tool_response>response:noop{result:<|"|>noop done<|"|>}<tool_response|>'


def test_round_trip_parse_then_re_extract():
    """Parsing the round-tripped raw output recovers the same call."""
    response = parse_response(NOOP_CALL)
    re_parsed = parse_response(response.tool_calls[0].raw)
    assert len(re_parsed.tool_calls) == 1
    assert re_parsed.tool_calls[0].name == "noop"
