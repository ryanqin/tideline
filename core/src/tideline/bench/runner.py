"""Translation benchmark runner.

Iterates pairs from `data/{tier}/*.tsv`, asks the agent to translate the
original via `translate {original} to English`, and aggregates predictions
into per-scenario + overall metric rows.

Each pair is one fresh agent run with an in-memory SQLite — the bench has
no interest in drawer/candidate state and shouldn't bleed across pairs.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from tideline.agent import Agent
from tideline.bench.metrics import bleu_score, chrf_score, exact_match
from tideline.runtime import ModelRuntime
from tideline.runtimes import get_runtime
from tideline.tools import (
    AddDrawerTool,
    AddTranslationTool,
    ListCandidatesTool,
    ListDrawersTool,
    ListTranslationsTool,
    NoopTool,
    ToolRegistry,
    init_all_tables,
)


_DATA_DIR = Path(__file__).resolve().parent / "data"
_TIERS = ("phrases", "sentences")

# Same system message the CLI uses, so bench results reflect production behavior.
_TIDELINE_SYSTEM = (
    "You are Tideline, a local-first translation assistant. "
    "When the user explicitly asks to translate text, perform the translation "
    "yourself, then call the add_translation tool to record "
    "(original, target_lang, translated) before responding to the user with "
    "the translated text. For other requests, use the available tools as "
    "appropriate. Be concise."
)


@dataclass(frozen=True)
class BenchPair:
    scenario: str  # "ja-en", "fr-en", ...
    original: str
    reference: str


@dataclass(frozen=True)
class BenchResult:
    tier: str
    scenario: str
    n: int
    exact_match: float
    chrf: float
    bleu: float | None  # None for the phrase tier


def default_data_dir() -> Path:
    return _DATA_DIR


def load_pairs(data_dir: Path, tier: str) -> list[BenchPair]:
    """Read every TSV under data_dir/tier/ into BenchPair tuples."""
    if tier not in _TIERS:
        raise ValueError(f"unknown tier {tier!r}; expected one of {_TIERS}")
    tier_dir = data_dir / tier
    if not tier_dir.is_dir():
        raise FileNotFoundError(f"missing tier directory: {tier_dir}")

    pairs: list[BenchPair] = []
    for tsv in sorted(tier_dir.glob("*.tsv")):
        scenario = tsv.stem  # "ja-en"
        for line in tsv.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 2:
                raise ValueError(
                    f"{tsv}: malformed line (expected 2 tab-separated columns): {line!r}"
                )
            original, reference = parts
            pairs.append(BenchPair(scenario, original.strip(), reference.strip()))
    return pairs


def _build_agent(runtime: ModelRuntime) -> tuple[Agent, sqlite3.Connection]:
    conn = sqlite3.connect(":memory:")
    init_all_tables(conn)
    registry = ToolRegistry()
    registry.register(NoopTool)
    registry.register(AddDrawerTool)
    registry.register(ListDrawersTool)
    registry.register(AddTranslationTool)
    registry.register(ListTranslationsTool)
    registry.register(ListCandidatesTool)
    agent = Agent(
        runtime,
        registry=registry,
        context={"db": conn},
        system_message=_TIDELINE_SYSTEM,
    )
    return agent, conn


def translate(runtime: ModelRuntime, original: str) -> str:
    agent, conn = _build_agent(runtime)
    try:
        return agent.run(f"translate {original} to English")
    finally:
        conn.close()


def _score(
    tier: str, scenario: str, predictions: list[str], references: list[str]
) -> BenchResult:
    return BenchResult(
        tier=tier,
        scenario=scenario,
        n=len(predictions),
        exact_match=exact_match(predictions, references),
        chrf=chrf_score(predictions, references),
        bleu=bleu_score(predictions, references) if tier == "sentences" else None,
    )


def run(
    runtime_name: str = "mock",
    data_dir: Path | None = None,
    tier: str = "phrases",
) -> list[BenchResult]:
    """Translate every pair under (data_dir, tier) and score per scenario.

    Returns one BenchResult per scenario plus one aggregate row labeled
    'all' that pools every prediction across scenarios.
    """
    data_dir = data_dir or _DATA_DIR
    runtime = get_runtime(runtime_name)
    pairs = load_pairs(data_dir, tier)

    by_scenario: dict[str, list[tuple[str, str]]] = {}
    for pair in pairs:
        prediction = translate(runtime, pair.original)
        by_scenario.setdefault(pair.scenario, []).append((prediction, pair.reference))

    results: list[BenchResult] = []
    all_preds: list[str] = []
    all_refs: list[str] = []
    for scenario in sorted(by_scenario):
        preds, refs = zip(*by_scenario[scenario])
        results.append(_score(tier, scenario, list(preds), list(refs)))
        all_preds.extend(preds)
        all_refs.extend(refs)

    if all_preds:
        results.append(_score(tier, "all", all_preds, all_refs))
    return results


def format_table(results: list[BenchResult]) -> str:
    if not results:
        return "(no results)"
    header = f"{'tier':<10} {'scenario':<8} {'n':>3}  {'EM':>6}  {'chrF':>6}  {'BLEU':>6}"
    sep = "-" * len(header)
    lines = [header, sep]
    for r in results:
        em = f"{r.exact_match * 100:5.1f}%"
        chrf = f"{r.chrf:5.1f}"
        bleu = f"{r.bleu:5.1f}" if r.bleu is not None else "  -- "
        lines.append(f"{r.tier:<10} {r.scenario:<8} {r.n:>3}  {em:>6}  {chrf:>6}  {bleu:>6}")
    return "\n".join(lines)
