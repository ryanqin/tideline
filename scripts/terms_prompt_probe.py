#!/usr/bin/env python3
"""Probe: which TERMS prompt makes on-device E2B emit parseable word pairs?

Phase 5a follow-up. The first on-device run of the three-line image prompt
(TRANSLATION / SCENE / TERMS) came back with an unparseable TERMS line —
translations only, no original=translation pairs — so every captured word
fell back to the unpromotable "[image N B]" summary row. Before baking a new
prompt into the APK (slow loop), iterate here against the SAME photo the
device captured, on the same E2B family via llama-mtmd-cli.

Scores each (prompt × temperature) cell with a Python port of the Kotlin
parser (ImageReply.kt) — a cell passes when it yields ≥1 valid pair AND a
non-empty translation.

Usage:
  python scripts/terms_prompt_probe.py --image /tmp/s23_wipes.jpg
  python scripts/terms_prompt_probe.py --image a.jpg b.png --temps 0.2,1.0
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODELS = REPO / "models"
LM = MODELS / "gemma-4-E2B-it-Q4_K_M.gguf"
MMPROJ = MODELS / "vision-e2b" / "mmproj-F16.gguf"

LANG = "Chinese"

PROMPTS = {
    # The prompt currently shipped in the APK (TidelineTranslateViewModel).
    "p0_current": (
        "Look at this image and reply in exactly three lines:\n"
        f"TRANSLATION: all visible text translated to {LANG} (write NONE if there is no text)\n"
        "SCENE: 5-8 words naming where/what this is — place, activity, or notable objects\n"
        "TERMS: the 1-6 most useful words or short phrases from the image, "
        "each as original=translation, separated by | (write NONE if there is no text)"
    ),
    # One-shot format example anchoring the pair shape.
    "p1_example": (
        "Look at this image and reply in exactly three lines:\n"
        f"TRANSLATION: all visible text translated to {LANG} (write NONE if there is no text)\n"
        "SCENE: 5-8 words naming where/what this is — place, activity, or notable objects\n"
        "TERMS: 1-6 key words EXACTLY as written in the image, each with its "
        f"{LANG} translation, like: ramen=拉面 | Exit=出口 (write NONE if there is no text)"
    ),
    # One TERM per line — no "|" separator. The on-device run showed the
    # |-spec bleeding into TRANSLATION (it came out as a "x | y | z" list)
    # and that rhythm is a repetition attractor: litertlm E2B looped the
    # same words for 5441 chars / 189 s and never reached SCENE/TERMS.
    "p3_line_terms": (
        "Look at this image and reply with these lines:\n"
        f"TRANSLATION: all visible text translated to {LANG}, as one natural "
        "sentence or phrase (write NONE if there is no text)\n"
        "SCENE: 5-8 words naming where/what this is — place, activity, or notable objects\n"
        "Then 1-6 key words from the image, each on its own line:\n"
        f"TERM: the original word = its {LANG} translation"
    ),
    # Spell out both sides of the pair explicitly.
    "p2_explicit": (
        "Look at this image and reply in exactly three lines:\n"
        f"TRANSLATION: all visible text translated to {LANG} (write NONE if there is no text)\n"
        "SCENE: 5-8 words naming where/what this is — place, activity, or notable objects\n"
        "TERMS: pick 1-6 useful words from the image text. For each, write the "
        f"original word as it appears, then =, then its {LANG} translation. "
        "Separate pairs with | (write NONE if there is no text)"
    ),
}

MAX_TERMS = 8
MAX_TERM_LENGTH = 60


def parse_image_reply(raw: str) -> dict:
    """Python port of ImageReply.kt — keep in sync."""
    text = raw.strip()
    low = text.lower()
    scene_idx = low.find("scene:")
    terms_idx = low.find("terms:")

    cut_candidates = [i for i in (scene_idx, terms_idx) if i >= 0]
    cut = min(cut_candidates) if cut_candidates else len(text)
    translated = re.sub(r"(?i)TRANSLATION:\s*", "", text[:cut]).strip()

    gist = None
    if scene_idx >= 0:
        line = text[scene_idx + 6 :].splitlines()[0] if text[scene_idx + 6 :] else ""
        t = line.lower().find("terms:")
        gist = (line[:t] if t >= 0 else line).strip() or None

    terms: list[tuple[str, str]] = []
    # line-per-term shape: every "TERM: a = b" line anywhere in the answer
    for m in re.finditer(r"(?im)^\s*TERM:\s*(.+)$", text):
        parts = re.split(r"[=→]", m.group(1), maxsplit=1)
        if len(parts) != 2:
            continue
        orig, trans = parts[0].strip(), parts[1].strip()
        if (orig and trans and len(orig) <= MAX_TERM_LENGTH and len(trans) <= MAX_TERM_LENGTH
                and "original" not in orig.lower() and "translation" not in trans.lower()
                and orig not in {t[0] for t in terms}):
            terms.append((orig, trans))
        if len(terms) >= MAX_TERMS:
            break
    if not terms and terms_idx >= 0:
        seg = text[terms_idx + 6 :]
        line = seg.splitlines()[0].strip() if seg else ""
        if line.upper() != "NONE":
            seen = set()
            for piece in re.split(r"[|;]", line):
                parts = re.split(r"[=→]", piece, maxsplit=1)
                if len(parts) != 2:
                    continue
                orig, trans = parts[0].strip(), parts[1].strip()
                if not orig or not trans:
                    continue
                if len(orig) > MAX_TERM_LENGTH or len(trans) > MAX_TERM_LENGTH:
                    continue
                # Mirror ImageReply.kt: an echoed format spec is not vocabulary.
                if "original" in orig.lower() or "translation" in trans.lower():
                    continue
                if orig in seen:
                    continue
                seen.add(orig)
                terms.append((orig, trans))
                if len(terms) >= MAX_TERMS:
                    break
    return {"translated": translated, "gist": gist, "terms": terms}


def find_bin() -> str:
    cand = os.environ.get("TIDELINE_MTMD_BIN") or shutil.which("llama-mtmd-cli")
    if not cand:
        for p in ("/opt/homebrew/bin/llama-mtmd-cli", "/usr/local/bin/llama-mtmd-cli"):
            if Path(p).exists():
                cand = p
                break
    if not cand or not Path(cand).exists():
        sys.exit("llama-mtmd-cli not found (brew install llama.cpp)")
    return cand


def run_one(
    bin_path: str, image: Path, prompt: str, temp: float, sys_prompt: str | None = None
) -> tuple[str, float]:
    cmd = [
        bin_path,
        "-m", str(LM),
        "--mmproj", str(MMPROJ),
        "--image", str(image),
        "-p", prompt,
        "--jinja",
        "-ngl", "0",
        "--temp", str(temp),
        "-n", "1024",
    ]
    if sys_prompt:
        cmd += ["-sys", sys_prompt]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    out = proc.stdout.strip()
    if not out and proc.returncode != 0:
        out = f"[exit {proc.returncode}] " + proc.stderr.strip()[-400:]
    return out, time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", nargs="+", required=True)
    ap.add_argument("--temps", default="0.2,1.0")
    ap.add_argument("--prompts", default=",".join(PROMPTS))
    # The APK's translator systemInstruction ("only the translation, no
    # preamble, no explanation") conflicts with the three-line format ask —
    # pass --device-sys to reproduce the on-device conversation faithfully.
    ap.add_argument("--device-sys", action="store_true")
    args = ap.parse_args()

    bin_path = find_bin()
    temps = [float(t) for t in args.temps.split(",")]
    keys = [k.strip() for k in args.prompts.split(",") if k.strip() in PROMPTS]

    for img in args.image:
        for key in keys:
            for temp in temps:
                sys_prompt = (
                    "You are a precise translator. Respond with only the "
                    "translation — no preamble, no explanation, no quotation marks."
                ) if args.device_sys else None
                out, dt = run_one(bin_path, Path(img), PROMPTS[key], temp, sys_prompt)
                # llama.cpp's jinja path surfaces Gemma's THOUGHT channel, and
                # at low temp the thought restates the instruction markers
                # verbatim — poisoning a first-marker parse. The device runtime
                # (litertlm) never shows thought, so score only the final
                # answer: everything from the LAST "TRANSLATION:" on.
                cut = out.rfind("TRANSLATION:")
                scored = out[cut:] if cut >= 0 else out
                parsed = parse_image_reply(scored)
                ok = bool(parsed["terms"]) and bool(parsed["translated"])
                print(f"\n=== {Path(img).name} × {key} × temp={temp}  "
                      f"[{'PASS' if ok else 'FAIL'}] ({dt:.0f}s)")
                print(f"  scored    | {scored[:400]!r}")
                print(f"  translated| {parsed['translated'][:120]!r}")
                print(f"  gist      | {parsed['gist']!r}")
                print(f"  terms     | {parsed['terms']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
