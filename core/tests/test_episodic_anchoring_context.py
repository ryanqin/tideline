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


def test_context_source_image_is_stored_as_recall_material(conn):
    """A captured photo rides in via context (the image pipeline / Android shell
    injects the bytes) — never through the LLM, which only produces the scene
    gist. Kept on the row as recall material (§3.2), round-tripping as a BLOB."""
    photo = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"
    AddTranslationTool().run(
        {"original": "ラーメン", "source_lang": "ja",
         "target_lang": "zh", "translated": "拉面"},
        {"db": conn, "source": "image", "source_image": photo},
    )
    row = conn.execute("SELECT source, source_image FROM translations").fetchone()
    assert row[0] == "image"
    assert bytes(row[1]) == photo


def test_source_image_null_when_capture_has_none(conn):
    """A text / audio capture supplies no image — the column stays NULL (not an
    empty blob), so the serving path can 404 honestly."""
    AddTranslationTool().run(
        {"original": "hello", "target_lang": "zh", "translated": "你好"},
        {"db": conn, "source": "text"},
    )
    row = conn.execute("SELECT source_image FROM translations").fetchone()
    assert row[0] is None


def test_explicit_source_lang_is_stored_and_normalized(conn):
    """The translating model reports the source language; it lands on the row —
    the §3.3 direction tag, set the moment the translation is made (not deferred
    to a later detection sweep). An ISO code the model emits ('ja') is normalized
    to the app's one spelling ('Japanese') so it buckets with everything else.
    '寿司' is bare kanji (detect_script gives None), so this proves the agent's
    value is used, not the deterministic fallback."""
    AddTranslationTool().run(
        {"original": "寿司", "source_lang": "ja",
         "target_lang": "zh", "translated": "寿司"},
        {"db": conn},
    )
    row = conn.execute("SELECT source_lang FROM translations").fetchone()
    assert row[0] == "Japanese"


def test_source_lang_falls_back_to_deterministic_script(conn):
    """If the agent omits source_lang, the deterministic script check fills it
    for unambiguous scripts (kana → Japanese); a genuinely ambiguous script
    (bare Latin / kanji) stays NULL for a model sweep to backfill."""
    AddTranslationTool().run(
        {"original": "ラーメン", "target_lang": "zh", "translated": "拉面"},
        {"db": conn},
    )
    AddTranslationTool().run(
        {"original": "café", "target_lang": "zh", "translated": "咖啡"},
        {"db": conn},
    )
    rows = conn.execute(
        "SELECT original, source_lang FROM translations ORDER BY id"
    ).fetchall()
    assert dict(rows) == {"ラーメン": "Japanese", "café": None}


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
