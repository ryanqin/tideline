"""L4 translation memory tools (translate-then-record pattern).

Two tools sharing the `memory` capability with the drawer tools:
- AddTranslationTool: silent translation pair recorder (the agent calls
  this AFTER producing a translation, to sediment the pair for later
  passive review)
- ListTranslationsTool: read-back

Translations are verbatim — every translation request adds a row, regardless
of whether it'll later promote to a candidate or card. Promotion logic lives
in Step 6+ and reads this table; nothing in this file knows about that.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from tideline.tools.base import Tool


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS translations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original TEXT NOT NULL,
            target_lang TEXT NOT NULL,
            translated TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


class AddTranslationTool(Tool):
    name = "add_translation"
    capability = "memory"
    schema: dict[str, str] = {
        "original": "string",
        "target_lang": "string",
        "translated": "string",
    }
    description = (
        "Record a completed translation. Use this AFTER you have produced "
        "a translation, to silently sediment the original-text + translated-"
        "text pair into the user's drawer for later passive review. Use only "
        "when the user explicitly requests a translation."
    )

    def run(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        conn: sqlite3.Connection = context["db"]
        cursor = conn.execute(
            "INSERT INTO translations (original, target_lang, translated) "
            "VALUES (?, ?, ?)",
            (args["original"], args["target_lang"], args["translated"]),
        )
        conn.commit()
        return f"translation #{cursor.lastrowid} recorded: {args['translated']}"


class ListTranslationsTool(Tool):
    name = "list_translations"
    capability = "memory"
    schema: dict[str, str] = {}
    description = (
        "List all recorded translations from the user's drawer. Use when the "
        "user asks to review or see what they've translated."
    )

    def run(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        conn: sqlite3.Connection = context["db"]
        rows = conn.execute(
            "SELECT id, original, target_lang, translated FROM translations "
            "ORDER BY id"
        ).fetchall()
        if not rows:
            return "no translations yet"
        return "\n".join(
            f"#{row[0]}: '{row[1]}' → ({row[2]}) '{row[3]}'" for row in rows
        )
