"""Seed data generator for the translations drawer.

Populates SQLite with realistic translation pairs whose repetition pattern
is the substrate emergence detection (Step 6b) will scan. Frequent terms
appear 4-6 times, occasional 2-3 times, rare 1 time — this gives
candidate promotion something real to find.

Scenarios are everyday contexts: Tokyo trip menu hunting, French recipes,
Latin music lyrics, Beijing business meetings, German tech docs. Each
contributes ~25 entries; ~120 total by default.

Usage:
  Programmatic:
    from tideline.seed import seed_db
    seed_db(conn)

  CLI:
    python -m tideline.seed --db /tmp/demo.db
    python -m tideline.seed --db /tmp/demo.db --clear  # drop existing first
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import sys
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "Tokyo trip — menu hunting",
        "target_lang": "English",
        "frequent": [
            ("ラーメン", "ramen"),
            ("寿司", "sushi"),
            ("天ぷら", "tempura"),
        ],
        "occasional": [
            ("駅", "station"),
            ("地下鉄", "subway"),
        ],
        "rare": [
            ("お会計", "the bill, please"),
            ("いらっしゃいませ", "welcome (greeting)"),
            ("ご注文は", "what would you like to order"),
            ("つけ麺", "tsukemen (dipping noodles)"),
            ("醤油", "soy sauce"),
        ],
    },
    {
        "name": "French cooking — recipe reading",
        "target_lang": "English",
        "frequent": [
            ("beurre", "butter"),
            ("œuf", "egg"),
            ("farine", "flour"),
        ],
        "occasional": [
            ("crème", "cream"),
            ("cuillère", "spoon"),
        ],
        "rare": [
            ("jaune d'œuf", "egg yolk"),
            ("blanc en neige", "stiff egg whites"),
            ("rouleau à pâtisserie", "rolling pin"),
            ("four", "oven"),
            ("préchauffer", "preheat"),
        ],
    },
    {
        "name": "Latin music — lyric translation",
        "target_lang": "English",
        "frequent": [
            ("amor", "love"),
            ("corazón", "heart"),
            ("noche", "night"),
        ],
        "occasional": [
            ("dolor", "pain"),
            ("bailar", "to dance"),
        ],
        "rare": [
            ("madrugada", "dawn"),
            ("recordar", "to remember"),
            ("sin ti", "without you"),
            ("siempre", "always"),
            ("nunca", "never"),
        ],
    },
    {
        "name": "Beijing meetings — business Mandarin",
        "target_lang": "English",
        "frequent": [
            ("合同", "contract"),
            ("会议", "meeting"),
            ("项目", "project"),
        ],
        "occasional": [
            ("提案", "proposal"),
            ("预算", "budget"),
        ],
        "rare": [
            ("准时", "on time / punctual"),
            ("汇报", "report"),
            ("决策", "decision"),
            ("合作", "cooperation"),
            ("签字", "to sign"),
        ],
    },
    {
        "name": "German tech docs — software reading",
        "target_lang": "English",
        "frequent": [
            ("Datenbank", "database"),
            ("Speicher", "memory / storage"),
        ],
        "occasional": [
            ("Server", "server"),
            ("Anwendung", "application"),
        ],
        "rare": [
            ("Fehlermeldung", "error message"),
            ("Schnittstelle", "interface"),
            ("Schlüssel", "key"),
            ("Versionskontrolle", "version control"),
            ("Verbindung", "connection"),
        ],
    },
    # Phase B4 substrate: cross-original same-concept drawers. Models a
    # polyglot user encountering the same concept across different
    # source languages / phrasings over time. Same target_lang (English)
    # means _pending_pairs will pair them; B1 should call them concept-
    # equivalent across these originals, producing the first real
    # cross-original Tier B clusters.
    {
        "name": "Polyglot crossings — same concept, different originals",
        "target_lang": "English",
        "frequent": [
            # noodle concept across Chinese / English descriptive
            ("拉面", "ramen", "Chinese"),
            ("noodle soup", "noodle soup", "English"),
            # subway concept across Chinese / English
            ("地铁", "subway", "Chinese"),
            ("metro", "metro", "English"),
        ],
        "occasional": [
            # love concept across French / Chinese
            ("l'amour", "love", "French"),
            ("爱", "love", "Chinese"),
        ],
        "rare": [
            ("evening train", "evening train", "English"),
        ],
    },
]


_FREQUENT_REPEAT = (4, 6)
_OCCASIONAL_REPEAT = (2, 3)
_RARE_REPEAT = (1, 1)


# Source language per scenario (the language the user encountered / typed).
# Most scenarios are single-language; pairs in the polyglot scenario carry
# their own source language via a 3-tuple override.
_SCENARIO_SOURCE_LANG = {
    "Tokyo trip — menu hunting": "Japanese",
    "French cooking — recipe reading": "French",
    "Latin music — lyric translation": "Spanish",
    "Beijing meetings — business Mandarin": "Chinese",
    "German tech docs — software reading": "German",
    "Polyglot crossings — same concept, different originals": "English",
}


def generate_entries(
    seed: int = 42,
    now: datetime | None = None,
) -> list[tuple[str, str, str, str, str]]:
    """Generate (original, target_lang, translated, source_lang, created_at_iso) tuples.

    Timestamps spread over the past 7 days from `now`. Fully deterministic
    given (seed, now) — pass an explicit `now` in tests for reproducibility.
    Output order is shuffled to mimic real chronological mixing.
    """
    rng = random.Random(seed)
    out: list[tuple[str, str, str, str, str]] = []
    if now is None:
        now = datetime.now()

    for scenario in SCENARIOS:
        target_lang = scenario["target_lang"]
        default_src = _SCENARIO_SOURCE_LANG[scenario["name"]]
        buckets: list[tuple[Iterable[tuple], tuple[int, int]]] = [
            (scenario["frequent"], _FREQUENT_REPEAT),
            (scenario["occasional"], _OCCASIONAL_REPEAT),
            (scenario["rare"], _RARE_REPEAT),
        ]
        for pairs, repeat_range in buckets:
            for pair in pairs:
                original, translated = pair[0], pair[1]
                source_lang = pair[2] if len(pair) > 2 else default_src
                count = rng.randint(*repeat_range)
                for _ in range(count):
                    days_ago = rng.uniform(0, 7)
                    ts = (now - timedelta(days=days_ago)).isoformat()
                    out.append((original, target_lang, translated, source_lang, ts))

    rng.shuffle(out)
    return out


def seed_db(conn: sqlite3.Connection, seed: int = 42) -> int:
    """Insert seed translations. Returns the count inserted."""
    entries = generate_entries(seed=seed)
    conn.executemany(
        "INSERT INTO translations "
        "(original, target_lang, translated, source_lang, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        entries,
    )
    conn.commit()
    return len(entries)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tideline.seed",
        description="Populate the translations DB with realistic seed data.",
    )
    parser.add_argument(
        "--db",
        required=True,
        help="SQLite path (use ':memory:' for ephemeral).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible output (default: 42).",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete existing translations before seeding.",
    )
    args = parser.parse_args(argv)

    if args.db != ":memory:":
        Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)

    from tideline.tools import init_all_tables

    init_all_tables(conn)

    if args.clear:
        conn.execute("DELETE FROM translations")
        conn.commit()

    count = seed_db(conn, seed=args.seed)
    conn.close()

    print(f"Seeded {count} translation entries into {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
