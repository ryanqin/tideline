"""`python -m tideline.cluster` — driving the engine by hand."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from tideline.cluster.common import _DEFAULT_MIN_VOTES, _DEFAULT_VOTE_THRESHOLD
from tideline.cluster.naming import name_clusters
from tideline.cluster.rebuild import rebuild_clusters
from tideline.cluster.schema import init_db
from tideline.cluster.voting import compare_pairs
from tideline.runtime import ModelRuntime
from tideline.runtimes import get_runtime


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
        "--name-clusters", action="store_true",
        help="Generate episodic titles (B6) for clusters that lack one",
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
    # Written out rather than derived from _VOTERS: the two sets are not the
    # same thing. _VOTERS is "relations that can vote"; this is "relations the
    # CLI can act on". theme belongs in the second and not the first — it
    # rebuilds and names, it just doesn't vote.
    parser.add_argument(
        "--vote-type", default="concept", choices=("concept", "theme"),
        help="Clustering relation: 'concept' (synonyms, default) or "
             "'theme' (scene types, grouped by the capture model's scene_label)",
    )
    args = parser.parse_args(argv)

    # Voting on themes writes rows nobody reads: theme clusters are grouped
    # deterministically on scene_label. Left open, this burns on-device
    # inference and then prints "Voted on N pairs: N yes" — a reading that
    # means nothing, which is worse than no reading at all.
    if args.compare > 0 and args.vote_type == "theme":
        parser.error(
            "theme clusters don't vote — they group deterministically on the "
            "capture model's scene_label. Use --rebuild (and --name-clusters) "
            "instead; --compare only applies to --vote-type concept."
        )

    if args.db != ":memory:":
        Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)

    from tideline.tools import init_all_tables
    init_all_tables(conn)
    init_db(conn)

    runtime: ModelRuntime | None = None

    if args.compare > 0:
        runtime = get_runtime(args.runtime)
        stats = compare_pairs(
            conn, runtime, max_pairs=args.compare,
            model_label=args.runtime, vote_type=args.vote_type,
        )
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
            vote_type=args.vote_type,
        )
        print(f"Built {n} cluster(s) (size >= 2)")

    if args.name_clusters:
        if runtime is None:
            runtime = get_runtime(args.runtime)
        nstats = name_clusters(conn, runtime, vote_type=args.vote_type)
        print(
            f"Named {nstats['named']} cluster(s); "
            f"skipped {nstats['skipped']}; "
            f"{nstats['unparseable']} unparseable"
        )

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
