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
import sqlite3

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
    a = conn.execute(
        "INSERT INTO translations (original, target_lang, translated) "
        "VALUES ('ramen','en','ramen')"
    ).lastrowid
    b = conn.execute(
        "INSERT INTO translations (original, target_lang, translated) "
        "VALUES ('sushi','en','sushi')"
    ).lastrowid
    conn.commit()
    # Same pair voted under both relations (concept a≡b, theme a~b).
    for _ in range(3):
        vote_on_pair(conn, _Yes(), a, b, vote_type="concept")
        vote_on_pair(conn, _Yes(), a, b, vote_type="theme")
    rebuild_clusters(conn, vote_type="concept")
    rebuild_clusters(conn, vote_type="theme")
    name_clusters(conn, _Title(), vote_type="concept")
    name_clusters(conn, _Title(), vote_type="theme")
    conn.close()

    c = TestClient(create_app(runtime_name="mock", db_path=db))
    concept = c.get("/api/clusters").json()
    theme = c.get("/api/themes").json()
    assert len(concept) == 1   # only the concept cluster
    assert len(theme) == 1     # only the theme cluster
    assert {m["original"] for m in concept[0]["members"]} == {"ramen", "sushi"}
    assert {m["original"] for m in theme[0]["members"]} == {"ramen", "sushi"}


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


def test_learnings_page_exposes_cluster_toggle(client):
    """The panel ships both grouping tabs so the by-language view is reachable."""
    r = client.get("/learnings")
    assert 'data-view="concept"' in r.text
    assert 'data-view="language"' in r.text


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
