"""A6 — Extract the main translatable term from a noisy snippet.

Future image / audio pipelines will hand the agent OCR output ("ラーメン
850円 とんこつ") or transcript fragments. The agent needs to pick out the
**translatable term**, not the price or measurement. This atom measures
that selection ability, with plenty of room for engineering to sharpen
prompts.

Lenient eval: response contains the expected term as a substring.

The leniency is load-bearing, and it took a measurement to find out why.

The judge is permeable in principle: the expected term sits inside the
snippet, the snippet sits inside the prompt, so any reply that echoes the
prompt scores a hit. Mock does exactly that and lands 10/10 — the line that
used to sit here, "Mock can't do it", was measurably false.

The obvious next thought is that real models must be exploiting it too, and
that the 50-90% figures are soft. They are not, and looking at the answers
says why. Scoring the same responses under a stricter judge — must contain the
term AND none of the snippet's other content words, i.e. must have *selected*
— drops E2B 5→3 and E4B 9→5. But every single divergence is one shape:

    gold `Beurre`     model `Beurre demi-sel`        (Beurre demi-sel — 250g)
    gold `合同`        model `合同金额`                (合同金额: ¥50000)
    gold `会议`        model `会议时间`                (会议时间: 周一上午 10:00)
    gold `Datenbank`  model `Datenbank-Verbindung`   (Datenbank-Verbindung fehl…)

Not regurgitation — a longer noun phrase containing the gold, and in each case
arguably the better answer. `Beurre demi-sel` is the product; `Beurre` is just
"butter". `Datenbank-Verbindung` is the compound; `Datenbank` is half of it.

So the gold span is one defensible choice among several, and the lenient judge
is what absorbs that. Tightening it would stop measuring "did it extract the
term" and start measuring "did it pick my span", which is a worse question. It
stays lenient on purpose. The mock-baseline gate in tests/test_bench_atoms.py
pins mock's 100% so the permeability stays a known constant rather than
becoming a surprise later.
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
