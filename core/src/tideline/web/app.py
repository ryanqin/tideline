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
from tideline.promotion import promote_candidates
from tideline.runtimes import get_runtime
from tideline.tools import AddTranslationTool, ToolRegistry, init_all_tables


_DEFAULT_DB = Path(".tideline") / "drawers.db"
_STATIC_DIR = Path(__file__).parent / "static"

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
                    SELECT t.original, t.translated, t.context_snippet
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
                        {"original": o, "translated": tr, "context": ctx or ""}
                        for o, tr, ctx in members
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
                "SELECT original, target_lang, translated, occurrence_count "
                "FROM candidates ORDER BY occurrence_count DESC, original LIMIT 50"
            ).fetchall()
            return [
                {"original": o, "target_lang": tl, "translated": tr, "count": cnt}
                for o, tl, tr, cnt in rows
            ]
        finally:
            conn.close()

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    return app
