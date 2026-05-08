from tideline.runtime import ModelRuntime
from tideline.runtimes.mock import MockRuntime

_REGISTRY: dict[str, type[ModelRuntime]] = {
    "mock": MockRuntime,
}


def get_runtime(name: str) -> ModelRuntime:
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(f"Unknown runtime '{name}'. Available: {available}")
    return _REGISTRY[name]()


__all__ = ["get_runtime"]
