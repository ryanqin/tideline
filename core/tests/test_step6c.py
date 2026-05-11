"""Step 6c verification: auto-promotion as a night-watch sweep on CLI startup.

Step 6b made promotion explicit (`python -m tideline.promotion`). Step 6c
hooks it into the CLI startup path so the agent's candidate view is always
fresh without the user (or a cron) having to remember to sweep.

Functional gates:
- Seeded DB + plain CLI invocation → candidates table populated without
  any explicit `tideline.promotion` call
- Auto-sweep is silent: no "Promoted N" noise on stdout for normal requests
- Uses the default threshold (3) — same shape as the Step 6b explicit run
- Empty DB → CLI works fine; sweep finds nothing, doesn't crash

Drift gates:
- Auto-promote lives in CLI, NOT in agent.py (the agent stays
  product-domain-blank — same gate as Step 6b)
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


# --- Auto-promotion fires on startup -------------------------------------


def test_seeded_db_then_cli_auto_promotes(tmp_path):
    db_path = tmp_path / "test.db"
    subprocess.run(
        [sys.executable, "-m", "tideline.seed", "--db", str(db_path)],
        capture_output=True, text=True, check=True,
    )

    # Verify no candidates exist yet
    conn = sqlite3.connect(str(db_path))
    pre = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    conn.close()
    assert pre == 0, "test setup broken: candidates already populated"

    # Run a plain CLI request — auto-promote should fire on startup
    result = _cli("hello", db=str(db_path))
    assert result.returncode == 0, result.stderr

    # Now candidates should be populated
    conn = sqlite3.connect(str(db_path))
    post = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    conn.close()
    assert post >= 10, f"expected auto-promote to surface >= 10 candidates, got {post}"


def test_auto_promote_uses_default_threshold_of_3(tmp_path):
    """Every auto-promoted row must have occurrence_count >= 3."""
    db_path = tmp_path / "test.db"
    subprocess.run(
        [sys.executable, "-m", "tideline.seed", "--db", str(db_path)],
        capture_output=True, text=True, check=True,
    )
    _cli("hello", db=str(db_path))

    conn = sqlite3.connect(str(db_path))
    bad = conn.execute(
        "SELECT original, occurrence_count FROM candidates WHERE occurrence_count < 3"
    ).fetchall()
    conn.close()
    assert not bad, f"sub-threshold rows leaked: {bad}"


# test_seed_then_cli_surfaces_candidates_no_explicit_promotion removed
# 2026-05-11: the CLI is no longer a conversational gateway to candidates.
# Auto-promotion still fires silently on startup (verified by
# test_seeded_db_then_cli_auto_promotes above, which reads the candidates
# table directly to confirm the sweep happened).


# --- The sweep is silent --------------------------------------------------


def test_auto_promote_produces_no_stdout_noise():
    """On unrelated requests, CLI output is exactly the agent's reply —
    no 'Promoted N candidate(s)' line bleeding in from the sweep."""
    result = _cli("hello")
    assert result.returncode == 0
    assert result.stdout.strip() == "[mock] echo: hello"
    assert "Promoted" not in result.stdout
    assert "candidate" not in result.stdout.lower()


def test_auto_promote_survives_empty_db():
    """Fresh in-memory DB with no translations: sweep finds nothing,
    CLI still answers normally."""
    result = _cli("hello")
    assert result.returncode == 0, result.stderr
    assert "[mock] echo: hello" in result.stdout


# --- Drift gate -----------------------------------------------------------


def test_drift_auto_promote_lives_in_cli_not_agent():
    """The night-watch trigger belongs to the CLI startup path. agent.py
    must NOT import promotion — same product-domain-blank gate as Step 6b,
    sharpened to catch the auto-promote temptation specifically."""
    import tideline.agent

    source = inspect.getsource(tideline.agent).lower()
    assert "promote" not in source
    assert "promotion" not in source

    # And confirm CLI does import it (otherwise this test gives false confidence)
    import tideline.cli.__main__ as cli_main

    cli_source = inspect.getsource(cli_main)
    assert "promote_candidates" in cli_source


# --- Surviving CLI smoke after scope narrowing ---------------------------


def test_translate_cli_still_works_with_auto_promote():
    """Auto-promote on startup must not interfere with the translation flow."""
    assert _cli("hello").stdout.strip() == "[mock] echo: hello"
    assert "[mock-translated to zh] hello" in _cli("translate hello to zh").stdout
