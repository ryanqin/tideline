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
    r = client.post("/api/translate", json={"text": "hello", "target_lang": "Chinese"})
    assert r.status_code == 200
    body = r.json()
    assert "translated" in body
    assert body["translated"]   # non-empty
    assert body["source"] == "text"


def test_translate_rejects_empty_text(client):
    r = client.post("/api/translate", json={"text": "  ", "target_lang": "Chinese"})
    assert r.status_code == 400


def test_translate_writes_drawer_row(tmp_path):
    db = str(tmp_path / "t.db")
    app = create_app(runtime_name="mock", db_path=db)
    c = TestClient(app)
    c.post("/api/translate", json={"text": "hello", "target_lang": "Chinese"})

    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
    conn.close()
    assert n >= 1


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
        "INSERT INTO translations (original, target_lang, translated, context_snippet) "
        "VALUES (?, ?, ?, ?)",
        ("ramen", "en", "ramen", "menu at Ichiran"),
    )
    a = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO translations (original, target_lang, translated, context_snippet) "
        "VALUES (?, ?, ?, ?)",
        ("udon", "en", "udon", "noodle shop Tokyo"),
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
    for token in ("promote_candidates", "cluster_sweep"):
        assert token in cli_src, f"cli/__main__.py missing {token}"
        assert token in web_src, f"web/app.py missing {token}"
