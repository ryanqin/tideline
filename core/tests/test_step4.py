"""Step 4 verification: real Gemma 4 runtime via llama-cpp-python.

Tests are skip-marked if the GGUF model file isn't present — we don't block
CI or contributors without the 3GB weights. The agent-loop test below is the
gate that validates our Mock-first strategy: if our fixture format diverges
from real Gemma 4 output, the parser misbehaves and this test reveals it.

To enable Step 4 tests:
  huggingface-cli download unsloth/gemma-4-E2B-it-GGUF \\
      --include 'gemma-4-E2B-it-Q4_K_M.gguf' \\
      --local-dir /Users/hualiangqin/VSCodeWorkspace/personal/tideline/models/
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# llama-cpp-python is in the `real` extra, not `dev` — skip the whole
# module if it isn't installed so `pip install -e './core[dev]'` users
# still get a green pytest run.
pytest.importorskip("llama_cpp")

GEMMA_PATH = Path(
    os.environ.get(
        "TIDELINE_GEMMA_PATH",
        "/Users/hualiangqin/VSCodeWorkspace/personal/tideline/models/gemma-4-E2B-it-Q4_K_M.gguf",
    )
).expanduser()

requires_gemma = pytest.mark.skipif(
    not GEMMA_PATH.exists(),
    reason=f"Gemma GGUF not found at {GEMMA_PATH}",
)


@pytest.fixture(scope="module")
def llama_cpp_runtime():
    if not GEMMA_PATH.exists():
        pytest.skip(f"Gemma GGUF not present at {GEMMA_PATH}")
    from tideline.runtimes.llama_cpp import LlamaCppRuntime

    return LlamaCppRuntime(model_path=str(GEMMA_PATH))


@requires_gemma
def test_real_gemma_loads_and_generates(llama_cpp_runtime):
    """Smoke: model loads via llama-cpp-python and produces real text.

    `len(output) > 0` alone would pass for a prompt echo, which is what a
    broken framing produces — so this also insists the reply isn't just the
    prompt handed back."""
    output = llama_cpp_runtime.generate(
        "<|turn>user\nhello<turn|>\n<|turn>model\n"
    )
    assert isinstance(output, str)
    assert output.strip(), "empty generation"
    assert "<|turn>user" not in output, "model echoed the prompt framing back"


@requires_gemma
def test_protocol_delimiters_are_single_tokens_in_the_shipped_weights():
    """The one guard that turns red the moment the model package changes.

    format.py frames every turn with literals like `<|turn>` and `<|tool_call>`
    and assumes the model sees each as ONE control token, not as a handful of
    subwords it has to spell. That assumption is a property of the GGUF, not of
    our code: Gemma 3's `<start_of_turn>` splits into 7 pieces in Gemma 4's
    vocabulary, so a re-quantized or re-packaged model can quietly invalidate
    the whole protocol while every mock-driven test stays green.

    `<turn|>` being end-of-generation is the other half: it is what makes the
    loop stop cleanly at the end of a model turn instead of running on into the
    next role.

    Criterion fixed before running: every delimiter exactly one token.
    """
    import llama_cpp

    from tideline import format as fmt

    vocab_only = llama_cpp.Llama(
        model_path=str(GEMMA_PATH), vocab_only=True, verbose=False
    )
    delimiters = {
        name: getattr(fmt, name)
        for name in (
            "STRING_DELIM", "TURN_OPEN", "TURN_CLOSE",
            "TOOL_CALL_OPEN", "TOOL_CALL_CLOSE",
            "TOOL_DECL_OPEN", "TOOL_DECL_CLOSE",
            "TOOL_RESPONSE_OPEN", "TOOL_RESPONSE_CLOSE",
        )
    }
    split = {}
    for name, literal in delimiters.items():
        tokens = vocab_only.tokenize(literal.encode(), add_bos=False, special=True)
        if len(tokens) != 1:
            split[name] = (literal, tokens)
    assert not split, (
        f"these protocol delimiters are no longer single control tokens in "
        f"{GEMMA_PATH.name}: {split}. The framing in format.py assumes the "
        f"model reads them as tokens, not as text it has to spell."
    )

    close = vocab_only.tokenize(
        fmt.TURN_CLOSE.encode(), add_bos=False, special=True
    )[0]
    assert llama_cpp.llama_vocab_is_eog(vocab_only._model.vocab, close), (
        f"{fmt.TURN_CLOSE} is no longer end-of-generation; the agent loop "
        f"relies on it to stop at the end of a model turn."
    )


@requires_gemma
def test_real_gemma_full_agent_loop(llama_cpp_runtime):
    """The Mock-first strategy validation: real Gemma + our parser + our
    registry drive an actual tool call when asked.

    This used to assert only that the budget sentinel was absent, which a run
    that never called a tool at all also satisfies — a model replying "Sure, I
    would call the noop tool now." passed it while the protocol was completely
    broken. What it has to check is that the tool RAN.
    """
    from tideline.agent import Agent
    from tideline.tools import NoopTool, ToolRegistry

    calls: list[str] = []

    class _CountingRegistry(ToolRegistry):
        def invoke(self, name, args, context=None):
            calls.append(name)
            return super().invoke(name, args, context)

    registry = _CountingRegistry()
    registry.register(NoopTool)
    result = Agent(llama_cpp_runtime, registry=registry, max_turns=3).run_result(
        "Please call the noop tool."
    )

    assert result.finish_reason == "stop", (
        "Agent ran out of turns — real Gemma likely didn't emit a parseable "
        "tool_call. Check raw output to see how the format diverges."
    )
    assert calls == ["noop"], (
        f"the noop tool was never invoked (calls={calls}); real Gemma's output "
        f"did not parse into a tool call our registry could dispatch."
    )
    assert not result.tool_errors, f"tool dispatch errored: {result.tool_errors}"


def test_runtime_registry_recognizes_llama_cpp_name():
    """Without loading the model, confirm the registry routes 'llama_cpp'.

    If the GGUF is missing, get_runtime instantiates LlamaCppRuntime which
    raises FileNotFoundError — that's the correct error for "name registered,
    file just absent". Any other error means the registry is broken.
    """
    from tideline.runtimes import get_runtime

    if GEMMA_PATH.exists():
        # If the model is present, instantiation will work. Just ensure
        # the call succeeds in returning a runtime instance.
        runtime = get_runtime("llama_cpp")
        assert runtime is not None
    else:
        with pytest.raises(FileNotFoundError):
            get_runtime("llama_cpp")
