"""Seed data generator for the translations drawer.

Populates SQLite with realistic translation pairs whose repetition pattern
is the substrate emergence detection (Step 6b) will scan. Frequent terms
appear 4-6 times, occasional 2-3 times, rare 1 time — this gives
candidate promotion something real to find.

Scenarios are everyday contexts a first-language-Chinese user runs into:
Tokyo trip menu hunting, French recipes, Latin music lyrics, work English
(contracts & meetings), German tech docs — each foreign text translated
INTO Chinese. Each contributes ~25 entries; ~120 total by default.

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
        "target_lang": "Chinese",
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
            ("ラーメン", "拉面"),
            ("刺身", "生鱼片"),
            ("天ぷら", "天妇罗"),
        ],
        "occasional": [
            ("駅", "车站"),
            ("地下鉄", "地铁"),
        ],
        "rare": [
            ("お会計", "买单"),
            ("いらっしゃいませ", "欢迎光临"),
            ("ご注文は", "您要点什么"),
            ("つけ麺", "蘸面"),
            ("醤油", "酱油"),
        ],
        # Which capture sessions each term could honestly appear in — its
        # OCR/transcript context must fit the term (a station word belongs
        # on a station sign, not a ramen menu). Copies round-robin only
        # within this whitelist.
        "term_sessions": {
            "ラーメン": ["ramen-yokocho", "counter-audio"],
            "刺身": ["sushi-counter", "izakaya-menu"],
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
        "target_lang": "Chinese",
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
            ("beurre", "黄油"),
            ("œuf", "鸡蛋"),
            ("farine", "面粉"),
        ],
        "occasional": [
            ("crème", "奶油"),
            ("cuillère", "勺子"),
        ],
        "rare": [
            ("jaune d'œuf", "蛋黄"),
            ("blanc en neige", "打发的蛋白"),
            ("rouleau à pâtisserie", "擀面杖"),
            ("four", "烤箱"),
            ("préchauffer", "预热"),
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
        "target_lang": "Chinese",
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
            ("amor", "爱"),
            ("corazón", "心"),
            ("noche", "夜晚"),
        ],
        "occasional": [
            ("dolor", "痛苦"),
            ("bailar", "跳舞"),
        ],
        "rare": [
            ("madrugada", "黎明"),
            ("recordar", "记得"),
            ("sin ti", "没有你"),
            ("siempre", "永远"),
            ("nunca", "从不"),
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
        "name": "Work English — contracts & meetings",
        "slug": "work-english",
        "target_lang": "Chinese",
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
            ("contract", "合同"),
            ("meeting", "会议"),
            ("project", "项目"),
        ],
        "occasional": [
            ("proposal", "提案"),
            ("budget", "预算"),
        ],
        "rare": [
            ("punctual", "准时"),
            ("report", "汇报"),
            ("decision", "决策"),
            ("cooperation", "合作"),
            ("sign", "签字"),
        ],
        "term_sessions": {
            "contract": ["contract-doc", "meeting-notes"],
            "meeting": ["meeting-notes", "voice-memo"],
            "project": ["whiteboard", "meeting-notes"],
            "proposal": ["whiteboard"],
            "budget": ["whiteboard"],
            "punctual": ["voice-memo"],
            "report": ["voice-memo"],
            "decision": ["meeting-notes"],
            "cooperation": ["voice-memo"],
            "sign": ["contract-doc"],
        },
    },
    {
        "name": "German tech docs — software reading",
        "slug": "german-docs",
        "target_lang": "Chinese",
        "sessions": [
            {"suffix": "api-docs", "source": "image", "day": 6,
             "gist": "A code documentation page about databases on a laptop screen"},
            {"suffix": "error-screen", "source": "image", "day": 4,
             "gist": "A screenshot of a red server error message and stack trace"},
            {"suffix": "git-readme", "source": "text", "day": 2,
             "gist": None},
        ],
        "frequent": [
            ("Datenbank", "数据库"),
            ("Speicher", "内存"),
        ],
        "occasional": [
            ("Server", "服务器"),
            ("Anwendung", "应用程序"),
        ],
        "rare": [
            ("Fehlermeldung", "错误信息"),
            ("Schnittstelle", "接口"),
            ("Schlüssel", "密钥"),
            ("Versionskontrolle", "版本控制"),
            ("Verbindung", "连接"),
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
    # source languages / phrasings over time. Same target_lang (Chinese)
    # means _pending_pairs will pair them; B1 should call them concept-
    # equivalent across these originals, producing the first real
    # cross-original Tier B clusters.
    {
        "name": "Polyglot crossings — same concept, different originals",
        "slug": "polyglot",
        "target_lang": "Chinese",
        "sessions": [
            {"suffix": "travel-notes", "source": "text", "day": 6,
             "gist": None},
            {"suffix": "transit-signs", "source": "image", "day": 5,
             "gist": "A subway direction sign photographed on a city platform"},
            {"suffix": "song-and-card", "source": "audio", "day": 4,
             "gist": None},
        ],
        "frequent": [
            # subway concept across English / French — both translate to 地铁
            ("subway", "地铁", "English"),
            ("métro", "地铁", "French"),
            # noodle concept across English / Japanese — both translate to 面条
            ("noodle soup", "面条", "English"),
            ("ヌードル", "面条", "Japanese"),
        ],
        "occasional": [
            # love concept across French / Italian — both translate to 爱
            ("l'amour", "爱", "French"),
            ("amore", "爱", "Italian"),
        ],
        "rare": [
            ("evening train", "晚班列车", "English"),
        ],
        "term_sessions": {
            "subway": ["travel-notes", "transit-signs"],
            "métro": ["transit-signs"],
            "noodle soup": ["travel-notes"],
            "ヌードル": ["travel-notes"],
            "l'amour": ["song-and-card"],
            "amore": ["song-and-card"],
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
    "Work English — contracts & meetings": "English",
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
