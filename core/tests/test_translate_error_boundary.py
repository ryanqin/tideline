"""What /api/translate does when the on-device model doesn't play along.

Every case here was reproduced against the real endpoint before it was fixed.
Two of them lied to the user and three crashed:

  A  model answers in prose, never calls the tool
       → {"translated": "你好", "recorded": true} with ZERO rows written.
         The UI showed a translation; nothing entered the emergence loop; no
         log said so. This is the one that matters — it looks like success.
  E  model keeps calling the tool until the turn budget runs out
       → the internal sentinel "[agent] turn budget exhausted" was handed back
         AS THE TRANSLATION, and the same word was written five times, which
         inflates occurrence_count toward promotion.
  B  model hallucinates a tool name         → KeyError  → HTTP 500
  C  model drops a closing delimiter        → ValueError → HTTP 500
  D  model omits a required argument        → KeyError  → HTTP 500

None of this is exotic: TidelineTranslateViewModel.kt:1112-1114 records that
the Mac probe passes where the device fails, i.e. real E2B already departs
from this exact format. The phone has had an error boundary all along
(onError + an outer try/catch); core was the end without one.

The rule these lock in: the ROW is the result. A capture counts as translated
when the tool wrote it and the guard passed — never because nothing objected,
and never NOT because the loop failed to say goodbye afterwards.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from tideline.runtime import ModelRuntime
from tideline.web.app import create_app


_GOOD_CALL = (
    '<|tool_call>call:add_translation{original:<|"|>hola<|"|>,'
    'source_lang:<|"|>Spanish<|"|>,target_lang:<|"|>Chinese<|"|>,'
    'translated:<|"|>你好<|"|>}<tool_call|>'
)


class _Fixed(ModelRuntime):
    """Replies with the same raw string every turn, and counts the turns."""

    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        return self.raw


@pytest.fixture
def endpoint(tmp_path):
    def _build(raw: str):
        db = tmp_path / f"t{abs(hash(raw)) % 10**8}.db"
        runtime = _Fixed(raw)
        client = TestClient(
            create_app(db_path=str(db), runtime=runtime),
            raise_server_exceptions=False,
        )
        return client, runtime, db

    return _build


def _rows(db) -> list[tuple]:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT original, translated FROM translations"
        ).fetchall()
    finally:
        conn.close()


def test_prose_reply_without_a_tool_call_is_not_reported_as_recorded(endpoint):
    """Case A. The one that looked like success."""
    client, runtime, db = endpoint("你好")

    body = client.post("/api/translate", json={"text": "hola"}).json()

    assert body["recorded"] is False
    assert body["guard"] == "not_translated"
    assert body["translated"] == ""
    assert _rows(db) == [], "nothing was written, so nothing may be claimed"


def test_a_recorded_translation_survives_an_unfinished_run(endpoint):
    """Case E. The row is the result; the loop's closing words are not.

    The model records a real translation and then talks itself out of turns.
    The word IS sedimented, so the honest answer is the row — not the internal
    sentinel (which used to be shown as the translation), and not a refusal
    (which would throw away an answer we have)."""
    client, runtime, db = endpoint(_GOOD_CALL)

    body = client.post("/api/translate", json={"text": "hola"}).json()

    assert runtime.calls == 5, "the loop did run to its turn budget"
    assert body["recorded"] is True
    assert body["translated"] == "你好"
    assert "[agent]" not in body["translated"]
    assert _rows(db) == [("hola", "你好")], "one capture, one row — not five"


@pytest.mark.parametrize(
    "label,raw",
    [
        (
            "hallucinated tool name",
            '<|tool_call>call:translate_text{text:<|"|>hola<|"|>}<tool_call|>',
        ),
        (
            "unterminated string delimiter",
            '<|tool_call>call:add_translation{original:<|"|>hola<|"|>,'
            'source_lang:<|"|>Spanish<|"|>,target_lang:<|"|>Chinese<|"|>,'
            'translated:<|"|>你好}<tool_call|>',
        ),
        (
            "missing required argument",
            '<|tool_call>call:add_translation{source_lang:<|"|>Spanish<|"|>,'
            'translated:<|"|>你好<|"|>}<tool_call|>',
        ),
    ],
)
def test_malformed_tool_calls_answer_honestly_instead_of_crashing(
    endpoint, label, raw
):
    """Cases B, C, D — each of these was an HTTP 500."""
    client, runtime, db = endpoint(raw)

    response = client.post("/api/translate", json={"text": "hola"})

    assert response.status_code == 200, f"{label} still crashes the endpoint"
    body = response.json()
    assert body["recorded"] is False
    assert body["guard"] == "not_translated"
    assert _rows(db) == []


def test_a_tool_failure_is_handed_back_to_the_model_not_raised():
    """The agent's half. A model that names a tool wrongly can often fix it if
    it is told, so the error goes back as that tool's response and the run
    continues inside the same budget — rather than leaving Agent.run."""
    from tideline.agent import Agent
    from tideline.tools import NoopTool, ToolRegistry

    registry = ToolRegistry()
    registry.register(NoopTool)

    replies = iter([
        '<|tool_call>call:nope{}<tool_call|>',  # no such tool
        "recovered",
    ])

    class _Scripted(ModelRuntime):
        def generate(self, prompt: str) -> str:
            return next(replies)

    result = Agent(_Scripted(), registry=registry).run_result("go")

    assert result.finish_reason == "stop"
    assert result.text == "recovered"
    assert result.tool_errors and "nope" in result.tool_errors[0]


def test_run_still_returns_plain_text_for_its_existing_callers():
    """run() is unchanged for the CLI and the bench; run_result() is the
    addition. Keeping both means the bench's budget metric keeps working."""
    from tideline.agent import BUDGET_EXHAUSTED_TEXT, Agent
    from tideline.tools import NoopTool, ToolRegistry

    registry = ToolRegistry()
    registry.register(NoopTool)
    always_calling = _Fixed("<|tool_call>call:noop{}<tool_call|>")

    text = Agent(always_calling, registry=registry).run("go")

    assert text == BUDGET_EXHAUSTED_TEXT
    assert isinstance(text, str)
