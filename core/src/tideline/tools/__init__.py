from __future__ import annotations

import sqlite3

from tideline.tools.base import Tool, ToolRegistry
from tideline.tools.memory import AddDrawerTool, ListDrawersTool
from tideline.tools.memory import init_db as _init_drawers
from tideline.tools.noop import NoopTool
from tideline.tools.translation import AddTranslationTool, ListTranslationsTool
from tideline.tools.translation import init_db as _init_translations


def init_all_tables(conn: sqlite3.Connection) -> None:
    """Initialize every SQLite table any registered tool may use."""
    _init_drawers(conn)
    _init_translations(conn)


__all__ = [
    "Tool",
    "ToolRegistry",
    "NoopTool",
    "AddDrawerTool",
    "ListDrawersTool",
    "AddTranslationTool",
    "ListTranslationsTool",
    "init_all_tables",
]
