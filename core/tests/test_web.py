"""Tideline web playground verification.

Third client in the three-layer architecture (Core ↔ HTTP/JSON ↔ Clients).
Must share the CLI's startup contract: init schema, run promote + cluster
sweeps, only then serve. Translation flow goes through the same Agent
and AddTranslationTool the CLI uses.

Functional gates:
- `create_app(runtime='mock', db=':memory:')` builds without error
- POST /api/translate returns a translated string and writes a row to
  translations
- GET /api/clusters / /api/candidates return JSON lists shaped as the
  frontend expects
- Static index.html and learnings.html are served at / and /learnings
- Empty DB → endpoints don't crash

Drift gates:
- agent.py stays transport-agnostic (no http/fastapi/uvicorn tokens)
- web/app.py runs the same startup sweep sequence as cli/__main__.py
  (promote_candidates + cluster_sweep) — locked so future refactors
  can't drift the two clients apart
"""

from __future__ import annotations

import inspect
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from tideline.web.app import create_app


@pytest.fixture
def client():
    app = create_app(runtime_name="mock", db_path=":memory:")
    return TestClient(app)


# --- Static routes -------------------------------------------------------


def test_root_serves_translator_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Tideline" in r.text
    assert "translate" in r.text.lower()


def test_learnings_route_serves_panel_html(client):
    r = client.get("/learnings")
    assert r.status_code == 200
    assert "clusters" in r.text.lower()


def test_shore_preview_route_serves_scene(client):
    # DESIGN §10 slice 1: the living shore preview + its time/tide engine.
    r = client.get("/shore")
    assert r.status_code == 200
    assert "shore" in r.text.lower()
    assert "/static/shore.js" in r.text
    engine = client.get("/static/shore.js")
    assert engine.status_code == 200
    assert "Shore" in engine.text


# --- /api/translate ------------------------------------------------------


def test_translate_endpoint_returns_translation(client):
    r = client.post("/api/translate", json={"text": "hello"})
    assert r.status_code == 200
    body = r.json()
    assert "translated" in body
    assert body["translated"]   # non-empty
    assert body["source"] == "text"


def test_translate_rejects_empty_text(client):
    r = client.post("/api/translate", json={"text": "  "})
    assert r.status_code == 400


def test_translate_writes_drawer_row(tmp_path):
    db = str(tmp_path / "t.db")
    app = create_app(runtime_name="mock", db_path=db)
    c = TestClient(app)
    c.post("/api/translate", json={"text": "hello"})

    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
    conn.close()
    assert n >= 1


def test_translate_tags_source_lang_live_on_first_occurrence(tmp_path):
    """The model-free backfill tags source_lang right after a translation —
    deterministically, even before the word is a candidate."""
    db = str(tmp_path / "t.db")
    c = TestClient(create_app(runtime_name="mock", db_path=db))
    c.post("/api/translate", json={"text": "ラーメン"})

    conn = sqlite3.connect(db)
    sl = conn.execute(
        "SELECT source_lang FROM translations WHERE original='ラーメン'"
    ).fetchone()[0]
    conn.close()
    assert sl == "Japanese"


def test_translate_promotes_and_cards_live_without_restart(tmp_path):
    """A word repeated to threshold becomes a tagged candidate and an auto-card
    within the same app run — the learnings view is live, not restart-gated."""
    db = str(tmp_path / "t.db")
    c = TestClient(create_app(runtime_name="mock", db_path=db))
    for _ in range(3):
        r = c.post("/api/translate", json={"text": "ラーメン"})
        assert r.status_code == 200

    row = next(d for d in c.get("/api/candidates").json() if d["original"] == "ラーメン")
    assert row["source_lang"] == "Japanese"  # deterministic, immediate
    assert any(x["original"] == "ラーメン" for x in c.get("/api/cards").json())


def test_card_review_reschedules_and_clears_due(tmp_path):
    """The consolidation loop over HTTP: a fresh card is `due` (the tide can
    carry it ashore); recording a 'remembered' outcome reschedules it so it's
    no longer due — the schedule stays internal, surfaced only as `due`."""
    db = str(tmp_path / "t.db")
    c = TestClient(create_app(runtime_name="mock", db_path=db))
    for _ in range(3):
        c.post("/api/translate", json={"text": "ラーメン"})

    card = next(x for x in c.get("/api/cards").json() if x["original"] == "ラーメン")
    assert card["due"] is True and card["strength"] == 0   # new + ready

    r = c.post("/api/cards/review", json={"card_id": card["id"], "remembered": True})
    assert r.status_code == 200
    assert r.json()["strength"] == 1

    after = next(x for x in c.get("/api/cards").json() if x["id"] == card["id"])
    assert after["due"] is False   # pushed out, no longer washing ashore


def test_card_review_unknown_card_is_404(client):
    r = client.post("/api/cards/review", json={"card_id": 999, "remembered": True})
    assert r.status_code == 404


def test_translate_target_is_always_the_first_language(tmp_path):
    """No A→B picker: the translation target is whatever first language the
    user has set, not a per-request choice. Setting native_lang=Japanese makes
    a translation land with target_lang=Japanese."""
    db = str(tmp_path / "t.db")
    c = TestClient(create_app(runtime_name="mock", db_path=db))
    c.post("/api/identity", json={"native_lang": "Japanese"})
    r = c.post("/api/translate", json={"text": "hello"})
    assert r.status_code == 200

    conn = sqlite3.connect(db)
    target = conn.execute(
        "SELECT target_lang FROM translations WHERE original='hello' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    conn.close()
    # Followed native_lang (Japanese), not the old default (Chinese). Case-
    # insensitive: the mock lowercases the parsed target; a real model keeps
    # the prompt's casing — either way it must be the first language.
    assert target.lower() == "japanese"


# --- interface language (multilingual support, zh + en) ------------------


def test_ui_locale_defaults_follow_first_language_until_set(tmp_path):
    """Smart default: before the user picks an interface language, it follows
    the first language — Chinese → zh, anything else → en — and reports it as
    not-yet-explicit so the picker knows it may still drift with the first
    language."""
    db = str(tmp_path / "t.db")
    c = TestClient(create_app(runtime_name="mock", db_path=db))

    ident = c.get("/api/identity").json()
    assert ident["ui_locale"] == "zh"          # default native is Chinese
    assert ident["ui_locale_set"] is False

    c.post("/api/identity", json={"native_lang": "English"})
    ident = c.get("/api/identity").json()
    assert ident["ui_locale"] == "en"          # follows the first language
    assert ident["ui_locale_set"] is False


def test_ui_locale_is_independent_once_set(tmp_path):
    """Once chosen, the interface language is its own setting: changing the
    first language (the translation target) no longer moves the UI."""
    db = str(tmp_path / "t.db")
    c = TestClient(create_app(runtime_name="mock", db_path=db))

    assert c.post("/api/ui-locale", json={"locale": "en"}).status_code == 200
    ident = c.get("/api/identity").json()
    assert ident["ui_locale"] == "en" and ident["ui_locale_set"] is True

    # First language → Japanese (translate into Japanese), UI stays English.
    c.post("/api/identity", json={"native_lang": "Japanese"})
    ident = c.get("/api/identity").json()
    assert ident["native_lang"] == "Japanese"
    assert ident["ui_locale"] == "en"          # independent — did not follow


def test_ui_locale_rejects_unsupported(tmp_path):
    db = str(tmp_path / "t.db")
    c = TestClient(create_app(runtime_name="mock", db_path=db))
    assert c.post("/api/ui-locale", json={"locale": "fr"}).status_code == 400
    assert c.post("/api/ui-locale", json={"locale": ""}).status_code == 400


# --- live sessionization (theme refinement) ------------------------------


def _session_of(db, original):
    conn = sqlite3.connect(db)
    sid = conn.execute(
        "SELECT session_id FROM translations WHERE original = ? "
        "ORDER BY id DESC LIMIT 1",
        (original,),
    ).fetchone()[0]
    conn.close()
    return sid


def test_live_translations_in_one_sitting_share_a_session(tmp_path):
    """Live captures land with a session id now (not NULL), and two within the
    same sitting share it — the time-window co-occurrence that lets live words
    form themes (DESIGN §3.2). Without this they were session-less and the theme
    sweep never saw them."""
    db = str(tmp_path / "t.db")
    c = TestClient(create_app(runtime_name="mock", db_path=db))
    c.post("/api/translate", json={"text": "ラーメン"})
    c.post("/api/translate", json={"text": "寿司"})

    s1, s2 = _session_of(db, "ラーメン"), _session_of(db, "寿司")
    assert s1 and s1.startswith("live-")   # no longer NULL
    assert s1 == s2                        # one sitting → one session


def test_live_session_breaks_after_an_inactivity_gap(tmp_path):
    """A gap longer than the window starts a new session — distinct sittings are
    distinct scenes, so they don't fuse into one giant theme."""
    db = str(tmp_path / "t.db")
    c = TestClient(create_app(runtime_name="mock", db_path=db))
    c.post("/api/translate", json={"text": "ラーメン"})
    first = _session_of(db, "ラーメン")

    # Simulate the sitting ending: push the last-seen time well past the window.
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE settings SET value = ? WHERE key = 'live_session_last_at'",
        ((datetime(2020, 1, 1)).isoformat(),),
    )
    conn.commit()
    conn.close()

    c.post("/api/translate", json={"text": "寿司"})
    assert _session_of(db, "寿司") != first   # new sitting → new session


def test_live_captures_form_a_theme_after_the_sweep(tmp_path):
    """The payoff: two distinct concepts captured in one live sitting co-occur
    into a theme on the next sweep — emergence works on real usage, not only on
    seed data. Both words are katakana, so source_lang is tagged
    deterministically even under the mock runtime; a theme is single-language
    (§3.3), so co-occurring words must share a source language to form a scene."""
    db = str(tmp_path / "t.db")
    c = TestClient(create_app(runtime_name="mock", db_path=db))
    c.post("/api/translate", json={"text": "ラーメン"})  # one concept
    c.post("/api/translate", json={"text": "サラダ"})     # a distinct concept
    session = _session_of(db, "ラーメン")

    # A fresh app on the same db runs the boot sweep (theme grouping + naming).
    c2 = TestClient(create_app(runtime_name="mock", db_path=db))
    themes = c2.get("/api/themes").json()
    live = [t for t in themes if t.get("session_id") == session]
    assert len(live) == 1, themes
    assert {m["original"] for m in live[0]["members"]} == {"ラーメン", "サラダ"}
    assert live[0]["due"] is True   # a brand-new scene is due to revisit


# --- /api/clusters and /api/candidates ----------------------------------


def test_clusters_endpoint_returns_list(client):
    r = client.get("/api/clusters")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_candidates_endpoint_returns_list(client):
    r = client.get("/api/candidates")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_clusters_shape_includes_members(tmp_path):
    """Verify the cluster response wraps member translations as the
    frontend expects."""
    from tideline.cluster import init_db, name_clusters, rebuild_clusters, vote_on_pair
    from tideline.runtime import ModelRuntime
    from tideline.tools import init_all_tables

    class _Yes(ModelRuntime):
        def generate(self, prompt: str) -> str:
            return "yes"

    class _Title(ModelRuntime):
        def generate(self, prompt: str) -> str:
            return "your Tokyo lunches"

    db = str(tmp_path / "t.db")
    conn = sqlite3.connect(db)
    init_all_tables(conn)
    init_db(conn)
    cur = conn.execute(
        "INSERT INTO translations (original, target_lang, translated, source_lang, context_snippet) "
        "VALUES (?, ?, ?, ?, ?)",
        ("ramen", "en", "ramen", "Japanese", "menu at Ichiran"),
    )
    a = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO translations (original, target_lang, translated, source_lang, context_snippet) "
        "VALUES (?, ?, ?, ?, ?)",
        ("udon", "en", "udon", "Japanese", "noodle shop Tokyo"),
    )
    b = cur.lastrowid
    conn.commit()
    # Three yes votes to satisfy the multi-vote default min_votes=3
    # (the web startup hook re-rebuilds with that threshold)
    vote_on_pair(conn, _Yes(), a, b)
    vote_on_pair(conn, _Yes(), a, b)
    vote_on_pair(conn, _Yes(), a, b)
    rebuild_clusters(conn)
    name_clusters(conn, _Title())
    conn.close()

    app = create_app(runtime_name="mock", db_path=db)
    c = TestClient(app)
    r = c.get("/api/clusters")
    data = r.json()
    assert len(data) == 1
    cluster = data[0]
    assert cluster["title"] == "your Tokyo lunches"
    assert len(cluster["members"]) == 2
    member_originals = {m["original"] for m in cluster["members"]}
    assert member_originals == {"ramen", "udon"}
    # context is forwarded
    assert any("Ichiran" in m["context"] for m in cluster["members"])
    # source language is forwarded per member
    assert all(m["source_lang"] == "Japanese" for m in cluster["members"])


# --- /api/themes (album-style thematic recall) --------------------------


def test_themes_endpoint_returns_list(client):
    r = client.get("/api/themes")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_themes_and_concept_clusters_isolated_across_endpoints(tmp_path):
    """The clusters table holds both relations; /api/clusters must show only
    concept clusters and /api/themes only theme clusters, no leak either way.
    Guards the bug a real model would expose: an unscoped SELECT surfacing
    theme groups in the By-concept view once the theme sweep runs."""
    from tideline.cluster import init_db, name_clusters, rebuild_clusters, vote_on_pair
    from tideline.runtime import ModelRuntime
    from tideline.tools import init_all_tables

    class _Yes(ModelRuntime):
        def generate(self, prompt: str) -> str:
            return "yes"

    class _Title(ModelRuntime):
        def generate(self, prompt: str) -> str:
            return "a remembered afternoon"

    db = str(tmp_path / "t.db")
    conn = sqlite3.connect(db)
    init_all_tables(conn)
    init_db(conn)

    def _add(original, translated):
        # All captured in one session (a remembered meal) → co-occurrence theme.
        return conn.execute(
            "INSERT INTO translations "
            "(original, target_lang, translated, source_lang, session_id) "
            "VALUES (?, '中文', ?, 'Japanese', 'meal')",
            (original, translated),
        ).lastrowid

    # Two same-meaning Japanese words → one CONCEPT cluster (拉面). A third,
    # distinct concept (寿司). They share one capture session, so the THEME is
    # that session (a remembered meal) spanning the two concepts — concept and
    # theme are different relations, the realistic shape now (§3.3).
    a = _add("ラーメン", "拉面")
    b = _add("中華そば", "拉面")   # same concept as a (deterministic)
    c = _add("寿司", "寿司")        # a different concept
    conn.commit()
    rebuild_clusters(conn, vote_type="concept")
    rebuild_clusters(conn, vote_type="theme")
    name_clusters(conn, _Title(), vote_type="concept")
    name_clusters(conn, _Title(), vote_type="theme")
    conn.close()

    client = TestClient(create_app(runtime_name="mock", db_path=db))
    concept = client.get("/api/clusters").json()
    theme = client.get("/api/themes").json()
    assert len(concept) == 1   # only the concept cluster (拉面 = ラーメン+中華そば)
    assert len(theme) == 1     # only the theme cluster
    assert {m["original"] for m in concept[0]["members"]} == {"ラーメン", "中華そば"}
    # The theme spans both concepts and expands to every row behind them.
    assert {m["original"] for m in theme[0]["members"]} == {"ラーメン", "中華そば", "寿司"}


def test_theme_is_reviewable_and_grading_reschedules_it(tmp_path):
    """A theme is a review unit too (DESIGN §10.3): it carries `due`/`strength`
    and a session_id, and grading it through /api/themes/review reschedules the
    scene so it stops being due — the consolidation loop, but for a remembered
    occasion rather than a single word."""
    from tideline.cluster import init_db, name_clusters, rebuild_clusters
    from tideline.runtime import ModelRuntime
    from tideline.tools import init_all_tables

    class _Title(ModelRuntime):
        def generate(self, prompt: str) -> str:
            return "a remembered meal"

    db = str(tmp_path / "t.db")
    conn = sqlite3.connect(db)
    init_all_tables(conn)
    init_db(conn)
    for original, translated in [("ラーメン", "拉面"), ("寿司", "寿司")]:
        conn.execute(
            "INSERT INTO translations "
            "(original, target_lang, translated, source_lang, session_id) "
            "VALUES (?, '中文', ?, 'Japanese', 'meal')",
            (original, translated),
        )
    conn.commit()
    rebuild_clusters(conn, vote_type="theme")
    name_clusters(conn, _Title(), vote_type="theme")
    conn.close()

    client = TestClient(create_app(runtime_name="mock", db_path=db))

    before = client.get("/api/themes").json()
    assert len(before) == 1
    theme = before[0]
    assert theme["session_id"] == "meal"
    assert theme["due"] is True            # never reviewed → due
    assert theme["strength"] == 0

    # Grade the scene as remembered → it climbs a box and stops being due.
    r = client.post(
        "/api/themes/review",
        json={"session_id": "meal", "remembered": True},
    )
    assert r.status_code == 200
    assert r.json()["strength"] == 1

    after = client.get("/api/themes").json()
    assert after[0]["due"] is False
    assert after[0]["strength"] == 1


# --- /api/clusters/by-language (deterministic lens) ----------------------


def test_clusters_by_language_endpoint_returns_list(client):
    r = client.get("/api/clusters/by-language")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def _seed_candidate(conn, original, target_lang, translated, source_lang, n):
    for _ in range(n):
        conn.execute(
            "INSERT INTO translations "
            "(original, target_lang, translated, source_lang, source) "
            "VALUES (?, ?, ?, ?, 'text')",
            (original, target_lang, translated, source_lang),
        )


def test_clusters_by_language_groups_candidates_by_source_lang(tmp_path):
    """The deterministic lens: candidates bucket by their source language,
    most-translated language first, direction carried per member."""
    db = str(tmp_path / "t.db")
    app = create_app(runtime_name="mock", db_path=db)
    c = TestClient(app)
    conn = sqlite3.connect(db)
    _seed_candidate(conn, "ラーメン", "English", "ramen", "Japanese", 4)
    _seed_candidate(conn, "寿司", "English", "sushi", "Japanese", 3)
    _seed_candidate(conn, "beurre", "English", "butter", "French", 5)
    conn.commit()
    from tideline.promotion import promote_candidates
    promote_candidates(conn)
    conn.close()

    data = c.get("/api/clusters/by-language").json()
    # Japanese total (4+3=7) outranks French (5), so it sorts first.
    assert [g["lang"] for g in data] == ["Japanese", "French"]
    jp = data[0]
    assert jp["total"] == 7
    # within a bucket, most-repeated first
    assert [m["original"] for m in jp["members"]] == ["ラーメン", "寿司"]
    ramen = jp["members"][0]
    assert ramen["count"] == 4
    assert ramen["target_lang"] == "English"


def test_clusters_by_language_buckets_unknown_source(tmp_path):
    """A candidate whose source language was never detected lands in an
    'Unknown' bucket rather than vanishing from the lens."""
    db = str(tmp_path / "t.db")
    app = create_app(runtime_name="mock", db_path=db)
    c = TestClient(app)
    conn = sqlite3.connect(db)
    for _ in range(3):
        conn.execute(
            "INSERT INTO translations (original, target_lang, translated, source) "
            "VALUES ('???', 'English', 'mystery', 'text')"
        )
    conn.commit()
    from tideline.promotion import promote_candidates
    promote_candidates(conn)
    conn.close()

    data = c.get("/api/clusters/by-language").json()
    assert [g["lang"] for g in data] == ["Unknown"]


def test_museum_page_exposes_all_lenses(client):
    """The museum shelves the collection three ways (DESIGN §10.7); every lens —
    including the by-language view re-housed here — is reachable from the lens
    switcher. The by-concept lens was retired (themes carry the grouping; the
    concept axis was redundant with cards + language)."""
    r = client.get("/learnings")
    for lens in ("cards", "language", "theme"):
        assert f'data-lens="{lens}"' in r.text
    assert 'data-lens="concept"' not in r.text


def test_navigation_desk_is_the_hub(client):
    """The desk is the hub (DESIGN §10.7, 2026-06-03): both the shore (one swipe
    up) and the museum (a header doorway) are reachable from home — not the
    museum buried behind the shore. Still no flat two-tab nav bar."""
    desk = client.get("/").text
    museum = client.get("/learnings").text
    # no flat two-tab nav on either page
    assert "<nav>" not in desk
    assert "<nav>" not in museum
    # the desk reaches the museum directly (a header doorway) AND still via the
    # shore's own doorway up the dunes
    assert 'class="to-museum"' in desk
    assert 'href="/learnings"' in desk
    assert 'id="toMuseum"' in desk
    # the museum's way out lands on the desk hub, not deep in the open shore
    assert 'class="back-to-shore" href="/"' in museum
    assert 'href="/?shore=open"' not in museum


# --- Drift gates ---------------------------------------------------------


def test_drift_agent_stays_transport_agnostic():
    """agent.py must not know about HTTP/FastAPI — the web client wraps
    around the agent, never the other way."""
    import tideline.agent

    source = inspect.getsource(tideline.agent).lower()
    for token in ("fastapi", "uvicorn", "starlette", "httpx"):
        assert token not in source, (
            f"agent.py contains transport token {token!r}; the agent must "
            f"stay transport-agnostic so it can serve CLI / Web / future "
            f"Android clients without modification."
        )


def test_drift_web_app_runs_same_startup_sweep_as_cli():
    """Both clients must invoke promote_candidates and cluster_sweep on
    startup; otherwise web and CLI users would see different state."""
    import tideline.cli.__main__ as cli_main
    import tideline.web.app as web_app

    cli_src = inspect.getsource(cli_main)
    web_src = inspect.getsource(web_app)
    for token in (
        "promote_candidates", "auto_promote_cards", "cluster_sweep",
        "tag_source_langs",
    ):
        assert token in cli_src, f"cli/__main__.py missing {token}"
        assert token in web_src, f"web/app.py missing {token}"


def test_drift_language_names_come_from_shared_i18n_helper():
    """Language names — the by-language buckets (full: 日语 / Japanese) and the
    source→target tag (compact: 日→中 / JA→ZH) — must resolve through i18n's
    locale-aware langName / langShort, one source of truth, so neither locale
    leaks the other's script. The views must NOT carry their own LANG_SHORT
    copy (the bug that left raw 'Japanese' in the Chinese UI and CJK tags in the
    English UI)."""
    import tideline.web.app as web_app

    static = Path(web_app.__file__).parent / "static"
    i18n = (static / "i18n.js").read_text()
    assert "function langShort" in i18n and "function langName" in i18n

    # en/zh language-name keys are aligned and cover every language + Unknown.
    en_block = i18n[i18n.index("\n  en"):i18n.index("\n  zh")]
    zh_block = i18n[i18n.index("\n  zh"):]
    en_langs = set(re.findall(r"\blang_(\w+):", en_block))
    zh_langs = set(re.findall(r"\blang_(\w+):", zh_block))
    assert en_langs == zh_langs, f"lang_* drift: {en_langs ^ zh_langs}"
    for lang in ("Chinese", "English", "Japanese", "French", "Spanish",
                 "German", "Italian", "Korean", "Unknown"):
        assert lang in en_langs, f"missing lang_{lang} in i18n"

    # No per-file LANG_SHORT definition leaked back into the views.
    for name in ("sheet.js", "learnings.html"):
        src = (static / name).read_text()
        assert not re.search(r"LANG_SHORT\s*=", src), (
            f"{name} redefines LANG_SHORT; language names must come from the "
            f"shared i18n langShort / langName helper."
        )


def test_drift_aria_labels_default_to_english():
    """Accessibility chrome labels are English by default (the interface falls
    back to English for screen readers): visible UI text is localized via i18n,
    but a hardcoded Chinese aria-label would read as CJK to a screen reader even
    in the English UI. Locks the fix — no static aria-label literal regresses to
    Chinese. (Dynamic aria-label="${...}" interpolations carry DATA — a learned
    word — not chrome, so they are out of scope and contain no literal CJK.)"""
    import tideline.web.app as web_app

    static = Path(web_app.__file__).parent / "static"
    cjk = re.compile(r'aria-label="[^"]*[぀-ヿ一-鿿][^"]*"')
    offenders = []
    for f in static.iterdir():
        if f.suffix in (".html", ".js"):
            offenders += [f"{f.name}: {m.group(0)}" for m in cjk.finditer(f.read_text())]
    assert not offenders, f"CJK literal in aria-label (keep English): {offenders}"


# --- /api/cards and the user nod -----------------------------------------


def test_cards_endpoint_returns_list(client):
    r = client.get("/api/cards")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_candidates_include_id(tmp_path):
    db = str(tmp_path / "t.db")
    app = create_app(runtime_name="mock", db_path=db)
    c = TestClient(app)
    conn = sqlite3.connect(db)
    for _ in range(3):
        conn.execute(
            "INSERT INTO translations (original, target_lang, translated, source) "
            "VALUES ('station', 'Japanese', '駅', 'text')"
        )
    conn.commit()
    from tideline.promotion import promote_candidates
    promote_candidates(conn)
    conn.close()

    data = c.get("/api/candidates").json()
    assert data and "id" in data[0]


def test_promote_creates_card_with_moments(tmp_path):
    """The nod: promoting a candidate creates a card whose review face is the
    stack of lived moments (episodic anchoring), not a bare count."""
    db = str(tmp_path / "t.db")
    app = create_app(runtime_name="mock", db_path=db)
    c = TestClient(app)
    conn = sqlite3.connect(db)
    for ctx in ("Shibuya menu", "cooking class", "station sign"):
        conn.execute(
            "INSERT INTO translations "
            "(original, target_lang, translated, source_lang, source, context_snippet) "
            "VALUES ('station', 'Japanese', '駅', 'English', 'image', ?)",
            (ctx,),
        )
    conn.commit()
    from tideline.promotion import promote_candidates
    promote_candidates(conn)
    cand_id = conn.execute(
        "SELECT id FROM candidates WHERE original='station'"
    ).fetchone()[0]
    conn.close()

    r = c.post("/api/cards/promote", json={"candidate_id": cand_id})
    assert r.status_code == 200
    assert "card_id" in r.json()

    cards = c.get("/api/cards").json()
    assert len(cards) == 1
    assert cards[0]["original"] == "station"
    assert cards[0]["source_lang"] == "English"
    assert cards[0]["target_lang"] == "Japanese"
    assert len(cards[0]["moments"]) == 3
    assert any("Shibuya" in m["context"] for m in cards[0]["moments"])


def test_promote_is_idempotent_over_http(tmp_path):
    db = str(tmp_path / "t.db")
    app = create_app(runtime_name="mock", db_path=db)
    c = TestClient(app)
    conn = sqlite3.connect(db)
    for _ in range(3):
        conn.execute(
            "INSERT INTO translations (original, target_lang, translated, source) "
            "VALUES ('water', 'Japanese', '水', 'text')"
        )
    conn.commit()
    from tideline.promotion import promote_candidates
    promote_candidates(conn)
    cand_id = conn.execute(
        "SELECT id FROM candidates WHERE original='water'"
    ).fetchone()[0]
    conn.close()

    c.post("/api/cards/promote", json={"candidate_id": cand_id})
    c.post("/api/cards/promote", json={"candidate_id": cand_id})
    assert len(c.get("/api/cards").json()) == 1


def test_promote_unknown_candidate_404(client):
    r = client.post("/api/cards/promote", json={"candidate_id": 99999})
    assert r.status_code == 404


def test_candidates_include_source_lang(tmp_path):
    """The ambiguous-arrow fix: each candidate carries its source language,
    derived from the translations it came from."""
    db = str(tmp_path / "t.db")
    app = create_app(runtime_name="mock", db_path=db)
    c = TestClient(app)
    conn = sqlite3.connect(db)
    for _ in range(3):
        conn.execute(
            "INSERT INTO translations "
            "(original, target_lang, translated, source_lang, source) "
            "VALUES ('ラーメン', 'English', 'ramen', 'Japanese', 'text')"
        )
    conn.commit()
    from tideline.promotion import promote_candidates
    promote_candidates(conn)
    conn.close()

    data = c.get("/api/candidates").json()
    row = next(d for d in data if d["original"] == "ラーメン")
    assert row["source_lang"] == "Japanese"
    assert row["target_lang"] == "English"


def test_identity_endpoint_returns_native_lang(client):
    r = client.get("/api/identity")
    assert r.status_code == 200
    assert "native_lang" in r.json()


def test_identity_defaults_to_chinese(client):
    """Unset first language falls back to the MVP default."""
    assert client.get("/api/identity").json()["native_lang"] == "Chinese"


def test_identity_post_persists_across_restart(tmp_path):
    """The chosen first language survives a fresh app boot on the same DB —
    it's persisted in the shared settings table, not an in-process global."""
    db = str(tmp_path / "t.db")
    c = TestClient(create_app(runtime_name="mock", db_path=db))
    r = c.post("/api/identity", json={"native_lang": "Japanese"})
    assert r.status_code == 200
    assert r.json()["native_lang"] == "Japanese"

    c2 = TestClient(create_app(runtime_name="mock", db_path=db))
    assert c2.get("/api/identity").json()["native_lang"] == "Japanese"


def test_identity_post_rejects_empty(client):
    r = client.post("/api/identity", json={"native_lang": "   "})
    assert r.status_code == 400


def test_learnings_page_has_native_lang_selector(client):
    r = client.get("/learnings")
    assert 'id="native-lang"' in r.text


# --- opt-out deck: auto-generation + sink over HTTP ----------------------


def _seed_repeats(db, original, target, translated, n=3):
    conn = sqlite3.connect(db)
    from tideline.tools import init_all_tables
    init_all_tables(conn)
    for _ in range(n):
        conn.execute(
            "INSERT INTO translations (original, target_lang, translated, source) "
            "VALUES (?, ?, ?, 'text')",
            (original, target, translated),
        )
    conn.commit()
    conn.close()


def test_startup_auto_generates_cards(tmp_path):
    """Opt-out: a repeated term surfaces as a card from the boot sweep alone —
    no manual promote anywhere in this test."""
    db = str(tmp_path / "t.db")
    _seed_repeats(db, "station", "Japanese", "駅")

    app = create_app(runtime_name="mock", db_path=db)  # boot auto-promotes
    c = TestClient(app)
    cards = c.get("/api/cards").json()
    assert any(card["original"] == "station" for card in cards)


def test_sink_removes_card_from_deck(tmp_path):
    db = str(tmp_path / "t.db")
    _seed_repeats(db, "water", "Japanese", "水")
    app = create_app(runtime_name="mock", db_path=db)
    c = TestClient(app)

    cards = c.get("/api/cards").json()
    assert len(cards) == 1
    card_id = cards[0]["id"]

    r = c.post("/api/cards/sink", json={"card_id": card_id})
    assert r.status_code == 200
    assert r.json() == {"sunk": True}
    assert c.get("/api/cards").json() == []


def test_sink_unknown_card_404(client):
    r = client.post("/api/cards/sink", json={"card_id": 99999})
    assert r.status_code == 404


def test_translation_image_is_served_as_recall_material(tmp_path):
    """A captured photo is kept on its translation row and served back as recall
    material (§3.2): an image capture serves its bytes with a content type
    sniffed from the bytes; a text/audio capture (no image) and an unknown id
    both 404 — so a future view can ask for the photo and fail cleanly."""
    from tideline.seed import seed_db
    from tideline.tools import init_all_tables

    db = str(tmp_path / "shots.db")
    conn = sqlite3.connect(db)
    init_all_tables(conn)
    seed_db(conn)
    img_id = conn.execute(
        "SELECT id FROM translations WHERE source = 'image' "
        "AND source_image IS NOT NULL ORDER BY id LIMIT 1"
    ).fetchone()[0]
    txt_id = conn.execute(
        "SELECT id FROM translations WHERE source_image IS NULL ORDER BY id LIMIT 1"
    ).fetchone()[0]
    conn.close()

    c = TestClient(create_app(runtime_name="mock", db_path=db))

    r = c.get(f"/api/translations/{img_id}/image")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content.startswith(b"\x89PNG\r\n\x1a\n")

    # A text / audio capture carries no image → 404.
    assert c.get(f"/api/translations/{txt_id}/image").status_code == 404
    # An unknown translation id → 404.
    assert c.get("/api/translations/999999/image").status_code == 404
