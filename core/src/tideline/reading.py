"""Reading the sediment back out — the query layer under the views.

Candidates and clusters are shaped for display here, not in the HTTP handlers,
because both shapes are shared by more than one view and the derivations
(which language a candidate belongs to, which scene label a theme hangs on)
must happen in exactly one place. Nothing in here knows about HTTP.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


# Candidates with their source language derived live from the translations they
# came from. The single source of truth for language metadata is `translations`;
# candidates/cards/clusters never carry a copy, they derive it — so a re-detect
# on the drawer flows everywhere for free.
_CANDIDATES_SQL = """
    SELECT id, original, target_lang, translated, occurrence_count,
        (SELECT t.source_lang FROM translations t
         WHERE t.original = candidates.original
           AND t.target_lang = candidates.target_lang
         ORDER BY t.id DESC LIMIT 1) AS source_lang
    FROM candidates ORDER BY occurrence_count DESC, original
"""


def fetch_candidates(
    conn: sqlite3.Connection, limit: int | None = None
) -> list[dict[str, Any]]:
    """The emergent vocabulary, frequency-ranked. Shared by /api/candidates
    (flat list) and /api/clusters/by-language (the same rows, bucketed by
    source language) so the language derivation lives in exactly one place."""
    sql = _CANDIDATES_SQL
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql).fetchall()
    return [
        {"id": cid, "original": o, "source_lang": sl, "target_lang": tl,
         "translated": tr, "count": cnt}
        for cid, o, tl, tr, cnt, sl in rows
    ]


def parse_region(raw: str | None) -> list[float] | None:
    """A stored word box ("[x0,y0,x1,y1]" normalized) as a list, or None —
    malformed JSON degrades to no mask, never to an error."""
    if not raw:
        return None
    try:
        box = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if isinstance(box, list) and len(box) == 4:
        try:
            return [float(v) for v in box]
        except (TypeError, ValueError):
            return None
    return None


def fetch_clusters(
    conn: sqlite3.Connection, vote_type: str
) -> list[dict[str, Any]]:
    """Clusters of one relation, each with its members. Shared by
    /api/clusters (vote_type='concept' — synonym aggregation) and /api/themes
    (vote_type='theme' — B7 relatedness). Scoping by vote_type is what keeps
    the two relations' clusters out of each other's view now that they share
    the clusters table."""
    rows = conn.execute(
        "SELECT id, title FROM clusters WHERE vote_type = ? ORDER BY id",
        (vote_type,),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for cid, title in rows:
        members = conn.execute(
            """
            SELECT t.original, t.translated, t.context_snippet, t.source_lang,
                   t.scene_label, t.id, t.source_image IS NOT NULL, t.source_region,
                   t.target_lang
            FROM cluster_members cm
            JOIN translations t ON t.id = cm.translation_id
            WHERE cm.cluster_id = ?
            ORDER BY t.id
            """,
            (cid,),
        ).fetchall()
        # A theme IS one scene type, so all its members share a scene_label —
        # the stable key its review schedule hangs on (theme_review), unlike the
        # cluster id which the night-watch sweep rebuilds. Concept members span
        # scene types, so this is only meaningful (single-valued) for themes.
        scene_labels = {m[4] for m in members if m[4]}
        scene_label = next(iter(scene_labels)) if len(scene_labels) == 1 else None
        result.append({
            "id": cid,
            # A theme shows its B6 scene-type name when the night-watch has
            # named it (a warm caption for the kind of place); until then it
            # falls back to the plain scene label. scene_label stays the key.
            "title": title or scene_label,
            "scene_label": scene_label,
            "members": [
                # `id`/`has_image` point recall back at the captured material
                # (the photo behind /api/translations/{id}/image), so opening
                # a scene can show what was actually lived, not just words.
                # target_lang so the shore can fold a word card into the
                # scene that already carries it, keyed the same way on both
                # ends (DESIGN §10.5.1 rule 4).
                {"original": o, "translated": tr, "context": ctx or "",
                 "source_lang": sl, "target_lang": tl, "id": tid,
                 "has_image": bool(img), "region": parse_region(region)}
                for o, tr, ctx, sl, _label, tid, img, region, tl in members
            ],
        })
    return result
