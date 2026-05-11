"""Bench infrastructure verification.

Functional gates:
- Metrics behave as documented (exact_match normalizes, chrF/BLEU pass
  through to sacrebleu with the right argument shape)
- Data files are well-formed (every TSV parses; expected scenarios + tiers
  present; pair counts meet minimum thresholds)
- Runner end-to-end with Mock produces a result list of the right shape

We do NOT assert on Mock's bench scores: Mock returns
"[mock-translated to english] X", which trivially scores ~0 against real
references. That's expected — the bench infrastructure works regardless of
what the runtime returns.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tideline.bench import metrics
from tideline.bench.runner import (
    BenchPair,
    default_data_dir,
    format_table,
    load_pairs,
    run,
)


# --- Metrics: exact_match -------------------------------------------------


def test_exact_match_perfect():
    assert metrics.exact_match(["hello", "world"], ["hello", "world"]) == 1.0


def test_exact_match_zero():
    assert metrics.exact_match(["foo", "bar"], ["hello", "world"]) == 0.0


def test_exact_match_normalizes_case_and_punctuation():
    assert metrics.exact_match(
        ["Hello!", "Te amo."],
        ["hello", "te amo"],
    ) == 1.0


def test_exact_match_handles_unicode_normalization():
    """NFKC: full-width and half-width digits collapse to the same form."""
    assert metrics.exact_match(["café"], ["café"]) == 1.0


def test_exact_match_partial():
    assert metrics.exact_match(["a", "b", "c"], ["a", "x", "c"]) == pytest.approx(2 / 3)


def test_exact_match_length_mismatch_raises():
    with pytest.raises(ValueError):
        metrics.exact_match(["a"], ["a", "b"])


def test_exact_match_empty_is_zero():
    assert metrics.exact_match([], []) == 0.0


# --- Metrics: chrF / BLEU through sacrebleu ------------------------------


def test_chrf_perfect_match_is_100():
    score = metrics.chrf_score(
        ["The cat sat on the mat."], ["The cat sat on the mat."]
    )
    assert score == pytest.approx(100.0)


def test_chrf_total_mismatch_is_near_zero():
    score = metrics.chrf_score(["xxxxxx"], ["the quick brown fox"])
    assert score < 10.0


def test_bleu_perfect_match_is_100():
    score = metrics.bleu_score(
        ["the cat sat on the mat", "i love you"],
        ["the cat sat on the mat", "i love you"],
    )
    assert score == pytest.approx(100.0)


def test_bleu_total_mismatch_is_zero():
    assert metrics.bleu_score(
        ["xxxxx yyyyy zzzzz aaaaa"], ["the quick brown fox"]
    ) == pytest.approx(0.0)


# --- Data files ----------------------------------------------------------


@pytest.mark.parametrize("tier", ["phrases", "sentences"])
def test_every_scenario_has_a_data_file(tier):
    data_dir = default_data_dir()
    expected_scenarios = {"ja-en", "fr-en", "es-en", "zh-en", "de-en"}
    tier_dir = data_dir / tier
    found = {p.stem for p in tier_dir.glob("*.tsv")}
    assert found == expected_scenarios, f"{tier}: missing {expected_scenarios - found}"


def test_load_pairs_phrases():
    pairs = load_pairs(default_data_dir(), "phrases")
    assert len(pairs) >= 50, f"expected >= 50 phrase pairs total, got {len(pairs)}"

    # Every pair has non-empty original and reference
    for p in pairs:
        assert p.original, f"empty original in {p.scenario}"
        assert p.reference, f"empty reference in {p.scenario} for {p.original!r}"
        assert "-" in p.scenario


def test_load_pairs_sentences():
    pairs = load_pairs(default_data_dir(), "sentences")
    assert len(pairs) >= 25, f"expected >= 25 sentence pairs total, got {len(pairs)}"


def test_load_pairs_rejects_unknown_tier():
    with pytest.raises(ValueError):
        load_pairs(default_data_dir(), "bogus")


def test_each_scenario_has_minimum_phrase_count():
    pairs = load_pairs(default_data_dir(), "phrases")
    by_scenario: dict[str, int] = {}
    for p in pairs:
        by_scenario[p.scenario] = by_scenario.get(p.scenario, 0) + 1
    for scenario, count in by_scenario.items():
        assert count >= 10, f"{scenario}: only {count} phrases (need >= 10)"


def test_each_scenario_has_minimum_sentence_count():
    pairs = load_pairs(default_data_dir(), "sentences")
    by_scenario: dict[str, int] = {}
    for p in pairs:
        by_scenario[p.scenario] = by_scenario.get(p.scenario, 0) + 1
    for scenario, count in by_scenario.items():
        assert count >= 5, f"{scenario}: only {count} sentences (need >= 5)"


# --- Runner end-to-end with Mock -----------------------------------------


def test_run_phrases_with_mock_produces_per_scenario_plus_all():
    results = run(runtime_name="mock", tier="phrases")
    scenarios = {r.scenario for r in results}
    assert {"ja-en", "fr-en", "es-en", "zh-en", "de-en"} <= scenarios
    assert "all" in scenarios

    # Phrase tier must not carry BLEU
    for r in results:
        assert r.bleu is None, f"phrase tier should skip BLEU; got {r.bleu} for {r.scenario}"


def test_run_sentences_with_mock_includes_bleu():
    results = run(runtime_name="mock", tier="sentences")
    for r in results:
        assert r.bleu is not None, f"sentence tier should report BLEU; got None for {r.scenario}"


def test_run_returns_correct_n_per_scenario():
    results = run(runtime_name="mock", tier="phrases")
    by_scenario = {r.scenario: r.n for r in results}
    pairs = load_pairs(default_data_dir(), "phrases")
    expected = {}
    for p in pairs:
        expected[p.scenario] = expected.get(p.scenario, 0) + 1
    for scenario, n in expected.items():
        assert by_scenario[scenario] == n
    assert by_scenario["all"] == sum(expected.values())


def test_format_table_renders_results():
    results = run(runtime_name="mock", tier="phrases")
    table = format_table(results)
    assert "scenario" in table
    assert "EM" in table
    assert "chrF" in table
    # phrase tier shows "--" for BLEU
    assert "--" in table


# --- CLI smoke -----------------------------------------------------------


def test_cli_bench_smoke():
    result = subprocess.run(
        [sys.executable, "-m", "tideline.bench", "--runtime", "mock", "--tier", "phrases"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "scenario" in result.stdout
    assert "all" in result.stdout
