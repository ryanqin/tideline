"""Theme review tier — spaced repetition for a remembered SCENE.

A theme is one capture session's worth of co-occurring words, in one language
(DESIGN §3.2 / §3.3 / §10.3). Unlike a card it has no stable row of its own —
theme clusters are rebuilt by the night-watch sweep, so their cluster ids
churn. The stable handle is the **session_id** every member of a theme shares
(a theme IS a capture session). So the review schedule lives in its own table
keyed on session_id, decoupled from the rebuilt cluster rows: a sweep can
recompute the clusters all it likes and the "when does this scene wash back
ashore" state survives.

Single-language is enforced at grouping time (cluster.py), so session_id keys a
theme uniquely for the usual single-language sitting (every seed, most live).
The rare live sitting that mixed two languages splits into two scenes that
currently share this one session_id's review state — a known limitation; the
fix would be a (session_id, source_lang) key, deferred until mixed sittings are
common enough to matter.

Reviewing a theme is masked recall of the whole scene — you see the meanings,
reach for the words, and self-grade once for the night. The Leitner ladder is
shared with cards (`card.reschedule`) so both review units ride one schedule.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from tideline.tools.card import reschedule


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS theme_reviews (
            session_id TEXT PRIMARY KEY,
            strength INTEGER NOT NULL DEFAULT 0,
            due_at TIMESTAMP,
            last_reviewed_at TIMESTAMP,
            reviews INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()


def review_theme(
    conn: sqlite3.Connection,
    session_id: str,
    remembered: bool,
    now: datetime,
) -> int:
    """Record one masked-recall outcome for a scene and reschedule it.

    Upsert on session_id (a never-reviewed scene starts at strength 0). Returns
    the scene's new strength. The schedule is internal (DESIGN §10.3) — the
    caller records the outcome, never shows a due date or count.
    """
    row = conn.execute(
        "SELECT strength FROM theme_reviews WHERE session_id = ?", (session_id,)
    ).fetchone()
    current = row[0] if row is not None else 0
    strength, due_iso = reschedule(current or 0, remembered, now)
    conn.execute(
        """
        INSERT INTO theme_reviews
            (session_id, strength, due_at, last_reviewed_at, reviews)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(session_id) DO UPDATE SET
            strength = excluded.strength,
            due_at = excluded.due_at,
            last_reviewed_at = excluded.last_reviewed_at,
            reviews = theme_reviews.reviews + 1
        """,
        (session_id, strength, due_iso, now.isoformat()),
    )
    conn.commit()
    return strength


def review_states(
    conn: sqlite3.Connection, now: datetime
) -> dict[str, dict[str, Any]]:
    """Map session_id → {strength, due} for every *reviewed* scene. A scene with
    no row here has never been reviewed → the caller defaults it to due=True,
    strength=0 (a new scene the tide should bring ashore, mirroring a brand-new
    card)."""
    now_iso = now.isoformat()
    rows = conn.execute(
        "SELECT session_id, strength, due_at FROM theme_reviews"
    ).fetchall()
    return {
        sid: {"strength": strength, "due": due_at is None or due_at <= now_iso}
        for sid, strength, due_at in rows
    }
