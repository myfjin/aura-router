#!/usr/bin/env python3
"""wake_recall.py — auto-recall at wake (the v1.2 pattern).

The cold-probe experiment (see ../experiment/COLD-PROBE.md) found that an agent's
recall reach is CONDITIONAL: it fires on concrete/actionable prompts, but on abstract
prompts a fresh instance doesn't recognize the gap — it confabulates, confidently.

The fix is not smarter recall. It's earlier recall: **fire the router before the
first word.** This script is a session-start step that

  1. reads the active-thread pointer (what was the work mid-doing?),
  2. routes the record for the slice relevant to that stride,
  3. prints a bounded wake block — stdout becomes session context,

so a cold instance wakes with the thread already lit, and abstract first prompts
land on the real work instead of a plausible reconstruction.

What the wake carries (the whole point is how little): the pointer + the recall
ability + this bounded slice. Not the history. Carry less, re-light on demand.

Wiring (Claude Code shown; any harness with a session-start hook works):

  .claude/settings.json
    {"hooks": {"SessionStart": [{"hooks": [{"type": "command",
        "command": "python3 /path/to/aura-router/wake/wake_recall.py"}]}]}}

  The pointer is auto-updated by the end of each working turn (e.g. a Stop hook
  writing the current stride), so no one maintains it by hand.

Configuration (env):
  AURA_WAKE_STORE    jsonl record, {"id", "text", ...} per line
                     (default: ../examples/synthetic_thread.jsonl — the demo corpus)
  AURA_WAKE_POINTER  json pointer file {"stride", "updated", "by"}
                     (default: ../examples/ACTIVE_THREAD.json)

Fail-open: any error prints nothing and exits 0 — a broken wake must never block
the session; it just wakes cold, like before.

Run manually:  python3 wake/wake_recall.py < /dev/null
"""
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STORE_PATH = Path(os.environ.get("AURA_WAKE_STORE",
                                 REPO / "examples/synthetic_thread.jsonl"))
POINTER_PATH = Path(os.environ.get("AURA_WAKE_POINTER",
                                   REPO / "examples/ACTIVE_THREAD.json"))

RECALL_BUDGET = 2400   # chars of relevance-routed slice
TAIL_N = 3             # always show the record tail (most recent context)
TAIL_TRUNC = 600       # per tail entry
HARD_CAP = 7000        # absolute ceiling on injected chars


def main():
    try:
        if not sys.stdin.isatty():
            sys.stdin.read()   # some hooks pass JSON on stdin; consume, unused
    except Exception:
        pass
    try:
        sys.path.insert(0, str(REPO))
        from engine.router import Store, Router

        store = Store.from_jsonl(STORE_PATH)
        pointer = {}
        try:
            pointer = json.loads(POINTER_PATH.read_text())
        except Exception:
            pass
        stride = (pointer.get("stride") or "").strip()

        out = ["=== WAKE — auto-recall at wake (aura-router v1.2 pattern) ==="]
        if stride:
            out.append(f"ACTIVE THREAD (updated {pointer.get('updated', '?')} by "
                       f"{pointer.get('by', '?')}): {stride}")
            s = Router(store).route(stride, budget_chars=RECALL_BUDGET)
            if s.items:
                out.append("-- relevant slice (routed on the active thread) --")
                for it in s.items:
                    out.append(f"[{it.meta.get('timestamp')}] {it.meta.get('speaker')}: {it.text}")
        else:
            out.append("ACTIVE THREAD: no pointer yet — tail only.")
        tail = store.items[-TAIL_N:]
        if tail:
            out.append("-- record tail --")
            for it in tail:
                t = it.text if len(it.text) <= TAIL_TRUNC else it.text[:TAIL_TRUNC] + " …[truncated]"
                out.append(f"[{it.meta.get('timestamp')}] {it.meta.get('speaker')}: {t}")
        out.append("(deeper: route the record yourself — engine/router.py)")
        print("\n".join(out)[:HARD_CAP])
    except Exception:
        return  # fail-open: wake silently without the slice


if __name__ == "__main__":
    main()
