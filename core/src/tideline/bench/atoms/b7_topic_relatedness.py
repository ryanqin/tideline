"""B7 — Do two terms belong to the same theme? (binary)

The primitive for thematic clustering ("your Tokyo lunches"). Where B1 asks
"same concept?" (clusters synonyms), B7 asks "same theme?" (clusters related-
but-different terms). The hard part is granularity: same-cuisine yes, cross-
cuisine no — otherwise "both food" collapses every dish into one cluster.

Prompt + parser live in `tideline.intelligence.relatedness` so the bench
measures the exact prompt the thematic cluster engine will run.

Note: CASES are kept disjoint from the few-shot pairs baked into the prompt
(sushi/ramen, sushi/croissant, contract/meeting, meeting/sushi) — scoring on
the shots would inflate the number.
"""

from __future__ import annotations

from tideline.intelligence import relatedness


ID = "B7"
NAME = "Topic relatedness (binary)"
CATEGORY = "tier_b"

SYSTEM_PROMPT = relatedness.SYSTEM_PROMPT


CASES = [
    # --- same theme (yes) ---
    {"term1": "ramen", "term2": "udon", "expected": "yes"},          # Japanese
    {"term1": "tempura", "term2": "sushi", "expected": "yes"},       # Japanese
    {"term1": "butter", "term2": "flour", "expected": "yes"},        # baking
    {"term1": "egg", "term2": "butter", "expected": "yes"},          # baking
    {"term1": "meeting", "term2": "budget", "expected": "yes"},      # office
    {"term1": "contract", "term2": "budget", "expected": "yes"},     # office
    {"term1": "database", "term2": "server", "expected": "yes"},     # tech
    {"term1": "server", "term2": "application", "expected": "yes"},  # tech
    {"term1": "合同", "term2": "会议", "expected": "yes"},            # business (zh)
    {"term1": "会议", "term2": "budget", "expected": "yes"},          # office (cross-lang)
    {"term1": "ラーメン", "term2": "寿司", "expected": "yes"},        # Japanese (cross-lang)
    # --- different theme (no) ---
    {"term1": "ramen", "term2": "database", "expected": "no"},       # food vs tech
    {"term1": "sushi", "term2": "budget", "expected": "no"},         # food vs office
    {"term1": "tempura", "term2": "contract", "expected": "no"},     # food vs office
    {"term1": "heart", "term2": "server", "expected": "no"},         # body vs tech
    {"term1": "flour", "term2": "meeting", "expected": "no"},        # baking vs office
    {"term1": "合同", "term2": "寿司", "expected": "no"},            # business vs food (cross-lang)
    {"term1": "ラーメン", "term2": "Datenbank", "expected": "no"},   # food vs tech (cross-lang)
    # --- cross-cuisine: the granularity test (no — "both food" isn't enough) ---
    {"term1": "ramen", "term2": "butter", "expected": "no"},         # Japanese vs baking
    {"term1": "udon", "term2": "egg", "expected": "no"},             # Japanese vs baking
    {"term1": "sushi", "term2": "flour", "expected": "no"},          # Japanese vs baking
    {"term1": "tempura", "term2": "croissant", "expected": "no"},    # Japanese vs French
    # --- second batch: built as held-out to validate prompt iteration, then
    # folded in for a more robust sample (still disjoint from the few-shot) ---
    {"term1": "latte", "term2": "espresso", "expected": "yes"},      # coffee
    {"term1": "invoice", "term2": "payroll", "expected": "yes"},     # office
    {"term1": "kimchi", "term2": "bibimbap", "expected": "yes"},     # Korean
    {"term1": "login", "term2": "password", "expected": "yes"},      # security
    {"term1": "地铁", "term2": "车站", "expected": "yes"},            # transit (zh)
    {"term1": "pho", "term2": "spring roll", "expected": "yes"},     # Vietnamese
    {"term1": "novel", "term2": "poem", "expected": "yes"},          # literature
    {"term1": "pasta", "term2": "login", "expected": "no"},          # food vs tech
    {"term1": "kimchi", "term2": "invoice", "expected": "no"},       # food vs office
    {"term1": "latte", "term2": "password", "expected": "no"},       # coffee vs tech
    {"term1": "pho", "term2": "butter", "expected": "no"},           # Vietnamese vs baking
    {"term1": "taco", "term2": "sushi", "expected": "no"},           # Mexican vs Japanese
    {"term1": "地铁", "term2": "寿司", "expected": "no"},            # transit vs food (cross-lang)
    {"term1": "novel", "term2": "server", "expected": "no"},         # literature vs tech
]


def build_prompt(case: dict) -> str:
    return relatedness.build_prompt(case["term1"], case["term2"])


def evaluate(case: dict, response: str) -> bool:
    parsed = relatedness.parse_response(response)
    if parsed is None:
        return False
    return parsed == (case["expected"] == "yes")
