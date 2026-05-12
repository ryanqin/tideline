"""Canonical Tideline agent cases (translation flow only).

Post-2026-05-11 scope narrowing: Tideline is a translation engine, not a
chatbot. The agent bench measures **end-to-end translation flow with
correct tool invocation** — equivalently, the A4 atom (which is too
composite to fit the direct-prompt atomic bench infrastructure).

Earlier S* (tool_selection: "what have I been seeing") and N* (no_tool:
"hello") cases tested chatbot behaviors that aren't real product
interactions (drawer/candidate queries are UI-direct, not dialogue).
They were removed; their measurement role is now covered by the atomic
bench's Tier B suite — concept matching, theme extraction, etc., as
direct LLM operations not gated through tool dispatch.

Arg checks are intentionally lenient: `target_lang` may come in as "zh"
or "chinese" or "Chinese"; either is acceptable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolCallExpectation:
    name: str
    args_check: Callable[[dict], bool] | None = None


@dataclass(frozen=True)
class AgentCase:
    id: str
    category: str
    prompt: str
    expected_tool_calls: tuple[ToolCallExpectation, ...] = field(default_factory=tuple)
    max_turns: int = 5


def _lang_match(value: str, *tokens: str) -> bool:
    """target_lang accepts code, name, or any token in the family."""
    v = value.lower().strip()
    return any(t.lower() in v for t in tokens)


def _original_is(text: str) -> Callable[[dict], bool]:
    target = text.lower().strip().strip("'\"")
    return lambda args: args.get("original", "").lower().strip().strip("'\"") == target


def _and(*checks: Callable[[dict], bool]) -> Callable[[dict], bool]:
    return lambda args: all(c(args) for c in checks)


CASES: tuple[AgentCase, ...] = (
    # --- translation_flow -------------------------------------------------
    AgentCase(
        id="T1",
        category="translation_flow",
        prompt="translate hello to Chinese",
        expected_tool_calls=(
            ToolCallExpectation(
                name="add_translation",
                args_check=_and(
                    _original_is("hello"),
                    lambda a: _lang_match(a.get("target_lang", ""), "chin", "zh"),
                ),
            ),
        ),
    ),
    AgentCase(
        id="T2",
        category="translation_flow",
        prompt="translate ラーメン to English",
        expected_tool_calls=(
            ToolCallExpectation(
                name="add_translation",
                args_check=_and(
                    _original_is("ラーメン"),
                    lambda a: _lang_match(a.get("target_lang", ""), "eng", "en"),
                ),
            ),
        ),
    ),
    AgentCase(
        id="T3",
        category="translation_flow",
        prompt="translate good morning to French",
        expected_tool_calls=(
            ToolCallExpectation(
                name="add_translation",
                args_check=_and(
                    _original_is("good morning"),
                    lambda a: _lang_match(a.get("target_lang", ""), "fren", "fr"),
                ),
            ),
        ),
    ),
    AgentCase(
        id="T4",
        category="translation_flow",
        prompt="could you translate 'thank you' into German",
        expected_tool_calls=(
            ToolCallExpectation(
                name="add_translation",
                args_check=_and(
                    _original_is("thank you"),
                    lambda a: _lang_match(a.get("target_lang", ""), "germ", "de"),
                ),
            ),
        ),
    ),
    AgentCase(
        id="T5",
        category="translation_flow",
        prompt="translate the bill to Japanese",
        expected_tool_calls=(
            ToolCallExpectation(
                name="add_translation",
                args_check=_and(
                    _original_is("the bill"),
                    lambda a: _lang_match(a.get("target_lang", ""), "japan", "ja"),
                ),
            ),
        ),
    ),
)


def cases_by_category() -> dict[str, list[AgentCase]]:
    out: dict[str, list[AgentCase]] = {}
    for c in CASES:
        out.setdefault(c.category, []).append(c)
    return out
