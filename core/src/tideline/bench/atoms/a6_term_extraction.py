"""A6 — Extract the main translatable term from a noisy snippet.

Future image / audio pipelines will hand the agent OCR output ("ラーメン
850円 とんこつ") or transcript fragments. The agent needs to pick out the
**translatable term**, not the price or measurement. This atom measures
that selection ability, with plenty of room for engineering to sharpen
prompts.

Lenient eval: response contains the expected term as a substring.

Known weakness, documented rather than hidden: the expected term sits inside
the snippet, and the snippet sits inside the prompt, so **any reply that
echoes the prompt scores a hit**. Mock does exactly that and lands 10/10 — the
line that used to sit here, "Mock can't do it", was measurably false. The
mock-baseline gate in tests/test_bench_atoms.py pins that 100% in place so it
stays a known constant instead of becoming a surprise. Tightening the judge
would move real-model scores too, so that is a re-measurement to run on
purpose, not a tidy-up to slip in alongside something else.
"""

from __future__ import annotations


ID = "A6"
NAME = "Extract translatable term"
CATEGORY = "tier_a"

SYSTEM_PROMPT = (
    "You are a precise term extractor. From a noisy text snippet (OCR or "
    "transcript), identify the single most likely term the user wants "
    "translated. Output only that term, no other text."
)


CASES = [
    {"snippet": "ラーメン 850円", "expected": "ラーメン"},
    {"snippet": "とんこつラーメン ¥980 (tax incl.)", "expected": "とんこつラーメン"},
    {"snippet": "Beurre demi-sel — 250g", "expected": "Beurre"},
    {"snippet": "Préchauffer le four à 180 degrés", "expected": "Préchauffer"},
    {"snippet": "合同金额: ¥50000", "expected": "合同"},
    {"snippet": "会议时间: 周一上午 10:00", "expected": "会议"},
    {"snippet": "Datenbank-Verbindung fehlgeschlagen (Error 1042)", "expected": "Datenbank"},
    {"snippet": "Server Status: ONLINE", "expected": "Server"},
    {"snippet": "Te amo ❤️ siempre", "expected": "Te amo"},
    {"snippet": "Sin ti — Luis Miguel (1993)", "expected": "Sin ti"},
]


def build_prompt(case: dict) -> str:
    return (
        f"From this snippet, extract the single most translatable term: "
        f"'{case['snippet']}'"
    )


def evaluate(case: dict, response: str) -> bool:
    return case["expected"].lower() in response.lower()
