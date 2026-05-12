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
    # Reuse the concept_match parser — same yes/no shape, same hedged-
    # answer behavior. parse_response returns None for ambiguous answers
    # (like "yes and no"), which here means the model didn't comply.
    from tideline.intelligence import concept_match

    parsed = concept_match.parse_response(response)
    if parsed is None:
        return False
    return (parsed is True) == (case["expected"] == "yes")
