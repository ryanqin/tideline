"""Tier B cluster engine verification.

The cluster engine accumulates B1 (concept-match) votes into a similarity
graph and produces clusters via Union-Find. Tests cover:

- Schema initialization
- Canonical pair ordering (vote on (5, 3) stored as (3, 5))
- vote_on_pair returns yes/no/None and persists correctly
- compare_pairs picks unvoted within-target_lang pairs
- rebuild_clusters runs Union-Find over yes-votes, produces connected
  components with size >= 2
- Idempotency: re-running rebuild_clusters with same votes is a no-op
- Vote threshold and min_votes parameters filter as documented

Tests use a hand-tuned "AlwaysYes" / "AlwaysNo" runtime instead of Mock
because Mock's _TRANSLATE_RE would interfere with B1 prompts. This lets
us exercise the engine's behavior deterministically without a real LLM.
"""

from __future__ import annotations

import sqlite3

import pytest

from tideline.cluster import (
    _UnionFind,
    _canonical_pair,
    _pending_pairs,
    cluster_sweep,
    compare_pairs,
    init_db,
    name_clusters,
    rebuild_clusters,
    vote_on_pair,
)
from tideline.intelligence import episodic_title
from tideline.runtime import ModelRuntime
from tideline.tools import init_all_tables


class _AlwaysYes(ModelRuntime):
    def generate(self, prompt: str) -> str:
        return "yes"


class _AlwaysNo(ModelRuntime):
    def generate(self, prompt: str) -> str:
        return "no"


class _AlwaysHedged(ModelRuntime):
    def generate(self, prompt: str) -> str:
        return "yes and no, it depends"


class _AlwaysFixedTitle(ModelRuntime):
    def __init__(self, title: str = "your Tokyo lunches") -> None:
        self._title = title

    def generate(self, prompt: str) -> str:
        return self._title


class _AlwaysEmpty(ModelRuntime):
    def generate(self, prompt: str) -> str:
        return "   \n  "


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    init_all_tables(c)
    yield c
    c.close()


def _add_translation(
    c: sqlite3.Connection, original: str, target_lang: str, translated: str
) -> int:
    cursor = c.execute(
        "INSERT INTO translations (original, target_lang, translated) "
        "VALUES (?, ?, ?)",
        (original, target_lang, translated),
    )
    c.commit()
    return cursor.lastrowid


# --- Schema --------------------------------------------------------------


def test_schema_creates_three_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name IN ('pair_similarity_votes', 'clusters', 'cluster_members')"
    ).fetchall()
    names = {r[0] for r in rows}
    assert names == {"pair_similarity_votes", "clusters", "cluster_members"}


def test_init_db_is_idempotent(conn):
    init_db(conn)
    init_db(conn)   # second call must not error
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='pair_similarity_votes'"
    ).fetchall()
    assert len(rows) == 1


def test_votes_table_rejects_inverted_pair_order(conn):
    """The CHECK constraint forbids translation_id_a >= translation_id_b."""
    a = _add_translation(conn, "hello", "zh", "你好")
    b = _add_translation(conn, "world", "zh", "世界")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO pair_similarity_votes "
            "(translation_id_a, translation_id_b, vote) VALUES (?, ?, ?)",
            (b, a, "yes"),   # b > a, so this should fail
        )


def test_canonical_pair_orders_min_first():
    assert _canonical_pair(3, 5) == (3, 5)
    assert _canonical_pair(5, 3) == (3, 5)
    assert _canonical_pair(7, 7) == (7, 7)


# --- vote_on_pair --------------------------------------------------------


def test_vote_on_pair_canonicalizes_storage(conn):
    a = _add_translation(conn, "hello", "zh", "你好")
    b = _add_translation(conn, "world", "zh", "世界")
    vote_on_pair(conn, _AlwaysYes(), b, a, model_label="test")  # reversed

    row = conn.execute(
        "SELECT translation_id_a, translation_id_b, vote "
        "FROM pair_similarity_votes"
    ).fetchone()
    assert row[0] == a    # canonicalized to (a, b) where a < b
    assert row[1] == b
    assert row[2] == "yes"


def test_vote_on_pair_returns_yes_no_none(conn):
    a = _add_translation(conn, "hello", "zh", "你好")
    b = _add_translation(conn, "world", "zh", "世界")
    assert vote_on_pair(conn, _AlwaysYes(), a, b) is True
    c = _add_translation(conn, "foo", "zh", "x")
    assert vote_on_pair(conn, _AlwaysNo(), a, c) is False
    d = _add_translation(conn, "bar", "zh", "y")
    assert vote_on_pair(conn, _AlwaysHedged(), a, d) is None


def test_vote_on_pair_skips_unparseable_response(conn):
    a = _add_translation(conn, "hello", "zh", "你好")
    b = _add_translation(conn, "world", "zh", "世界")
    vote_on_pair(conn, _AlwaysHedged(), a, b)
    rows = conn.execute("SELECT COUNT(*) FROM pair_similarity_votes").fetchone()
    assert rows[0] == 0   # no row inserted


def test_vote_on_pair_returns_none_for_missing_translation(conn):
    a = _add_translation(conn, "hello", "zh", "你好")
    assert vote_on_pair(conn, _AlwaysYes(), a, 9999) is None
    rows = conn.execute("SELECT COUNT(*) FROM pair_similarity_votes").fetchone()
    assert rows[0] == 0


# --- compare_pairs -------------------------------------------------------


def test_compare_pairs_processes_unvoted_pairs_only(conn):
    """Single-vote semantics: with min_votes_per_pair=1 a pair leaves
    the pending set after one vote — that's Phase B1 behavior, still
    valid for callers that want cheap one-shot voting."""
    a = _add_translation(conn, "ramen", "English", "ramen")
    b = _add_translation(conn, "sushi", "English", "sushi")
    c = _add_translation(conn, "tempura", "English", "tempura")

    stats = compare_pairs(conn, _AlwaysYes(), max_pairs=10, min_votes_per_pair=1)
    assert stats["voted"] == 3   # (a,b), (a,c), (b,c)
    assert stats["yes"] == 3

    # Re-run: no new pairs left
    stats2 = compare_pairs(conn, _AlwaysYes(), max_pairs=10, min_votes_per_pair=1)
    assert stats2["voted"] == 0


def test_compare_pairs_skips_cross_target_lang_pairs(conn):
    a = _add_translation(conn, "hello", "English", "hello")
    _add_translation(conn, "ラーメン", "Japanese", "ラーメン")
    _add_translation(conn, "ramen", "English", "ramen")
    _add_translation(conn, "寿司", "Japanese", "寿司")

    # Single-vote semantics so the test measures cross-language skipping,
    # not the multi-vote accumulation loop.
    stats = compare_pairs(conn, _AlwaysYes(), max_pairs=10, min_votes_per_pair=1)
    # Only English-English (1 pair: hello, ramen) and Japanese-Japanese
    # (1 pair: ラーメン, 寿司). Cross-language pairs skipped.
    assert stats["voted"] == 2


def test_compare_pairs_respects_max_pairs(conn):
    for term in ("a", "b", "c", "d", "e"):
        _add_translation(conn, term, "en", term)

    stats = compare_pairs(conn, _AlwaysYes(), max_pairs=3)
    assert stats["voted"] == 3


def test_compare_pairs_counts_unparseable_separately(conn):
    a = _add_translation(conn, "hello", "zh", "你好")
    b = _add_translation(conn, "world", "zh", "世界")
    # Single-vote semantics so the hedged pair leaves the pending set
    # after one attempt. (Under multi-vote default, a hedged pair would
    # stay pending forever — a known limitation since hedged responses
    # don't record a row in pair_similarity_votes.)
    stats = compare_pairs(conn, _AlwaysHedged(), max_pairs=10, min_votes_per_pair=1)
    assert stats["voted"] == 0
    assert stats["unparseable"] == 1


# --- pending_pairs -------------------------------------------------------


def test_pending_pairs_returns_unvoted_within_lang(conn):
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "sushi", "en", "sushi")
    c = _add_translation(conn, "tempura", "en", "tempura")

    # Vote on (a, b)
    vote_on_pair(conn, _AlwaysYes(), a, b)

    pending = _pending_pairs(conn, limit=10)
    assert (a, b) not in pending
    assert (a, c) in pending
    assert (b, c) in pending


# --- rebuild_clusters ----------------------------------------------------


def test_rebuild_clusters_empty_db_produces_no_clusters(conn):
    n = rebuild_clusters(conn)
    assert n == 0
    rows = conn.execute("SELECT COUNT(*) FROM clusters").fetchone()
    assert rows[0] == 0


def test_rebuild_clusters_single_yes_edge_creates_pair(conn):
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "noodle soup", "en", "noodle soup")
    vote_on_pair(conn, _AlwaysYes(), a, b)

    # Single-vote rebuild path (Phase B1 semantics): min_votes=1 explicit.
    n = rebuild_clusters(conn, min_votes=1)
    assert n == 1
    members = conn.execute(
        "SELECT translation_id FROM cluster_members ORDER BY translation_id"
    ).fetchall()
    assert [m[0] for m in members] == [a, b]


def test_rebuild_clusters_transitive_closure(conn):
    """If yes(a,b) and yes(b,c), a-b-c all merge into one cluster."""
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "noodle soup", "en", "noodle soup")
    c = _add_translation(conn, "udon", "en", "udon")
    vote_on_pair(conn, _AlwaysYes(), a, b)
    vote_on_pair(conn, _AlwaysYes(), b, c)
    # a and c never directly voted; transitive union should still merge.

    n = rebuild_clusters(conn, min_votes=1)
    assert n == 1
    members = conn.execute(
        "SELECT translation_id FROM cluster_members ORDER BY translation_id"
    ).fetchall()
    assert [m[0] for m in members] == [a, b, c]


def test_rebuild_clusters_no_votes_no_clusters_even_with_pairs(conn):
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "sushi", "en", "sushi")
    vote_on_pair(conn, _AlwaysNo(), a, b)

    n = rebuild_clusters(conn)
    assert n == 0


def test_rebuild_clusters_separates_disjoint_groups(conn):
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "udon", "en", "udon")
    c = _add_translation(conn, "contract", "en", "contract")
    d = _add_translation(conn, "deal", "en", "deal")
    vote_on_pair(conn, _AlwaysYes(), a, b)
    vote_on_pair(conn, _AlwaysYes(), c, d)
    # NO link between (a,b) and (c,d)

    n = rebuild_clusters(conn, min_votes=1)
    assert n == 2

    cluster_sizes = sorted(
        row[0] for row in conn.execute(
            "SELECT COUNT(*) FROM cluster_members GROUP BY cluster_id"
        )
    )
    assert cluster_sizes == [2, 2]


def test_rebuild_clusters_is_idempotent(conn):
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "udon", "en", "udon")
    vote_on_pair(conn, _AlwaysYes(), a, b)

    rebuild_clusters(conn, min_votes=1)
    first = conn.execute("SELECT COUNT(*) FROM cluster_members").fetchone()[0]
    rebuild_clusters(conn, min_votes=1)
    second = conn.execute("SELECT COUNT(*) FROM cluster_members").fetchone()[0]
    assert first == second == 2


def test_rebuild_clusters_preserves_title_when_membership_unchanged(conn):
    """A rebuild that produces the same connected components must keep
    the existing cluster titles — otherwise every cluster_sweep would
    wipe names and force regeneration (model sampling drift / mock noise
    would corrupt human-readable titles)."""
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "udon", "en", "udon")
    vote_on_pair(conn, _AlwaysYes(), a, b)
    rebuild_clusters(conn, min_votes=1)
    conn.execute("UPDATE clusters SET title = ?", ("your Tokyo lunches",))
    conn.commit()

    # Rebuild without changing votes — title must persist
    rebuild_clusters(conn, min_votes=1)
    row = conn.execute("SELECT title FROM clusters").fetchone()
    assert row[0] == "your Tokyo lunches"


def test_rebuild_clusters_threshold_filters(conn):
    """vote_threshold=0.5 means a pair with 1 yes / 1 no doesn't survive."""
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "sushi", "en", "sushi")
    # Manually insert mixed votes
    conn.execute(
        "INSERT INTO pair_similarity_votes "
        "(translation_id_a, translation_id_b, vote) VALUES (?, ?, 'yes')",
        (a, b),
    )
    conn.execute(
        "INSERT INTO pair_similarity_votes "
        "(translation_id_a, translation_id_b, vote) VALUES (?, ?, 'no')",
        (a, b),
    )
    conn.commit()

    # ratio = 0.5, threshold 0.66 → no edge → no cluster
    n = rebuild_clusters(conn, vote_threshold=0.66, min_votes=1)
    assert n == 0

    # Lower threshold to exactly 0.5 → edge → cluster
    n = rebuild_clusters(conn, vote_threshold=0.5, min_votes=1)
    assert n == 1


def test_rebuild_clusters_min_votes_filters(conn):
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "udon", "en", "udon")
    vote_on_pair(conn, _AlwaysYes(), a, b)

    # min_votes=2 → pair has only 1 vote → no cluster
    n = rebuild_clusters(conn, min_votes=2)
    assert n == 0

    n = rebuild_clusters(conn, min_votes=1)
    assert n == 1


def test_rebuild_rejects_bad_parameters(conn):
    with pytest.raises(ValueError):
        rebuild_clusters(conn, vote_threshold=1.5)
    with pytest.raises(ValueError):
        rebuild_clusters(conn, vote_threshold=-0.1)
    with pytest.raises(ValueError):
        rebuild_clusters(conn, min_votes=0)


# --- UnionFind ----------------------------------------------------------


def test_union_find_basic():
    uf = _UnionFind()
    uf.union(1, 2)
    uf.union(3, 4)
    uf.union(2, 3)
    assert uf.find(1) == uf.find(4)
    assert uf.find(1) != uf.find(99) or 99 not in uf._parent


# --- episodic_title.parse_response --------------------------------------


def test_parse_response_strips_title_prefix():
    assert episodic_title.parse_response("Title: your Tokyo lunches") == "your Tokyo lunches"
    assert episodic_title.parse_response("title - Sunday baking") == "Sunday baking"
    assert episodic_title.parse_response("Episodic Title: a recipe session") == "a recipe session"


def test_parse_response_strips_surrounding_quotes():
    assert episodic_title.parse_response('"your Tokyo lunches"') == "your Tokyo lunches"
    assert episodic_title.parse_response("'Sunday baking session'") == "Sunday baking session"


def test_parse_response_returns_first_line():
    response = "your Tokyo lunches\n\nThis title captures the shared moment."
    assert episodic_title.parse_response(response) == "your Tokyo lunches"


def test_parse_response_handles_empty_and_whitespace():
    assert episodic_title.parse_response("") is None
    assert episodic_title.parse_response("   \n  ") is None


def test_parse_response_caps_runaway_length():
    long = " ".join(["word"] * 30)
    result = episodic_title.parse_response(long)
    assert result is not None
    assert len(result.split()) == 12


# --- name_clusters ------------------------------------------------------


def test_name_clusters_writes_title_to_unnamed_cluster(conn):
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "udon", "en", "udon")
    vote_on_pair(conn, _AlwaysYes(), a, b)
    rebuild_clusters(conn, min_votes=1)

    stats = name_clusters(conn, _AlwaysFixedTitle("your Tokyo lunches"))
    assert stats == {"named": 1, "skipped": 0, "unparseable": 0}

    row = conn.execute("SELECT title FROM clusters").fetchone()
    assert row[0] == "your Tokyo lunches"


def test_name_clusters_does_not_overwrite_existing_titles(conn):
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "udon", "en", "udon")
    vote_on_pair(conn, _AlwaysYes(), a, b)
    rebuild_clusters(conn, min_votes=1)

    name_clusters(conn, _AlwaysFixedTitle("original"))
    stats = name_clusters(conn, _AlwaysFixedTitle("different"))

    assert stats["named"] == 0
    row = conn.execute("SELECT title FROM clusters").fetchone()
    assert row[0] == "original"


def test_name_clusters_safe_on_empty_db(conn):
    stats = name_clusters(conn, _AlwaysFixedTitle())
    assert stats == {"named": 0, "skipped": 0, "unparseable": 0}


def test_name_clusters_counts_unparseable_responses(conn):
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "udon", "en", "udon")
    vote_on_pair(conn, _AlwaysYes(), a, b)
    rebuild_clusters(conn, min_votes=1)

    stats = name_clusters(conn, _AlwaysEmpty())
    assert stats == {"named": 0, "skipped": 0, "unparseable": 1}
    row = conn.execute("SELECT title FROM clusters").fetchone()
    assert row[0] is None


def test_name_clusters_forwards_context_snippet_to_prompt(conn):
    cursor = conn.execute(
        "INSERT INTO translations (original, target_lang, translated, context_snippet) "
        "VALUES (?, ?, ?, ?)",
        ("ラーメン", "en", "ramen", "menu at Ichiran in Shibuya"),
    )
    a = cursor.lastrowid
    cursor = conn.execute(
        "INSERT INTO translations (original, target_lang, translated, context_snippet) "
        "VALUES (?, ?, ?, ?)",
        ("寿司", "en", "sushi", "conveyor sushi, Tokyo"),
    )
    b = cursor.lastrowid
    conn.commit()
    vote_on_pair(conn, _AlwaysYes(), a, b)
    rebuild_clusters(conn, min_votes=1)

    captured: dict[str, str] = {}

    class _Capturer(ModelRuntime):
        def generate(self, prompt: str) -> str:
            captured["prompt"] = prompt
            return "your Tokyo food trip"

    name_clusters(conn, _Capturer())
    assert "Shibuya" in captured["prompt"]
    assert "Tokyo" in captured["prompt"]


# --- cluster_sweep (Phase B3) -------------------------------------------


def test_cluster_sweep_end_to_end_on_seeded_translations(conn):
    """cluster_sweep is the night-watch entry point: vote → rebuild →
    name in one call. With AlwaysYes voting + AlwaysFixedTitle naming
    the seeded translations should collapse into a single cluster with
    the stub title. Single-vote semantics explicit so the test stays
    focused on the pipeline, not the multi-vote default."""
    for term in ("ramen", "udon", "soba"):
        _add_translation(conn, term, "en", term)

    stats = cluster_sweep(
        conn,
        _AlwaysYes(),
        max_pairs=10,
        min_votes_per_pair=1,
    )
    # All three pairs voted yes → one cluster of three members
    assert stats["voted"] == 3
    assert stats["yes"] == 3
    assert stats["clusters"] == 1
    assert stats["named"] == 1

    row = conn.execute("SELECT title FROM clusters").fetchone()
    assert row[0] is not None


def test_cluster_sweep_respects_budget(conn):
    for term in ("a", "b", "c", "d", "e"):
        _add_translation(conn, term, "en", term)

    stats = cluster_sweep(conn, _AlwaysYes(), max_pairs=2)
    assert stats["voted"] == 2


def test_cluster_sweep_safe_on_empty_db(conn):
    stats = cluster_sweep(conn, _AlwaysYes())
    assert stats == {
        "voted": 0, "yes": 0, "no": 0, "unparseable_votes": 0,
        "clusters": 0, "named": 0, "unparseable_names": 0,
    }


def test_cluster_sweep_is_idempotent(conn):
    """Running twice on the same DB must not double-create clusters or
    re-vote already-voted pairs. Single-vote semantics explicit."""
    for term in ("ramen", "udon"):
        _add_translation(conn, term, "en", term)

    first = cluster_sweep(conn, _AlwaysYes(), max_pairs=10, min_votes_per_pair=1)
    second = cluster_sweep(conn, _AlwaysYes(), max_pairs=10, min_votes_per_pair=1)

    assert first["voted"] == 1
    assert second["voted"] == 0   # no unvoted pairs left
    assert first["clusters"] == 1
    assert second["clusters"] == 1   # same cluster, not duplicated

    count = conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0]
    assert count == 1


# --- Phase B4: multi-vote accumulation ----------------------------------


class _MostlyYes(ModelRuntime):
    """Returns 'yes' twice, then 'no' — used to test partial yes ratio."""

    def __init__(self) -> None:
        self._calls = 0

    def generate(self, prompt: str) -> str:
        self._calls += 1
        return "yes" if self._calls <= 2 else "no"


class _MostlyNo(ModelRuntime):
    """Returns 'yes' once, then 'no' twice."""

    def __init__(self) -> None:
        self._calls = 0

    def generate(self, prompt: str) -> str:
        self._calls += 1
        return "yes" if self._calls == 1 else "no"


def test_compare_pairs_default_min_votes_keeps_pair_pending_until_three(conn):
    """With the Phase B4 default (min_votes_per_pair=3), a single pair
    is voted on three times in one compare_pairs call — the per-vote
    refetch loop keeps picking the same partially-voted pair until it
    reaches the threshold."""
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "udon", "en", "udon")

    # One pair only; budget=10 means the loop will refetch until the
    # pair is no longer pending (3 votes) or budget exhausts.
    stats = compare_pairs(conn, _AlwaysYes(), max_pairs=10)
    assert stats["voted"] == 3   # pair completed in one call

    # Re-run: pair already has 3 votes, no longer pending
    stats = compare_pairs(conn, _AlwaysYes(), max_pairs=10)
    assert stats["voted"] == 0


def test_compare_pairs_concentrates_budget_on_partial_pair(conn):
    """The per-vote refetch + 'partially voted first' priority means a
    pair that's halfway through accumulation will be completed before
    we open a new pair. Critical Phase B4 property — without it, budget
    spreads thinly and no pair ever reaches the cluster threshold."""
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "udon", "en", "udon")
    c = _add_translation(conn, "soba", "en", "soba")
    # Three pairs, but seed one with one prior vote so it's "partially voted".
    vote_on_pair(conn, _AlwaysYes(), a, b)
    # Budget=2 — should both votes go to the partial pair (a,b)?
    stats = compare_pairs(conn, _AlwaysYes(), max_pairs=2)
    assert stats["voted"] == 2

    # Verify (a,b) reached 3 votes (1 prior + 2 from this sweep)
    cnt_ab = conn.execute(
        "SELECT COUNT(*) FROM pair_similarity_votes "
        "WHERE translation_id_a=? AND translation_id_b=?",
        (a, b),
    ).fetchone()[0]
    assert cnt_ab == 3


def test_rebuild_clusters_default_min_votes_rejects_single_vote(conn):
    """Default Phase B4 rebuild_clusters requires min_votes=3. A single
    yes vote isn't enough — guards against single-false-positive
    cluster pollution on cross-original pairs."""
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "noodle soup", "en", "noodle soup")
    vote_on_pair(conn, _AlwaysYes(), a, b)

    n = rebuild_clusters(conn)
    assert n == 0   # 1 vote < default min_votes=3


def test_rebuild_clusters_default_accepts_two_of_three_yes(conn):
    """Phase B4 threshold default (0.66) accepts 2 yes / 3 votes."""
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "noodle soup", "en", "noodle soup")
    runtime = _MostlyYes()
    # Three explicit votes
    vote_on_pair(conn, runtime, a, b)
    vote_on_pair(conn, runtime, a, b)
    vote_on_pair(conn, runtime, a, b)

    n = rebuild_clusters(conn)
    assert n == 1   # 2 yes / 3 votes = 0.666... ≥ 0.66


def test_rebuild_clusters_default_rejects_one_of_three_yes(conn):
    """Inverse: 1 yes / 3 votes = 0.33 fails the 0.66 threshold."""
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "udon", "en", "udon")
    runtime = _MostlyNo()
    vote_on_pair(conn, runtime, a, b)
    vote_on_pair(conn, runtime, a, b)
    vote_on_pair(conn, runtime, a, b)

    n = rebuild_clusters(conn)
    assert n == 0   # 1 yes / 3 votes = 0.33 < 0.66


# --- CLI smoke ----------------------------------------------------------


def test_cli_compare_and_rebuild(tmp_path):
    """End-to-end: seed → run cluster CLI → check clusters exist."""
    import subprocess
    import sys

    db_path = tmp_path / "test.db"
    # Use seed to populate translations
    subprocess.run(
        [sys.executable, "-m", "tideline.seed", "--db", str(db_path)],
        capture_output=True, text=True, check=True,
    )

    # We can't use mock for voting because Mock's translate-regex would
    # interfere. Use the mock runtime which falls through to echo for
    # B1's "Are these two terms..." prompt — echo doesn't contain yes/no,
    # so parse_response returns None → no votes recorded.
    # This proves the CLI runs cleanly even with no parseable votes.
    result = subprocess.run(
        [sys.executable, "-m", "tideline.cluster",
         "--db", str(db_path), "--runtime", "mock",
         "--compare", "5", "--rebuild"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Voted on" in result.stdout
    assert "cluster" in result.stdout.lower()
