import argparse
import sqlite3
import sys
from pathlib import Path

from tideline.agent import Agent
from tideline.promotion import promote_candidates
from tideline.runtimes import get_runtime
from tideline.tools import AddTranslationTool, ToolRegistry, init_all_tables


_DEFAULT_DB = Path(".tideline") / "drawers.db"

# Tideline is a translation engine, not a chatbot. The system message is
# tight on purpose: one job (translate + record), strict output discipline
# (no preamble, no commentary), no invitation to converse.
_TIDELINE_SYSTEM = (
    "You are Tideline, a local-first translation engine. "
    "When the user provides text to translate: first call the add_translation "
    "tool with (original, target_lang, translated), then respond to the user "
    "with only the translated text — no preamble, no quotation marks, no "
    "commentary."
)


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

    # Night-watch sweep: silently promote any drawer entries that crossed the
    # repetition threshold during prior sessions. Idempotent, cheap, no output.
    promote_candidates(conn)

    registry = ToolRegistry()
    registry.register(AddTranslationTool)

    # source="text" is the CLI's input modality. Future Android/HTTP entry
    # points override this to "image" or "audio" via their own context.
    agent = Agent(
        runtime,
        registry=registry,
        context={"db": conn, "source": "text"},
        system_message=_TIDELINE_SYSTEM,
    )
    print(agent.run(args.prompt))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
