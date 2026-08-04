"""The startup sweep, once.

Every client does the same thing before serving anyone: heal, promote, tag,
cluster. It was written out twice — cli/__main__.py and web/app.py — and the
web copy's own comment said "same shape as cli/__main__.py", which is a
comment doing a function's job. They had already diverged in one way that
matters: the web opened its connection through a helper that sets
`busy_timeout`, the CLI used a bare connect.

The order is load-bearing and the reason lives here now:

  1. heal casing splits BEFORE promoting, so the sweep re-derives counts on
     one canonical row instead of two (PREMIUM and Premium as separate
     candidates). A no-op once healed.
  2. promote, then generate cards — both idempotent, deterministic, and
     careful never to resurrect a card the user sank.
  3. tag source languages BEFORE clustering: concept clusters are scoped per
     language pair (DESIGN §3.3), so the concept sweep reads a field the tag
     sweep has to have filled.
  4. cluster, concept and theme independently.

Steps 3 and 4 call the model, so each is caught separately: a glitch in one
relation must not take out the other, and none of them may take out the
translation flow the user actually came for. They are also expensive, which
is why they run here and never in the per-translation path.

What they do NOT do any more is fail silently. Six bare `except: pass` meant a
user reporting "scenes never get names" left nothing behind to read.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Callable

from tideline.cluster import cluster_sweep
from tideline.promotion import auto_promote_cards, heal_casing_splits, promote_candidates
from tideline.runtime import ModelRuntime
from tideline.tagging import tag_source_langs


logger = logging.getLogger("tideline.boot")


def _soft(step: str, fn: Callable[[], object]) -> bool:
    """Run a model-backed step; report failure instead of swallowing it."""
    try:
        fn()
        return True
    except Exception:
        logger.exception("startup sweep step %r failed — continuing", step)
        return False


def startup_sweep(
    conn: sqlite3.Connection, runtime: ModelRuntime
) -> dict[str, bool]:
    """Bring the database up to date before serving. Returns which model-backed
    steps succeeded, so a caller (or a test) can tell a clean boot from a
    degraded one — previously indistinguishable."""
    heal_casing_splits(conn)
    promote_candidates(conn)
    auto_promote_cards(conn)
    return {
        "tag_source_langs": _soft(
            "tag_source_langs", lambda: tag_source_langs(conn, runtime)
        ),
        "cluster_concept": _soft(
            "cluster_concept", lambda: cluster_sweep(conn, runtime)
        ),
        "cluster_theme": _soft(
            "cluster_theme", lambda: cluster_sweep(conn, runtime, vote_type="theme")
        ),
    }
