"""Tool base class and capability-indexed registry.

Registry indexes by **capability class**, not just by name (the OpenClaw
borrow). Tools sharing a capability all surface via `get_by_capability()`.
Name lookup is also exposed because the model emits a specific
`call:NAME{...}` and we need to dispatch on that exact name.

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

    @abstractmethod
    def run(self, args: dict[str, Any], context: dict[str, Any]) -> Any:
        raise NotImplementedError


class ToolRegistry:
    def __init__(self) -> None:
        self._by_name: dict[str, type[Tool]] = {}
        self._by_capability: dict[str, list[type[Tool]]] = {}

    def register(self, tool_class: type[Tool]) -> None:
        if tool_class.name in self._by_name:
            raise ValueError(f"Tool name '{tool_class.name}' already registered")
        self._by_name[tool_class.name] = tool_class
        self._by_capability.setdefault(tool_class.capability, []).append(tool_class)

    def get_by_name(self, name: str) -> type[Tool] | None:
        return self._by_name.get(name)

    def get_by_capability(self, capability: str) -> list[type[Tool]]:
        return list(self._by_capability.get(capability, []))

    def all_declarations(self) -> str:
        return "\n".join(
            serialize_tool_declaration(cls.name, cls.schema)
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
