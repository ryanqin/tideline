"""L4 translation memory tools (translate-then-record pattern).

Two tools sharing the `memory` capability with the drawer tools:
- AddTranslationTool: silent translation pair recorder (the agent calls
  this AFTER producing a translation, to sediment the pair for later
  passive review)
- ListTranslationsTool: read-back

Translations are verbatim — every translation request adds a row, regardless
of whether it'll later promote to a candidate or card.

**Episodic anchoring (added 2026-05-11):** each row carries optional
context fields (`source`, `context_snippet`, `session_id`) so that a later
candidate / card can be traced back to the lived moment of original
encounter. See DESIGN.md §3.2.
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
            source TEXT,
            context_snippet TEXT,
            session_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Backfill columns for any pre-existing v0 schema. SQLite has no
    # "ADD COLUMN IF NOT EXISTS", so probe and add per missing column.
    existing = {row[1] for row in conn.execute("PRAGMA table_info(translations)")}
    for column, ddl in (
        ("source", "ALTER TABLE translations ADD COLUMN source TEXT"),
        ("context_snippet", "ALTER TABLE translations ADD COLUMN context_snippet TEXT"),
        ("session_id", "ALTER TABLE translations ADD COLUMN session_id TEXT"),
    ):
        if column not in existing:
            conn.execute(ddl)
    conn.commit()


class AddTranslationTool(Tool):
    name = "add_translation"
    capability = "memory"
    schema: dict[str, str] = {
        "original": "string",
        "target_lang": "string",
        "translated": "string",
        "source": "string",
        "context_snippet": "string",
        "session_id": "string",
    }
    description = (
        "Record a completed translation. Use this AFTER you have produced "
        "a translation, to silently sediment the original-text + translated-"
        "text pair into the user's sediment layer. Required args: original, "
        "target_lang, translated. Optional args: source (image/audio/text), "
        "context_snippet (surrounding text from OCR or transcript), "
        "session_id (groups translations from one outing/session)."
    )

    def run(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        conn: sqlite3.Connection = context["db"]
        # Source / session priority: explicit arg from the LLM > context-
        # injected default from the client (CLI, HTTP, Android shell) > None.
        # This lets the keyboard CLI default to source="text", the image
        # pipeline default to source="image", etc., without requiring the
        # LLM to reason about which input modality fired.
        source = args.get("source") or context.get("source")
        session_id = args.get("session_id") or context.get("session_id")
        cursor = conn.execute(
            "INSERT INTO translations "
            "(original, target_lang, translated, source, context_snippet, session_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                args["original"],
                args["target_lang"],
                args["translated"],
                source,
                args.get("context_snippet"),
                session_id,
            ),
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
