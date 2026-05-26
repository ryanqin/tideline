"""L0 identity / settings kv store.

Covers the default fallback, set→get round-trip, and upsert (one row per key).
The native_lang setting is the only key today; the table is generic so future
settings reuse it.
"""

from __future__ import annotations

import sqlite3

from tideline.tools import init_all_tables
from tideline.tools.settings import DEFAULT_NATIVE_LANG, get_setting, set_setting


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_all_tables(conn)
    return conn


def test_get_setting_returns_default_when_absent() -> None:
    conn = _conn()
    assert get_setting(conn, "native_lang", DEFAULT_NATIVE_LANG) == "Chinese"


def test_set_then_get_setting() -> None:
    conn = _conn()
    set_setting(conn, "native_lang", "Japanese")
    assert get_setting(conn, "native_lang", DEFAULT_NATIVE_LANG) == "Japanese"


def test_set_setting_upserts_single_row() -> None:
    conn = _conn()
    set_setting(conn, "native_lang", "Japanese")
    set_setting(conn, "native_lang", "French")
    assert get_setting(conn, "native_lang", DEFAULT_NATIVE_LANG) == "French"
    n = conn.execute(
        "SELECT COUNT(*) FROM settings WHERE key = 'native_lang'"
    ).fetchone()[0]
    assert n == 1


def test_init_all_tables_creates_settings_table() -> None:
    conn = _conn()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='settings'"
    ).fetchone()
    assert row is not None
