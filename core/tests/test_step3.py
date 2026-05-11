"""Step 3 verification: L4 memory-as-tools.

Functional gates:
- AddDrawerTool writes a row to the drawers table
- ListDrawersTool reads rows back, ordered by id
- End-to-end via Mock + Agent: "remember: hello" then "list drawers" both work

Drift gates:
- Two tools sharing capability "memory" both surface from get_by_capability —
  the real-world pressure test that capability-indexed registry holds up
  when more than one tool occupies the same capability slot.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys

import pytest

from tideline.agent import Agent
from tideline.runtimes import get_runtime
from tideline.tools import (
    AddDrawerTool,
    ListDrawersTool,
    NoopTool,
    ToolRegistry,
)
from tideline.tools.memory import init_db


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    init_db(c)
    yield c
    c.close()


# --- Tool unit tests ------------------------------------------------------


def test_add_drawer_writes_row(conn):
    result = AddDrawerTool().run({"content": "first sediment"}, {"db": conn})
    assert result == "drawer #1 added"

    rows = conn.execute("SELECT id, content FROM drawers").fetchall()
    assert rows == [(1, "first sediment")]


def test_list_drawers_empty(conn):
    assert ListDrawersTool().run({}, {"db": conn}) == "no drawers yet"


def test_list_drawers_returns_in_id_order(conn):
    AddDrawerTool().run({"content": "alpha"}, {"db": conn})
    AddDrawerTool().run({"content": "beta"}, {"db": conn})
    out = ListDrawersTool().run({}, {"db": conn})
    assert out == "#1: alpha\n#2: beta"


# --- Drift gate: capability-indexed under multi-tool pressure -------------


def test_drift_memory_capability_holds_two_tools():
    """Add and list both register under 'memory'. get_by_capability must
    return both — the real check on whether L2's capability index works
    when a capability has multiple inhabitants (not just multi-tool noop
    via test scaffolding, but actual production tools)."""
    registry = ToolRegistry()
    registry.register(AddDrawerTool)
    registry.register(ListDrawersTool)

    memory_tools = registry.get_by_capability("memory")
    assert len(memory_tools) == 2
    assert AddDrawerTool in memory_tools
    assert ListDrawersTool in memory_tools


def test_drift_memory_tools_have_distinct_names():
    registry = ToolRegistry()
    registry.register(AddDrawerTool)
    registry.register(ListDrawersTool)

    assert registry.get_by_name("add_drawer") is AddDrawerTool
    assert registry.get_by_name("list_drawers") is ListDrawersTool


# --- End-to-end via Agent + Mock ------------------------------------------


def test_agent_remember_writes_to_db(conn):
    registry = ToolRegistry()
    registry.register(NoopTool)
    registry.register(AddDrawerTool)
    registry.register(ListDrawersTool)
    agent = Agent(get_runtime("mock"), registry=registry, context={"db": conn})

    result = agent.run("remember: hello world")

    assert result == "drawer #1 added"
    rows = conn.execute("SELECT content FROM drawers").fetchall()
    assert rows == [("hello world",)]


def test_agent_list_drawers_returns_contents(conn):
    conn.execute("INSERT INTO drawers (content) VALUES (?)", ("from a previous run",))
    conn.commit()

    registry = ToolRegistry()
    registry.register(NoopTool)
    registry.register(AddDrawerTool)
    registry.register(ListDrawersTool)
    agent = Agent(get_runtime("mock"), registry=registry, context={"db": conn})

    result = agent.run("list drawers")

    assert "from a previous run" in result


def test_agent_remember_then_list_in_same_session(conn):
    registry = ToolRegistry()
    registry.register(NoopTool)
    registry.register(AddDrawerTool)
    registry.register(ListDrawersTool)
    agent = Agent(get_runtime("mock"), registry=registry, context={"db": conn})

    agent.run("remember: first")
    agent.run("remember: second")
    listed = agent.run("list drawers")

    assert "first" in listed
    assert "second" in listed


# --- CLI smoke ------------------------------------------------------------


def _cli(*extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "tideline.cli", "--runtime", "mock", "--db", ":memory:", *extra],
        capture_output=True,
        text=True,
    )


# test_cli_remember_smoke + test_cli_step2_noop_still_works_with_memory_layer
# removed 2026-05-11: the CLI is now a translation engine only and no longer
# registers AddDrawerTool or NoopTool. Tideline is not a chatbot — "remember:"
# and "noop" are not real product interactions. Unit-level coverage of
# AddDrawerTool / NoopTool remains via the agent + custom registry tests
# above.


def test_cli_step1_echo_still_works_with_memory_layer():
    """Mock's fallthrough echo behavior survives Step 3's L4 layer addition."""
    result = _cli("hello")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[mock] echo: hello"
