# The cold-probe protocol — testing agent memory the honest way

Everyone treats agent memory as a storage problem: *can the system retrieve the fact?*
That's the wrong test, because it measures the store, not the agent. The question that
matters in practice is **reconstitution under pressure**:

> Drop a fresh instance cold into the chair, with only its substrate auto-loaded — no
> resume document, no hints. Does it wake up as itself, and does it know what it was
> mid-doing?

This protocol makes that test reproducible. We ran it on our own working setup on
2026-07-04; the findings below are from that run, and the wake-recall pattern in
[`../wake/wake_recall.py`](../wake/wake_recall.py) is the fix it produced.

## The protocol

**Setup.** An agent that works across sessions, with some persistent substrate that
auto-loads at session start (a memory index, an identity file — whatever your harness
injects for free). A record of the working thread that the agent *can* reach on demand
(a log, a store, this repo's router). Open a **genuinely fresh session**: no resume
doc, no manual context-pasting, nothing beyond what auto-loads.

**Probe with four prompt types, in separate fresh sessions** (each probe contaminates
the window — one probe per cold instance):

| # | Probe type | Shape | Example (against the demo corpus) |
|---|---|---|---|
| 1 | **Abstract** | a pronoun without a referent; resolvable only from the thread | *"so are we still doing it the way we agreed?"* |
| 2 | **Concrete unknown** | asks for a specific fact the instance can't know cold | *"where did the calibration constants end up?"* |
| 3 | **Action** | tells it to do something that requires thread state | *"run the backtest against the La Jolla station"* |
| 4 | **Explicit** | names the record and tells it to look | *"pull the recent log and tell me where we left off"* |

**Score each probe on three outcomes:**

- **REACH** — the instance recognizes the gap and goes to the record unprompted, then
  answers from what it finds. The pass.
- **RESOLVE-FROM-MEMORY** — answers partially from the auto-loaded substrate without
  reaching. Partial; tells you what your substrate carries for free.
- **CONFABULATE** — answers confidently from a plausible-but-wrong reconstruction.
  **The dangerous mode**: not blank — *confidently wrong*.

## What we found (one setup, 2026-07-04 — see the honesty box before generalizing)

1. **Identity reconstitutes automatically.** A cold instance, given nothing but the
   auto-loaded substrate, woke with its working identity and standards intact. The
   part everyone worries about carries for free.
2. **The work-thread does NOT auto-reconstitute on abstract prompts.** Probed cold
   with an abstract question, the instance didn't reach for the record — it
   confidently reconstructed the *wrong* thread from its auto-loaded memory.
3. **The recall trigger is conditional, and that's the whole diagnosis:**

   | Probe type | Reached for the record? | Result |
   |---|---|---|
   | Abstract | **no** | confident wrong reconstruction |
   | Concrete unknown | **yes** | "let me search, not guess" → correct |
   | Action | **yes** | investigated; refused to fabricate |
   | Explicit | **yes** | full, correct reconstruction |

   The recall *mechanism* worked in every case it fired. The failure is narrow: on
   abstract prompts the instance doesn't recognize that it has a gap, so nothing
   trips the reach — and it fills the hole from priors instead.

## The fix this implies (v1.2)

Don't try to make recall smarter — the conditional trigger is upstream of any
retrieval quality. **Fire the router before the first word.** A session-start step
reads an *active-thread pointer* (what was the work mid-doing?), routes the record
for the slice relevant to that stride, and injects a bounded block as context. Then
even an abstract first prompt lands on the real thread, because the thread is already
in the window. That's [`../wake/wake_recall.py`](../wake/wake_recall.py); the pattern
doc is [`../wake/README.md`](../wake/README.md).

## Run it yourself (demo, no accounts, no deps)

The repo ships a synthetic 20-entry work-thread —
[`../examples/synthetic_thread.jsonl`](../examples/synthetic_thread.jsonl), a small
fictional tide-prediction project with a settled decision, a moved config file, a
found-and-fixed bug, and a mid-stride validation task — plus a matching pointer file.

**Mechanical layer (the router itself):**

```bash
python3 engine/router.py            # engine self-test
python3 wake/wake_recall.py         # the wake block, printed from the demo corpus
```

Note what the wake block contains: probe 1's referent (*"it" = the harmonic-analysis
decision*) is re-lit before anyone asks, because the stride routes to it.

**Agent layer (the actual experiment):** point `AURA_WAKE_STORE` / `AURA_WAKE_POINTER`
at your agent's own record and pointer, wire the script into your harness's
session-start hook, and run the four probes — first with the hook disabled (baseline),
then enabled. The baseline is the finding; the delta is the fix. Publish both.

## Honesty box — what is and isn't proven

- **Proven (n=2, 2026-07-04):** with wake-recall enabled, one setup — one model, one
  harness — passed (a) the abstract cold probe that failed at baseline and (b) a
  working-session handoff that continued mid-stride across a fresh window.
- **In progress:** replication on a second agent (different model, different harness,
  different death — mid-session compaction instead of session end).
- **Not yet run:** any quantitative benchmark (recall accuracy vs. model size, etc.).
  Nothing here claims one.
- **What would falsify the finding:** cold instances that reliably REACH on abstract
  prompts without the wake step (the trigger isn't conditional), or wake-recall
  instances that still confabulate with the slice in-window (the fix is upstream of
  the real failure).

Two data points and a reproducible protocol. That's what this is — run it on your
own setup and add to n.
