"""B6 — Generate an episodically-anchored title for a group of translations.

The defining atom for Tideline's memory-anchor product principle
(DESIGN.md §3.2). Generic categorical naming ("Japanese food") fails;
we want lived, episodic naming ("your Tokyo lunches", "a Sunday recipe
session"). The cases include `context_snippet` hints so the model has
material to anchor with — not just the terms in isolation.

Eval: response must contain at least one episodic-hook token (a place,
time, activity, or specific situation cue). Generic taxonomy tokens
("words", "vocabulary", "items", "Japanese") alone are not enough.
"""

from __future__ import annotations


ID = "B6"
NAME = "Episodic title (memory-anchored)"
CATEGORY = "tier_b"

SYSTEM_PROMPT = (
    "Generate a 3-7 word episodic title that captures the lived moment "
    "behind a group of translations. Be specific about place, time, or "
    "activity — not generic categories. Output only the title, no preamble."
)


CASES = [
    {
        "items": [
            {"term": "ラーメン", "context": "menu at Ichiran in Shibuya"},
            {"term": "寿司", "context": "menu at conveyor sushi, Tokyo"},
            {"term": "天ぷら", "context": "menu, Tokyo restaurant district"},
            {"term": "お会計", "context": "asking for the bill, Tokyo dinner"},
        ],
        "episodic_tokens": ["tokyo", "japan", "trip", "dinner", "lunch",
                            "restaurant", "menu", "eating", "outing"],
    },
    {
        "items": [
            {"term": "beurre", "context": "recipe step, baking croissants"},
            {"term": "œuf", "context": "ingredient list, weekend baking"},
            {"term": "préchauffer", "context": "oven step, Sunday recipe"},
            {"term": "battre", "context": "egg whites step, baking"},
        ],
        "episodic_tokens": ["baking", "recipe", "weekend", "sunday",
                            "kitchen", "cooking", "session", "croissant"],
    },
    {
        "items": [
            {"term": "合同", "context": "Beijing client meeting"},
            {"term": "签字", "context": "contract signing, Beijing trip"},
            {"term": "汇报", "context": "weekly report, business trip"},
            {"term": "决策", "context": "decision discussion, Beijing office"},
        ],
        "episodic_tokens": ["beijing", "business", "trip", "office",
                            "meeting", "client", "deal"],
    },
    {
        "items": [
            {"term": "Datenbank", "context": "incident postmortem doc"},
            {"term": "Fehlermeldung", "context": "error log analysis"},
            {"term": "Verbindung", "context": "connection issue debug"},
            {"term": "Schlüssel", "context": "auth key rotation"},
        ],
        "episodic_tokens": ["debug", "incident", "outage", "postmortem",
                            "ops", "engineer", "german tech", "troubleshoot"],
    },
    {
        "items": [
            {"term": "amor", "context": "song lyric"},
            {"term": "corazón", "context": "ballad chorus"},
            {"term": "sin ti", "context": "song title fragment"},
            {"term": "siempre", "context": "lyric line"},
        ],
        "episodic_tokens": ["lyric", "song", "ballad", "music",
                            "listening", "spanish music", "latin", "playlist"],
    },
]


def build_prompt(case: dict) -> str:
    lines = []
    for item in case["items"]:
        lines.append(f"  - '{item['term']}' — encountered: {item['context']}")
    items_text = "\n".join(lines)
    return (
        f"These translations were encountered together. Generate a 3-7 word "
        f"title that captures their shared episodic moment (place, time, "
        f"activity):\n{items_text}"
    )


def evaluate(case: dict, response: str) -> bool:
    low = response.lower()
    return any(token in low for token in case["episodic_tokens"])
