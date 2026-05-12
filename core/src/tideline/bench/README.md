# Tideline Bench Suites

Three orthogonal bench suites share one CLI entry, each measuring a
different facet of model + harness fitness:

- **translate**: BLEU / chrF / exact-match on curated reference pairs.
  Scores text quality.
- **agent**: tool-call correctness on the end-to-end translation flow.
  Scores how reliably the model behaves inside our agent harness with
  the production system message.
- **atoms**: per-operation reliability of every LLM atom Tideline depends
  on, measured via direct prompts (no agent loop). Tier A atoms are
  translation-engine operations (word/sentence translation, source-lang
  ID, output discipline, term extraction). Tier B atoms are intelligence-
  layer operations (concept match, register classification, ambiguity
  detection, theme extraction, complexity tier, episodic title) — these
  measure whether each future Tier B feature is technically viable
  before we build it.

```
python -m tideline.bench                                 # translate (default)
python -m tideline.bench --suite translate
python -m tideline.bench --suite agent
python -m tideline.bench --suite atoms
python -m tideline.bench --suite all                     # all three
python -m tideline.bench --suite agent --per-case        # show pass/fail per case
python -m tideline.bench --suite atoms --per-case        # show failure samples

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

Scores agent-loop behavior on the end-to-end translation flow. Post-
2026-05-11 scope narrowing, this bench measures **one thing**: does the
model, given a user translation request, both produce a correct
translation AND call `add_translation` with correctly-shaped args?

5 canonical cases (T1-T5) cover variations in phrasing ("translate X
to Y", "could you translate 'X' into Y", direction switches) and source
script. Earlier S* (chatbot-style tool selection) and N* (off-task
restraint) cases were retired with the chatbot scope — their roles
moved to the atomic bench's Tier B (direct LLM operations, no harness).

## Metrics

- **task_success_rate**: cases where add_translation fired with shapely args
- **wrong_tool_rate**: cases where some tool fired but not the expected one
- **budget_exhaustion_rate**: cases that hit max_turns without resolving
- **mean num_tool_calls / response_words**: distributional shape

## Reference numbers — E2B vs E4B, 2026-05-11 (post-narrowing)

| Metric | n | E2B | E4B |
|---|---:|---:|---:|
| task_success_rate | 5 | 80.0% | **100.0%** |
| wrong_tool_rate | 5 |  20.0% |   0.0% |
| budget_exhaustion_rate | 5 |   0.0% |   0.0% |
| mean num_tool_calls | 5 | 1.00 | 1.00 |
| mean response_words | 5 | 3.0 | 1.0 |

E4B is uniformly stronger; the same E4B "high gear" pattern from translate
bench holds for tool-call correctness. The single E2B wrong-tool case is
likely an OCR-style off-by-one on the `original` arg.

## Regression caught by this bench (worth recording)

During scope narrowing, an early system-message rewrite said:

> Translate the user's text... Output only the translated text. **After**
> translating, call the add_translation tool.

E2B's agent score dropped from 80% to 20% under this prompt — the model
output the translation, considered the turn done, and skipped the tool
call. Reordering to "first call the add_translation tool, then respond"
restored 80%.

**The atom bench saw nothing wrong** — A1 still scored 100%, because
direct-prompt translation doesn't require a tool call. Only the agent
bench's end-to-end measurement caught the regression. This is exactly
why both benches exist: atoms measure ceiling capability, agent measures
harness-fitness reality.

---

# Atomic Capability Bench

Per-operation reliability for every LLM atom Tideline depends on.
Direct-prompt evaluation — no agent loop, no tool dispatch — so each
score reflects the model's ceiling capability on that atom, isolated
from harness effects.

## Atoms

| ID | Tier | Operation | Why measure it |
|---|---|---|---|
| A1 | A | Translate word/phrase | Foundation of every drawer entry |
| A2 | A | Translate sentence | Captures longer-text cases |
| A3 | A | Source language ID | Lets background tag drawer rows without a `source` field |
| A5 | A | Output discipline (no preamble) | Diagnostic for whether system prompt holds discipline alone |
| A6 | A | Extract translatable term | Future image/audio pipeline needs to pick the term out of noisy OCR |
| B1 | B | Concept match (yes/no) | If reliable, accumulated pair votes drive clustering |
| B2 | B | Register classification | Letting candidate surfacing filter by register |
| B3 | B | Ambiguity detection | Attaching alternative-meaning hints to drawers |
| B4 | B | Common theme (3 terms) | Precursor to B6 — generic theme extraction |
| B5 | B | Complexity tier (word/phrase/sentence) | Routing between A1-style and A2-style processing |
| B6 | B | Episodic title generation | THE memory-anchor atom — names a cluster by lived moment, not generic category |

A4 (tool-call correctness) is not a direct-prompt atom — it's measured
by the agent bench's translation_flow cases above.

## Reference numbers — E2B vs E4B, 2026-05-11

| Atom | n | E2B | E4B | Δ |
|---|---:|---:|---:|---:|
| A1 word translation | 12 | **100.0%** | 100.0% | 0 |
| A2 sentence translation | 10 | 80.0% | 90.0% | +10 |
| A3 source language ID | 12 | **100.0%** | 91.7% | −8 |
| A5 output discipline | 10 | **100.0%** | 100.0% | 0 |
| A6 term extraction | 10 | 70.0% | **90.0%** | +20 |
| B1 concept match | 12 | **100.0%** | 83.3% | −17 |
| B2 register classification | 12 | 83.3% | 83.3% | 0 |
| B3 ambiguity detection | 12 | 91.7% | **100.0%** | +8 |
| B4 common theme | 10 | 70.0% | 60.0% | −10 |
| B5 complexity tier | 12 | 75.0% | **91.7%** | +17 |
| B6 episodic title | 5 | 100.0% | 100.0% | 0 (small sample) |

Wall time (CPU only, ~117 cases): E2B ~35s, E4B ~58s.

## Reading the atomic bench — actionable findings

**Most Tier B atoms are usable at the atom level on both models.**
This is the central finding: even the smaller E2B is ≥70% on every
atom except B4 (theme=60% on E4B). The "weak signal + accumulation"
strategy works — a background sweep that runs B1 (concept match) 1000
times during idle hours will produce a stable similarity graph for
clustering, even at E2B's 83-100% per-call accuracy.

**Per-atom priority for Tier B development:**

| Confidence | Atoms | Implication |
|---|---|---|
| ✅ Ship-ready | A1, A3, A5, B1, B3, B6 (E2B; A1, A2, A5, B3, B5 on E4B) | Can be built into Tier B features now |
| ⚠️ Needs prompt work | A6, B2, B4, B5 | Below 80% on one or both models — prompt tweaks or smaller decomposition first |
| 🚫 Insufficient | (none below 60% on either model) | No atom is fundamentally broken |

**B4 theme extraction at 60-70%** is the weakest cell. For semantic
clustering, this means using B1 pair-votes (100%/83%) is more reliable
than asking B4 to name a cluster — let the cluster emerge from votes,
then maybe use B6 for the title separately.

**B6 episodic title 100% on both is suspect** (only 5 cases, lenient
"contains any episodic token" eval). The atom is the most important
one for the memory-anchor product principle and warrants a larger
case set + stricter eval in a follow-up bench iteration.

**Mock atom scores are infrastructure noise** — Mock isn't a real LLM
and gets accidental hits (e.g., 100% on A6 because Mock echoes input
which contains the expected term). Look at E2B/E4B columns only.

## What the atom bench doesn't measure

- Compositional reliability: P(success at A1) × P(success at A4) gives
  a ceiling estimate for translation_flow, but real models have
  correlated failures the joint probability misses. Agent bench
  measures the actual composition.
- Cross-prompt drift: each atom uses its own SYSTEM_PROMPT. A real
  product run uses ONE system prompt for many atom types — concurrent
  prompt mass could degrade individual atoms.
- Latency: the bench runs CPU only; mobile inference rates differ.
- Cost of false positives: B3 ambiguity at 100% on E4B sounds great,
  but if it ever says "yes" on an unambiguous word, the user sees a
  hint that doesn't make sense. The bench measures aggregate accuracy,
  not failure asymmetry.
