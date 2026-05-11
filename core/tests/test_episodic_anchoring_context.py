"""Context-injected episodic fields verification.

Each client (CLI / HTTP / Android shell) defaults source/session via
the agent's `context` dict. The AddTranslationTool reads these as
fallbacks when the LLM doesn't supply them explicitly — so the keyboard
CLI tags every row source="text" without needing Gemma to reason about
input modality.

Functional gates:
- LLM-supplied args take priority over context defaults
- Context defaults fill in when args are omitted
- Both are NULL when neither side supplies
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys

import pytest

from tideline.tools import AddTranslationTool, init_all_tables


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    init_all_tables(c)
    yield c
    c.close()


def test_context_source_default_fills_when_args_omit(conn):
    AddTranslationTool().run(
        {"original": "hello", "target_lang": "zh", "translated": "你好"},
        {"db": conn, "source": "text"},
    )
    row = conn.execute("SELECT source FROM translations").fetchone()
    assert row[0] == "text"


def test_explicit_args_override_context_default(conn):
    """If the LLM does supply source, it wins over the context default."""
    AddTranslationTool().run(
        {
            "original": "hello",
            "target_lang": "zh",
            "translated": "你好",
            "source": "image",
        },
        {"db": conn, "source": "text"},
    )
    row = conn.execute("SELECT source FROM translations").fetchone()
    assert row[0] == "image"


def test_both_unset_leaves_source_null(conn):
    AddTranslationTool().run(
        {"original": "hello", "target_lang": "zh", "translated": "你好"},
        {"db": conn},
    )
    row = conn.execute("SELECT source FROM translations").fetchone()
    assert row[0] is None


def test_session_id_follows_same_fallback_pattern(conn):
    AddTranslationTool().run(
        {"original": "hello", "target_lang": "zh", "translated": "你好"},
        {"db": conn, "session_id": "tokyo-2026-04"},
    )
    row = conn.execute("SELECT session_id FROM translations").fetchone()
    assert row[0] == "tokyo-2026-04"


def test_cli_tags_translations_as_text_source(tmp_path):
    """End-to-end: CLI translation should land source='text' on the row."""
    db_path = tmp_path / "test.db"
    result = subprocess.run(
        [
            sys.executable, "-m", "tideline.cli",
            "--runtime", "mock", "--db", str(db_path),
            "translate hello to zh",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    c = sqlite3.connect(str(db_path))
    row = c.execute("SELECT source FROM translations").fetchone()
    c.close()
    assert row[0] == "text"
