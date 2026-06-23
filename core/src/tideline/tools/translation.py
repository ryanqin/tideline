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

from tideline.intelligence.source_language import detect_script, normalize_language
from tideline.intelligence.translation_guard import (
    TranslationOutcome,
    judge_translation,
)
from tideline.tools.base import Tool


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS translations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original TEXT NOT NULL,
            target_lang TEXT NOT NULL,
            translated TEXT NOT NULL,
            source_lang TEXT,
            source TEXT,
            context_snippet TEXT,
            source_image BLOB,
            source_region TEXT,
            source_audio BLOB,
            session_id TEXT,
            scene_label TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Backfill columns for any pre-existing v0 schema. SQLite has no
    # "ADD COLUMN IF NOT EXISTS", so probe and add per missing column.
    existing = {row[1] for row in conn.execute("PRAGMA table_info(translations)")}
    for column, ddl in (
        ("source_lang", "ALTER TABLE translations ADD COLUMN source_lang TEXT"),
        ("source", "ALTER TABLE translations ADD COLUMN source TEXT"),
        ("context_snippet", "ALTER TABLE translations ADD COLUMN context_snippet TEXT"),
        ("session_id", "ALTER TABLE translations ADD COLUMN session_id TEXT"),
        # The captured source image (a menu photo / sign), kept as recall
        # material — never discarded after the VLM reads it (§3.2).
        ("source_image", "ALTER TABLE translations ADD COLUMN source_image BLOB"),
        # Where the word sits in its photo: JSON "[x0,y0,x1,y1]" normalized to
        # the stored image (device OCR fills it). Anchors the photo-word mask.
        ("source_region", "ALTER TABLE translations ADD COLUMN source_region TEXT"),
        # The captured recording itself (a heard phrase's WAV) — dictation
        # material, kept after the model transcribes it; the standard
        # pronunciation is NOT stored (TTS regenerates it from text).
        ("source_audio", "ALTER TABLE translations ADD COLUMN source_audio BLOB"),
        # The scene TYPE this was met in (拉面店 / 车站 / 咖啡馆) — a short label
        # the capture model reports, the key a theme clusters on (a kind of
        # place, across visits). The descriptive context_snippet stays the
        # per-moment gist; this is the coarse category. (§3.2)
        ("scene_label", "ALTER TABLE translations ADD COLUMN scene_label TEXT"),
    ):
        if column not in existing:
            conn.execute(ddl)
    # Drop the deprecated native_gloss column: Tideline now always translates
    # into the user's first language (target == native), so a gloss into that
    # language is moot. SQLite >= 3.35 supports DROP COLUMN.
    if "native_gloss" in existing:
        conn.execute("ALTER TABLE translations DROP COLUMN native_gloss")
    conn.commit()


class AddTranslationTool(Tool):
    name = "add_translation"
    capability = "memory"
    schema: dict[str, str] = {
        "original": "string",
        "source_lang": "string",
        "target_lang": "string",
        "translated": "string",
        "source": "string",
        "context_snippet": "string",
        "session_id": "string",
        "scene_label": "string",
    }
    description = (
        "Record a completed translation. Use this AFTER you have produced "
        "a translation, to silently sediment the original-text + translated-"
        "text pair into the user's sediment layer. Required args: original, "
        "source_lang (the language the original text is written in), "
        "target_lang, translated. Optional args: source (image/audio/text), "
        "context_snippet (surrounding text from OCR or transcript), "
        "session_id (groups translations from one outing/session), "
        "scene_label (a short 2-4 char type of place/scene this was met in, "
        "e.g. 拉面店 / 车站 / 咖啡馆 — the same kind of place gets the same "
        "label so it clusters across visits)."
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
        # The captured image bytes (a menu photo / sign) ride in via context from
        # the capture client (the image pipeline / Android shell), NEVER through
        # the LLM — the model produces the scene gist (context_snippet), not the
        # photo, and the tool schema stays text-only. Kept as recall material;
        # None for text / audio captures. (DESIGN §3.2)
        source_image = context.get("source_image")
        # The direction tag (source language → your first language) belongs ON
        # the translation, set the moment it's made: the model that just read and
        # translated the text knows its source language — with full context, so
        # better than an isolated later detect(). The agent passes it as
        # source_lang, NORMALIZED to the app's one spelling (a model says "ja",
        # the rest of the app says "Japanese" — they must bucket together). If
        # it's omitted/unknown, fall back to the deterministic script check (kana
        # → Japanese, hangul → Korean), leaving a genuinely ambiguous script
        # (kanji / Latin) NULL for a model sweep to backfill. (§3.3, two tags.)
        source_lang = normalize_language(args.get("source_lang")) or detect_script(
            args["original"]
        )
        # Tideline only translates INTO your first language (DESIGN §3.3), so a
        # same-language source or a plain echo isn't a real result — judge it
        # and refuse to sediment a non-translation, keeping the emergence loop
        # clean. We pass the app's best read of the source language (the agent's
        # report, else the deterministic script check), so the same-language
        # case is caught even when the model didn't label it. The verdict rides
        # back on the context so the HTTP layer can tell the user, honestly,
        # that this one was beyond reach. (Mirrors the Android shell's
        # TranslationGuard: fail empty, never with a wrong answer.)
        outcome = judge_translation(
            source=args["original"],
            translated=args["translated"],
            reported_lang=source_lang,
            native_lang=args["target_lang"],
        )
        context["translation_outcome"] = outcome.value
        if outcome is not TranslationOutcome.TRANSLATED:
            return (
                f"not recorded ({outcome.value}): no real translation into "
                f"{args['target_lang']} to sediment"
            )
        cursor = conn.execute(
            "INSERT INTO translations "
            "(original, target_lang, translated, source_lang, source, "
            "context_snippet, session_id, source_image, scene_label) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                args["original"],
                args["target_lang"],
                args["translated"],
                source_lang,
                source,
                args.get("context_snippet"),
                session_id,
                source_image,
                args.get("scene_label") or context.get("scene_label"),
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
