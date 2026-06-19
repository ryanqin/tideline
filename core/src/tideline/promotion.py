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
from collections import defaultdict
from pathlib import Path


_DEFAULT_THRESHOLD = 3


def canonical_word(word: str) -> str:
    """Casing-normalize a learned word: "lowercase except proper nouns".

    Signage shouts common nouns in all-caps (PREMIUM, ALCOHOL); typed text and
    other captures meet them as "Premium" / "premium". Left alone they split
    into two candidates and two review cards. The learned word is one word, so
    fold case for IDENTITY — but display the lemma, lowercased, EXCEPT where the
    casing likely IS the word: a short all-caps acronym (NASA, USB) or an
    internally-capitalised name (iPhone, eBay). A word with no ASCII-cased
    letters (CJK, kana) is returned untouched.

    Deterministic and idempotent — canonical(canonical(x)) == canonical(x) — so
    it can key the candidates table directly. Proper-noun detection is fuzzy, so
    this is a garnish-level heuristic ([[tideline_engineering_vs_reasoning]]):
    the model is already asked to skip proper names, and a miss here is only
    cosmetic, never load-bearing.
    """
    letters = [c for c in word if c.isascii() and c.isalpha()]
    if not letters:
        return word
    # an internal uppercase (an upper right after a lower): iPhone, McD, eBay
    if any(cur.isupper() and prev.islower() for prev, cur in zip(word, word[1:])):
        return word
    # a short all-caps acronym keeps its shout: NASA, USB, EU
    if len(letters) <= 4 and all(c.isupper() for c in letters):
        return word
    return word.lower()


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

    # Group case-insensitively (COLLATE NOCASE) so PREMIUM and Premium count as
    # ONE word's occasions — otherwise the same word, shouted on a sign and
    # typed in lower-case elsewhere, splits its evidence across two candidates
    # and neither may reach the threshold. The stored `original` is then
    # canonicalized below, so the candidate's UNIQUE(original) key is stable.
    rows = conn.execute(
        """
        SELECT
            original,
            target_lang,
            (SELECT translated FROM translations t2
             WHERE t2.original = t.original COLLATE NOCASE
               AND t2.target_lang = t.target_lang
             ORDER BY id DESC LIMIT 1) AS translated,
            COUNT(*) AS occurrence_count,
            MIN(created_at) AS first_seen_at,
            MAX(created_at) AS last_seen_at
        FROM translations t
        GROUP BY original COLLATE NOCASE, target_lang
        HAVING COUNT(DISTINCT COALESCE(session_id, 'row#' || id)) >= ?
        """,
        (threshold,),
    ).fetchall()

    if not rows:
        return 0

    # Canonicalize the display casing (lowercase except proper nouns); the
    # arbitrary group representative SQLite returns becomes deterministic.
    rows = [(canonical_word(o), *rest) for (o, *rest) in rows]

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
    # contributed — case-insensitively, since the candidate's stored original
    # is canonical ("premium") while the drawer keeps each as met ("PREMIUM").
    conn.execute(
        """
        INSERT OR IGNORE INTO candidate_evidence (candidate_id, translation_id)
        SELECT c.id, t.id
        FROM candidates c
        JOIN translations t
          ON t.original = c.original COLLATE NOCASE
         AND t.target_lang = c.target_lang
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


def heal_casing_splits(conn: sqlite3.Connection) -> int:
    """Collapse candidates that split on casing before `canonical_word` keyed
    the table — a one-time, idempotent heal for databases that promoted
    "PREMIUM" and "Premium" as two separate candidates (and two review cards)
    under an older build. Each (canonical, target_lang) group folds onto a
    single canonical candidate, carrying the strongest review progress forward
    so the user never re-learns a word they already knew; occurrence counts and
    evidence are left for `promote_candidates` to re-derive (it groups
    case-insensitively). This is the lossless alternative to the only remedies
    that existed before — a clean install or sinking the duplicate by hand.

    A no-op once healed (no candidate has a non-canonical `original` left), so
    it is safe to run in the boot sweep ahead of `promote_candidates`. Returns
    the number of duplicate candidate rows removed.
    """
    groups: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
    for cid, original, target_lang in conn.execute(
        "SELECT id, original, target_lang FROM candidates"
    ):
        groups[(canonical_word(original), target_lang)].append((cid, original))

    removed = 0
    for (canon, _target_lang), members in groups.items():
        # Already healed: a lone candidate whose original is already canonical.
        if len(members) == 1 and members[0][1] == canon:
            continue
        ids = [cid for cid, _ in members]

        # The survivor is the row already in canonical form; if none is (the DB
        # was only ever swept by pre-canonical code), rename the lowest id so a
        # canonical row exists to fold the rest onto.
        survivor = next((cid for cid, orig in members if orig == canon), None)
        if survivor is None:
            survivor = min(ids)
            conn.execute(
                "UPDATE candidates SET original = ? WHERE id = ?", (canon, survivor)
            )

        # Carry the strongest review progress onto the survivor's card: highest
        # box wins (don't make a known word new again), then most reviews, then
        # most recently seen. The merged word is active unless every variant was
        # sunk — sinking one casing of a word shouldn't bury a kept one. Cards
        # exist from a prior boot's auto-promote (the very rows we're healing),
        # so the survivor's card is there to update.
        placeholders = ",".join("?" * len(ids))
        cards = conn.execute(
            f"SELECT state, strength, due_at, last_reviewed_at, reviews "
            f"FROM cards WHERE candidate_id IN ({placeholders})",
            ids,
        ).fetchall()
        if cards:
            best = max(cards, key=lambda c: (c[1] or 0, c[4] or 0, c[3] or ""))
            state = "sunk" if all(c[0] == "sunk" for c in cards) else "active"
            conn.execute(
                "UPDATE cards SET original = ?, state = ?, strength = ?, due_at = ?, "
                "last_reviewed_at = ?, reviews = ? WHERE candidate_id = ?",
                (canon, state, best[1], best[2], best[3], best[4], survivor),
            )

        dups = [cid for cid in ids if cid != survivor]
        if dups:
            dup_ph = ",".join("?" * len(dups))
            conn.execute(f"DELETE FROM cards WHERE candidate_id IN ({dup_ph})", dups)
            conn.execute(
                f"DELETE FROM candidate_evidence WHERE candidate_id IN ({dup_ph})", dups
            )
            conn.execute(f"DELETE FROM candidates WHERE id IN ({dup_ph})", dups)
            removed += len(dups)

    conn.commit()
    return removed


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
