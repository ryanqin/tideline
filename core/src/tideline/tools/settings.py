"""L0 identity / app settings — a tiny key-value store in SQLite.

The first (and, for the MVP, only) key is `native_lang`: the user's first
language. It's the L0 identity layer from DESIGN.md — the learnings view reads
it to decide when a native-language gloss is worth showing and to localize
labels.

Lives in core (not the web layer) so every client — CLI, web, future Android —
reads the same persisted setting. The agent never touches it: this is not a
tool, just a setting the UI reads and writes directly (DESIGN.md §3.1,
"Tideline is not a chatbot").
"""

from __future__ import annotations

import sqlite3

# The user's first language, used to suppress glosses that would be redundant
# (no point glossing into a language the user already speaks natively). Chinese
# is the MVP default until the user picks one; generating a per-user native
# gloss in the real translation flow is ②b-2's second cut and needs a model.
DEFAULT_NATIVE_LANG = "Chinese"


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.commit()


def get_setting(conn: sqlite3.Connection, key: str, default: str) -> str:
    """Read a setting, falling back to `default` when it was never set."""
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    return row[0] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Write a setting, upserting on the key so there's one row per setting."""
    conn.execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()
