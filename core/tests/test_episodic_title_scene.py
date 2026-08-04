"""The SCENE reply parser, driven by the shared parity vectors.

The SCENE prompt (episodic_title.SCENE_SYSTEM_PROMPT) asks the model for a
Chinese name, but until now `parse_response` — written for the English
episodic title — was reading the answer. Every one of its three defences
missed: the preamble arrives as 名字：, the marks around the name are
full-width, and the length cap counts space-delimited words, so a rambling
Chinese reply is one "word" and never trips it.

The phone met all three on real hardware first and fixed them in
SceneNaming.kt (2026-06-15). These cases come from that suite — including
four verbatim on-device E2B replies, which are the reason an emoji strip
exists at all — and now live in `parity/vectors/scene_name.json` so both
ends read one list instead of two copies drifting apart.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tideline.intelligence import episodic_title


_VECTORS = (
    Path(__file__).resolve().parents[2] / "parity" / "vectors" / "scene_name.json"
)


def _cases() -> list[dict]:
    data = json.loads(_VECTORS.read_text(encoding="utf-8"))
    return data["cases"]


def test_vectors_file_is_present_and_populated():
    """A missing vector file must fail loudly, not silently skip the suite."""
    cases = _cases()
    assert len(cases) >= 18
    assert {c["id"] for c in cases} == {c["id"] for c in cases if c["id"]}


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["id"])
def test_scene_name_parity_vector(case):
    assert episodic_title.parse_scene_response(case["input"]) == case["expected"]


def test_scene_parser_points_at_the_vectors_it_is_tested_by():
    """The vector file names its two implementations; keep that pointer true."""
    data = json.loads(_VECTORS.read_text(encoding="utf-8"))
    core_impl = data["implementations"]["core"]
    assert core_impl.endswith("::parse_scene_response")
    module_path = Path(__file__).resolve().parents[1] / "src" / "tideline"
    named = core_impl.split("::")[0].replace("core/src/tideline/", "")
    assert (module_path / named).exists(), f"vector points at a missing {named}"


def test_episodic_parser_is_left_alone():
    """The English path keeps counting words — this fix must not touch it."""
    rambled = " ".join(f"word{i}" for i in range(20))
    title = episodic_title.parse_response(rambled)
    assert title is not None
    assert len(title.split()) == 12


def test_the_two_parsers_disagree_exactly_where_they_should():
    """A Chinese reply the old parser waved through is what motivated the fix."""
    decorated = "名字：生活集市 🛒"
    assert episodic_title.parse_response(decorated) == "名字：生活集市 🛒"
    assert episodic_title.parse_scene_response(decorated) == "生活集市"
