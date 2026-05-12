"""Tier B cluster engine — accumulated pair votes → connected-component clusters.

The first Tier B feature. Each B1 invocation is one weak signal asking
"are these two translations the same concept?" — stored in
`pair_similarity_votes`. When enough votes accumulate, `rebuild_clusters`
runs Union-Find over the yes-votes and persists connected components as
clusters with their members.

Vote storage canonicalizes pairs as (min_id, max_id) so a vote on (5, 3)
and a vote on (3, 5) are the same edge. Multiple votes per pair are
allowed across time so accumulation works for less-reliable atoms in the
future; today B1 is reliable enough at 83-100% that single-vote-per-pair
is the MVP default.

CLI:
  python -m tideline.cluster --db PATH --compare 20 --rebuild
  python -m tideline.cluster --db PATH --rebuild
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from tideline.format import build_prompt as _build_turn_prompt
from tideline.format import make_turn
from tideline.intelligence import concept_match
from tideline.runtime import ModelRuntime
from tideline.runtimes import get_runtime


_DEFAULT_VOTE_THRESHOLD = 0.66
_DEFAULT_MIN_VOTES = 1


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pair_similarity_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            translation_id_a INTEGER NOT NULL REFERENCES translations(id) ON DELETE CASCADE,
            translation_id_b INTEGER NOT NULL REFERENCES translations(id) ON DELETE CASCADE,
            vote TEXT NOT NULL CHECK (vote IN ('yes', 'no')),
            model TEXT,
            voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (translation_id_a < translation_id_b)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_votes_pair "
        "ON pair_similarity_votes(translation_id_a, translation_id_b)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cluster_members (
            cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
            translation_id INTEGER NOT NULL REFERENCES translations(id) ON DELETE CASCADE,
            UNIQUE(cluster_id, translation_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cluster_members_cluster "
        "ON cluster_members(cluster_id)"
    )
    conn.commit()


# --- Voting ---------------------------------------------------------------


def _canonical_pair(a: int, b: int) -> tuple[int, int]:
    return (min(a, b), max(a, b))


def _fetch_translation(conn: sqlite3.Connection, tid: int) -> tuple[str, str, str] | None:
    row = conn.execute(
        "SELECT original, target_lang, translated FROM translations WHERE id = ?",
        (tid,),
    ).fetchone()
    return row


def _direct_generate(runtime: ModelRuntime, system: str, user: str) -> str:
    history = [make_turn("system", system), make_turn("user", user)]
    full_prompt = _build_turn_prompt(history)
    return runtime.generate(full_prompt).strip()


def vote_on_pair(
    conn: sqlite3.Connection,
    runtime: ModelRuntime,
    a: int,
    b: int,
    model_label: str = "unknown",
) -> bool | None:
    """Run the B1 concept-match atom on a pair, persist the vote.

    Returns True (yes), False (no), or None (model hedged or unparseable —
    no vote stored).
    """
    a, b = _canonical_pair(a, b)
    row_a = _fetch_translation(conn, a)
    row_b = _fetch_translation(conn, b)
    if row_a is None or row_b is None:
        return None

    original_a, target_a, translated_a = row_a
    original_b, target_b, translated_b = row_b

    # Use the user-facing original as the concept handle; the target-lang
    # rendering is the disambiguator for cross-language matches.
    prompt = concept_match.build_prompt(
        original_a, target_a or "unknown",
        original_b, target_b or "unknown",
    )
    response = _direct_generate(runtime, concept_match.SYSTEM_PROMPT, prompt)
    parsed = concept_match.parse_response(response)
    if parsed is None:
        return None

    conn.execute(
        "INSERT INTO pair_similarity_votes "
        "(translation_id_a, translation_id_b, vote, model) "
        "VALUES (?, ?, ?, ?)",
        (a, b, "yes" if parsed else "no", model_label),
    )
    conn.commit()
    return parsed


def _pending_pairs(
    conn: sqlite3.Connection, limit: int
) -> list[tuple[int, int]]:
    """Pick unvoted within-target_lang pairs, prioritizing pairs likely
    to be yes-edges so early sweeps build clusters quickly:

      1. Pairs with identical original text (almost always concept-equal)
      2. Then random sampling of cross-original within-lang pairs

    This is the MVP "prioritize cheap signal" heuristic. Future iterations
    can replace it with embedding-distance-ordered candidates etc.
    """
    rows = conn.execute(
        """
        SELECT t1.id, t2.id
        FROM translations t1
        JOIN translations t2 ON t2.id > t1.id
        WHERE t1.target_lang = t2.target_lang
          AND NOT EXISTS (
            SELECT 1 FROM pair_similarity_votes v
            WHERE v.translation_id_a = t1.id AND v.translation_id_b = t2.id
          )
        ORDER BY
            CASE WHEN t1.original = t2.original THEN 0 ELSE 1 END,
            RANDOM()
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [(row[0], row[1]) for row in rows]


def compare_pairs(
    conn: sqlite3.Connection,
    runtime: ModelRuntime,
    max_pairs: int = 10,
    model_label: str = "unknown",
) -> dict[str, int]:
    """Vote on up to `max_pairs` unvoted within-target_lang pairs.

    Returns {'voted': N, 'yes': N, 'no': N, 'unparseable': N}.
    """
    pairs = _pending_pairs(conn, max_pairs)
    yes_count = no_count = bad_count = 0
    for a, b in pairs:
        result = vote_on_pair(conn, runtime, a, b, model_label=model_label)
        if result is True:
            yes_count += 1
        elif result is False:
            no_count += 1
        else:
            bad_count += 1
    return {
        "voted": yes_count + no_count,
        "yes": yes_count,
        "no": no_count,
        "unparseable": bad_count,
    }


# --- Cluster rebuild ------------------------------------------------------


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        if x not in self._parent:
            self._parent[x] = x
            return x
        # Path compression
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb


def rebuild_clusters(
    conn: sqlite3.Connection,
    vote_threshold: float = _DEFAULT_VOTE_THRESHOLD,
    min_votes: int = _DEFAULT_MIN_VOTES,
) -> int:
    """Rebuild clusters from accumulated votes. Returns the number of
    clusters produced (size >= 2, single-member groups don't form clusters).

    Algorithm:
      1. SELECT pairs with vote_count >= min_votes AND yes_ratio >= threshold
      2. Union-Find over the resulting edge set
      3. DELETE FROM clusters / cluster_members
      4. For each connected component with >= 2 members, INSERT a cluster
         and its members
    """
    if not (0.0 <= vote_threshold <= 1.0):
        raise ValueError(f"vote_threshold must be in [0,1], got {vote_threshold}")
    if min_votes < 1:
        raise ValueError(f"min_votes must be >= 1, got {min_votes}")

    edges = conn.execute(
        """
        SELECT
            translation_id_a,
            translation_id_b,
            SUM(CASE WHEN vote = 'yes' THEN 1 ELSE 0 END) AS yes_votes,
            COUNT(*) AS total_votes
        FROM pair_similarity_votes
        GROUP BY translation_id_a, translation_id_b
        HAVING total_votes >= ? AND (yes_votes * 1.0 / total_votes) >= ?
        """,
        (min_votes, vote_threshold),
    ).fetchall()

    uf = _UnionFind()
    for a, b, _, _ in edges:
        uf.union(a, b)

    # Group nodes by their representative
    groups: dict[int, list[int]] = defaultdict(list)
    for node in uf._parent:
        groups[uf.find(node)].append(node)

    # Wipe existing clusters and rebuild
    conn.execute("DELETE FROM cluster_members")
    conn.execute("DELETE FROM clusters")

    cluster_count = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        cursor = conn.execute("INSERT INTO clusters (title) VALUES (NULL)")
        cluster_id = cursor.lastrowid
        conn.executemany(
            "INSERT INTO cluster_members (cluster_id, translation_id) VALUES (?, ?)",
            [(cluster_id, m) for m in sorted(members)],
        )
        cluster_count += 1

    conn.commit()
    return cluster_count


# --- CLI ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tideline.cluster",
        description="Tier B semantic clustering engine.",
    )
    parser.add_argument("--db", required=True, help="SQLite path")
    parser.add_argument(
        "--runtime", default="mock",
        help="Model backend for voting (default: mock; use llama_cpp for real)",
    )
    parser.add_argument(
        "--compare", type=int, default=0, metavar="N",
        help="Run B1 voting on up to N unvoted pairs (default: 0 = skip voting)",
    )
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Rebuild clusters from accumulated votes",
    )
    parser.add_argument(
        "--vote-threshold", type=float, default=_DEFAULT_VOTE_THRESHOLD,
        help=f"Yes-ratio threshold to count as similarity edge "
             f"(default: {_DEFAULT_VOTE_THRESHOLD})",
    )
    parser.add_argument(
        "--min-votes", type=int, default=_DEFAULT_MIN_VOTES,
        help=f"Minimum vote count per pair to consider "
             f"(default: {_DEFAULT_MIN_VOTES})",
    )
    args = parser.parse_args(argv)

    if args.db != ":memory:":
        Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)

    from tideline.tools import init_all_tables
    init_all_tables(conn)
    init_db(conn)

    if args.compare > 0:
        runtime = get_runtime(args.runtime)
        stats = compare_pairs(conn, runtime, max_pairs=args.compare, model_label=args.runtime)
        print(
            f"Voted on {stats['voted']} pairs: "
            f"{stats['yes']} yes, {stats['no']} no, "
            f"{stats['unparseable']} unparseable"
        )

    if args.rebuild:
        n = rebuild_clusters(
            conn,
            vote_threshold=args.vote_threshold,
            min_votes=args.min_votes,
        )
        print(f"Built {n} cluster(s) (size >= 2)")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
