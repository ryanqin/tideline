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
    _concept_partition,
    _deterministic_concept_edges,
    _pending_pairs,
    _pending_theme_pairs,
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
    c: sqlite3.Connection,
    original: str,
    target_lang: str,
    translated: str,
    source_lang: str | None = None,
) -> int:
    cursor = c.execute(
        "INSERT INTO translations (original, target_lang, translated, source_lang) "
        "VALUES (?, ?, ?, ?)",
        (original, target_lang, translated, source_lang),
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


# --- Deterministic concept edges, scoped per language-pair (no votes) ----


def test_same_word_merges_with_zero_votes(conn):
    """The same source word seen twice is trivially one concept — a
    deterministic edge, no vote needed (and on any budget)."""
    _add_translation(conn, "ラーメン", "Chinese", "拉面", source_lang="Japanese")
    _add_translation(conn, "ラーメン", "Chinese", "拉面", source_lang="Japanese")
    assert rebuild_clusters(conn, vote_type="concept") == 1


def test_same_rendering_merges_within_one_language_with_zero_votes(conn):
    """Two DIFFERENT words of the SAME source language that render to the
    same first-language form are the same concept — Japanese 駅 and 停車場
    both → 车站. Merges deterministically, no vote."""
    a = _add_translation(conn, "駅", "Chinese", "车站", source_lang="Japanese")
    b = _add_translation(conn, "停車場", "Chinese", "车站", source_lang="Japanese")
    assert (a, b) in _deterministic_concept_edges(conn)
    assert rebuild_clusters(conn, vote_type="concept") == 1


def test_same_rendering_does_NOT_merge_across_languages(conn):
    """A concept cluster never holds two language-pairs (§3.3). 駅 (Japanese)
    and station (English) both render to 车站, but they are two different
    language directions — they must stay two separate clusters, never fused.
    The user meeting one concept in two languages is a rare case we don't
    chase."""
    a = _add_translation(conn, "駅", "Chinese", "车站", source_lang="Japanese")
    b = _add_translation(conn, "station", "Chinese", "车站", source_lang="English")

    assert _deterministic_concept_edges(conn) == []   # different language pair
    assert (a, b) not in _pending_pairs(conn, limit=10, vote_type="concept")
    # Even three forced cross-language yes votes must not fuse them.
    for _ in range(3):
        vote_on_pair(conn, _AlwaysYes(), a, b, vote_type="concept")
    assert rebuild_clusters(conn, vote_type="concept") == 0


def test_deterministic_edges_exclude_distinct_unrelated_concepts(conn):
    """Different words with different first-language forms are NOT a
    deterministic edge — they still need a model vote to cluster."""
    a = _add_translation(conn, "ラーメン", "Chinese", "拉面", source_lang="Japanese")
    b = _add_translation(conn, "寿司", "Chinese", "寿司", source_lang="Japanese")
    assert _deterministic_concept_edges(conn) == []
    assert rebuild_clusters(conn, vote_type="concept") == 0  # no edge, no cluster
    assert (a, b) in _pending_pairs(conn, limit=10, vote_type="concept")


def test_concept_voting_skips_deterministic_pairs(conn):
    """`_pending_pairs` for concept must not hand deterministic pairs to the
    model — voting on a foregone conclusion is what eats the sweep budget."""
    same_orig_a = _add_translation(conn, "駅", "Chinese", "车站", source_lang="Japanese")
    same_orig_b = _add_translation(conn, "駅", "Chinese", "车站", source_lang="Japanese")
    same_rend_a = _add_translation(conn, "地下鉄", "Chinese", "地铁", source_lang="Japanese")
    same_rend_b = _add_translation(conn, "メトロ", "Chinese", "地铁", source_lang="Japanese")

    pending = _pending_pairs(conn, limit=50, vote_type="concept")
    assert (same_orig_a, same_orig_b) not in pending
    assert (same_rend_a, same_rend_b) not in pending


def test_theme_votes_between_concepts_not_rows(conn):
    """Theme relatedness is judged between concepts, one node per concept.
    Two rows of the same word are one concept, so they're never proposed as a
    theme pair; two distinct concepts are."""
    _add_translation(conn, "ラーメン", "Chinese", "拉面", source_lang="Japanese")
    _add_translation(conn, "ラーメン", "Chinese", "拉面", source_lang="Japanese")
    _add_translation(conn, "餃子", "Chinese", "煎饺", source_lang="Japanese")

    reps = list(set(_concept_partition(conn).values()))
    assert len(reps) == 2  # ramen-concept + gyoza-concept (not 3 rows)
    pending = _pending_theme_pairs(conn, reps, limit=50)
    assert len(pending) == 1  # exactly the one concept-pair


def test_theme_cluster_expands_to_every_row_of_its_concepts(conn):
    """The fragmentation fix: ONE theme vote between two concepts pulls in
    every row behind both concepts — not just the two rows that were voted."""
    r1 = _add_translation(conn, "ラーメン", "Chinese", "拉面", source_lang="Japanese")
    r2 = _add_translation(conn, "ラーメン", "Chinese", "拉面", source_lang="Japanese")
    r3 = _add_translation(conn, "ラーメン", "Chinese", "拉面", source_lang="Japanese")
    g1 = _add_translation(conn, "餃子", "Chinese", "煎饺", source_lang="Japanese")
    g2 = _add_translation(conn, "餃子", "Chinese", "煎饺", source_lang="Japanese")

    ra, rb = sorted(set(_concept_partition(conn).values()))  # the two concepts
    for _ in range(3):
        vote_on_pair(conn, _AlwaysYes(), ra, rb, vote_type="theme")

    assert rebuild_clusters(conn, vote_type="theme") == 1
    assert set(_cluster_member_ids(conn, "theme")) == {r1, r2, r3, g1, g2}


def test_a_single_concept_is_not_a_theme(conn):
    """A theme needs >= 2 distinct concepts. One word seen many times is a
    single concept — even a (degenerate) within-concept theme vote forms no
    theme."""
    rows = [
        _add_translation(conn, "ラーメン", "Chinese", "拉面", source_lang="Japanese")
        for _ in range(3)
    ]
    for _ in range(3):
        vote_on_pair(conn, _AlwaysYes(), rows[0], rows[1], vote_type="theme")
    assert rebuild_clusters(conn, vote_type="theme") == 0


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


# --- Theme clustering (vote_type partition) -----------------------------


def _cluster_member_ids(c: sqlite3.Connection, vote_type: str) -> list[int]:
    rows = c.execute(
        "SELECT cm.translation_id FROM cluster_members cm "
        "JOIN clusters cl ON cl.id = cm.cluster_id "
        "WHERE cl.vote_type = ? ORDER BY cm.translation_id",
        (vote_type,),
    ).fetchall()
    return [r[0] for r in rows]


def test_migration_adds_vote_type_to_legacy_schema():
    """A pre-partition DB (votes/clusters without vote_type) is upgraded in
    place by init_db, and legacy rows backfill to 'concept' — what they were
    before theme clustering existed. Also proves ALTER ... ADD COLUMN with a
    CHECK constraint runs on this SQLite build."""
    c = sqlite3.connect(":memory:")
    c.execute(
        "CREATE TABLE translations (id INTEGER PRIMARY KEY, original TEXT, "
        "target_lang TEXT, translated TEXT)"
    )
    c.execute(
        """CREATE TABLE pair_similarity_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            translation_id_a INTEGER NOT NULL,
            translation_id_b INTEGER NOT NULL,
            vote TEXT NOT NULL,
            model TEXT,
            voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (translation_id_a < translation_id_b)
        )"""
    )
    c.execute(
        "CREATE TABLE clusters (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "title TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    c.execute(
        "INSERT INTO translations (id, original, target_lang, translated) "
        "VALUES (1, 'ramen', 'en', 'ramen'), (2, 'udon', 'en', 'udon')"
    )
    c.execute(
        "INSERT INTO pair_similarity_votes "
        "(translation_id_a, translation_id_b, vote) VALUES (1, 2, 'yes')"
    )
    c.execute("INSERT INTO clusters (title) VALUES ('legacy cluster')")
    c.commit()

    pre = {r[1] for r in c.execute("PRAGMA table_info(pair_similarity_votes)")}
    assert "vote_type" not in pre   # sanity: legacy schema

    init_db(c)   # triggers _migrate_vote_type

    votes_cols = {r[1] for r in c.execute("PRAGMA table_info(pair_similarity_votes)")}
    clusters_cols = {r[1] for r in c.execute("PRAGMA table_info(clusters)")}
    assert "vote_type" in votes_cols
    assert "vote_type" in clusters_cols
    assert c.execute(
        "SELECT vote_type FROM pair_similarity_votes"
    ).fetchone()[0] == "concept"
    assert c.execute("SELECT vote_type FROM clusters").fetchone()[0] == "concept"
    c.close()


def test_vote_on_pair_unknown_vote_type_raises(conn):
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "udon", "en", "udon")
    with pytest.raises(ValueError):
        vote_on_pair(conn, _AlwaysYes(), a, b, vote_type="bogus")


def test_vote_on_pair_stores_vote_type(conn):
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "sushi", "en", "sushi")
    vote_on_pair(conn, _AlwaysYes(), a, b, vote_type="theme")
    assert conn.execute(
        "SELECT vote_type FROM pair_similarity_votes"
    ).fetchone()[0] == "theme"


def test_votes_partition_by_type_on_same_pair(conn):
    """Concept and theme votes on the SAME pair accumulate independently —
    the partition keeps the relations from contaminating each other. ramen
    vs sushi: different concepts (no) but the same cuisine theme (yes)."""
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "sushi", "en", "sushi")
    vote_on_pair(conn, _AlwaysNo(), a, b, vote_type="concept")
    vote_on_pair(conn, _AlwaysYes(), a, b, vote_type="theme")

    concept = conn.execute(
        "SELECT vote FROM pair_similarity_votes WHERE vote_type='concept'"
    ).fetchall()
    theme = conn.execute(
        "SELECT vote FROM pair_similarity_votes WHERE vote_type='theme'"
    ).fetchall()
    assert [v[0] for v in concept] == ["no"]
    assert [v[0] for v in theme] == ["yes"]


def test_pending_pairs_independent_per_vote_type(conn):
    """A pair fully voted for concept is still pending for theme."""
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "sushi", "en", "sushi")
    vote_on_pair(conn, _AlwaysYes(), a, b, vote_type="concept")

    assert (a, b) not in _pending_pairs(conn, limit=10, vote_type="concept")
    assert (a, b) in _pending_pairs(conn, limit=10, vote_type="theme")


def test_theme_and_concept_clusters_coexist(conn):
    """rebuild_clusters scoped by vote_type: concept aggregates synonyms,
    theme groups a related-but-distinct term, and both clusters live in the
    table tagged by relation."""
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "ramen noodles", "en", "ramen noodles")
    c = _add_translation(conn, "sushi", "en", "sushi")
    vote_on_pair(conn, _AlwaysYes(), a, b, vote_type="concept")  # a ≡ b
    vote_on_pair(conn, _AlwaysYes(), a, c, vote_type="theme")    # a ~ c

    assert rebuild_clusters(conn, min_votes=1, vote_type="concept") == 1
    assert rebuild_clusters(conn, min_votes=1, vote_type="theme") == 1

    counts = dict(conn.execute(
        "SELECT vote_type, COUNT(*) FROM clusters GROUP BY vote_type"
    ).fetchall())
    assert counts == {"concept": 1, "theme": 1}
    assert _cluster_member_ids(conn, "concept") == sorted([a, b])
    assert _cluster_member_ids(conn, "theme") == sorted([a, c])


def test_rebuild_one_relation_leaves_other_intact(conn):
    """The vote_type-scoped DELETE means rebuilding theme must not wipe the
    concept clusters or their human-edited titles."""
    a = _add_translation(conn, "ramen", "en", "ramen")
    b = _add_translation(conn, "ramen noodles", "en", "ramen noodles")
    vote_on_pair(conn, _AlwaysYes(), a, b, vote_type="concept")
    rebuild_clusters(conn, min_votes=1, vote_type="concept")
    conn.execute(
        "UPDATE clusters SET title='your noodle words' WHERE vote_type='concept'"
    )
    conn.commit()

    c = _add_translation(conn, "sushi", "en", "sushi")
    vote_on_pair(conn, _AlwaysYes(), a, c, vote_type="theme")
    rebuild_clusters(conn, min_votes=1, vote_type="theme")

    concept = conn.execute(
        "SELECT title FROM clusters WHERE vote_type='concept'"
    ).fetchall()
    assert len(concept) == 1
    assert concept[0][0] == "your noodle words"


def test_cluster_sweep_theme_end_to_end(conn):
    """cluster_sweep(vote_type='theme') votes + rebuilds + names theme
    clusters, tagged separately from concept. AlwaysYes drives both the
    yes-votes and a stub title (same single-runtime pattern as the concept
    sweep test)."""
    for term in ("ramen", "sushi", "tempura"):
        _add_translation(conn, term, "en", term)

    stats = cluster_sweep(
        conn, _AlwaysYes(),
        max_pairs=10, min_votes_per_pair=1, vote_type="theme",
    )
    assert stats["voted"] == 3
    assert stats["clusters"] == 1
    assert stats["named"] == 1
    rows = conn.execute("SELECT vote_type, title FROM clusters").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "theme"
    assert rows[0][1] is not None


def test_cli_vote_type_theme_smoke(tmp_path):
    """CLI accepts --vote-type theme and runs the theme relation end to end.
    Mock voting falls through to echo (no parseable yes/no), so this proves
    the wiring runs clean — not that clusters form."""
    import subprocess
    import sys

    db_path = tmp_path / "test.db"
    subprocess.run(
        [sys.executable, "-m", "tideline.seed", "--db", str(db_path)],
        capture_output=True, text=True, check=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "tideline.cluster",
         "--db", str(db_path), "--runtime", "mock",
         "--vote-type", "theme", "--compare", "5", "--rebuild", "--name-clusters"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Voted on" in result.stdout
