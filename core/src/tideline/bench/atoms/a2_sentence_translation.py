"""A2 — Translate a full sentence.

Strictness drops one notch from A1: sentences admit phrasing variation,
so we use chrF >= 40 as the pass threshold rather than exact match.
chrF is robust across morphology and script; 40 corresponds to clearly
related output (random text scores ~0-10, near-perfect ~80+).
"""

from __future__ import annotations


ID = "A2"
NAME = "Translate sentence"
CATEGORY = "tier_a"

SYSTEM_PROMPT = (
    "You are a precise translator. Respond with only the translation — "
    "no preamble, no explanation, no quotation marks."
)


CASES = [
    {"original": "お会計をお願いします", "target_lang": "English",
     "reference": "Could I have the bill, please?"},
    {"original": "駅はどこですか", "target_lang": "English",
     "reference": "Where is the station?"},
    {"original": "Préchauffer le four à 180 degrés.", "target_lang": "English",
     "reference": "Preheat the oven to 180 degrees."},
    {"original": "Battre les œufs en neige.", "target_lang": "English",
     "reference": "Beat the egg whites until stiff."},
    {"original": "No puedo vivir sin ti.", "target_lang": "English",
     "reference": "I cannot live without you."},
    {"original": "Mi corazón es tuyo.", "target_lang": "English",
     "reference": "My heart is yours."},
    {"original": "合同需要签字。", "target_lang": "English",
     "reference": "The contract needs to be signed."},
    {"original": "请准时到达。", "target_lang": "English",
     "reference": "Please arrive on time."},
    {"original": "Die Datenbank ist verbunden.", "target_lang": "English",
     "reference": "The database is connected."},
    {"original": "Die Datei wurde nicht gefunden.", "target_lang": "English",
     "reference": "The file was not found."},
]

_CHRF_THRESHOLD = 40.0


def build_prompt(case: dict) -> str:
    return f"Translate the following to {case['target_lang']}: {case['original']}"


def evaluate(case: dict, response: str) -> bool:
    from sacrebleu import sentence_chrf

    if not response.strip():
        return False
    score = sentence_chrf(response, [case["reference"]]).score
    return score >= _CHRF_THRESHOLD
