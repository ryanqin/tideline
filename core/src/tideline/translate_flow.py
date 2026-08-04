"""One capture, start to finish — the policy layer under the transport.

This is what happens when someone hands Tideline a piece of text: stamp it with
its sitting, ask the model, decide whether anything was really translated, and
backfill so the word shows up in learnings straight away. None of it is HTTP,
and all of it used to live inside an HTTP handler — which meant the CLI and the
web ran different amounts of it, and the phone (which has the same flow in
Kotlin) had nothing on this side to be read against.

Two rules are written down here because they are the ones that get lost:

**The target is always your first language.** Not a per-request A→B picker.
That is what separates Tideline from a general translator (DESIGN §3.3), and
it is a product rule, not a default value.

**The ROW is the result.** A capture counts as translated when the tool wrote
it and the guard let it through — never merely because nothing objected, and
never NOT because the loop failed to say goodbye afterwards. Both directions
have been wrong here: reporting a prose reply as recorded showed a translation
while sedimenting nothing, and discarding a recorded translation because the
run overran its turns would throw away a real answer. (DESIGN §3.3: fail
empty, never with a wrong answer.)
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from tideline.agent import Agent
from tideline.intelligence.translation_guard import TranslationOutcome
from tideline.prompts import TIDELINE_SYSTEM
from tideline.runtime import ModelRuntime
from tideline.session import live_session_id
from tideline.tools import AddTranslationTool, ToolRegistry
from tideline.tools.settings import DEFAULT_NATIVE_LANG, get_setting


logger = logging.getLogger("tideline.translate")


@dataclass(frozen=True)
class CaptureResult:
    """What to tell the user, and whether anything was kept.

    `guard` is None on success; otherwise it names why this one was beyond
    reach ("same_as_native" | "not_translated") and the UI localizes it.
    """

    translated: str
    recorded: bool
    guard: str | None = None
    recorded_id: int | None = None


def translate_capture(
    conn: sqlite3.Connection,
    runtime: ModelRuntime,
    text: str,
    *,
    source: str = "text",
    now: datetime | None = None,
) -> CaptureResult:
    registry = ToolRegistry()
    registry.register(AddTranslationTool)
    # Stamp this capture with its sitting's session id, so a burst of live
    # translations co-occurs into a theme (DESIGN §3.2) instead of landing
    # session-less and invisible to the theme sweep.
    session_id = live_session_id(conn, now or datetime.now())
    context: dict = {"db": conn, "source": source, "session_id": session_id}

    native = get_setting(conn, "native_lang", DEFAULT_NATIVE_LANG)
    agent = Agent(
        runtime,
        registry=registry,
        context=context,
        system_message=TIDELINE_SYSTEM,
    )
    try:
        result = agent.run_result(f"translate {text} to {native}")
    except Exception:
        # Nothing inside a run is worth a crash for the person who just typed
        # a word. Whatever broke, this capture was beyond reach.
        logger.exception("translate run failed")
        result = None

    outcome = context.get("translation_outcome")
    recorded_id = context.get("translation_recorded_id")

    if outcome == TranslationOutcome.TRANSLATED.value and recorded_id:
        # A clean run's closing text is the translation; when the run ran out
        # of turns instead, fall back to the row it wrote.
        if result is not None and result.finish_reason == "stop" and result.text:
            translated = result.text
        else:
            logger.warning(
                "translate recorded #%s but did not finish cleanly: %r",
                recorded_id, text,
            )
            translated = context.get("translation_text", "")
        return CaptureResult(
            translated=translated, recorded=True, recorded_id=recorded_id
        )

    if outcome and outcome != TranslationOutcome.TRANSLATED.value:
        guard = outcome  # the guard spoke: same_as_native / echo
    else:
        guard = "not_translated"
        if result is None:
            pass  # already logged with its traceback
        elif result.finish_reason == "budget_exhausted":
            logger.warning("translate exhausted its turn budget: %r", text)
        else:
            logger.warning("translate produced no tool call: %r", text)
    return CaptureResult(translated="", recorded=False, guard=guard)
