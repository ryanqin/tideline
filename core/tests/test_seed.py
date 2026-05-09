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

    # Sample frequent terms across scenarios
    for term in ("ラーメン", "beurre", "amor", "合同", "Datenbank"):
        assert 4 <= counts[term] <= 6, (
            f"Frequent term {term!r} should appear 4-6 times, got {counts[term]}"
        )


def test_occasional_terms_appear_2_to_3_times():
    entries = generate_entries(seed=42)
    counts = Counter(e[0] for e in entries)

    for term in ("駅", "crème", "dolor", "提案", "Server"):
        assert 2 <= counts[term] <= 3, (
            f"Occasional term {term!r} should appear 2-3 times, got {counts[term]}"
        )


def test_rare_terms_appear_exactly_once():
    entries = generate_entries(seed=42)
    counts = Counter(e[0] for e in entries)

    for term in ("お会計", "préchauffer", "siempre", "签字", "Versionskontrolle"):
        assert counts[term] == 1, (
            f"Rare term {term!r} should appear once, got {counts[term]}"
        )


# --- Drift gate: emergence has fuel --------------------------------------


def test_seed_data_has_emergence_signal(conn):
    """Load-bearing: seed must produce >= 3 occurrences for >= 10 originals.

    Without enough multi-occurrence patterns, Step 6b's candidate promotion
    finds nothing. This test confirms the seed generator's data is
    structurally sufficient for the next step.
    """
    seed_db(conn)

    rows = conn.execute(
        "SELECT original, COUNT(*) AS c FROM translations "
        "GROUP BY original HAVING c >= 3 ORDER BY c DESC"
    ).fetchall()

    assert len(rows) >= 10, (
        f"Need >= 10 originals with >= 3 occurrences for emergence; got {len(rows)}: {rows}"
    )


def test_seed_db_count_matches_generate(conn):
    inserted = seed_db(conn)
    rows = conn.execute("SELECT COUNT(*) FROM translations").fetchone()
    assert rows[0] == inserted
    assert inserted > 100


def test_seed_data_spans_multiple_source_languages(conn):
    """We expect Japanese, French, Spanish, Chinese, German originals — five
    distinct script families to make the demo visually convincing."""
    seed_db(conn)

    originals = conn.execute("SELECT DISTINCT original FROM translations").fetchall()
    text = " ".join(r[0] for r in originals)

    # crude script presence checks
    has_japanese = any("ラ" in r[0] or "寿" in r[0] for r in originals)
    has_chinese = any("会议" in r[0] or "合同" in r[0] for r in originals)
    has_french = any("beurre" == r[0] or "œuf" == r[0] for r in originals)
    has_spanish = any("amor" == r[0] for r in originals)
    has_german = any("Datenbank" == r[0] for r in originals)

    assert has_japanese, "Missing Japanese-script source terms"
    assert has_chinese, "Missing Chinese-script source terms"
    assert has_french, "Missing French source terms"
    assert has_spanish, "Missing Spanish source terms"
    assert has_german, "Missing German source terms"


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
    assert count > 100


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
