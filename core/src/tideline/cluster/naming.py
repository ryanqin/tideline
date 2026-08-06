"""Giving a cluster a name a person would recognise (the B6 atom).

Depends on `common`, not on voting — the one function it needed from there is
now where both can reach it.
"""

from __future__ import annotations

import sqlite3

from tideline.cluster.common import _direct_generate
from tideline.intelligence import episodic_title
from tideline.runtime import ModelRuntime
from tideline.tools.settings import DEFAULT_NATIVE_LANG, get_setting


# --- Naming (B6 episodic title) -------------------------------------------


def _unnamed_clusters(conn: sqlite3.Connection, vote_type: str = "concept") -> list[int]:
    rows = conn.execute(
        "SELECT id FROM clusters WHERE (title IS NULL OR title = '') "
        "AND vote_type = ? ORDER BY id",
        (vote_type,),
    ).fetchall()
    return [r[0] for r in rows]


def _cluster_items(conn: sqlite3.Connection, cluster_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT t.original, COALESCE(t.context_snippet, '')
        FROM cluster_members cm
        JOIN translations t ON t.id = cm.translation_id
        WHERE cm.cluster_id = ?
        ORDER BY t.id
        """,
        (cluster_id,),
    ).fetchall()
    return [{"term": r[0], "context": r[1]} for r in rows]


def name_clusters(
    conn: sqlite3.Connection,
    runtime: ModelRuntime,
    vote_type: str = "concept",
) -> dict[str, int]:
    """Generate an episodic title for every unnamed cluster of `vote_type`.

    For each cluster with NULL/empty title, call the B6 atom with the
    members' (original, context_snippet) pairs and write the parsed
    title back. Already-named clusters are left untouched so user-edited
    titles survive a re-run. Both relations use B6 — episodic naming fits
    theme clusters ("your Tokyo lunches") even more naturally than the
    synonym (concept) clusters it was first built for.

    Returns {'named': N, 'skipped': N, 'unparseable': N}.
    """
    named = skipped = bad = 0
    # Titles surface in the UI (shells/crabs on the shore), so they must be in
    # the reader's first language — never the source. The B6 prompt takes the
    # language explicitly; the model is only the garnish on top of that rule.
    native = get_setting(conn, "native_lang", DEFAULT_NATIVE_LANG)
    for cluster_id in _unnamed_clusters(conn, vote_type):
        items = _cluster_items(conn, cluster_id)
        if not items:
            skipped += 1
            continue
        # A theme is a SCENE TYPE — name it as a kind of place (拉面店 → a warm
        # place caption), not as a one-time occasion. Its members share a
        # scene_label; pass it as the strong hint. Concept clusters keep the
        # original episodic B6.
        if vote_type == "theme":
            label_row = conn.execute(
                "SELECT t.scene_label FROM cluster_members cm "
                "JOIN translations t ON t.id = cm.translation_id "
                "WHERE cm.cluster_id = ? AND t.scene_label IS NOT NULL LIMIT 1",
                (cluster_id,),
            ).fetchone()
            scene_label = label_row[0] if label_row else None
            if scene_label:
                system = episodic_title.SCENE_SYSTEM_PROMPT
                prompt = episodic_title.build_scene_prompt(scene_label, items, native)
                # The SCENE prompt asks for a Chinese name, so it needs the
                # parser that speaks Chinese — 名字：preambles, full-width
                # marks, the emoji E2B decorates with, and a cap counted in
                # characters. parse_response would let all four through.
                parse = episodic_title.parse_scene_response
            else:
                system = episodic_title.SYSTEM_PROMPT
                prompt = episodic_title.build_prompt(items, native)
                parse = episodic_title.parse_response
        else:
            system = episodic_title.SYSTEM_PROMPT
            prompt = episodic_title.build_prompt(items, native)
            parse = episodic_title.parse_response
        response = _direct_generate(runtime, system, prompt)
        title = parse(response)
        if not title:
            bad += 1
            continue
        conn.execute(
            "UPDATE clusters SET title = ? WHERE id = ?",
            (title, cluster_id),
        )
        named += 1
    conn.commit()
    return {"named": named, "skipped": skipped, "unparseable": bad}
