#!/usr/bin/env python3
"""aura_router_mcp.py — an MCP server exposing the relevance-router.

The dynamic-context loop as a *standard socket*: any MCP-speaking agent calls `route()`
and gets back only the relevant slice of an unbounded store. Infinite reach, bounded
attention — the router is the decision (what to pull), MCP is the transport (how it's
reached).

Point it at YOUR store (a jsonl of {"id","text", ...} objects) via the AURA_ROUTER_STORE
env var; the server carries no substrate of its own.

Tools:
  route(query, budget_chars, min_score) -> the relevant slice (ranked, within budget)
  add_item(id, text)                    -> write-back into the store (the loop's memory grows)
  store_info()                          -> store size + which source it's pointed at

Run (stdio MCP server):
  AURA_ROUTER_STORE=mydata.jsonl python server/aura_router_mcp.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))
from router import Store, Router, Window, Item  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

_STORE_PATH = os.environ.get("AURA_ROUTER_STORE", "")
_DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo_store.jsonl"

if _STORE_PATH and Path(_STORE_PATH).exists():
    _store = Store.from_jsonl(_STORE_PATH)
elif _DEMO.exists():
    _store = Store.from_jsonl(_DEMO)
else:
    _store = Store([Item("demo", 'set AURA_ROUTER_STORE to a jsonl of {"id","text"} to use your own record')])

_router = Router(_store)
_window = Window(_router)

mcp = FastMCP("aura-router")


@mcp.tool()
def route(query: str, budget_chars: int = 2000, min_score: float = 0.0) -> dict:
    """Pull the relevant slice of the store that fits budget_chars (bounded attention).
    Returns items ranked most-relevant-first, only up to the budget."""
    s = _router.route(query, budget_chars=budget_chars, min_score=min_score)
    return {
        "items": [{"id": it.id, "score": sc, "text": it.text} for it, sc in zip(s.items, s.scores)],
        "n": len(s.items), "used_chars": s.used_chars, "budget_chars": s.budget_chars,
    }


@mcp.tool()
def add_item(id: str, text: str) -> dict:
    """Write a new item back into the store — the moving spotlight's memory grows, so the
    next route() can see it."""
    _window.write_back(Item(id, text))
    return {"ok": True, "store_size": len(_router.store)}


@mcp.tool()
def store_info() -> dict:
    """Store size + which source it's pointed at."""
    return {"store_size": len(_router.store), "source": _STORE_PATH or "(bundled demo)"}


if __name__ == "__main__":
    mcp.run()
