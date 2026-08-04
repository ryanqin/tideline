"""The production system message, in one place.

There were three copies of this string — web, CLI, and the agent bench — and
they had already come apart: commit a53c650 (2026-06-08) taught the web copy
to ask for `source_lang` and left the other two behind, with a message saying
"system prompt asks for it", singular. Nothing was red, because nothing was
checking.

That is the whole reason this module exists. It follows the convention
`intelligence/` already set: one prompt per job, imported by everyone who runs
it, with a test asserting they're the same object — the way
`test_source_language.py` pins the A3 atom's prompt to the bench's.

The translate bench (`bench/runner.py`) deliberately does NOT use this. It
measures translation quality under a wider, older instruction and a larger
tool set; its published E2B/E4B numbers are only comparable to each other, so
swapping its prompt would void them. It says so at its own definition.
"""

from __future__ import annotations


# Tideline is a translation engine, not a chatbot. This is tight on purpose:
# one job (translate + record), strict output discipline (no preamble, no
# commentary), no invitation to converse. `source_lang` is asked for because
# the model that just read and translated the text knows the source language
# better than an isolated later detect() does — and it's the key concept
# clustering buckets on (DESIGN §3.3).
TIDELINE_SYSTEM = (
    "You are Tideline, a local-first translation engine. "
    "When the user provides text to translate: first call the add_translation "
    "tool with (original, source_lang, target_lang, translated) — source_lang "
    "is the language the original text is written in — then respond to the user "
    "with only the translated text — no preamble, no quotation marks, no "
    "commentary."
)
