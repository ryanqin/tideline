"""L4 candidate surfacing tool.

The candidates table is the second tier of the drawer → candidate → card
pipeline. A row lands here only after `tideline.promotion.promote_candidates`
finds that an (original, target_lang) pair has been seen often enough to be
worth resurfacing.

This file owns the table schema and the read-back tool. The promotion engine
(which writes into this table) lives in `tideline.promotion` — separated so
the writer can run as a background sweep without dragging in the tool layer.

**Episodic anchoring (added 2026-05-11):** the `candidate_evidence` join
table links each candidate back to the specific translation rows that
contributed to it — so the UI can surface "ramen — your six encounters"
rather than "ramen × 6". See DESIGN.md §3.2.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from tideline.tools.base import Tool


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original TEXT NOT NULL,
            target_lang TEXT NOT NULL,
            translated TEXT NOT NULL,
            occurrence_count INTEGER NOT NULL,
            first_seen_at TIMESTAMP NOT NULL,
            last_seen_at TIMESTAMP NOT NULL,
            promoted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(original, target_lang)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_evidence (
            candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            translation_id INTEGER NOT NULL REFERENCES translations(id) ON DELETE CASCADE,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(candidate_id, translation_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_candidate_evidence_candidate "
        "ON candidate_evidence(candidate_id)"
    )
    conn.commit()


class ListCandidatesTool(Tool):
    name = "list_candidates"
    capability = "memory"
    schema: dict[str, str] = {}
    description = (
        "List items that have surfaced as candidates — terms the user has "
        "translated often enough that they may be worth learning. Use when "
        "the user asks what they've been seeing lately, what's emerging, or "
        "what to review."
    )

    def run(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        conn: sqlite3.Connection = context["db"]
        rows = conn.execute(
            "SELECT original, target_lang, translated, occurrence_count "
            "FROM candidates ORDER BY occurrence_count DESC, original"
        ).fetchall()
        if not rows:
            return "no candidates yet"
        return "\n".join(
            f"'{r[0]}' → ({r[1]}) '{r[2]}'  [seen {r[3]}x]" for r in rows
        )
