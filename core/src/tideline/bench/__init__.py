"""Translation accuracy benchmarking for Tideline.

Computes BLEU / chrF / exact-match scores against curated reference pairs.
Data ships with the package under `data/`. Run via:

    python -m tideline.bench --runtime mock                  # infrastructure smoke
    python -m tideline.bench --runtime llama_cpp             # real Gemma 4

The reference translations are textbook-level pairs, not native-speaker
audited. See data/README.md for sourcing caveats.
"""
