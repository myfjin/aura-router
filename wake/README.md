# The wake-recall pattern (v1.2)

**Problem:** an agent's recall reach is conditional. Fresh instances go to the record
on concrete or action prompts, but on abstract prompts they don't recognize the gap —
they confabulate from whatever auto-loads. Measured, not assumed: see
[`../experiment/COLD-PROBE.md`](../experiment/COLD-PROBE.md).

**Fix:** fire the router *before the first prompt*. Three parts:

1. **Auto-recall at wake** — a session-start hook runs
   [`wake_recall.py`](wake_recall.py); its stdout is injected as session context
   before any user input.
2. **The active-thread pointer** — a minimal marker (`{"stride", "updated", "by"}`)
   of what the work was mid-doing, auto-updated at the end of each working turn
   (e.g. by a stop hook), so the wake knows what to re-light. No one maintains it
   by hand — a pointer you must remember to update is a resume-doc with extra steps.
3. **The budget principle** — inject the *relevant slice*, not the log.
   Relevance-ranked, bounded (`RECALL_BUDGET` chars + a short recent tail, hard cap
   overall). Carry the pointer and the recall ability; re-light content on demand.

What crosses each session boundary is deliberately small: identity (your harness's
auto-loaded substrate) + the pointer + the recall ability. **Not the history.**

## Wiring (Claude Code example)

```json
{
  "hooks": {
    "SessionStart": [
      {"hooks": [{"type": "command",
                  "command": "python3 /path/to/aura-router/wake/wake_recall.py"}]}
    ]
  }
}
```

Any harness with a session-start hook and stdout-as-context works the same way.
Point the script at your record with env vars:

```bash
AURA_WAKE_STORE=~/my-agent/record.jsonl \
AURA_WAKE_POINTER=~/my-agent/ACTIVE_THREAD.json \
python3 wake/wake_recall.py
```

Unset, it runs against the bundled demo corpus — try it dry before wiring anything.

## Design constraints that matter

- **Fail-open.** Any error prints nothing and exits 0. A broken wake must never
  block a session; the instance just wakes cold, like before the pattern existed.
- **Bounded, always.** The wake block competes with the user's actual work for
  window space. The budget is the feature, not a limitation.
- **The pointer is written by the work, not about it.** Auto-updated from the turn
  that just happened; manual curation reintroduces the failure mode this replaces.
