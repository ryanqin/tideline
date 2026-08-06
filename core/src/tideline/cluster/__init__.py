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

This was one 909-line module and is now a package along the seams it already
had, marked out in `# --- section ---` comments:

    common     constants and the single-turn model call, so the parts that
               share them don't have to import each other
    schema     the tables, and the vote_type migration
    dispatch   which relation a vote is about (the _Voter table)
    voting     asking the model about a pair, recording what it said
    rebuild    votes + deterministic edges → connected components
    naming     the B6 title for a cluster
    sweep      the night watch: vote, rebuild, name, on a budget
    __main__   the CLI

The dependency graph is a DAG and stays one: everything may use `common`;
`sweep` and the CLI sit on top; nothing below reaches back up. `naming` used
to need `voting` for exactly one function, which made a dependency out of a
coincidence — that function moved to `common` and the edge went away.

Every name the module exported is re-exported here, private ones included, so
`from tideline.cluster import ...` keeps working unchanged — for callers and
for the 1131 lines of tests that reach for `_UnionFind`, `_canonical_pair`,
`_concept_partition`, `_deterministic_concept_edges` and `_pending_pairs`.
"""

from __future__ import annotations

from tideline.cluster.common import (
    _DEFAULT_MIN_VOTES,
    _DEFAULT_VOTE_THRESHOLD,
    _DETERMINISTIC_CONCEPT_PREDICATE,
    _direct_generate,
)
from tideline.cluster.dispatch import _VOTERS, _Voter, _voter
from tideline.cluster.naming import _cluster_items, _unnamed_clusters, name_clusters
from tideline.cluster.rebuild import (
    _concept_edges,
    _concept_partition,
    _deterministic_concept_edges,
    _UnionFind,
    _vote_edges,
    rebuild_clusters,
)
from tideline.cluster.schema import _migrate_vote_type, init_db
from tideline.cluster.sweep import _DEFAULT_SWEEP_BUDGET, cluster_sweep
from tideline.cluster.voting import (
    _canonical_pair,
    _fetch_translation,
    _pending_pairs,
    compare_pairs,
    vote_on_pair,
)

__all__ = [
    # The engine's public surface.
    "init_db",
    "vote_on_pair",
    "compare_pairs",
    "rebuild_clusters",
    "name_clusters",
    "cluster_sweep",
    # Private, but reached for by the test suite — listed so a future reader
    # knows removing one is a test-visible change, not a local edit.
    "_UnionFind",
    "_canonical_pair",
    "_concept_partition",
    "_deterministic_concept_edges",
    "_pending_pairs",
]
