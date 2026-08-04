"""Tool base class and registry.

Dispatch is by name, because that is what the model emits: a specific
`call:NAME{...}` that has to reach a specific tool.

There used to be a second index, by "capability class" — borrowed from
OpenClaw and advertised in ARCHITECTURE as this project's headline
borrowing. It was never read: `get_by_capability` had zero callers in
src/, and its only five uses were tests asserting the index existed. Six
of seven tools declared the same capability ("memory"), so the dimension
had no discriminating power either. `Tool.capability` survives as a label
worth keeping on the class; the index it fed does not.

Tools receive a `context` dict at invocation time — that's where shared
resources (DB connection, http client, etc.) get threaded through. The
registry and Tool ABC don't define what goes into context; agents and
callers agree on it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from tideline.format import serialize_tool_declaration


class Tool(ABC):
    name: ClassVar[str]
    capability: ClassVar[str]
    schema: ClassVar[dict[str, str]] = {}
    description: ClassVar[str] = ""
    # Which of `schema`'s keys the model must fill. Sent to the model as
    # part of the declaration — a small model filling arguments needs to
    # know which ones aren't optional.
    required: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def run(self, args: dict[str, Any], context: dict[str, Any]) -> Any:
        raise NotImplementedError


class ToolRegistry:
    def __init__(self) -> None:
        self._by_name: dict[str, type[Tool]] = {}

    def register(self, tool_class: type[Tool]) -> None:
        if tool_class.name in self._by_name:
            raise ValueError(f"Tool name '{tool_class.name}' already registered")
        self._by_name[tool_class.name] = tool_class

    def get_by_name(self, name: str) -> type[Tool] | None:
        return self._by_name.get(name)

    def all_declarations(self) -> str:
        return "\n".join(
            serialize_tool_declaration(
                cls.name, cls.schema, cls.description, cls.required
            )
            for cls in self._by_name.values()
        )

    def invoke(
        self,
        name: str,
        args: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> Any:
        cls = self._by_name.get(name)
        if cls is None:
            raise KeyError(f"No tool named '{name}' registered")
        return cls().run(args, context or {})
