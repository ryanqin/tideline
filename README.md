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
├── android/           ← Kotlin shell, forked from Google AI Edge Gallery (Week 3)
├── bench/             ← latency / accuracy / memory-footprint scripts
├── demo/              ← video script + judge_run.sh one-shot
└── docs/              ← extended notes incl. borrowing diffs
```

---

## Status — honest WIP marker

**As of 2026-04-29: design locked, code not yet written.**

The repo currently contains:
- ✓ Constraint analysis ([DESIGN.md §1](DESIGN.md))
- ✓ Product principle locked ([DESIGN.md §3](DESIGN.md))
- ✓ Six-layer framework + three-layer deployment + memory layering ([ARCHITECTURE.md](ARCHITECTURE.md))
- ✓ Borrowing strategy mapped against three reference repos
- ⏳ `core/`, `cli/`, `android/`, `bench/`, `demo/` — directories scaffolded, code not yet committed

Engineering discipline: **runtime is the last step, not the first.** Mock first, then plug in real Gemma. If the Android shell falls behind, it gets cut and I ship CLI + core only — Reproducibility holds either way.

---

## How to run it locally

> Most of these commands won't work yet — the source tree is still empty as of 2026-04-29. They're the contract I'm building against.

**Prereqs:** Python 3.11+, ~6 GB free disk for Gemma E4B weights, llama.cpp built with Metal/CUDA if available.

```bash
# 1. Install agent core (planned)
cd core && pip install -e .

# 2. Drop Gemma weights into ./models/
#    (gguf for llama.cpp, .task for MediaPipe — see docs/deployment.md)

# 3. Smoke test with MockRuntime — no model required
python -m tideline.cli --runtime mock "hello"

# 4. Real run with local Gemma E4B
python -m tideline.cli --runtime llama_cpp --model models/gemma-4-e4b.gguf

# 5. Judge mode — one shot, deterministic
./demo/judge_run.sh
```

When the HTTP server is up, the Android shell and any other client speak to it over plain JSON. There is no "main" client — CLI and phone are peers.

---

## Tech stack

- **Model:** Gemma 4 E2B (default) / E4B (heavy)
- **Runtimes:** llama.cpp (gguf), MediaPipe LLM Inference (`.task`), Mock (testing)
- **Agent core:** Python 3.11, async loop, SentencePiece for real Gemma tokenization
- **Memory:** ChromaDB (verbatim drawers + semantic search), SQLite (structured tables), temporal KG (time-bounded triples)
- **Transport:** HTTP/JSON between core and clients
- **Mobile:** Kotlin / Android, forked from [Google AI Edge Gallery](https://github.com/google-ai-edge/gallery), MediaPipe LLM runtime on-device
- **Testing:** pytest, MockRuntime for fast loops

Explicit non-goals: post-training, iOS, multi-user, cloud sync, third-party translation APIs, web frontend (unless time permits as a fallback surface).

---

## First milestone

The first end-to-end delivery target for Tideline is the [Kaggle Gemma 4 Good Hackathon](https://www.kaggle.com/competitions/gemma-4-good-hackathon) (deadline 2026-05-18, education / offline track). The hackathon is a forcing function, not the project's identity — Tideline will keep developing past 5/18 as a long-lived local-first agent framework.

---

## Why I'm doing it this way

I'm a CS + Psychology major heading into **Forward Deployed Engineer** roles. I think in mesh topologies — interfaces and seams matter more to me than any single component. This repo is a chance to build an agent framework where the **seams are the product**: `ModelRuntime`, `InputSource`, the capability-indexed tool registry, the four-tier memory with promotion gates. The translator on top is a real thing I'd want to use; the framework underneath is what I want to be able to lift into the next project unchanged.

— Ryan Qin (`ryanqin10@gmail.com`)

---

## License

[Apache-2.0](LICENSE) — aligned with the Gemma 4 model weights license.

> A Chinese version of this README and the design docs is planned for a later pass.
