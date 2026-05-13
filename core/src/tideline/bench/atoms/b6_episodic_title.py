"""B6 — Generate an episodically-anchored title for a group of translations.

The defining atom for Tideline's memory-anchor product principle
(DESIGN.md §3.2). Generic categorical naming ("Japanese food") fails;
we want lived, episodic naming ("your Tokyo lunches", "a Sunday recipe
session"). The cases include `context` hints so the model has material
to anchor with — not just the terms in isolation.

Prompt construction lives in `tideline.intelligence.episodic_title` so
the bench measures the exact prompts the cluster naming engine
(`tideline.cluster.name_clusters`) uses in production.

Eval: response must contain at least one episodic-hook token (a place,
time, activity, or specific situation cue). Generic taxonomy tokens
("words", "vocabulary", "items", "Japanese") alone are not enough.
"""

from __future__ import annotations

import re

from tideline.intelligence import episodic_title


ID = "B6"
NAME = "Episodic title (memory-anchored)"
CATEGORY = "tier_b"

SYSTEM_PROMPT = episodic_title.SYSTEM_PROMPT


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
    return episodic_title.build_prompt(case["items"])


def evaluate(case: dict, response: str) -> bool:
    """Episodic-token hit using word-boundary matching.

    Substring matching falsely accepts generic taxonomy answers — e.g.
    "Japanese words" hits the token "japan" by substring even though
    "Japanese" is exactly the kind of categorical label B6 is meant to
    reject. Word-boundary anchoring requires the token to appear as its
    own word (or multi-word phrase) in the response.
    """
    low = response.lower()
    return any(
        re.search(rf"\b{re.escape(token)}\b", low)
        for token in case["episodic_tokens"]
    )
