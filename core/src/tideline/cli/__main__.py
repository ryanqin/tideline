import argparse
import sqlite3
import sys
from pathlib import Path

from tideline.agent import Agent
from tideline.cluster import cluster_sweep
from tideline.cluster import init_db as init_cluster_db
from tideline.promotion import auto_promote_cards, promote_candidates
from tideline.runtimes import get_runtime
from tideline.tagging import tag_native_glosses, tag_source_langs
from tideline.tools.settings import DEFAULT_NATIVE_LANG, get_setting
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
    init_cluster_db(conn)

    # Night-watch sweep: silently promote any drawer entries that crossed the
    # repetition threshold during prior sessions. Idempotent, cheap, no output.
    promote_candidates(conn)

    # Opt-out card generation: every candidate gets a review card the user can
    # later sink. Idempotent, deterministic — never resurrects a sunk card.
    auto_promote_cards(conn)

    # Tier B sweep: budgeted background voting + cluster rebuild + naming.
    # Two relations over the same tables — concept (synonym aggregation,
    # feeds the by-language lens) and theme (B7 relatedness, feeds album-
    # style recall). Each is wrapped fail-soft AND independently, because it
    # calls the LLM: a glitch on one relation must never break the other or
    # the user's primary translation flow. Both are "expensive" sweeps and
    # belong here at startup, never in the per-translation hot path.
    try:
        cluster_sweep(conn, runtime)
    except Exception:
        pass
    try:
        cluster_sweep(conn, runtime, vote_type="theme")
    except Exception:
        pass

    # Tag sweep: backfill source_lang on untagged rows. Deterministic for
    # non-Latin scripts (free); model fallback for Latin. Fail-soft.
    try:
        tag_source_langs(conn, runtime)
    except Exception:
        pass

    # Native-gloss sweep: render each term in the user's first language. Pure
    # generation, so it always uses the model; on mock it no-ops. Fail-soft.
    try:
        tag_native_glosses(conn, runtime, get_setting(conn, "native_lang", DEFAULT_NATIVE_LANG))
    except Exception:
        pass

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
