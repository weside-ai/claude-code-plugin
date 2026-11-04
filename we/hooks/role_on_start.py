#!/usr/bin/env python3
"""SessionStart hook (every source: startup, resume, clear, compact): this session's role card (L1).

Only in a repo with a crew (``scripts/crew.py find``); no crew → nothing, exit 0. A crew
``crew.py`` refuses (``CrewError``) is never silence: the role comes from ``crew.fallback`` (the
defaults: ``worker`` or ``master`` from the environment, a pin finds no member) and the line
``<labels.crew_unreadable>: <reason>`` (``render_process.crew_notice``) leads the notes. A session
without a role (``crew.role_of_session`` → None) gets the one line ``render_process.POINTER``, the
only pointer to ``references/working-mode.md`` (after a refused crew: the line, then the pointer). Otherwise it prints, in this order, what
``scripts/render_process.py`` composes (``card_parts``, ``compose``):

1. the role card ``roles/<role>.md`` (a held role key, ``specialist``, ``master`` or ``worker``);
2. the repo addendum: a pinned member's ``<workplace>/.weside/roles/<slug>.md``, an unpinned
   master's or worker's ``<crew repo>/.weside/roles/<role>.md``, when present;
3. the notes: per extra repo of the member that does not exist here, ``extra repo <value> not
   found, skipped`` (``crew.extra_repos``; the card never depends on an extra repo), then
   ``render_process.POINTER``;
4. per extra repo that exists: its ``AGENTS.md`` up to the first level-2 heading;
5. per extra repo: the output of each ``type: command`` SessionStart hook of its
   ``.claude/settings.json`` whose matcher takes this source, run there with this hook's input
   (timeout ``render_process.HOOK_TIMEOUT`` s each, ``render_process.EXTRA_HOOKS_CAP`` s for all
   together; a failure is the one line ``extra hook failed: <command>``, a hook past the cap
   ``extra hook skipped, total cap N s reached: <command>``). Each output is recorded for the
   role totals, which never run a hook.

The whole stays within ``render_process.BUDGET`` (Claude Code previews a longer hook output):
hook output is cut first, then head lines, each with a line naming the full source. Card,
addendum and notes over the budget → nothing printed, one stderr line naming the addendum, exit 1
(the budget gate keeps a repo from shipping that). Parts 1 to 4 do not read ``source``, so they
are byte-identical on every source; part 5 may differ by time and matcher.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import crew as crewlib
import render_process


def output(hook_input: dict, environ: dict | None = None) -> tuple[str | None, str | None]:
    """(additionalContext or None, stderr line or None)."""
    env = os.environ if environ is None else environ
    cwd = hook_input.get("cwd") or os.getcwd()
    try:
        crew_path, crew = crewlib.find_and_load(cwd)
    except crewlib.CrewError as exc:
        crew_path = crewlib.find(cwd)
        crew = crewlib.fallback(crew_path, str(exc))
    if crew_path is None or crew is None:
        return None, None
    notice = render_process.crew_notice(crew) if crew.get("crew_error") else None
    role = crewlib.role_of_session(crew, env, hook_input)
    if role is None:
        return "\n\n".join(filter(None, (notice, render_process.POINTER))), None
    kind, pin = crewlib.session_kind(env, hook_input.get("agent_type"), hook_input)
    found = crewlib.member(crew, pin) if pin and kind != "worker" else None
    slug = found[0] if found else ""
    try:
        parts = render_process.card_parts(crew_path, crew, role, slug, hook_input)
        if notice:
            parts = parts._replace(notes=(notice, *parts.notes))
        text, _ = render_process.compose(parts)
    except (OSError, crewlib.CrewError, render_process.RenderError) as exc:
        return None, f"role_on_start: {exc}; not loaded, read it with the Read tool"
    return text, None


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        data = {}
    hook_input = data if isinstance(data, dict) else {}
    text, error = output(hook_input)
    if error:
        print(error, file=sys.stderr)
        return 1
    if text is not None:
        out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
        json.dump(out, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
