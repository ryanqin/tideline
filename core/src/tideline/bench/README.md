# Translation Accuracy Bench

Three-metric translation evaluation against curated reference pairs.

```
python -m tideline.bench --runtime mock                    # smoke
python -m tideline.bench --runtime llama_cpp               # real Gemma 4
python -m tideline.bench --runtime llama_cpp --tier sentences
```

Install bench dependencies:

```
pip install -e ".[bench]"     # adds sacrebleu
```

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

## Reference numbers — Gemma 4 E2B, 2026-05-11

Captured on Apple Silicon (CPU only, llama-cpp-python 0.3.22, temperature 0.3,
agent full-loop including `add_translation` tool call). Re-run on your hardware
to verify reproducibility:

```
python -m tideline.bench --runtime llama_cpp
```

### Phrases (60 pairs, 5 scenarios × 12 each)

| Scenario | n  | exact_match | chrF |
|---|---:|---:|---:|
| de-en | 12 |  91.7% | 84.7 |
| es-en | 12 |  75.0% | 71.6 |
| fr-en | 12 |  66.7% | 68.6 |
| ja-en | 12 |  83.3% | 74.3 |
| zh-en | 12 |  91.7% | 96.9 |
| **all** | **60** | **81.7%** | **80.4** |

### Sentences (30 pairs, 5 scenarios × 6 each)

| Scenario | n | exact_match | chrF | BLEU |
|---|---:|---:|---:|---:|
| de-en | 6 | 100.0% | 100.0 | 100.0 |
| es-en | 6 |  83.3% |  93.1 |  85.4 |
| fr-en | 6 |  50.0% |  78.2 |  69.0 |
| ja-en | 6 |  66.7% |  69.6 |  53.7 |
| zh-en | 6 |  16.7% |  72.2 |  39.6 |
| **all** | **30** | **63.3%** | **82.4** | **68.3** |

### Reading the numbers

- **zh-en sentence 16.7% EM + 72 chrF** is the classic "low EM, high chrF"
  pattern — Gemma's translations are correct but phrased differently from the
  reference (e.g., "The contract requires signing" vs. "The contract needs to
  be signed"). The chrF score is the more honest signal here.
- **fr-en phrase 66.7% EM** is the weakest single cell — likely driven by
  short polysemous words (e.g., "four" = oven, but also the number) where
  the reference forces one interpretation.
- **Cross-tier drop** (phrases 81.7% → sentences 63.3% EM) is partly
  metric strictness (one wording variation = a miss on the whole sentence,
  not just one word) and partly reflects the genuine difficulty difference.

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
