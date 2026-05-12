"""B5 — Classify text complexity: word / phrase / sentence.

Used by the night-watch sweep to decide whether to apply word-level
processing (A1-style) or sentence-level (A2-style). If B5 is reliable,
the sweep can route automatically; if it's weak, we fall back to a
length-based heuristic.
"""

from __future__ import annotations


ID = "B5"
NAME = "Complexity tier classification"
CATEGORY = "tier_b"

SYSTEM_PROMPT = (
    "Classify text complexity. Answer with exactly one word: word, phrase, "
    "or sentence. No other text."
)


CASES = [
    {"text": "ramen", "expected": "word"},
    {"text": "Datenbank", "expected": "word"},
    {"text": "corazón", "expected": "word"},
    {"text": "preheat", "expected": "word"},
    {"text": "stiff egg whites", "expected": "phrase"},
    {"text": "rolling pin", "expected": "phrase"},
    {"text": "the bill, please", "expected": "phrase"},
    {"text": "version control", "expected": "phrase"},
    {"text": "Could I have the bill please?", "expected": "sentence"},
    {"text": "The contract needs to be signed.", "expected": "sentence"},
    {"text": "Preheat the oven to 180 degrees.", "expected": "sentence"},
    {"text": "I cannot live without you.", "expected": "sentence"},
]


_VALID = ("word", "phrase", "sentence")


def build_prompt(case: dict) -> str:
    return (
        f"Classify the complexity of this text: '{case['text']}'.\n"
        f"Options: word, phrase, sentence.\n"
        f"Answer with exactly one of these three words."
    )


def evaluate(case: dict, response: str) -> bool:
    low = response.lower().strip()
    first_match = min(
        ((low.find(opt), opt) for opt in _VALID if low.find(opt) != -1),
        default=(-1, None),
    )
    if first_match[0] == -1:
        return False
    return first_match[1] == case["expected"]
