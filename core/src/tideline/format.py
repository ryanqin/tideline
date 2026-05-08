"""Gemma 4 chat-format serializer + parser.

Single source of truth for how we frame prompts and read model output.
Keeps the agent format-agnostic above this module.

Reference: tests/fixtures/gemma_outputs.py (verbatim from official docs).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal


STRING_DELIM = '<|"|>'
TURN_OPEN = "<|turn>"
TURN_CLOSE = "<turn|>"
TOOL_CALL_OPEN = "<|tool_call>"
TOOL_CALL_CLOSE = "<tool_call|>"
TOOL_DECL_OPEN = "<|tool>"
TOOL_DECL_CLOSE = "<tool|>"
TOOL_RESPONSE_OPEN = "<|tool_response>"
TOOL_RESPONSE_CLOSE = "<tool_response|>"


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    raw: str


@dataclass
class Response:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: Literal["stop", "tool_calls", "length"] = "stop"
    raw: str = ""


_TOOL_CALL_RE = re.compile(
    re.escape(TOOL_CALL_OPEN) + r"(.+?)" + re.escape(TOOL_CALL_CLOSE),
    re.DOTALL,
)
_CALL_HEAD_RE = re.compile(r"call:(\w+)\{(.*)\}", re.DOTALL)


def parse_response(raw: str) -> Response:
    tool_calls: list[ToolCall] = []
    for match in _TOOL_CALL_RE.finditer(raw):
        head = _CALL_HEAD_RE.match(match.group(1))
        if not head:
            continue
        tool_calls.append(
            ToolCall(
                name=head.group(1),
                args=_parse_body(head.group(2)),
                raw=match.group(0),
            )
        )

    text = _TOOL_CALL_RE.sub("", raw).strip()
    finish: Literal["stop", "tool_calls", "length"] = (
        "tool_calls" if tool_calls else "stop"
    )
    return Response(text=text, tool_calls=tool_calls, finish_reason=finish, raw=raw)


def _parse_body(body: str) -> dict[str, Any]:
    body = body.strip()
    if not body:
        return {}

    args: dict[str, Any] = {}
    pos = 0
    n = len(body)

    while pos < n:
        colon = body.find(":", pos)
        if colon == -1:
            break
        key = body[pos:colon].strip()
        pos = colon + 1
        while pos < n and body[pos] in " \t":
            pos += 1

        if body[pos:pos + len(STRING_DELIM)] == STRING_DELIM:
            pos += len(STRING_DELIM)
            close = body.find(STRING_DELIM, pos)
            if close == -1:
                raise ValueError(f"unterminated string in body: {body!r}")
            args[key] = body[pos:close]
            pos = close + len(STRING_DELIM)
        else:
            comma = body.find(",", pos)
            if comma == -1:
                raw_val = body[pos:].strip()
                pos = n
            else:
                raw_val = body[pos:comma].strip()
                pos = comma
            args[key] = _coerce_scalar(raw_val)

        if pos < n and body[pos] == ",":
            pos += 1

    return args


def _coerce_scalar(s: str) -> Any:
    s = s.strip()
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def serialize_tool_declaration(name: str, schema: dict[str, str]) -> str:
    parts = [
        f"{key}:{STRING_DELIM}{type_}{STRING_DELIM}"
        for key, type_ in schema.items()
    ]
    body = ",".join(parts)
    return f"{TOOL_DECL_OPEN}declaration:{name}{{{body}}}{TOOL_DECL_CLOSE}"


def serialize_tool_response(name: str, result: Any) -> str:
    body = f"result:{STRING_DELIM}{result}{STRING_DELIM}"
    return f"{TOOL_RESPONSE_OPEN}response:{name}{{{body}}}{TOOL_RESPONSE_CLOSE}"


def make_turn(role: str, content: str) -> str:
    return f"{TURN_OPEN}{role}\n{content}{TURN_CLOSE}"


def build_prompt(history: list[str], generation_role: str = "model") -> str:
    return "\n".join(history) + f"\n{TURN_OPEN}{generation_role}\n"
