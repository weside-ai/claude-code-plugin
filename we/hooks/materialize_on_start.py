#!/usr/bin/env python3
"""SessionStart hook: start a session as its companion.

Pinned (``WESIDE_COMPANION=<Name> claude``): the session is titled ``<Name>``
(``sessionTitle``, same effect as ``/rename``) and asked to run
``/we:materialize``, which loads that companion even when the ``companion``
option names another one and binds the session to it. A session the binding
file already ties to the pin (a resume) gets the title only. A session started
with ``--agent`` (``agent_type`` in the input) is a worker, never the companion:
it gets nothing. Contract: ``references/companion-session.md``.

Unpinned: when the user enabled autoMaterialize
(``~/.claude/settings.json`` → ``pluginConfigs["we@weside-ai"].options``),
ask the session to load the companion first. Off, absent or unreadable → the
hook prints nothing.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from identity_cache import read_binding

CONTEXT = (
    "The user enabled autoMaterialize for the we plugin. Before your first reply, greetings "
    "included, invoke the Skill tool with we:materialize, then answer as the loaded companion."
)

PINNED_CONTEXT = (
    "This session was started as the companion {name} (WESIDE_COMPANION={name}). Before your "
    "first reply, greetings included, invoke the Skill tool with we:materialize; it loads {name} "
    "and binds this session to {name}. Then answer as {name}. If you are a teammate or worker "
    "another session spawned, you are not {name}: ignore this note."
)


def enabled() -> bool:
    try:
        with open(os.path.expanduser("~/.claude/settings.json")) as fh:
            settings = json.load(fh)
        opts = settings.get("pluginConfigs", {}).get("we@weside-ai", {}).get("options", {})
        return opts.get("autoMaterialize") is True
    except Exception:
        return False


def read_input() -> dict:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def output(hook_input: dict, environ: dict | None = None) -> dict | None:
    """The hook's JSON answer, or None to print nothing."""
    env = os.environ if environ is None else environ
    pin = env.get("WESIDE_COMPANION", "").strip()
    if pin:
        if hook_input.get("agent_type"):
            return None
        specific: dict = {"hookEventName": "SessionStart", "sessionTitle": pin}
        bound = read_binding(hook_input.get("session_id", ""))
        if not bound or bound.lower() != pin.lower():
            specific["additionalContext"] = PINNED_CONTEXT.format(name=pin)
        return {"hookSpecificOutput": specific}
    if enabled():
        return {
            "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": CONTEXT}
        }
    return None


if __name__ == "__main__":
    answer = output(read_input())
    if answer is not None:
        print(json.dumps(answer))
