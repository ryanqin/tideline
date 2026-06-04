"""Probe: does E4B identify the Paris trip's French words as French?

This is the "model-as-function" check for the multilingual demo — source_lang
detection for Latin script is the model's job (kana is deterministic, Latin is
not). We feed each French seed word through detect() and report what comes back.
"""
import sys

sys.path.insert(0, "core/src")

from tideline.intelligence.source_language import detect, detect_script
from tideline.runtimes.llama_cpp import LlamaCppRuntime

# The Paris trip's French terms (all tiers).
FRENCH = [
    "café", "thé", "métro", "pain", "fromage", "addition", "facture",
    "vin", "croissant", "musée", "bonjour", "billet", "merci",
]
# A couple of Japanese ones as a control — these resolve deterministically
# (kana) and must NOT touch the model.
JP_CONTROL = ["ラーメン", "お茶"]

rt = LlamaCppRuntime()  # reads TIDELINE_GEMMA_PATH / _GPU_LAYERS from env

print("=== Japanese control (deterministic, no model) ===")
for w in JP_CONTROL:
    print(f"  {w:10} detect_script -> {detect_script(w)}")

print("\n=== French (Latin script -> model fallback) ===")
ok = 0
for w in FRENCH:
    assert detect_script(w) is None, f"{w} should be ambiguous script"
    got = detect(w, runtime=rt)
    hit = got == "French"
    ok += hit
    print(f"  {w:12} -> {got!r}  {'OK' if hit else 'MISS'}")

print(f"\nFrench detected as French: {ok}/{len(FRENCH)}")
