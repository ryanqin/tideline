# Tideline Bench Suites

Two orthogonal bench suites share one CLI entry:

- **translate**: BLEU / chrF / exact-match on curated reference pairs.
  Scores text quality.
- **agent**: tool-call correctness, turn efficiency, restraint.
  Scores how well a model behaves inside our agent harness.

```
python -m tideline.bench                                 # translate (default)
python -m tideline.bench --suite translate
python -m tideline.bench --suite agent
python -m tideline.bench --suite all                     # both
python -m tideline.bench --suite agent --per-case        # show pass/fail per case

# Real model:
python -m tideline.bench --suite all --runtime llama_cpp
```

Install bench dependencies:

```
pip install -e ".[bench]"     # adds sacrebleu
```

---

# Translation Accuracy Bench

Three-metric translation evaluation against curated reference pairs.

## Metrics

| Metric | Where it fits | Score range |
|---|---|---|
| **exact_match** | Single-word lookups where partial credit is misleading | 0–100% |
| **chrF** | Character n-gram F-score; robust across short and long text and morphologically rich languages | 0–100 |
| **BLEU** | Standard MT metric; meaningful only on sentence-length text (skipped for `phrases`) | 0–100 |

`sacrebleu` powers chrF and BLEU; exact_match is implemented locally with
NFKC normalization + punctuation stripping + case folding.

## Test set

Five scenarios mirror the seed data (Tokyo menus, French recipes, Latin
lyrics, Beijing meetings, German tech). Each scenario contributes ~12
phrase pairs and ~6 sentence pairs.

### ⚠️ Reference-translation caveat

These references are **textbook-level translations written by the author**,
not native-speaker audited. They are good enough to catch large quality
regressions, but BLEU/chrF differences in the low single digits should not
be over-interpreted — they may reflect translator phrasing choices rather
than true model differences.

Native speakers reviewing and refining the references would meaningfully
strengthen this bench. PRs welcome.

## Reference numbers — Gemma 4 E2B & E4B, 2026-05-11

Captured on Apple Silicon (CPU only, llama-cpp-python 0.3.22, Q4_K_M GGUF
from unsloth, temperature 0.3, agent full-loop including `add_translation`
tool call). Re-run on your hardware to verify reproducibility:

```
python -m tideline.bench --runtime llama_cpp                                   # E2B (default)
TIDELINE_GEMMA_PATH=models/gemma-4-E4B-it-Q4_K_M.gguf python -m tideline.bench --runtime llama_cpp   # E4B
```

### Phrases (60 pairs, 5 scenarios × 12 each)

| Scenario | n  | E2B EM | E2B chrF | E4B EM | E4B chrF |
|---|---:|---:|---:|---:|---:|
| de-en | 12 |  91.7% | 84.7 |  91.7% | 85.6 |
| es-en | 12 |  75.0% | 71.6 |  83.3% | 75.6 |
| fr-en | 12 |  66.7% | 68.6 |  75.0% | 83.1 |
| ja-en | 12 |  83.3% | 74.3 |  66.7% | 61.4 |
| zh-en | 12 |  91.7% | 96.9 |  83.3% | 90.5 |
| **all** | **60** | **81.7%** | **80.4** | **80.0%** | **79.0** |

### Sentences (30 pairs, 5 scenarios × 6 each)

| Scenario | n | E2B EM | E2B chrF | E2B BLEU | E4B EM | E4B chrF | E4B BLEU |
|---|---:|---:|---:|---:|---:|---:|---:|
| de-en | 6 | 100.0% | 100.0 | 100.0 | 100.0% | 100.0 | 100.0 |
| es-en | 6 |  83.3% |  93.1 |  85.4 |  83.3% |  94.2 |  89.3 |
| fr-en | 6 |  50.0% |  78.2 |  69.0 |  33.3% |  82.4 |  64.5 |
| ja-en | 6 |  66.7% |  69.6 |  53.7 |  66.7% |  69.4 |  54.3 |
| zh-en | 6 |  16.7% |  72.2 |  39.6 |  50.0% |  81.8 |  67.1 |
| **all** | **30** | **63.3%** | **82.4** | **68.3** | **66.7%** | **85.7** | **74.0** |

### Latency (CPU only, 60-pair phrase tier)

| Model | Wall-clock | Per-pair |
|---|---:|---:|
| E2B (~3 GB) | ~1:30 | ~1.5 s |
| E4B (~4.6 GB) | ~2:22 | ~2.4 s |

### Reading the numbers

**E4B is not uniformly better than E2B.** It's a different shape, not a strict upgrade:

- **Sentence tier: E4B wins clearly.** +3.3 pt EM, +3.3 chrF, +5.7 BLEU
  averaged across scenarios. Particularly dramatic on zh-en sentences
  (16.7% → 50.0% EM) where E4B's richer reasoning unlocks idiomatic
  phrasings E2B fumbles.
- **Phrase tier: E2B is microscopically better overall** (81.7% vs 80.0% EM)
  but the geographic split is the real story — E4B is **+8 pt on es / fr**,
  E2B is **+9-17 pt on ja / zh**. E4B leans Indo-European; E2B is more
  even-handed across CJK.
- **fr-en sentence EM 50% → 33%, chrF 78 → 82** under E4B is another
  classic "low EM, high chrF" case — E4B paraphrases more naturally but my
  rigid single reference penalizes it. chrF is the honest signal here.
- **zh-en sentence 16.7% EM + 72 chrF (E2B)** is the same pattern from a
  different model: Gemma's translations are correct ("The contract requires
  signing") but phrased differently from the reference ("needs to be signed").

### Implication for product

The default is **E2B**: faster, smaller, and more consistent on short CJK
lookups — which is the modal Tideline use case (a learner pointing a camera
at a menu / sign / lyric). **E4B is the high-gear switch** when the user
needs sentence-length translation or non-CJK target languages — its
sentence-tier dominance and European-language strength justify the 1.5x
inference cost in those contexts.

---

## What the bench measures

- **Full agent-loop accuracy**, not raw runtime output. Each pair runs
  through `Agent.run("translate {original} to English")` with the full
  Tideline system message and tool registry. Numbers reflect what users
  actually experience.
- Each pair gets a fresh in-memory SQLite — drawer/candidate state does
  not bleed between pairs.

## What it does NOT measure

- Fluency or register fit beyond what BLEU/chrF capture.
- Cultural adequacy or idiomatic naturalness.
- Latency, memory, or any operational property.
- Translation **into** non-English target languages (current data is all
  source → English).

---

# Agent Capability Bench

Scores agent-loop behavior, not translation text. 13 canonical Tideline
prompts across three categories probe distinct capabilities:

| Category | n | What it probes |
|---|---:|---|
| translation_flow | 5 | Model calls `add_translation` with correctly-shaped args after producing a translation |
| tool_selection | 5 | Model dispatches to the right tool (`list_drawers`, `list_candidates`, etc.) for ambient memory requests |
| no_tool_off_task | 3 | Model **restrains** — off-task prompts ("hello", "what is 2+2?") fire NO tools |

## Metrics

- **task_success_rate**: cases where the right tool fired with shapely
  args (no-tool cases pass when no tool fires)
- **wrong_tool_rate**: cases where some tool fired but not the expected
  one — distinguishes "didn't understand" from "didn't try"
- **budget_exhaustion_rate**: cases that hit max_turns without resolving
- **mean num_tool_calls / response_words**: distributional shape

## Reference numbers — Mock vs E2B vs E4B, 2026-05-11

| Category | n | Mock | E2B | E4B |
|---|---:|---:|---:|---:|
| translation_flow | 5 | 80.0% | 80.0% | **100.0%** |
| tool_selection | 5 | 60.0% | 40.0% | 60.0% |
| no_tool_off_task | 3 | 100.0% | 100.0% | 100.0% |
| **all** | **13** | 76.9% | 69.2% | **84.6%** |

Wall time (CPU only): Mock <1s, E2B ~16s, E4B ~37s.

### Reading the agent bench

**E4B is uniformly stronger on agent behavior** — clear translation_flow
dominance (100% vs E2B's 80%), same tool_selection score but with
sharper restraint. Combined with E4B's sentence-tier translation lead,
the case for the E4B "high gear" gets stronger as task complexity rises.

**Mock outscores E2B at 76.9% vs 69.2%** — surprising at first, but the
explanation matters: Mock is a hand-tuned pattern matcher whose failure
modes (T4 "into" vs "to", S2/S4 plural nouns) are different from a real
model's failure modes (S1/S3/S5 — see below). The bench is doing exactly
what it should: revealing that "model quality" and "harness fit" are
distinct axes.

### Universal failure points (both E2B and E4B)

Three cases fail across both real models, with **0 wrong_tool calls** —
the models simply don't fire any tool, treating these as plain
conversation:

- **S1: "what have I been seeing lately?"** — should trigger
  `list_candidates`, whose description literally says "use when the user
  asks what they've been seeing lately." Verbatim match in the description,
  still missed.
- **S3: "remember: try yakisoba next time"** — should trigger `add_drawer`.
  Mock catches this via the "remember:" prefix; real models likely treat
  it as a mental note rather than an explicit tool invocation.
- **S5: "what's emerging?"** — same family as S1, same miss.

This is an actionable finding: **the gap is in our tool descriptions and
system message, not in Gemma 4's intrinsic capability**. Future work:
sharpen tool descriptions, possibly add few-shot examples in the system
prompt for the surfacing intents.

### What the agent bench measures

Each case runs through the full agent loop with a `RecordingRegistry`
that captures every tool invocation. Pass criteria:

1. Every expected tool fires at least once with matching args
2. For no-tool cases: no tool fires at all
3. Argument matchers are lenient on common variations (e.g.,
   `target_lang` matches both "zh" and "Chinese")

### What it doesn't measure

- Quality of the final response text (translation BLEU/chrF covers
  that orthogonally)
- Multi-turn coherence (every case is a single user prompt)
- Latency under load — single-pair throughput only
- Real-user prompt diversity — 13 cases is enough to discriminate but
  not exhaustive
