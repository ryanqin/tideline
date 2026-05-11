"""Step 2 verification: tool registry + end-to-end turn loop + drift gates.

Functional gate — agent.run("noop") with NoopTool registered drives a real
turn loop (Mock emits a tool_call, registry dispatches noop, result feeds
back, Mock wraps up) and returns "noop done" within the turn budget.

Drift gates:
1. Registry is **capability-indexed** — get_by_capability returns a list,
   not a single tool. Multiple tools per capability is the OpenClaw promise.
2. The OpenAI JSON-schema interlayer is gone. Catches accidental reintroduction
   of `from openai`, `model_json_schema(`, or `json_schema` anywhere in src/.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tideline.agent import Agent
from tideline.runtimes import get_runtime
from tideline.tools import NoopTool, Tool, ToolRegistry


CORE_SRC = Path(__file__).resolve().parent.parent / "src" / "tideline"


# --- Registry -------------------------------------------------------------


def test_registry_get_by_name():
    reg = ToolRegistry()
    reg.register(NoopTool)
    assert reg.get_by_name("noop") is NoopTool
    assert reg.get_by_name("nonexistent") is None


def test_registry_rejects_duplicate_name():
    reg = ToolRegistry()
    reg.register(NoopTool)
    with pytest.raises(ValueError, match="already registered"):
        reg.register(NoopTool)


def test_registry_invoke_dispatches_to_tool():
    reg = ToolRegistry()
    reg.register(NoopTool)
    assert reg.invoke("noop", {}) == "noop done"


def test_registry_invoke_unknown_tool_raises():
    reg = ToolRegistry()
    with pytest.raises(KeyError):
        reg.invoke("ghost", {})


def test_registry_all_declarations_includes_registered_tool():
    reg = ToolRegistry()
    reg.register(NoopTool)
    assert "<|tool>declaration:noop{}<tool|>" in reg.all_declarations()


# --- Drift gates ----------------------------------------------------------


def test_drift_registry_indexed_by_capability():
    """Multiple tools per capability all surface via get_by_capability."""

    class AltNoop(Tool):
        name = "noop_alt"
        capability = "noop"
        schema: dict[str, str] = {}
        description = "An alternative no-op."

        def run(self, args: dict[str, Any]) -> str:
            return "alt noop done"

    reg = ToolRegistry()
    reg.register(NoopTool)
    reg.register(AltNoop)

    by_cap = reg.get_by_capability("noop")
    assert isinstance(by_cap, list)
    assert NoopTool in by_cap
    assert AltNoop in by_cap
    assert len(by_cap) == 2

    by_cap_missing = reg.get_by_capability("does_not_exist")
    assert by_cap_missing == []


def test_drift_no_openai_schema_dependency():
    """OpenAI JSON schema was an inherited-premise abstraction — dropped on
    2026-05-08 once Gemma's real format was confirmed. Catch any drift back.
    """
    forbidden = ["from openai", "model_json_schema(", "json_schema"]
    for py_file in CORE_SRC.rglob("*.py"):
        content = py_file.read_text()
        for token in forbidden:
            assert token not in content, (
                f"{py_file.relative_to(CORE_SRC)} contains forbidden token "
                f"{token!r}; OpenAI JSON schema was deliberately dropped as the "
                f"tool definition format. If reintroducing this is intentional, "
                f"update this guard with a design-discussion link."
            )


# --- End-to-end smoke ----------------------------------------------------


def test_agent_run_noop_completes_turn_loop():
    """Full Step 2 functional gate: noop tool + Mock + Agent → 'noop done'."""
    registry = ToolRegistry()
    registry.register(NoopTool)
    agent = Agent(get_runtime("mock"), registry=registry)
    assert agent.run("please run noop") == "noop done"


def test_agent_run_hello_preserves_step1_echo():
    """Step 1 smoke behavior must still hold: non-tool prompts echo through Mock."""
    registry = ToolRegistry()
    registry.register(NoopTool)
    agent = Agent(get_runtime("mock"), registry=registry)
    assert agent.run("hello") == "[mock] echo: hello"


def test_cli_smoke_step1_unchanged():
    """The Step 1 CLI smoke command still works end-to-end after Step 2 widening."""
    result = subprocess.run(
        [sys.executable, "-m", "tideline.cli", "--runtime", "mock", "--db", ":memory:", "hello"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip() == "[mock] echo: hello"


# test_cli_smoke_noop_drives_turn_loop removed 2026-05-11: NoopTool is a test
# fixture, not a product feature. After the translation-engine scope
# narrowing, the CLI registers only AddTranslationTool. Noop dispatch via
# CLI is no longer a supported interaction. The agent-level turn loop is
# still covered by test_agent_run_noop_completes_turn_loop above (which
# constructs a custom registry directly).
