from abc import ABC, abstractmethod


class ModelRuntime(ABC):
    """Every model backend implements this surface; the agent never sees more."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        raise NotImplementedError
