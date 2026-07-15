"""Fast hashing embeddings over subword tokens.

The trained tokenizer feeds a signed hashing embedder (the "hashing trick"): each
subword token is hashed into a fixed-width vector with sublinear term weighting,
then L2-normalised. It needs no model and no training beyond the tokenizer, so
embedding a log line is a few hashes — fast enough for the hot path — and cosine
similarity drives the clustering of unknown log variants.
"""

from __future__ import annotations

import hashlib
import math
from typing import Sequence

from .tokenizer import Tokenizer


def _h(token: str) -> int:
    return int.from_bytes(hashlib.md5(token.encode()).digest()[:8], "big")


def l2(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec))
    return [x / n for x in vec] if n else vec


class HashingEmbedder:
    def __init__(self, tokenizer: Tokenizer, dim: int = 64) -> None:
        self.tokenizer = tokenizer
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        counts: dict[int, float] = {}
        for tok in self.tokenizer.encode(text):
            hsh = _h(tok)
            counts[hsh] = counts.get(hsh, 0.0) + 1.0
        vec = [0.0] * self.dim
        for hsh, c in counts.items():
            sign = 1.0 if (hsh >> 61) & 1 else -1.0
            vec[hsh % self.dim] += sign * (1.0 + math.log(c))
        return l2(vec)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))   # inputs are L2-normalised


def centroid(vectors: Sequence[Sequence[float]]) -> list[float]:
    if not vectors:
        return []
    dim = len(vectors[0])
    acc = [0.0] * dim
    for v in vectors:
        for i, x in enumerate(v):
            acc[i] += x
    return l2([x / len(vectors) for x in acc])
