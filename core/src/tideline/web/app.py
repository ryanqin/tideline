"""FastAPI app factory for the Tideline web playground.

Mirrors the CLI startup hook exactly: init schema, run the promote +
cluster sweeps, then serve. Each HTTP request opens its own SQLite
connection so the agent loop stays thread-friendly for uvicorn's
async runtime.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tideline.agent import Agent
from tideline.cluster import cluster_sweep
from tideline.cluster import init_db as init_cluster_db
from tideline.promotion import promote_candidates, promote_to_card
from tideline.runtimes import get_runtime
from tideline.tools import AddTranslationTool, ToolRegistry, init_all_tables


_DEFAULT_DB = Path(".tideline") / "drawers.db"
_STATIC_DIR = Path(__file__).parent / "static"

# L0 Identity (MVP): the user's first language. A persisted setting + UI control
# is ②b-2; for now it's a fixed default the learnings view uses to (a) decide when
# a native-language gloss is worth showing and (b) localize labels.
_NATIVE_LANG = "Chinese"

_TIDELINE_SYSTEM = (
    "You are Tideline, a local-first translation engine. "
    "When the user provides text to translate: first call the add_translation "
    "tool with (original, target_lang, translated), then respond to the user "
    "with only the translated text — no preamble, no quotation marks, no "
    "commentary."
)


class TranslateRequest(BaseModel):
    text: str
    target_lang: str = "Chinese"


class TranslateResponse(BaseModel):
    translated: str
    source: str = "text"


class PromoteRequest(BaseModel):
    candidate_id: int


def _connect(db_path: str) -> sqlite3.Connection:
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    init_all_tables(conn)
    init_cluster_db(conn)
    return conn


def create_app(
    runtime_name: str = "mock",
    db_path: str | None = None,
) -> FastAPI:
    """Build the FastAPI app. Defaults match the CLI client.

    A single runtime instance is shared across requests so the LLM
    (when llama_cpp) only loads once. Each request opens its own DB
    connection.
    """
    db = db_path or str(_DEFAULT_DB)
    runtime = get_runtime(runtime_name)

    # Startup sweep — same shape as cli/__main__.py
    boot_conn = _connect(db)
    promote_candidates(boot_conn)
    try:
        cluster_sweep(boot_conn, runtime)
    except Exception:
        pass
    boot_conn.close()

    app = FastAPI(title="Tideline", description="Local-first translation playground")

    @app.get("/")
    def root() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/learnings")
    def learnings_page() -> FileResponse:
        return FileResponse(_STATIC_DIR / "learnings.html")

    @app.post("/api/translate", response_model=TranslateResponse)
    def translate(req: TranslateRequest) -> TranslateResponse:
        if not req.text.strip():
            raise HTTPException(status_code=400, detail="text is empty")
        conn = _connect(db)
        try:
            registry = ToolRegistry()
            registry.register(AddTranslationTool)
            agent = Agent(
                runtime,
                registry=registry,
                context={"db": conn, "source": "text"},
                system_message=_TIDELINE_SYSTEM,
            )
            prompt = f"translate {req.text} to {req.target_lang}"
            translated = agent.run(prompt)
        finally:
            conn.close()
        return TranslateResponse(translated=translated, source="text")

    @app.get("/api/clusters")
    def clusters() -> list[dict[str, Any]]:
        conn = _connect(db)
        try:
            rows = conn.execute(
                "SELECT id, title FROM clusters ORDER BY id"
            ).fetchall()
            result: list[dict[str, Any]] = []
            for cid, title in rows:
                members = conn.execute(
                    """
                    SELECT t.original, t.translated, t.context_snippet, t.source_lang, t.native_gloss
                    FROM cluster_members cm
                    JOIN translations t ON t.id = cm.translation_id
                    WHERE cm.cluster_id = ?
                    ORDER BY t.id
                    """,
                    (cid,),
                ).fetchall()
                result.append({
                    "id": cid,
                    "title": title,
                    "members": [
                        {"original": o, "translated": tr, "context": ctx or "",
                         "source_lang": sl, "native_gloss": ng}
                        for o, tr, ctx, sl, ng in members
                    ],
                })
            return result
        finally:
            conn.close()

    @app.get("/api/candidates")
    def candidates() -> list[dict[str, Any]]:
        conn = _connect(db)
        try:
            rows = conn.execute(
                """
                SELECT id, original, target_lang, translated, occurrence_count,
                    (SELECT t.source_lang FROM translations t
                     WHERE t.original = candidates.original
                       AND t.target_lang = candidates.target_lang
                     ORDER BY t.id DESC LIMIT 1) AS source_lang,
                    (SELECT t.native_gloss FROM translations t
                     WHERE t.original = candidates.original
                       AND t.target_lang = candidates.target_lang
                       AND t.native_gloss IS NOT NULL
                     ORDER BY t.id DESC LIMIT 1) AS native_gloss
                FROM candidates ORDER BY occurrence_count DESC, original LIMIT 50
                """
            ).fetchall()
            return [
                {"id": cid, "original": o, "source_lang": sl, "target_lang": tl,
                 "translated": tr, "count": cnt, "native_gloss": ng}
                for cid, o, tl, tr, cnt, sl, ng in rows
            ]
        finally:
            conn.close()

    @app.get("/api/cards")
    def cards() -> list[dict[str, Any]]:
        """Review deck: each promoted card with the stack of lived moments it
        grew from (episodic anchoring, DESIGN.md §3.2) — reached live through
        candidate_evidence, never a frozen copy, so the stack keeps growing."""
        conn = _connect(db)
        try:
            rows = conn.execute(
                """
                SELECT id, candidate_id, original, target_lang, translated,
                    (SELECT t.source_lang FROM candidate_evidence ce
                     JOIN translations t ON t.id = ce.translation_id
                     WHERE ce.candidate_id = cards.candidate_id
                     ORDER BY t.id DESC LIMIT 1) AS source_lang,
                    (SELECT t.native_gloss FROM candidate_evidence ce
                     JOIN translations t ON t.id = ce.translation_id
                     WHERE ce.candidate_id = cards.candidate_id
                       AND t.native_gloss IS NOT NULL
                     ORDER BY t.id DESC LIMIT 1) AS native_gloss
                FROM cards ORDER BY created_at DESC, original
                """
            ).fetchall()
            result: list[dict[str, Any]] = []
            for card_id, cand_id, original, target_lang, translated, source_lang, native_gloss in rows:
                moments = conn.execute(
                    """
                    SELECT t.translated, t.source, t.context_snippet, t.created_at
                    FROM candidate_evidence ce
                    JOIN translations t ON t.id = ce.translation_id
                    WHERE ce.candidate_id = ?
                    ORDER BY t.created_at
                    """,
                    (cand_id,),
                ).fetchall()
                result.append({
                    "id": card_id,
                    "original": original,
                    "source_lang": source_lang,
                    "native_gloss": native_gloss,
                    "target_lang": target_lang,
                    "translated": translated,
                    "moments": [
                        {"translated": m_tr, "source": m_src or "", "context": m_ctx or "", "at": m_at}
                        for m_tr, m_src, m_ctx, m_at in moments
                    ],
                })
            return result
        finally:
            conn.close()

    @app.post("/api/cards/promote")
    def promote_card(req: PromoteRequest) -> dict[str, int]:
        """The user nod: promote a candidate into a review card. Idempotent.

        This is the only place a card is born — surfaced from the UI, never via
        the agent (DESIGN.md §3.1, "Tideline is not a chatbot")."""
        conn = _connect(db)
        try:
            card_id = promote_to_card(conn, req.candidate_id)
            if card_id is None:
                raise HTTPException(status_code=404, detail="candidate not found")
            return {"card_id": card_id}
        finally:
            conn.close()

    @app.get("/api/identity")
    def identity() -> dict[str, str]:
        """L0 identity (MVP): the user's first language. The learnings view uses
        it to localize labels and to decide when a native gloss is worth showing."""
        return {"native_lang": _NATIVE_LANG}

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    return app
