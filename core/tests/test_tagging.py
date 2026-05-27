"""source_lang backfill sweep — deterministic-first, budgeted model fallback."""

from __future__ import annotations

import sqlite3

from tideline.runtime import ModelRuntime
from tideline.tagging import tag_source_langs
from tideline.tools import init_all_tables


class _AlwaysFrench(ModelRuntime):
    def generate(self, prompt: str) -> str:
        return "French"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_all_tables(conn)
    return conn


def _add(conn, original, translated="x", target="English", source_lang=None):
    conn.execute(
        "INSERT INTO translations (original, target_lang, translated, source_lang, source) "
        "VALUES (?, ?, ?, ?, 'text')",
        (original, target, translated, source_lang),
    )
    conn.commit()


def test_tag_fills_unambiguous_scripts_deterministically_without_model():
    conn = _conn()
    _add(conn, "ラーメン")  # kana → Japanese
    _add(conn, "한국어")     # hangul → Korean
    stats = tag_source_langs(conn, runtime=None)  # no model at all
    assert stats["deterministic"] == 2
    assert stats["via_model"] == 0
    langs = dict(
        conn.execute("SELECT original, source_lang FROM translations").fetchall()
    )
    assert langs == {"ラーメン": "Japanese", "한국어": "Korean"}


def test_tag_han_only_defers_to_model():
    # A bare CJK run is ambiguous (Chinese vs kanji-only Japanese): with no
    # model it stays untagged rather than getting a wrong deterministic guess.
    conn = _conn()
    _add(conn, "合同")
    stats = tag_source_langs(conn, runtime=None)
    assert stats["tagged"] == 0
    assert stats["remaining"] == 1


def test_tag_latin_needs_model():
    conn = _conn()
    _add(conn, "beurre")
    # Without a runtime, Latin stays untagged.
    stats = tag_source_langs(conn, runtime=None)
    assert stats["tagged"] == 0
    assert stats["remaining"] == 1
    # With a model, it gets tagged.
    stats2 = tag_source_langs(conn, runtime=_AlwaysFrench())
    assert stats2["via_model"] == 1
    got = conn.execute(
        "SELECT source_lang FROM translations WHERE original='beurre'"
    ).fetchone()[0]
    assert got == "French"


def test_tag_skips_already_tagged():
    conn = _conn()
    _add(conn, "ラーメン", source_lang="Japanese")  # already tagged
    _add(conn, "すし")  # untagged, kana → Japanese
    stats = tag_source_langs(conn, runtime=None)
    assert stats["deterministic"] == 1  # only the untagged row


def test_tag_respects_model_budget():
    conn = _conn()
    for w in ("beurre", "fromage", "pain", "vin"):  # 4 Latin rows
        _add(conn, w)
    stats = tag_source_langs(conn, runtime=_AlwaysFrench(), budget=2)
    assert stats["via_model"] == 2  # budget caps model tags
    assert stats["remaining"] == 2  # two still untagged this sweep


def test_tag_idempotent_second_sweep_noop():
    conn = _conn()
    _add(conn, "ラーメン")
    tag_source_langs(conn, runtime=None)
    stats = tag_source_langs(conn, runtime=None)
    assert stats["tagged"] == 0  # nothing left untagged
