"""Seed data generator for the translations drawer.

Populates SQLite with realistic translation pairs whose repetition pattern
is the substrate emergence detection (Step 6b) will scan. Frequent terms
appear 4-6 times, occasional 2-3 times, rare 1 time — this gives
candidate promotion something real to find.

Scenarios are everyday contexts: Tokyo trip menu hunting, French recipes,
Latin music lyrics, Beijing business meetings, German tech docs. Each
contributes ~25 entries; ~120 total by default.

**Episodic honesty (2026-05-28):** the demo's "scene feel" must only use
signals the real capture pipeline can actually produce — never narrated
prose the product can't generate. Mirrors what the on-device Android
pipeline was verified to emit (TidelineTranslateViewModel.translateImage):
each scenario is split into *capture sessions* (a menu photo, a sign, a
voice memo). Every row carries:

  - `source`     — the input modality (image / audio / text), exactly what
                   the client injects by default (image pipeline → "image").
  - `context_snippet` — the VLM's short *scene gist* for an image capture
                   (e.g. "A wooden tray with a bowl of noodles and a cup of
                   broth") — a real model-produced description of where/what
                   the moment was, which is why storing it is honest. ONLY
                   image captures carry it; text/audio rows leave it None,
                   because their prompts ask for no SCENE line (matches the
                   live app exactly). The episodic title (B6,
                   `episodic_title.build_prompt`) turns these gists into the
                   "your Tokyo ramen night" feeling at naming time.
  - `session_id` — groups everything captured in one moment, so a single
                   menu photo's items cluster as one remembered event.

A term repeats because it shows up across *several* sessions (seen on the
menu, then a sign, then heard at the counter) — the honest shape of a word
you keep running into.

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


# Each scenario carries its word pairs (in three frequency tiers) plus a
# list of `sessions`: the discrete capture moments of the trip/activity.
# A session's `gist` is the short scene description a VLM would emit for an
# image capture (the recorded context_snippet) — or None for text/audio
# captures, whose prompts produce no SCENE line in the real app. `day` is
# days-ago from `now`, giving each session its own timestamp cluster.
SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "Tokyo trip — menu hunting",
        "slug": "tokyo-menu",
        "target_lang": "English",
        "sessions": [
            {"suffix": "ramen-yokocho", "source": "image", "day": 6,
             "gist": "A glowing ticket machine outside a narrow late-night ramen shop"},
            {"suffix": "izakaya-menu", "source": "image", "day": 5,
             "gist": "An open paper menu on a low wooden izakaya table"},
            {"suffix": "station-signs", "source": "image", "day": 4,
             "gist": "Blue exit signs above the gates of a busy train station"},
            {"suffix": "counter-audio", "source": "audio", "day": 5,
             "gist": None},
            {"suffix": "sushi-counter", "source": "image", "day": 3,
             "gist": "Small plates circling a conveyor-belt sushi counter"},
        ],
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
        # Which capture sessions each term could honestly appear in — its
        # OCR/transcript context must fit the term (a station word belongs
        # on a station sign, not a ramen menu). Copies round-robin only
        # within this whitelist.
        "term_sessions": {
            "ラーメン": ["ramen-yokocho", "counter-audio"],
            "寿司": ["sushi-counter", "izakaya-menu"],
            "天ぷら": ["izakaya-menu", "sushi-counter"],
            "駅": ["station-signs"],
            "地下鉄": ["station-signs"],
            "お会計": ["counter-audio"],
            "いらっしゃいませ": ["counter-audio"],
            "ご注文は": ["counter-audio"],
            "つけ麺": ["ramen-yokocho"],
            "醤油": ["ramen-yokocho", "sushi-counter"],
        },
    },
    {
        "name": "French cooking — recipe reading",
        "slug": "french-recipe",
        "target_lang": "English",
        "sessions": [
            {"suffix": "madeleine-blog", "source": "image", "day": 6,
             "gist": "A recipe open on a phone propped against a mixing bowl"},
            {"suffix": "grandmere-livre", "source": "image", "day": 5,
             "gist": "A flour-dusted page of an old handwritten cookbook"},
            {"suffix": "youtube-gateau", "source": "audio", "day": 4,
             "gist": None},
            {"suffix": "frigo-pot", "source": "image", "day": 3,
             "gist": "A tub of crème fraîche held in front of an open fridge"},
            {"suffix": "tarte-ipad", "source": "image", "day": 2,
             "gist": "A baking recipe on a tablet beside a lemon tart"},
        ],
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
        "term_sessions": {
            "beurre": ["madeleine-blog", "grandmere-livre"],
            "œuf": ["grandmere-livre", "tarte-ipad"],
            "farine": ["madeleine-blog", "youtube-gateau"],
            "crème": ["frigo-pot"],
            "cuillère": ["youtube-gateau", "grandmere-livre"],
            "jaune d'œuf": ["tarte-ipad"],
            "blanc en neige": ["tarte-ipad"],
            "rouleau à pâtisserie": ["madeleine-blog"],
            "four": ["youtube-gateau"],
            "préchauffer": ["madeleine-blog"],
        },
    },
    {
        "name": "Latin music — lyric translation",
        "slug": "latin-lyrics",
        "target_lang": "English",
        "sessions": [
            {"suffix": "spotify-lyrics", "source": "text", "day": 6,
             "gist": None},
            {"suffix": "fiesta-coro", "source": "audio", "day": 5,
             "gist": None},
            {"suffix": "bolero-radio", "source": "audio", "day": 4,
             "gist": None},
            {"suffix": "album-cover", "source": "image", "day": 3,
             "gist": "A Spanish album cover with the song title in flowing script"},
        ],
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
        "term_sessions": {
            "amor": ["spotify-lyrics", "bolero-radio"],
            "corazón": ["spotify-lyrics", "fiesta-coro"],
            "noche": ["bolero-radio", "fiesta-coro"],
            "dolor": ["bolero-radio"],
            "bailar": ["fiesta-coro"],
            "madrugada": ["bolero-radio"],
            "recordar": ["spotify-lyrics"],
            "sin ti": ["spotify-lyrics"],
            "siempre": ["album-cover"],
            "nunca": ["bolero-radio"],
        },
    },
    {
        "name": "Beijing meetings — business Mandarin",
        "slug": "beijing-meetings",
        "target_lang": "English",
        "sessions": [
            {"suffix": "contract-doc", "source": "image", "day": 6,
             "gist": "A printed contract open to the signature page"},
            {"suffix": "meeting-notes", "source": "text", "day": 5,
             "gist": None},
            {"suffix": "whiteboard", "source": "image", "day": 4,
             "gist": "A whiteboard covered with a project schedule and budget figures"},
            {"suffix": "voice-memo", "source": "audio", "day": 3,
             "gist": None},
        ],
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
        "term_sessions": {
            "合同": ["contract-doc", "meeting-notes"],
            "会议": ["meeting-notes", "voice-memo"],
            "项目": ["whiteboard", "meeting-notes"],
            "提案": ["whiteboard"],
            "预算": ["whiteboard"],
            "准时": ["voice-memo"],
            "汇报": ["voice-memo"],
            "决策": ["meeting-notes"],
            "合作": ["voice-memo"],
            "签字": ["contract-doc"],
        },
    },
    {
        "name": "German tech docs — software reading",
        "slug": "german-docs",
        "target_lang": "English",
        "sessions": [
            {"suffix": "api-docs", "source": "image", "day": 6,
             "gist": "A code documentation page about databases on a laptop screen"},
            {"suffix": "error-screen", "source": "image", "day": 4,
             "gist": "A screenshot of a red server error message and stack trace"},
            {"suffix": "git-readme", "source": "text", "day": 2,
             "gist": None},
        ],
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
        "term_sessions": {
            "Datenbank": ["api-docs"],
            "Speicher": ["api-docs"],
            "Server": ["error-screen"],
            "Anwendung": ["error-screen"],
            "Fehlermeldung": ["error-screen"],
            "Schnittstelle": ["git-readme"],
            "Schlüssel": ["git-readme"],
            "Versionskontrolle": ["git-readme"],
            "Verbindung": ["error-screen"],
        },
    },
    # Phase B4 substrate: cross-original same-concept drawers. Models a
    # polyglot user encountering the same concept across different
    # source languages / phrasings over time. Same target_lang (English)
    # means _pending_pairs will pair them; B1 should call them concept-
    # equivalent across these originals, producing the first real
    # cross-original Tier B clusters.
    {
        "name": "Polyglot crossings — same concept, different originals",
        "slug": "polyglot",
        "target_lang": "English",
        "sessions": [
            {"suffix": "travel-notes", "source": "text", "day": 6,
             "gist": None},
            {"suffix": "transit-signs", "source": "image", "day": 5,
             "gist": "A subway direction sign photographed on a city platform"},
            {"suffix": "song-and-card", "source": "audio", "day": 4,
             "gist": None},
        ],
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
        "term_sessions": {
            "拉面": ["travel-notes"],
            "noodle soup": ["travel-notes"],
            "地铁": ["transit-signs"],
            "metro": ["transit-signs"],
            "l'amour": ["song-and-card"],
            "爱": ["song-and-card"],
            "evening train": ["transit-signs"],
        },
    },
]


_FREQUENT_REPEAT = (4, 6)
_OCCASIONAL_REPEAT = (2, 3)
_RARE_REPEAT = (1, 1)

# Co-captured items in one session cluster within this many minutes of the
# session's day mark — tight enough to read as "one sitting", loose enough
# to look natural on a timeline.
_SESSION_SPREAD_MINUTES = 90


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
) -> list[tuple[str, str, str, str, str, str, str, str]]:
    """Generate seed rows as 8-tuples.

    Each tuple is
    ``(original, target_lang, translated, source_lang, source,
    context_snippet, session_id, created_at_iso)``.

    A term's N copies are distributed round-robin across its scenario's
    capture sessions, so a frequent term naturally lands in several
    sessions (the honest shape of a recurring word) while every copy
    inherits that session's modality, scene gist (image captures only;
    None for text/audio), and timestamp cluster. Fully deterministic given
    (seed, now). Output order is shuffled to mimic real chronological mixing.
    """
    rng = random.Random(seed)
    out: list[tuple[str, str, str, str, str, str, str, str]] = []
    if now is None:
        now = datetime.now()

    for scenario in SCENARIOS:
        target_lang = scenario["target_lang"]
        default_src = _SCENARIO_SOURCE_LANG[scenario["name"]]
        by_suffix = {s["suffix"]: s for s in scenario["sessions"]}
        term_sessions = scenario["term_sessions"]
        slug = scenario["slug"]
        buckets: list[tuple[Iterable[tuple], tuple[int, int]]] = [
            (scenario["frequent"], _FREQUENT_REPEAT),
            (scenario["occasional"], _OCCASIONAL_REPEAT),
            (scenario["rare"], _RARE_REPEAT),
        ]
        for pairs, repeat_range in buckets:
            for pair in pairs:
                original, translated = pair[0], pair[1]
                source_lang = pair[2] if len(pair) > 2 else default_src
                eligible = [by_suffix[suf] for suf in term_sessions[original]]
                count = rng.randint(*repeat_range)
                for i in range(count):
                    # Round-robin across the term's *eligible* sessions:
                    # distinct copies land in distinct capture moments that
                    # fit the term (a station word on a station sign, not a
                    # ramen menu). No RNG draw here — keep the per-copy RNG
                    # budget at exactly one uniform() so the frequency-tier
                    # counts stay identical.
                    session = eligible[i % len(eligible)]
                    minutes = rng.uniform(0, _SESSION_SPREAD_MINUTES)
                    ts = (
                        now
                        - timedelta(days=session["day"])
                        + timedelta(minutes=minutes)
                    ).isoformat()
                    # The VLM scene gist for image captures; None for text/
                    # audio (their prompts emit no SCENE line in the real app).
                    context_snippet = session["gist"]
                    session_id = f"{slug}-{session['suffix']}"
                    out.append(
                        (
                            original,
                            target_lang,
                            translated,
                            source_lang,
                            session["source"],
                            context_snippet,
                            session_id,
                            ts,
                        )
                    )

    rng.shuffle(out)
    return out


def seed_db(conn: sqlite3.Connection, seed: int = 42) -> int:
    """Insert seed translations. Returns the count inserted."""
    entries = generate_entries(seed=seed)
    conn.executemany(
        "INSERT INTO translations "
        "(original, target_lang, translated, source_lang, source, "
        "context_snippet, session_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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
