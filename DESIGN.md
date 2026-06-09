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

Three principles, equally weighted. Every feature decision must align with all three.

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
- **A theme IS a remembered occasion — co-occurrence, not semantic similarity (locked 2026-06-03).** Themes group what was captured *together* (the same session / time window) into "your night in the ramen alley", not what a model judges "related". We tried model relatedness (B7) and a real-model probe showed it can't draw a clean scene boundary on real vocabulary and leaks across domains (ラーメン~駅 = a systematic false yes); co-occurrence is deterministic, scene-level, and exactly the episodic anchor. Relatedness is demoted to garnish (naming, and a possible future "merge two nights that were the same kind of outing"). Concept clustering still merges synonyms; theme clustering just groups co-occurring concepts. A theme is also **single-language** (§3.3): a sitting that mixed two languages becomes two scenes, one per language — never one mixed scene.

### 3.3 The target is always your first language; learning is scoped per language-pair (locked 2026-05-27)

> **Tideline is not a generic A→B translator. It always translates into your first language — everything you meet comes to you in your own tongue, and what recurs settles into a vocabulary that is *yours*. You set your language once; there is no per-translation target to pick.**

**Why this matters:** the product isn't "pick two languages and convert." It's "let the world speak to you in your language." The lived scenario is a *trip or a meeting* — you're translating from **one** non-first-language, across similar scenes, and the things that recur and overlap are what deserve to fuse. A user meeting the *same* concept in two *different* source languages does happen, but it's a rare case we deliberately **don't** chase.

**How to apply:**

- **Two tags on every translation:** (1) **the concept** — what is being translated; and (2) **the direction** — which source language → your language. The *by-language* lens surfaces the direction; the concept is still load-bearing but no longer its own museum lens (the by-concept lens was **retired 2026-06-08** as redundant with the cards deck + by-language) — it now lives inside the cards deck and inside themes (a scene's words are grouped by concept).
- **The direction tag is set when the translation is made.** `add_translation` records `source_lang` inline — the model just read and translated the text, so it knows the source language (with full context, better than an isolated later guess); a deterministic script check (kana → Japanese, hangul → Korean) fills it when the model omits it, and an ISO code the model emits (`ja`) is normalized to the app's one spelling (`Japanese`). A genuinely ambiguous bare word the model can't place stays untagged for a background sweep to backfill. This is what lets a theme group strictly by language (§3.2).
- **No target-language picker.** Translation always renders into the first language (one global setting); the UI offers no per-translation target choice. (The native-language gloss layer was removed for the same reason — the translation *is* the first-language form; a second gloss column was redundant.)
- **Clusters are scoped per language-pair.** A concept cluster fuses same-meaning translations **from one source language**; **one cluster never holds two language-pairs.** 駅 (Japanese) and station (English) both render to 车站, but they are two directions — two clusters, never fused. (Both still live under the same first-language form in the by-language lens; they are just not *one* concept.)
- **Same-concept is settled by construction *within a language*, not by a vote.** The same source word, or two words of the same source language that render to the same first-language form, are the same concept deterministically — no model call, and it forms on a near-zero clustering budget (closing the "budget pit"). The model is reserved for the genuinely ambiguous residue: same-language synonyms that render differently.

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
| 2026-05-27 | Product principle **three**: the target is always the first language; learning is scoped per language-pair | §3.3; no target picker, native gloss removed, two tags (concept + direction) |
| 2026-05-27 | Learnings surface reimagined as a living tidal **shore** (§10) — translate ⇄ shore as two collapsing states of one world; "the tide is theatre, not pedagogy"; the sea = the sediment layer | Extends §3, does not replace it; web first, Android later. Locked + built out (see §10.9) |
| 2026-06-03 | Shore built out: one-world navigation, glint = unopened, varied card shells, drag-to-sink, frosted sand | §10.9 "Built since" |
| 2026-06-03 | Consolidation loop: spaced-repetition review schedule on cards; due cards wash ashore, masked recall self-grades | §10.3; `card.py`, shore + sheet |
| 2026-06-03 | Desk is the hub: museum reachable from home (header doorway) + the shore, not buried behind the shore; museum's way out lands on the desk | §10.7; revises Increment C |
| 2026-06-03 | Concept clustering made **deterministic** and **scoped per language-pair** — same source word, or same first-language rendering within one source language, = same concept with no model vote; a cluster never spans two languages; forms on a near-zero budget (closes the "budget pit") | §3.3; `core/.../cluster.py` |
| 2026-06-03 | **Themes = co-occurrence (capture sessions), not model relatedness** — a real-model B7 probe showed relatedness can't draw a clean scene boundary on real vocab and leaks across domains; co-occurrence is deterministic + scene-level. Theme clustering reworked to group a session's concepts; relatedness demoted to garnish | §3.2; `core/.../cluster.py` |
| 2026-06-08 | **By-concept lens retired** (redundant with the cards deck + by-language) — museum now shelves three ways (cards / language / theme); the shore drops concept "shells" and is purely due-review. **Themes made single-language** (§3.3 extended to themes): a capture session is bucketed by source language, so a mixed-language sitting splits into one scene per language, never a mixed scene | §3.2/§3.3/§10.7/§10.9; web static + `core/.../cluster.py` |
| 2026-06-08 | **source_lang captured at translate time** — `add_translation` records the direction tag inline (the translating model reports it, ISO codes normalized to one spelling, deterministic script fallback), so every translation carries source→target from the moment it's made instead of waiting for a detection sweep; themes then group strictly by that tag | §3.3; `core/.../tools/translation.py`, `intelligence/source_language.py` |
| 2026-06-09 | **Cards deck collapses same-language synonyms** (delivers the §3.3 promise that the concept now lives inside the cards deck) — the cards lens groups by (meaning, source language), so 拉面 ← 中華そば / ラーメン is one tile instead of two duplicate-looking ones; opening it shows the meaning once, then each foreign word with its own moments + sink. A different language with the same meaning stays its own tile (one cluster = one language-pair); the shore still reviews each word on its own | §3.3/§10.7; web static (`learnings.html`, `sheet.js`) |

---

## 10. The shore — a living tidal interface for learning (locked 2026-05-27, web first)

> The learnings surface stops being a top-down list and becomes **a place**: a tidal shore you stand on. Your translations flow into the sea; the tide quietly works while you're away; matured learning washes back up as shells you beachcomb. Warmth and the pull to explore come from the place being *alive* — never from a nudge to visit it.

This **extends, it does not replace**, the three product principles (§3). The translator stays the front door (§3.1); every shell still carries the lived moments it grew from (§3.2); every shell is named in your own language (§3.3). The shore is the visual *home* of the emergence engine, not a new engine.

### 10.1 Why a shore (and why it's safe)

The warmth / exploration goal kept colliding with restraint (§3.1, "an agent that knows when not to talk"). The shore resolves it: **the tide does the surfacing, not a notification.** You are never pinged — you return to the water's edge and find what the tide left. The pull is real, but it is *pull*: you come to it. Same move Ant Forest makes with daily energy, minus the push/FOMO engine we must **not** borrow (no expiring streaks, no "a friend took your…" pressure).

### 10.2 The spatial model — one world, two collapsing states

One continuous vertical world, seen as if standing on the beach: **sky (with the real sun/moon) at the top, the sea across the horizon, wet sand and washed-up shells at your feet.** Two states share that world, and the one you're *not* using collapses to a sliver of itself:

- **Translate — the default front door.** The translator owns the screen. The whole shore collapses to **a single living coastline strip pinned along the bottom** — surf meeting sand, breathing with the tide, maybe a shell glinting. That strip is both the invitation (swipe up to wade in) and the place a finished translation is tossed (down across the surf, into the sea). The translator stays clean and primary; the shore is one gesture away, never standing weight. **The glint is meaningful: when the tide has brought a *new* shell up, the strip catches a faint light** — enough to make you want to look, never a badge or a count. It is an in-app ambient cue only (the shore looks a little more alive), never an OS notification: the pull, not a push (§10.3).
- **Shore — swipe up.** The shore expands to fill the view (sky, sea, sand, shells). The translator collapses to **a few minimal input affordances tucked into a corner** (a compact way to cast a new word — camera / mic / keyboard, per §5), out of the way but one tap from tossing another word into the sea. You can still translate from the shore; it just steps back.

The pivot is the coastline/horizon sliding: **swipe up to wade into the shore, swipe down (or a handle) to return to the desk at the water's edge.** Both transitions need a non-gesture control and must respect reduced motion; only the *expanded* shore animates (the collapsed strip is cheap — matters for battery / Android).

### 10.3 The core principle — the tide is theatre, not pedagogy

The line that keeps the idea honest:

- **What exists as a shell, and which shell is "up" for review, is decided underneath** — by the emergence engine (cluster maturity) and the hidden review schedule (memory science). *Never* by the height of the water.
- **The tide owns the theatre and the cadence:** a newly matured cluster rides in on the next tide; a card due for recall is "carried back up to where you can reach it"; one you didn't tend recedes to rest near the water — **not lost, it returns on the next tide.** No streak, no shame, no "due" count (consistent with the album rule: a schedule may decide *which* memory surfaces, but is never shown as a task).
- So the rhythm is real and **un-clocked** — the ~50-min daily drift means the shore is never the same at the same wall-clock time, so there is no "check in at 9am" alarm to keep — while *what* surfaces stays pedagogically sound.

### 10.4 The sea is the sediment layer

Tie the metaphor to §3.1's substrate: **the sea is the sediment.** Every translation flows into it (every translation is stored; the vast majority stay there forever). A few mature and wash back as shells. So **"throwing something into the sea" has one consistent meaning — *let it rest in the sediment*** — whether it's a fresh translation entering, or a shell you swipe back because you don't need to study it (the sink gesture). The sand is the surfaced / active layer; the sea is the resting layer.

### 10.5 Objects and gestures

- **A creature encodes its relation type**, so the kinds of learning become something you can *see*, not a toggle: a **crab = theme** (a "your Tokyo lunches" scene) and **a single card = a sea-glass drawn from a small varied pool** by a stable hash of its id (so the beach reads varied, not a wall of identical pebbles). *(Concept scallops retired from the shore 2026-06-08 with the by-concept lens; the shore is now purely due-review — cards + scenes — and browsing lives in the museum. Ratified 2026-06-03 — see §10.9.)*
- **Tap a shell → open it into the existing card / masked-recall flow.** The back is still the stack of lived moments (§3.2). The learning interaction is **not** reinvented; the shore is its doorway.
- **Swipe a shell back into the sea → sink** (the one curation gesture; it rests in the sediment, may return).
- **Toss a finished translation down into the surf → it joins the sea / sediment** (the visible form of "every translation writes to sediment").

### 10.6 Time and sky

- **v1 — device local time drives the sky** (dawn / day / golden-hour / night gradients; the golden-hour palette already shipped is simply the *dusk frame* of this cycle) and **the date drives the moon phase.** Zero permissions, ships immediately. The user can also **set time / timezone by hand** (for travel, or just to walk the shore through the day); that manual scrub is also the natural demo + test handle.
- **v2 (optional) — true sunrise/sunset times and moon position** need the user's latitude: a soft, optional ask, in keeping with local-first / privacy. Accuracy is an opt-in, never a gate.

### 10.7 The museum (full collection + the accessible floor)

The shore shows **only what's ashore right now** — which is what fixes overload: a calm few, not a wall of 23 cards. The **complete collection lives in a shell museum**. **The desk is the hub (revised 2026-06-03):** the museum is one tap from home (a header doorway), and the shore is one swipe up — both your learnings views are reachable from the front door, not the museum buried behind the shore. (You can still walk to the museum from inside the shore via its own doorway; the museum's way out lands you back at the desk.) There the existing lenses live — **by card / by language / by theme** — as ordered shelves of shells. The museum also **is the list / reduced-motion / screen-reader fallback**: every shell is a focusable, labelled control, and the museum is a plain, navigable view of the same data. Nothing built so far (cards, by-language, themes) is discarded — it is **re-housed** here.

### 10.8 Build constraints

- **Stylized and calm, not a game.** CSS / SVG / DOM + Pointer Events; no game engine, no physics lib. A quiet shore that's alive, not an arcade.
- **Accessible and lazy.** Shells are real focusable buttons with labels; a list fallback always exists; the scene animates only when expanded; honor `prefers-reduced-motion`.
- **Android-portable.** Keep it DOM / SVG so the same model survives the eventual on-device shell (§8); avoid anything that only lives in a heavy web canvas.

### 10.9 Open (to ratify before/while building)

**Locked (2026-05-27):** shore *below* the translator, the two states collapsing into each other (10.2); device-time sky **+ manual time/timezone override** (10.6); tide = theatre (10.3); sea = sediment (10.4); creature-type → relation-type — **scallop = concept · crab = theme · single card = a varied shell from a pool** (10.5, ratified 2026-06-03); the collapsed translator sits in **a corner** in shore state (10.2); the coastline carries a **faint glint** — in-app ambient, never a push/badge/count (10.2; *now* marks every unopened shell, see Built since).

**Built since (2026-06-03) — shipped, refines the above:**
- **One world, not two tabs (§10.7).** Translate ⇄ shore ⇄ museum is one continuous place reached spatially: the desk is the front door, the shore is one swipe up, and the museum is reached *from* the shore (a doorway up the beach to the shelves); the museum's only way out is back to the open shore. The flat Translate/Museum nav is gone.
- **The glint marks the unopened, not just the new (revises §10.2).** Every shell you haven't opened yet catches the faint light; opening it (tapping) puts its glint out. Session-scoped — still no stored unread count, no badge, no number; the "pull, not push" rule holds.
- **A card is a *varied* shell, not only sea-glass (revises §10.5).** Concept = scallop and theme = crab stay single anchors, but a single card is drawn from a small pool of shell shapes by a stable hash of its id — so the beach of cards reads varied, never a wall of identical pebbles.
- **Sink is also a drag (realizes §10.4/§10.5).** The open water above the surf is the drop target: drag a shell up past the surf and let go and it sinks back into the sediment (a ripple, then it's gone). The sheet's "sink" button stays as the keyboard / screen-reader path.
- **The sand has a frosted grain** — a fine static noise on the near sand, under the shells, for a matte texture (never a blur over a shell).

**Still to design (implementation, owned by the build):** the exact tide curve — how the (device or hand-set) time + lunar phase map to a water level (semidiurnal ≈ 12h25m + ≈ 50-min daily drift + fortnightly spring/neap from moon phase) and to the cadence on which a newly matured shell rides in.
