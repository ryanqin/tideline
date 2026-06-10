"""Episodic anchoring verification (DESIGN.md §3.2).

Each promoted candidate must retain a back-reference to every translation
row that contributed to it — so the UI can surface a candidate as a stack
of lived moments rather than a bare count.

Functional gates:
- `translations` table carries source / context_snippet / session_id columns
- `AddTranslationTool` accepts these as optional args and persists them
- `candidate_evidence` table exists, gets populated by promote_candidates,
  one row per contributing translation
- Evidence is idempotent across re-runs (UNIQUE constraint holds)
- Evidence preserves correct back-references (candidate ↔ its translations)

Drift gates:
- Pre-existing v0 schema (no episodic columns) is auto-migrated by init_db
- Translations without the new fields still work (columns are NULL-able)
"""

from __future__ import annotations

import sqlite3

import pytest

from tideline.promotion import promote_candidates
from tideline.tools import AddTranslationTool, init_all_tables


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    init_all_tables(c)
    yield c
    c.close()


# --- translations table carries the new columns --------------------------


def test_translations_schema_has_episodic_columns(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(translations)")}
    assert "source" in cols
    assert "context_snippet" in cols
    assert "session_id" in cols
    assert "source_image" in cols  # the kept capture photo (§3.2 recall material)


def test_init_db_migrates_legacy_schema():
    """A pre-existing translations table without the new columns should be
    upgraded automatically when init_db runs again."""
    c = sqlite3.connect(":memory:")
    # Manually create the OLD schema (no episodic columns)
    c.execute(
        """
        CREATE TABLE translations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original TEXT NOT NULL,
            target_lang TEXT NOT NULL,
            translated TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    c.execute(
        "INSERT INTO translations (original, target_lang, translated) "
        "VALUES (?, ?, ?)",
        ("hello", "zh", "你好"),
    )
    c.commit()

    init_all_tables(c)

    cols = {row[1] for row in c.execute("PRAGMA table_info(translations)")}
    assert "source" in cols
    assert "context_snippet" in cols
    assert "session_id" in cols
    assert "source_image" in cols

    # Legacy row survives, new columns NULL
    row = c.execute(
        "SELECT original, source, context_snippet, session_id, source_image "
        "FROM translations"
    ).fetchone()
    assert row == ("hello", None, None, None, None)
    c.close()


# --- AddTranslationTool persists new fields ------------------------------


def test_add_translation_persists_optional_context(conn):
    AddTranslationTool().run(
        {
            "original": "ラーメン",
            "target_lang": "English",
            "translated": "ramen",
            "source": "image",
            "context_snippet": "とんこつラーメン 850円",
            "session_id": "tokyo-trip-2026-04",
        },
        {"db": conn},
    )
    row = conn.execute(
        "SELECT source, context_snippet, session_id FROM translations"
    ).fetchone()
    assert row == ("image", "とんこつラーメン 850円", "tokyo-trip-2026-04")


def test_add_translation_works_without_optional_context(conn):
    """Backward-compatible: minimal args (original/target_lang/translated) still work."""
    AddTranslationTool().run(
        {"original": "hello", "target_lang": "zh", "translated": "你好"},
        {"db": conn},
    )
    row = conn.execute(
        "SELECT source, context_snippet, session_id FROM translations"
    ).fetchone()
    assert row == (None, None, None)


# --- candidate_evidence table exists -------------------------------------


def test_candidate_evidence_table_exists(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='candidate_evidence'"
    ).fetchall()
    assert len(rows) == 1


def test_candidate_evidence_indexed_for_candidate_lookup(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='candidate_evidence'"
    ).fetchall()
    names = {r[0] for r in rows}
    assert any("candidate" in n for n in names), f"no candidate-lookup index: {names}"


# --- promote_candidates writes evidence ---------------------------------


def _add(conn: sqlite3.Connection, original: str, lang: str, translated: str) -> int:
    cursor = conn.execute(
        "INSERT INTO translations (original, target_lang, translated) "
        "VALUES (?, ?, ?)",
        (original, lang, translated),
    )
    conn.commit()
    return cursor.lastrowid


def test_promotion_writes_evidence_for_each_contributing_translation(conn):
    ids = [_add(conn, "hello", "zh", "你好") for _ in range(3)]
    promote_candidates(conn)

    cand_id = conn.execute(
        "SELECT id FROM candidates WHERE original = ?", ("hello",)
    ).fetchone()[0]

    evidence_ids = [
        row[0]
        for row in conn.execute(
            "SELECT translation_id FROM candidate_evidence WHERE candidate_id = ? "
            "ORDER BY translation_id",
            (cand_id,),
        )
    ]
    assert evidence_ids == ids


def test_promotion_evidence_is_idempotent_on_rerun(conn):
    """Re-running promote_candidates must not duplicate evidence rows."""
    for _ in range(3):
        _add(conn, "hello", "zh", "你好")

    promote_candidates(conn)
    first_count = conn.execute("SELECT COUNT(*) FROM candidate_evidence").fetchone()[0]

    promote_candidates(conn)
    second_count = conn.execute("SELECT COUNT(*) FROM candidate_evidence").fetchone()[0]

    assert first_count == second_count == 3


def test_promotion_evidence_grows_when_new_translations_arrive(conn):
    """Adding more translations + re-promoting must extend evidence, not replace it."""
    for _ in range(3):
        _add(conn, "hello", "zh", "你好")
    promote_candidates(conn)
    initial_count = conn.execute(
        "SELECT COUNT(*) FROM candidate_evidence"
    ).fetchone()[0]
    assert initial_count == 3

    # Three more sightings of the same pair
    for _ in range(3):
        _add(conn, "hello", "zh", "你好")
    promote_candidates(conn)

    new_count = conn.execute("SELECT COUNT(*) FROM candidate_evidence").fetchone()[0]
    assert new_count == 6   # all six translations now linked


def test_promotion_evidence_isolates_candidates(conn):
    """Two distinct candidates should not share each other's evidence."""
    hello_ids = [_add(conn, "hello", "zh", "你好") for _ in range(3)]
    thanks_ids = [_add(conn, "thanks", "ja", "ありがとう") for _ in range(3)]
    promote_candidates(conn)

    cand_rows = {
        original: cand_id
        for original, cand_id in conn.execute(
            "SELECT original, id FROM candidates"
        ).fetchall()
    }

    hello_evidence = {
        row[0] for row in conn.execute(
            "SELECT translation_id FROM candidate_evidence WHERE candidate_id = ?",
            (cand_rows["hello"],),
        )
    }
    thanks_evidence = {
        row[0] for row in conn.execute(
            "SELECT translation_id FROM candidate_evidence WHERE candidate_id = ?",
            (cand_rows["thanks"],),
        )
    }

    assert hello_evidence == set(hello_ids)
    assert thanks_evidence == set(thanks_ids)
    assert hello_evidence.isdisjoint(thanks_evidence)


def test_promotion_evidence_links_to_real_translation_rows(conn):
    """Every translation_id in candidate_evidence must reference a real translation."""
    for _ in range(3):
        _add(conn, "hello", "zh", "你好")
    promote_candidates(conn)

    orphans = conn.execute(
        """
        SELECT ce.translation_id FROM candidate_evidence ce
        LEFT JOIN translations t ON t.id = ce.translation_id
        WHERE t.id IS NULL
        """
    ).fetchall()
    assert not orphans, f"orphan evidence rows: {orphans}"


def test_promotion_with_seed_data_attaches_evidence_to_every_candidate(conn):
    """End-to-end: seed produces ~120 translations, promotion to >= 10 candidates
    each of which carries >= 3 evidence rows (the threshold)."""
    from tideline.seed import seed_db

    seed_db(conn)
    promote_candidates(conn)

    cand_counts = conn.execute(
        """
        SELECT c.occurrence_count, COUNT(ce.translation_id)
        FROM candidates c
        LEFT JOIN candidate_evidence ce ON ce.candidate_id = c.id
        GROUP BY c.id
        """
    ).fetchall()

    assert cand_counts, "no candidates produced from seed"
    for occurrence_count, evidence_count in cand_counts:
        assert evidence_count == occurrence_count, (
            f"candidate occurrence_count={occurrence_count} but evidence={evidence_count} "
            f"— evidence should always equal occurrence for fresh promotion"
        )
