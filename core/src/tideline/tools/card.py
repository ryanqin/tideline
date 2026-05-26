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
from typing import Any

from tideline.tools.base import Tool


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
    existing = {row[1] for row in conn.execute("PRAGMA table_info(cards)")}
    if "state" not in existing:
        conn.execute(
            "ALTER TABLE cards ADD COLUMN state TEXT NOT NULL DEFAULT 'active'"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cards_candidate ON cards(candidate_id)"
    )
    conn.commit()


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
