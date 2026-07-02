#!/usr/bin/env python3
"""router.py — the relevance-router: the dynamic-context loop core.

The context organ of the continuity hypothesis. A discrete-instance mind has a finite
window but the record it must stay "itself" across is unbounded. The router is the moving
spotlight: given a situation and a bounded budget, it pulls ONLY the relevant slice of the
record into the window.

    unbounded STORE  <-->  RELEVANCE-ROUTER  <-->  the WINDOW (what's held now)
      (everything)        (what to pull, when)        (small, fixed)

Infinite reach, bounded attention. This is how "carry less, re-light from the record"
(truth #3 of the hypothesis) actually works at the context level.

Design:
- CORE is deterministic + stdlib-only (TF-IDF cosine) — no LLM, no network, no credit — so
  it runs anywhere and its tests are reproducible.
- The relevance backend is PLUGGABLE: swap TF-IDF for a stronger embedder (MiniLM, etc.)
  without touching the loop.
- Generic by design: point it at YOUR store. It carries no substrate — the engine is
  public, what you feed it is yours.

Run:  python3 router.py        # self-test
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

_WORD = re.compile(r"[a-z0-9]+")


def _tok(text: str) -> list[str]:
    return _WORD.findall(text.lower())


# ── the record: an unbounded source of items ───────────────────────────────
@dataclass
class Item:
    id: str
    text: str
    meta: dict = field(default_factory=dict)


class Store:
    """An unbounded source of items. In-memory core; load from jsonl. Source-agnostic —
    adapters for state.db / chroma / files live SEPARATELY so this core stays clean and
    substrate-free (the engine is public; the substrate is not)."""

    def __init__(self, items: list[Item] | None = None):
        self.items: list[Item] = list(items or [])

    @classmethod
    def from_jsonl(cls, path, id_key: str = "id", text_key: str = "text") -> "Store":
        items = []
        for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = o.get(text_key)
            if not t:
                continue
            items.append(Item(str(o.get(id_key, i)), t,
                              {k: v for k, v in o.items() if k != text_key}))
        return cls(items)

    def add(self, item: Item) -> None:
        self.items.append(item)

    def __len__(self) -> int:
        return len(self.items)


# ── deterministic relevance: TF-IDF cosine (stdlib, no deps, reproducible) ──
class TfidfRelevance:
    """The default, dependency-free relevance backend. Deterministic → tests are exact.
    Interface = score(query) -> [float per item]. Any backend with this shape is swappable
    (an embedding backend is a drop-in replacement; the loop never changes)."""

    def __init__(self, items: list[Item]):
        self.items = items
        self.df: dict[str, int] = {}
        self.doc_tf: list[dict[str, int]] = []
        for it in items:
            tf: dict[str, int] = {}
            for w in _tok(it.text):
                tf[w] = tf.get(w, 0) + 1
            self.doc_tf.append(tf)
            for w in tf:
                self.df[w] = self.df.get(w, 0) + 1
        self.N = max(1, len(items))
        self.doc_vec = [self._vec(tf) for tf in self.doc_tf]
        self.doc_norm = [math.sqrt(sum(v * v for v in dv.values())) or 1.0 for dv in self.doc_vec]

    def _idf(self, w: str) -> float:
        return math.log((self.N + 1) / (self.df.get(w, 0) + 1)) + 1.0

    def _vec(self, tf: dict[str, int]) -> dict[str, float]:
        return {w: c * self._idf(w) for w, c in tf.items()}

    def score(self, query: str) -> list[float]:
        qtf: dict[str, int] = {}
        for w in _tok(query):
            qtf[w] = qtf.get(w, 0) + 1
        qv = self._vec(qtf)
        qn = math.sqrt(sum(v * v for v in qv.values())) or 1.0
        out = []
        for i, dv in enumerate(self.doc_vec):
            dot = sum(qv.get(w, 0.0) * dv.get(w, 0.0) for w in qv)
            out.append(dot / (qn * self.doc_norm[i]))
        return out


# ── the router: pull the relevant slice that fits the budget ───────────────
@dataclass
class Slice:
    items: list           # pulled items, most-relevant first, within budget
    scores: list
    used_chars: int
    budget_chars: int


class Router:
    """route(query, budget) -> the relevant slice that FITS the budget. Bounded attention:
    fill the window with the highest-relevance items up to budget_chars, in rank order."""

    def __init__(self, store: Store, relevance=None):
        self.store = store
        self.rel = relevance or TfidfRelevance(store.items)

    def route(self, query: str, budget_chars: int = 2000, min_score: float = 0.0) -> Slice:
        scores = self.rel.score(query)
        order = sorted(range(len(self.store.items)), key=lambda i: -scores[i])
        picked, ps, used = [], [], 0
        for i in order:
            if scores[i] <= min_score:
                break
            t = self.store.items[i].text
            if picked and used + len(t) > budget_chars:
                break                      # window full — stop (keep what fits, in rank order)
            picked.append(self.store.items[i])
            ps.append(round(scores[i], 4))
            used += len(t)
            if used >= budget_chars:
                break
        return Slice(picked, ps, used, budget_chars)


class Window:
    """The moving spotlight = the dynamic-context LOOP. Each step pulls a fresh slice for
    the situation; write_back adds new items so the next step can see them. This is the
    'infinite context loop': the window moves over a store that never has to fit inside it."""

    def __init__(self, router: Router):
        self.router = router

    def step(self, situation: str, budget_chars: int = 2000) -> Slice:
        return self.router.route(situation, budget_chars)

    def write_back(self, item: Item) -> None:
        self.router.store.add(item)
        # the core rebuilds relevance so the new item is visible next step; a production
        # backend caches/updates incrementally (adapter concern, not core).
        self.router.rel = TfidfRelevance(self.router.store.items)


# ── self-test: the run-gate on the router core ─────────────────────────────
def _selftest() -> bool:
    ok, total = 0, 0

    def check(desc, cond):
        nonlocal ok, total
        total += 1
        ok += bool(cond)
        print(f"  {'OK ' if cond else 'XX '} {desc}")

    store = Store([
        Item("d1", "the circuit breaker opens after repeated failures and recovers on a timeout"),
        Item("d2", "a write-ahead log records every mutation before applying it for durability"),
        Item("d3", "gossip protocol spreads membership updates across distributed nodes"),
        Item("d4", "a token bucket rate limiter refills tokens at a fixed rate over time"),
        Item("d5", "the cat sat quietly on the warm windowsill in the afternoon sun"),
    ])
    r = Router(store)

    s = r.route("how does a rate limiter refill tokens", budget_chars=500)
    check(f"relevant item ranks first (got {s.items[0].id})", s.items and s.items[0].id == "d4")
    check("irrelevant prose (d5) not top", not s.items or s.items[0].id != "d5")

    # bounded attention: tiny budget → at most the single best item fits
    tiny = r.route("distributed membership gossip", budget_chars=40)
    check(f"budget respected: used<=budget+one-item ({tiny.used_chars} for 40)", len(tiny.items) <= 1)
    check("tiny-budget slice still returns the best match (d3)", tiny.items and tiny.items[0].id == "d3")

    # a totally unrelated query with min_score gate → nothing forced in
    none = r.route("quantum chromodynamics lagrangian", budget_chars=500, min_score=0.05)
    check(f"low-relevance query pulls little/nothing ({len(none.items)} items)", len(none.items) <= 1)

    # the LOOP: write_back makes a new item retrievable next step
    w = Window(r)
    w.write_back(Item("d6", "kafka consumer groups rebalance partitions when members join or leave"))
    s2 = w.step("kafka partition rebalance among consumers", budget_chars=500)
    check("write_back item retrievable next step (d6)", s2.items and s2.items[0].id == "d6")

    print(f"\naccuracy: {ok}/{total} = {100 * ok // total}%")
    return ok == total


def main():
    raise SystemExit(0 if _selftest() else 1)


if __name__ == "__main__":
    main()
