"""The night watch: vote, rebuild, name, on a budget.

The one entry point the lifecycle hooks (`boot.startup_sweep`) call.
"""

from __future__ import annotations

import sqlite3

from tideline.cluster.common import _DEFAULT_MIN_VOTES, _DEFAULT_VOTE_THRESHOLD
from tideline.cluster.naming import name_clusters
from tideline.cluster.rebuild import rebuild_clusters
from tideline.cluster.voting import compare_pairs
from tideline.runtime import ModelRuntime


# --- Night-watch sweep (Phase B3) -----------------------------------------


_DEFAULT_SWEEP_BUDGET = 3


def cluster_sweep(
    conn: sqlite3.Connection,
    runtime: ModelRuntime,
    max_pairs: int = _DEFAULT_SWEEP_BUDGET,
    model_label: str = "sweep",
    min_votes_per_pair: int = _DEFAULT_MIN_VOTES,
    vote_threshold: float = _DEFAULT_VOTE_THRESHOLD,
    vote_type: str = "concept",
) -> dict[str, int]:
    """One round of background cluster work: vote, rebuild, name.

    Designed for the CLI startup hook — caller decides whether to swallow
    exceptions for a fail-soft UX. Returns aggregate stats so tests (and
    explicit `--name-clusters` etc.) can verify what happened.

    `vote_type` runs one relation end-to-end ('concept' default, or
    'theme'). The two relations are independent sweeps over the same
    tables — a caller wanting both kinds of clusters calls this twice.

    Concept votes (budget = `max_pairs`); theme does NOT vote — themes are
    co-occurrence (capture sessions), built deterministically in
    rebuild_clusters, so the theme sweep is just rebuild + episodic naming.
    """
    if vote_type == "theme":
        # No voting step: themes are co-occurrence, not relatedness.
        vote_stats = {"voted": 0, "yes": 0, "no": 0, "unparseable": 0}
    else:
        vote_stats = compare_pairs(
            conn, runtime,
            max_pairs=max_pairs,
            model_label=model_label,
            min_votes_per_pair=min_votes_per_pair,
            vote_type=vote_type,
        )
    n_clusters = rebuild_clusters(
        conn, vote_threshold=vote_threshold, min_votes=min_votes_per_pair,
        vote_type=vote_type,
    )
    name_stats = name_clusters(conn, runtime, vote_type=vote_type)
    return {
        "voted": vote_stats["voted"],
        "yes": vote_stats["yes"],
        "no": vote_stats["no"],
        "unparseable_votes": vote_stats["unparseable"],
        "clusters": n_clusters,
        "named": name_stats["named"],
        "unparseable_names": name_stats["unparseable"],
    }
