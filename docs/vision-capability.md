# On-device vision: Gemma 4 E2B/E4B capability map

**Status:** desktop (llama.cpp) validated 2026-05-28 · on-device (Android / LiteRT-LM) probe wired, real run pending
**Question it answers:** can Tideline's on-device Gemma 4 actually *see* a photo — read its text and grasp its scene — well enough to (a) translate what's on a menu/sign and (b) feed a "warm" episodic index for the emergence loop?

## TL;DR

Yes, the vision path works. Two honest limits to design around:

- **Clean printed text & broad scenes** → both E2B and E4B are good. The "scene gist as episodic warmth index" use is green-lit even on E2B.
- **Handwritten/brush signs, fine-grained object identity (e.g. food types)** → E2B misreads or confidently mislabels; **E4B is materially better**. Use E4B where OCR accuracy or correct vocab labels matter.
- **Weathered/engraved text** → both fail. Out of reach; engineering must tolerate this.

Never make episodic grouping *load-bearing* on exact OCR strings — treat VLM output as the point-of-light enrichment layer, not the skeleton (see DESIGN principle: engineering carries weight, weak LLM only embellishes).

## Two different stacks — do not conflate

| | Desktop / Python core | Android app |
|---|---|---|
| Runtime | llama.cpp (`llama-cpp-python`, `llama-mtmd-cli`) | **LiteRT-LM** (`liblitertlm`, Google AI Edge) |
| Model format | GGUF + separate **mmproj** vision projector | **`.litertlm`** bundle (vision encoder baked in) |
| Variant tested | E2B *and* E4B | **E2B only** (`gemma-4-E2B-it.litertlm`) |
| Vision compute | GPU (Metal) or CPU | LLM on GPU, **vision encoder on CPU** |

Consequence: the `mmproj-F16.gguf` files under `models/vision-e2b|e4b/` are **desktop-only**. The phone gets its vision encoder from inside the `.litertlm` bundle — do **not** push mmproj to the device.

## Capability map (desktop, llama.cpp, real photos)

Test images: synthetic JP menu + 6 real photos sampled from `ThePioneer/japanese-photos` (CC0). Harness: `scripts/vision_smoke.py`.

| Input | Difficulty | E2B (Q4) | E4B (Q4) |
|---|---|---|---|
| Synthetic menu (clean print) | easy | all 14 lines correct | all correct |
| Public sign 「水生動物を…八王子市」 | clean print | good, dropped 「ほたる」 | **full coverage** |
| A-board 「餃子とビールは文化です。」 | brush/handwritten | **misread** (餃子→飲食, dropped ビール, 営業中→喫煙中) | **fully correct** |
| Weathered engraved stele | very hard | hallucinated | hallucinated (different guess) |
| Lake + forest | scene gist | accurate, vivid | accurate, also caught the railing |
| Ropeway + Mt Fuji | multi-object scene | accurate | accurate |
| Food tray (yuba / tofu skin) | fine-grained | **confidently wrong** ("dumplings") | careful ("dumpling or tofu skin"), noticed more |

Speed (Apple Silicon, Metal `-ngl 99`): **E2B ~9–11 s, E4B ~15–21 s per call** (cold load each invocation; ~1.7× for E4B). Not representative of phone latency.

## E2B vs E4B — which to use

- **E2B** — fine for: scene-gist warmth index, clean printed signs, broad object/scene description. It is the Android default today.
- **E4B** — needed for: handwritten/stylized menu OCR, fine-grained object/food naming (where a confident wrong label would *teach the wrong word*). Cost: ~1.7× latency, larger bundle.
- **Neither** handles weathered/engraved/low-contrast text — design fallbacks, don't promise it.

## Reproduce (desktop)

```bash
# 1. multimodal CLI (no llama-cpp-python — 0.3.23 has no Gemma vision handler)
brew install llama.cpp

# 2. vision projector (your LM gguf is already in models/; mmproj is the missing half)
hf download unsloth/gemma-4-E2B-it-GGUF mmproj-F16.gguf --local-dir models/vision-e2b/
hf download unsloth/gemma-4-E4B-it-GGUF mmproj-F16.gguf --local-dir models/vision-e4b/

# 3. run the matrix  (Gemma 4 needs --jinja; harness sets it)
python scripts/vision_smoke.py --gen-sample                    # synth JP menu
python scripts/vision_smoke.py                                 # full matrix
python scripts/vision_smoke.py --image a.jpg b.jpg --prompts scene
TIDELINE_MTMD_NGL=99 python scripts/vision_smoke.py            # Metal (brew build is stable; the old segfault was llama-cpp-python)
```

Two prompts mirror the product's dual goal: `translate` (OCR + translate visible text) and `scene` (one-line gist + 3 objects). The instruct tune emits a `<|channel>thought` reasoning preamble before the `<channel|>` final answer — parse the final segment in product code.

## On-device (Android / LiteRT-LM)

The image path is **already wired** (Phase 5a probe, `TidelineTranslateViewModel.translateImage`):

- `EngineConfig(backend=GPU, visionBackend=CPU, audioBackend=CPU, maxNumImages=1)` — the bundle carries `tf_lite_vision_encoder`; leaving these unset was the original Phase 5a SIGSEGV.
- Image-then-text content order (image first grounds the instruction; text-first collapsed output to a lone 「。」).
- Already logs `BENCH start / first_token ttft_ms / done total_ms gen_ms approx_tok_per_s`.

To run the real-device test:

```bash
adb push gemma-4-E2B-it.litertlm /data/local/tmp/      # vision-capable bundle
# build & install the app, pick a photo in-app, then:
adb logcat -s TidelineTranslateVM | grep BENCH          # read TTFT / total / tok-s
```

What to measure / decide on-device:
1. Does the sideloaded E2B `.litertlm` bundle actually carry a working vision tower (the code's open question)?
2. Vision latency on S23 Ultra — vision encoder is on **CPU**, so expect well above the ~150 ms *text* TTFT. This number decides whether interactive image translation is viable, and whether the ~1.7× cost of an E4B bundle is affordable.
3. Real-photo OCR quality on-device vs the desktop map above (same E2B weakness on brush/handwritten text should reproduce).

## Open questions

- S23 Ultra vision latency (CPU encoder) — **the gating number**, untested.
- Is there an E4B `.litertlm` bundle, and is its quality gain worth the latency on phone?
- thinking-channel handling in the Android path (final-segment parse).
- Episodic anchoring: Android currently stores `contextSnippet=null` for images — wiring the VLM scene gist into `context_snippet` is the feature this capability unlocks (resolves the seed "honest scene" knot: a real VLM-produced gist is honest to store).
