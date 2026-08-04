"""FastAPI app factory for the Tideline web playground.

Mirrors the CLI startup hook exactly: init schema, run the promote +
cluster sweeps, then serve. Each HTTP request opens its own SQLite
connection so the agent loop stays thread-friendly for uvicorn's
async runtime.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tideline.boot import light_sweep, startup_sweep
from tideline.cluster import init_db as init_cluster_db
from tideline.reading import fetch_candidates, fetch_clusters, parse_region
from tideline.promotion import promote_to_card, sink_card
from tideline.runtime import ModelRuntime
from tideline.runtimes import get_runtime
from tideline.translate_flow import translate_capture
from tideline.tools import init_all_tables
from tideline.tools.card import review_card
from tideline.tools.theme_review import review_states, review_theme
from tideline.tools.settings import (
    DEFAULT_NATIVE_LANG,
    UI_LOCALES,
    derived_ui_locale,
    get_setting,
    set_setting,
)


_DEFAULT_DB = Path(".tideline") / "drawers.db"
_STATIC_DIR = Path(__file__).parent / "static"

# Cache-busting: the HTML references its assets as /static/x.js?v=<token>, where
# the token is a short hash of those assets' mtimes. Edit any of them and the
# token changes, so the browser is forced to fetch the new copy instead of
# silently reusing a stale one (which once showed raw i18n keys like
# "nav_museum" after the strings had already been translated).
_VERSIONED_ASSETS = ("i18n.js", "shore.js", "sheet.js", "styles.css")


def _asset_version() -> str:
    h = hashlib.sha1()
    for name in _VERSIONED_ASSETS:
        try:
            h.update(str((_STATIC_DIR / name).stat().st_mtime_ns).encode())
        except OSError:
            pass
    return h.hexdigest()[:10]


def _render_page(filename: str) -> HTMLResponse:
    """Serve a static HTML shell with the asset-version token stamped in, and
    mark it no-cache so the browser always revalidates the shell and never
    reuses one that points at stale (differently-versioned) assets."""
    html = (_STATIC_DIR / filename).read_text(encoding="utf-8")
    html = html.replace("__ASSET_V__", _asset_version())
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

# L0 identity: the user's first language now persists in the settings table
# (DEFAULT_NATIVE_LANG until they pick one) and is read/written via /api/identity.

# Startup sweeps and the translate path fail soft — which is right, but silent
# fail-soft leaves nothing to look at when a user reports "scenes never get
# names". Everything swallowed now says so here.
logger = logging.getLogger("tideline.web")


class TranslateRequest(BaseModel):
    text: str
    # No target_lang: Tideline always translates into the user's first
    # language (read from settings), never a per-request A→B target.


class TranslateResponse(BaseModel):
    translated: str
    source: str = "text"
    # When the guard judged this not a real foreign → first-language translation
    # (the source was already your language, or the model just echoed it), the
    # row is NOT sedimented: `recorded` is False and `guard` carries the verdict
    # ("same_as_native" | "not_translated") so the UI can say, honestly, that
    # this one was beyond reach. Both default to the happy path. (DESIGN §3.3.)
    recorded: bool = True
    guard: str | None = None


class PromoteRequest(BaseModel):
    candidate_id: int


class SinkRequest(BaseModel):
    card_id: int


class ReviewRequest(BaseModel):
    card_id: int
    remembered: bool


class ThemeReviewRequest(BaseModel):
    scene_label: str
    remembered: bool


class IdentityRequest(BaseModel):
    native_lang: str


class UiLocaleRequest(BaseModel):
    locale: str


def _connect(db_path: str) -> sqlite3.Connection:
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    # The live post-translate backfill means a request can write while another
    # is mid-write; wait briefly for the lock instead of erroring out.
    conn.execute("PRAGMA busy_timeout = 3000")
    init_all_tables(conn)
    init_cluster_db(conn)
    return conn


def create_app(
    runtime_name: str = "mock",
    db_path: str | None = None,
    runtime: ModelRuntime | None = None,
) -> FastAPI:
    """Build the FastAPI app. Defaults match the CLI client.

    A single runtime instance is shared across requests so the LLM
    (when llama_cpp) only loads once. Each request opens its own DB
    connection. A `runtime` instance can be passed directly (tests inject a
    stub); otherwise it's resolved from `runtime_name`.
    """
    db = db_path or str(_DEFAULT_DB)
    if runtime is None:
        runtime = get_runtime(runtime_name)

    # One startup sweep, shared with the CLI (boot.py) — it used to be
    # written out here and there, with a comment promising they matched.
    boot_conn = _connect(db)
    startup_sweep(boot_conn, runtime)
    boot_conn.close()

    app = FastAPI(title="Tideline", description="Local-first translation playground")

    @app.get("/")
    def root() -> HTMLResponse:
        return _render_page("index.html")

    @app.get("/learnings")
    def learnings_page() -> HTMLResponse:
        return _render_page("learnings.html")

    @app.get("/shore")
    def shore_page() -> HTMLResponse:
        """Preview of the living tidal shore (DESIGN §10), slice 1: the empty,
        time-driven coast. Standalone for now; slice 2 fuses this scene into the
        translate page's two collapsing states."""
        return _render_page("shore.html")

    @app.post("/api/translate", response_model=TranslateResponse)
    def translate(req: TranslateRequest) -> TranslateResponse:
        """Transport only: validate, hand the capture to the flow, serialize."""
        if not req.text.strip():
            raise HTTPException(status_code=400, detail="text is empty")
        conn = _connect(db)
        try:
            capture = translate_capture(conn, runtime, req.text, source="text")
            # Live backfill so the new word shows up in learnings immediately.
            # Fail-soft: a backfill hiccup must never break the translation.
            try:
                light_sweep(conn)
            except Exception:
                logger.exception("light sweep after translate failed")
        finally:
            conn.close()
        return TranslateResponse(
            translated=capture.translated,
            source="text",
            recorded=capture.recorded,
            guard=capture.guard,
        )

    @app.get("/api/clusters")
    def clusters() -> list[dict[str, Any]]:
        """Concept clusters — synonym aggregation (B1). vote_type-scoped so
        theme clusters never leak into the By-concept view."""
        conn = _connect(db)
        try:
            return fetch_clusters(conn, "concept")
        finally:
            conn.close()

    @app.get("/api/themes")
    def themes() -> list[dict[str, Any]]:
        """Album-style thematic recall: theme clusters (B7 relatedness) — the
        "your Tokyo lunches" groupings, distinct from the synonym clusters at
        /api/clusters. Same shape so the panel can reuse the card. Passive by
        design: surfaced only when the user opens this view, never pushed.

        Each theme also carries its review state (DESIGN §10.3): `due` is what
        the shore reads to decide which scene washes ashore — a never-reviewed
        scene is due by default; a graded one rests until its interval elapses.
        `strength` is internal. The museum ignores both (it shows every scene)."""
        conn = _connect(db)
        try:
            result = fetch_clusters(conn, "theme")
            states = review_states(conn, datetime.now())
            for theme in result:
                label = theme.get("scene_label")
                state = states.get(label) if label else None
                # A scene with no review row has never been reviewed → due,
                # strength 0 (mirrors a brand-new card).
                theme["due"] = state["due"] if state else True
                theme["strength"] = state["strength"] if state else 0
            return result
        finally:
            conn.close()

    @app.get("/api/candidates")
    def candidates() -> list[dict[str, Any]]:
        conn = _connect(db)
        try:
            return fetch_candidates(conn, limit=50)
        finally:
            conn.close()

    @app.get("/api/clusters/by-language")
    def clusters_by_language() -> list[dict[str, Any]]:
        """Deterministic counterpart to /api/clusters: the same emergent
        vocabulary grouped by source language instead of by concept. Needs no
        model — source_lang already rides on every drawer row — so unlike the
        by-concept clusters (which only exist once B1 votes accumulate) this
        lens is always available. Engineering carries the reliable view; the
        model's clustering is the garnish on top, not the load-bearing path.

        Each group is shaped like a cluster (a title + members) so the panel
        can reuse the same card. Most-translated language first."""
        conn = _connect(db)
        try:
            buckets: dict[str, dict[str, Any]] = {}
            for cand in fetch_candidates(conn):
                key = cand["source_lang"] or "Unknown"
                bucket = buckets.setdefault(
                    key, {"lang": key, "members": [], "total": 0}
                )
                bucket["members"].append(cand)
                bucket["total"] += cand["count"]
            groups = list(buckets.values())
            groups.sort(key=lambda g: (-g["total"], g["lang"]))
            return groups
        finally:
            conn.close()

    @app.get("/api/cards")
    def cards() -> list[dict[str, Any]]:
        """Review deck: the active cards, each with the stack of lived moments
        it grew from (episodic anchoring, DESIGN.md §3.2) — reached live through
        candidate_evidence, never a frozen copy, so the stack keeps growing.

        Cards are auto-generated (opt-out); sunk cards are filtered out here,
        which is how the user's subtraction sticks."""
        conn = _connect(db)
        now_iso = datetime.now().isoformat()
        try:
            rows = conn.execute(
                """
                SELECT id, candidate_id, original, target_lang, translated,
                    strength, due_at,
                    (SELECT t.source_lang FROM candidate_evidence ce
                     JOIN translations t ON t.id = ce.translation_id
                     WHERE ce.candidate_id = cards.candidate_id
                     ORDER BY t.id DESC LIMIT 1) AS source_lang
                FROM cards WHERE state = 'active' ORDER BY created_at DESC, original
                """
            ).fetchall()
            result: list[dict[str, Any]] = []
            for (card_id, cand_id, original, target_lang, translated,
                 strength, due_at, source_lang) in rows:
                moments = conn.execute(
                    """
                    SELECT t.translated, t.source, t.context_snippet, t.created_at,
                           t.id, t.source_image IS NOT NULL, t.source_region,
                           t.source_audio IS NOT NULL
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
                    "target_lang": target_lang,
                    "translated": translated,
                    # Review schedule (DESIGN §10.3): `due` is what the tide reads
                    # to decide which shell washes ashore — never shown as a date
                    # or count. `strength` is internal too. The museum ignores
                    # both (it shows the whole deck).
                    "strength": strength,
                    "due": due_at is None or due_at <= now_iso,
                    # Each moment carries its translation id + whether that
                    # capture kept a photo, so the sheet can show the lived
                    # material itself (/api/translations/{id}/image), not just
                    # describe it (§3.2 — the moment is recall material).
                    "moments": [
                        {"translated": m_tr, "source": m_src or "", "context": m_ctx or "",
                         "at": m_at, "id": m_id, "has_image": bool(m_img),
                         "region": parse_region(m_region), "has_audio": bool(m_aud)}
                        for m_tr, m_src, m_ctx, m_at, m_id, m_img, m_region, m_aud in moments
                    ],
                })
            return result
        finally:
            conn.close()

    @app.get("/api/translations/{translation_id}/image")
    def translation_image(translation_id: int) -> Response:
        """Serve a capture's stored source image (a menu photo / sign) — recall
        material kept on the translation row, never discarded once the VLM read
        it (DESIGN §3.2). 404 when that row carries no image (a text / audio
        capture, or an unknown id). The content type is sniffed from the bytes,
        so the demo's PNGs and a device's JPEGs both serve correctly without a
        stored mime column."""
        conn = _connect(db)
        try:
            row = conn.execute(
                "SELECT source_image FROM translations WHERE id = ?",
                (translation_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None or row[0] is None:
            raise HTTPException(status_code=404, detail="no image for this capture")
        data = bytes(row[0])
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            media = "image/png"
        elif data.startswith(b"\xff\xd8\xff"):
            media = "image/jpeg"
        else:
            media = "application/octet-stream"
        return Response(content=data, media_type=media)

    @app.get("/api/translations/{translation_id}/audio")
    def translation_audio(translation_id: int) -> Response:
        """Serve a heard capture's stored recording — dictation material: play
        what the moment actually sounded like, recall it, then compare against
        the standard pronunciation (client-side TTS, never stored). 404 when
        the row carries no recording."""
        conn = _connect(db)
        try:
            row = conn.execute(
                "SELECT source_audio FROM translations WHERE id = ?",
                (translation_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None or row[0] is None:
            raise HTTPException(status_code=404, detail="no recording for this capture")
        return Response(content=bytes(row[0]), media_type="audio/wav")

    @app.post("/api/cards/promote")
    def promote_card(req: PromoteRequest) -> dict[str, int]:
        """Promote a single candidate into a review card. Idempotent.

        Under opt-out this is no longer the primary path — cards are auto-
        generated by the night-watch sweep (`auto_promote_cards`). It stays as
        the idempotent primitive and a hook for an explicit pin; it's never
        reached via the agent (DESIGN.md §3.1, "Tideline is not a chatbot")."""
        conn = _connect(db)
        try:
            card_id = promote_to_card(conn, req.candidate_id)
            if card_id is None:
                raise HTTPException(status_code=404, detail="candidate not found")
            return {"card_id": card_id}
        finally:
            conn.close()

    @app.post("/api/cards/sink")
    def sink(req: SinkRequest) -> dict[str, bool]:
        """The user's one curation gesture: sink a card back to sediment. The
        deck is opt-out, so this — not promotion — is what the user does. A
        sunk card leaves the deck and the night-watch sweep never resurfaces
        it (auto_promote_cards is INSERT OR IGNORE on candidate_id)."""
        conn = _connect(db)
        try:
            if not sink_card(conn, req.card_id):
                raise HTTPException(status_code=404, detail="card not found")
            return {"sunk": True}
        finally:
            conn.close()

    @app.post("/api/cards/review")
    def review(req: ReviewRequest) -> dict[str, int]:
        """Record one masked-recall outcome and reschedule the card. This is
        the consolidation loop closing: reaching for a word and remembering (or
        not) feeds the spaced-repetition schedule that decides when the tide
        carries it back (DESIGN §10.3). The schedule stays internal — the UI
        records the outcome, never shows a due date or count."""
        conn = _connect(db)
        try:
            strength = review_card(conn, req.card_id, req.remembered, datetime.now())
            if strength is None:
                raise HTTPException(status_code=404, detail="card not found")
            return {"strength": strength}
        finally:
            conn.close()

    @app.post("/api/themes/review")
    def review_theme_endpoint(req: ThemeReviewRequest) -> dict[str, int]:
        """Record one masked-recall outcome for a whole scene type and reschedule
        it. The theme review unit (DESIGN §10.3): you reach for the words of a
        kind of place and grade it once. Keyed on scene_label (the scene's stable
        handle), so it survives cluster rebuilds. Schedule stays internal — the
        UI records the outcome, never a date or count."""
        conn = _connect(db)
        try:
            strength = review_theme(
                conn, req.scene_label, req.remembered, datetime.now()
            )
            return {"strength": strength}
        finally:
            conn.close()

    @app.get("/api/identity")
    def identity() -> dict[str, Any]:
        """L0 identity: the user's first language + interface language.

        `native_lang` sets the translation target (§3.3). `ui_locale` is the
        interface language — its own setting, but until the user picks one it
        follows the first language (`ui_locale_set` is false then), so a
        Chinese-first user gets a Chinese UI without choosing. Once set, the UI
        is independent of the first language."""
        conn = _connect(db)
        try:
            native = get_setting(conn, "native_lang", DEFAULT_NATIVE_LANG)
            stored = get_setting(conn, "ui_locale", "")
            return {
                "native_lang": native,
                "ui_locale": stored or derived_ui_locale(native),
                "ui_locale_set": bool(stored),
            }
        finally:
            conn.close()

    @app.post("/api/identity")
    def set_identity(req: IdentityRequest) -> dict[str, str]:
        """Persist the user's first language. Read back by every client off the
        shared settings table; the gloss-suppression rule follows it live."""
        lang = req.native_lang.strip()
        if not lang:
            raise HTTPException(status_code=400, detail="native_lang is empty")
        conn = _connect(db)
        try:
            set_setting(conn, "native_lang", lang)
            return {"native_lang": lang}
        finally:
            conn.close()

    @app.post("/api/ui-locale")
    def set_ui_locale(req: UiLocaleRequest) -> dict[str, str]:
        """Persist the interface language, independent of the first language.
        After this the UI no longer follows the first language — the user owns
        it (the smart default only seeds the first, unset state)."""
        loc = req.locale.strip()
        if loc not in UI_LOCALES:
            raise HTTPException(status_code=400, detail="unsupported ui locale")
        conn = _connect(db)
        try:
            set_setting(conn, "ui_locale", loc)
            return {"ui_locale": loc}
        finally:
            conn.close()

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    return app
