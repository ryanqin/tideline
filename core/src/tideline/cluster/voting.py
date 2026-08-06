"""Asking the model about a pair, and recording what it said.

Vote storage canonicalizes pairs as (min_id, max_id) so a vote on (5, 3) and a
vote on (3, 5) are the same edge. Multiple votes per pair are allowed across
time so accumulation works for less-reliable atoms.
"""

from __future__ import annotations

import sqlite3

from tideline.cluster.common import (
    _DEFAULT_MIN_VOTES,
    _DETERMINISTIC_CONCEPT_PREDICATE,
    _direct_generate,
)
from tideline.cluster.dispatch import _voter
from tideline.runtime import ModelRuntime


def _canonical_pair(a: int, b: int) -> tuple[int, int]:
    return (min(a, b), max(a, b))


def _fetch_translation(conn: sqlite3.Connection, tid: int) -> tuple[str, str, str] | None:
    # The middle field is the term's SOURCE language — the language it was met
    # in (ラーメン→Japanese, ramen→English). The concept voter renders it next
    # to the term so the model judges the word in its real language; passing
    # the *target* language here (always the user's Chinese) mislabelled both
    # terms as Chinese and broke voting on same-language synonyms.
    row = conn.execute(
        "SELECT original, source_lang, translated FROM translations WHERE id = ?",
        (tid,),
    ).fetchone()
    return row


def vote_on_pair(
    conn: sqlite3.Connection,
    runtime: ModelRuntime,
    a: int,
    b: int,
    model_label: str = "unknown",
    vote_type: str = "concept",
) -> bool | None:
    """Run the pair atom for `vote_type` on a pair, persist the vote.

    `vote_type` selects the relation (see `_VOTERS`): 'concept' (B1
    synonym aggregation — the default, original Tier B behavior) or
    'theme' (B7 thematic relatedness). The vote is stored tagged with
    `vote_type` so the two relations never cross-contaminate.

    Returns True (yes), False (no), or None (model hedged or unparseable —
    no vote stored).
    """
    voter = _voter(vote_type)
    a, b = _canonical_pair(a, b)
    row_a = _fetch_translation(conn, a)
    row_b = _fetch_translation(conn, b)
    if row_a is None or row_b is None:
        return None

    prompt = voter.build(row_a, row_b)
    response = _direct_generate(runtime, voter.system_prompt, prompt)
    parsed = voter.parse(response)
    if parsed is None:
        return None

    conn.execute(
        "INSERT INTO pair_similarity_votes "
        "(translation_id_a, translation_id_b, vote, vote_type, model) "
        "VALUES (?, ?, ?, ?, ?)",
        (a, b, "yes" if parsed else "no", vote_type, model_label),
    )
    conn.commit()
    return parsed


def _pending_pairs(
    conn: sqlite3.Connection,
    limit: int,
    min_votes_per_pair: int = 1,
    exclude: set[tuple[int, int]] | None = None,
    vote_type: str = "concept",
) -> list[tuple[int, int]]:
    """Pick within-target_lang pairs that still need votes.

    A pair is "pending" while its accumulated vote count is strictly
    less than `min_votes_per_pair`.

    This is the concept (and general row-level) path. Voting is restricted to
    pairs within the same source language (clusters are scoped per
    language-pair, §3.3), and deterministic same-concept pairs (same source
    word, or same first-language rendering within one language — see
    `_DETERMINISTIC_CONCEPT_PREDICATE`) are excluded entirely: they don't need
    a model vote (they're settled by construction and added as edges in
    rebuild_clusters), and excluding them keeps a modest budget from being
    eaten by same-word pairs before it reaches genuinely ambiguous synonyms.

    Theme clustering does NOT vote at all — themes are co-occurrence (capture
    sessions), built deterministically in rebuild_clusters. So this is the
    concept path in practice. (`vote_type` still parameterises the vote count,
    so it stays a correct general "pending pairs of this relation" query.)

    Priority order (Phase B4):
      1. Pairs already partially voted come first — finishing accumulation
         on an in-progress pair is cheaper than starting a new one, and
         converges to clusters faster
      2. RANDOM tiebreaker

    With `min_votes_per_pair=1` (single-vote semantics for tests that
    exercise Phase B1 behavior), a pair leaves the pending set after
    one vote. With `min_votes_per_pair=3` (the Phase B4 default), each
    pair stays in the rotation until three votes accumulate, and the
    partial-progress priority concentrates the budget on completing
    pairs rather than spraying single votes across the whole pair space.

    Vote counting is scoped to `vote_type`: a pair's concept votes and
    theme votes accumulate independently, so the same pair stays
    "pending" separately per relation. The within-target_lang restriction
    is shared — for a single-first-language user every translation lands
    in the same target_lang, so theme grouping is unaffected;
    cross-target_lang theme grouping (polyglot) is a known MVP gap.
    """
    # Concept voting stays inside one source language (clusters are scoped
    # per language-pair, §3.3) and skips deterministic same-concept pairs
    # (those are added as edges in rebuild_clusters). Theme voting has no
    # such shortcut and is not language-scoped here.
    concept_clause = (
        "AND COALESCE(t1.source_lang, '') = COALESCE(t2.source_lang, '')\n"
        f"          AND NOT {_DETERMINISTIC_CONCEPT_PREDICATE}\n          "
        if vote_type == "concept" else ""
    )
    rows = conn.execute(
        f"""
        SELECT
            t1.id,
            t2.id,
            (SELECT COUNT(*) FROM pair_similarity_votes v
             WHERE v.translation_id_a = t1.id
               AND v.translation_id_b = t2.id
               AND v.vote_type = ?) AS votes_so_far
        FROM translations t1
        JOIN translations t2 ON t2.id > t1.id
        WHERE t1.target_lang = t2.target_lang
          {concept_clause}AND (SELECT COUNT(*) FROM pair_similarity_votes v
               WHERE v.translation_id_a = t1.id
                 AND v.translation_id_b = t2.id
                 AND v.vote_type = ?) < ?
        ORDER BY
            votes_so_far DESC,
            RANDOM()
        LIMIT ?
        """,
        # Over-fetch so the Python-side exclude filter still leaves
        # `limit` candidates in normal cases. Excluded set is bounded
        # by the caller's budget so this stays cheap.
        (vote_type, vote_type, min_votes_per_pair,
         limit + (len(exclude) if exclude else 0)),
    ).fetchall()
    pairs = [(row[0], row[1]) for row in rows]
    if exclude:
        pairs = [p for p in pairs if p not in exclude]
    return pairs[:limit]


def compare_pairs(
    conn: sqlite3.Connection,
    runtime: ModelRuntime,
    max_pairs: int = 10,
    model_label: str = "unknown",
    min_votes_per_pair: int = _DEFAULT_MIN_VOTES,
    vote_type: str = "concept",
) -> dict[str, int]:
    """Vote on up to `max_pairs` pending within-target_lang pairs.

    A pair is pending while its vote count < `min_votes_per_pair`.
    See `_pending_pairs` for the Phase B1 vs Phase B4 semantics.

    `vote_type` selects the relation ('concept' default, or 'theme') and
    is threaded through pending-pair selection and voting so a sweep only
    touches one relation's accumulation.

    Pairs are fetched one at a time so the priority order (already-
    partially-voted pairs first) actually takes effect — a single bulk
    SELECT would see all pairs at zero votes and degenerate into random
    sampling, defeating Phase B4's "concentrate budget on completing
    pairs" goal. SQL is cheap compared to LLM calls, so re-fetching
    per iteration is fine.

    Returns {'voted': N, 'yes': N, 'no': N, 'unparseable': N}.
    """
    yes_count = no_count = bad_count = 0
    # Track pairs that hedged within this call so we don't keep retrying
    # them and exhausting budget on a single unparseable case.
    hedged_pairs: set[tuple[int, int]] = set()
    for _ in range(max_pairs):
        pending = _pending_pairs(
            conn, limit=1,
            min_votes_per_pair=min_votes_per_pair,
            exclude=hedged_pairs,
            vote_type=vote_type,
        )
        if not pending:
            break
        a, b = pending[0]
        result = vote_on_pair(
            conn, runtime, a, b, model_label=model_label, vote_type=vote_type,
        )
        if result is True:
            yes_count += 1
        elif result is False:
            no_count += 1
        else:
            bad_count += 1
            hedged_pairs.add((a, b))
    return {
        "voted": yes_count + no_count,
        "yes": yes_count,
        "no": no_count,
        "unparseable": bad_count,
    }
