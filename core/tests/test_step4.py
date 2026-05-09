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
    """Smoke: model loads via llama-cpp-python and produces non-empty text."""
    output = llama_cpp_runtime.generate(
        "<|turn>user\nhello<turn|>\n<|turn>model\n"
    )
    assert isinstance(output, str)
    assert len(output) > 0


@requires_gemma
def test_real_gemma_full_agent_loop(llama_cpp_runtime):
    """The Mock-first strategy validation: real Gemma + our parser + our
    registry should drive a noop tool call when asked. If our fixture format
    matches reality, this passes; if not, it reveals exactly what's different.
    """
    from tideline.agent import Agent
    from tideline.tools import NoopTool, ToolRegistry

    registry = ToolRegistry()
    registry.register(NoopTool)
    agent = Agent(llama_cpp_runtime, registry=registry, max_turns=3)

    result = agent.run("Please call the noop tool.")
    assert "[agent] turn budget exhausted" not in result, (
        "Agent ran out of turns — real Gemma likely didn't emit a parseable "
        "tool_call. Check raw output to see how the format diverges from our "
        "fixture assumptions."
    )


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
