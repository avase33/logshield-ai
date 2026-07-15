"""A fast, localized subword tokenizer trained on log syntax.

General-purpose LLM tokenizers are too slow for millions of logs per second. This
is a compact WordPiece/BPE-style tokenizer that learns a vocabulary of subword
units directly from your own log corpus (system syntax like ``timeout``,
``connection``, ``<IP>``, ``eof``), then tokenizes greedily by longest match.

* ``train`` learns merges via a BPE loop over a sampled corpus (deterministic).
* ``encode`` does greedy longest-match subword segmentation with ``##`` marking
  word-internal continuations, falling back to ``[UNK]`` for unknown characters.

No dependencies; the trained vocab is a plain dict, so it (de)serialises trivially.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

_WORD = re.compile(r"<[A-Z]+>|[a-z0-9]+|[^\sa-z0-9]", re.I)

SPECIAL = ["[PAD]", "[UNK]"]


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


@dataclass
class Tokenizer:
    vocab: dict[str, int] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.vocab)

    def _encode_word(self, word: str) -> list[str]:
        # placeholders like <ip> are atomic tokens if in vocab
        if word in self.vocab:
            return [word]
        out: list[str] = []
        i, n = 0, len(word)
        while i < n:
            j = n
            piece = None
            while j > i:
                sub = word[i:j]
                cand = sub if i == 0 else "##" + sub
                if cand in self.vocab:
                    piece = cand
                    break
                j -= 1
            if piece is None:
                out.append("[UNK]")
                i += 1
            else:
                out.append(piece)
                i = j
        return out

    def encode(self, text: str) -> list[str]:
        toks: list[str] = []
        for w in _words(text):
            toks.extend(self._encode_word(w))
        return toks

    def encode_ids(self, text: str) -> list[int]:
        unk = self.vocab.get("[UNK]", 1)
        return [self.vocab.get(t, unk) for t in self.encode(text)]


def train(corpus: Iterable[str], vocab_size: int = 2000, min_freq: int = 2,
          max_merges: int = 4000) -> Tokenizer:
    """Learn a subword vocabulary via a BPE merge loop."""
    word_freq: Counter = Counter()
    for line in corpus:
        for w in _words(line):
            word_freq[w] += 1

    # atomic placeholder + frequent whole-word tokens seed the vocab
    vocab: dict[str, int] = {}
    for tok in SPECIAL:
        vocab[tok] = len(vocab)

    # represent each word as a sequence of chars; BPE merges most frequent pairs
    sequences: dict[tuple[str, ...], int] = {}
    for w, f in word_freq.items():
        if f < min_freq and not (w.startswith("<") and w.endswith(">")):
            continue
        if w.startswith("<") and w.endswith(">"):
            vocab.setdefault(w, len(vocab))          # placeholders are atomic
            continue
        sequences[tuple(w)] = f
        for c in w:                                   # ensure base chars present
            vocab.setdefault(c, len(vocab))
            vocab.setdefault("##" + c, len(vocab))

    merges = 0
    while len(vocab) < vocab_size and merges < max_merges:
        pairs: Counter = Counter()
        for seq, f in sequences.items():
            for a, b in zip(seq, seq[1:]):
                pairs[(a, b)] += f
        if not pairs:
            break
        (a, b), best = pairs.most_common(1)[0]
        if best < min_freq:
            break
        merged = a + b
        vocab.setdefault(merged, len(vocab))
        vocab.setdefault("##" + merged, len(vocab))
        # apply the merge across all sequences
        new_sequences: dict[tuple[str, ...], int] = {}
        for seq, f in sequences.items():
            new_seq: list[str] = []
            i = 0
            while i < len(seq):
                if i < len(seq) - 1 and seq[i] == a and seq[i + 1] == b:
                    new_seq.append(merged)
                    i += 2
                else:
                    new_seq.append(seq[i])
                    i += 1
            new_sequences[tuple(new_seq)] = f
        sequences = new_sequences
        merges += 1

    return Tokenizer(vocab=vocab)
