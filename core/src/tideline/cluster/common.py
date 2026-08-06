"""Pieces more than one part of the engine needs.

Split out so the parts that use them don't have to import each other: naming
needed exactly one function from voting (`_direct_generate`) and nothing else,
which would have made a dependency out of a coincidence.
"""

from __future__ import annotations

from tideline.format import build_prompt as _build_turn_prompt
from tideline.format import make_turn
from tideline.runtime import ModelRuntime


_DEFAULT_VOTE_THRESHOLD = 0.66
# Phase B4: multi-vote accumulation is the default. Cross-original pairs
# (the real Tier B value) need 3 votes with ≥2 yes to form an edge —
# that's the guard against single-false-positive cluster pollution.
_DEFAULT_MIN_VOTES = 3

# Two translations are the same *concept* by construction — no model vote
# needed — when they share a source word (the same word seen twice), or
# when two words *of the same source language* resolve to the same
# first-language form (Japanese 駅 and 停車場 both → 车站). These edges are
# added directly in rebuild_clusters; voting on them would only spend the
# sweep budget on a foregone conclusion (the same-word pairs alone can eat
# a whole small budget before any genuinely ambiguous pair is reached —
# the "budget pit"), so excluding them lets a modest budget reach real
# synonyms.
#
# Concept clusters are scoped per language-pair (§3.3): a cluster never
# mixes two source languages. So the same-rendering branch requires the
# SAME source_lang — 駅 (Japanese) and station (English) both render to
# 车站, but they are two language-pairs and must stay two clusters. The
# user meeting one concept in two different languages is a rare case we
# deliberately don't chase. (COALESCE so untagged rows match each other,
# and so the all-NULL state in unit tests behaves as one language.)
# Empty translated guarded so unfilled rows don't all collapse together.
_DETERMINISTIC_CONCEPT_PREDICATE = (
    "(t1.original = t2.original "
    "OR (t1.translated = t2.translated AND t1.translated <> '' "
    "AND COALESCE(t1.source_lang, '') = COALESCE(t2.source_lang, '')))"
)


def _direct_generate(runtime: ModelRuntime, system: str, user: str) -> str:
    history = [make_turn("system", system), make_turn("user", user)]
    full_prompt = _build_turn_prompt(history)
    return runtime.generate(full_prompt).strip()
