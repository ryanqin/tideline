"""L4 memory-as-tools: SQLite-backed drawer store.

Two tools sharing the `memory` capability:
- AddDrawerTool: silent sediment writer
- ListDrawersTool: read-back

Drawers are verbatim — 99% of them stay forever and never get promoted to
candidates / cards. SRS only kicks in for explicitly nodded cards, which is
a Step 5+ concern.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from tideline.tools.base import Tool


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS drawers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL
        )
        """
    )
    conn.commit()


class AddDrawerTool(Tool):
    name = "add_drawer"
    capability = "memory"
    schema: dict[str, str] = {"content": "string"}
    description = (
        "Add a content snippet to the silent memory drawer for later passive "
        "review. Use when the user explicitly asks to remember, save, or note "
        "something."
    )

    def run(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        conn: sqlite3.Connection = context["db"]
        cursor = conn.execute(
            "INSERT INTO drawers (content) VALUES (?)",
            (args["content"],),
        )
        conn.commit()
        return f"drawer #{cursor.lastrowid} added"


class ListDrawersTool(Tool):
    name = "list_drawers"
    capability = "memory"
    schema: dict[str, str] = {}
    description = (
        "List all content snippets currently stored in the memory drawer. "
        "Use when the user asks to see what's been saved or remembered."
    )

    def run(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        conn: sqlite3.Connection = context["db"]
        rows = conn.execute(
            "SELECT id, content FROM drawers ORDER BY id"
        ).fetchall()
        if not rows:
            return "no drawers yet"
        return "\n".join(f"#{row[0]}: {row[1]}" for row in rows)
