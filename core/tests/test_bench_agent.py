"""Agent bench infrastructure verification.

Functional gates:
- Case catalog is well-formed (>= 12 cases, all three categories present)
- RecordingRegistry captures invocations transparently (super().invoke
  still dispatches; recorded args are a copy, not a reference)
- run_case produces a fully-populated CaseResult
- summarize produces per-category rows plus an 'all' row
- Mock-based end-to-end: translation_flow and tool_selection cases should
  pass because Mock pattern-matches our prompts; no_tool cases should
  pass because Mock falls through to echo for them
- CLI dispatch: `--suite agent` runs without error

What we DON'T assert: real-model success rates. Those are captured by
running against llama_cpp and recorded in the bench README.
"""

from __future__ import annotations

import subprocess
import sqlite3
import sys

import pytest

from tideline.agent import Agent
from tideline.bench.agent.cases import CASES, AgentCase, ToolCallExpectation, cases_by_category
from tideline.bench.agent.metrics import CategorySummary, summarize, format_summary_table
from tideline.bench.agent.runner import (
    CaseResult,
    RecordingRegistry,
    _BUDGET_EXHAUSTED_SENTINEL,
    run as run_agent_bench,
    run_case,
)
from tideline.runtimes import get_runtime
from tideline.tools import AddDrawerTool, NoopTool, init_all_tables


# --- Case catalog --------------------------------------------------------


def test_case_catalog_has_three_categories():
    by_cat = cases_by_category()
    assert set(by_cat.keys()) == {"translation_flow", "tool_selection", "no_tool_off_task"}


def test_case_catalog_minimum_size():
    assert len(CASES) >= 12, f"expected >= 12 cases, got {len(CASES)}"


def test_each_category_has_minimum_cases():
    by_cat = cases_by_category()
    assert len(by_cat["translation_flow"]) >= 4
    assert len(by_cat["tool_selection"]) >= 4
    assert len(by_cat["no_tool_off_task"]) >= 2


def test_case_ids_are_unique():
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids))


def test_no_tool_cases_have_empty_expected_calls():
    by_cat = cases_by_category()
    for c in by_cat["no_tool_off_task"]:
        assert c.expected_tool_calls == (), f"{c.id} should expect no tool calls"


def test_translation_cases_expect_add_translation():
    by_cat = cases_by_category()
    for c in by_cat["translation_flow"]:
        names = [exp.name for exp in c.expected_tool_calls]
        assert "add_translation" in names, f"{c.id} should expect add_translation"


# --- Case arg checks behave -----------------------------------------------


def test_translation_arg_check_accepts_lang_variants():
    """T1 expects add_translation with target_lang signaling Chinese.
    'zh', 'chinese', 'Chinese' should all match."""
    t1 = next(c for c in CASES if c.id == "T1")
    add_tr = next(e for e in t1.expected_tool_calls if e.name == "add_translation")
    assert add_tr.args_check is not None
    assert add_tr.args_check({"original": "hello", "target_lang": "zh"})
    assert add_tr.args_check({"original": "hello", "target_lang": "chinese"})
    assert add_tr.args_check({"original": "hello", "target_lang": "Chinese"})
    assert not add_tr.args_check({"original": "hello", "target_lang": "japanese"})
    assert not add_tr.args_check({"original": "goodbye", "target_lang": "zh"})


def test_translation_arg_check_handles_quoted_original():
    """T4 has prompt with 'thank you' in quotes; the matcher should strip."""
    t4 = next(c for c in CASES if c.id == "T4")
    add_tr = next(e for e in t4.expected_tool_calls if e.name == "add_translation")
    assert add_tr.args_check({"original": "thank you", "target_lang": "german"})
    assert add_tr.args_check({"original": "'thank you'", "target_lang": "de"})


# --- RecordingRegistry ---------------------------------------------------


def test_recording_registry_captures_invocations():
    registry = RecordingRegistry()
    registry.register(NoopTool)
    registry.register(AddDrawerTool)

    conn = sqlite3.connect(":memory:")
    init_all_tables(conn)

    registry.invoke("noop", {}, {"db": conn})
    registry.invoke("add_drawer", {"content": "hi"}, {"db": conn})

    assert registry.invocations == [("noop", {}), ("add_drawer", {"content": "hi"})]
    conn.close()


def test_recording_registry_args_are_copied_not_referenced():
    """Mutating the original args dict after invoke must not affect the record."""
    registry = RecordingRegistry()
    registry.register(AddDrawerTool)
    conn = sqlite3.connect(":memory:")
    init_all_tables(conn)

    args = {"content": "hi"}
    registry.invoke("add_drawer", args, {"db": conn})
    args["content"] = "MUTATED"

    assert registry.invocations[0][1]["content"] == "hi"
    conn.close()


# --- run_case end-to-end with Mock ---------------------------------------


def test_run_case_returns_populated_result():
    runtime = get_runtime("mock")
    case = next(c for c in CASES if c.id == "T1")
    result = run_case(runtime, case)

    assert isinstance(result, CaseResult)
    assert result.case_id == "T1"
    assert result.category == "translation_flow"
    assert result.prompt == case.prompt
    assert result.num_tool_calls >= 1   # Mock fires add_translation
    assert result.expected_tools_called  # Mock pattern matches
    assert not result.budget_exhausted
    assert result.response_words > 0


def test_mock_passes_simple_translation_pattern():
    """T1-T3, T5 use the literal 'translate X to Y' shape Mock's regex handles.
    Not all T cases (T4 uses 'into' instead of 'to') — Mock is a unit-test
    stub, not an NLP-quality parser. Real models are what the bench measures."""
    runtime = get_runtime("mock")
    for case_id in ("T1", "T2", "T3", "T5"):
        case = next(c for c in CASES if c.id == case_id)
        result = run_case(runtime, case)
        assert result.expected_tools_called, (
            f"{case_id} fits Mock's regex and should pass; got "
            f"invocations={result.num_tool_calls}, final={result.final_response!r}"
        )


def test_mock_passes_emergence_cue_cases():
    """S1 and S5 trigger Mock's 'been seeing' / 'emerging' keywords."""
    runtime = get_runtime("mock")
    for case_id in ("S1", "S5"):
        case = next(c for c in CASES if c.id == case_id)
        result = run_case(runtime, case)
        assert result.expected_tools_called, (
            f"{case_id} matches Mock's emergence keywords and should pass"
        )


def test_mock_no_tool_cases_correctly_fire_nothing():
    """N1-N3: Mock has no pattern for these → must not fire any tool."""
    runtime = get_runtime("mock")
    by_cat = cases_by_category()
    for case in by_cat["no_tool_off_task"]:
        result = run_case(runtime, case)
        assert not result.any_tool_called, (
            f"{case.id} ({case.prompt!r}) should fire NO tools under Mock; "
            f"got {result.num_tool_calls} calls"
        )
        assert result.expected_tools_called  # no expectation → trivially OK


# --- run() and summarize() -----------------------------------------------


def test_full_mock_run_produces_full_case_count():
    results = run_agent_bench("mock")
    assert len(results) == len(CASES)


def test_summarize_includes_per_category_plus_all():
    results = run_agent_bench("mock")
    summaries = summarize(results)
    cats = {s.category for s in summaries}
    assert "translation_flow" in cats
    assert "tool_selection" in cats
    assert "no_tool_off_task" in cats
    assert "all" in cats


def test_summarize_all_row_aggregates_correctly():
    results = run_agent_bench("mock")
    summaries = summarize(results)
    all_row = next(s for s in summaries if s.category == "all")
    assert all_row.n == len(CASES)
    # Rates are fractions in [0, 1] regardless of how Mock scores.
    assert 0.0 <= all_row.task_success_rate <= 1.0
    assert 0.0 <= all_row.wrong_tool_rate <= 1.0
    assert 0.0 <= all_row.budget_exhaustion_rate <= 1.0
    # Mock should never exhaust the turn budget — it always emits a parseable
    # tool call or echoes plain text in one turn.
    assert all_row.budget_exhaustion_rate == 0.0


def test_format_summary_table_renders():
    results = run_agent_bench("mock")
    table = format_summary_table(summarize(results))
    assert "category" in table
    assert "success" in table
    assert "all" in table


# --- CLI -----------------------------------------------------------------


def test_cli_agent_suite_smoke():
    result = subprocess.run(
        [sys.executable, "-m", "tideline.bench", "--suite", "agent", "--runtime", "mock"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "category" in result.stdout
    assert "all" in result.stdout


def test_cli_translate_suite_unchanged():
    """Backward compat: default --suite is translate, behavior matches Step's bench."""
    result = subprocess.run(
        [sys.executable, "-m", "tideline.bench", "--runtime", "mock", "--tier", "phrases"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "scenario" in result.stdout


def test_cli_all_suite_runs_both():
    result = subprocess.run(
        [sys.executable, "-m", "tideline.bench", "--suite", "all", "--runtime", "mock",
         "--tier", "phrases"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "scenario" in result.stdout       # translate output
    assert "category" in result.stdout       # agent output
