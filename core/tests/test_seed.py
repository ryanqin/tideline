"""Step 6a verification: seed data generator.

Functional gates:
- Deterministic given a seed (reproducible across runs)
- Inserts the expected count
- Each scenario contributes its three frequency tiers correctly

Drift gate (the load-bearing one):
- Seed data MUST contain enough repetition patterns for emergence
  detection (Step 6b) to find. Without this, candidate promotion has
  nothing to find and the entire emergence story is hollow.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime

import pytest

from tideline.seed import SCENARIOS, generate_entries, seed_db
from tideline.tools import init_all_tables


_FIXED_NOW = datetime(2026, 5, 9, 12, 0, 0)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    init_all_tables(c)
    yield c
    c.close()


# --- Determinism ----------------------------------------------------------


def test_generate_entries_is_deterministic_with_seed():
    a = generate_entries(seed=42, now=_FIXED_NOW)
    b = generate_entries(seed=42, now=_FIXED_NOW)
    assert a == b


def test_different_seeds_produce_different_orderings():
    a = generate_entries(seed=42, now=_FIXED_NOW)
    b = generate_entries(seed=99, now=_FIXED_NOW)
    assert a != b


# --- Repetition pattern correctness --------------------------------------


def test_frequent_terms_appear_4_to_6_times():
    entries = generate_entries(seed=42)
    counts = Counter(e[0] for e in entries)

    # Frequent terms of the Tokyo trip (all originals — the foreign source a
    # Chinese-first user meets on menus and signs).
    for term in ("ラーメン", "刺身", "天ぷら", "駅"):
        assert 4 <= counts[term] <= 6, (
            f"Frequent term {term!r} should appear 4-6 times, got {counts[term]}"
        )


def test_occasional_terms_appear_2_to_3_times():
    entries = generate_entries(seed=42)
    counts = Counter(e[0] for e in entries)

    for term in ("焼き鳥", "枝豆", "わさび", "海鮮丼"):
        assert 2 <= counts[term] <= 3, (
            f"Occasional term {term!r} should appear 2-3 times, got {counts[term]}"
        )


def test_rare_terms_appear_exactly_once():
    entries = generate_entries(seed=42)
    counts = Counter(e[0] for e in entries)

    for term in ("いらっしゃいませ", "お会計", "つけ麺", "生ビール", "切符"):
        assert counts[term] == 1, (
            f"Rare term {term!r} should appear once, got {counts[term]}"
        )


# --- Drift gate: emergence has fuel --------------------------------------


def test_seed_data_has_emergence_signal(conn):
    """Load-bearing: seed must produce repetition for >= 10 originals.

    Without enough multi-occurrence patterns, Step 6b's candidate promotion
    finds nothing. The Tokyo trip's frequent (4-6x) and occasional (2-3x)
    tiers give ten recurring terms — fuel for promotion + clustering.
    """
    seed_db(conn)

    rows = conn.execute(
        "SELECT original, COUNT(*) AS c FROM translations "
        "GROUP BY original HAVING c >= 2 ORDER BY c DESC"
    ).fetchall()

    assert len(rows) >= 10, (
        f"Need >= 10 originals with >= 2 occurrences for emergence; got {len(rows)}: {rows}"
    )


def test_seed_db_count_matches_generate(conn):
    inserted = seed_db(conn)
    rows = conn.execute("SELECT COUNT(*) FROM translations").fetchone()
    assert rows[0] == inserted
    assert inserted > 30  # one focused trip, ~40 captures


def test_seed_each_capture_is_one_foreign_language_into_chinese(conn):
    """The §3.3 unit is a single lived moment in a single foreign language,
    translated INTO the user's first language (Chinese). The drawer may hold
    *several* trips in different languages (Tokyo in Japanese, Paris in French)
    — that multiplicity is exactly what the by-language lens shows — but no
    single capture session mixes languages, and nothing is translated FROM
    Chinese (you don't translate your own language)."""
    seed_db(conn)

    # Several foreign source languages coexist (several trips), never the
    # user's own first language as a source.
    source_langs = {
        r[0] for r in conn.execute("SELECT DISTINCT source_lang FROM translations")
    }
    assert source_langs == {"Japanese", "French"}, source_langs
    assert "Chinese" not in source_langs

    # Everything is translated INTO the user's first language (Chinese).
    assert conn.execute(
        "SELECT DISTINCT target_lang FROM translations"
    ).fetchall() == [("Chinese",)]

    # Each capture session is monolingual — a single remembered moment is one
    # language (the §3.3 unit; the by-language split lives across sessions).
    mixed = conn.execute(
        "SELECT session_id FROM translations "
        "GROUP BY session_id HAVING COUNT(DISTINCT source_lang) > 1"
    ).fetchall()
    assert mixed == [], mixed


# --- CLI ------------------------------------------------------------------


def test_cli_seed_runs(tmp_path):
    db_path = tmp_path / "test.db"
    result = subprocess.run(
        [sys.executable, "-m", "tideline.seed", "--db", str(db_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Seeded" in result.stdout

    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
    conn.close()
    assert count > 30


def test_cli_seed_clear_flag(tmp_path):
    """--clear should empty the table before reseeding."""
    db_path = tmp_path / "test.db"

    # First seed
    subprocess.run(
        [sys.executable, "-m", "tideline.seed", "--db", str(db_path)],
        capture_output=True,
        text=True,
        check=True,
    )

    # Second seed without --clear should double the count
    subprocess.run(
        [sys.executable, "-m", "tideline.seed", "--db", str(db_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    conn = sqlite3.connect(str(db_path))
    doubled = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
    conn.close()

    # Now seed with --clear — should reset to single count
    subprocess.run(
        [sys.executable, "-m", "tideline.seed", "--db", str(db_path), "--clear"],
        capture_output=True,
        text=True,
        check=True,
    )
    conn = sqlite3.connect(str(db_path))
    after_clear = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
    conn.close()

    assert doubled > after_clear
    assert after_clear == doubled // 2


# --- source language (closed-loop A, step 2 labeling) --------------------


def test_seed_sets_source_language(conn):
    seed_db(conn)
    # scenario default → Japanese (the menus and signs)
    assert conn.execute(
        "SELECT DISTINCT source_lang FROM translations WHERE original='ラーメン'"
    ).fetchall() == [("Japanese",)]


def test_seed_has_same_language_synonyms_for_concept_fusion(conn):
    """Two different Japanese words that land on the same first-language word
    are seeded so the within-language concept fusion (§3.3) has something to
    cluster: 中華そば and ラーメン both → 拉面, both Japanese."""
    seed_db(conn)
    rows = conn.execute(
        "SELECT DISTINCT original, source_lang FROM translations "
        "WHERE translated = '拉面' ORDER BY original"
    ).fetchall()
    originals = {r[0] for r in rows}
    assert {"ラーメン", "中華そば"} <= originals, originals
    assert {r[1] for r in rows} == {"Japanese"}  # one language-pair


def test_seed_french_trip_has_same_language_synonyms_for_concept_fusion(conn):
    """The Paris trip mirrors the fusion within French: addition and facture
    both → 账单, both French, so within-language fusion is demonstrated in a
    second language too (and exercises the Latin-script source-lang path)."""
    seed_db(conn)
    rows = conn.execute(
        "SELECT DISTINCT original, source_lang FROM translations "
        "WHERE translated = '账单' ORDER BY original"
    ).fetchall()
    originals = {r[0] for r in rows}
    assert {"addition", "facture"} <= originals, originals
    assert {r[1] for r in rows} == {"French"}  # one language-pair


def test_seed_same_native_word_from_two_languages_stays_separate(conn):
    """A native word reached from two languages must NOT collapse into one
    language-pair (§3.3): 茶 is reached from both お茶 (Japanese) and thé
    (French). They share the translated word but differ in source language —
    the by-language lens depends on them staying distinct."""
    seed_db(conn)
    rows = conn.execute(
        "SELECT DISTINCT original, source_lang FROM translations "
        "WHERE translated = '茶' ORDER BY source_lang"
    ).fetchall()
    by_lang = {r[1]: r[0] for r in rows}
    assert by_lang.get("Japanese") == "お茶"
    assert by_lang.get("French") == "thé"
