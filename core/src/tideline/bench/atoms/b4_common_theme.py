"""B4 — Given a small group of terms, name their common theme.

A precursor to B6 (episodic title) — this measures generic theme
extraction, no episodic context required. If B4 is strong but B6 is
weak, the gap is specifically about episodic-grounded naming, not
about pattern recognition.

Eval: response (lowercased) must contain at least one of the expected
theme tokens.
"""

from __future__ import annotations


ID = "B4"
NAME = "Common theme (3 terms)"
CATEGORY = "tier_b"

SYSTEM_PROMPT = (
    "Identify the common theme of the given terms in 2-5 words. "
    "No preamble, no explanation, just the theme."
)


CASES = [
    {"terms": ["ラーメン", "寿司", "天ぷら"],
     "theme_tokens": ["japanese", "japan", "food", "cuisine"]},
    {"terms": ["beurre", "œuf", "farine"],
     "theme_tokens": ["french", "cooking", "baking", "ingredient", "cuisine"]},
    {"terms": ["合同", "会议", "项目", "提案"],
     "theme_tokens": ["business", "chinese", "office", "work", "corporate"]},
    {"terms": ["Datenbank", "Server", "Schnittstelle", "Verbindung"],
     "theme_tokens": ["tech", "computing", "software", "german", "it"]},
    {"terms": ["amor", "corazón", "sin ti", "siempre"],
     "theme_tokens": ["love", "spanish", "romantic", "romance"]},
    {"terms": ["駅", "地下鉄", "つけ麺"],
     "theme_tokens": ["japan", "tokyo", "travel", "japanese"]},
    {"terms": ["preheat", "yolk", "rolling pin"],
     "theme_tokens": ["bak", "cook", "kitchen"]},
    {"terms": ["contract", "budget", "proposal"],
     "theme_tokens": ["business", "office", "work", "corporate"]},
    {"terms": ["bank", "letter", "table"],
     "theme_tokens": ["ambigu", "polysem", "multiple"]},  # ambiguous words theme
    {"terms": ["telescope", "submarine", "elephant"],
     "theme_tokens": ["noun", "unrelat", "concrete", "object"]},
]


def build_prompt(case: dict) -> str:
    items = ", ".join(f"'{t}'" for t in case["terms"])
    return f"What is the common theme of these terms? {items}"


def evaluate(case: dict, response: str) -> bool:
    low = response.lower()
    return any(token in low for token in case["theme_tokens"])
