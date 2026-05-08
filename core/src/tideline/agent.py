from __future__ import annotations

from typing import Any

from tideline.format import (
    build_prompt,
    make_turn,
    parse_response,
    serialize_tool_response,
)
from tideline.runtime import ModelRuntime
from tideline.tools import ToolRegistry


class Agent:
    def __init__(
        self,
        runtime: ModelRuntime,
        registry: ToolRegistry | None = None,
        context: dict[str, Any] | None = None,
        max_turns: int = 5,
    ) -> None:
        self._runtime = runtime
        self._registry = registry or ToolRegistry()
        self._context = context or {}
        self._max_turns = max_turns

    def run(self, prompt: str) -> str:
        history: list[str] = [make_turn("user", prompt)]

        for _ in range(self._max_turns):
            full_prompt = build_prompt(history)
            raw = self._runtime.generate(full_prompt)
            response = parse_response(raw)

            if response.finish_reason == "stop":
                return response.text

            history.append(make_turn("model", response.raw))

            for tc in response.tool_calls:
                result = self._registry.invoke(tc.name, tc.args, self._context)
                history.append(
                    make_turn("tool", serialize_tool_response(tc.name, result))
                )

        return "[agent] turn budget exhausted"
