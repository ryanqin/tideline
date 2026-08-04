"""Occasion boundaries — when one sitting ends and the next begins.

Captures within the inactivity window belong to one session; a longer gap
mints a new id. Promotion counts distinct sessions, so this rule is what makes
"met three times" mean "met on three occasions" rather than "typed three times
in a row". It is a memory-layer rule, and it had been living inside an HTTP
handler — the phone had already pulled it out into a pure decision plus a
persistence shell (data/LiveSession.kt), and this is the same two-part shape,
so both ends can be read side by side.

The id is a STABLE minted handle, not a read-time time-bucket: the theme
review schedule hangs off it and must not shift as new rows arrive.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Callable
from uuid import uuid4

from tideline.tools.settings import get_setting, set_setting


LIVE_SESSION_WINDOW = timedelta(minutes=30)


def mint_session_id() -> str:
    return "live-" + uuid4().hex[:12]


def resolve_live_session(
    current_id: str | None,
    last_at: datetime | None,
    now: datetime,
    mint: Callable[[], str] = mint_session_id,
) -> str:
    """The pure decision: keep the running session, or start a new one.

    Mirrors LiveSession.kt::resolveLiveSession, including its boundary — a gap
    of exactly the window still counts as the same sitting.
    """
    if current_id and last_at is not None and now - last_at <= LIVE_SESSION_WINDOW:
        return current_id
    return mint()


def _parse_last_at(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None  # corrupt timestamp → start a fresh session


def live_session_id(conn: sqlite3.Connection, now: datetime) -> str:
    """The session id for a capture happening now; refreshes the window.

    The id and last-seen time live in settings as local ISO — a format we own,
    unlike translations.created_at, which SQLite stores in UTC with a space
    separator. Without this, every live row landed with a NULL session_id and
    the theme sweep (which groups by session) never saw it, so scenes only ever
    emerged from seed data.
    """
    raw_last_at = get_setting(conn, "live_session_last_at", "")
    sid = resolve_live_session(
        current_id=get_setting(conn, "live_session_id", "") or None,
        last_at=_parse_last_at(raw_last_at) if raw_last_at else None,
        now=now,
    )
    set_setting(conn, "live_session_id", sid)
    set_setting(conn, "live_session_last_at", now.isoformat())
    return sid
