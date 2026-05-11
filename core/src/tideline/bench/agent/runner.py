"""Agent bench runner.

Each case is one fresh agent run with a RecordingRegistry that captures
the (name, args) of every tool invocation. The run's final response, the
captured invocation list, and the "turn budget exhausted" sentinel
together yield the per-case CaseResult.

Aggregation happens in `agent/metrics.py`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from tideline.agent import Agent
from tideline.bench.agent.cases import CASES, AgentCase, ToolCallExpectation
from tideline.runtime import ModelRuntime
from tideline.runtimes import get_runtime
from tideline.tools import (
    AddDrawerTool,
    AddTranslationTool,
    ListCandidatesTool,
    ListDrawersTool,
    ListTranslationsTool,
    NoopTool,
    ToolRegistry,
    init_all_tables,
)


_BUDGET_EXHAUSTED_SENTINEL = "[agent] turn budget exhausted"

_TIDELINE_SYSTEM = (
    "You are Tideline, a local-first translation assistant. "
    "When the user explicitly asks to translate text, perform the translation "
    "yourself, then call the add_translation tool to record "
    "(original, target_lang, translated) before responding to the user with "
    "the translated text. For other requests, use the available tools as "
    "appropriate. Be concise."
)


class RecordingRegistry(ToolRegistry):
    """ToolRegistry that captures every invocation for later inspection.

    The agent talks to the registry through `.invoke()` only, so subclassing
    that one method is enough — declarations and lookup go through unchanged.
    """

    def __init__(self) -> None:
        super().__init__()
        self.invocations: list[tuple[str, dict[str, Any]]] = []

    def invoke(
        self,
        name: str,
        args: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> Any:
        self.invocations.append((name, dict(args)))
        return super().invoke(name, args, context)


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    category: str
    prompt: str
    expected_tools_called: bool   # all expected calls happened with matching args
    any_tool_called: bool         # at least one tool fired
    wrong_tool_called: bool       # any tool fired AND expected_tools_called is False
    num_tool_calls: int
    budget_exhausted: bool
    response_words: int
    final_response: str


def _match_expectation(
    expectation: ToolCallExpectation,
    invocations: list[tuple[str, dict[str, Any]]],
) -> bool:
    for name, args in invocations:
        if name != expectation.name:
            continue
        if expectation.args_check is None:
            return True
        if expectation.args_check(args):
            return True
    return False


def _build_agent(runtime: ModelRuntime) -> tuple[Agent, RecordingRegistry, sqlite3.Connection]:
    conn = sqlite3.connect(":memory:")
    init_all_tables(conn)
    registry = RecordingRegistry()
    registry.register(NoopTool)
    registry.register(AddDrawerTool)
    registry.register(ListDrawersTool)
    registry.register(AddTranslationTool)
    registry.register(ListTranslationsTool)
    registry.register(ListCandidatesTool)
    agent = Agent(
        runtime,
        registry=registry,
        context={"db": conn},
        system_message=_TIDELINE_SYSTEM,
    )
    return agent, registry, conn


def run_case(runtime: ModelRuntime, case: AgentCase) -> CaseResult:
    agent, registry, conn = _build_agent(runtime)
    try:
        final = agent.run(case.prompt)
    finally:
        conn.close()

    expected_called = all(
        _match_expectation(exp, registry.invocations) for exp in case.expected_tool_calls
    )
    any_called = bool(registry.invocations)
    # When the case explicitly expects NO tools, "expected_tools_called" is
    # trivially True (empty AND). Treat that as success only if no tool fired.
    if not case.expected_tool_calls:
        expected_called = not any_called

    wrong = any_called and not expected_called
    return CaseResult(
        case_id=case.id,
        category=case.category,
        prompt=case.prompt,
        expected_tools_called=expected_called,
        any_tool_called=any_called,
        wrong_tool_called=wrong,
        num_tool_calls=len(registry.invocations),
        budget_exhausted=_BUDGET_EXHAUSTED_SENTINEL in final,
        response_words=len(final.split()),
        final_response=final,
    )


def run(runtime_name: str = "mock") -> list[CaseResult]:
    runtime = get_runtime(runtime_name)
    return [run_case(runtime, case) for case in CASES]
