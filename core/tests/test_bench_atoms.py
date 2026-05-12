"""Atom bench infrastructure verification.

The atom bench measures per-operation LLM reliability via direct
`runtime.generate()` — no Agent loop, no tool dispatch. Each atom is a
module declaring ID / NAME / CATEGORY / SYSTEM_PROMPT / CASES /
build_prompt / evaluate.

Functional gates:
- All 11 atom modules load and expose the required interface
- Each atom has at least 5 cases (statistical floor for accuracy claims)
- Atom IDs are unique
- Categories are constrained to {"tier_a", "tier_b"}
- Each atom's evaluate() returns bool on plausible inputs
- Runner produces one CaseResult per (atom, case) pair
- Summarize aggregates per-atom accuracy correctly

We do NOT assert specific Mock or real-model scores — those are the
output of the bench, not infrastructure invariants.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tideline.bench.atoms.metrics import (
    AtomSummary,
    format_failure_samples,
    format_summary_table,
    summarize,
)
from tideline.bench.atoms.runner import CaseResult, load_atoms, run as run_atoms, run_atom


_REQUIRED_ATTRS = ("ID", "NAME", "CATEGORY", "SYSTEM_PROMPT", "CASES")
_REQUIRED_CALLABLES = ("build_prompt", "evaluate")


# --- Atom module interface -----------------------------------------------


def test_load_atoms_returns_eleven_modules():
    atoms = load_atoms()
    assert len(atoms) == 11, f"expected 11 atoms, got {len(atoms)}"


def test_each_atom_module_exposes_required_attributes():
    for atom in load_atoms():
        for attr in _REQUIRED_ATTRS:
            assert hasattr(atom, attr), f"{atom.__name__} missing {attr}"
        for fn_name in _REQUIRED_CALLABLES:
            fn = getattr(atom, fn_name, None)
            assert callable(fn), f"{atom.__name__}.{fn_name} not callable"


def test_atom_ids_are_unique():
    ids = [atom.ID for atom in load_atoms()]
    assert len(ids) == len(set(ids)), f"duplicate atom IDs: {ids}"


def test_atom_ids_match_expected_pattern():
    ids = {atom.ID for atom in load_atoms()}
    expected = {"A1", "A2", "A3", "A5", "A6",
                "B1", "B2", "B3", "B4", "B5", "B6"}
    assert ids == expected


def test_atom_categories_constrained():
    for atom in load_atoms():
        assert atom.CATEGORY in ("tier_a", "tier_b"), (
            f"{atom.ID} category {atom.CATEGORY!r} not in tier_a / tier_b"
        )


def test_a_atoms_are_tier_a_and_b_atoms_are_tier_b():
    for atom in load_atoms():
        if atom.ID.startswith("A"):
            assert atom.CATEGORY == "tier_a", f"{atom.ID} should be tier_a"
        elif atom.ID.startswith("B"):
            assert atom.CATEGORY == "tier_b", f"{atom.ID} should be tier_b"


def test_each_atom_has_minimum_case_count():
    for atom in load_atoms():
        assert len(atom.CASES) >= 5, (
            f"{atom.ID} has only {len(atom.CASES)} cases (need >= 5)"
        )


def test_each_atom_build_prompt_returns_nonempty_string():
    for atom in load_atoms():
        for case in atom.CASES:
            prompt = atom.build_prompt(case)
            assert isinstance(prompt, str) and prompt.strip(), (
                f"{atom.ID} build_prompt returned empty/non-string for case {case}"
            )


def test_each_atom_system_prompt_is_nonempty():
    for atom in load_atoms():
        assert isinstance(atom.SYSTEM_PROMPT, str)
        assert atom.SYSTEM_PROMPT.strip()


def test_each_atom_evaluate_returns_bool():
    """Sanity: pass each atom's first case its own reference (or close) and
    check evaluate produces a boolean. Doesn't assert on the value."""
    for atom in load_atoms():
        case = atom.CASES[0]
        result = atom.evaluate(case, "")
        assert isinstance(result, bool), (
            f"{atom.ID}.evaluate returned {type(result)}, expected bool"
        )


# --- Evaluator specific behavior -----------------------------------------


def test_a1_evaluator_normalizes_case_and_punctuation():
    from tideline.bench.atoms import a1_word_translation as a1

    case = {"original": "hello", "target_lang": "Chinese", "reference": "你好"}
    assert a1.evaluate(case, "你好")
    assert a1.evaluate(case, "你好。")
    assert a1.evaluate(case, " 你好 ")
    assert not a1.evaluate(case, "不对")


def test_a3_evaluator_accepts_both_name_and_code():
    from tideline.bench.atoms import a3_source_language_id as a3

    case = {"text": "ラーメン", "expected": ["japanese", "ja"]}
    assert a3.evaluate(case, "Japanese")
    assert a3.evaluate(case, "ja")
    assert a3.evaluate(case, "This is Japanese.")
    assert not a3.evaluate(case, "Chinese")


def test_a5_evaluator_catches_preamble_phrases():
    from tideline.bench.atoms import a5_output_discipline as a5

    case = {"original": "hello", "target_lang": "Chinese"}
    assert a5.evaluate(case, "你好")
    assert not a5.evaluate(case, "Here's the translation: 你好")
    assert not a5.evaluate(case, "The translation is: 你好")
    assert not a5.evaluate(case, "Sure, 你好")


def test_b1_evaluator_parses_yes_no():
    from tideline.bench.atoms import b1_concept_match as b1

    case = {
        "term1": ("love", "English"),
        "term2": ("amor", "Spanish"),
        "expected": "yes",
    }
    assert b1.evaluate(case, "yes")
    assert b1.evaluate(case, "Yes.")
    assert b1.evaluate(case, "yes, they refer to the same concept")
    assert not b1.evaluate(case, "no")
    # If model said both, it didn't comply — counts as fail
    assert not b1.evaluate(case, "yes and no")


def test_b2_evaluator_picks_first_valid_option():
    from tideline.bench.atoms import b2_register_classification as b2

    case = {"term": "ラーメン", "expected": "menu"}
    assert b2.evaluate(case, "menu")
    assert b2.evaluate(case, "Menu.")
    assert not b2.evaluate(case, "conversation")
    # If model rambles but starts with the right option, accept it
    assert b2.evaluate(case, "menu (also possible in conversation)")


# --- Runner & metrics ----------------------------------------------------


def test_run_atom_with_mock_returns_one_result_per_case():
    from tideline.bench.atoms import a1_word_translation as a1
    from tideline.runtimes import get_runtime

    runtime = get_runtime("mock")
    results = run_atom(runtime, a1)
    assert len(results) == len(a1.CASES)
    for r in results:
        assert isinstance(r, CaseResult)
        assert r.atom_id == "A1"


def test_run_full_mock_produces_results_for_all_atoms():
    results = run_atoms("mock")
    atom_ids = {r.atom_id for r in results}
    assert len(atom_ids) == 11


def test_summarize_produces_one_row_per_atom():
    results = run_atoms("mock")
    summaries = summarize(results)
    assert len(summaries) == 11
    for s in summaries:
        assert isinstance(s, AtomSummary)
        assert 0.0 <= s.accuracy <= 1.0


def test_summarize_accuracy_matches_pass_count():
    results = run_atoms("mock")
    summaries = summarize(results)
    for s in summaries:
        expected_acc = s.pass_count / s.n if s.n else 0.0
        assert s.accuracy == pytest.approx(expected_acc)


def test_format_summary_table_renders():
    results = run_atoms("mock")
    summaries = summarize(results)
    table = format_summary_table(summaries)
    assert "atom" in table
    assert "acc" in table
    # Every atom appears
    for s in summaries:
        assert s.atom_id in table


def test_format_failure_samples_renders_or_says_none():
    results = run_atoms("mock")
    samples = format_failure_samples(results)
    # Either real failure detail or the no-failures sentinel
    assert isinstance(samples, str)
    assert samples.strip()


# --- CLI -----------------------------------------------------------------


def test_cli_atoms_suite_smoke():
    result = subprocess.run(
        [sys.executable, "-m", "tideline.bench", "--suite", "atoms",
         "--runtime", "mock"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "atom" in result.stdout
    assert "A1" in result.stdout
    assert "B1" in result.stdout


def test_cli_all_suite_includes_atoms_section():
    result = subprocess.run(
        [sys.executable, "-m", "tideline.bench", "--suite", "all",
         "--runtime", "mock", "--tier", "phrases"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    # Translate, agent, and atoms sections all present
    assert "scenario" in result.stdout    # translate
    assert "category" in result.stdout    # agent
    assert "atom" in result.stdout        # atoms
