# Tideline

> A local-first translation agent. Translation is the daily surface; learning is what the tide leaves behind.

---

## What & Why

Two stacked goals, both visible up front:

1. **Real goal** — build a reusable, well-shaped **local-first agent framework**. The framework is the thing I want to lift, unchanged, into the next project.
2. **Carrier goal** — ship a real product on top of it: an **on-device real-time translator** where **language learning emerges as a passive side-effect**. The agent stays out of the way until the user's translation history accumulates enough signal to surface something worth learning.

Design slogan I'm holding myself to:

> **90% translator · 7% light touches · 2% active harvest · 1% background autonomy.**
> "An agent that knows when not to talk."

Track alignment for the launch milestone: **education** + **offline / privacy / low-bandwidth** — translation is one of the few use cases that genuinely needs all three at once.

Full product reasoning lives in [DESIGN.md](DESIGN.md). Technical decomposition lives in [ARCHITECTURE.md](ARCHITECTURE.md).

---

## The name

**Tideline** — the line a tide leaves on the beach: shells, driftwood, scraps of seaweed marking where the water has been.

Day-to-day translation works like a tide: it comes, it goes, most of it is used and forgotten. But some things stay — words that keep coming back, grammar that confuses on the second pass, phrasing tied to a specific place. Those are the residue worth learning from.

The agent doesn't *collect* learning material. It just lets translation recede. The learning is whatever the tideline leaves behind.

---

## Constraints (load-bearing, not apologetic)

- **Local inference only.** Gemma 4 **E2B** as default, **E4B** as the heavy gear. Mid-tier Android phones, Raspberry Pi-class hardware. No cloud LLM calls in the hot path.
- **No post-training, no fine-tuning.** Everything is prompt + tool design + memory design on stock weights.
- **No third-party translation APIs.** All translation goes through the local Gemma runtime. Offline-first is non-negotiable.
- **Android only** for the mobile shell. iOS is out of scope for this milestone.
- **<500 lines per file** as a self-imposed CI rule — I've read the codebases (Hermes, OpenClaw) where this discipline broke down, and I'd rather feel the constraint early.

---

## Architecture (current shape)

Three concentric ideas:

**Outer ring — three-layer deployment** so the agent never knows what's running it:

```
  Agent Core (Python)  ←── HTTP/JSON ──→   ├─ CLI client      (dev/debug)
                                            ├─ Android shell   (production)
                                            └─ Web playground  (judge fallback)
```

Two abstract interfaces hold this together: `ModelRuntime` (LlamaCpp / MediaPipe / Mock) and `InputSource` (stdin / HTTP / Android capture).

**Middle ring — the six-layer agent framework** (this is the part I'm actually here to build):

```
  L6  Rules-as-Data            markdown rules, hot-reload
  L5  Delivery / Events        user-facing output vs inspector stream
  L4  Memory-as-Tools          agent decides what to remember, via tools
  L3  Orchestrator             turn loop + token budget + permission ctx
  L2  Tool System              capability-indexed registry
  L1  Runtime Abstraction      5–8 method ceiling, provider fallback
```

**Inner ring — four-layer memory** with the deliberate property that **99% of captured content stays in `drawers` and is never promoted**. SRS only kicks in for `cards` that the user has explicitly nodded at.

```
  L0  identity → L1 critical-facts board → L2 session → L3 library
                                                          ├─ drawers (verbatim, silent)
                                                          ├─ candidates (clustered, threshold-passed)
                                                          └─ cards (SRS-eligible, user-confirmed)
```

Three projects I'm explicitly borrowing shape from, with notes in [ARCHITECTURE.md §5](ARCHITECTURE.md):
- **OpenClaw** — capability-indexed tool registry, Delivery/Events split
- **Hermes** — memory-as-tools, rules-as-markdown, provider fallback chain
- **Claw-code** — turn-based loop with token budgeting, `ToolPermissionContext`

---

## Repo layout

```
tideline/
├── README.md          ← this file
├── DESIGN.md          ← product-layer decisions
├── ARCHITECTURE.md    ← technical decomposition
├── LICENSE            ← Apache-2.0
├── .gitignore
├── core/              ← Python agent (75% of my time budget)
├── cli/               ← Python CLI client — first end-to-end target
├── android/           ← reserved for future in-tree mobile code; the shipped shell lives in a separate fork (see Android section below)
├── bench/             ← latency / accuracy / memory-footprint scripts
├── demo/              ← video script + judge_run.sh one-shot
└── docs/              ← extended notes incl. borrowing diffs
```

---

## Status — honest WIP marker

**Snapshot 2026-05-22:** core + CLI + Android shell are running end-to-end on real hardware. Trajectory continuation past this milestone is the open question.

- ✓ Constraint analysis ([DESIGN.md §1](DESIGN.md))
- ✓ Product principle locked ([DESIGN.md §3](DESIGN.md))
- ✓ Six-layer framework + three-layer deployment + memory layering ([ARCHITECTURE.md](ARCHITECTURE.md))
- ✓ Borrowing strategy mapped against three reference repos
- ✓ **`core/`** — Tier B Phase B1–B4 shipped (B1-vote semantic clustering, B6-driven episodic naming, cross-original multi-vote accumulation, CLI startup sweep). Atom bench + agent bench + translation bench all green on E2B/E4B
- ✓ **`cli/`** — translation flow + memory-tool pressure tests
- ✓ **Web playground** — FastAPI client + vanilla HTML/JS frontend; same three-layer API the Android shell calls
- ✓ **Android shell** — Phase 0-3 shipped on a Galaxy S23 Ultra (fork at [ryanqin/gallery@tideline](https://github.com/ryanqin/gallery/tree/tideline)). See the dedicated section below for the on-device numbers and quality probe.
- ⏳ Android Phase 5 (camera / mic / clustering UI), full demo polish, decision on whether to chase the next on-device hackathon or close out as portfolio

Engineering discipline that survived contact: **runtime is the last step, not the first.** Mock-first kept the core honest; the Android shell only got wired to real Gemma after the Python side passed its atom bench. If the shell had fallen behind, CLI + core would have shipped alone — Reproducibility was never at risk.

---

## Android shell — Phase 0-3 shipped (2026-05-22)

The mobile shell lives in a fork of Google AI Edge Gallery on a dedicated `tideline` branch: **[github.com/ryanqin/gallery@tideline](https://github.com/ryanqin/gallery/tree/tideline)**. The fork reuses Gemma's officially-supported LiteRT-LM runtime path; everything Tideline-specific is under `Android/src/app/src/main/java/com/google/ai/edge/gallery/ui/tideline/` and `…/data/tideline/`. The Python core is untouched.

What's actually working on-device today, on a Galaxy S23 Ultra (Snapdragon 8 Gen 2 for Galaxy, Android 15):

- **Translation flow:** Compose UI → `TidelineTranslateViewModel` → LiteRT-LM `Engine` + `Conversation` → Gemma 4 E2B (Q4) sideloaded at `/data/local/tmp/gemma-4-E2B-it.litertlm`. No HF OAuth dance, no Model Manager — direct API.
- **Prompt parity with Python core:** same `SYSTEM_PROMPT` and `Translate the following to {lang}: {original}` template that drive `core/src/tideline/bench/atoms/a1_word_translation.py` and `a2_sentence_translation.py`. On-phone behaviour matches the atom-bench reference by construction.
- **Persistence via Room/SQLite:** the `translations` table mirrors the Python core's table 1:1 — `id / original / target_lang / translated / source / context_snippet / session_id / created_at`. Future export/import between the two stays trivial.
- **Verified offline.** App was retested in airplane mode end-to-end; inference never reaches the network.

### Latency — GPU backend, plugged in, 20 back-to-back translations

| metric | value |
|---|---|
| Cold-start TTFT (1st translation after engine init) | 343 ms |
| Warm TTFT (n=19) | p50 **152 ms** · p95 174 ms |
| Total wall, short outputs | p50 200 ms · p95 287 ms |
| Stream rate, 5-char kana output | ~140 chars/sec (≈ tok/sec) |
| Thermal throttling across the 20 runs | none observed; TTFT stays in 144–174 ms |

### Quality — 10-word probe (Tideline a1-atom style)

| original | translated | verdict |
|---|---|---|
| hello | こんにちは | ✓ |
| water | 水 | ✓ |
| station | 駅 | ✓ |
| money | お金 | ✓ |
| hospital | 病院 | ✓ |
| airport | 空港 | ✓ |
| coffee | コーヒー | ✓ |
| train | 電車 | ✓ |
| tea | 茶 | ✓ |
| food | 物 | partial (should be 食べ物 / 食料) |
| bathroom | ルーム | wrong (only the "room" katakana, no お手洗い) |

8/10 clean, 1 partial, 1 wrong. The failure mode on `bathroom` is honest: E2B has a quality ceiling on compound / less frequent terms, and the prompt isn't doing any retrieval or repair around it. That ceiling is the price of running entirely on a phone at this latency, not something to hide.

### What's deferred

Camera / mic input, night-watch clustering, candidate promotion, real episodic-session boundaries (current `session_id` is an app-launch UUID, not a real outing), and a polished model-download UX (HF OAuth path is wired in upstream but currently bypassed via `adb push`). All on the Phase 5+ list, gated on whether Tideline's trajectory continues past this milestone or hands off to the next project.

---

## How to run it locally

**Prereqs:** Python 3.11+, ~6 GB free disk for Gemma E4B weights, llama.cpp built with Metal/CUDA if available.

```bash
# 1. Install agent core
cd core && pip install -e .

# 2. Drop Gemma weights into ./models/
#    (gguf for llama.cpp, .task for MediaPipe — see docs/deployment.md)

# 3. Smoke test with MockRuntime — no model required
python -m tideline.cli --runtime mock "hello"

# 4. Real run with local Gemma E4B
python -m tideline.cli --runtime llama_cpp --model models/gemma-4-e4b.gguf

# 5. Web playground (FastAPI + vanilla HTML/JS)
python -m tideline.web
```

For the Android shell, see [its own section above](#android-shell--phase-0-3-shipped-2026-05-22) — it runs Gemma fully on-device via LiteRT-LM, no HTTP roundtrip to the Python core. The HTTP layer in the three-layer architecture is what the web playground rides on; the Android Phase 2 shortcut was to inline the agent core directly in Kotlin (acknowledged trade-off, documented in the section).

---

## Tech stack

- **Model:** Gemma 4 E2B (default) / E4B (heavy)
- **Runtimes:** llama.cpp (gguf), MediaPipe LLM Inference (`.task`), Mock (testing)
- **Agent core:** Python 3.11, async loop, SentencePiece for real Gemma tokenization
- **Memory:** ChromaDB (verbatim drawers + semantic search), SQLite (structured tables), temporal KG (time-bounded triples)
- **Transport:** HTTP/JSON between core and clients
- **Mobile:** Kotlin / Android, fork of [Google AI Edge Gallery](https://github.com/google-ai-edge/gallery) at [ryanqin/gallery@tideline](https://github.com/ryanqin/gallery/tree/tideline), LiteRT-LM `Engine` + `Conversation` API on-device, Room/SQLite for the drawer table
- **Testing:** pytest, MockRuntime for fast loops

Explicit non-goals: post-training, iOS, multi-user, cloud sync, third-party translation APIs, web frontend (unless time permits as a fallback surface).

---

## First milestone

The originally-named delivery target was the [Kaggle Gemma 4 Good Hackathon](https://www.kaggle.com/competitions/gemma-4-good-hackathon) (deadline 2026-05-18, education / offline track). The repo was carried through the design + Python core + web playground in time, but the submission window closed without an entry while attention was held by a separate take-home commitment. The hackathon was always a forcing function rather than the project's identity, and the design slogan held: Tideline is a local-first agent framework first, and the Android shell shipped on its own schedule afterward.

Next on-device surface candidates: the Qualcomm Edge AI Developer Hackathon series (regional events through 2026) and any successor Gemma open-models programme.

---

## License

[Apache-2.0](LICENSE) — aligned with the Gemma 4 model weights license.
