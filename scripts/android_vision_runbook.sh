#!/usr/bin/env bash
#
# On-device vision test runbook for Tideline (S23 Ultra / Snapdragon).
#
# Runs the Phase 5a image-translation probe against a REAL multimodal bundle
# and reads the BENCH latency the ViewModel already logs. The desktop work
# (docs/vision-capability.md) proved Gemma 4 weights can see; this answers the
# two on-device unknowns: does the .litertlm vision tower actually load, and
# what is the S23 vision latency (encoder runs on CPU).
#
# WHY the gemma-3n bundle: the official multimodal .litertlm Google ships is
# Gemma 3n E2B/E4B (open, has the SigLIP vision encoder). A loadable Gemma 4
# .litertlm is not a documented workflow yet. The Android ViewModel is already
# written to Gemma 3n's multimodal format (image-before-text), so this bundle
# is the realistic target — we push it under the filename the code expects.
#
# Prereqs on THIS machine: adb on PATH, S23 connected (`adb devices` shows it),
# the bundle downloaded to models/, the app buildable (Android Studio / gradle).
#
# Run from repo root:  bash scripts/android_vision_runbook.sh

set -euo pipefail
cd "$(dirname "$0")/.."

BUNDLE="models/gemma-3n-E2B-it-int4.litertlm"
DEVICE_MODEL_PATH="/data/local/tmp/gemma-4-E2B-it.litertlm"   # the path MODEL_PATH hardcodes
IMG_DIR="scripts/vision_smoke_assets/jp_real"
DEVICE_IMG_DIR="/sdcard/Pictures/tideline_test"

echo "== 0. preflight =="
command -v adb >/dev/null || { echo "adb not on PATH — install platform-tools"; exit 1; }
adb get-state >/dev/null 2>&1 || { echo "no device — connect S23 + enable USB debugging"; exit 1; }
adb devices -l
[ -f "$BUNDLE" ] || { echo "missing bundle $BUNDLE — run: hf download google/gemma-3n-E2B-it-litert-lm gemma-3n-E2B-it-int4.litertlm --local-dir models/"; exit 1; }

echo "== 1. push the multimodal bundle (3.4 GB — slow, one time) =="
echo "   pushing $BUNDLE -> $DEVICE_MODEL_PATH"
adb push "$BUNDLE" "$DEVICE_MODEL_PATH"

echo "== 2. push the curated test images into device media =="
adb shell mkdir -p "$DEVICE_IMG_DIR"
for f in "$IMG_DIR"/*.jpg scripts/vision_smoke_assets/jp_menu_synth.png; do
  [ -f "$f" ] && adb push "$f" "$DEVICE_IMG_DIR/"
done
# make them show up in the photo picker
adb shell "content call --uri content://media/external/file --method scan_volume --arg external" 2>/dev/null \
  || adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file://$DEVICE_IMG_DIR" >/dev/null 2>&1 || true

echo "== 3. build & install the app =="
./gradlew :app:installDebug

echo "== 4. (manual) in the app: init engine, pick an image from $DEVICE_IMG_DIR, run translate =="
echo "   then watch the BENCH log this terminal will tail:"
echo
echo "   image-then-text OCR prompt is already wired in translateImage()."
echo "   key lines: 'BENCH first_token ttft_ms=' (vision encode + prefill) and"
echo "              'BENCH done total_ms= gen_ms= approx_tok_per_s='."
echo
echo "== 5. tailing BENCH (Ctrl-C to stop) =="
adb logcat -c
adb logcat -s TidelineTranslateVM | grep --line-buffered "BENCH"
