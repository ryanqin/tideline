"""B7 — Do two terms belong to the same theme? (binary)

The primitive for *thematic* clustering — the engine behind "your Tokyo
lunches" style memories. Distinct from B1 (`concept_match`): B1 asks whether
two terms are the *same concept* (ラーメン ≡ ramen), which clusters synonyms;
B7 asks whether they belong to the *same theme* (ramen ~ sushi), which clusters
related-but-different terms a learner would group.

The granularity is deliberately drawn at the **specific-setting** level (one
cuisine, one outing, one kind of meeting), NOT the broad category. That's the
whole game: "both are food" must be a *no* (ramen / croissant), or relatedness
stops being an equivalence-ish relation and Union-Find collapses every food
into one blob. Real-E2B spike (2026-05-26): this prompt scored 12/12 on a hand
set incl. the cross-cuisine discriminators, and works across languages.

Shared-prompt module (like concept_match): the bench atom
`bench/atoms/b7_topic_relatedness` and the future thematic cluster engine both
import SYSTEM_PROMPT / build_prompt / parse_response from here — never two
prompts for one atom.
"""

from __future__ import annotations

import re


SYSTEM_PROMPT = (
    "Two words share a theme only if they'd come up in the SAME SPECIFIC "
    "setting — the same cuisine, the same single trip, the same kind of "
    "meeting — not merely the same broad category. Two foods from different "
    "cuisines do NOT share a theme. Answer with only 'yes' or 'no'."
)

# Few-shot contrast carries most of the lift (without it the model defaults to
# "different things → no"). One same-theme and one cross-cuisine pair on each
# side so it learns the granularity, not just a yes/no bias. Keep bench CASES
# disjoint from these pairs — testing on the shots inflates the score.
_FEWSHOT = (
    "Examples:\n"
    "- 'sushi' / 'ramen' -> yes\n"
    "- 'sushi' / 'croissant' -> no\n"
    "- 'contract' / 'meeting' -> yes\n"
    "- 'meeting' / 'sushi' -> no\n"
)

_WORD_RE = re.compile(r"\b[a-z]+\b")


def build_prompt(term1: str, term2: str) -> str:
    return _FEWSHOT + f"Now answer for: '{term1}' / '{term2}' ->"


def parse_response(response: str) -> bool | None:
    """True (yes) / False (no) / None (hedged or unparseable). Mirrors
    concept_match: a reply carrying both words is discarded, not guessed."""
    tokens = _WORD_RE.findall(response.lower())
    has_yes = "yes" in tokens
    has_no = "no" in tokens
    if has_yes and has_no:
        return None
    if has_yes:
        return True
    if has_no:
        return False
    return None
