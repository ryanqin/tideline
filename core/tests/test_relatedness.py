"""B7 topic-relatedness — shared prompt + bench-atom wiring.

Unit-level only (parser, prompt shape, shared-prompt contract, honest test
design). Real-model accuracy is the atom bench's job, run separately.
"""

from __future__ import annotations

from tideline.bench.atoms import b7_topic_relatedness as b7
from tideline.intelligence import relatedness


# --- parser ---------------------------------------------------------------


def test_parse_yes_no_hedge_unparseable():
    assert relatedness.parse_response("yes") is True
    assert relatedness.parse_response("Yes.") is True
    assert relatedness.parse_response("no") is False
    assert relatedness.parse_response("yes and no") is None  # hedged → discard
    assert relatedness.parse_response("maybe") is None


def test_build_prompt_includes_both_terms_and_fewshot():
    p = relatedness.build_prompt("ramen", "udon")
    assert "ramen" in p and "udon" in p
    assert "Examples:" in p  # few-shot contrast is part of the prompt


# --- shared-prompt contract (never two prompts for one atom) --------------


def test_b7_atom_shares_intelligence_prompt():
    assert b7.SYSTEM_PROMPT is relatedness.SYSTEM_PROMPT
    case = b7.CASES[0]
    assert b7.build_prompt(case) == relatedness.build_prompt(case["term1"], case["term2"])


def test_b7_registered_in_atom_suite():
    from tideline.bench.atoms.runner import _ATOM_MODULES

    assert "tideline.bench.atoms.b7_topic_relatedness" in _ATOM_MODULES


# --- honest bench design --------------------------------------------------


def test_cases_disjoint_from_fewshot():
    """Scoring on the few-shot pairs would inflate the number — guard it."""
    shots = {
        frozenset(p)
        for p in [("sushi", "ramen"), ("sushi", "croissant"),
                  ("contract", "meeting"), ("meeting", "sushi")]
    }
    for case in b7.CASES:
        assert frozenset((case["term1"], case["term2"])) not in shots


def test_cases_balanced_and_labeled():
    labels = [c["expected"] for c in b7.CASES]
    assert set(labels) == {"yes", "no"}
    # roughly balanced so the score isn't a yes/no-bias artifact
    assert abs(labels.count("yes") - labels.count("no")) <= 2


def test_evaluate_maps_parsed_to_expected():
    yes_case = {"term1": "a", "term2": "b", "expected": "yes"}
    no_case = {"term1": "a", "term2": "b", "expected": "no"}
    assert b7.evaluate(yes_case, "yes") is True
    assert b7.evaluate(yes_case, "no") is False
    assert b7.evaluate(no_case, "no") is True
    assert b7.evaluate(yes_case, "maybe") is False  # unparseable counts as fail
