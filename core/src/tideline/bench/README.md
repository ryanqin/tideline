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

30 cases: 6 terms (Latin, accented Latin, kana, kanji, hangul, a
multi-word phrase) × 5 phrasings, of which P1 — `translate X to Y` — is
the one production actually sends. It was 5 cases until 2026-08-04, which
meant one case was 20 points; an instrument that reports in ±20% steps
cannot decide anything about a prompt. Earlier S* (chatbot-style tool selection) and N* (off-task
restraint) cases were retired with the chatbot scope — their roles
moved to the atomic bench's Tier B (direct LLM operations, no harness).

## Metrics

- **task_success_rate**: cases where add_translation fired with shapely args
- **wrong_tool_rate**: cases where some tool fired but not the expected one
- **budget_exhaustion_rate**: cases that hit max_turns without resolving
- **mean num_tool_calls / response_words**: distributional shape

## Reference numbers

**The 2026-05-11 numbers (n=5, E2B 80.0%) are void.** Not because they were
wrong, but because n=5 meant one case was 20 points: that instrument could
only report in ±20% steps, so it could never have told a real change from a
coin flip. It is 30 cases now — 6 terms (Latin, accented, kana, kanji, hangul,
multi-word) × 5 phrasings, with P1 being the phrasing production actually
sends.

### E2B, 30 cases, 2026-08-04

Three variants of the tool declaration, same 30 cases, same weights:

| Metric | no description | full description | **short description** |
|---|---:|---:|---:|
| task_success_rate | 76.7% (23/30) | 83.3% (25/30) | **86.7% (26/30)** |
| wrong_tool_rate | 6.7% | 6.7% | **3.3%** |
| budget_exhaustion_rate | 0.0% | 0.0% | 0.0% |
| mean num_tool_calls | 0.83 | 0.90 | 0.90 |
| declaration tokens | 92 | 263 | **146** |

The first column is where this started: eight field names and the word
`string` eight times, and nothing else. What the tool was FOR and which
arguments were mandatory had been written on the Tool class the whole time and
never reached the model. Adding them, in the shape
`format_function_declaration` emits in the GGUF's own jinja template, bought
two cases.

**Then trimming the description bought another one.** The "full" version was
prose: purpose, plus a paragraph documenting every optional argument. The
short version keeps only what the model cannot get elsewhere — when to call,
and what `source_lang` means — and drops the optional-argument catalogue
entirely; which arguments are mandatory is carried structurally by
`required:[…]`, so saying it again in English was redundant. That is 117 fewer
tokens **and one more case**, with the wrong-tool rate halved.

The lesson is not "shorter is better". It is that the catalogue was costing
tokens to make the model slightly *less* accurate — a tool description is
context the model has to hold while choosing, and documenting arguments it
was never going to need is noise competing with the instruction that matters.

**This measurement was pre-registered.** The decision rule (adopt at ≥+2
cases with no rise in wrong-tool or budget-exhaustion; revert at ≤−2; revert
as underpowered in between) was fixed in writing before the change was
implemented, and the baseline was run twice first to size the noise.

Both baseline runs were identical and both treatment runs were identical.
This sentence has now been wrong twice and is on its third wording, which is
worth saying out loud, because each correction came from measuring rather than
from thinking harder.

It first read "run-to-run variance is 0", implying a noise measurement. It
isn't one: generating the same prompt six times at `temperature=0.3` returns
the same tokens six times, so there is no sampling noise here **to** measure.

That second version was still wrong, in a way the atom bench later exposed:
identical output holds for the same prompt *from the same cache state*. Change
what the runtime processed beforehand and the same prompt can produce a
different answer — enough to move three of twelve atom scores on E2B. These
runs were comparable because both arms walked the same 30 cases in the same
order, and both benches now clear the cache between units, but "deterministic"
was never the right word for it. "Reproducible under a fixed procedure" is.

So the +2 is exactly reproducible under this procedure, which is stronger than
a noisy +2 — and it is also two specific cases flipping, not an estimate of a
distribution. A different quantization, sampler, temperature, or cache state
could land elsewhere, and nothing here speaks to that.

**Where the cost lands, corrected.** The declaration grew from 92 to 263
tokens, which on this Mac's CPU is ~2.9s → ~4.3s for a cold prefill; in a
running server the system prefix is KV-cached across requests, so the
steady-state cost is far smaller (small enough that per-word decode variance
swamped it in measurement). This was first written up as a cost paid
"on-device", which is wrong: **Android has no tool protocol at all** — no
declarations, no `<|tool_call>`, its own plain prompt, and rows written in
Kotlin after the reply lands. The tool-calling loop this bench measures runs
in core only, so both the +2 and the tokens it costs land on the web/CLI
surface, and the phone sees neither.

That reframes what was bought, without changing the decision: a correctness
gain on the reference implementation, paid for on a surface where latency is
not the product promise.

The trim experiment this paragraph used to propose has since been run, with
its criterion fixed in advance (adopt at ≥25/30, keep the long version at
24/30 or below). It returned 26/30 — better than the version it replaced,
at 146 tokens instead of 263 — and reproduced exactly on a second run. Both
halves of the guess were wrong in the same direction: the prose was not
carrying the gain, it was costing a little of it.

Not separable, by construction: `description` cannot be added to the old flat
`{arg:<|"|>string<|"|>}` form without reading as another parameter name, so
shape and content had to move together. If this ever regresses, back out one
at a time.

### E4B at n=30 — and why the aggregate is the wrong number to quote

| Metric | E2B | E4B |
|---|---:|---:|
| task_success_rate | **86.7% (26/30)** | 70.0% (21/30) |
| wrong_tool_rate | 6.7% | **0.0%** |
| mean num_tool_calls | 0.93 | 0.70 |
| mean response_words | 1.5 | 2.2 |

Read alone, that says the bigger model is five cases worse at calling a tool,
which would refute what this file used to claim from n=5 — "E4B is uniformly
stronger; the same high-gear pattern holds for tool-call correctness".

The per-phrasing split says something more useful:

| phrasing | E2B | E4B |
|---|---:|---:|
| `translate X to Y` — **what production sends** | 5/6 | 4/6 |
| `could you translate 'X' into Y` | 6/6 | 6/6 |
| `what is X in Y?` | 5/6 | **0/6** |
| `X -> Y` | 5/6 | 5/6 |
| `Please translate the following into Y: X` | 5/6 | **6/6** |

**The entire five-case gap is one phrasing.** On the other four E4B ties or
wins. Asked "what is 한글 in English?" it answers the question — correctly,
in prose, without calling `add_translation`. Its wrong-tool rate is 0%: it
never picks the wrong tool, it declines to treat an interrogative as an
instruction. E2B doesn't draw that distinction and pattern-matches every
translate-shaped request into a tool call, which here is the behaviour the
harness wants.

Two things follow. The old n=5 claim is refuted, but not by "E4B is worse" —
by "n=5 could not have found this", since those five cases were all
imperative. And **the aggregate is a weighted average whose weights I chose**:
six of thirty cases use a phrasing production never sends, and those six
decide the whole comparison. Quote the split, not the total. (The same caveat
applies, more weakly, to the description A/B above: those deltas are
within-model, but they are aggregates over this same case mix.)

On the phrasing that actually ships, the two models are within one case of
each other — so nothing here argues against E2B carrying translation.

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

## Reference numbers — E2B vs E4B, re-measured 2026-08-07

Every atom now starts with the model's cache cleared (see below). These
numbers are a property of the atom, the prompts and the weights, and nothing
else — verified by running the suite in reverse order and getting all twelve
back identical.

The `mock` column is the zero baseline: Mock is not a model, it answers by
rule, and where a rule happens to align with a judge it scores. **An atom's
real signal is its score minus that column**, and `tests/test_bench_atoms.py`
pins these mock numbers so a future prompt or judge change that moves one has
to say so.

| Atom | n | mock | E2B | E4B | Δ |
|---|---:|---:|---:|---:|---:|
| A1 word translation | 12 | 0.0% | **100.0%** | 100.0% | 0 |
| A2 sentence translation | 10 | 0.0% | 80.0% | 90.0% | +10 |
| A3 source language ID | 12 | 25.0% | **100.0%** | 91.7% | −8 |
| A5 output discipline | 10 | 0.0% | **100.0%** | 100.0% | 0 |
| A6 term extraction | 10 | **100.0%** | 50.0% | **90.0%** | +40 |
| B1 concept match | 12 | 0.0% | **100.0%** | 83.3% | −17 |
| B2 register classification | 12 | 33.3% | 66.7% | **83.3%** | +17 |
| B3 ambiguity detection | 12 | 50.0% | 91.7% | **100.0%** | +8 |
| B4 common theme | 10 | 10.0% | **70.0%** | 60.0% | −10 |
| B5 complexity tier | 12 | 33.3% | 66.7% | **91.7%** | +25 |
| B6 episodic title | 5 | 0.0% | 100.0% | 100.0% | 0 (small sample) |
| B7 topic relatedness | 36 | 0.0% | 83.3% | **91.7%** | +8 |

Wall time (CPU only): E2B ~2:00, E4B ~2:30.

### The bench was measuring the wrong thing, and here is how much

Until 2026-08-07 the suite ran every atom through one shared runtime. A
backend with a KV cache carries state between calls, so an atom's score was a
reading of **the atom plus whatever ran before it**:

| Atom | in-suite (warm) | isolated | |
|---|---:|---:|---|
| A6 (E2B) | 7/10 | 5/10 | −2 |
| B2 (E2B) | 10/12 | 8/12 | −2 |
| B5 (E2B) | 9/12 | 8/12 | −1 |
| B7 (E4B) | 34/36 | 33/36 | −1 |

Same weights, same prompts, same judge. Asked to extract the term from
"Préchauffer le four à 180 degrés", E2B answers `four` from a cold cache and
`Préchauffer` with four atoms' worth of history behind it. Three of twelve
atoms move on E2B; one on E4B.

That is not noise in the usual sense — each reading reproduces exactly, four
runs out of four. It is that floating-point differences from a different cache
state flip a sampling decision on cases where the model is near its decision
boundary. **Cache sensitivity is therefore a readout of how many cases a model
is genuinely unsure about** — five across the table for E2B, one for E4B,
which is its own quiet argument about the two models.

The published table before this fix was internally consistent (2026-08-04
reproduced 2026-05-11 to the decimal) only because nobody had reordered the
suite in between. Adding an atom would have silently moved four scores.

`ModelRuntime.reset()` — a no-op by default, `Llama.reset()` on llama.cpp — is
now called before each atom, and before each case in the agent bench for the
same reason.

### What else moved, and what didn't

**B6's judge was tightened** (2026-08-04). It accepted `"Your Japanese words"`
while correctly rejecting `"Japanese words"` — and B6's own SYSTEM_PROMPT tells
the model to "Lead with … a possessive ('your', 'our')", so the judge was
paying out for copying a surface format instruction onto the exact category
label the atom exists to reject. Neither model's B6 score moved: both were and
remain 100%. The bypass was real but unused. Mock's B6 went 100% → 0%.

**A6's judge was examined and deliberately left alone.** It is a substring
test, so a prompt echo passes it — which is why Mock scores 100%. Scoring the
same real responses under a stricter judge drops E2B 5→3 and E4B 9→5, but
every divergence is the model returning a longer noun phrase *containing* the
gold (`Beurre demi-sel` for `Beurre`, `Datenbank-Verbindung` for `Datenbank`),
and in each case arguably the better answer. The gold span is one defensible
choice among several; the leniency is what absorbs that. See the module
docstring.

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
