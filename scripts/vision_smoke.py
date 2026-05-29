#!/usr/bin/env python3
"""Empirical smoke test: can on-device Gemma 4 E2B/E4B actually *see* images?

Runs llama.cpp's `llama-mtmd-cli` over a matrix of (model variant × image ×
prompt) and prints what each model produced, with wall-clock timing. This is
the first-hand check the deep-research deferred (see memory
`tideline_vision_capability`): does the vision path work at all on this stack,
and is the OCR / scene-gist quality good enough to drive Tideline's episodic
"warm" index?

Two prompts mirror the product's dual goal:
  - translate : OCR + translate visible text  (the "image has text" path)
  - scene     : one-line scene gist + 3 objects (the "textless image" path)

Requires the llama.cpp multimodal CLI (brew install llama.cpp), the two LM
GGUFs in models/, and the matching mmproj files in models/vision-e2b|e4b/.

Usage:
  python scripts/vision_smoke.py --gen-sample             # synth JP menu image
  python scripts/vision_smoke.py                          # run full matrix
  python scripts/vision_smoke.py --image ramen.jpg sky.jpg  # add real photos
  python scripts/vision_smoke.py --variant E4B            # one model only

Env knobs:
  TIDELINE_MTMD_BIN  path to llama-mtmd-cli (default: PATH / homebrew)
  TIDELINE_MTMD_NGL  GPU layers (default 0 = CPU; try 99 for Metal once stable)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODELS = REPO / "models"
ASSETS = REPO / "scripts" / "vision_smoke_assets"

VARIANTS = {
    "E2B": (MODELS / "gemma-4-E2B-it-Q4_K_M.gguf", MODELS / "vision-e2b" / "mmproj-F16.gguf"),
    "E4B": (MODELS / "gemma-4-E4B-it-Q4_K_M.gguf", MODELS / "vision-e4b" / "mmproj-F16.gguf"),
}

PROMPTS = {
    "translate": (
        "Read every piece of text visible in this image and translate it into "
        "English. List each original line followed by its English translation."
    ),
    "scene": (
        "Describe this scene in one short sentence, then list the three most "
        "prominent objects you can see. Be concise."
    ),
}


def find_bin() -> str:
    cand = os.environ.get("TIDELINE_MTMD_BIN") or shutil.which("llama-mtmd-cli")
    if not cand:
        for p in ("/opt/homebrew/bin/llama-mtmd-cli", "/usr/local/bin/llama-mtmd-cli"):
            if Path(p).exists():
                cand = p
                break
    if not cand or not Path(cand).exists():
        sys.exit(
            "llama-mtmd-cli not found. Install with `brew install llama.cpp`, "
            "or set TIDELINE_MTMD_BIN to its path."
        )
    return cand


def gen_sample() -> Path:
    """Render a synthetic Japanese ramen-shop menu — a clean CJK OCR target."""
    from PIL import Image, ImageDraw, ImageFont

    ASSETS.mkdir(parents=True, exist_ok=True)
    out = ASSETS / "jp_menu_synth.png"
    W, H = 720, 900
    img = Image.new("RGB", (W, H), (250, 247, 240))
    d = ImageDraw.Draw(img)
    font_path = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
    big = ImageFont.truetype(font_path, 64)
    mid = ImageFont.truetype(font_path, 40)
    small = ImageFont.truetype(font_path, 30)

    d.text((W // 2, 70), "風雲児", font=big, fill=(40, 30, 25), anchor="mm")
    d.text((W // 2, 140), "ラーメン専門店", font=mid, fill=(60, 50, 45), anchor="mm")
    d.text((W // 2, 195), "営業 11:00 - 23:00  新宿西口", font=small, fill=(90, 80, 75), anchor="mm")
    d.line((60, 240, W - 60, 240), fill=(180, 120, 60), width=3)

    items = [
        ("特製ラーメン", "￥1180"),
        ("ラーメン", "￥980"),
        ("つけ麺", "￥1050"),
        ("醤油ラーメン", "￥900"),
        ("餃子 (6個)", "￥450"),
        ("お会計はレジで", ""),
    ]
    y = 310
    for name, price in items:
        d.text((80, y), name, font=mid, fill=(40, 35, 30), anchor="lm")
        if price:
            d.text((W - 80, y), price, font=mid, fill=(40, 35, 30), anchor="rm")
        y += 95
    img.save(out)
    print(f"wrote {out}")
    return out


def run_one(bin_path: str, lm: Path, mmproj: Path, image: Path, prompt: str, ngl: int) -> tuple[str, float]:
    cmd = [
        bin_path,
        "-m", str(lm),
        "--mmproj", str(mmproj),
        "--image", str(image),
        "-p", prompt,
        "--jinja",  # Gemma 4's embedded chat template requires the jinja path
        "-ngl", str(ngl),
        "--temp", "0.2",
        "-n", "512",
    ]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    dt = time.time() - t0
    out = proc.stdout.strip()
    if not out and proc.returncode != 0:
        out = f"[exit {proc.returncode}] " + proc.stderr.strip()[-800:]
    return out, dt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen-sample", action="store_true", help="only generate the synthetic JP menu and exit")
    ap.add_argument("--image", nargs="*", default=[], help="extra real image paths to test")
    ap.add_argument("--variant", choices=list(VARIANTS), help="restrict to one model variant")
    ap.add_argument("--no-synth", action="store_true", help="skip the built-in synthetic menu image")
    ap.add_argument("--prompts", default=",".join(PROMPTS), help="comma list of prompt keys to run (translate,scene)")
    args = ap.parse_args()

    if args.gen_sample:
        gen_sample()
        return 0

    bin_path = find_bin()
    ngl = int(os.environ.get("TIDELINE_MTMD_NGL", "0"))

    images = []
    if not args.no_synth:
        synth = ASSETS / "jp_menu_synth.png"
        if not synth.exists():
            synth = gen_sample()
        images.append(synth)
    images.extend(Path(p) for p in args.image)

    sel_prompts = {k: PROMPTS[k] for k in args.prompts.split(",") if k in PROMPTS}
    variants = {args.variant: VARIANTS[args.variant]} if args.variant else VARIANTS

    # Preflight: every required file present?
    for name, (lm, mmproj) in variants.items():
        for f in (lm, mmproj):
            if not f.exists():
                sys.exit(f"missing for {name}: {f}")

    print(f"bin={bin_path}  ngl={ngl}  images={[i.name for i in images]}\n")
    for name, (lm, mmproj) in variants.items():
        for image in images:
            if not image.exists():
                print(f"!! missing image {image}, skipping")
                continue
            for pkey, prompt in sel_prompts.items():
                print(f"━━━ {name} · {image.name} · {pkey} ━━━")
                out, dt = run_one(bin_path, lm, mmproj, image, prompt, ngl)
                print(out)
                print(f"   ⏱ {dt:.1f}s\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
