"""Seed data generator for the translations drawer.

Populates SQLite with one realistic story whose repetition pattern is the
substrate emergence detection (Step 6b) will scan. Frequent terms appear 4-6
times, occasional 2-3 times, rare 1 time — this gives candidate promotion
something real to find.

The story is **a week in Tokyo** for a first-language-Chinese traveller: it's
read mostly off Japanese menus and signs, with the odd bilingual tourist board
(so a few English terms cross in). Every foreign text is translated INTO
Chinese. It is shaped to exercise the whole pipeline end to end:

  - repeated terms promote to candidates → cards (frequency);
  - the same concept met in two languages (ラーメン / "ramen" → 拉面,
    駅 / "station" → 车站, 地下鉄 / "subway" → 地铁) gives cross-language
    **concept** clusters (B1);
  - dishes that share a scene / cuisine gather into **theme** clusters (B7) —
    "your night in the ramen alley", "the izakaya table".

**Episodic honesty (2026-05-28):** the demo's "scene feel" must only use
signals the real capture pipeline can actually produce — never narrated prose
the product can't generate. Mirrors what the on-device Android pipeline was
verified to emit (TidelineTranslateViewModel.translateImage): the trip is
split into *capture sessions* (a menu photo, a sign, a voice memo). Every row
carries:

  - `source`     — the input modality (image / audio / text), exactly what
                   the client injects by default (image pipeline → "image").
  - `context_snippet` — the VLM's short *scene gist* for an image capture
                   (e.g. "回转寿司传送带上一小碟一小碟转过来的握寿司") — a real
                   model-produced description of where/what the moment was,
                   written in the user's first language (Chinese), which is why
                   storing it is honest. ONLY image captures carry it; text /
                   audio rows leave it None, because their prompts ask for no
                   SCENE line (matches the live app exactly). The episodic title
                   (B6, `episodic_title.build_prompt`) turns these gists into
                   the "你在拉面横丁的那一夜" feeling at naming time.
  - `session_id` — groups everything captured in one moment, so a single menu
                   photo's items cluster as one remembered event.

A term repeats because it shows up across *several* sessions (seen on the menu,
then a sign, then heard at the counter) — the honest shape of a word you keep
running into.

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


# One trip, told as its capture moments — a week in Tokyo. Each scenario carries
# its word pairs (in three frequency tiers) plus a list of `sessions`: the
# discrete capture moments of the trip. A session's `gist` is the short scene
# description a VLM would emit for an image capture (the recorded
# context_snippet), in the user's first language — or None for text/audio
# captures, whose prompts produce no SCENE line in the real app. `day` is
# days-ago from `now`, giving each session its own timestamp cluster.
SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "Tokyo trip — a week of meals and trains",
        "slug": "tokyo",
        "target_lang": "Chinese",
        "sessions": [
            {"suffix": "ramen-yokocho", "source": "image", "day": 6,
             "gist": "深夜拉面横丁里那台发着暖光的购票机"},
            {"suffix": "izakaya", "source": "image", "day": 5,
             "gist": "居酒屋矮桌上摊开的一张手写纸菜单"},
            {"suffix": "station", "source": "image", "day": 4,
             "gist": "车站检票口上方那块蓝色的出口指示牌"},
            {"suffix": "bilingual-signs", "source": "image", "day": 4,
             "gist": "车站走廊里一块中英日三语的旅游指示牌"},
            {"suffix": "counter-audio", "source": "audio", "day": 5,
             "gist": None},
            {"suffix": "sushi", "source": "image", "day": 3,
             "gist": "回转寿司传送带上一小碟一小碟转过来的握寿司"},
            {"suffix": "market", "source": "image", "day": 2,
             "gist": "清晨筑地市场摊位上铺在碎冰上的海鲜"},
        ],
        "frequent": [
            # the recurring words of the trip — and the three concepts met in
            # BOTH languages (Japanese menu/sign + the bilingual tourist board),
            # kept frequent so both twins promote and cluster across languages:
            #   ラーメン ↔ ramen   → 拉面
            #   駅      ↔ station → 车站
            #   地下鉄   ↔ subway  → 地铁
            ("ラーメン", "拉面"),
            ("ramen", "拉面", "English"),
            ("駅", "车站"),
            ("station", "车站", "English"),
            ("地下鉄", "地铁"),
            ("subway", "地铁", "English"),
            ("刺身", "生鱼片"),
            ("天ぷら", "天妇罗"),
            ("餃子", "煎饺"),
            ("醤油", "酱油"),
        ],
        "occasional": [
            ("焼き鳥", "烤鸡肉串"),
            ("枝豆", "毛豆"),
            ("わさび", "芥末"),
            ("海鮮丼", "海鲜盖饭"),
        ],
        "rare": [
            ("いらっしゃいませ", "欢迎光临"),
            ("お会計", "买单"),
            ("つけ麺", "蘸面"),
            ("生ビール", "扎啤"),
            ("切符", "车票"),
        ],
        # Which capture sessions each term could honestly appear in — its
        # OCR / transcript context must fit the term (a station word belongs on
        # a station sign, not a ramen menu). Copies round-robin only within this
        # whitelist.
        "term_sessions": {
            "ラーメン": ["ramen-yokocho", "counter-audio"],
            "ramen": ["bilingual-signs", "ramen-yokocho"],
            "駅": ["station", "bilingual-signs"],
            "station": ["bilingual-signs", "station"],
            "地下鉄": ["station"],
            "subway": ["bilingual-signs", "station"],
            "刺身": ["sushi", "izakaya"],
            "天ぷら": ["izakaya", "market"],
            "餃子": ["ramen-yokocho"],
            "醤油": ["sushi", "izakaya"],
            "焼き鳥": ["izakaya"],
            "枝豆": ["izakaya"],
            "わさび": ["sushi"],
            "海鮮丼": ["market", "sushi"],
            "いらっしゃいませ": ["counter-audio"],
            "お会計": ["counter-audio"],
            "つけ麺": ["ramen-yokocho"],
            "生ビール": ["izakaya"],
            "切符": ["station"],
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
# The Tokyo trip is Japanese by default; the bilingual-board English terms
# carry their own source language via a 3-tuple override.
_SCENARIO_SOURCE_LANG = {
    "Tokyo trip — a week of meals and trains": "Japanese",
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
