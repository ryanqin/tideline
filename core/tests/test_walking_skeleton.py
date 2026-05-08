"""Step 1 verification: walking skeleton functional + drift gates.

Functional gate — `python -m tideline.cli --runtime mock "hello"` prints the
expected output and exits 0.

Drift gates — the architectural properties this step was meant to preserve:
1. The agent module is IO-free: no argparse, no sys.argv, no input/print.
   Lets us later swap in HTTP/Android transport without touching the agent.
2. The CLI only imports the public surface (Agent + runtime registry).
   Lets the agent grow internal complexity without dragging the CLI along.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path


CORE_SRC = Path(__file__).resolve().parent.parent / "src" / "tideline"


def test_smoke_mock_runtime_end_to_end():
    result = subprocess.run(
        [sys.executable, "-m", "tideline.cli", "--runtime", "mock", "--db", ":memory:", "hello"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert result.stdout.strip() == "[mock] echo: hello"


def test_drift_agent_module_is_io_free():
    import tideline.agent

    source = inspect.getsource(tideline.agent)
    forbidden = ["import sys", "import argparse", "argv", "input(", "print("]
    found = [token for token in forbidden if token in source]
    assert not found, (
        f"agent.py contains IO-coupled tokens {found}; the agent must stay "
        f"transport-agnostic so we can later plug in HTTP/Android."
    )


def test_drift_cli_imports_only_public_surface():
    cli_main = CORE_SRC / "cli" / "__main__.py"
    tree = ast.parse(cli_main.read_text())

    allowed = {
        "argparse",
        "sys",
        "sqlite3",
        "pathlib",
        "tideline.agent",
        "tideline.runtimes",
        "tideline.tools",
        "tideline.tools.memory",
    }
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)

    extras = imports - allowed
    assert not extras, (
        f"CLI imports outside the allowed public surface: {extras}. "
        f"If intentional, update the allowlist after a design discussion."
    )
