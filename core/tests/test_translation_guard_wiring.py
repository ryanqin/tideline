"""The translation guard, wired into the live path (DESIGN §3.3).

Two seams: AddTranslationTool refuses to sediment a non-translation (a same-
language source or an echo), and /api/translate reads the verdict back to tell
the user, honestly, that this one was beyond reach instead of surfacing a wrong
result. The pure judgement is covered in test_translation_guard; here we prove
the wiring — a real pair still lands, a guarded one is skipped and flagged.
"""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from tideline.format import (
    STRING_DELIM,
    TOOL_CALL_CLOSE,
    TOOL_CALL_OPEN,
    TOOL_RESPONSE_OPEN,
)
from tideline.runtime import ModelRuntime
from tideline.tools.translation import AddTranslationTool, init_db
from tideline.web.app import create_app


# --- the tool gate: a non-translation is never sedimented -----------------


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn


def _row_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]


def test_tool_records_a_real_translation():
    conn = _conn()
    ctx: dict = {"db": conn}
    AddTranslationTool().run(
        {
            "original": "ラーメン",
            "source_lang": "Japanese",
            "target_lang": "Chinese",
            "translated": "拉面",
        },
        ctx,
    )
    assert ctx["translation_outcome"] == "translated"
    assert _row_count(conn) == 1


def test_tool_refuses_a_same_language_source():
    conn = _conn()
    ctx: dict = {"db": conn}
    msg = AddTranslationTool().run(
        {
            "original": "今天天气不错",
            "source_lang": "Chinese",  # source already the reader's language
            "target_lang": "Chinese",
            "translated": "今天的天气",
        },
        ctx,
    )
    assert ctx["translation_outcome"] == "same_as_native"
    assert _row_count(conn) == 0
    assert "not recorded" in msg


def test_tool_refuses_an_echo():
    conn = _conn()
    ctx: dict = {"db": conn}
    AddTranslationTool().run(
        {
            "original": "guten tag",
            "source_lang": "German",
            "target_lang": "Chinese",
            "translated": "guten tag",  # echoed, not translated
        },
        ctx,
    )
    assert ctx["translation_outcome"] == "not_translated"
    assert _row_count(conn) == 0


# --- the endpoint: a guarded result is flagged, not surfaced --------------


class _RecordsRuntime(ModelRuntime):
    """Drives the agent to call add_translation with chosen args, then return a
    final line — lets the endpoint test pick a source_lang / translated the
    embedding mock can't express (it never reports a language or echoes)."""

    def __init__(self, original: str, source_lang: str, translated: str) -> None:
        self._o, self._sl, self._tr = original, source_lang, translated

    def generate(self, prompt: str) -> str:
        if TOOL_RESPONSE_OPEN in prompt:
            return self._tr  # final turn: the model's own (possibly bad) text
        return (
            f"{TOOL_CALL_OPEN}call:add_translation{{"
            f"original:{STRING_DELIM}{self._o}{STRING_DELIM},"
            f"source_lang:{STRING_DELIM}{self._sl}{STRING_DELIM},"
            f"target_lang:{STRING_DELIM}Chinese{STRING_DELIM},"
            f"translated:{STRING_DELIM}{self._tr}{STRING_DELIM}"
            f"}}{TOOL_CALL_CLOSE}"
        )


def test_endpoint_flags_a_same_language_source_and_skips_it(tmp_path):
    db = str(tmp_path / "t.db")
    rt = _RecordsRuntime("你好世界", "Chinese", "你好世界")
    c = TestClient(create_app(runtime=rt, db_path=db))

    body = c.post("/api/translate", json={"text": "你好世界"}).json()

    assert body["recorded"] is False
    assert body["guard"] == "same_as_native"
    assert body["translated"] == ""  # the wrong text is not surfaced
    conn = sqlite3.connect(db)
    assert _row_count(conn) == 0  # nothing sedimented


def test_endpoint_flags_an_echo_and_skips_it(tmp_path):
    db = str(tmp_path / "t.db")
    rt = _RecordsRuntime("bonjour le monde", "French", "bonjour le monde")
    c = TestClient(create_app(runtime=rt, db_path=db))

    body = c.post("/api/translate", json={"text": "bonjour le monde"}).json()

    assert body["recorded"] is False
    assert body["guard"] == "not_translated"
    conn = sqlite3.connect(db)
    assert _row_count(conn) == 0


def test_endpoint_marks_a_real_translation_recorded(tmp_path):
    db = str(tmp_path / "t.db")
    c = TestClient(create_app(runtime_name="mock", db_path=db))

    body = c.post("/api/translate", json={"text": "ラーメン"}).json()

    assert body["recorded"] is True
    assert body["guard"] is None
    assert body["translated"]  # a real translation is surfaced
    conn = sqlite3.connect(db)
    assert _row_count(conn) == 1
