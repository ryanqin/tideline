"""A1 — Translate a single word or short phrase to a target language.

The simplest translation atom: input is one term, output should be exactly
the reference translation (case-insensitive, punctuation-stripped). Any
preamble like "the translation is" fails this atom (a side-effect; A5
isolates preamble specifically).
"""

from __future__ import annotations

import re
import unicodedata


ID = "A1"
NAME = "Translate word/phrase"
CATEGORY = "tier_a"

SYSTEM_PROMPT = (
    "You are a precise translator. Respond with only the translation — "
    "no preamble, no explanation, no quotation marks."
)


CASES = [
    {"original": "ラーメン", "target_lang": "English", "reference": "ramen"},
    {"original": "駅", "target_lang": "English", "reference": "station"},
    {"original": "beurre", "target_lang": "English", "reference": "butter"},
    {"original": "œuf", "target_lang": "English", "reference": "egg"},
    {"original": "amor", "target_lang": "English", "reference": "love"},
    {"original": "corazón", "target_lang": "English", "reference": "heart"},
    {"original": "合同", "target_lang": "English", "reference": "contract"},
    {"original": "会议", "target_lang": "English", "reference": "meeting"},
    {"original": "Datenbank", "target_lang": "English", "reference": "database"},
    {"original": "Server", "target_lang": "English", "reference": "server"},
    {"original": "hello", "target_lang": "Chinese", "reference": "你好"},
    {"original": "thank you", "target_lang": "Japanese", "reference": "ありがとう"},
]


_PUNCT = re.compile(r"[\.\,\!\?\;\:\'\"\(\)\[\]\{\}。、！？]+")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = _PUNCT.sub("", text)
    return " ".join(text.split())


def build_prompt(case: dict) -> str:
    return f"Translate '{case['original']}' to {case['target_lang']}."


def evaluate(case: dict, response: str) -> bool:
    return _normalize(response) == _normalize(case["reference"])
