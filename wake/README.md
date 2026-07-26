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
- **Not every turn that looks like the user is the user.** See below — this one
  cost us six forged entries and a self-poisoning pointer.

## Field note: the harness writes turns that wear the user's name

*Found on our own deployment, 2026-07-26.*

Context compaction is a **second wake** — the session-start hook fires again when the
window is squashed, which is right: compaction is exactly when the thread needs
re-lighting. But compaction also writes into the transcript, and what it writes can
look like a human turn.

In our harness the compaction summary arrives as a row typed `user`, flagged
`isCompactSummary`, carrying plain string content. Our pointer-writer's test for "is
this the human's turn?" was *does this row have text* — so it took the summary as the
user's words. Two consequences, and the second is the dangerous one:

1. the summary was appended to the record **under the human's name** — forged
   provenance, in the one file that is supposed to be the honest record;
2. the summary became the **stride**, so the next wake routed on
   *"This session is being continued from a previous conversation…"* — boilerplate
   that appears in **every** compaction. The router faithfully retrieved other
   compaction summaries. The pointer had been pointed at its own noise.

The fix is one guard, and its shape matters: treat such a row as a **boundary** —
stop the backward walk there and record no user text — rather than skipping past it
in search of a "real" turn. We tried walking past. It crosses turn boundaries and
re-collects prior turns; one transcript's captured turn went from 964 to 59,257
characters. The synthetic rows are load-bearing precisely *because* they mark where
a turn begins.

Two things generalize past our harness:

- **Ask of your pointer-writer: could the harness itself have produced this text?**
  Compaction summaries, command wrappers, tool preambles, resumption banners — any
  of them can be typed as the user in a transcript format.
- **A stride made of harness boilerplate is worse than no stride**, because it is the
  string most likely to match other boilerplate. A poisoned pointer doesn't fail
  loudly; it retrieves confidently, and every wake after it inherits the mistake.

We dated the damage before fixing it — the bad entries stopped on a day the record was
rebuilt, which made this look like an artifact of the rebuild rather than a live bug.
It wasn't: a fixture reproduced it against current code. **A static artifact records
the whole past, not the present.** Test the producer, not the output.
