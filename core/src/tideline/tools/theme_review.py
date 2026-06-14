"""Theme review tier — spaced repetition for a SCENE TYPE.

A theme is a kind of place clustered across visits (DESIGN §3.2 / §10.3) — all
the words ever met at a ramen shop, a station, a café. Unlike a card it has no
stable row of its own: theme clusters are rebuilt by the night-watch sweep, so
their cluster ids churn. The stable handle is the **scene_label** every member
shares (a theme IS a scene type). So the review schedule lives in its own table
keyed on scene_label, decoupled from the rebuilt cluster rows: a sweep can
recompute the clusters all it likes and the "when does this scene wash back
ashore" state survives.

Reviewing a theme is masked recall of the whole scene type — you see the
meanings, reach for the words, and self-grade once. The Leitner ladder is
shared with cards (`card.reschedule`) so both review units ride one schedule.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from tideline.tools.card import reschedule


def init_db(conn: sqlite3.Connection) -> None:
    # Themes re-keyed from capture session to scene type (2026-06-13). A pre-
    # existing session-keyed table is dropped: review state is forward-looking
    # (a fresh scale, like the casing change), not migrated across the re-key.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(theme_reviews)")}
    if cols and "scene_label" not in cols:
        conn.execute("DROP TABLE theme_reviews")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS theme_reviews (
            scene_label TEXT PRIMARY KEY,
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
    scene_label: str,
    remembered: bool,
    now: datetime,
) -> int:
    """Record one masked-recall outcome for a scene type and reschedule it.

    Upsert on scene_label (a never-reviewed scene starts at strength 0). Returns
    the scene's new strength. The schedule is internal (DESIGN §10.3) — the
    caller records the outcome, never shows a due date or count.
    """
    row = conn.execute(
        "SELECT strength FROM theme_reviews WHERE scene_label = ?", (scene_label,)
    ).fetchone()
    current = row[0] if row is not None else 0
    strength, due_iso = reschedule(current or 0, remembered, now)
    conn.execute(
        """
        INSERT INTO theme_reviews
            (scene_label, strength, due_at, last_reviewed_at, reviews)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(scene_label) DO UPDATE SET
            strength = excluded.strength,
            due_at = excluded.due_at,
            last_reviewed_at = excluded.last_reviewed_at,
            reviews = theme_reviews.reviews + 1
        """,
        (scene_label, strength, due_iso, now.isoformat()),
    )
    conn.commit()
    return strength


def review_states(
    conn: sqlite3.Connection, now: datetime
) -> dict[str, dict[str, Any]]:
    """Map scene_label → {strength, due} for every *reviewed* scene. A scene with
    no row here has never been reviewed → the caller defaults it to due=True,
    strength=0 (a new scene the tide should bring ashore, mirroring a brand-new
    card)."""
    now_iso = now.isoformat()
    rows = conn.execute(
        "SELECT scene_label, strength, due_at FROM theme_reviews"
    ).fetchall()
    return {
        label: {"strength": strength, "due": due_at is None or due_at <= now_iso}
        for label, strength, due_at in rows
    }
