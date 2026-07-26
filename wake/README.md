# The wake-recall pattern (v1.2, scope guard v1.2.2)

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

Put it in **user-level** settings (`~/.claude/settings.json`), not one project's:

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

## Deployment is part of the mechanism (v1.2.2)

The failure we shipped and then found on ourselves: the **pointer-writing** hook was
user-level and the **wake** hook lived in one project's settings. So every session
everywhere *wrote* the pointer, and only sessions in that one project *read* it.
Three of four project histories were waking cold — including sessions started from
the home directory, where a lot of ad-hoc work actually happens. Nothing errored.
Nothing looked broken. The cold sessions just confabulated, which is the exact
failure this pattern exists to remove.

Two things follow, and both are load-bearing:

- **Wire the wake where every session sees it** — the same scope as whatever writes
  the pointer. A wake hook installed per-project silently rots as projects are added.
- **Then the pointer is global and your projects are not.** One `ACTIVE_THREAD.json`
  per machine means a session in project B would wake holding project A's stride.
  So the pointer records **where it was written** (`cwd`, `project`) and the wake
  checks it.

```json
{"stride": "…", "updated": "…", "by": "…",
 "cwd": "/home/dana/work/marlin", "project": "marlin"}
```

On a mismatch the **routed slice is suppressed and the record tail is kept**. The tail
is what the record has been doing lately — useful anywhere. A routed slice from
another project's stride is not; it is confident, specific, and wrong for this window.

The guard is deliberately hard to trigger, because withholding memory is its own
failure mode:

| situation | result |
|---|---|
| pointer has no `cwd`/`project` (written by an older version) | routes — unknown is not mismatch |
| session started from the home directory | routes — home is the ad-hoc lane, not a project |
| session in a subdirectory of the project that wrote the stride | routes — same tree |
| both name a project, names differ | **tail only** |
| any internal error | routes — fail-open |

Try both paths against the bundled example:

```bash
AURA_WAKE_POINTER=examples/ACTIVE_THREAD.scoped.json AURA_WAKE_PROJECT=marlin \
  python3 wake/wake_recall.py </dev/null      # in scope  → stride + slice + tail

AURA_WAKE_POINTER=examples/ACTIVE_THREAD.scoped.json AURA_WAKE_PROJECT=ledger \
  python3 wake/wake_recall.py </dev/null      # elsewhere → labelled line + tail
```

`AURA_WAKE_PROJECT` overrides the project name (otherwise it comes from the session
`cwd` — the hook's stdin JSON, else the process cwd). `AURA_WAKE_SCOPE=any` turns the
guard off entirely, for a machine where every session really is the same work.

**Verify behaviour, not configuration.** Reading a settings file proves a hook is
*configured*. Start a real session from an unrelated directory and look for the block —
that is the only thing that proves it *fires*.

## Design constraints that matter

- **Fail-open.** Any error prints nothing and exits 0. A broken wake must never
  block a session; the instance just wakes cold, like before the pattern existed.
- **Bounded, always.** The wake block competes with the user's actual work for
  window space. The budget is the feature, not a limitation.
- **The pointer is written by the work, not about it.** Auto-updated from the turn
  that just happened; manual curation reintroduces the failure mode this replaces.
- **The pointer must describe the work, not quote the last message.** We learned
  this on our own deployment: a stride copied verbatim from a conversational
  opener ("im back again!") routes on greeting-noise and pulls a confidently
  wrong slice. Write the pointer from the *substance* of the turn — e.g. the
  opening line plus the start of the reply, where the work vocabulary lives.
- **Floor and cap the slice.** `RECALL_MIN_SCORE` keeps a weak match from
  injecting anything (a tail-only wake beats a wrong-thread slice), and
  `SLICE_TRUNC` keeps one long record entry from eating the whole window. Both
  guards exist because we watched both failures happen, same day, on our own
  record.
