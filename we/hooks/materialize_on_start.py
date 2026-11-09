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
be filled and reported to the Orchestrator (for HR) instead. A session already bound to
the pin gets that skill line alone, but only on ``startup`` and ``resume``
(``--continue`` too): after ``compact`` or ``clear`` the skill is still in
context or the unbound note names it. Contract:
``references/companion-session.md``.

The pin and the worker check come from ``crew.session_kind``: a ``--agent`` session gets nothing,
a consultation (pin + ``WE_ROLE=worker``) is the companion like a master. In a repo whose crew has
no ``weside_account: true`` (a team without a weside account) a pinned session gets its title and
the role-skill line only, never the request to materialize.

Unpinned: when the user enabled autoMaterialize
(``CLAUDE_PLUGIN_OPTION_AUTOMATERIALIZE``, else ``pluginConfigs`` in Claude Code's settings: ``claude_home.plugin_option``),
ask the session to load the companion first. Off, absent or unreadable → the
hook prints nothing.
A background session (``claude --bg``, ``$CLAUDE_JOB_DIR`` set) without a pin is a
worker: instead of the autoMaterialize note it gets a warning not to load or speak as the
companion (``identity_cache.py bind`` refuses it too); the user sees it only when the variable
is absent, not when the session's environment carries it empty (a worker with the pin cleared).

A crew ``crew.py`` refuses (``CrewError``) is never silence for a pin: its context starts with
the line ``<labels.crew_unreadable>: <reason> — load the identity with /we:materialize``
(``render_process.crew_notice`` over ``crew.fallback``), on every source, bound or not.

MCP guard: in a repo whose crew has no ``weside_account: true``, the plugin's
``weside-mcp`` server must not connect. The one per-repo switch that keeps it from connecting is the
project's tracked ``.claude/settings.json`` entry ``deniedMcpServers: [{"serverName":
"plugin:we:weside-mcp"}]`` (measured 06.11.2026 on Claude Code 2.1.319; ``disabledMcp*`` keys, a
failing ``headersHelper`` and ``permissions.deny`` do not stop the connection). ``/we:setup`` writes
it; on ``startup`` and ``resume`` this hook prints one ``systemMessage`` line when it is missing.

Wake: a session already bound to its pin starts its wake poller here on ``startup`` and
``resume`` (``scripts/wake_poller.py``; a fresh session starts it at its bind).
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import claude_home
import crew
import render_process
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
    "per its repo's instruction file, then tell {orch} in one line (for HR)."
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
        orch = crew.holder_name(members, "coordinator") if members else None
        return STUB_ACTION.format(name=name, path=path, orch=orch or "the Orchestrator")
    if loadable:
        return SKILL_ACTION.format(skill=path.parent.name, name=name)
    return READ_ACTION.format(path=path, name=name)


def weside_backed(cwd: str) -> bool:
    """Whether a pin here names a weside companion: no crew (a plain pin), or a crew with
    ``weside_account: true``. A crew without it is a team without an account: title and role
    skill only, no ``/we:materialize``."""
    try:
        _, members = crew.find_and_load(cwd)
    except crew.CrewError:
        return True
    return members is None or members.get("weside_account") is True


MCP_SERVER = "plugin:we:weside-mcp"
MCP_ENTRY = '"deniedMcpServers": [{"serverName": "plugin:we:weside-mcp"}]'
MCP_WARNING = (
    "we: this repo's crew has no weside account, but {settings} does not deny the weside MCP: add "
    f"{MCP_ENTRY} there (`/we:setup` writes it), or the server keeps asking for a sign-in."
)


def mcp_warning(cwd: str) -> str | None:
    """The warning line when the crew here has no weside account and the project's tracked
    settings do not deny the weside MCP; None otherwise (no crew, an account, a refused crew)."""
    try:
        crew_file, members = crew.find_and_load(cwd)
    except crew.CrewError:
        return None
    if crew_file is None or members is None or members.get("weside_account") is True:
        return None
    root = _project_root(cwd) or crew_file.parent.parent
    settings = root / ".claude" / "settings.json"
    # Only the tracked file counts: a deny in `settings.local.json` holds on one machine and would
    # hide the warning from the teammates whose clone lacks it.
    try:
        denied = json.loads(settings.read_text(encoding="utf-8"))
        denied = denied.get("deniedMcpServers") if isinstance(denied, dict) else None
    except (OSError, ValueError):
        denied = None
    if isinstance(denied, list) and any(
        isinstance(d, dict) and d.get("serverName") == MCP_SERVER for d in denied
    ):
        return None
    return MCP_WARNING.replace("{settings}", str(settings))


def _project_root(cwd: str) -> Path | None:
    """The git top level of ``cwd`` (where the project's ``.claude/`` lives), or None."""
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None


def with_mcp_warning(answer: dict | None, hook_input: dict) -> dict | None:
    """``answer`` plus the MCP guard's ``systemMessage`` on ``startup``/``resume``."""
    if hook_input.get("source") not in ("startup", "resume") or hook_input.get("agent_type"):
        return answer
    line = mcp_warning(hook_input.get("cwd") or os.getcwd())
    if line is None:
        return answer
    answer = dict(answer or {})
    answer["systemMessage"] = (
        f"{answer['systemMessage']}\n{line}" if answer.get("systemMessage") else line
    )
    return answer


def refused_line(cwd: str) -> str | None:
    """The one line for a pin whose crew ``crew.py`` refuses, else None."""
    try:
        crew.find_and_load(cwd)
    except crew.CrewError as exc:
        notice = render_process.crew_notice(crew.fallback(crew.find(cwd), str(exc)))
        return f"{notice} — load the identity with /we:materialize"
    return None


def enabled() -> bool:
    return claude_home.plugin_option("autoMaterialize") is True


def read_input() -> dict:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def output(hook_input: dict, environ: dict | None = None) -> dict | None:
    """The hook's JSON answer, or None to print nothing."""
    env = os.environ if environ is None else environ
    _, pin = crew.session_kind(env, hook_input.get("agent_type"), hook_input)
    if pin:
        specific: dict = {"hookEventName": "SessionStart", "sessionTitle": pin}
        bound = read_binding(hook_input.get("session_id", ""))
        cwd = hook_input.get("cwd") or os.getcwd()
        if not weside_backed(cwd):
            action = role_skill(pin, cwd)
            if action and hook_input.get("source") in ("startup", "resume"):
                specific["additionalContext"] = BOUND_ROLE_SKILL_CONTEXT.format(
                    action=action, name=pin, ignore=IGNORE_CONTEXT.format(name=pin)
                )
        elif not bound or bound.lower() != pin.lower():
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
        refused = refused_line(cwd)
        if refused:
            rest = specific.get("additionalContext")
            specific["additionalContext"] = f"{refused}\n\n{rest}" if rest else refused
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
    answer = with_mcp_warning(output(hook_input), hook_input)
    if answer is not None:
        print(json.dumps(answer))
    companion = wake_companion(hook_input)
    if companion:
        with contextlib.suppress(Exception):
            wake_poller.spawn(companion, check_login=False)
