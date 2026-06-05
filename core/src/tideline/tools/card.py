"""L4 card tier — the user-nodded top of the drawer → candidate → card pipeline.

A row lands here only when the user *explicitly* promotes a candidate (the
"nod" from DESIGN.md §3.1 — cards are the only tier that enters the review
system; drawers and candidates never do). This file owns the table schema and
the read-back tool; the promotion writer (`tideline.promotion.promote_to_card`)
is separate, mirroring how the candidates table and its night-watch writer split.

**Episodic anchoring (DESIGN.md §3.2):** a card stores `candidate_id`, so its
provenance — the stack of lived moments — is reachable live through
`candidate_evidence → translations`. We deliberately do NOT freeze a copy of the
evidence: the moments keep accumulating as the user re-encounters the term, and
that growing stack is the point.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from tideline.tools.base import Tool


# Spaced-repetition schedule (DESIGN §10.3): a gentle Leitner ladder mapping a
# card's `strength` (box, 0 = new) to the number of days until it next becomes
# due. Remembered climbs a box (interval grows), forgotten drops a box (returns
# sooner). The schedule is INTERNAL — never shown as a due date or count; it
# only decides which shell the tide carries ashore. Engineering bears this
# weight; no model is involved (see tideline_engineering_vs_reasoning).
_REVIEW_INTERVALS_DAYS = (0, 1, 3, 7, 16, 35, 75)


def reschedule(strength: int, remembered: bool, now: datetime) -> tuple[int, str]:
    """One Leitner step on the shared ladder: a remembered item climbs a box
    (its interval grows), a forgotten one drops a box (it returns sooner).
    Returns ``(new_strength, due_at_iso)``. Both the card review and the theme
    review (`theme_review.review_theme`) go through this, so the spaced-
    repetition schedule stays one source of truth across review units."""
    max_box = len(_REVIEW_INTERVALS_DAYS) - 1
    strength = strength or 0
    strength = min(strength + 1, max_box) if remembered else max(strength - 1, 0)
    due = now + timedelta(days=_REVIEW_INTERVALS_DAYS[strength])
    return strength, due.isoformat()


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            original TEXT NOT NULL,
            target_lang TEXT NOT NULL,
            translated TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'active',
            strength INTEGER NOT NULL DEFAULT 0,
            due_at TIMESTAMP,
            last_reviewed_at TIMESTAMP,
            reviews INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(candidate_id)
        )
        """
    )
    # Opt-out lifecycle (DESIGN.md §3.1, 2026-05-25 revision): cards are
    # auto-generated and the user curates by *sinking* the ones they don't
    # want — `state` is 'active' (in the review deck) or 'sunk' (back to
    # sediment, never resurfaced). Backfill the column for any pre-opt-out
    # schema; existing cards default to 'active', which is the right
    # migration — they were nodded in under the old opt-in flow.
    #
    # Review-state columns (DESIGN §10.3, 2026-06-03): `strength`/`due_at`/
    # `last_reviewed_at`/`reviews` carry the spaced-repetition schedule. A
    # back-filled card starts at strength 0 with NULL due_at — i.e. new and
    # ready to surface, which is the right default for one promoted before
    # the review loop existed.
    existing = {row[1] for row in conn.execute("PRAGMA table_info(cards)")}
    migrations = {
        "state": "ALTER TABLE cards ADD COLUMN state TEXT NOT NULL DEFAULT 'active'",
        "strength": "ALTER TABLE cards ADD COLUMN strength INTEGER NOT NULL DEFAULT 0",
        "due_at": "ALTER TABLE cards ADD COLUMN due_at TIMESTAMP",
        "last_reviewed_at": "ALTER TABLE cards ADD COLUMN last_reviewed_at TIMESTAMP",
        "reviews": "ALTER TABLE cards ADD COLUMN reviews INTEGER NOT NULL DEFAULT 0",
    }
    for column, ddl in migrations.items():
        if column not in existing:
            conn.execute(ddl)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cards_candidate ON cards(candidate_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cards_due ON cards(state, due_at)"
    )
    conn.commit()


def review_card(
    conn: sqlite3.Connection,
    card_id: int,
    remembered: bool,
    now: datetime,
) -> int | None:
    """Record one masked-recall outcome and reschedule the card.

    Deterministic spaced repetition: a remembered card climbs one box (its
    interval grows), a forgotten one drops a box (it returns sooner). Writes
    the new due time as an ISO string; the schedule is internal (DESIGN §10.3).
    Returns the card's new `strength`, or None if the card doesn't exist.
    """
    row = conn.execute(
        "SELECT strength FROM cards WHERE id = ?", (card_id,)
    ).fetchone()
    if row is None:
        return None
    strength, due_iso = reschedule(row[0] or 0, remembered, now)
    conn.execute(
        "UPDATE cards SET strength = ?, due_at = ?, last_reviewed_at = ?, "
        "reviews = reviews + 1 WHERE id = ?",
        (strength, due_iso, now.isoformat(), card_id),
    )
    conn.commit()
    return strength


def due_cards(
    conn: sqlite3.Connection,
    now: datetime,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Active cards ready for review at `now`: never-reviewed (NULL due_at)
    first, then those whose due time has passed, soonest-overdue first. This is
    what the tide draws ashore — the caller renders shells, never a count
    (DESIGN §10.3). `limit` lets the shore keep it a calm few.
    """
    sql = (
        "SELECT id, candidate_id, original, target_lang, translated, strength "
        "FROM cards WHERE state = 'active' "
        "AND (due_at IS NULL OR due_at <= ?) "
        "ORDER BY (due_at IS NULL) DESC, due_at ASC, created_at ASC, id ASC"
    )
    params: list[Any] = [now.isoformat()]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    rows = conn.execute(sql, params).fetchall()
    return [
        {
            "id": r[0],
            "candidate_id": r[1],
            "original": r[2],
            "target_lang": r[3],
            "translated": r[4],
            "strength": r[5],
        }
        for r in rows
    ]


class ListCardsTool(Tool):
    name = "list_cards"
    capability = "memory"
    schema: dict[str, str] = {}
    description = (
        "List cards the user has promoted for review — the terms they have "
        "explicitly chosen to learn. Use when the user asks what they are "
        "actively studying."
    )

    def run(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        conn: sqlite3.Connection = context["db"]
        rows = conn.execute(
            "SELECT original, target_lang, translated FROM cards "
            "WHERE state = 'active' ORDER BY created_at DESC, original"
        ).fetchall()
        if not rows:
            return "no cards yet"
        return "\n".join(f"'{r[0]}' → ({r[1]}) '{r[2]}'" for r in rows)
