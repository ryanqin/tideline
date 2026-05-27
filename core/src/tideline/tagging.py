"""Background tagging sweep — backfill source_lang on drawer rows.

The night-watch sweeps so far promote by frequency (promotion) and cluster by
concept (cluster). This one fills in the *source language* of past
translations: `add_translation` records original / target / translated but not
the source language, so rows arrive untagged and the by-language view buckets
them as "Unknown" until this runs.

Deterministic script detection handles non-Latin scripts for free and runs on
every untagged row; only ambiguous Latin-script rows spend model budget, and a
per-row model failure is swallowed so it can never cost the deterministic tags
their commit. native_gloss backfill is a separate cut (it's generation, not
detection — it needs the model).
"""

from __future__ import annotations

import sqlite3

from tideline.intelligence import source_language
from tideline.runtime import ModelRuntime


_DEFAULT_BUDGET = 20


def tag_source_langs(
    conn: sqlite3.Connection,
    runtime: ModelRuntime | None = None,
    budget: int = _DEFAULT_BUDGET,
) -> dict[str, int]:
    """Fill source_lang for translations that lack it.

    Deterministic script detection is free and runs on every untagged row;
    rows it can't resolve (Latin script) fall back to the model, up to `budget`
    attempts per sweep. Returns {'tagged','deterministic','via_model','remaining'}.
    """
    rows = conn.execute(
        "SELECT id, original FROM translations "
        "WHERE source_lang IS NULL OR source_lang = ''"
    ).fetchall()

    deterministic = via_model = model_calls = 0
    for tid, original in rows:
        script = source_language.detect_script(original or "")
        lang = script
        if lang is None and runtime is not None and model_calls < budget:
            model_calls += 1
            try:
                lang = source_language.detect(original or "", runtime)
            except Exception:
                lang = None  # a model glitch on one row must not abort the sweep
            if lang is not None:
                via_model += 1
        if lang is None:
            continue
        conn.execute(
            "UPDATE translations SET source_lang = ? WHERE id = ?", (lang, tid)
        )
        if script is not None:
            deterministic += 1
    conn.commit()

    remaining = conn.execute(
        "SELECT COUNT(*) FROM translations "
        "WHERE source_lang IS NULL OR source_lang = ''"
    ).fetchone()[0]
    return {
        "tagged": deterministic + via_model,
        "deterministic": deterministic,
        "via_model": via_model,
        "remaining": remaining,
    }
