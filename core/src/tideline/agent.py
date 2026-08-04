from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from tideline.format import (
    build_prompt,
    make_turn,
    parse_response,
    serialize_tool_response,
)
from tideline.runtime import ModelRuntime
from tideline.tools import ToolRegistry


_DEFAULT_SYSTEM = "You are a helpful assistant."

BUDGET_EXHAUSTED_TEXT = "[agent] turn budget exhausted"


@dataclass
class AgentResult:
    """What a run produced, and whether it finished.

    `run()` hands back only `text`, which is enough for a human reading a CLI
    but not for a caller deciding whether to show a user a result: a run that
    burned its turns has `text` too, and it is not an answer. `finish_reason`
    is the part callers have to branch on.
    """

    text: str
    finish_reason: Literal["stop", "budget_exhausted"] = "stop"
    # Tool failures fed back to the model during this run. Empty on a clean
    # run; a run can recover from these and still finish "stop".
    tool_errors: list[str] = field(default_factory=list)


class Agent:
    def __init__(
        self,
        runtime: ModelRuntime,
        registry: ToolRegistry | None = None,
        context: dict[str, Any] | None = None,
        max_turns: int = 5,
        system_message: str = _DEFAULT_SYSTEM,
    ) -> None:
        self._runtime = runtime
        self._registry = registry or ToolRegistry()
        self._context = context or {}
        self._max_turns = max_turns
        self._system_message = system_message

    def run(self, prompt: str) -> str:
        """The model's final text. Use `run_result` when you need to know
        whether the run actually finished."""
        return self.run_result(prompt).text

    def run_result(self, prompt: str) -> AgentResult:
        declarations = self._registry.all_declarations()
        system_content = self._system_message
        if declarations:
            system_content = f"{system_content}\n{declarations}"

        history: list[str] = [
            make_turn("system", system_content),
            make_turn("user", prompt),
        ]
        tool_errors: list[str] = []

        for _ in range(self._max_turns):
            full_prompt = build_prompt(history)
            raw = self._runtime.generate(full_prompt)
            try:
                response = parse_response(raw)
            except ValueError as exc:
                # A malformed tool call — an unterminated string, usually. A
                # small model producing slightly-off syntax is weather, not a
                # crash: take the turn as plain text and let the caller judge
                # what it's worth. Previously this ValueError left Agent.run
                # and reached the user as a 500.
                tool_errors.append(f"unparseable tool call: {exc}")
                return AgentResult(
                    text=raw.strip(),
                    finish_reason="stop",
                    tool_errors=tool_errors,
                )

            if response.finish_reason == "stop":
                return AgentResult(
                    text=response.text,
                    finish_reason="stop",
                    tool_errors=tool_errors,
                )

            history.append(make_turn("model", response.raw))

            for tc in response.tool_calls:
                try:
                    result = self._registry.invoke(tc.name, tc.args, self._context)
                except Exception as exc:  # noqa: BLE001 — deliberate, see below
                    # A hallucinated tool name, a missing required argument, a
                    # tool raising: the model can often fix these if it's told.
                    # Feed the error back as that tool's response and let it
                    # try again inside the same turn budget — that is what the
                    # budget is for. The blanket except is deliberate: a tool
                    # is arbitrary code, and no failure inside one should be
                    # able to take down the caller.
                    result = f"error: {type(exc).__name__}: {exc}"
                    tool_errors.append(f"{tc.name}: {result}")
                history.append(
                    make_turn("tool", serialize_tool_response(tc.name, result))
                )

        return AgentResult(
            text=BUDGET_EXHAUSTED_TEXT,
            finish_reason="budget_exhausted",
            tool_errors=tool_errors,
        )
