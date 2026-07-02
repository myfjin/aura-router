# router.py — the relevance-router (dynamic-context loop core)

*Built by the overnight self-redirecting loop, 2026-07-01. Bounded target, floored, one wake.*

## What it is
The **context organ** of the continuity hypothesis. A discrete-instance mind has a finite
window, but the record it must stay *itself* across is unbounded. The router is the moving
spotlight:

```
   unbounded STORE  <-->  RELEVANCE-ROUTER  <-->  the WINDOW (held now)
     (everything)        (what to pull, when)       (small, fixed)
```

**Infinite reach, bounded attention.** This is how *"carry less, re-light from the record"*
(truth #3 of the hypothesis) works at the context level: each turn, the router pulls only
the relevant slice of the record into the window.

## Why it's built this way
- **Deterministic + stdlib-only core** (TF-IDF cosine) — no LLM, no network, no credit. Runs
  anywhere; tests are exact and reproducible.
- **Pluggable relevance backend** — the interface is `score(query) -> [float per item]`. Swap
  TF-IDF for a stronger embedder (MiniLM, etc.) without touching the loop.
- **Generic, substrate-free** — point it at *your* store. The engine is public; what you feed
  it is yours. No `state.db`, no patterns, no mesh — nothing private lives in here.

## The pieces
| Class | Role |
|---|---|
| `Item(id, text, meta)` | one unit of the record |
| `Store` | the unbounded source (in-memory core; `from_jsonl`; adapters live separately) |
| `TfidfRelevance` | the default deterministic backend (swappable) |
| `Router.route(query, budget_chars, min_score)` | pull the relevant slice that **fits the budget** (bounded attention, rank order) |
| `Window.step / write_back` | the **loop** — pull a slice each step; write_back so the next step sees new items |

## Usage
```python
from router import Store, Router, Window, Item
store  = Store.from_jsonl("mydata.jsonl")      # or Store([Item(...), ...])
router = Router(store)
slice_ = router.route("what am I looking for now", budget_chars=2000)
for it, sc in zip(slice_.items, slice_.scores):
    print(sc, it.id, it.text[:80])
# the moving spotlight:
w = Window(router)
w.write_back(Item("new1", "something learned this turn"))
w.step("the next situation")                    # sees new1
```

## Status
- **Core: built + self-test green (6/6).** Relevant ranks first; irrelevant excluded; budget
  respected; `write_back` retrievable next step.
- **Next bricks (deferred — need review / their own go):**
  - an **embedding backend** (MiniLM) as a drop-in `score()` — local, but heavier.
  - **adapters** (state.db / chroma / files) — these touch substrate, so they stay *out* of
    this public core by design.
  - the **MCP wrapper** — expose `route()` over MCP so any agent plugs into the same memory.
    This is the "hands" layer; it ships as the public engine once reviewed.

The router is the substance; MCP is the packaging. Substance first — done. Packaging next,
with your eyes on it.
