"""Canonical Tideline agent cases.

Three categories of prompts probe distinct agent capabilities:

- translation_flow: "translate X to Y" must call add_translation with
  shapely-matched args (original ≈ X, target_lang signals Y).
- tool_selection: ambient requests must dispatch to the right tool from
  the memory capability cluster.
- no_tool_off_task: requests that are out of scope should NOT fire any
  tool — the agent's restraint matters as much as its tool use.

Arg checks are intentionally lenient: `target_lang` may come in as "zh"
or "chinese" or "Chinese"; either is acceptable. Strict equality would
penalize valid model variation we don't actually care about.
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
    # --- tool_selection ---------------------------------------------------
    AgentCase(
        id="S1",
        category="tool_selection",
        prompt="what have I been seeing lately?",
        expected_tool_calls=(ToolCallExpectation(name="list_candidates"),),
    ),
    AgentCase(
        id="S2",
        category="tool_selection",
        prompt="show me my drawers",
        expected_tool_calls=(ToolCallExpectation(name="list_drawers"),),
    ),
    AgentCase(
        id="S3",
        category="tool_selection",
        prompt="remember: try yakisoba next time",
        expected_tool_calls=(
            ToolCallExpectation(
                name="add_drawer",
                args_check=lambda a: "yakisoba" in a.get("content", "").lower(),
            ),
        ),
    ),
    AgentCase(
        id="S4",
        category="tool_selection",
        prompt="list my translations",
        expected_tool_calls=(ToolCallExpectation(name="list_translations"),),
    ),
    AgentCase(
        id="S5",
        category="tool_selection",
        prompt="what's emerging?",
        expected_tool_calls=(ToolCallExpectation(name="list_candidates"),),
    ),
    # --- no_tool_off_task -------------------------------------------------
    AgentCase(
        id="N1",
        category="no_tool_off_task",
        prompt="hello",
        expected_tool_calls=(),
    ),
    AgentCase(
        id="N2",
        category="no_tool_off_task",
        prompt="what is 2 plus 2?",
        expected_tool_calls=(),
    ),
    AgentCase(
        id="N3",
        category="no_tool_off_task",
        prompt="write me a poem about clouds",
        expected_tool_calls=(),
    ),
)


def cases_by_category() -> dict[str, list[AgentCase]]:
    out: dict[str, list[AgentCase]] = {}
    for c in CASES:
        out.setdefault(c.category, []).append(c)
    return out
