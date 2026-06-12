"""drawer → candidate → card: the user-nod promotion (closed-loop A, step 1).

Covers card creation from a candidate, idempotency of the nod, episodic
evidence reachability through candidate_evidence, and the missing-candidate
guard.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from tideline.promotion import (
    auto_promote_cards,
    promote_candidates,
    promote_to_card,
    sink_card,
)
from tideline.tools import init_all_tables
from tideline.tools.card import _REVIEW_INTERVALS_DAYS, due_cards, review_card

_NOW = datetime(2026, 6, 3, 12, 0, 0)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_all_tables(conn)
    return conn


def _add(conn: sqlite3.Connection, original: str, translated: str, target: str = "Japanese") -> None:
    conn.execute(
        "INSERT INTO translations (original, target_lang, translated, source) "
        "VALUES (?, ?, ?, 'text')",
        (original, target, translated),
    )
    conn.commit()


def _candidate_id(conn: sqlite3.Connection, original: str) -> int:
    return conn.execute(
        "SELECT id FROM candidates WHERE original = ?", (original,)
    ).fetchone()[0]


def test_promote_to_card_creates_card_from_candidate() -> None:
    conn = _conn()
    for _ in range(3):
        _add(conn, "station", "駅")
    promote_candidates(conn, threshold=3)

    card_id = promote_to_card(conn, _candidate_id(conn, "station"))

    assert card_id is not None
    row = conn.execute(
        "SELECT candidate_id, original, target_lang, translated FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()
    assert row == (_candidate_id(conn, "station"), "station", "Japanese", "駅")


def test_promote_to_card_is_idempotent() -> None:
    conn = _conn()
    for _ in range(3):
        _add(conn, "water", "水")
    promote_candidates(conn, threshold=3)
    cand_id = _candidate_id(conn, "water")

    first = promote_to_card(conn, cand_id)
    second = promote_to_card(conn, cand_id)

    assert first == second
    assert conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1


def test_card_evidence_reachable_through_candidate() -> None:
    # Episodic anchoring: a card's lived moments are reachable (and keep
    # growing) via candidate_evidence → translations.
    conn = _conn()
    for _ in range(3):
        _add(conn, "coffee", "コーヒー")
    promote_candidates(conn, threshold=3)
    card_id = promote_to_card(conn, _candidate_id(conn, "coffee"))

    moments = conn.execute(
        """
        SELECT t.id FROM cards c
        JOIN candidate_evidence ce ON ce.candidate_id = c.candidate_id
        JOIN translations t ON t.id = ce.translation_id
        WHERE c.id = ?
        """,
        (card_id,),
    ).fetchall()
    assert len(moments) == 3


def test_promote_to_card_unknown_candidate_returns_none() -> None:
    conn = _conn()
    assert promote_to_card(conn, 999) is None


# --- opt-out: auto-generation + sink (closed-loop A, step 1 revision) -----


def test_auto_promote_cards_creates_active_card_per_candidate() -> None:
    # Opt-out: no nod needed — every candidate becomes an active card.
    conn = _conn()
    for _ in range(3):
        _add(conn, "station", "駅")
    for _ in range(3):
        _add(conn, "water", "水")
    promote_candidates(conn, threshold=3)

    n = auto_promote_cards(conn)

    assert n == 2
    rows = conn.execute(
        "SELECT original, state FROM cards ORDER BY original"
    ).fetchall()
    assert rows == [("station", "active"), ("water", "active")]


def test_auto_promote_cards_is_idempotent() -> None:
    conn = _conn()
    for _ in range(3):
        _add(conn, "coffee", "コーヒー")
    promote_candidates(conn, threshold=3)

    first = auto_promote_cards(conn)
    second = auto_promote_cards(conn)

    assert first == 1
    assert second == 0  # the second sweep adds nothing
    assert conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1


def test_card_meaning_follows_the_candidate_after_a_better_rendering() -> None:
    # A card is the candidate's projection, not a creation-time snapshot:
    # when a later capture improves the rendering (the candidate keeps the
    # latest — the word-fix path repairs half-translations this way), the
    # card's meaning follows. Its STATE stays the user's.
    conn = _conn()
    for _ in range(3):
        _add(conn, "premium", "高 premium")
    promote_candidates(conn, threshold=3)
    auto_promote_cards(conn)

    _add(conn, "premium", "高级")          # the fixed rendering arrives
    promote_candidates(conn, threshold=3)  # the candidate refreshes to the latest
    auto_promote_cards(conn)               # ...and the card follows

    row = conn.execute("SELECT translated, state FROM cards").fetchone()
    assert row == ("高级", "active")


def test_sink_card_sets_state_sunk() -> None:
    conn = _conn()
    for _ in range(3):
        _add(conn, "train", "電車")
    promote_candidates(conn, threshold=3)
    auto_promote_cards(conn)
    card_id = conn.execute("SELECT id FROM cards WHERE original='train'").fetchone()[0]

    assert sink_card(conn, card_id) is True
    state = conn.execute("SELECT state FROM cards WHERE id=?", (card_id,)).fetchone()[0]
    assert state == "sunk"


def test_sink_card_unknown_returns_false() -> None:
    conn = _conn()
    assert sink_card(conn, 999) is False


def test_sunk_card_not_resurrected_by_later_sweep() -> None:
    # The opt-out promise: once sunk, no later night-watch sweep (even with new
    # encounters of the same term) flips a card back into the deck.
    conn = _conn()
    for _ in range(3):
        _add(conn, "money", "お金")
    promote_candidates(conn, threshold=3)
    auto_promote_cards(conn)
    card_id = conn.execute("SELECT id FROM cards WHERE original='money'").fetchone()[0]
    sink_card(conn, card_id)

    for _ in range(2):
        _add(conn, "money", "お金")
    promote_candidates(conn, threshold=3)
    n = auto_promote_cards(conn)

    assert n == 0
    state = conn.execute("SELECT state FROM cards WHERE id=?", (card_id,)).fetchone()[0]
    assert state == "sunk"


# --- review schedule (spaced repetition, DESIGN §10.3) --------------------


def _one_card(conn: sqlite3.Connection, original: str = "station", translated: str = "駅") -> int:
    for _ in range(3):
        _add(conn, original, translated)
    promote_candidates(conn, threshold=3)
    auto_promote_cards(conn)
    return conn.execute(
        "SELECT id FROM cards WHERE original = ?", (original,)
    ).fetchone()[0]


def test_new_card_is_due_immediately() -> None:
    # A freshly auto-promoted card has NULL due_at = new + ready to surface.
    conn = _conn()
    cid = _one_card(conn)
    due = due_cards(conn, _NOW)
    assert [c["id"] for c in due] == [cid]
    assert due[0]["strength"] == 0


def test_remembered_grows_the_interval() -> None:
    conn = _conn()
    cid = _one_card(conn)

    assert review_card(conn, cid, remembered=True, now=_NOW) == 1
    # No longer due right after a remembered review — it's been pushed out.
    assert due_cards(conn, _NOW) == []
    # Due again once its interval elapses.
    later = _NOW + timedelta(days=_REVIEW_INTERVALS_DAYS[1])
    assert [c["id"] for c in due_cards(conn, later)] == [cid]
    # A second success climbs another box (interval grows further).
    assert review_card(conn, cid, remembered=True, now=later) == 2


def test_forgot_drops_a_box() -> None:
    conn = _conn()
    cid = _one_card(conn)
    review_card(conn, cid, remembered=True, now=_NOW)   # → 1
    review_card(conn, cid, remembered=True, now=_NOW)   # → 2
    assert review_card(conn, cid, remembered=False, now=_NOW) == 1   # drops a box


def test_strength_caps_and_floors() -> None:
    conn = _conn()
    cid = _one_card(conn)
    max_box = len(_REVIEW_INTERVALS_DAYS) - 1
    for _ in range(max_box + 3):
        review_card(conn, cid, remembered=True, now=_NOW)
    assert conn.execute(
        "SELECT strength FROM cards WHERE id=?", (cid,)
    ).fetchone()[0] == max_box
    # A new card forgotten can't go below box 0.
    other = _one_card(conn, "water", "水")
    assert review_card(conn, other, remembered=False, now=_NOW) == 0


def test_due_cards_hides_not_yet_due() -> None:
    conn = _conn()
    a = _one_card(conn, "station", "駅")
    b = _one_card(conn, "water", "水")
    review_card(conn, a, remembered=True, now=_NOW)   # a pushed out; b still new
    assert [c["id"] for c in due_cards(conn, _NOW)] == [b]


def test_due_cards_respects_limit() -> None:
    conn = _conn()
    _one_card(conn, "station", "駅")
    _one_card(conn, "water", "水")
    _one_card(conn, "coffee", "コーヒー")
    assert len(due_cards(conn, _NOW)) == 3
    assert len(due_cards(conn, _NOW, limit=2)) == 2


def test_sunk_card_is_not_due() -> None:
    conn = _conn()
    cid = _one_card(conn)
    sink_card(conn, cid)
    assert due_cards(conn, _NOW) == []


def test_review_unknown_card_returns_none() -> None:
    conn = _conn()
    assert review_card(conn, 999, remembered=True, now=_NOW) is None


def test_migration_backfills_review_columns_on_legacy_cards() -> None:
    # A pre-review-loop cards table (state but no review columns) gains them on
    # init_db; old rows default to new + ready (strength 0, NULL due_at).
    from tideline.tools import card as card_mod

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE cards (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "candidate_id INTEGER, original TEXT, target_lang TEXT, translated TEXT, "
        "state TEXT NOT NULL DEFAULT 'active', "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "INSERT INTO cards (candidate_id, original, target_lang, translated) "
        "VALUES (1, 'station', 'Japanese', '駅')"
    )
    conn.commit()
    assert "strength" not in {r[1] for r in conn.execute("PRAGMA table_info(cards)")}

    card_mod.init_db(conn)

    cols = {r[1] for r in conn.execute("PRAGMA table_info(cards)")}
    assert {"strength", "due_at", "last_reviewed_at", "reviews"} <= cols
    assert conn.execute(
        "SELECT strength, due_at, reviews FROM cards"
    ).fetchone() == (0, None, 0)
    assert len(due_cards(conn, _NOW)) == 1   # legacy card surfaces as new
