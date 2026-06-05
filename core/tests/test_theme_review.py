"""Theme review: spaced repetition for a remembered scene (keyed on session_id).

Mirrors the card SRS gates, but the unit is a capture session, and the schedule
lives in its own table so cluster rebuilds never touch it. The Leitner ladder is
shared with cards (`card.reschedule`) — these gates lock the theme side of it.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from tideline.tools.card import _REVIEW_INTERVALS_DAYS
from tideline.tools.theme_review import init_db, review_states, review_theme

_NOW = datetime(2026, 6, 4, 12, 0, 0)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    init_db(c)
    yield c
    c.close()


def test_never_reviewed_scene_has_no_row_and_defaults_to_due(conn):
    # An unreviewed scene simply isn't in the table; the endpoint treats absent
    # as due=True / strength=0 (a new scene the tide should bring ashore).
    assert review_states(conn, _NOW) == {}


def test_remembered_climbs_a_box_and_pushes_due_out(conn):
    strength = review_theme(conn, "tokyo-izakaya", remembered=True, now=_NOW)
    assert strength == 1
    states = review_states(conn, _NOW)
    # strength 1 → interval 1 day → not due now.
    assert states["tokyo-izakaya"] == {"strength": 1, "due": False}
    later = _NOW + timedelta(days=_REVIEW_INTERVALS_DAYS[1], seconds=1)
    assert review_states(conn, later)["tokyo-izakaya"]["due"] is True


def test_forgotten_floors_at_zero_and_stays_due(conn):
    # A brand-new scene forgotten: strength floors at 0, interval 0 → still due.
    strength = review_theme(conn, "paris-bistro", remembered=False, now=_NOW)
    assert strength == 0
    assert review_states(conn, _NOW)["paris-bistro"]["due"] is True


def test_climb_is_capped_at_the_top_box(conn):
    sid = "tokyo-sushi"
    for _ in range(len(_REVIEW_INTERVALS_DAYS) + 3):
        s = review_theme(conn, sid, remembered=True, now=_NOW)
    assert s == len(_REVIEW_INTERVALS_DAYS) - 1


def test_reviews_count_increments_on_each_grade(conn):
    sid = "paris-market"
    review_theme(conn, sid, remembered=True, now=_NOW)
    review_theme(conn, sid, remembered=False, now=_NOW)
    row = conn.execute(
        "SELECT reviews, last_reviewed_at FROM theme_reviews WHERE session_id = ?",
        (sid,),
    ).fetchone()
    assert row[0] == 2
    assert row[1] is not None


def test_remembered_then_forgotten_drops_back(conn):
    sid = "tokyo-ramen-yokocho"
    review_theme(conn, sid, remembered=True, now=_NOW)   # → 1
    review_theme(conn, sid, remembered=True, now=_NOW)   # → 2
    s = review_theme(conn, sid, remembered=False, now=_NOW)  # → 1
    assert s == 1
