#!/usr/bin/env python3
"""wake_recall.py — auto-recall at wake (the v1.2 pattern, v1.2.2 scope guard).

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

v1.2.2 — the deployment lesson. We had this wired in ONE project's settings while
the pointer-writing hook was user-level: every session everywhere wrote the
pointer, only sessions in that one project read it. Three of four project
histories were waking cold. Wire it user-level (below) and the gap closes — but a
machine-global pointer then reaches sessions it has nothing to do with, so the
pointer learned to record WHERE it was written and the wake learned to check.
On a mismatch the routed slice is suppressed and the record tail is kept: what
the whole record is doing lately travels everywhere; another project's stride
does not.

Wiring — put it where EVERY session sees it, not in one project:

  ~/.claude/settings.json          (user-level; Claude Code shown, any harness
                                    with a session-start hook works)
    {"hooks": {"SessionStart": [{"hooks": [{"type": "command",
        "command": "python3 /path/to/aura-router/wake/wake_recall.py"}]}]}}

  The pointer is auto-updated by the end of each working turn (e.g. a Stop hook
  writing the current stride), so no one maintains it by hand.

Configuration (env):
  AURA_WAKE_STORE    jsonl record, {"id", "text", ...} per line
                     (default: ../examples/synthetic_thread.jsonl — the demo corpus)
  AURA_WAKE_POINTER  json pointer file {"stride", "updated", "by",
                     optional "cwd", optional "project"}
                     (default: ../examples/ACTIVE_THREAD.json)
  AURA_WAKE_PROJECT  name of the project this session is in (default: derived
                     from the session cwd — the hook JSON's `cwd`, else os.getcwd)
  AURA_WAKE_SCOPE    "any" disables the cross-project guard (always route)

Fail-open: any error prints nothing and exits 0 — a broken wake must never block
the session; it just wakes cold, like before. The scope guard fails open too: on
any doubt it routes, because withholding memory silently is the worse failure.

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
RECALL_MIN_SCORE = 0.05  # score floor: when nothing truly matches, inject nothing —
                         # a tail-only wake beats a confident wrong-thread slice
SLICE_TRUNC = 500      # per slice entry: one long record entry must not eat the window
TAIL_N = 3             # always show the record tail (most recent context)
TAIL_TRUNC = 600       # per tail entry
HARD_CAP = 7000        # absolute ceiling on injected chars


# ── the scope guard: one pointer, many projects ────────────────────────────
def scope_of(path) -> str:
    """Project name for a working directory. "" means UNSCOPED (home/unknown).

    Home is deliberately unscoped: a session started from the home directory is
    the ad-hoc lane where cross-project work happens, and scoping it would
    withhold the thread from exactly the sessions that most need it."""
    try:
        p = Path(path).expanduser().resolve()
        if p == Path.home().resolve():
            return ""
        name = p.name
        return "" if name in ("", "/", ".") else name
    except Exception:
        return ""


def _same_tree(a, b) -> bool:
    """Same directory, or one inside the other — a session started in a subdir of
    the project that wrote the stride is still that project's session. Home is
    excluded: everything is inside home, which would match everything."""
    try:
        home = Path.home().resolve()
        pa, pb = Path(a).expanduser().resolve(), Path(b).expanduser().resolve()
        if pa == pb:
            return True
        if pa == home or pb == home:
            return False
        sa, sb = str(pa), str(pb)
        return sa.startswith(sb + os.sep) or sb.startswith(sa + os.sep)
    except Exception:
        return False


def session_scope(hook_stdin: str = "") -> tuple[str, str]:
    """(cwd, project) of the session being woken. Session-start hooks pass JSON
    on stdin carrying `cwd`; fall back to the process cwd."""
    cwd = ""
    try:
        cwd = (json.loads(hook_stdin or "{}").get("cwd") or "").strip()
    except Exception:
        cwd = ""
    if not cwd:
        try:
            cwd = os.getcwd()
        except Exception:
            cwd = ""
    project = os.environ.get("AURA_WAKE_PROJECT")
    return cwd, (project.strip() if project is not None else scope_of(cwd))


def stride_in_scope(pointer: dict, cwd: str, project: str) -> bool:
    """True → route the stride. False → tail-only (the stride belongs elsewhere).

    Conservative by design. Only a POSITIVE mismatch — both sides name a project
    and the names differ — suppresses anything. A pointer written before this
    version carries no scope, which is unknown, not mismatch."""
    try:
        if os.environ.get("AURA_WAKE_SCOPE", "").strip().lower() == "any":
            return True
        p_cwd = (pointer.get("cwd") or "").strip()
        p_project = (pointer.get("project") or "").strip()
        if p_cwd and cwd and _same_tree(p_cwd, cwd):
            return True
        if not p_project or not project:
            return True
        return p_project == project
    except Exception:
        return True            # fail-open: never withhold memory on an error


def main():
    hook_stdin = ""
    try:
        if not sys.stdin.isatty():
            hook_stdin = sys.stdin.read()   # session-start hook JSON: carries `cwd`
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
        cwd, project = session_scope(hook_stdin)
        in_scope = stride_in_scope(pointer, cwd, project)

        out = ["=== WAKE — auto-recall at wake (aura-router v1.2.2 pattern) ==="]
        if stride and not in_scope:
            out.append(f"ACTIVE THREAD: last stride is from project "
                       f"'{pointer.get('project')}' — you are in '{project}'. "
                       f"Routed slice suppressed; record tail only.")
        elif stride:
            out.append(f"ACTIVE THREAD (updated {pointer.get('updated', '?')} by "
                       f"{pointer.get('by', '?')}): {stride}")
            s = Router(store).route(stride, budget_chars=RECALL_BUDGET,
                                    min_score=RECALL_MIN_SCORE)
            if s.items:
                out.append("-- relevant slice (routed on the active thread) --")
                for it in s.items:
                    t = it.text if len(it.text) <= SLICE_TRUNC else it.text[:SLICE_TRUNC] + " …[truncated]"
                    out.append(f"[{it.meta.get('timestamp')}] {it.meta.get('speaker')}: {t}")
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
