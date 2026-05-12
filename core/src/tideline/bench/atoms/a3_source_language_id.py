"""A3 — Identify the source language of a snippet.

Lenient eval: the response matches if it contains either the language name
or its ISO code, case-insensitive. The model may answer "Japanese" or "ja"
or "日本語" — all acceptable. This is the kind of operation a background
sweep might invoke 1000s of times to tag drawer rows that lack `source`.
"""

from __future__ import annotations


ID = "A3"
NAME = "Identify source language"
CATEGORY = "tier_a"

SYSTEM_PROMPT = (
    "You are a precise language identifier. Respond with only the language "
    "name in English, no preamble."
)


CASES = [
    {"text": "ラーメン", "expected": ["japanese", "ja"]},
    {"text": "お会計をお願いします", "expected": ["japanese", "ja"]},
    {"text": "beurre", "expected": ["french", "fr"]},
    {"text": "Préchauffer le four", "expected": ["french", "fr"]},
    {"text": "corazón", "expected": ["spanish", "es"]},
    {"text": "Te amo", "expected": ["spanish", "es"]},
    {"text": "合同", "expected": ["chinese", "zh", "mandarin"]},
    {"text": "我们什么时候开会", "expected": ["chinese", "zh", "mandarin"]},
    {"text": "Datenbank", "expected": ["german", "de"]},
    {"text": "Die Verbindung wurde unterbrochen", "expected": ["german", "de"]},
    {"text": "hello world", "expected": ["english", "en"]},
    {"text": "ciao bella", "expected": ["italian", "it"]},
]


def build_prompt(case: dict) -> str:
    return f"What language is this text written in? '{case['text']}'"


def evaluate(case: dict, response: str) -> bool:
    norm = response.lower().strip()
    return any(token in norm for token in case["expected"])
