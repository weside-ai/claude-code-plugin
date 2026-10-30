#!/usr/bin/env python3
"""UserPromptSubmit hook: the wake's counter — a pending note once, and a stale poller named.

Two lines it may add as context, nothing else, and no network call:

- A pending note the wake poller wrote for this session's inbox socket
  (``<news dir>/pending-<socket basename>.json``) after a delivery the socket did not take: the
  hook claims it atomically (rename), prints the wake line once, deletes it, and adds 1 to the
  companion's ``hook_delivered`` counter for the UTC day. The line is rendered again from handoff
  ids and room refs (a note of the room-news rule: room refs and integers), so a note carries no
  text into the session.
- For a session bound to its pin whose socket had a poller (its lock file
  ``<news dir>/poller-<socket basename>.lock`` exists; only a started poller creates it):
  when the companion's ``last_ok`` (or, before the first success,
  the poller's ``started``) is older than three poll intervals (180 s),
  ``weside: wake stale since N min (last error: <class>)``.

What it cannot see: a line the socket accepted and never injected (held), and a wake the session
received but did not read. The docs call it the counter "hook delivered n times" until a forced
delivery failure against a real session proved it a fallback. Contract:
``references/companion-session.md`` § Wake; file formats: ``scripts/wake_poller.py``.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import wake_poller
from identity_cache import read_binding

STALE_AFTER_S = 3 * wake_poller.INTERVAL_S


def claim_pending(socket_path: str) -> dict | None:
    """Take this socket's pending note (rename first, so two prompts cannot both print it)."""
    note = wake_poller.pending_path(socket_path)
    claimed = note.with_name(f".{note.name}.{os.getpid()}.claimed")
    try:
        os.replace(note, claimed)
    except OSError:
        return None
    try:
        data = json.loads(claimed.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    finally:
        with contextlib.suppress(OSError):
            claimed.unlink()
    return data if isinstance(data, dict) else None


def pending_line(socket_path: str, now: float) -> str | None:
    data = claim_pending(socket_path)
    if data is None:
        return None
    companion = data.get("companion")
    handoffs, rooms = data.get("handoffs"), data.get("rooms")
    if not isinstance(companion, str):
        return None
    try:
        if isinstance(handoffs, list):
            line = wake_poller.render_handoffs(
                companion, [{"id": h["id"], "from": h["from"]} for h in handoffs]
            )
        elif isinstance(rooms, list):
            line = wake_poller.render(
                companion,
                [
                    {"room": r["room"], "count": r["count"], "saturated": bool(r.get("saturated"))}
                    for r in rooms
                ],
                bool(data.get("since_last_session")),
            )
        else:
            return None
    except (KeyError, TypeError, ValueError):
        return None
    with wake_poller.locked_state(companion) as state:
        wake_poller.bump(state, "hook_delivered", now)
    return line


def stale_line(hook_input: dict, environ: dict, now: float) -> str | None:
    pin = environ.get("WESIDE_COMPANION", "").strip()
    sock = environ.get("CLAUDE_CODE_MESSAGING_SOCKET", "")
    if not pin or not sock or not wake_poller.poller_lock_path(sock).exists():
        return None
    bound = read_binding(hook_input.get("session_id", ""))
    if not bound or bound.lower() != pin.lower():
        return None
    if not wake_poller.state_path(bound).exists():
        return None
    state = wake_poller.read_state(bound)
    ref = wake_poller.parse_iso(state["last_ok"]) or wake_poller.parse_iso(state["started"])
    if ref is None or now - ref <= STALE_AFTER_S:
        return None
    err = state["last_error"]
    minutes = int((now - ref) // 60)
    return (
        f"weside: wake stale since {minutes} min (last error: {err['class'] if err else 'none'})"
    )


def output(hook_input: dict, environ: dict | None = None, now: float | None = None) -> dict | None:
    env = os.environ if environ is None else environ
    now = time.time() if now is None else now
    lines = []
    sock = env.get("CLAUDE_CODE_MESSAGING_SOCKET", "")
    if sock:
        line = pending_line(sock, now)
        if line:
            lines.append(line)
    stale = stale_line(hook_input, env, now)
    if stale:
        lines.append(stale)
    if not lines:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(lines),
        }
    }


def read_input() -> dict:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


if __name__ == "__main__":
    try:
        answer = output(read_input())
    except Exception:
        answer = None
    if answer is not None:
        print(json.dumps(answer))
