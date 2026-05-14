"""Run the Tideline web playground via uvicorn.

  $ python -m tideline.web --runtime llama_cpp --db /path/to/db.sqlite
  $ python -m tideline.web                  # defaults: mock runtime + .tideline/drawers.db
"""

from __future__ import annotations

import argparse
import sys

import uvicorn

from tideline.web.app import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tideline.web",
        description="Tideline web playground",
    )
    parser.add_argument("--runtime", default="mock", help="Model backend")
    parser.add_argument("--db", default=None, help="SQLite path")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    app = create_app(runtime_name=args.runtime, db_path=args.db)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
