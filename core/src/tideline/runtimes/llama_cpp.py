"""Real Gemma 4 runtime via llama-cpp-python (in-process).

Loads a GGUF model in the Python process; generate() returns the raw model
string that format.parse_response() consumes — same shape as Mock's output.

L1 abstraction promise: Mock → LlamaCpp is a registry-only swap. The
ModelRuntime.generate(prompt: str) -> str surface stays unchanged.

Model path resolution (priority):
  1. `model_path` constructor argument
  2. `TIDELINE_GEMMA_PATH` environment variable
  3. `<repo_root>/models/gemma-4-E2B-it-Q4_K_M.gguf` (canonical local install)

The default is resolved relative to this source file, not the current
working directory — so `python -m tideline.cli` from any cwd finds the
GGUF as long as it lives at the canonical repo-root `models/` location.
For wheel installs without a repo, set TIDELINE_GEMMA_PATH explicitly.
"""

from __future__ import annotations

import os
from pathlib import Path

from tideline.runtime import ModelRuntime


# core/src/tideline/runtimes/llama_cpp.py → parents[4] = repo root
_DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parents[4] / "models" / "gemma-4-E2B-it-Q4_K_M.gguf"
)


class LlamaCppRuntime(ModelRuntime):
    def __init__(
        self,
        model_path: str | None = None,
        n_ctx: int = 8192,
        n_gpu_layers: int | None = None,
        max_tokens: int = 512,
        temperature: float = 0.3,
    ) -> None:
        from llama_cpp import Llama  # lazy: only required when this runtime is selected

        path = (
            model_path
            or os.environ.get("TIDELINE_GEMMA_PATH")
            or _DEFAULT_MODEL_PATH
        )

        # Metal full offload (n_gpu_layers=-1) still segfaults on Gemma 4's
        # forward graph as of llama-cpp-python 0.3.23 — likely the PLE /
        # final-norm kernels that llama.cpp upstream tracks in issue #22243.
        # Empirically (Apple M2 Pro, 2026-05-13) n_gpu_layers=28 is the
        # stable upper bound and yields ~1.4-1.9x speedup vs CPU on Tideline
        # workloads with identical output. CUDA backend untested.
        # Default stays 0 (pure CPU) for cross-platform stability — Linux
        # CUDA users may need a different stable cutoff. Override with
        # TIDELINE_GEMMA_GPU_LAYERS=28 to enable Metal acceleration on Mac.
        if n_gpu_layers is None:
            n_gpu_layers = int(os.environ.get("TIDELINE_GEMMA_GPU_LAYERS", "0"))
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(
                f"Gemma GGUF not found at {resolved}. "
                f"Install via: huggingface-cli download unsloth/gemma-4-E2B-it-GGUF "
                f"--include 'gemma-4-E2B-it-Q4_K_M.gguf' --local-dir ./models/, "
                f"or set TIDELINE_GEMMA_PATH to your existing copy."
            )

        self._llm = Llama(
            model_path=str(resolved),
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            chat_format=None,  # let GGUF-embedded jinja template drive framing
            flash_attn=True,  # required: Gemma 4 has mixed V embedding sizes across layers
            verbose=False,
        )
        self._max_tokens = max_tokens
        self._temperature = temperature

    def generate(self, prompt: str) -> str:
        response = self._llm(
            prompt,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            stop=["<turn|>"],  # end of model turn — stops cleanly before next role
        )
        return response["choices"][0]["text"]
