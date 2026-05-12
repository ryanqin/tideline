"""Tier B intelligence layer — background-callable LLM operations.

This package owns the prompt construction and response parsing for each
intelligence atom (concept matching, ambiguity detection, etc.). Both the
atom bench (`bench/atoms/`) and the production engines (`cluster.py`,
future `naming.py`) import from here, ensuring the bench measures
precisely what the product runs.

Tier B operations are **never user-conversational**. They are invoked by
background sweeps during idle time, accumulate weak signals into stable
state, and surface through the UI reading SQL directly — not through the
agent loop. This is the "weak signal + accumulation" architecture from
DESIGN.md / Obsidian "原子化测量" note.
"""
