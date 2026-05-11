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
from tideline.promotion import promote_candidates
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

    # Should contain a few of the frequent-tier terms from the seed
    candidate_terms = ["ラーメン", "beurre", "amor", "合同", "Datenbank"]
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


def test_cli_list_candidates_smoke(tmp_path):
    """End-to-end: seed → promote → ask the agent → see top emergent terms."""
    db_path = tmp_path / "test.db"
    subprocess.run(
        [sys.executable, "-m", "tideline.seed", "--db", str(db_path)],
        capture_output=True, text=True, check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "tideline.promotion", "--db", str(db_path)],
        capture_output=True, text=True, check=True,
    )
    result = subprocess.run(
        [
            sys.executable, "-m", "tideline.cli",
            "--runtime", "mock", "--db", str(db_path),
            "what have I been seeing lately?",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "[seen" in result.stdout  # at least one candidate line surfaced


def test_cli_step1_through_5_smoke_unchanged_after_step6b():
    """All earlier behaviors must survive Step 6b's new candidate tool."""
    def _cli(*extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable, "-m", "tideline.cli",
                "--runtime", "mock", "--db", ":memory:",
                *extra,
            ],
            capture_output=True, text=True,
        )

    assert _cli("hello").stdout.strip() == "[mock] echo: hello"
    assert _cli("please run noop").stdout.strip() == "noop done"
    assert _cli("remember: cli smoke").stdout.strip() == "drawer #1 added"
    assert "[mock-translated to zh] hello" in _cli("translate hello to zh").stdout
