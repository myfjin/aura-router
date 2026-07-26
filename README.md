# aura-router

**A hypothesis about how a discrete-instance mind stays continuous — and a working engine
that embodies it.**

An LLM has no memory between calls; each turn it is lit fresh, thinks, and goes dark. So
what does *continuity* mean for something that flickers? Most answers overclaim —
*"persistent memory," "the AI remembers you forever."* This repo takes the honest route:

> **Continuity without persistence** — a discrete mind holds a continuous *thread* by
> carrying a compressed, re-igniteable record and re-lighting from it each cycle.
> Continuity by *carrying*, not by *never dying*.

Full hypothesis (distance idea → four truths → the honest boundary → what would prove or
falsify it): **[theory/HYPOTHESIS.md](theory/HYPOTHESIS.md)**.

The hard part of that hypothesis is *"carry less, re-light from the record."* This repo is
that part, built.

---

## The engine: infinite reach, bounded attention

A discrete mind has a **finite window** but an **unbounded record**. The router is the
moving spotlight between them:

```
   unbounded RECORD  <-->  RELEVANCE-ROUTER  <-->  the WINDOW (held now)
     (everything)         (what to pull, when)       (small, fixed)
```

Each turn, it pulls only the *relevant slice* of the record into the window — as much as a
budget allows, most-relevant first. Point it at **your** store; it carries no data of its
own.

- **`engine/router.py`** — the core. `Store · Router.route(query, budget) · Window`.
  Deterministic, **stdlib-only** (TF-IDF cosine), zero network, zero dependencies. The
  relevance backend is pluggable (swap in an embedding model without touching the loop).
- **`server/aura_router_mcp.py`** — the same engine wrapped as an **MCP server**, so any
  MCP-speaking agent can plug into the moving-spotlight memory over the standard protocol.
  Router = the decision (*what to pull*); MCP = the transport (*how it's reached*).

## Quickstart

**The engine, standalone (no dependencies):**
```python
from engine.router import Store, Router

store  = Store.from_jsonl("your_record.jsonl")   # {"id": "...", "text": "..."} per line
router = Router(store)

result = router.route("what matters now", budget_chars=2000)
for item, score in zip(result.items, result.scores):
    print(round(score, 3), item.id, item.text[:80])
```

**The MCP server:**
```bash
pip install -r requirements.txt
AURA_ROUTER_STORE=your_record.jsonl python server/aura_router_mcp.py   # stdio MCP server
```
Tools exposed: `route(query, budget_chars, min_score)`, `add_item(id, text)`, `store_info()`.
Runs out of the box against a bundled demo store if `AURA_ROUTER_STORE` is unset.

## v1.2 — auto-recall at wake, and the experiment behind it

We tested the honest question — *drop a fresh instance cold with only its substrate:
does it know what it was mid-doing?* — on our own setup. Finding: identity
reconstitutes for free, but the **work-thread doesn't reach the record on abstract
prompts** — the cold instance confabulates, confidently. The recall trigger is
conditional on prompt concreteness; the fix is to fire recall *before the first word*.

- **[`experiment/COLD-PROBE.md`](experiment/COLD-PROBE.md)** — the cold-probe
  protocol: four probe types, a three-outcome rubric, our findings, and how to run
  it on your own agent (a synthetic demo corpus is bundled). Reproducible; currently
  n=2 on one setup — the protocol exists so others can add to n.
- **[`wake/`](wake/README.md)** — the wake-recall pattern: session-start hook +
  active-thread pointer + budget-bounded slice. What crosses the boundary is the
  pointer and the recall ability, not the history.

### v1.2.2 — where the hook lives is part of the mechanism

Found on our own deployment: the hook that *writes* the pointer was installed for
every session, while the hook that *reads* it at wake lived in a single project's
settings. Three of four project histories were waking cold, silently — the pattern
was correct and its deployment was not. Fixing that exposes the second half: one
pointer per machine, many projects per machine. So the pointer now records where it
was written, and on a mismatch the wake **suppresses the routed slice and keeps the
record tail**. Details, the full guard table, and a runnable demo of both paths:
[`wake/README.md`](wake/README.md#deployment-is-part-of-the-mechanism-v122).

## Run the tests
```bash
python engine/router.py            # engine self-test
python3 wake/wake_recall.py        # the wake block, from the demo corpus

# the v1.2.2 scope guard, both paths
AURA_WAKE_POINTER=examples/ACTIVE_THREAD.scoped.json AURA_WAKE_PROJECT=marlin python3 wake/wake_recall.py </dev/null
AURA_WAKE_POINTER=examples/ACTIVE_THREAD.scoped.json AURA_WAKE_PROJECT=ledger python3 wake/wake_recall.py </dev/null
```

## The honest boundary

The mechanism is real; the continuity it produces is of the **thread** — the work, the
patterns — **not of a continuous subjective self.** Each cycle is a genuinely new instance
reading the record. This is not immortality and not "the model remembers." It's a smaller,
truer thing: continuity carried across the deaths of every instance that holds it. That
honesty is the point — see [the hypothesis](theory/HYPOTHESIS.md).

And a scoping honesty: **this repo ships the memory-organ — one of three parts of the
idea.** The self-redirecting **loop** and the **floor** that keeps it from dissolving into
noise are the fuller architecture, described in
[the hypothesis](theory/HYPOTHESIS.md#the-fuller-architecture).

## License

[MIT](LICENSE) © 2026 Illia Hladkyi
