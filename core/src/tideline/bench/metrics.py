"""Translation evaluation metrics.

Three metrics, each tuned for a different translation length:

- `exact_match` — case-folded, punctuation-stripped string equality.
  Useful for single-word lookups where partial credit is misleading.
- `chrf_score` — character n-gram F-score (sacrebleu). Robust across
  short and long text and morphologically rich languages.
- `bleu_score` — corpus-level BLEU (sacrebleu). Standard MT metric; only
  meaningful at sentence length (degenerates on isolated words).

All scores are returned as floats. exact_match is a fraction in [0, 1];
chrF and BLEU follow sacrebleu's 0-100 convention.
"""

from __future__ import annotations

import re
import unicodedata


_PUNCT_RE = re.compile(r"[\.\,\!\?\;\:\'\"\(\)\[\]\{\}。、！？¡¿]+")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = _PUNCT_RE.sub("", text)
    return " ".join(text.split())


def exact_match(predictions: list[str], references: list[str]) -> float:
    if len(predictions) != len(references):
        raise ValueError(
            f"predictions ({len(predictions)}) and references "
            f"({len(references)}) must have equal length"
        )
    if not predictions:
        return 0.0
    hits = sum(
        1 for p, r in zip(predictions, references) if _normalize(p) == _normalize(r)
    )
    return hits / len(predictions)


def chrf_score(predictions: list[str], references: list[str]) -> float:
    """sacrebleu corpus_chrf. Returns 0-100."""
    from sacrebleu import corpus_chrf

    if len(predictions) != len(references):
        raise ValueError(
            f"predictions ({len(predictions)}) and references "
            f"({len(references)}) must have equal length"
        )
    if not predictions:
        return 0.0
    return corpus_chrf(predictions, [references]).score


def bleu_score(predictions: list[str], references: list[str]) -> float:
    """sacrebleu corpus_bleu. Returns 0-100. Use only on sentence-length text."""
    from sacrebleu import corpus_bleu

    if len(predictions) != len(references):
        raise ValueError(
            f"predictions ({len(predictions)}) and references "
            f"({len(references)}) must have equal length"
        )
    if not predictions:
        return 0.0
    return corpus_bleu(predictions, [references]).score
