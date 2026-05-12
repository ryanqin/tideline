"""B3 — Does this English term have multiple distinct meanings in isolation?

If the agent can reliably flag ambiguity, future Tier B can attach
alternative-meaning hints to drawers, letting the user see "this could
be the oven sense OR the number sense" rather than guessing.
"""

from __future__ import annotations


ID = "B3"
NAME = "Ambiguity detection (binary)"
CATEGORY = "tier_b"

SYSTEM_PROMPT = (
    "You answer with exactly one word: 'yes' or 'no'. No other text."
)


CASES = [
    {"word": "bank", "expected": "yes"},        # river vs financial
    {"word": "bow", "expected": "yes"},         # weapon vs greeting vs ribbon
    {"word": "table", "expected": "yes"},       # furniture vs data
    {"word": "spring", "expected": "yes"},      # season vs coil vs water source
    {"word": "match", "expected": "yes"},       # fire vs pairing vs sport
    {"word": "letter", "expected": "yes"},      # alphabet vs mail
    {"word": "elephant", "expected": "no"},
    {"word": "telescope", "expected": "no"},
    {"word": "kindergarten", "expected": "no"},
    {"word": "philosophy", "expected": "no"},
    {"word": "ramen", "expected": "no"},
    {"word": "submarine", "expected": "no"},
]


def build_prompt(case: dict) -> str:
    return (
        f"Does the English word '{case['word']}' have multiple distinct "
        f"unrelated meanings when read in isolation (no context)?"
    )


def evaluate(case: dict, response: str) -> bool:
    low = response.lower().strip()
    has_yes = "yes" in low.split()
    has_no = "no" in low.split()
    if has_yes and has_no:
        return False
    if low.startswith("yes") or has_yes:
        return case["expected"] == "yes"
    if low.startswith("no") or has_no:
        return case["expected"] == "no"
    return False
