from __future__ import annotations

import sqlite3

from tideline.tools.base import Tool, ToolRegistry
from tideline.tools.candidate import ListCandidatesTool
from tideline.tools.candidate import init_db as _init_candidates
from tideline.tools.card import init_db as _init_cards
from tideline.tools.memory import AddDrawerTool, ListDrawersTool
from tideline.tools.memory import init_db as _init_drawers
from tideline.tools.noop import NoopTool
from tideline.tools.settings import init_db as _init_settings
from tideline.tools.theme_review import init_db as _init_theme_reviews
from tideline.tools.translation import AddTranslationTool, ListTranslationsTool
from tideline.tools.translation import init_db as _init_translations


def init_all_tables(conn: sqlite3.Connection) -> None:
    """Initialize every SQLite table any registered tool may use."""
    _init_drawers(conn)
    _init_translations(conn)
    _init_candidates(conn)
    _init_cards(conn)  # cards FK candidates → must init after candidates
    _init_settings(conn)  # L0 identity (native_lang) + future app settings
    _init_theme_reviews(conn)  # SRS schedule for reviewable scenes (themes)
    # Cluster engine tables (Tier B). Init here so any code path that calls
    # init_all_tables (CLI, bench, tests) gets the full schema; the cluster
    # engine itself also has its own init_db for direct callers.
    #
    # Imported here rather than at module level, deliberately. It is NOT a
    # circular-import guard — hoisting it works, verified. It is that
    # cluster.naming reads tools.settings, so a module-level import would
    # make tools ⇄ cluster a real cycle at import time. Python resolves that
    # one today only because settings.py needs nothing back from this
    # package; a one-line change there would turn a working import into an
    # ImportError far from its cause. The deferral costs one lookup per DB
    # open and keeps the two packages orderable.
    from tideline.cluster import init_db as _init_clusters
    _init_clusters(conn)


__all__ = [
    "Tool",
    "ToolRegistry",
    "NoopTool",
    "AddDrawerTool",
    "ListDrawersTool",
    "AddTranslationTool",
    "ListTranslationsTool",
    "ListCandidatesTool",
    "init_all_tables",
]
