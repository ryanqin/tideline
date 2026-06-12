"""Tier-promotion engine: drawer → candidate (night-watch) + candidate → card (user nod).

Scans the translations drawer, groups by (original, target_lang), and
promotes any pair met in at least `threshold` distinct OCCASIONS (capture
sessions) into the candidates table. Counting sessions, not rows, is what
keeps a re-photographed menu from inflating every word on it at once: ten
captures in one sitting are one encounter. Rows with no session (debug
paths, pre-session data) each count as their own occasion. Idempotent: re-runs UPSERT on the unique key, so a
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

    Also writes one `candidate_evidence` row per contributing translation,
    preserving the back-link from each candidate to the lived moments it
    accumulated from (the episodic-anchoring principle from DESIGN.md §3.2).

    Returns the number of candidate rows touched (inserted or updated).
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
        HAVING COUNT(DISTINCT COALESCE(session_id, 'row#' || id)) >= ?
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

    # Evidence rows: link each candidate to every translation that
    # contributed. UNIQUE constraint makes this idempotent across re-runs.
    conn.execute(
        """
        INSERT OR IGNORE INTO candidate_evidence (candidate_id, translation_id)
        SELECT c.id, t.id
        FROM candidates c
        JOIN translations t
          ON t.original = c.original AND t.target_lang = c.target_lang
        """
    )
    conn.commit()
    return len(rows)


def promote_to_card(conn: sqlite3.Connection, candidate_id: int) -> int | None:
    """Promote one candidate into a card — the explicit user "nod".

    Unlike `promote_candidates` (the silent night-watch sweep), this is
    user-driven: cards are the only tier that enters review, and they appear
    only when the user deliberately promotes a candidate (DESIGN.md §3.1).

    Idempotent on candidate_id: re-promoting an existing card is a no-op. The
    card stores `candidate_id`, so its episodic evidence stays reachable — and
    keeps growing — through `candidate_evidence`; we don't freeze a copy.

    Returns the card id, or None if the candidate doesn't exist.
    """
    cand = conn.execute(
        "SELECT original, target_lang, translated FROM candidates WHERE id = ?",
        (candidate_id,),
    ).fetchone()
    if cand is None:
        return None

    conn.execute(
        """
        INSERT INTO cards (candidate_id, original, target_lang, translated)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(candidate_id) DO NOTHING
        """,
        (candidate_id, cand[0], cand[1], cand[2]),
    )
    conn.commit()

    row = conn.execute(
        "SELECT id FROM cards WHERE candidate_id = ?", (candidate_id,)
    ).fetchone()
    return row[0] if row else None


def auto_promote_cards(conn: sqlite3.Connection) -> int:
    """Opt-out card generation (DESIGN.md §3.1, 2026-05-25 revision).

    Every candidate automatically gets a review card; the user curates the
    deck by *sinking* cards they don't want, never by promoting. Engineering
    surfaces everything (the load-bearing path); the user only does
    subtraction. This runs in the night-watch sweep alongside
    `promote_candidates`, so cards appear without any explicit nod.

    `INSERT OR IGNORE` on the UNIQUE(candidate_id) key is what makes "a sunk
    card stays sunk" hold: a card the user already sank (or any card that
    already exists) is left untouched, so a later sweep never resurfaces it.
    Returns the number of new cards created.

    A card's STATE is the user's (sunk stays sunk), but its meaning is the
    candidate's projection, not a creation-time snapshot: when a later
    capture improves the rendering (the candidate keeps the latest), the
    card's translated follows. Without this a card frozen at creation keeps
    quizzing an old translation after the drawer has moved on.
    """
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO cards (candidate_id, original, target_lang, translated)
        SELECT id, original, target_lang, translated FROM candidates
        """
    )
    conn.execute(
        """
        UPDATE cards SET translated =
            (SELECT translated FROM candidates WHERE candidates.id = cards.candidate_id)
        WHERE translated <>
            (SELECT translated FROM candidates WHERE candidates.id = cards.candidate_id)
        """
    )
    conn.commit()
    return cur.rowcount


def sink_card(conn: sqlite3.Connection, card_id: int) -> bool:
    """Push a card back down to sediment — the only curation gesture in the
    opt-out deck. Idempotent. Returns True if a card with that id exists.

    A sunk card drops out of the review deck (readers filter on
    state='active') and is never resurrected by `auto_promote_cards`.
    """
    cur = conn.execute(
        "UPDATE cards SET state = 'sunk' WHERE id = ?", (card_id,)
    )
    conn.commit()
    return cur.rowcount > 0


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
