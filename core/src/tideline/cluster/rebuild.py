"""Votes and deterministic edges into connected components.

Two relations, two algorithms, one persistence tail — see `rebuild_clusters`
for which is which and why they share only the tail.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from tideline.cluster.common import (
    _DEFAULT_MIN_VOTES,
    _DEFAULT_VOTE_THRESHOLD,
    _DETERMINISTIC_CONCEPT_PREDICATE,
)


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


def _deterministic_concept_edges(
    conn: sqlite3.Connection,
) -> list[tuple[int, int]]:
    """Within-target_lang translation pairs that are the same concept by
    construction (see `_DETERMINISTIC_CONCEPT_PREDICATE`): same source word,
    or same first-language rendering within one source language. These need
    no model vote, so they're excluded from voting (`_pending_pairs`) and
    added straight to the Union-Find here — that's what lets a concept
    cluster form deterministically, on any budget.
    """
    return conn.execute(
        f"""
        SELECT t1.id, t2.id
        FROM translations t1
        JOIN translations t2 ON t2.id > t1.id
        WHERE t1.target_lang = t2.target_lang
          AND {_DETERMINISTIC_CONCEPT_PREDICATE}
        """
    ).fetchall()


def _vote_edges(
    conn: sqlite3.Connection,
    vote_type: str,
    vote_threshold: float,
    min_votes: int,
    lang_scoped: bool,
) -> list[tuple[int, int]]:
    """Translation-id pairs whose accumulated `vote_type` votes clear the
    threshold (>= min_votes total AND yes-ratio >= vote_threshold). When
    `lang_scoped`, only same-source-language pairs count (concept stays inside
    one language-pair, §3.3); theme is not language-scoped.
    """
    lang_filter = (
        "AND COALESCE(t1.source_lang, '') = COALESCE(t2.source_lang, '')"
        if lang_scoped else ""
    )
    rows = conn.execute(
        f"""
        SELECT v.translation_id_a, v.translation_id_b
        FROM pair_similarity_votes v
        JOIN translations t1 ON t1.id = v.translation_id_a
        JOIN translations t2 ON t2.id = v.translation_id_b
        WHERE v.vote_type = ?
          {lang_filter}
        GROUP BY v.translation_id_a, v.translation_id_b
        HAVING COUNT(*) >= ?
           AND (SUM(CASE WHEN v.vote = 'yes' THEN 1 ELSE 0 END) * 1.0
                / COUNT(*)) >= ?
        """,
        (vote_type, min_votes, vote_threshold),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def _concept_edges(
    conn: sqlite3.Connection,
    vote_threshold: float = _DEFAULT_VOTE_THRESHOLD,
    min_votes: int = _DEFAULT_MIN_VOTES,
) -> list[tuple[int, int]]:
    """Every edge that makes two translations the same concept: the
    deterministic same-concept pairs plus concept votes that cleared the
    threshold (same-language only). Shared by concept rebuild and the concept
    partition so both agree on what a concept is.
    """
    return _deterministic_concept_edges(conn) + _vote_edges(
        conn, "concept", vote_threshold, min_votes, lang_scoped=True
    )


def _concept_partition(conn: sqlite3.Connection) -> dict[int, int]:
    """Map every translation id to its concept representative.

    Concepts are the connected components of `_concept_edges`; a translation
    in no concept edge is its own concept (maps to itself). Theme clustering
    uses this so relatedness is judged between *concepts* — one node per
    concept — not between every repeated row of the same word. Without it the
    six rows of a word seen six times are six separate theme nodes, and a
    single theme vote only links one of them (fragmentation); collapsing to
    concepts also shrinks the pair space from rows^2 to concepts^2.
    """
    uf = _UnionFind()
    for a, b in _concept_edges(conn):
        uf.union(a, b)
    partition: dict[int, int] = {}
    for (tid,) in conn.execute("SELECT id FROM translations"):
        partition[tid] = uf.find(tid)  # find() seeds a singleton as its own rep
    return partition


def rebuild_clusters(
    conn: sqlite3.Connection,
    vote_threshold: float = _DEFAULT_VOTE_THRESHOLD,
    min_votes: int = _DEFAULT_MIN_VOTES,
    vote_type: str = "concept",
) -> int:
    """Rebuild the `vote_type` clusters from accumulated votes. Returns the
    number of clusters produced (size >= 2, single-member groups don't
    form clusters).

    Scoped to one relation: only `vote_type` votes form edges, and only
    `vote_type` clusters are wiped + rebuilt — the other relation's
    clusters (and their titles) are untouched, so concept and theme
    clusters coexist in the same tables.

    Algorithm differs by relation:
      - concept: Union-Find over deterministic same-concept edges + concept
        votes over threshold (within one source language, `_concept_edges`);
        a component of >= 2 member rows becomes a cluster.
      - theme: group translations by the model-reported `scene_label` (a SCENE
        TYPE — a kind of place clustered across visits); a label with >= 2
        distinct concepts (via `_concept_partition`) becomes a theme whose
        members are every row met at that scene type. No votes — `min_votes`
        and `vote_threshold` are ignored for theme.
    Then DELETE this vote_type's clusters/members and INSERT the new ones.
    """
    if vote_type != "theme":
        # Only validated on the path that reads them. The docstring above says
        # theme ignores both, and it does — so rejecting a value theme never
        # looks at was the code contradicting its own contract.
        if not (0.0 <= vote_threshold <= 1.0):
            raise ValueError(f"vote_threshold must be in [0,1], got {vote_threshold}")
        if min_votes < 1:
            raise ValueError(f"min_votes must be >= 1, got {min_votes}")

    if vote_type == "theme":
        # A theme is a SCENE TYPE — a kind of place clustered ACROSS visits, not
        # one occasion. The handle is the short scene label the capture model
        # reports (拉面店 / 车站 / 咖啡馆); members are every word ever met at
        # that kind of place. The model only categorises (garnish); grouping is
        # exact-match on the label (engineering load-bearing) — cross-type
        # separation is clean, and same-type synonym drift (居酒屋/酒馆) only
        # makes near-duplicate themes, never a false merge. (Real-model relat-
        # edness can't draw a clean boundary on word pairs — 2026-06-03 probe;
        # the scene-label probe — 2026-06-13 — categorises cleanly. §3.2.)
        # A scene still needs >= 2 distinct concepts to be a scene.
        partition = _concept_partition(conn)
        scenes: dict[str, list[int]] = defaultdict(list)
        for tid, label in conn.execute(
            "SELECT id, scene_label FROM translations "
            "WHERE scene_label IS NOT NULL AND scene_label <> ''"
        ):
            scenes[label].append(tid)
        groups: dict[int, list[int]] = {}
        for idx, (_label, rows) in enumerate(scenes.items()):
            concepts = {partition.get(r, r) for r in rows}
            if len(concepts) < 2:  # a one-concept scene is not a scene
                continue
            groups[idx] = rows
        # KNOWN LIMITATION (mirrors the old mixed-session note): a scene label is
        # in the target language, so a café in Paris and one in Tokyo could share
        # "咖啡馆" and merge across languages (§3.3 wants one language pair per
        # cluster). Deferred until cross-language same-scene captures are common;
        # seed trips are single-language so it doesn't bite the demo.
    else:
        # Concept edges: deterministic same-concept pairs + concept votes that
        # cleared the threshold, all kept inside one source language (§3.3).
        uf = _UnionFind()
        for a, b in _concept_edges(conn, vote_threshold, min_votes):
            uf.union(a, b)
        groups = defaultdict(list)
        for node in uf._parent:
            groups[uf.find(node)].append(node)

    # Snapshot existing (membership_signature → title) so a rebuild that
    # produces the same connected components preserves human-readable
    # titles. Without this, every cluster_sweep wipes titles and the
    # next name_clusters call regenerates them — model sampling drift
    # would make titles oscillate, and mock runtime would replace good
    # titles with echo noise. Scoped to this vote_type so concept and
    # theme titles never bleed across (a concept cluster and a theme
    # cluster may share a membership signature).
    preserved: dict[tuple[int, ...], str] = {}
    for cid, title in conn.execute(
        "SELECT id, title FROM clusters WHERE vote_type = ?", (vote_type,)
    ):
        if not title:
            continue
        member_ids = [
            r[0] for r in conn.execute(
                "SELECT translation_id FROM cluster_members WHERE cluster_id = ?",
                (cid,),
            )
        ]
        preserved[tuple(sorted(member_ids))] = title

    # Wipe only this vote_type's clusters and rebuild. SQLite doesn't
    # enforce FKs by default, so delete members explicitly first.
    conn.execute(
        "DELETE FROM cluster_members WHERE cluster_id IN "
        "(SELECT id FROM clusters WHERE vote_type = ?)",
        (vote_type,),
    )
    conn.execute("DELETE FROM clusters WHERE vote_type = ?", (vote_type,))

    cluster_count = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        sig = tuple(sorted(members))
        title = preserved.get(sig)
        cursor = conn.execute(
            "INSERT INTO clusters (title, vote_type) VALUES (?, ?)",
            (title, vote_type),
        )
        cluster_id = cursor.lastrowid
        conn.executemany(
            "INSERT INTO cluster_members (cluster_id, translation_id) VALUES (?, ?)",
            [(cluster_id, m) for m in sorted(members)],
        )
        cluster_count += 1

    conn.commit()
    return cluster_count
