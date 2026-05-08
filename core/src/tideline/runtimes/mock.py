from __future__ import annotations

from tideline.format import (
    STRING_DELIM,
    TOOL_CALL_CLOSE,
    TOOL_CALL_OPEN,
    TOOL_RESPONSE_CLOSE,
    TOOL_RESPONSE_OPEN,
    TURN_CLOSE,
    TURN_OPEN,
)
from tideline.runtime import ModelRuntime


_NOOP_CALL = f"{TOOL_CALL_OPEN}call:noop{{}}{TOOL_CALL_CLOSE}"
_LIST_DRAWERS_CALL = f"{TOOL_CALL_OPEN}call:list_drawers{{}}{TOOL_CALL_CLOSE}"


class MockRuntime(ModelRuntime):
    """Deterministic test runtime that emits Gemma-formatted output.

    Decision rules (in priority order):
      1. If a tool_response appears in the prompt, surface its result as the
         final assistant text. This terminates the turn loop with the tool's
         output as the user-visible answer.
      2. If the user turn starts with "remember:", emit add_drawer with the
         remainder as content.
      3. If the user turn mentions "list drawer" / "show drawer", emit
         list_drawers.
      4. If the user turn mentions "noop", emit the noop tool call.
      5. Otherwise, echo the user content (preserves Step 1 smoke behavior).
    """

    def generate(self, prompt: str) -> str:
        last_tool_result = _extract_last_tool_response(prompt)
        if last_tool_result is not None:
            return last_tool_result

        user_content = _last_user_content(prompt)
        if user_content is None:
            return f"[mock] echo: {prompt}"

        stripped = user_content.strip()
        lower = stripped.lower()

        if lower.startswith("remember:"):
            content = stripped.split(":", 1)[1].strip()
            return (
                f"{TOOL_CALL_OPEN}call:add_drawer{{"
                f"content:{STRING_DELIM}{content}{STRING_DELIM}"
                f"}}{TOOL_CALL_CLOSE}"
            )

        if "list drawer" in lower or "show drawer" in lower:
            return _LIST_DRAWERS_CALL

        if "noop" in lower:
            return _NOOP_CALL

        return f"[mock] echo: {user_content}"


def _last_user_content(prompt: str) -> str | None:
    user_marker = f"{TURN_OPEN}user\n"
    if user_marker not in prompt:
        return None
    after = prompt.rsplit(user_marker, 1)[1]
    return after.split(TURN_CLOSE, 1)[0]


def _extract_last_tool_response(prompt: str) -> str | None:
    """Pull the result string out of the most recent <|tool_response>...<tool_response|> block."""
    start = prompt.rfind(TOOL_RESPONSE_OPEN)
    if start == -1:
        return None
    end = prompt.find(TOOL_RESPONSE_CLOSE, start)
    if end == -1:
        return None
    block = prompt[start:end]
    delim_a = block.find(STRING_DELIM)
    if delim_a == -1:
        return None
    delim_b = block.find(STRING_DELIM, delim_a + len(STRING_DELIM))
    if delim_b == -1:
        return None
    return block[delim_a + len(STRING_DELIM):delim_b]
