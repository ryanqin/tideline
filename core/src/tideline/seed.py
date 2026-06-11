"""Seed data generator for the translations drawer.

Populates SQLite with one realistic story whose repetition pattern is the
substrate emergence detection (Step 6b) will scan. Frequent terms appear 4-6
times, occasional 2-3 times, rare 1 time — this gives candidate promotion
something real to find.

The data is **two trips** for a first-language-Chinese traveller: a week in
**Tokyo** (Japanese) and a few days in **Paris** (French). Each trip is **one
foreign language**, read off menus, signs and the counter — the lived §3.3
scenario: you translate from a single non-first-language across similar scenes,
and what recurs *within that language* is what fuses. Every foreign text is
translated INTO Chinese. The two-language shape is deliberate — it's what lets
the **by-language lens** show something (a single trip hides it). It exercises
the whole pipeline end to end:

  - repeated terms promote to candidates → cards (frequency);
  - **same-language synonyms** gather into one **concept** cluster (B1):
    different words *in the same language* that land on the same first-language
    word fuse deterministically, no vote (中華そば & ラーメン both → 拉面;
    addition & facture both → 账单). Clusters are scoped per language-pair
    (§3.3): a native word reached from two languages stays **two** clusters —
    お茶→茶 (Japanese) and thé→茶 (French) never fuse, métro→地铁 (French) and
    地下鉄→地铁 (Japanese) never fuse. That separation IS the by-language story;
  - dishes / sights that share a scene gather into **theme** clusters by
    co-occurrence (a capture session) — "your night in the ramen alley", "the
    morning at the Paris café".

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
import hashlib
import json
import random
import sqlite3
import struct
import sys
import zlib
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# Two trips, each told as its capture moments — a week in Tokyo (Japanese) and
# a few days in Paris (French). Each scenario carries
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
            {"suffix": "counter-audio", "source": "audio", "day": 5,
             "gist": None},
            {"suffix": "sushi", "source": "image", "day": 3,
             "gist": "回转寿司传送带上一小碟一小碟转过来的握寿司"},
            {"suffix": "market", "source": "image", "day": 2,
             "gist": "清晨筑地市场摊位上铺在碎冰上的海鲜"},
        ],
        "frequent": [
            # The recurring words of the trip — one language (Japanese), met
            # again and again across menus, signs and the counter. Two are
            # *same-language synonyms* of another frequent term: different
            # Japanese words that land on the same first-language word, so they
            # fuse into ONE concept cluster (within Japanese, no model vote
            # needed; §3.3) — and both are frequent so the merged concept is
            # substantial:
            #   中華そば → 拉面  (fuses with ラーメン)
            #   メトロ   → 地铁  (fuses with 地下鉄)
            ("ラーメン", "拉面"),
            ("中華そば", "拉面"),
            ("駅", "车站"),
            ("地下鉄", "地铁"),
            ("メトロ", "地铁"),
            ("刺身", "生鱼片"),
            ("天ぷら", "天妇罗"),
            ("餃子", "煎饺"),
            ("醤油", "酱油"),
            ("寿司", "寿司"),
            ("お茶", "茶"),
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
            "中華そば": ["ramen-yokocho"],
            "駅": ["station"],
            "地下鉄": ["station"],
            "メトロ": ["station"],
            "刺身": ["sushi", "izakaya"],
            "天ぷら": ["izakaya", "market"],
            "餃子": ["ramen-yokocho"],
            "醤油": ["sushi", "izakaya"],
            "寿司": ["sushi", "market"],
            "お茶": ["sushi", "izakaya"],
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
    {
        "name": "Paris trip — a few days of cafés and the métro",
        "slug": "paris",
        "target_lang": "Chinese",
        "sessions": [
            {"suffix": "cafe-morning", "source": "image", "day": 18,
             "gist": "清晨街角咖啡馆露天座上那杯冒着热气的咖啡"},
            {"suffix": "boulangerie", "source": "image", "day": 17,
             "gist": "面包店橱窗里斜插在藤篮中的长棍面包"},
            {"suffix": "metro", "source": "image", "day": 16,
             "gist": "地铁站台上方那块白底的线路指示牌"},
            {"suffix": "bistro", "source": "image", "day": 15,
             "gist": "小酒馆黑板上用粉笔写的当日菜单"},
            {"suffix": "market", "source": "image", "day": 14,
             "gist": "露天市场摊位上堆成小山的奶酪和水果"},
            {"suffix": "waiter-audio", "source": "audio", "day": 15,
             "gist": None},
        ],
        "frequent": [
            # One language (French — Latin script, so source_lang is the
            # *model's* call in the live app, not deterministic like kana). Two
            # are *same-language synonyms* of each other that land on the same
            # first-language word → they fuse into ONE French concept cluster,
            # mirroring the Japanese 中華そば/ラーメン fusion within this trip:
            #   addition → 账单  (fuses with facture)
            # Two more (thé→茶, métro→地铁) deliberately collide with Japanese
            # native words but MUST stay separate clusters (§3.3, per
            # language-pair) — that collision is the by-language demo.
            ("café", "咖啡"),
            ("thé", "茶"),
            ("métro", "地铁"),
            ("pain", "面包"),
            ("fromage", "奶酪"),
            ("addition", "账单"),
            ("facture", "账单"),
        ],
        "occasional": [
            ("vin", "葡萄酒"),
            ("croissant", "牛角包"),
            ("musée", "博物馆"),
        ],
        "rare": [
            ("bonjour", "你好"),
            ("billet", "车票"),
            ("merci", "谢谢"),
        ],
        "term_sessions": {
            "café": ["cafe-morning", "bistro", "waiter-audio"],
            "thé": ["cafe-morning", "bistro"],
            "métro": ["metro"],
            "pain": ["boulangerie", "market"],
            "fromage": ["market", "bistro"],
            "addition": ["bistro", "cafe-morning", "waiter-audio"],
            "facture": ["bistro"],
            "vin": ["bistro", "market"],
            "croissant": ["cafe-morning", "boulangerie"],
            "musée": ["metro"],
            "bonjour": ["waiter-audio", "cafe-morning"],
            "billet": ["metro"],
            "merci": ["waiter-audio"],
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
# Each trip is one foreign language: Tokyo is Japanese, Paris is French. A
# word pair may still override its source language with an optional 3rd
# element, but each single-language trip doesn't use it.
_SCENARIO_SOURCE_LANG = {
    "Tokyo trip — a week of meals and trains": "Japanese",
    "Paris trip — a few days of cafés and the métro": "French",
}


# --- Demo capture images -----------------------------------------------------
# An image capture keeps its source photo so the storage + serving path carries
# real image bytes — honest to §3.2, where the source image is recall material,
# not discarded once the VLM has read it. The seed can't ship real photos, so
# each image session gets a small solid swatch in a distinct warm tone; the real
# on-device camera/album capture replaces it with the actual photo. Pure-stdlib
# (a hand-assembled minimal PNG) so seeding pulls in no Pillow dependency.
def _swatch_png(rgb: tuple[int, int, int], size: int = 96) -> bytes:
    def _chunk(typ: bytes, data: bytes) -> bytes:
        body = typ + data
        return (
            struct.pack(">I", len(data))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    row = b"\x00" + bytes(rgb) * size  # filter byte 0 (None) + `size` RGB pixels
    raw = row * size
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


def _session_color(session_id: str) -> tuple[int, int, int]:
    """A stable warm tone per capture session, so each seeded photo is a
    distinct swatch (recognizable once a display slice renders it)."""
    h = hashlib.sha1(session_id.encode("utf-8")).digest()
    return (150 + h[0] % 95, 110 + h[1] % 90, 80 + h[2] % 80)


def _pseudo_region(session_id: str, original: str) -> str:
    """Deterministic normalized [x0,y0,x1,y1] box for a seed word — stands in
    for the device OCR's real geometry so the mask UI is demoable offline."""
    h = hashlib.sha1(f"{session_id}:{original}".encode()).digest()
    x0 = 0.06 + (h[0] / 255) * 0.40
    y0 = 0.10 + (h[1] / 255) * 0.55
    w = 0.28 + (h[2] / 255) * 0.22
    hgt = 0.08 + (h[3] / 255) * 0.05
    return json.dumps(
        [round(x0, 4), round(y0, 4), round(min(x0 + w, 0.94), 4), round(min(y0 + hgt, 0.94), 4)]
    )


def _beep_wav(session_id: str) -> bytes:
    """A short sine-tone WAV (16 kHz mono PCM16) standing in for a real
    captured recording — pitch keyed to the session so demo "recordings"
    are tellable apart. Real captures carry the device mic's WAV."""
    import math

    rate, seconds = 16_000, 1.2
    freq = 392 + (int(hashlib.sha1(session_id.encode()).hexdigest(), 16) % 5) * 66
    n = int(rate * seconds)
    pcm = bytearray()
    for i in range(n):
        # gentle fade in/out so the placeholder doesn't click
        env = min(1.0, i / 800, (n - i) / 800)
        v = int(12_000 * env * math.sin(2 * math.pi * freq * i / rate))
        pcm += struct.pack("<h", v)
    hdr = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    hdr += b"data" + struct.pack("<I", len(pcm))
    return hdr + bytes(pcm)


def generate_entries(
    seed: int = 42,
    now: datetime | None = None,
) -> list[tuple]:
    """Generate seed rows as 9-tuples.

    Each tuple is
    ``(original, target_lang, translated, source_lang, source,
    context_snippet, session_id, created_at_iso, source_image,
    source_region, source_audio)`` — the photo bytes + the word's normalized
    [x0,y0,x1,y1] box for image sessions, the recording's WAV bytes for
    audio sessions, None elsewhere.

    A term's N copies are distributed round-robin across its scenario's
    capture sessions, so a frequent term naturally lands in several
    sessions (the honest shape of a recurring word) while every copy
    inherits that session's modality, scene gist (image captures only;
    None for text/audio), and timestamp cluster. Fully deterministic given
    (seed, now). Output order is shuffled to mimic real chronological mixing.
    """
    rng = random.Random(seed)
    out: list[tuple] = []
    # A capture's source photo is shared by all rows from that session (computed
    # once), so a menu photo's items all point at the same image.
    image_cache: dict[str, bytes] = {}
    audio_cache: dict[str, bytes] = {}
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
                    # Keep the capture's source image (image sessions only) as
                    # recall material — one swatch per session, shared by its
                    # rows. Real captures carry the device photo; this is the
                    # demo placeholder.
                    source_image = (
                        image_cache.setdefault(
                            session_id, _swatch_png(_session_color(session_id))
                        )
                        if session["source"] == "image"
                        else None
                    )
                    # Where the word sits in its photo (real captures: device
                    # OCR; here a deterministic pseudo-box on the swatch) —
                    # anchors the toggleable photo-word mask in the UI.
                    source_region = (
                        _pseudo_region(session_id, original)
                        if session["source"] == "image"
                        else None
                    )
                    # A heard session keeps its "recording" (placeholder tone;
                    # real captures carry the mic WAV) — dictation material.
                    source_audio = (
                        audio_cache.setdefault(session_id, _beep_wav(session_id))
                        if session["source"] == "audio"
                        else None
                    )
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
                            source_image,
                            source_region,
                            source_audio,
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
        "context_snippet, session_id, created_at, source_image, source_region, "
        "source_audio) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
