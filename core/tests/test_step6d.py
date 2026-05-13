"""Phase B3 verification: Tier B cluster sweep on CLI startup.

Step 6c hooked promotion (drawer → candidate threshold) into CLI startup
as a night-watch sweep. Phase B3 layers the cluster engine on top: every
CLI invocation also runs a budgeted vote / rebuild / name pass so that
clusters grow on their own between explicit invocations.

Functional gates:
- CLI startup creates the cluster schema (pair_similarity_votes,
  clusters, cluster_members) even when no cluster work happens
- Sweep is silent: no "cluster" / "voted" line on stdout for normal requests
- Empty DB → CLI still works, sweep finds nothing
- Mock runtime → sweep runs but produces zero parseable votes
  (Mock's _TRANSLATE_RE doesn't match B1/B6 prompts); CLI must not crash
- Translation flow continues to work after the new hook

Drift gates:
- Cluster sweep lives in CLI, NOT in agent.py — same product-domain-blank
  gate as Step 6c, extended to the cluster vocabulary
"""

from __future__ import annotations

import inspect
import sqlite3
import subprocess
import sys


def _cli(*extra: str, db: str = ":memory:") -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable, "-m", "tideline.cli",
            "--runtime", "mock", "--db", db,
            *extra,
        ],
        capture_output=True, text=True,
    )


# --- Cluster schema is initialised on startup ----------------------------


def test_cli_startup_creates_cluster_schema(tmp_path):
    """Even on a fresh DB with no translations, the cluster tables must
    exist after one CLI invocation so the sweep can run next time."""
    db_path = tmp_path / "test.db"
    result = _cli("hello", db=str(db_path))
    assert result.returncode == 0, result.stderr

    conn = sqlite3.connect(str(db_path))
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('pair_similarity_votes','clusters','cluster_members')"
        )
    }
    conn.close()
    assert tables == {"pair_similarity_votes", "clusters", "cluster_members"}


# --- Sweep is silent ------------------------------------------------------


def test_cluster_sweep_produces_no_stdout_noise():
    result = _cli("hello")
    assert result.returncode == 0
    assert result.stdout.strip() == "[mock] echo: hello"
    for noisy in ("cluster", "voted", "named"):
        assert noisy not in result.stdout.lower()


def test_cluster_sweep_survives_empty_db():
    result = _cli("hello")
    assert result.returncode == 0, result.stderr
    assert "[mock] echo: hello" in result.stdout


def test_cluster_sweep_with_mock_does_not_crash(tmp_path):
    """Mock runtime never produces yes/no for B1 prompts (its TRANSLATE_RE
    matches a different shape). The sweep should accumulate 'unparseable'
    counts but never raise."""
    db_path = tmp_path / "test.db"
    subprocess.run(
        [sys.executable, "-m", "tideline.seed", "--db", str(db_path)],
        capture_output=True, text=True, check=True,
    )
    result = _cli("hello", db=str(db_path))
    assert result.returncode == 0, result.stderr


# --- Translation still works ---------------------------------------------


def test_translate_cli_still_works_with_cluster_sweep():
    """Phase B3 must not interfere with the translation flow that
    Step 6c hardened."""
    assert _cli("hello").stdout.strip() == "[mock] echo: hello"
    assert "[mock-translated to zh] hello" in _cli("translate hello to zh").stdout


# --- Drift gate -----------------------------------------------------------


def test_drift_cluster_sweep_lives_in_cli_not_agent():
    """The night-watch trigger for the cluster engine belongs to CLI
    startup. agent.py must NOT import cluster / vote / sweep terminology
    — same product-domain-blank gate as Step 6c."""
    import tideline.agent

    source = inspect.getsource(tideline.agent).lower()
    for token in ("cluster", "vote", "rebuild_clusters", "name_clusters"):
        assert token not in source, (
            f"agent.py contains cluster-domain token {token!r}; the agent "
            f"must stay product-domain-blank."
        )

    # And confirm CLI does import it (otherwise this gate gives false confidence)
    import tideline.cli.__main__ as cli_main

    cli_source = inspect.getsource(cli_main)
    assert "cluster_sweep" in cli_source
