"""Which relation a vote is about, and how to ask the model about it.

A Voter only adapts a row pair to its atom's shared prompt module — prompt and
parser stay in `intelligence/`, never duplicated here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from tideline.intelligence import concept_match, relatedness


# --- Vote-type dispatch ---------------------------------------------------
#
# One vote/cluster schema, two clustering relations selected by `vote_type`:
#   • 'concept' — B1 concept_match: "same concept?" (ラーメン ≡ ramen).
#     Aggregates synonyms; feeds the by-language lens + existing clusters.
#   • 'theme'   — scene TYPE, grouped deterministically by the capture model's
#     `scene_label`. **It does not vote.** See the tombstone on the theme
#     Voter below.
# A Voter only adapts a (original, target_lang, translated) row pair to its
# atom's shared prompt module — prompt + parser stay in intelligence/, never
# duplicated here. Adding a relation later = registering one Voter; the
# voting / rebuild machinery below is relation-agnostic.


@dataclass(frozen=True)
class _Voter:
    system_prompt: str
    build: Callable[[tuple, tuple], str]
    parse: Callable[[str], "bool | None"]


_VOTERS: dict[str, _Voter] = {
    "concept": _Voter(
        system_prompt=concept_match.SYSTEM_PROMPT,
        # Render each term with its SOURCE language so the model judges the
        # words in the language they were met in (concept voting is scoped to
        # one source language, §3.3, so both terms share it — e.g. Japanese
        # 駅 vs 停車場). _fetch_translation returns source_lang in slot 1;
        # passing the target language here would mislabel both as Chinese.
        build=lambda ra, rb: concept_match.build_prompt(
            ra[0], ra[1] or "unknown", rb[0], rb[1] or "unknown"
        ),
        parse=concept_match.parse_response,
    ),
    # TOMBSTONE (2026-06-13): this voter has no reader. Themes stopped being
    # built from votes when they became scene TYPES grouped on the capture
    # model's `scene_label` — `_vote_edges` is only ever called with 'concept'.
    # Votes cast here are written to the table and read by nobody. Kept because
    # B7 relatedness is still a measured atom (bench b7) and because the shape
    # is the template for any future relation; the CLI can no longer reach it.
    # If DESIGN.md §3.2's "merge near-duplicate scene types" is ever built, it
    # wants votes on scene LABELS, not on word pairs — the word-pair form is
    # exactly what the 2026-06-03 on-device probe judged unusable.
    "theme": _Voter(
        system_prompt=relatedness.SYSTEM_PROMPT,
        # Relatedness judges the surface terms only — no language slot; the
        # cuisine/setting granularity lives in its few-shot prompt.
        build=lambda ra, rb: relatedness.build_prompt(ra[0], rb[0]),
        parse=relatedness.parse_response,
    ),
}


def _voter(vote_type: str) -> _Voter:
    try:
        return _VOTERS[vote_type]
    except KeyError:
        raise ValueError(
            f"unknown vote_type {vote_type!r}; expected one of {sorted(_VOTERS)}"
        ) from None
