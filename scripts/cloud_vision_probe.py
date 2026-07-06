#!/usr/bin/env python3
"""Probe: does a cloud VLM clear the exact walls on-device E2B hit?

The on-device vision boundary (mapped on real photos, 2026-06-16, memory
续26d) has four failure families the guard can only refuse, not fix:
dense menus loop for minutes, blurry/angled small text hallucinates,
kanji-only Japanese is misread as Chinese, and kanji terms come back
untranslated. The user then dropped the premise those walls were built on
("no-network translation moments are rare"), which opens a hybrid image
path: cloud VLM when online, E2B + guard offline.

Before wiring that into the product, this probe runs the SAME production
prompt (TidelineTranslateViewModel image prompt, verbatim) and the SAME
parser (a line-by-line Python port of ImageReply.kt) against an
OpenAI-compatible chat-completions API, on images from those exact failure
families. The probe earns the product change when every documented failure
becomes a parsed, term-bearing (or honestly guarded) reply.

Usage:
  export OPENAI_API_KEY=sk-...          # or TIDELINE_CLOUD_API_KEY
  python3 scripts/cloud_vision_probe.py                 # default probe set
  python3 scripts/cloud_vision_probe.py --image a.jpg   # ad-hoc images
  python3 scripts/cloud_vision_probe.py --dry-run       # no key: parser self-test
  python3 scripts/cloud_vision_probe.py --list-models   # what the key can see

Endpoint config (any OpenAI-compatible server; Gemini works through its
compatibility endpoint):
  TIDELINE_CLOUD_BASE_URL   default https://api.openai.com/v1
      Gemini: https://generativelanguage.googleapis.com/v1beta/openai
  TIDELINE_CLOUD_MODEL      default gpt-4o-mini (Gemini e.g. gemini-2.5-flash)

The default set mixes in-repo photos (scripts/vision_smoke_assets/jp_real/)
with three Wikimedia Commons fetches cached under /tmp/tlimg3/ — /tmp gets
cleaned, so missing files are skipped with a note. To refetch, search
commons.wikimedia.org API (generator=search, gsrnamespace=6) for:
"japanese restaurant menu board" (board_1), "ramen shop menu japan"
(menu_1), "非常口 sign" (exit_2), and download the 1200px thumbs.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JP_REAL = REPO / "scripts" / "vision_smoke_assets" / "jp_real"

BASE_URL = os.environ.get("TIDELINE_CLOUD_BASE_URL", "https://api.openai.com/v1").rstrip("/")
MODEL = os.environ.get("TIDELINE_CLOUD_MODEL", "gpt-4o-mini")
API_KEY = os.environ.get("TIDELINE_CLOUD_API_KEY") or os.environ.get("OPENAI_API_KEY")

TARGET_LANG = "Chinese"

# ---------------------------------------------------------------------------
# Production image prompt — verbatim mirror of TidelineTranslateViewModel's
# translateImage prompt (android/.../ui/TidelineTranslateViewModel.kt). If the
# APK prompt changes, change this with it; the probe only means something
# while the two are the same words.
# ---------------------------------------------------------------------------
def build_prompt(lang: str = TARGET_LANG) -> str:
    return (
        "Look at this image and reply with these lines:\n"
        f"TRANSLATION: all visible text translated to {lang}, as one natural "
        "sentence or phrase (write NONE if there is no text)\n"
        "SCENE: 5-8 words naming where/what this is — place, activity, or notable objects\n"
        "SCENE_TYPE: the kind of place in 2-4 characters (例如 拉面店 / 车站 / 咖啡馆) — "
        "the same kind of place should get the same label so it groups across visits\n"
        "LANGUAGE: the language the visible text is written in, one word like English\n"
        "Then 1-6 key words from the image worth learning, each on its own "
        "line exactly like this example:\n"
        "TERM: Exit = 出口\n"
        "Skip brand names, logos and proper names — they are not vocabulary."
    )


# ---------------------------------------------------------------------------
# Parser — line-by-line port of intelligence/ImageReply.kt (parseImageReply,
# parsePair, rendersInTargetScript). Same constants, same guards, same
# fail-soft order, so a cloud reply is judged by the product's own rules.
# ---------------------------------------------------------------------------
MAX_TERMS = 8
MAX_TERM_LENGTH = 60


def renders_in_target_script(translated: str, target_lang: str) -> bool:
    if target_lang.lower() != "chinese":
        return True
    has_cjk = any(0x4E00 <= ord(c) <= 0x9FFF for c in translated)
    has_latin = any(("a" <= c <= "z") or ("A" <= c <= "Z") for c in translated)
    return has_cjk and not has_latin


def parse_pair(segment: str, target_lang: str):
    """Returns ("ok", (orig, trans)) | ("half", orig) | ("bad", None)."""
    parts = re.split(r"[=→]", segment, maxsplit=1)
    if len(parts) != 2:
        return ("bad", None)
    orig, trans = parts[0].strip(), parts[1].strip()
    if not orig or not trans:
        return ("bad", None)
    if len(orig) > MAX_TERM_LENGTH or len(trans) > MAX_TERM_LENGTH:
        return ("bad", None)
    if not any(c.isalpha() for c in orig):
        return ("bad", None)
    if "original" in orig.lower() or "translation" in trans.lower():
        return ("bad", None)
    if not renders_in_target_script(trans, target_lang):
        return ("half", orig)
    return ("ok", (orig, trans))


def _first_line_after(text: str, idx: int, marker: str) -> str:
    return text[idx + len(marker):].splitlines()[0].strip() if idx >= 0 else ""


def parse_image_reply(raw: str, target_lang: str = TARGET_LANG) -> dict:
    text = raw.strip()
    lower = text.lower()
    scene_type_idx = lower.find("scene_type:")
    scene_idx = lower.find("scene:")
    language_idx = lower.find("language:")
    terms_idx = lower.find("terms:")
    m = re.search(r"(?im)^\s*TERM:", text)
    first_term_idx = m.start() if m else -1

    non_neg = [i for i in (scene_idx, scene_type_idx, language_idx, terms_idx, first_term_idx) if i >= 0]
    cut_idx = min(non_neg) if non_neg else len(text)
    translated = re.sub(r"(?i)TRANSLATION:\s*", "", text[:cut_idx]).strip()

    scene_gist = None
    if scene_idx >= 0:
        line = _first_line_after(text, scene_idx, "SCENE:")
        t = re.search(r"(?i)TERMS?:", line)
        line = line[: t.start()] if t else line
        scene_gist = line.strip() or None

    line_parses = [
        parse_pair(m.group(1), target_lang)
        for m in re.finditer(r"(?im)^\s*TERM:\s*(.+)$", text)
    ]

    inline_parses = []
    if terms_idx >= 0:
        line = _first_line_after(text, terms_idx, "TERMS:")
        if line.upper() != "NONE":
            inline_parses = [parse_pair(seg, target_lang) for seg in re.split(r"[|;]", line)]

    language = None
    if language_idx >= 0:
        cand = _first_line_after(text, language_idx, "LANGUAGE:")
        if cand and len(cand) <= 20 and " " not in cand:
            language = cand

    scene_type = None
    if scene_type_idx >= 0:
        cand = _first_line_after(text, scene_type_idx, "SCENE_TYPE:").strip("。.：:")
        if cand and len(cand) <= 12:
            scene_type = cand

    chosen = line_parses if any(k != "bad" for k, _ in line_parses) else inline_parses
    terms, seen = [], set()
    for kind, val in chosen:
        if kind == "ok" and val[0] not in seen:
            seen.add(val[0])
            terms.append(val)
            if len(terms) == MAX_TERMS:
                break
    retry_worthy, rseen = [], set()
    for kind, val in chosen:
        if kind == "half" and val not in rseen and all(o != val for o, _ in terms):
            rseen.add(val)
            retry_worthy.append(val)
            if len(retry_worthy) == MAX_TERMS:
                break

    return {
        "translated": translated,
        "scene_gist": scene_gist,
        "scene_type": scene_type,
        "language": language,
        "terms": terms,
        "retry_worthy": retry_worthy,
    }


# The guard's language leg (TranslationGuard.canonLang): the image path blocks
# before sedimenting when the model reports the text is already the native
# language. The probe reports when that verdict WOULD fire.
def guard_same_as_native(language: str | None, native: str = "Chinese") -> bool:
    if not language:
        return False
    canon = language.strip().lower()
    return canon in {"chinese", "中文", "zh", "zh-cn", "mandarin", "汉语", "漢語"}


def self_test() -> None:
    r = parse_image_reply(
        "TRANSLATION: 特价优惠奶酪\nSCENE: cheese shop shelf with price tags\n"
        "SCENE_TYPE: 食品店\nLANGUAGE: French\n"
        "TERM: OFFRE SPECIALE = 特价优惠\nTERM: fromage = 奶酪"
    )
    assert r["translated"] == "特价优惠奶酪"
    assert r["scene_type"] == "食品店" and r["language"] == "French"
    assert r["terms"] == [("OFFRE SPECIALE", "特价优惠"), ("fromage", "奶酪")]

    r = parse_image_reply("TERM: Premium = 高 premium")
    assert r["terms"] == [] and r["retry_worthy"] == ["Premium"]

    r = parse_image_reply("TERM: original = translation")
    assert r["terms"] == [] and r["retry_worthy"] == []

    r = parse_image_reply("TRANSLATION: x\nTERMS: Exit = 出口 | 75% = 百分之七十五")
    assert r["terms"] == [("Exit", "出口")]

    r = parse_image_reply("こんにちは、これはただの返事です")
    assert r["translated"].startswith("こんにちは") and r["terms"] == []

    r = parse_image_reply("TRANSLATION: NONE\nTERMS: NONE")
    assert r["terms"] == []

    assert guard_same_as_native("Chinese") and not guard_same_as_native("Japanese")
    print("parser self-test: 7/7 ok")


# ---------------------------------------------------------------------------
# Image prep — mirrors media/ImageOps.prepareCaptureImage: EXIF-upright,
# long edge capped at 1024, JPEG q85. The probe must send what the app sends.
# ---------------------------------------------------------------------------
def prepare_image(path: Path) -> bytes:
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def call_cloud(image_bytes: bytes, prompt: str) -> tuple[str, dict, float]:
    data_url = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode()
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                # Image before text — the order the Android path uses
                # (Contents.of(listOf(ImageBytes, Text))).
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    req = urllib.request.Request(
        BASE_URL + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.load(resp)
    elapsed = time.time() - t0
    content = body["choices"][0]["message"]["content"] or ""
    return content, body.get("usage", {}), elapsed


def list_models() -> None:
    req = urllib.request.Request(
        BASE_URL + "/models", headers={"Authorization": f"Bearer {API_KEY}"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    for m in sorted(item.get("id", "?") for item in body.get("data", [])):
        print(m)


# (path, family note) — the documented on-device failure each image probes.
PROBE_SET: list[tuple[Path, str]] = [
    (Path("/tmp/tlimg3/board_1.jpg"), "密集菜单墙 STEAK HOUSE 88(E2B 超长复读卡死家族)→ 期望正常返回+多词条"),
    (Path("/tmp/tlimg3/menu_1.jpg"), "拉面店密集竖排告示(复读家族)→ 期望正常返回"),
    (Path("/tmp/tlimg3/exit_2.jpg"), "緊急出口/EXIT(真中文系对照)→ 期望 LANGUAGE=Chinese、护栏正确触发"),
    (JP_REAL / "japanese_photos_04187.jpg", "纯汉字「沿線食堂」(E2B 误判中文家族)→ 期望 Japanese+可用词条"),
    (JP_REAL / "japanese_photos_02206.jpg", "瓶身小字汉字+品牌 CHOSHI BEER(小字+品牌过滤)→ 期望词条避开品牌"),
    (JP_REAL / "japanese_photos_08323.jpg", "斜角暗光杯垫 暴走東京 BAR(幻觉抵抗家族)→ 期望不瞎编"),
    (JP_REAL / "japanese_photos_00011.jpg", "暗光酒吧拉丁酒标(拉丁对照+品牌过滤)"),
]


def run_probe(paths: list[tuple[Path, str]]) -> None:
    prompt = build_prompt()
    print(f"endpoint={BASE_URL}  model={MODEL}\n")
    for path, note in paths:
        print(f"=== {path.name} — {note}")
        if not path.exists():
            print("    SKIP: file missing (Wikimedia cache cleaned? see docstring to refetch)\n")
            continue
        image = prepare_image(path)
        try:
            raw, usage, elapsed = call_cloud(image, prompt)
        except urllib.error.HTTPError as e:
            print(f"    HTTP {e.code}: {e.read().decode(errors='replace')[:400]}\n")
            continue
        r = parse_image_reply(raw)
        flags = []
        if guard_same_as_native(r["language"]):
            flags.append("guard:SAME_AS_NATIVE would fire")
        if len(raw) > 3500:
            flags.append("repetition_suspect(raw>3500ch)")
        if not r["terms"] and not guard_same_as_native(r["language"]):
            flags.append("no_terms")
        print(f"    {elapsed:.1f}s  tokens={usage.get('prompt_tokens', '?')}+{usage.get('completion_tokens', '?')}  raw={len(raw)}ch")
        print(f"    LANGUAGE={r['language']}  SCENE_TYPE={r['scene_type']}  gist={r['scene_gist']}")
        print(f"    TRANSLATION: {r['translated'][:90]}")
        for o, t in r["terms"]:
            print(f"    TERM: {o} = {t}")
        if r["retry_worthy"]:
            print(f"    retry-worthy: {r['retry_worthy']}")
        if flags:
            print(f"    FLAGS: {'; '.join(flags)}")
        print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", nargs="*", help="ad-hoc image paths (override default probe set)")
    ap.add_argument("--dry-run", action="store_true", help="parser self-test + prompt + set listing, no network")
    ap.add_argument("--list-models", action="store_true")
    args = ap.parse_args()

    self_test()
    if args.dry_run:
        print("\n--- production prompt (verbatim mirror) ---")
        print(build_prompt())
        print("\n--- probe set ---")
        for p, note in PROBE_SET:
            state = "ok" if p.exists() else "MISSING"
            print(f"[{state}] {p} — {note}")
        return

    if not API_KEY:
        sys.exit("No API key: set OPENAI_API_KEY (or TIDELINE_CLOUD_API_KEY). --dry-run works without one.")
    if args.list_models:
        list_models()
        return

    paths = [(Path(p), "ad-hoc") for p in args.image] if args.image else PROBE_SET
    run_probe(paths)


if __name__ == "__main__":
    main()
