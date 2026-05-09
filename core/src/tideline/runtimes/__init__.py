from tideline.runtime import ModelRuntime
from tideline.runtimes.mock import MockRuntime


_AVAILABLE = ("mock", "llama_cpp")


def get_runtime(name: str) -> ModelRuntime:
    if name == "mock":
        return MockRuntime()
    if name == "llama_cpp":
        # Lazy import — llama_cpp may not be installed without the [real] extra
        from tideline.runtimes.llama_cpp import LlamaCppRuntime

        return LlamaCppRuntime()
    available = ", ".join(_AVAILABLE)
    raise KeyError(f"Unknown runtime '{name}'. Available: {available}")


__all__ = ["get_runtime"]
