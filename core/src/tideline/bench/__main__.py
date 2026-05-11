"""CLI entry for Tideline bench suites.

Two orthogonal benches share this entry point:

  python -m tideline.bench                          # translate (default)
  python -m tideline.bench --suite translate
  python -m tideline.bench --suite agent
  python -m tideline.bench --suite all

Translate bench scores output text quality (BLEU/chrF/EM) against
reference translations. Agent bench scores agent-loop behavior (correct
tool selection, parseable calls, turn efficiency).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tideline.bench.agent.metrics import format_per_case_table, format_summary_table, summarize
from tideline.bench.agent.runner import run as run_agent
from tideline.bench.runner import default_data_dir, format_table, run as run_translate


def _run_translate(runtime: str, tier: str, data_dir: Path) -> None:
    tiers = ("phrases", "sentences") if tier == "both" else (tier,)
    results = []
    for t in tiers:
        results.extend(run_translate(runtime, data_dir, t))
    print(format_table(results))


def _run_agent(runtime: str, per_case: bool) -> None:
    results = run_agent(runtime)
    print(format_summary_table(summarize(results)))
    if per_case:
        print()
        print(format_per_case_table(results))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tideline.bench",
        description="Translation accuracy and agent capability benches.",
    )
    parser.add_argument("--runtime", default="mock", help="Model backend (default: mock)")
    parser.add_argument(
        "--suite",
        choices=("translate", "agent", "all"),
        default="translate",
        help="Which bench to run (default: translate)",
    )
    parser.add_argument(
        "--tier",
        choices=("phrases", "sentences", "both"),
        default="both",
        help="Translate-bench tier (default: both)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=default_data_dir(),
        help="Override the bundled translate-bench data directory",
    )
    parser.add_argument(
        "--per-case",
        action="store_true",
        help="Agent bench: also print pass/fail for each individual case",
    )
    args = parser.parse_args(argv)

    if args.suite in ("translate", "all"):
        _run_translate(args.runtime, args.tier, args.data_dir)
        if args.suite == "all":
            print()

    if args.suite in ("agent", "all"):
        _run_agent(args.runtime, args.per_case)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
