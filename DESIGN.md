# DESIGN — Product Decisions

> This document fixes the **product-layer** decisions. Technical implementation lives in [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 1. First milestone constraints — Kaggle Gemma 4 Good Hackathon (verified 2026-04-16)

| Constraint | Requirement |
|---|---|
| Track | Must be one of **health / education / climate** |
| Scenario | Must hit at least one of: **low-bandwidth / offline-capable / privacy-first / infrastructure-poor regions** |
| Judging axes | Vision / Technical Execution / Impact / Reproducibility (four axes) |
| Weighted bias | Real problem + demonstrable functionality + clear use case |

Quoting the Kaggle page:
> offline educational tools for rural classrooms, privacy-preserving medical diagnostic assistants, decentralized energy solutions

---

## 2. Topic selection (locked 2026-04-16)

### **On-device real-time translator + emergent language learning**

Why this hits:
- **education** track ✓
- **offline** + **privacy** + **low-bandwidth** simultaneously ✓ (translation natively requires all three)
- Real user persona is sharp: people working abroad / international students / immigrant families / language learners

---

## 3. Product principles

Two principles, equally weighted. Every feature decision must align with both.

### 3.1 Translator first, learning is byproduct (locked 2026-04-17)

> **This agent is, first and foremost, a real-time on-device translator. Learning is the passive byproduct — only when translation content accumulates and patterns repeat does material worth learning surface.**

**How to apply:**

- **Default UI/interaction = translator.** Don't bind a "learning action" to every word lookup.
  - ✗ "confirm: create card?" prompts
  - ✗ aggressive SRS push
  - ✗ jumping to a "learning path" after each translation
- **Every translation writes to the sediment layer.** The vast majority of entries **stay there forever** and never get promoted.
- **Promotion to `candidates`** only when a threshold is crossed; promotion to `cards` (entering SRS) only with an explicit user nod.
  - Three thresholds: repetition frequency / semantic clustering / explicit user signal
- **Background "night-watch" scan** does silent clustering and candidate generation, but **never push-notifies**.
  - Surfaces only when the user opens the candidates UI panel (not via dialogue).

**Tideline is NOT a chatbot.** The only user input surfaces are: image (camera/OCR), audio (microphone), and keyboard text — all of them are "text to translate," never "things to discuss with the agent." Candidates and drawers are read by the UI directly from SQL; the agent is not a conversational gateway to them.

### 3.2 Episodic anchoring: learning carries its provenance (locked 2026-05-11)

> **Every promoted item — candidate, card, future cluster — retains a back-reference to the original translation moments that contributed to it. Learning is not abstract definitions; learning is episodic memory accumulating into form.**

**Why this matters:** Anki strips context from cards, so the front says "ラーメン" and the back says "ramen" and the result is grinding. Tideline's competitive premise is that **the back of every card is actually a stack of the lived moments where the user encountered the word** — the menu in Shibuya at 14:32, the cooking class on Sunday, the song lyric at midnight. Episodic context is the strongest retrieval anchor in cognitive science; reuniting language items with their original encounter is what makes the learning stick.

**How to apply:**

- **Drawer entries are episodic, not lexical.** Each row carries the original translation, plus available context: source (image / audio / text), surrounding snippet if any, timestamp, optional session grouping.
- **Candidates point back to their drawer evidence.** A `candidate_evidence` join table preserves the full list of contributing drawer entries, not just a count.
- **The UI never shows a candidate as "ramen × 6."** It shows the stack of six moments. The number is incidental; the moments are the point.
- **Tier B intelligence (semantic clustering, cluster naming, summarization) must preserve provenance.** A cluster titled "your Tokyo lunches" links back to every constituent translation row; the cluster is a *view* over evidence, not a replacement for it.

### Demo narrative line

> **"90% of the time it's just a translator. 7% light touches, 2% active harvest, 1% background autonomy."**
> **"And every harvest carries the moment it grew from."**

Headline impression for judges: **"an agent that knows when not to talk, and an agent that remembers where everything came from."** Two complementary statements about what *agency* and *memory* mean in this product.

---

## 4. Why Gemma 4 (and not another model)

| Constraint | Why Gemma 4 satisfies it |
|---|---|
| No post-training (I can't and have no compute) | E2B/E4B works out of the box |
| Local execution, low cost | Phone / Raspberry Pi-class hardware is enough |
| Agent framework essentials | **Native function calling** (Google positions it as agentic-workflow native) |
| Multimodal input | text + image + native audio |
| Long context | 128K |
| Reasoning capacity | Built-in reasoning mode (step-by-step) |
| Multilingual | 35+ languages out of the box, 140+ in pretraining |

---

## 5. Input priority (locked 2026-04-17)

```
 📷 image     ← highest priority (menus / signs / documents)
   ↓
 🎤 audio     ← second (conversations / live translation)
   ↓
 ⌨ text      ← fallback (active lookup)
```

**Why this ordering:** in translation scenarios, the most common case is **"I see something I don't understand"** — image is the first reflex; "I heard something" is second; "I'll type it in" only happens when the first two are inconvenient.

---

## 6. Target platform

### Android **only** (iOS deferred)

| Platform | Default model | Scenario |
|---|---|---|
| Android | **E2B** | Mid-tier phones 24-30 t/s, broad compatibility |
| Android | E4B | High-end gear, multimodal + complex reasoning |

Why no iOS: time budget doesn't allow it, and MediaPipe / LiteRT-LM is more mature on Android.

---

## 7. Milestone judging axes — alignment

| Axis | This project's positioning |
|---|---|
| **Vision** | "An agent that knows when not to talk" — restraint as aesthetic + seamless translate-to-learn gradient |
| **Technical Execution** | Six-layer agent framework + Runtime abstraction + Memory layering + temporal KG |
| **Impact** | Real pain point for language learners; offline coverage for infrastructure-poor regions |
| **Reproducibility** | **Agent Core is pure Python, `pip install .` runs it**; Android is an optional shell |

**Reproducibility is the hidden bonus axis:** lots of hackathon submissions score 0 because judges can't run them. Our Core/Android decoupling guarantees judges **don't need an Android device** to validate the core agent.

---

## 8. Core architecture principle: Core and Android **fully decoupled**

> **(Locked 2026-04-17 — critically important)**

### Why

> The real learning goal is the **agent framework**; the hackathon is a vehicle. If agent code and Android code are entangled, 40% of time will be eaten by Kotlin / UI / MediaPipe configuration — **derailing the learning goal**; and the agent won't be reusable in future projects.

### How to apply

```
┌────────────────────────────────────────────────────────┐
│                                                        │
│   Agent Core (Python)  ←──── HTTP/JSON ────→  Clients  │
│                                                        │
│   "doesn't know where it runs"     ├─ CLI (Python)     │
│                                    ├─ Android shell    │
│   Decoupled via abstract           └─ Web playground   │
│   interfaces:                                          │
│     - ModelRuntime                                     │
│       (LlamaCpp / MediaPipe / Mock)                    │
│     - InputSource                                      │
│       (CLI / HTTP / Android)                           │
│                                                        │
└────────────────────────────────────────────────────────┘
```

- Core and clients are **peers**; there is no "main client"
- Same agent logic runs identically on CLI and on phone
- Android is responsible for: **UI + camera/mic capture + on-device E4B runtime + HTTP client only**
- Judges can `pip install .` + run the CLI demo — **no Android device required**

### Time-budget protection

```
 Week 1-2: 100% Python core         ← agent framework golden window
 Week 3:   start touching Android shell ← only after Core is fully working
 Week 4:   polish + demo recording  ← architecture is frozen
```

If Week 3 reveals Android is over-budget, **cut Android decisively, ship CLI + core only** — Reproducibility scoring is unaffected.

---

## 9. Decision changelog

| Date | Decision | Notes |
|---|---|---|
| 2026-04-16 | Selected Kaggle Gemma 4 Good Hackathon as the first delivery milestone | New repo created |
| 2026-04-16 | Topic: translator + emergent learning | Hits all three scenario constraints |
| 2026-04-17 | Product principle locked: "translator first, learning is byproduct" | Demo narrative line |
| 2026-04-17 | Android-only platform, default E2B | iOS cut |
| 2026-04-17 | Core/Android fully decoupled (three-layer architecture) | Protects agent-learning time |
| 2026-04-20 | Design docs committed | First commit |
| 2026-04-29 | Project formally named **Tideline**, preparing for open source | Decoupling repo identity from the hackathon; positioning as a long-lived agent framework |
