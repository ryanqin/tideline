"""CLI entry for the translation accuracy bench.

Examples:
  python -m tideline.bench --runtime mock                       # smoke
  python -m tideline.bench --runtime llama_cpp --tier sentences
  python -m tideline.bench --runtime llama_cpp --tier both      # default
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tideline.bench.runner import default_data_dir, format_table, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tideline.bench",
        description="Translation accuracy benchmark for Tideline.",
    )
    parser.add_argument(
        "--runtime",
        default="mock",
        help="Model backend (default: mock — smoke-tests infrastructure only)",
    )
    parser.add_argument(
        "--tier",
        choices=("phrases", "sentences", "both"),
        default="both",
        help="Which tier to evaluate (default: both)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=default_data_dir(),
        help="Override the bundled data directory",
    )
    args = parser.parse_args(argv)

    tiers = ("phrases", "sentences") if args.tier == "both" else (args.tier,)
    all_results = []
    for tier in tiers:
        all_results.extend(run(args.runtime, args.data_dir, tier))

    print(format_table(all_results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
