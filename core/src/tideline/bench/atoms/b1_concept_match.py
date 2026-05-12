"""B1 — Are these two terms about the same concept? (binary)

The atomic primitive for semantic clustering. If this works reliably,
a background sweep can ask it on O(N^2) pairs to build a similarity
graph; pairs with vote-accumulated affinity become a cluster. Cheap
weak signals + accumulation → cluster emergence.

Eval: parse first yes/no token from response.
"""

from __future__ import annotations


ID = "B1"
NAME = "Concept match (binary)"
CATEGORY = "tier_b"

SYSTEM_PROMPT = (
    "You answer with exactly one word: 'yes' or 'no'. No other text."
)


CASES = [
    # Same concept across languages
    {"term1": ("love", "English"), "term2": ("amor", "Spanish"), "expected": "yes"},
    {"term1": ("ramen", "English"), "term2": ("ラーメン", "Japanese"), "expected": "yes"},
    {"term1": ("egg", "English"), "term2": ("œuf", "French"), "expected": "yes"},
    {"term1": ("database", "English"), "term2": ("Datenbank", "German"), "expected": "yes"},
    {"term1": ("station", "English"), "term2": ("駅", "Japanese"), "expected": "yes"},
    {"term1": ("meeting", "English"), "term2": ("会议", "Chinese"), "expected": "yes"},
    # Same language, near-synonyms
    {"term1": ("ramen", "English"), "term2": ("noodle soup", "English"), "expected": "yes"},
    # Different concepts
    {"term1": ("love", "English"), "term2": ("heart", "English"), "expected": "no"},
    {"term1": ("station", "English"), "term2": ("subway", "English"), "expected": "no"},
    {"term1": ("contract", "English"), "term2": ("budget", "English"), "expected": "no"},
    {"term1": ("ramen", "English"), "term2": ("sushi", "English"), "expected": "no"},
    {"term1": ("database", "English"), "term2": ("application", "English"), "expected": "no"},
]


def build_prompt(case: dict) -> str:
    t1, l1 = case["term1"]
    t2, l2 = case["term2"]
    return (
        f"Are these two terms referring to the same concept?\n"
        f"1. '{t1}' ({l1})\n"
        f"2. '{t2}' ({l2})"
    )


def evaluate(case: dict, response: str) -> bool:
    low = response.lower().strip()
    has_yes = "yes" in low.split()
    has_no = "no" in low.split()
    # Hedged or contradictory ("yes and no") doesn't count as a clean answer.
    if has_yes and has_no:
        return False
    if low.startswith("yes") or has_yes:
        return case["expected"] == "yes"
    if low.startswith("no") or has_no:
        return case["expected"] == "no"
    return False
