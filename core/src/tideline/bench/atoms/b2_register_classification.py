"""B2 — Classify a term's register: menu / sign / conversation / formal.

If this works, a background sweep can tag every drawer with a register
label, letting candidate surfacing be filtered ("show me menu terms
only"). Some cases are genuinely ambiguous (お会計 could be menu OR
conversation); we pick the most natural single label.
"""

from __future__ import annotations


ID = "B2"
NAME = "Register classification"
CATEGORY = "tier_b"

SYSTEM_PROMPT = (
    "Classify the register of the given term. Answer with exactly one "
    "word from the options provided, no other text."
)


CASES = [
    {"term": "ラーメン", "expected": "menu"},
    {"term": "寿司", "expected": "menu"},
    {"term": "beurre", "expected": "menu"},     # cooking → menu/recipe context
    {"term": "préchauffer", "expected": "menu"},
    {"term": "Datenbank", "expected": "formal"},
    {"term": "Versionskontrolle", "expected": "formal"},
    {"term": "合同", "expected": "formal"},
    {"term": "签字", "expected": "formal"},
    {"term": "STOP", "expected": "sign"},
    {"term": "出口", "expected": "sign"},
    {"term": "hello", "expected": "conversation"},
    {"term": "good morning", "expected": "conversation"},
]


_VALID = ("menu", "sign", "conversation", "formal")


def build_prompt(case: dict) -> str:
    return (
        f"Classify the typical usage register of this term: '{case['term']}'.\n"
        f"Options: menu, sign, conversation, formal.\n"
        f"Answer with exactly one of these four words."
    )


def evaluate(case: dict, response: str) -> bool:
    low = response.lower().strip()
    # Find which valid option appears first in the response
    first_match = min(
        ((low.find(opt), opt) for opt in _VALID if low.find(opt) != -1),
        default=(-1, None),
    )
    if first_match[0] == -1:
        return False
    return first_match[1] == case["expected"]
