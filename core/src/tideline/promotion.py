"""Drawer → candidate promotion engine.

Scans the translations drawer, groups by (original, target_lang), and
promotes any pair whose occurrence count crosses `threshold` into the
candidates table. Idempotent: re-runs UPSERT on the unique key, so a
candidate's occurrence_count and last_seen_at stay current without
duplicating rows.

This is the "night-watch" sweep from the product design — silent, write-only,
no user notification. The agent reads the resulting candidates table via the
ListCandidatesTool when the user explicitly asks.

Usage:
  Programmatic:
    from tideline.promotion import promote_candidates
    n = promote_candidates(conn, threshold=3)

  CLI:
    python -m tideline.promotion --db /tmp/demo.db
    python -m tideline.promotion --db /tmp/demo.db --threshold 5
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


_DEFAULT_THRESHOLD = 3


def promote_candidates(
    conn: sqlite3.Connection,
    threshold: int = _DEFAULT_THRESHOLD,
) -> int:
    """Promote drawer entries crossing `threshold` into candidates.

    Returns the number of rows touched (inserted or updated).
    """
    if threshold < 1:
        raise ValueError(f"threshold must be >= 1, got {threshold}")

    rows = conn.execute(
        """
        SELECT
            original,
            target_lang,
            (SELECT translated FROM translations t2
             WHERE t2.original = t.original AND t2.target_lang = t.target_lang
             ORDER BY id DESC LIMIT 1) AS translated,
            COUNT(*) AS occurrence_count,
            MIN(created_at) AS first_seen_at,
            MAX(created_at) AS last_seen_at
        FROM translations t
        GROUP BY original, target_lang
        HAVING COUNT(*) >= ?
        """,
        (threshold,),
    ).fetchall()

    if not rows:
        return 0

    conn.executemany(
        """
        INSERT INTO candidates
            (original, target_lang, translated, occurrence_count,
             first_seen_at, last_seen_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(original, target_lang) DO UPDATE SET
            translated = excluded.translated,
            occurrence_count = excluded.occurrence_count,
            last_seen_at = excluded.last_seen_at
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tideline.promotion",
        description="Promote drawer entries to candidates by repetition count.",
    )
    parser.add_argument(
        "--db",
        required=True,
        help="SQLite path (use ':memory:' for ephemeral).",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=_DEFAULT_THRESHOLD,
        help=f"Minimum occurrence count to promote (default: {_DEFAULT_THRESHOLD}).",
    )
    args = parser.parse_args(argv)

    if args.db != ":memory:":
        Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)

    from tideline.tools import init_all_tables

    init_all_tables(conn)
    n = promote_candidates(conn, threshold=args.threshold)
    conn.close()

    print(f"Promoted {n} candidate(s) at threshold={args.threshold}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
