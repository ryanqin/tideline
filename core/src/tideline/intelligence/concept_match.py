"""B1 — Are these two terms the same concept? (binary yes/no)

The cluster engine's primitive: every vote is one yes/no answer about
whether two translation rows refer to the same concept. Accumulated
yes-votes form edges in the similarity graph; connected components
become clusters. With B1 at 83-100% atom-bench accuracy on E2B/E4B,
a single vote per pair is reliable enough for MVP — multi-vote
accumulation can be layered on later for atoms with lower accuracy.

The atom bench (`bench/atoms/b1_concept_match.py`) imports
`SYSTEM_PROMPT`, `build_prompt`, and `parse_response` from here so the
benchmark and the production caller use identical prompts.
"""

from __future__ import annotations

import re


SYSTEM_PROMPT = (
    "You answer with exactly one word: 'yes' or 'no'. No other text."
)


_WORD_RE = re.compile(r"\b[a-z]+\b")


def build_prompt(
    term1: str, lang1: str,
    term2: str, lang2: str,
) -> str:
    return (
        f"Are these two terms referring to the same concept?\n"
        f"1. '{term1}' ({lang1})\n"
        f"2. '{term2}' ({lang2})"
    )


def parse_response(response: str) -> bool | None:
    """Return True (yes) / False (no) / None (unparseable).

    Hedged or contradictory answers ("yes and no", "yes and no, it depends")
    return None so the caller can discard the vote rather than be misled by
    a positional false read.
    """
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
