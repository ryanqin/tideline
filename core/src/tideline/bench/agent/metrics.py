"""Agent bench aggregation.

Four headline metrics, all 0-1 fractions or simple means:

- task_success_rate: cases where every expected tool call happened with
  shapely args, AND no-tool cases stayed tool-free.
- wrong_tool_rate: cases where the model fired SOME tool but not the
  expected one (or fired a tool when none was expected). Distinguishes
  "didn't understand" from "didn't try".
- budget_exhaustion_rate: cases that hit max_turns without resolving.
- mean_num_tool_calls / mean_response_words: distributional shape.

Per-category breakdowns surface where a model is strong vs. weak
(translation_flow vs tool_selection vs no_tool_off_task).
"""

from __future__ import annotations

from dataclasses import dataclass

from tideline.bench.agent.runner import CaseResult


@dataclass(frozen=True)
class CategorySummary:
    category: str
    n: int
    task_success_rate: float
    wrong_tool_rate: float
    budget_exhaustion_rate: float
    mean_num_tool_calls: float
    mean_response_words: float


def _summarize(category: str, rows: list[CaseResult]) -> CategorySummary:
    n = len(rows)
    if n == 0:
        return CategorySummary(category, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return CategorySummary(
        category=category,
        n=n,
        task_success_rate=sum(r.expected_tools_called for r in rows) / n,
        wrong_tool_rate=sum(r.wrong_tool_called for r in rows) / n,
        budget_exhaustion_rate=sum(r.budget_exhausted for r in rows) / n,
        mean_num_tool_calls=sum(r.num_tool_calls for r in rows) / n,
        mean_response_words=sum(r.response_words for r in rows) / n,
    )


def summarize(results: list[CaseResult]) -> list[CategorySummary]:
    """One CategorySummary per category present, plus one labeled 'all'."""
    by_cat: dict[str, list[CaseResult]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)

    summaries = [_summarize(cat, by_cat[cat]) for cat in sorted(by_cat)]
    summaries.append(_summarize("all", results))
    return summaries


def format_summary_table(summaries: list[CategorySummary]) -> str:
    header = (
        f"{'category':<22} {'n':>3}  {'success':>7}  {'wrong':>6}  "
        f"{'budget':>6}  {'tool/c':>6}  {'words':>5}"
    )
    sep = "-" * len(header)
    lines = [header, sep]
    for s in summaries:
        lines.append(
            f"{s.category:<22} {s.n:>3}  "
            f"{s.task_success_rate * 100:6.1f}%  "
            f"{s.wrong_tool_rate * 100:5.1f}%  "
            f"{s.budget_exhaustion_rate * 100:5.1f}%  "
            f"{s.mean_num_tool_calls:5.2f}  "
            f"{s.mean_response_words:5.1f}"
        )
    return "\n".join(lines)


def format_per_case_table(results: list[CaseResult]) -> str:
    """For debugging: one line per case with pass/fail."""
    header = f"{'id':<4} {'category':<22} {'pass':<5}  prompt"
    sep = "-" * len(header)
    lines = [header, sep]
    for r in results:
        mark = "✓" if r.expected_tools_called else "✗"
        prompt = r.prompt if len(r.prompt) <= 60 else r.prompt[:57] + "..."
        lines.append(f"{r.case_id:<4} {r.category:<22} {mark:<5}  {prompt}")
    return "\n".join(lines)
