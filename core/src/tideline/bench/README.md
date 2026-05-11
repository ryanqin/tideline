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
