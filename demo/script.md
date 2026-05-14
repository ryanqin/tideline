# Tideline — demo video script

> 60-second product demo for the Kaggle Gemma 4 Good Hackathon.
> Anchored to the `bash judge_run.sh` flow so the recording matches what
> a judge running the script themselves would see.

---

## Production targets

- **Length:** 60 seconds (hard cap; under is fine)
- **Aspect ratio:** 16:9, 1920×1080
- **Recording tool:** macOS QuickTime + screen recording, or OBS
- **Audio:** Single voice-over track, room-quiet. Background instrumental optional, mix at –20 dB
- **Cursor:** Highlight cursor (built into macOS Settings → Accessibility → Display)
- **Captions:** Burn-in optional but recommended for silent autoplay

## Pre-recording checklist

```
1. bash install.sh           # one-time
2. rm -f /tmp/tideline-demo.db
3. bash judge_run.sh         # let it prime once; you'll re-launch
4. Verify clusters look good at /learnings (titles like
   "Our night eating noodles together"). If a title is awkward, run
   step 2-3 again — model sampling produces different titles each time.
5. SKIP_PRIME=1 bash judge_run.sh   # now starts in 5s, ready to record
```

---

## Scene-by-scene script (English voice-over)

### 0:00 – 0:08 — Hook

**Visual:** Open browser already at `http://127.0.0.1:8000/`. Translator page visible. Empty input.

**Voice-over:**
> "What if your translator could learn from you, without you doing anything?"

**Caption (optional):** "Tideline — local-first translation that learns by living."

### 0:08 – 0:20 — The 99%: just a translator

**Visual:** Type `sushi` → select Chinese → click Translate. Wait ~2s. "寿司" appears. Then type `metro` → Chinese → "地铁". Then `noodle soup` → Chinese → "面条汤". Three quick translations, no extra UI ceremony.

**Voice-over:**
> "Type. Translate. Move on. That's 99% of how you use it. Everything runs on your laptop — Gemma 4 E2B, no cloud calls, no upload."

### 0:20 – 0:28 — The quiet shift

**Visual:** Brief fade or text overlay: "After a few weeks of casual use…". Cursor moves toward the "Learnings" tab in the nav bar.

**Voice-over:**
> "After a few weeks of casual use, something quietly comes together in the background."

### 0:28 – 0:48 — The reveal: episodic clusters

**Visual:** Click "Learnings" tab. Page loads. Cluster cards stream in:
- "Our night eating noodles together"
- "The night we shared the proposal"
- "Our subway memories from that night"
- (scroll slowly to show 4-5 cards)

Click one cluster card — show the members underneath, each with the original term, translation, and the small italic context line ("menu at Ichiran in Shibuya" etc).

**Voice-over:**
> "It doesn't tell you 'Japanese vocabulary'. It tells you 'the night you ate noodles in Tokyo'. Anki strips knowledge from experience. Tideline does the opposite — every cluster is anchored to the moment it came from."

### 0:48 – 0:60 — Reproducibility close

**Visual:** Cut to terminal. Show `bash judge_run.sh` running, then the browser opening automatically. Show the GitHub URL `github.com/ryanqin/tideline` as text overlay.

**Voice-over:**
> "Open source. One command from a clean checkout to the running demo. Built on Gemma 4 E2B, designed for low-bandwidth, offline-first language learning."

**End frame (hold 2s):** "github.com/ryanqin/tideline" + Apache-2.0 badge.

---

## Chinese voice-over (alternate track)

### 0:00 – 0:08

> "如果你的翻译器能在你毫无察觉的情况下从你的使用里学到东西呢?"

### 0:08 – 0:20

> "输入,翻译,继续做事 —— 99% 的时间你就这样用它。所有计算都在你电脑本地,Gemma 4 E2B,不联网,不上传。"

### 0:20 – 0:28

> "用了几周之后,后台悄悄地有一些东西成形。"

### 0:28 – 0:48

> "它不告诉你'日语词汇',它告诉你'那晚你在东京吃面条的事'。Anki 把知识从经历里剥离,Tideline 反过来 —— 每一个簇都锚到它来自的那个时刻。"

### 0:48 – 0:60

> "开源。一行命令从干净的 checkout 到 demo 跑起来。基于 Gemma 4 E2B 构建,为低带宽、离线优先的语言学习设计。"

---

## Visual style notes

**Color palette:** stick to the live web playground's palette — light neutral background `#fafaf7`, deep blue accent `#1f3a5f`. Don't introduce demo-only branding that won't be in the actual product.

**Pacing:** Translator section (0:08-0:20) should feel calm and quick — three translations in 12 seconds, no rush but no dwell. Learnings section (0:28-0:48) should slow down — let each cluster card sit for ~2 seconds so the viewer can read the title.

**Cursor / typing:** Type at human pace (don't paste). The viewer needs to feel "I could be doing this myself."

**Cuts:** Hard cuts between sections, no fancy transitions. The product is restrained; the video should feel restrained too.

**Music:** Optional. If used, pick something instrumental, slow, ambient. The Tideline product voice is "an agent that knows when not to talk" — the video should match.

---

## Captions / subtitle file

If recording silent (autoplay-friendly version), burn captions matching the voice-over text above. Use a minimal sans-serif like SF Pro or Inter, white text with a thin dark drop shadow for legibility on the off-white UI background.

---

## What this video is NOT

- **Not a tutorial.** Don't explain "click Translate to translate." The product is self-evident; the video sells the *idea*.
- **Not a feature tour.** No reveal of CLI / `--compare 200` / SQL schema / atom bench. Those are for `ARCHITECTURE.md`, not the 60s sell.
- **Not a benchmark deck.** Don't show numbers (E2B 100% B6 accuracy, 1.4× GPU speedup). Those are for the README and judges who go deep.
- **Not a roadmap pitch.** No "next we'll do Android, then iOS, then..." — this is what works *today*.

The 60 seconds buys exactly one thing: the judge thinks "huh, that's actually different from Anki." That single shift is the whole goal.

---

## Sources of footage

| Scene | Source |
|---|---|
| Translator page | Live `bash judge_run.sh` browser at `/` |
| 3 translations | Type live; backend is real Gemma 4 E2B |
| Fade transition | Editor-side overlay; ~1s fade-to-light, then back |
| Learnings page | Live browser at `/learnings` after prime |
| Terminal close | Live screen recording of `bash judge_run.sh` running from clean checkout |
| End frame | Static image / overlay with Tideline name + GitHub URL + Apache-2.0 badge |
