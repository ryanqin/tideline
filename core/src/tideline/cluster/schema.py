"""The engine's tables, and the migration that reshaped them.

`init_db` is called by every entry point (CLI, web, bench, tests) through
`tools.init_all_tables`, so it has to stay idempotent.
"""

from __future__ import annotations

import sqlite3


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pair_similarity_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            translation_id_a INTEGER NOT NULL REFERENCES translations(id) ON DELETE CASCADE,
            translation_id_b INTEGER NOT NULL REFERENCES translations(id) ON DELETE CASCADE,
            vote TEXT NOT NULL CHECK (vote IN ('yes', 'no')),
            vote_type TEXT NOT NULL DEFAULT 'concept' CHECK (vote_type IN ('concept', 'theme')),
            model TEXT,
            voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (translation_id_a < translation_id_b)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_votes_pair "
        "ON pair_similarity_votes(translation_id_a, translation_id_b)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            vote_type TEXT NOT NULL DEFAULT 'concept' CHECK (vote_type IN ('concept', 'theme')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cluster_members (
            cluster_id INTEGER NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
            translation_id INTEGER NOT NULL REFERENCES translations(id) ON DELETE CASCADE,
            UNIQUE(cluster_id, translation_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cluster_members_cluster "
        "ON cluster_members(cluster_id)"
    )
    _migrate_vote_type(conn)
    conn.commit()


def _migrate_vote_type(conn: sqlite3.Connection) -> None:
    """Backfill the vote_type partition column on pre-2026-05-26 schemas.

    The vote/cluster tables now multiplex two clustering relations by
    `vote_type`: 'concept' (B1 synonym aggregation — the original Tier B
    behavior, feeds the by-language lens) and 'theme' (B7 relatedness —
    feeds album-style recall). Fresh tables declare the column inline (with
    a CHECK); any DB created before the partition gets it here via ALTER,
    existing rows backfilled to 'concept' — exactly what they were.
    """
    votes_cols = {row[1] for row in conn.execute("PRAGMA table_info(pair_similarity_votes)")}
    if "vote_type" not in votes_cols:
        conn.execute(
            "ALTER TABLE pair_similarity_votes ADD COLUMN vote_type TEXT NOT NULL "
            "DEFAULT 'concept' CHECK (vote_type IN ('concept', 'theme'))"
        )
    clusters_cols = {row[1] for row in conn.execute("PRAGMA table_info(clusters)")}
    if "vote_type" not in clusters_cols:
        conn.execute(
            "ALTER TABLE clusters ADD COLUMN vote_type TEXT NOT NULL "
            "DEFAULT 'concept' CHECK (vote_type IN ('concept', 'theme'))"
        )
