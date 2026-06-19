"""Step 6b verification: drawer → candidate promotion.

Functional gates:
- promote_candidates inserts a row for each (original, target_lang) pair
  whose count crosses the threshold; nothing else
- Re-running is idempotent (upsert by unique key, not duplicated)
- Threshold parameter actually filters
- Seed-data scan produces the expected emergence signal (top items
  occurrence_count >= 3)
- ListCandidatesTool reads the table back, sorted by occurrence_count desc
- Agent end-to-end: "what have I been seeing" → list_candidates call → contents

Drift gates:
- memory capability now houses 5 tools (drawer x2, translation x2, candidate x1)
- agent.py still owns zero product-domain vocabulary — translation AND
  candidate concerns must stay outside it
"""

from __future__ import annotations

import inspect
import sqlite3
import subprocess
import sys

import pytest

from tideline.agent import Agent
from tideline.promotion import (
    auto_promote_cards,
    canonical_word,
    heal_casing_splits,
    promote_candidates,
)
from tideline.runtimes import get_runtime
from tideline.seed import seed_db
from tideline.tools import (
    AddDrawerTool,
    AddTranslationTool,
    ListCandidatesTool,
    ListDrawersTool,
    ListTranslationsTool,
    NoopTool,
    ToolRegistry,
    init_all_tables,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    init_all_tables(c)
    yield c
    c.close()


def _add(conn: sqlite3.Connection, original: str, lang: str, translated: str) -> None:
    conn.execute(
        "INSERT INTO translations (original, target_lang, translated) "
        "VALUES (?, ?, ?)",
        (original, lang, translated),
    )
    conn.commit()


# --- Promotion engine -----------------------------------------------------


def test_empty_db_promotes_nothing(conn):
    assert promote_candidates(conn) == 0
    rows = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()
    assert rows[0] == 0


def test_below_threshold_is_not_promoted(conn):
    _add(conn, "hello", "zh", "你好")
    _add(conn, "hello", "zh", "你好")  # count=2, threshold default 3

    assert promote_candidates(conn) == 0
    rows = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()
    assert rows[0] == 0


def test_at_threshold_creates_candidate(conn):
    for _ in range(3):
        _add(conn, "hello", "zh", "你好")

    n = promote_candidates(conn, threshold=3)
    assert n == 1

    rows = conn.execute(
        "SELECT original, target_lang, translated, occurrence_count FROM candidates"
    ).fetchall()
    assert rows == [("hello", "zh", "你好", 3)]


def test_distinct_pairs_promoted_separately(conn):
    for _ in range(3):
        _add(conn, "hello", "zh", "你好")
    for _ in range(4):
        _add(conn, "thanks", "ja", "ありがとう")

    n = promote_candidates(conn)
    assert n == 2

    rows = conn.execute(
        "SELECT original, occurrence_count FROM candidates "
        "ORDER BY occurrence_count DESC"
    ).fetchall()
    assert rows == [("thanks", 4), ("hello", 3)]


def test_canonical_word_lowercases_except_proper_nouns():
    # shouted common nouns become the lemma
    assert canonical_word("PREMIUM") == "premium"
    assert canonical_word("Premium") == "premium"
    assert canonical_word("ALCOHOL") == "alcohol"
    assert canonical_word("germs") == "germs"
    # likely proper nouns keep their casing
    assert canonical_word("NASA") == "NASA"      # short all-caps acronym
    assert canonical_word("iPhone") == "iPhone"  # internal uppercase
    # no ASCII-cased letters → untouched (CJK / kana)
    assert canonical_word("ラーメン") == "ラーメン"
    assert canonical_word("拉面") == "拉面"
    # idempotent
    assert canonical_word(canonical_word("PREMIUM")) == "premium"


def test_case_variants_merge_into_one_canonical_candidate(conn):
    # The same word met shouting on a sign and typed in lower-case is ONE word:
    # its occasions combine, and it promotes as a single lowercased candidate.
    _add(conn, "PREMIUM", "zh", "高级")
    _add(conn, "PREMIUM", "zh", "高级")
    _add(conn, "Premium", "zh", "高级")  # 3 occasions across two casings

    n = promote_candidates(conn, threshold=3)
    assert n == 1
    rows = conn.execute(
        "SELECT original, occurrence_count FROM candidates"
    ).fetchall()
    assert rows == [("premium", 3)]

    # Evidence links every casing's row (3), case-insensitively.
    ev = conn.execute(
        "SELECT COUNT(*) FROM candidate_evidence ce JOIN candidates c "
        "ON ce.candidate_id = c.id WHERE c.original = 'premium'"
    ).fetchone()
    assert ev[0] == 3


# --- Casing heal-in-place migration (heal_casing_splits) ------------------
# An older, pre-canonical build promoted the same word under two casings as
# two candidates and two review cards. The heal folds them onto one canonical
# row, carrying the strongest review progress forward — the lossless
# alternative to a clean install. These tests hand-build that legacy state
# (current promote can't produce it — it canonicalizes).


def _seed_legacy_split(conn) -> None:
    """Two casing variants of one word, as old code left them: 'PREMIUM'
    (strength 3, 5 reviews) and 'Premium' (strength 1, 1 review), each its own
    candidate + card, with the drawer rows behind them (3 distinct occasions)."""
    for sess, original in (("s1", "PREMIUM"), ("s2", "PREMIUM"), ("s3", "Premium")):
        conn.execute(
            "INSERT INTO translations (original, target_lang, translated, session_id) "
            "VALUES (?, 'zh', '高级', ?)",
            (original, sess),
        )
    conn.executescript(
        """
        INSERT INTO candidates (id, original, target_lang, translated,
            occurrence_count, first_seen_at, last_seen_at)
          VALUES (1, 'PREMIUM', 'zh', '高级', 2, '2026-01-01', '2026-01-02'),
                 (2, 'Premium', 'zh', '高级', 1, '2026-01-03', '2026-01-03');
        INSERT INTO cards (candidate_id, original, target_lang, translated,
            state, strength, reviews)
          VALUES (1, 'PREMIUM', 'zh', '高级', 'active', 3, 5),
                 (2, 'Premium', 'zh', '高级', 'active', 1, 1);
        """
    )
    conn.commit()


def test_heal_collapses_casing_split_into_one_canonical(conn):
    _seed_legacy_split(conn)
    assert heal_casing_splits(conn) == 1  # one duplicate candidate removed

    # one canonical candidate, one card, carrying the STRONGEST progress
    assert conn.execute("SELECT original FROM candidates").fetchall() == [("premium",)]
    assert conn.execute(
        "SELECT original, state, strength, reviews FROM cards"
    ).fetchall() == [("premium", "active", 3, 5)]

    # promote then re-derives the merged occasions + evidence on the survivor
    promote_candidates(conn)
    auto_promote_cards(conn)
    assert conn.execute(
        "SELECT original, occurrence_count FROM candidates"
    ).fetchone() == ("premium", 3)
    assert conn.execute("SELECT COUNT(*) FROM candidate_evidence").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1


def test_heal_folds_onto_existing_canonical_row(conn):
    # The realistic boot order: a new sweep already made the canonical
    # 'premium' (fresh, strength 0); a leftover 'PREMIUM' from the old build
    # still carries the review progress. Fold onto the canonical one, inherit
    # the stronger progress.
    conn.executescript(
        """
        INSERT INTO candidates (id, original, target_lang, translated,
            occurrence_count, first_seen_at, last_seen_at)
          VALUES (1, 'premium', 'zh', '高级', 3, '2026-01-01', '2026-01-05'),
                 (2, 'PREMIUM', 'zh', '高级', 2, '2026-01-01', '2026-01-02');
        INSERT INTO cards (candidate_id, original, target_lang, translated,
            state, strength, reviews)
          VALUES (1, 'premium', 'zh', '高级', 'active', 0, 0),
                 (2, 'PREMIUM', 'zh', '高级', 'active', 4, 6);
        """
    )
    conn.commit()

    assert heal_casing_splits(conn) == 1
    assert conn.execute("SELECT id, original FROM candidates").fetchall() == [(1, "premium")]
    # survivor is the canonical row (id 1), now wearing the leftover's progress
    assert conn.execute(
        "SELECT candidate_id, strength, reviews FROM cards"
    ).fetchall() == [(1, 4, 6)]


def test_heal_keeps_active_if_any_variant_active(conn):
    _seed_legacy_split(conn)
    conn.execute("UPDATE cards SET state = 'sunk' WHERE candidate_id = 2")
    conn.commit()
    heal_casing_splits(conn)
    # one casing was sunk, the other kept — the merged word stays active
    assert conn.execute("SELECT state FROM cards").fetchone() == ("active",)


def test_heal_keeps_sunk_when_all_variants_sunk(conn):
    _seed_legacy_split(conn)
    conn.execute("UPDATE cards SET state = 'sunk'")
    conn.commit()
    heal_casing_splits(conn)
    # the user buried both casings — don't resurface the merged word
    assert conn.execute("SELECT state FROM cards").fetchone() == ("sunk",)


def test_heal_is_noop_and_idempotent_on_clean_db(conn):
    for _ in range(3):
        _add(conn, "hello", "zh", "你好")
    promote_candidates(conn)
    auto_promote_cards(conn)
    before = conn.execute("SELECT original, strength FROM cards").fetchall()

    assert heal_casing_splits(conn) == 0      # nothing to heal
    assert heal_casing_splits(conn) == 0      # idempotent
    assert conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] == 1
    assert conn.execute("SELECT original, strength FROM cards").fetchall() == before


def test_promotion_is_idempotent_on_second_run(conn):
    for _ in range(3):
        _add(conn, "hello", "zh", "你好")

    promote_candidates(conn)
    promote_candidates(conn)  # second run must not duplicate

    rows = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()
    assert rows[0] == 1


def test_promotion_updates_count_when_drawer_grows(conn):
    for _ in range(3):
        _add(conn, "hello", "zh", "你好")
    promote_candidates(conn)

    for _ in range(2):
        _add(conn, "hello", "zh", "你好")
    promote_candidates(conn)

    rows = conn.execute(
        "SELECT occurrence_count FROM candidates WHERE original = ?", ("hello",)
    ).fetchone()
    assert rows[0] == 5


def test_threshold_parameter_filters(conn):
    for _ in range(2):
        _add(conn, "a", "zh", "x")
    for _ in range(4):
        _add(conn, "b", "zh", "y")

    # threshold=2 catches both
    n = promote_candidates(conn, threshold=2)
    assert n == 2

    # Reset and try threshold=4: only "b"
    conn.execute("DELETE FROM candidates")
    conn.commit()
    n = promote_candidates(conn, threshold=4)
    assert n == 1
    row = conn.execute("SELECT original FROM candidates").fetchone()
    assert row[0] == "b"


def test_threshold_zero_is_rejected(conn):
    with pytest.raises(ValueError):
        promote_candidates(conn, threshold=0)


# --- Promotion against seed data (the load-bearing one) ------------------


def test_seed_data_promotes_expected_emergence_set(conn):
    """The whole point: seed → promote should surface the frequent terms.

    Seed assertion guaranteed >= 10 originals with count >= 3, so the same
    promotion run must yield >= 10 candidate rows.
    """
    seed_db(conn)
    n = promote_candidates(conn, threshold=3)
    assert n >= 10

    rows = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()
    assert rows[0] >= 10

    # All promoted candidates must have count >= threshold
    bad = conn.execute(
        "SELECT original, occurrence_count FROM candidates WHERE occurrence_count < 3"
    ).fetchall()
    assert not bad, f"sub-threshold rows leaked into candidates: {bad}"


def test_seed_threshold_5_keeps_only_frequent_terms(conn):
    """Raising threshold to 5 should isolate the 'frequent' tier."""
    seed_db(conn)
    n = promote_candidates(conn, threshold=5)
    # Frequent tier appears 4-6 times; ~half will hit 5+. Conservative bound:
    # at least a few, but strictly fewer than the threshold=3 count.
    n_lower = conn.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM translations "
        "GROUP BY original, target_lang HAVING COUNT(*) >= 3)"
    ).fetchone()[0]
    assert 0 < n < n_lower


# --- ListCandidatesTool --------------------------------------------------


def test_list_candidates_empty(conn):
    assert ListCandidatesTool().run({}, {"db": conn}) == "no candidates yet"


def test_list_candidates_sorted_by_count_desc(conn):
    for _ in range(3):
        _add(conn, "hello", "zh", "你好")
    for _ in range(5):
        _add(conn, "thanks", "ja", "ありがとう")
    promote_candidates(conn)

    out = ListCandidatesTool().run({}, {"db": conn})
    lines = out.splitlines()

    # thanks (5x) must come before hello (3x)
    assert "thanks" in lines[0]
    assert "[seen 5x]" in lines[0]
    assert "hello" in lines[1]
    assert "[seen 3x]" in lines[1]


# --- Drift gates ----------------------------------------------------------


def test_drift_memory_capability_now_houses_five_tools():
    registry = ToolRegistry()
    registry.register(AddDrawerTool)
    registry.register(ListDrawersTool)
    registry.register(AddTranslationTool)
    registry.register(ListTranslationsTool)
    registry.register(ListCandidatesTool)

    memory_tools = registry.get_by_capability("memory")
    assert len(memory_tools) == 5
    assert ListCandidatesTool in memory_tools


def test_drift_agent_has_no_candidate_or_translation_knowledge():
    """agent.py must contain no product-domain vocabulary. Translation already
    proven absent in Step 5; this gate extends to candidate/promotion."""
    import tideline.agent

    source = inspect.getsource(tideline.agent).lower()
    forbidden = [
        "translate", "translation", "target_lang",
        "candidate", "promote", "promotion", "emergence",
    ]
    found = [t for t in forbidden if t in source]
    assert not found, (
        f"agent.py contains product-domain tokens {found}; semantics belong "
        f"in CLI system message + tool descriptions, not the agent."
    )


# --- Agent end-to-end via Mock -------------------------------------------


def test_agent_surfaces_candidates_when_user_asks(conn):
    seed_db(conn)
    promote_candidates(conn)

    registry = ToolRegistry()
    registry.register(NoopTool)
    registry.register(AddDrawerTool)
    registry.register(ListDrawersTool)
    registry.register(AddTranslationTool)
    registry.register(ListTranslationsTool)
    registry.register(ListCandidatesTool)
    agent = Agent(get_runtime("mock"), registry=registry, context={"db": conn})

    result = agent.run("what have I been seeing lately?")

    # Should contain a few of the frequent-tier terms from the Tokyo trip seed
    candidate_terms = ["ラーメン", "駅", "刺身", "天ぷら", "餃子"]
    hits = [t for t in candidate_terms if t in result]
    assert len(hits) >= 2, (
        f"expected frequent-tier terms in candidates output, got: {result}"
    )


# --- CLI smoke ------------------------------------------------------------


def test_cli_promotion_runs(tmp_path):
    db_path = tmp_path / "test.db"
    subprocess.run(
        [sys.executable, "-m", "tideline.seed", "--db", str(db_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "tideline.promotion", "--db", str(db_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Promoted" in result.stdout

    conn = sqlite3.connect(str(db_path))
    n = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    conn.close()
    assert n >= 10


def test_cli_promotion_threshold_flag(tmp_path):
    db_path = tmp_path / "test.db"
    subprocess.run(
        [sys.executable, "-m", "tideline.seed", "--db", str(db_path)],
        capture_output=True,
        text=True,
        check=True,
    )

    result = subprocess.run(
        [
            sys.executable, "-m", "tideline.promotion",
            "--db", str(db_path), "--threshold", "5",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "threshold=5" in result.stdout


# test_cli_list_candidates_smoke + test_cli_step1_through_5_smoke_unchanged
# removed 2026-05-11: the CLI no longer routes natural-language queries
# like "what have I been seeing lately?" — that's the UI's job to read from
# SQL directly. The agent-bench harness keeps a custom registry that covers
# ListCandidatesTool's agent-loop behavior in isolation.
