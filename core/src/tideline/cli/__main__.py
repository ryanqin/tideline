import argparse
import sqlite3
import sys
from pathlib import Path

from tideline.agent import Agent
from tideline.boot import startup_sweep
from tideline.cluster import init_db as init_cluster_db
from tideline.prompts import TIDELINE_SYSTEM
from tideline.runtimes import get_runtime
from tideline.tools import AddTranslationTool, ToolRegistry, init_all_tables


_DEFAULT_DB = Path(".tideline") / "drawers.db"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tideline",
        description="Tideline CLI — local-first translation engine",
    )
    parser.add_argument("--runtime", default="mock", help="Model backend (default: mock)")
    parser.add_argument(
        "--db",
        default=str(_DEFAULT_DB),
        help="SQLite path for translation store "
        "(':memory:' for ephemeral; default: ./.tideline/drawers.db)",
    )
    parser.add_argument("prompt", help="The text to translate")
    args = parser.parse_args(argv)

    try:
        runtime = get_runtime(args.runtime)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.db != ":memory:":
        Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
    init_all_tables(conn)
    init_cluster_db(conn)

    # The same startup sweep the web app runs (boot.py). It used to be
    # written out in both places, with a comment promising they matched —
    # and they had already drifted on connection settings.
    startup_sweep(conn, runtime)

    registry = ToolRegistry()
    registry.register(AddTranslationTool)

    # source="text" is the CLI's input modality. Future Android/HTTP entry
    # points override this to "image" or "audio" via their own context.
    agent = Agent(
        runtime,
        registry=registry,
        context={"db": conn, "source": "text"},
        system_message=TIDELINE_SYSTEM,
    )
    print(agent.run(args.prompt))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
