from abc import ABC, abstractmethod


class ModelRuntime(ABC):
    """Every model backend implements this surface; the agent never sees more."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        raise NotImplementedError

    def reset(self) -> None:
        """Forget everything generated so far — for callers that need each
        request judged on its own.

        A backend with a KV cache carries state between calls. That is a
        speed-up in production, where a shared runtime serves request after
        request, and a correctness problem in a benchmark, where it makes a
        score depend on what ran before it. Measured on Gemma 4 E2B: A6 scores
        7/10 when the suite reaches it with four atoms' worth of cache behind
        it and 5/10 when it starts cold — same weights, same prompts, same
        judge, two different answers to "Préchauffer le four à 180 degrés".
        Four of twelve atoms move that way.

        Concrete rather than abstract, and a no-op by default: a backend with
        no cache has nothing to forget, and the many small test stubs that
        implement only `generate` should stay that small.
        """
        return None
