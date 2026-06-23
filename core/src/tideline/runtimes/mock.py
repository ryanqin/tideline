from __future__ import annotations

import re

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
_LIST_TRANSLATIONS_CALL = (
    f"{TOOL_CALL_OPEN}call:list_translations{{}}{TOOL_CALL_CLOSE}"
)
_LIST_CANDIDATES_CALL = (
    f"{TOOL_CALL_OPEN}call:list_candidates{{}}{TOOL_CALL_CLOSE}"
)

# "translate <text> to <lang>" — captures the text and target language.
# The text capture is lazy so "to" inside text doesn't break parsing.
_TRANSLATE_RE = re.compile(
    r"translate\s+(.+?)\s+to\s+(\w+)",
    re.IGNORECASE | re.DOTALL,
)


class MockRuntime(ModelRuntime):
    """Deterministic test runtime that emits Gemma-formatted output.

    Decision rules (in priority order):
      1. tool_response in prompt → surface its result (terminates turn loop)
      2. user turn matches "translate X to Y" → emit add_translation
      3. user turn starts with "remember:" → emit add_drawer
      4. user turn mentions "list translation" → emit list_translations
      5. user turn mentions "list drawer" / "show drawer" → emit list_drawers
      6. user turn mentions an emergence cue (candidates / been seeing /
         emerging / been translating) → emit list_candidates
      7. user turn mentions "noop" → emit noop tool_call
      8. otherwise → echo (preserves Step 1 behavior)
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

        match = _TRANSLATE_RE.search(stripped)
        if match:
            original = match.group(1).strip().strip("'\"")
            target_lang = match.group(2).strip().strip("'\"").lower()
            # A stand-in "translation": the target tag plus the source REVERSED,
            # never the source verbatim. The translation guard flags output that
            # still IS the input (an echo), so a mock translation must not embed
            # the original — yet reversing keeps each word mapping to a distinct
            # output, so distinct concepts don't fuse on identical text.
            translated = f"[mock-translated to {target_lang}] {original[::-1]}"
            return (
                f"{TOOL_CALL_OPEN}call:add_translation{{"
                f"original:{STRING_DELIM}{original}{STRING_DELIM},"
                f"target_lang:{STRING_DELIM}{target_lang}{STRING_DELIM},"
                f"translated:{STRING_DELIM}{translated}{STRING_DELIM}"
                f"}}{TOOL_CALL_CLOSE}"
            )

        if lower.startswith("remember:"):
            content = stripped.split(":", 1)[1].strip()
            return (
                f"{TOOL_CALL_OPEN}call:add_drawer{{"
                f"content:{STRING_DELIM}{content}{STRING_DELIM}"
                f"}}{TOOL_CALL_CLOSE}"
            )

        if "list translation" in lower or "show translation" in lower:
            return _LIST_TRANSLATIONS_CALL

        if "list drawer" in lower or "show drawer" in lower:
            return _LIST_DRAWERS_CALL

        if (
            "list candidate" in lower
            or "show candidate" in lower
            or "been seeing" in lower
            or "been translating" in lower
            or "what's emerging" in lower
            or "whats emerging" in lower
        ):
            return _LIST_CANDIDATES_CALL

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
