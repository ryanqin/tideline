"""Atom bench runner.

Each atom module declares `ID`, `NAME`, `CATEGORY` ("tier_a" / "tier_b"),
`SYSTEM_PROMPT`, `CASES` (list of dicts), `build_prompt(case)`, and
`evaluate(case, response)`. The runner iterates all atoms × cases through
direct `runtime.generate()` — bypassing Agent because we want to measure
single-shot LLM behavior, not full agent loops.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from tideline.format import build_prompt as _build_turn_prompt
from tideline.format import make_turn
from tideline.runtime import ModelRuntime
from tideline.runtimes import get_runtime


_ATOM_MODULES: tuple[str, ...] = (
    "tideline.bench.atoms.a1_word_translation",
    "tideline.bench.atoms.a2_sentence_translation",
    "tideline.bench.atoms.a3_source_language_id",
    "tideline.bench.atoms.a5_output_discipline",
    "tideline.bench.atoms.a6_term_extraction",
    "tideline.bench.atoms.b1_concept_match",
    "tideline.bench.atoms.b2_register_classification",
    "tideline.bench.atoms.b3_ambiguity_detection",
    "tideline.bench.atoms.b4_common_theme",
    "tideline.bench.atoms.b5_complexity_tier",
    "tideline.bench.atoms.b6_episodic_title",
)


@dataclass(frozen=True)
class CaseResult:
    atom_id: str
    atom_name: str
    category: str
    case_idx: int
    case_data: dict[str, Any]
    response: str
    passed: bool


def _direct_generate(runtime: ModelRuntime, system: str, user: str) -> str:
    """Single-turn LLM call. Returns the raw model output (stripped).

    No tool parsing — atoms measure direct response capability, not the
    agent loop. If the model emits tool-call markers, the raw string is
    what we see and evaluate; off-script behavior IS a failure signal.
    """
    history = [make_turn("system", system), make_turn("user", user)]
    full_prompt = _build_turn_prompt(history)
    return runtime.generate(full_prompt).strip()


def load_atoms() -> list[ModuleType]:
    return [importlib.import_module(path) for path in _ATOM_MODULES]


def run_atom(runtime: ModelRuntime, atom: ModuleType) -> list[CaseResult]:
    results: list[CaseResult] = []
    for idx, case in enumerate(atom.CASES):
        user_prompt = atom.build_prompt(case)
        response = _direct_generate(runtime, atom.SYSTEM_PROMPT, user_prompt)
        passed = atom.evaluate(case, response)
        results.append(
            CaseResult(
                atom_id=atom.ID,
                atom_name=atom.NAME,
                category=atom.CATEGORY,
                case_idx=idx,
                case_data=dict(case),
                response=response,
                passed=passed,
            )
        )
    return results


def run(runtime_name: str = "mock") -> list[CaseResult]:
    runtime = get_runtime(runtime_name)
    out: list[CaseResult] = []
    for atom in load_atoms():
        out.extend(run_atom(runtime, atom))
    return out
