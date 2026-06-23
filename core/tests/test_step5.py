"""Step 5 verification: translation flow + drawer schema upgrade.

Functional gates:
- AddTranslationTool persists rows to translations table
- ListTranslationsTool reads them back, ordered by id
- Mock detects "translate X to Y" → emits add_translation → DB row appears
- CLI smoke: `translate hello to zh` returns the mock translation, table has the row

Drift gates:
- Memory capability now houses 4 tools (add_drawer, list_drawers, add_translation,
  list_translations) — capability-indexed registry holds at this scale
- agent.py contains no translation-specific knowledge (product semantics live
  in CLI's system message + tool descriptions, not in agent code)
"""

from __future__ import annotations

import inspect
import sqlite3
import subprocess
import sys

import pytest

from tideline.agent import Agent
from tideline.runtimes import get_runtime
from tideline.tools import (
    AddDrawerTool,
    AddTranslationTool,
    ListDrawersTool,
    ListTranslationsTool,
    NoopTool,
    ToolRegistry,
    init_all_tables,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    init_all_tables(c)
    yield c
    c.close()


# --- Tool unit tests ------------------------------------------------------


def test_add_translation_writes_row(conn):
    out = AddTranslationTool().run(
        {"original": "hello", "target_lang": "zh", "translated": "你好"},
        {"db": conn},
    )
    assert "translation #1 recorded" in out
    assert "你好" in out

    rows = conn.execute(
        "SELECT id, original, target_lang, translated FROM translations"
    ).fetchall()
    assert rows == [(1, "hello", "zh", "你好")]


def test_list_translations_empty(conn):
    assert ListTranslationsTool().run({}, {"db": conn}) == "no translations yet"


def test_list_translations_returns_in_id_order(conn):
    AddTranslationTool().run(
        {"original": "hello", "target_lang": "zh", "translated": "你好"},
        {"db": conn},
    )
    AddTranslationTool().run(
        {"original": "thanks", "target_lang": "ja", "translated": "ありがとう"},
        {"db": conn},
    )
    out = ListTranslationsTool().run({}, {"db": conn})
    assert "#1: 'hello' → (zh) '你好'" in out
    assert "#2: 'thanks' → (ja) 'ありがとう'" in out


# --- Drift gates ----------------------------------------------------------


def test_drift_memory_capability_now_houses_four_tools():
    """Multi-tool drift gate at production scale: 4 tools share `memory`."""
    registry = ToolRegistry()
    registry.register(AddDrawerTool)
    registry.register(ListDrawersTool)
    registry.register(AddTranslationTool)
    registry.register(ListTranslationsTool)

    memory_tools = registry.get_by_capability("memory")
    assert len(memory_tools) == 4
    assert AddDrawerTool in memory_tools
    assert ListDrawersTool in memory_tools
    assert AddTranslationTool in memory_tools
    assert ListTranslationsTool in memory_tools


def test_drift_agent_has_no_translation_knowledge():
    """agent.py must not encode product-level translation semantics —
    those live in the CLI's system message and tool descriptions."""
    import tideline.agent

    source = inspect.getsource(tideline.agent)
    forbidden = ["translate", "translation", "language", "target_lang"]
    found = [t for t in forbidden if t.lower() in source.lower()]
    assert not found, (
        f"agent.py contains translation-domain tokens {found}; product "
        f"knowledge belongs in system message + tool descriptions, not agent."
    )


# --- End-to-end via Agent + Mock ------------------------------------------


def test_agent_translate_records_to_db(conn):
    registry = ToolRegistry()
    registry.register(NoopTool)
    registry.register(AddDrawerTool)
    registry.register(ListDrawersTool)
    registry.register(AddTranslationTool)
    registry.register(ListTranslationsTool)
    agent = Agent(get_runtime("mock"), registry=registry, context={"db": conn})

    result = agent.run("translate hello to zh")

    # Mock translation = "[mock-translated to zh] olleh"
    assert "[mock-translated to zh] olleh" in result
    rows = conn.execute(
        "SELECT original, target_lang, translated FROM translations"
    ).fetchall()
    assert rows == [("hello", "zh", "[mock-translated to zh] olleh")]


def test_agent_translate_handles_quoted_text(conn):
    registry = ToolRegistry()
    registry.register(AddTranslationTool)
    registry.register(ListTranslationsTool)
    agent = Agent(get_runtime("mock"), registry=registry, context={"db": conn})

    agent.run('translate "good morning" to ja')

    rows = conn.execute("SELECT original, target_lang FROM translations").fetchall()
    assert rows == [("good morning", "ja")]


def test_agent_list_translations_returns_contents(conn):
    conn.execute(
        "INSERT INTO translations (original, target_lang, translated) "
        "VALUES (?, ?, ?)",
        ("hello", "zh", "你好"),
    )
    conn.commit()

    registry = ToolRegistry()
    registry.register(AddTranslationTool)
    registry.register(ListTranslationsTool)
    agent = Agent(get_runtime("mock"), registry=registry, context={"db": conn})

    result = agent.run("list translations")
    assert "hello" in result
    assert "你好" in result


# --- CLI smoke ------------------------------------------------------------


def _cli(*extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable, "-m", "tideline.cli",
            "--runtime", "mock", "--db", ":memory:",
            *extra,
        ],
        capture_output=True,
        text=True,
    )


def test_cli_translate_smoke():
    result = _cli("translate hello to zh")
    assert result.returncode == 0, result.stderr
    assert "[mock-translated to zh] olleh" in result.stdout


# test_cli_step1_2_3_smoke_unchanged_after_step5 removed 2026-05-11: the
# noop/remember CLI assertions covered behaviors that no longer exist after
# the translation-engine scope narrowing. The "hello" echo assertion is
# still covered by test_step2.test_cli_smoke_step1_unchanged.
