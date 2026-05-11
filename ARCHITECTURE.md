# ARCHITECTURE — Technical Decomposition

> Product decisions live in [DESIGN.md](DESIGN.md). This document focuses on the **technical implementation skeleton**.

---

## 1. Three-layer deployment architecture (top level)

```
┌────────────────────────────────────────────────────────────┐
│                                                            │
│    ┌──────────────┐                                        │
│    │ Agent Core   │  ←───── HTTP/JSON ─────┐               │
│    │ (Python)     │                        │               │
│    │              │                        ├── CLI         │
│    │  six-layer   │                        │   (dev/debug) │
│    │  framework   │                        │               │
│    └──────────────┘                        ├── Android     │
│         ↑                                  │   shell       │
│         │                                  │   (production)│
│    ┌────┴─────────────┐                    │               │
│    │ ModelRuntime API │                    └── Web play    │
│    │  ├ LlamaCpp      │                       (judge       │
│    │  ├ MediaPipe     │                        fallback)   │
│    │  └ Mock          │                                    │
│    └──────────────────┘                                    │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**Two key abstract interfaces:**
- `ModelRuntime` — multi-runtime mounting (llama.cpp / MediaPipe / Mock for testing)
- `InputSource` — input-source polymorphism (CLI stdin / HTTP request / Android capture)

---

## 2. Six-layer agent framework (the real learning goal)

```
┌──────────────────────────────────────────────────────────┐
│  L6  Rules-as-Data (v2)                                  │
│      threshold rules in rules/*.md, hot-reload           │
├──────────────────────────────────────────────────────────┤
│  L5  Delivery / Events dual channel                      │
│      Delivery → user-visible output                      │
│      Events   → Inspector view / debug stream            │
├──────────────────────────────────────────────────────────┤
│  L4  Memory Tools (memory-as-tools)                      │
│      agent decides what to record via                    │
│      add_drawer / promote_candidate — not harness inject │
├──────────────────────────────────────────────────────────┤
│  L3  Orchestrator                                        │
│      turn-based loop + token-budget throttling           │
│      ToolPermissionContext (deny_names / deny_prefixes)  │
├──────────────────────────────────────────────────────────┤
│  L2  Tool System                                         │
│      capability-indexed registry (by capability class,   │
│      not plugin id)                                      │
├──────────────────────────────────────────────────────────┤
│  L1  Runtime Abstraction                                 │
│      ModelRuntime interface (5–8 method ceiling)         │
│      provider fallback chain                             │
└──────────────────────────────────────────────────────────┘
```

**Why six layers:** each layer has a **clear responsibility boundary** and can be tested / replaced / explained independently — making the "framework feel" legible to judges.

---

## 3. Memory layering (L0–L3)

```
┌────────────────────────────────────────────────────┐
│ L0  Identity                                       │
│     immutable user profile (native lang /          │
│     target lang / level)                           │
├────────────────────────────────────────────────────┤
│ L1  Critical-facts board                           │
│     ~170 tokens auto-injected into every prompt    │
│     holds: active candidates / recent anomalies    │
├────────────────────────────────────────────────────┤
│ L2  Session working memory                         │
│     short-term context within the current dialog   │
├────────────────────────────────────────────────────┤
│ L3  Library (long-term memory)                     │
│   ┌──────────────┐   ┌─────────────────┐           │
│   │ drawers      │→→→│ candidates      │           │
│   │ verbatim     │   │ clustered /     │           │
│   │ 99% stay     │   │ threshold-passed│           │
│   │ here         │   └────────┬────────┘           │
│   └──────────────┘            ↓ user nod           │
│                      ┌─────────────────┐           │
│                      │ cards (SRS)     │           │
│                      │ enters review   │           │
│                      └─────────────────┘           │
└────────────────────────────────────────────────────┘
```

**SRS only serves promoted `cards`** — `drawers` / `candidates` never enter the review system, guaranteeing that the bulk of sediment stays **completely silent** to the user.

---

## 4. Data-layer tech stack

| Component | Purpose |
|---|---|
| **ChromaDB** | Stores verbatim drawers; semantic-search backbone |
| **SQLite** | Structured tables: drawers / candidates / cards / rooms / sessions |
| **Temporal KG** | Triples with `valid_from / valid_to` (time-aware knowledge graph) |
| **SentencePiece** | Real Gemma tokenizer (**no word-split estimation**) |

---

## 5. Three borrowings (standing on shoulders)

### From **OpenClaw**
- ✓ **Capability-indexed tool registry**: tools indexed by **capability class** (e.g. `search` / `translate`), not by plugin id
- ✓ **Delivery vs. Events dual channel**: user-facing output and debug stream are split

### From **Hermes** (most aligned with our product principle)
- ✓ **Memory-as-tools**: agent decides what to remember via explicit tools like `add_drawer`
  - *Why this fits*: the product principle requires "silent sediment"; the agent must hold **active** custody of memory
- ✓ **Skills / rules as markdown data**: threshold rules live in `rules/*.md`, hot-reload supported
- ✓ **Provider fallback chain**: a single entry point tries multiple runtimes by priority

### From **Claw-code**
- ✓ **Turn-based loop + token-budget throttling**: finer than a simple `max_turns`
- ✓ **ToolPermissionContext**: `deny_names` / `deny_prefixes` as stateless predicates
  - *Why*: friendly switch between test mode and demo mode (block dangerous tools, allow whitebox debugging)

### Specific code being borrowed
| Source file | Borrowing strategy |
|---|---|
| `mempalace/knowledge_graph.py` | Almost as-is |
| `mempalace/searcher.py` | Refactor |
| `mempalace/layers.py` | Refactor |
| `mempalace/palace_graph.py` | Reference only |
| AAAK / conversation mining CLI | **Not borrowed** |

---

## 6. Pitfalls deliberately avoided (others have stepped on these)

| Pitfall | This project's mitigation |
|---|---|
| Hermes 594KB single file | **Hard limit <500 lines/file**, CI-enforced |
| OpenClaw 40+ provider hooks | **ModelRuntime interface ceiling: 5–8 methods** |
| OpenClaw 5-layer retry inside orchestrator | **Retry pushed down to runtime layer** |
| Claw-code word-split token estimation | Use **Gemma SentencePiece real tokenizer** |

---

## 7. Repo structure detail

```
tideline/
│
├── core/                      ← Python Agent (75% time)
│   ├── src/tideline/
│   │   ├── runtime/           ← L1: ModelRuntime + impls
│   │   │   ├── base.py        ← interface definition
│   │   │   ├── llama_cpp.py
│   │   │   ├── mediapipe.py
│   │   │   └── mock.py        ← test runtime
│   │   ├── tools/             ← L2: capability-indexed registry
│   │   │   ├── registry.py
│   │   │   ├── memory_tools.py  ← concrete L4 tools
│   │   │   └── translate.py
│   │   ├── orchestrator/      ← L3: turn-based loop
│   │   ├── memory/            ← Memory layering + ChromaDB + SQLite
│   │   ├── rules/             ← L6: hot-reload markdown rules
│   │   └── delivery_events.py ← L5: dual channel
│   ├── server.py              ← HTTP server
│   ├── pyproject.toml
│   └── tests/
│
├── cli/                       ← Python CLI client
│   └── tideline_cli.py
│
├── android/                   ← Kotlin shell (20% time)
│   ├── app/                   ← forked from Google AI Edge Gallery
│   └── README.md
│
├── bench/                     ← reserved for future top-level bench scripts
│   └── (translation accuracy now lives in core/src/tideline/bench/)
│
├── demo/                      ← submission materials
│   ├── video_script.md
│   ├── recording/
│   └── judge_run.sh           ← one-shot run for judges
│
└── docs/                      ← extended docs
    ├── api.md
    ├── deployment.md
    └── borrowings_notes.md    ← detailed three-borrowings diff
```

---

## 8. Startup order (Day 1 of Week 1)

```
 1. Initialize Python package in core/ (pyproject.toml)
 2. Write MockRuntime first (no model dependency, returns fixed strings)
 3. Stub ToolRegistry (one translate tool, mock impl)
 4. Wire Orchestrator's minimal loop: input → tool selection → tool call → output
 5. Write CLI client: echo input through the mock pipeline end-to-end
 6. At this point **no real model has been loaded**, but the entire agent skeleton runs
 7. Then swap in LlamaCppRuntime with real Gemma E4B weights

Key principle: **Runtime is the last step, not the first.**
Get the framework right, then plug in the "engine."
```

---

## 9. Non-goals

- ✗ Post-training / fine-tuning Gemma
- ✗ iOS support
- ✗ Multi-user / account system
- ✗ Cloud sync (conflicts with offline-first)
- ✗ Web frontend (unless time permits, as a judge fallback only)
- ✗ Third-party translation APIs (violates offline principle, **all translation goes through local Gemma**)
