#!/usr/bin/env python3
"""SessionStart hook: starts the crew's event poller and this session's event tail.

Only in a project whose ``.weside/config.json`` has an ``events:`` block; elsewhere nothing,
exit 0. Then:

1. ``event_poller.ensure``: the project's one poller (``scripts/command_center/event_poller.py``),
   unless one runs; it starts with ``HOME``, ``PATH`` and ``LANG`` only, never a ``CLAUDE_*``
   variable, so it holds no inbox token;
2. ``event_tail.spawn``: this session's tail, only for a crew member's session (its pin) that is no
   worker; the tail gets the session's inbox socket and token in its environment, never in argv or
   a file, and ``CLAUDE_CODE_SESSION_ID`` from the hook input (it reads the session's board line).

Prints nothing on success: the lines arrive later through the inbox. Fails open: any failure is
one stderr line ``events_on_start: skipped (<class>: <message>)`` and exit 0.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "command_center"))


def start(hook_input: dict, environ: dict) -> list[str]:
    """What it started (``events: …`` lines); [] outside a project with ``events:``."""
    import crew as crew_mod  # noqa: PLC0415  (import cost only where the hook acts)
    import event_poller  # noqa: PLC0415
    import event_tail  # noqa: PLC0415

    cwd = hook_input.get("cwd") or os.getcwd()
    root = event_poller.project_root(cwd)
    if root is None or event_poller.read_block(root / ".weside" / "config.json") is None:
        return []
    said = [event_poller.ensure(root, environ)]
    kind, _ = crew_mod.session_kind(environ, hook_input.get("agent_type"), hook_input)
    if kind in ("worker", "consult"):
        return said
    env = dict(environ)
    if hook_input.get("session_id"):
        env["CLAUDE_CODE_SESSION_ID"] = str(hook_input["session_id"])
    said.append(event_tail.spawn(root, env))
    return said


def main() -> int:
    try:
        hook_input = json.loads(sys.stdin.read() or "{}")
        start(hook_input if isinstance(hook_input, dict) else {}, dict(os.environ))
    except Exception as exc:  # a session start never fails on the event wiring
        print(f"events_on_start: skipped ({type(exc).__name__}: {exc})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
