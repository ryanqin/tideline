"""CLI entry for Tideline bench suites.

Three orthogonal benches share this entry point:

  python -m tideline.bench                          # translate (default)
  python -m tideline.bench --suite translate
  python -m tideline.bench --suite agent
  python -m tideline.bench --suite atoms            # per-operation reliability
  python -m tideline.bench --suite all

Translate bench scores output text quality (BLEU / chrF / EM). Agent
bench scores end-to-end agent-loop behavior with tool dispatch. Atoms
bench scores **each LLM operation's reliability in isolation** —
priority map for Tier B feature development.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tideline.bench.agent.metrics import (
    format_per_case_table as agent_per_case,
    format_summary_table as agent_summary_table,
    summarize as agent_summarize,
)
from tideline.bench.agent.runner import run as run_agent
from tideline.bench.atoms.metrics import (
    format_failure_samples as atom_failure_samples,
    format_summary_table as atom_summary_table,
    summarize as atom_summarize,
)
from tideline.bench.atoms.runner import run as run_atoms
from tideline.bench.runner import default_data_dir, format_table, run as run_translate


def _run_translate(runtime: str, tier: str, data_dir: Path) -> None:
    tiers = ("phrases", "sentences") if tier == "both" else (tier,)
    results = []
    for t in tiers:
        results.extend(run_translate(runtime, data_dir, t))
    print(format_table(results))


def _run_agent(runtime: str, per_case: bool) -> None:
    results = run_agent(runtime)
    print(agent_summary_table(agent_summarize(results)))
    if per_case:
        print()
        print(agent_per_case(results))


def _run_atoms(runtime: str, per_case: bool) -> None:
    results = run_atoms(runtime)
    print(atom_summary_table(atom_summarize(results)))
    if per_case:
        print()
        print(atom_failure_samples(results))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tideline.bench",
        description="Translation, agent, and atomic capability benches.",
    )
    parser.add_argument("--runtime", default="mock", help="Model backend (default: mock)")
    parser.add_argument(
        "--suite",
        choices=("translate", "agent", "atoms", "all"),
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
        help="Agent / atom benches: also print per-case detail",
    )
    args = parser.parse_args(argv)

    if args.suite in ("translate", "all"):
        _run_translate(args.runtime, args.tier, args.data_dir)
        if args.suite == "all":
            print()

    if args.suite in ("agent", "all"):
        _run_agent(args.runtime, args.per_case)
        if args.suite == "all":
            print()

    if args.suite in ("atoms", "all"):
        _run_atoms(args.runtime, args.per_case)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
