"""source_lang backfill sweep — deterministic-first, budgeted model fallback."""

from __future__ import annotations

import sqlite3

from tideline.runtime import ModelRuntime
from tideline.tagging import tag_native_glosses, tag_source_langs
from tideline.tools import init_all_tables


class _AlwaysFrench(ModelRuntime):
    def generate(self, prompt: str) -> str:
        return "French"


class _AlwaysGloss(ModelRuntime):
    def __init__(self, gloss: str = "译") -> None:
        self._gloss = gloss

    def generate(self, prompt: str) -> str:
        return self._gloss


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


# --- native_gloss backfill -----------------------------------------------


def test_gloss_fills_eligible_rows():
    conn = _conn()
    _add(conn, "ラーメン", source_lang="Japanese", target="English")
    stats = tag_native_glosses(conn, _AlwaysGloss("拉面"), "Chinese")
    assert stats["glossed"] == 1
    got = conn.execute(
        "SELECT native_gloss FROM translations WHERE original='ラーメン'"
    ).fetchone()[0]
    assert got == "拉面"


def test_gloss_skips_when_target_is_native():
    conn = _conn()
    _add(conn, "ramen", source_lang="Japanese", target="Chinese")  # target IS native
    stats = tag_native_glosses(conn, _AlwaysGloss(), "Chinese")
    assert stats["glossed"] == 0


def test_gloss_skips_when_source_is_native():
    conn = _conn()
    _add(conn, "合同", source_lang="Chinese", target="English")  # source IS native
    stats = tag_native_glosses(conn, _AlwaysGloss(), "Chinese")
    assert stats["glossed"] == 0


def test_gloss_one_model_call_per_distinct_term():
    conn = _conn()
    for _ in range(4):
        _add(conn, "ラーメン", source_lang="Japanese", target="English")

    calls = {"n": 0}

    class _Counting(ModelRuntime):
        def generate(self, prompt: str) -> str:
            calls["n"] += 1
            return "拉面"

    stats = tag_native_glosses(conn, _Counting(), "Chinese")
    assert calls["n"] == 1  # one model call for the distinct term
    assert stats["glossed"] == 4  # applied to all four rows


def test_gloss_respects_budget():
    conn = _conn()
    for w in ("ラーメン", "すし", "うどん"):
        _add(conn, w, source_lang="Japanese", target="English")
    stats = tag_native_glosses(conn, _AlwaysGloss("译"), "Chinese", budget=2)
    assert stats["terms"] == 2
    assert stats["remaining"] == 1


def test_gloss_idempotent():
    conn = _conn()
    _add(conn, "ラーメン", source_lang="Japanese", target="English")
    tag_native_glosses(conn, _AlwaysGloss("拉面"), "Chinese")
    stats = tag_native_glosses(conn, _AlwaysGloss("拉面"), "Chinese")
    assert stats["glossed"] == 0


def test_gloss_mock_echo_writes_nothing():
    # The real mock is a stub, not a translator: its echo of the gloss prompt
    # runs well past the headword length cap, so a mock-runtime sweep writes no
    # junk glosses. (This is why gloss quality genuinely needs a real model.)
    from tideline.runtimes import get_runtime

    conn = _conn()
    _add(conn, "ラーメン", source_lang="Japanese", target="English")
    stats = tag_native_glosses(conn, get_runtime("mock"), "Chinese")
    assert stats["glossed"] == 0
    got = conn.execute(
        "SELECT native_gloss FROM translations WHERE original='ラーメン'"
    ).fetchone()[0]
    assert got is None
