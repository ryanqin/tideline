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


# Six terms, chosen so the script varies (Latin, accented Latin, kana, kanji,
# hangul, a multi-word phrase) — a small model's tool call can come apart on
# the argument it has to copy verbatim, not just on the instruction.
_TERMS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("hello", "Chinese", ("chin", "zh")),
    ("ラーメン", "English", ("eng", "en")),
    ("good morning", "French", ("fren", "fr")),
    ("thank you", "German", ("germ", "de")),
    ("the bill", "Japanese", ("japan", "ja")),
    ("한글", "English", ("eng", "en")),
)

# Five phrasings. P1 is the one production actually sends (web/app.py builds
# `translate {text} to {native}`), so it carries the most weight when reading
# a regression; the rest are the CLI's and any future client's freedom, and
# they are where instruction-following usually breaks first.
_PHRASINGS: tuple[tuple[str, str], ...] = (
    ("P1", "translate {term} to {lang}"),
    ("P2", "could you translate '{term}' into {lang}"),
    ("P3", "what is {term} in {lang}?"),
    ("P4", "{term} -> {lang}"),
    ("P5", "Please translate the following into {lang}: {term}"),
)


def _build_cases() -> tuple[AgentCase, ...]:
    out: list[AgentCase] = []
    for term_idx, (term, lang, tokens) in enumerate(_TERMS, start=1):
        for phrasing_id, template in _PHRASINGS:
            out.append(
                AgentCase(
                    id=f"T{term_idx}{phrasing_id}",
                    category="translation_flow",
                    prompt=template.format(term=term, lang=lang),
                    expected_tool_calls=(
                        ToolCallExpectation(
                            name="add_translation",
                            args_check=_and(
                                _original_is(term),
                                lambda a, tk=tokens: _lang_match(
                                    a.get("target_lang", ""), *tk
                                ),
                            ),
                        ),
                    ),
                )
            )
    return tuple(out)


# 30 cases. It was 5, which meant one case was 20 points and no measurement
# could tell a real change from a coin flip — an instrument that can only
# report ±20% cannot be used to decide anything about a prompt.
CASES: tuple[AgentCase, ...] = _build_cases()


def cases_by_category() -> dict[str, list[AgentCase]]:
    out: dict[str, list[AgentCase]] = {}
    for c in CASES:
        out.setdefault(c.category, []).append(c)
    return out
