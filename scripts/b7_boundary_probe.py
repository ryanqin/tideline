"""B7 relatedness — boundary probe (increment 3, theme line).

Two parts, run against a real Gemma runtime:
  1. BENCH — the existing 36-case b7 set: accuracy + which categories miss
     (model-choice data: E2B loose vs E4B clean).
  2. PROBE — the *product's actual* single-language vocabulary (the Tokyo
     seed's Japanese terms), grouped by question type, to read the model's
     NATURAL granularity. The crux is "cross-scene, same cuisine"
     (ラーメン[ramen alley] vs 寿司[sushi morning]): yes => cuisine-level (all
     Japanese food collapses to one theme), no => scene-level is reachable.

Not a committed test — an experiment to let the data tell us the boundary.

Run:
  TIDELINE_GEMMA_PATH=models/gemma-4-E4B-it-Q4_K_M.gguf \
  TIDELINE_GEMMA_GPU_LAYERS=0 PYTHONPATH=core/src \
  python3 scripts/b7_boundary_probe.py
"""

from __future__ import annotations

import os
import sys

from tideline.bench.atoms import b7_topic_relatedness as b7
from tideline.bench.atoms.runner import _direct_generate
from tideline.intelligence import relatedness
from tideline.runtimes import get_runtime


def _vote(runtime, t1: str, t2: str):
    out = _direct_generate(runtime, relatedness.SYSTEM_PROMPT,
                           relatedness.build_prompt(t1, t2))
    return relatedness.parse_response(out), out.replace("\n", " ")[:40]


# Product vocabulary = the Tokyo seed's Japanese terms, grouped by the scene
# they were captured in. The probe asks: does the model's relatedness split
# these scenes (scene-level) or merge them as "Japanese food" (cuisine-level)?
PROBE = {
    "transit internal (expect yes)": [
        ("駅", "地下鉄"), ("地下鉄", "メトロ"), ("駅", "切符"),
    ],
    "ramen-alley internal": [
        ("ラーメン", "餃子"), ("ラーメン", "つけ麺"), ("餃子", "生ビール"),
    ],
    "izakaya internal": [
        ("刺身", "焼き鳥"), ("焼き鳥", "枝豆"), ("枝豆", "醤油"),
    ],
    "CRUX: cross food-scene, same cuisine": [
        ("ラーメン", "寿司"), ("ラーメン", "刺身"),
        ("餃子", "寿司"), ("ラーメン", "焼き鳥"),
    ],
    "cross domain food vs transit (expect no)": [
        ("ラーメン", "駅"), ("寿司", "地下鉄"), ("醤油", "切符"),
    ],
}


def run_bench(runtime) -> None:
    by_cat = {}
    correct = 0
    for case in b7.CASES:
        parsed, raw = _vote(runtime, case["term1"], case["term2"])
        ok = parsed is not None and parsed == (case["expected"] == "yes")
        correct += ok
        # crude category from the inline comment grouping
        cat = case["expected"]
        by_cat.setdefault(cat, [0, 0])
        by_cat[cat][0] += ok
        by_cat[cat][1] += 1
        if not ok:
            got = {True: "yes", False: "no", None: "??"}[parsed]
            print(f"   MISS {case['term1']}/{case['term2']} "
                  f"exp={case['expected']} got={got} «{raw}»")
    print(f"\nBENCH b7: {correct}/{len(b7.CASES)} = {correct/len(b7.CASES):.0%}")
    for cat, (c, n) in by_cat.items():
        print(f"   expected={cat}: {c}/{n}")


def run_probe(runtime) -> None:
    print("\n=== PROBE: natural granularity on the seed's Japanese vocab ===")
    for group, pairs in PROBE.items():
        print(f"\n[{group}]")
        for t1, t2 in pairs:
            parsed, raw = _vote(runtime, t1, t2)
            verdict = {True: "YES", False: "no ", None: "?? "}[parsed]
            print(f"   {verdict}  {t1} ~ {t2}   «{raw}»")


def main() -> int:
    path = os.environ.get("TIDELINE_GEMMA_PATH", "?")
    print(f"model: {path}  (gpu_layers={os.environ.get('TIDELINE_GEMMA_GPU_LAYERS','0')})")
    runtime = get_runtime("llama_cpp")
    print("=== BENCH: existing 36-case b7 set (misses shown) ===")
    run_bench(runtime)
    run_probe(runtime)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
