"""B1 — Are these two terms about the same concept? (binary)

The atomic primitive for semantic clustering. If this works reliably,
a background sweep can ask it on O(N^2) pairs to build a similarity
graph; pairs with vote-accumulated affinity become a cluster. Cheap
weak signals + accumulation → cluster emergence.

Prompt construction and response parsing live in
`tideline.intelligence.concept_match` so the bench measures the exact
prompts the cluster engine (`tideline.cluster`) uses in production.
"""

from __future__ import annotations

from tideline.intelligence import concept_match


ID = "B1"
NAME = "Concept match (binary)"
CATEGORY = "tier_b"

SYSTEM_PROMPT = concept_match.SYSTEM_PROMPT


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
    return concept_match.build_prompt(t1, l1, t2, l2)


def evaluate(case: dict, response: str) -> bool:
    parsed = concept_match.parse_response(response)
    if parsed is None:
        return False
    expected_yes = case["expected"] == "yes"
    return parsed == expected_yes
