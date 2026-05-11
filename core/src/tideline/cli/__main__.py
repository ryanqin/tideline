import argparse
import sqlite3
import sys
from pathlib import Path

from tideline.agent import Agent
from tideline.promotion import promote_candidates
from tideline.runtimes import get_runtime
from tideline.tools import (
    AddDrawerTool,
    AddTranslationTool,
    ListCandidatesTool,
    ListDrawersTool,
    ListTranslationsTool,
    NoopTool,
    ToolRegistry,
    init_all_tables,
)


_DEFAULT_DB = Path(".tideline") / "drawers.db"

_TIDELINE_SYSTEM = (
    "You are Tideline, a local-first translation assistant. "
    "When the user explicitly asks to translate text, perform the translation "
    "yourself, then call the add_translation tool to record "
    "(original, target_lang, translated) before responding to the user with "
    "the translated text. For other requests, use the available tools as "
    "appropriate. Be concise."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tideline",
        description="Tideline CLI — local-first translation agent",
    )
    parser.add_argument("--runtime", default="mock", help="Model backend (default: mock)")
    parser.add_argument(
        "--db",
        default=str(_DEFAULT_DB),
        help="SQLite path for drawer / translation store "
        "(':memory:' for ephemeral; default: ./.tideline/drawers.db)",
    )
    parser.add_argument("prompt", help="The text to send to the agent")
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

    # Night-watch sweep: silently promote any drawer entries that crossed the
    # repetition threshold during prior sessions. Idempotent, cheap, no output.
    promote_candidates(conn)

    registry = ToolRegistry()
    registry.register(NoopTool)
    registry.register(AddDrawerTool)
    registry.register(ListDrawersTool)
    registry.register(AddTranslationTool)
    registry.register(ListTranslationsTool)
    registry.register(ListCandidatesTool)

    agent = Agent(
        runtime,
        registry=registry,
        context={"db": conn},
        system_message=_TIDELINE_SYSTEM,
    )
    print(agent.run(args.prompt))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
