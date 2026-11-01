#!/usr/bin/env python3
"""SessionStart hook: start a session as its companion.

Pinned (``WESIDE_COMPANION=<Name> claude``): the session is titled ``<Name>``
(``sessionTitle``: prompt bar, transcript, ``/resume`` picker; the session list of
``claude agents`` keeps its derived name, so ``wclaude`` also passes ``--name``) and asked to run
``/we:materialize``, which loads that companion even when the ``companion``
option names another one and binds the session to it. A session the binding
file already ties to the pin (a resume) gets the title only. A session started
with ``--agent`` (``agent_type`` in the input) is a worker, never the companion:
it gets nothing. When a role skill ``<prefix>-<name lowercased>`` exists
(``scripts/crew.py skill-path``: the project's ``.claude/skills/``, ``~/.claude/skills/``, then
the member's ``workplace`` repo from the crew), the note also asks the session to invoke it after
materializing, or to read it when only the workplace holds it; a skill still marked as a stub is to
be filled and reported to HR instead. A session already bound to
the pin gets that skill line alone, but only on ``startup`` and ``resume``
(``--continue`` too): after ``compact`` or ``clear`` the skill is still in
context or the unbound note names it. Contract:
``references/companion-session.md``.

Unpinned: when the user enabled autoMaterialize
(``~/.claude/settings.json`` → ``pluginConfigs["we@weside-ai"].options``),
ask the session to load the companion first. Off, absent or unreadable → the
hook prints nothing.
A background session (``claude --bg``, ``$CLAUDE_JOB_DIR`` set) without a pin is a
worker: instead of the autoMaterialize note it gets a warning not to load or speak as the
companion (``identity_cache.py bind`` refuses it too); the user sees it only when the variable
is absent, not when the session's environment carries it empty (a worker with the pin cleared).

Wake: a session already bound to its pin starts its wake poller here on ``startup`` and
``resume`` (``scripts/wake_poller.py``; a fresh session starts it at its bind).
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import crew
import wake_poller
from identity_cache import read_binding

CONTEXT = (
    "The user enabled autoMaterialize for the we plugin. Before your first reply, greetings "
    "included, invoke the Skill tool with we:materialize, then answer as the loaded companion."
)

BG_UNPINNED_CONTEXT = (
    "WARNING: this is a background session (claude --bg) without WESIDE_COMPANION, so it is a "
    "worker, not the companion. Do not invoke we:materialize and do not answer as a companion, "
    "even though autoMaterialize is on; identity_cache.py bind refuses this session."
)

BG_UNPINNED_MESSAGE = (
    "we: background session without WESIDE_COMPANION, autoMaterialize skipped. "
    "A companion starts in the foreground as WESIDE_COMPANION=<Name> claude (a tmux window for "
    "background work); claude --bg carries the daemon's environment, not the shell's."
)

PINNED_CONTEXT = (
    "This session was started as the companion {name} (WESIDE_COMPANION={name}). Before your "
    "first reply, greetings included, invoke the Skill tool with we:materialize; it loads {name} "
    "and binds this session to {name}. Then answer as {name}.{role_skill}"
    "{ignore}"
)

BOUND_ROLE_SKILL_CONTEXT = (
    "This session is the companion {name}. Before your first reply, {action}{ignore}"
)

ROLE_SKILL_CONTEXT = " After that, {action}"

SKILL_ACTION = (
    "invoke the Skill tool with {skill}: it holds {name}'s working knowledge for this environment."
)

READ_ACTION = (
    "read {path} with the Read tool and follow it: it holds {name}'s working knowledge for this "
    "environment (its repo is not this session's, so the Skill tool does not list it)."
)

STUB_ACTION = (
    "fill {name}'s role skill {path}: it is still a stub. Follow the skeleton inside, commit it "
    "per its repo's instruction file, then tell {hr} in one line."
)

IGNORE_CONTEXT = (
    " If you are a teammate or worker another session spawned, you are not {name}: ignore this "
    "note."
)


def role_skill(name: str, cwd: str) -> str | None:
    """The role-skill sentence for ``name`` (invoke, read or fill as a stub), or None."""
    found = crew.skill_path(name, cwd)
    if found is None:
        return None
    path, loadable = found
    if crew.is_stub(path):
        try:
            _, members = crew.find_and_load(cwd)
        except crew.CrewError:
            members = None
        hr = crew.holder_name(members, "hr") if members else None
        return STUB_ACTION.format(name=name, path=path, hr=hr or "HR")
    if loadable:
        return SKILL_ACTION.format(skill=path.parent.name, name=name)
    return READ_ACTION.format(path=path, name=name)


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
        cwd = hook_input.get("cwd") or os.getcwd()
        if not bound or bound.lower() != pin.lower():
            action = role_skill(pin, cwd)
            specific["additionalContext"] = PINNED_CONTEXT.format(
                name=pin,
                role_skill=ROLE_SKILL_CONTEXT.format(action=action) if action else "",
                ignore=IGNORE_CONTEXT.format(name=pin),
            )
        elif hook_input.get("source") in ("startup", "resume"):
            action = role_skill(pin, cwd)
            if action:
                specific["additionalContext"] = BOUND_ROLE_SKILL_CONTEXT.format(
                    action=action, name=pin, ignore=IGNORE_CONTEXT.format(name=pin)
                )
        return {"hookSpecificOutput": specific}
    if enabled() and env.get("CLAUDE_JOB_DIR"):
        answer: dict = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": BG_UNPINNED_CONTEXT,
            }
        }
        # an empty pin in the session's environment marks a deliberate worker: no user warning
        if "WESIDE_COMPANION" not in env:
            answer["systemMessage"] = BG_UNPINNED_MESSAGE
        return answer
    if enabled():
        return {
            "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": CONTEXT}
        }
    return None


def wake_companion(hook_input: dict, environ: dict | None = None) -> str | None:
    """The companion whose wake poller this start spawns, or None.

    Keyed on the binding, never on the environment alone: only a session already bound to its
    pin (a resume, ``-c``) on ``startup``/``resume``; a fresh session spawns at its bind, a
    worker (``--agent``) and an unpinned or unbound session never.
    """
    env = os.environ if environ is None else environ
    pin = env.get("WESIDE_COMPANION", "").strip()
    if not pin or hook_input.get("agent_type"):
        return None
    if hook_input.get("source") not in ("startup", "resume"):
        return None
    bound = read_binding(hook_input.get("session_id", ""))
    if not bound or bound.lower() != pin.lower():
        return None
    return bound


if __name__ == "__main__":
    hook_input = read_input()
    answer = output(hook_input)
    if answer is not None:
        print(json.dumps(answer))
    companion = wake_companion(hook_input)
    if companion:
        with contextlib.suppress(Exception):
            wake_poller.spawn(companion, check_login=False)
