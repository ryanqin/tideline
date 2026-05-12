"""A5 — Output discipline: no preamble, no commentary, just the answer.

The system prompt explicitly instructs no preamble; the user prompt is a
plain translation request without re-emphasizing the rule. Pass = the
model's response contains zero of a list of common preamble phrases.

This atom is **diagnostic for the system-message lever**: if A5 is low
but A1 is high (where A1's prompt re-states the rule), the system message
isn't holding on its own. If A5 is also high, the system prompt has bite.
"""

from __future__ import annotations


ID = "A5"
NAME = "Output discipline (no preamble)"
CATEGORY = "tier_a"

SYSTEM_PROMPT = (
    "You are a translation engine. Output only the translated text — "
    "no preamble, no explanation, no commentary, no markdown formatting."
)


CASES = [
    {"original": "hello", "target_lang": "Chinese"},
    {"original": "thank you", "target_lang": "Japanese"},
    {"original": "good morning", "target_lang": "French"},
    {"original": "where is the bathroom", "target_lang": "Spanish"},
    {"original": "the contract is ready", "target_lang": "German"},
    {"original": "ラーメン", "target_lang": "English"},
    {"original": "beurre", "target_lang": "English"},
    {"original": "合同", "target_lang": "English"},
    {"original": "corazón", "target_lang": "English"},
    {"original": "Datenbank", "target_lang": "English"},
]


_FORBIDDEN_PHRASES = (
    "here's the translation",
    "here is the translation",
    "the translation is",
    "translation:",
    "translated:",
    "i'll translate",
    "i will translate",
    "in english:",
    "in chinese:",
    "in japanese:",
    "in french:",
    "in spanish:",
    "in german:",
    "in english,",
    "sure,",
    "of course",
    "certainly",
)


def build_prompt(case: dict) -> str:
    # No instruction repeats inside the user prompt — discipline must come
    # from the system message alone.
    return f"Translate '{case['original']}' to {case['target_lang']}."


def evaluate(case: dict, response: str) -> bool:
    low = response.lower()
    return not any(phrase in low for phrase in _FORBIDDEN_PHRASES)
