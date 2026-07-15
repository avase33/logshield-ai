"""Drain-style online log template mining.

Drain groups log *messages* into templates using a fixed-depth parse tree, which
makes matching O(depth) instead of O(#templates) — essential at 50k logs/sec. A
message first descends by token count, then by its leading tokens, reaching a
short list of candidate templates; the best match above a similarity threshold is
merged (differing token positions become ``<*>``), otherwise a new template is
created.

We feed Drain the already-masked line (see :mod:`.masking`), so Drain only has to
absorb residual, non-regexable variability (e.g. differing verbs or hostnames),
yielding stable, human-readable templates and a stable ``template_id`` per group.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

WILDCARD = "<*>"


@dataclass
class LogGroup:
    template_id: str
    tokens: list[str]
    count: int = 0

    @property
    def template(self) -> str:
        return " ".join(self.tokens)


@dataclass
class ParseResult:
    template: str
    template_id: str
    is_new: bool
    matched_count: int


def _token_id(tokens: list[str]) -> str:
    key = " ".join(tokens).encode()
    return "tpl_" + hashlib.md5(key).hexdigest()[:12]


class _Node:
    __slots__ = ("children", "groups")

    def __init__(self) -> None:
        self.children: dict[str, _Node] = {}
        self.groups: list[LogGroup] = []


class DrainParser:
    def __init__(self, max_depth: int = 4, sim_threshold: float = 0.4,
                 max_children: int = 100) -> None:
        self.max_depth = max(2, max_depth)
        self.sim_threshold = sim_threshold
        self.max_children = max_children
        self._root: dict[int, _Node] = {}   # keyed by token length
        self._groups: dict[str, LogGroup] = {}

    # ---- similarity -----------------------------------------------------

    @staticmethod
    def _similarity(a: list[str], b: list[str]) -> float:
        if not a:
            return 1.0
        same = sum(1 for x, y in zip(a, b) if x == y or x == WILDCARD or y == WILDCARD)
        return same / len(a)

    def _leaf(self, tokens: list[str], create: bool) -> _Node | None:
        length = len(tokens)
        node = self._root.get(length)
        if node is None:
            if not create:
                return None
            node = _Node()
            self._root[length] = node
        depth = min(self.max_depth, length)
        for i in range(depth):
            tok = tokens[i]
            # numeric-ish tokens funnel into a wildcard branch to bound fan-out
            if any(c.isdigit() for c in tok):
                tok = WILDCARD
            nxt = node.children.get(tok)
            if nxt is None:
                if not create:
                    nxt = node.children.get(WILDCARD)
                    if nxt is None:
                        return None
                else:
                    if len(node.children) >= self.max_children:
                        tok = WILDCARD
                    nxt = node.children.get(tok)
                    if nxt is None:
                        nxt = _Node()
                        node.children[tok] = nxt
            node = nxt
        return node

    # ---- public ---------------------------------------------------------

    def add(self, masked_line: str) -> ParseResult:
        tokens = masked_line.split()
        if not tokens:
            tokens = ["<empty>"]
        leaf = self._leaf(tokens, create=True)
        assert leaf is not None

        best, best_sim = None, -1.0
        for group in leaf.groups:
            sim = self._similarity(group.tokens, tokens)
            if sim > best_sim:
                best, best_sim = group, sim

        if best is not None and best_sim >= self.sim_threshold:
            # merge: positions that differ become wildcards
            merged = [a if a == b else WILDCARD for a, b in zip(best.tokens, tokens)]
            changed = merged != best.tokens
            if changed:
                del self._groups[best.template_id]
                best.tokens = merged
                best.template_id = _token_id(merged)
                self._groups[best.template_id] = best
            best.count += 1
            return ParseResult(best.template, best.template_id, is_new=False, matched_count=best.count)

        tid = _token_id(tokens)
        group = LogGroup(template_id=tid, tokens=list(tokens), count=1)
        leaf.groups.append(group)
        self._groups[tid] = group
        return ParseResult(group.template, tid, is_new=True, matched_count=1)

    @property
    def templates(self) -> list[LogGroup]:
        return list(self._groups.values())

    def template_count(self, template_id: str) -> int:
        g = self._groups.get(template_id)
        return g.count if g else 0
