"""drawer → candidate → card: the user-nod promotion (closed-loop A, step 1).

Covers card creation from a candidate, idempotency of the nod, episodic
evidence reachability through candidate_evidence, and the missing-candidate
guard.
"""

from __future__ import annotations

import sqlite3

from tideline.promotion import promote_candidates, promote_to_card
from tideline.tools import init_all_tables


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
