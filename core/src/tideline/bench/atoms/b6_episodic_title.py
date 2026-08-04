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


# Case-agnostic episodic markers — any episodic title can lean on these
# regardless of the underlying scene. Time-of-day / day-name / narrative
# possessives are the universal scaffolding of "a remembered moment".
# Without these, a perfectly episodic plain-narrative title like
# "the night the connection broke" fails the per-case keyword list,
# which would force evaluators to enumerate every possible scene-setting
# verb per case — exactly the synonym-sea trap the bench-honesty rule
# warns against. These markers are evaluator scaffolding, not
# scene-specific tokens.
_UNIVERSAL_EPISODIC_MARKERS = frozenset({
    # Time-of-day
    "night", "tonight", "evening", "morning", "afternoon", "midnight",
    "dawn", "dusk", "noon",
    # Relative day markers
    "yesterday", "today", "tomorrow",
    # Day-of-week
    "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday",
    # Period markers
    "weekend",
    # Narrative possessives
    "your", "our", "my", "their",
})


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
    # These cases expect English episodic titles → an English-first reader.
    # Passing the native language keeps the bench measuring the exact
    # production prompt (which now writes the title in the reader's first
    # language) without changing what a correct answer looks like.
    return episodic_title.build_prompt(case["items"], case.get("native_lang", "English"))


# The category labels B6 exists to reject. Not a synonym dragnet — this is
# the SYSTEM_PROMPT's own avoid-list ("Avoid category labels ('vocabulary',
# 'words', '<language> X')") read back as a scoring rule.
_TAXONOMY_LABELS = frozenset({
    "vocabulary", "vocab", "words", "word", "terms", "term",
    "list", "phrases", "glossary",
})

# The prompt asks for 3-7 words. Anything much longer isn't a title — it's a
# paragraph, or the prompt handed back — and no token it happens to contain
# should buy it a pass.
_MAX_TITLE_WORDS_TO_PASS = 10


def evaluate(case: dict, response: str) -> bool:
    """Does the model's reply anchor a remembered moment?

    Judged on the title production would actually STORE (via the shared
    parse_response), not on the raw reply — the bench should measure what the
    product does with the answer.

    Three ways to fail, then the token hit:

    1. Nothing parseable comes back.
    2. It isn't a title. A reply longer than `_MAX_TITLE_WORDS_TO_PASS` words
       is a paragraph or an echo of the prompt; the prompt's own template says
       "captures **their** shared episodic moment", and "their" is a universal
       marker, so an echo used to score a pass on the strength of the question.
    3. It's a category label. `"Japanese words"` was correctly rejected, but
       `"Your Japanese words"` passed — the SYSTEM_PROMPT tells the model to
       "Lead with ... a possessive ('your', 'our')", so the marker list was
       rewarding a model for copying a surface format instruction rather than
       for anchoring anything. A possessive can no longer rescue a taxonomy
       answer.

    Then: a word-boundary hit on a case-specific episodic token OR a universal
    episodic marker. The universal set covers plain-narrative titles ("the
    night the connection broke") that scaffold a moment without scene-specific
    vocabulary. Word boundaries (not substrings) are what keep "Japanese" from
    hitting the token "japan".
    """
    title = episodic_title.parse_response(response)
    if not title:
        return False
    low = title.lower()
    if len(low.split()) > _MAX_TITLE_WORDS_TO_PASS:
        return False
    if any(re.search(rf"\b{label}\b", low) for label in _TAXONOMY_LABELS):
        return False
    candidates = set(case["episodic_tokens"]) | _UNIVERSAL_EPISODIC_MARKERS
    return any(
        re.search(rf"\b{re.escape(token)}\b", low)
        for token in candidates
    )
