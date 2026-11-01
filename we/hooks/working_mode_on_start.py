#!/usr/bin/env python3
"""SessionStart hook: the working mode's core for this session, only when the repo has a crew.

Prints at most ``MAX_LINES`` short lines (``MAX_CHARS``, asserted by the test): this session's
kind and role, one line per working-mode role holder (``roles.*``) with its duties, where questions
go, and the imperative to read ``references/working-mode.md``, which owns the rules. No crew
(``scripts/crew.py find``) → nothing. The kind comes from ``crew.session_kind`` (``worker``,
``consult``, ``named``, ``unnamed``), the one resolver ``materialize_on_start.py`` reads too.
Every source (startup, resume, clear, compact) gets it: a compaction drops the earlier injection.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import crew as crewlib

REFERENCE = Path(__file__).resolve().parent.parent / "references" / "working-mode.md"
MAX_LINES = 10
MAX_CHARS = 1200

DUTIES = {
    "orchestrator": "starts and parks build masters, starts a worker for a single story, routes "
    "questions and milestones, keeps the board (/board); steers no session it started",
    "product_owner": "the WHAT, the order, plan approval",
    "hr": "workplaces and role skills, crew drift",
    "tester": "staging acceptance; moves a story to Done",
}
TITLES = {
    "orchestrator": "Orchestrator",
    "product_owner": "Product Owner",
    "hr": "HR",
    "tester": "Tester",
}


def _held_role(crew: dict, slug: str | None) -> str | None:
    for role, holder in crew.get("roles", {}).items():
        if slug and holder == slug and role in DUTIES:
            return role
    return None


def _session_line(crew: dict, kind: str, pin: str) -> str:
    if kind == "worker":
        return (
            "- This session: a worker. Build your brief; questions, blockers and your report go "
            "to your starter (the brief's first `Lead:` line, or your result as a subagent)."
        )
    if kind == "unnamed":
        return (
            "- This session: unnamed master (build master or helper). The WHAT from the Product "
            "Owner, the HOW from the epic owner (label `owner-<slug>`), else the component owner."
        )
    found = crewlib.member(crew, pin)
    if found is None:
        return (
            f"- This session: the companion {pin}, not in the crew: ask the Orchestrator for "
            "your role before you act."
        )
    slug, entry = found
    if kind == "consult":
        return (
            f"- This session: a consultation as the companion {pin}: answer what you were asked, "
            "steer no workers, then end."
        )
    role = _held_role(crew, slug)
    if role:
        return f"- This session: named master, the companion {pin}, the {TITLES[role]} (below)."
    comps = ", ".join(str(c) for c in entry.get("components") or [])
    duty = (
        f"component owner of {comps}: the HOW, review, plan acceptance"
        if comps
        else "you judge and review what you are asked"
    )
    if entry.get("on_call"):
        duty += "; on call: answer what you were woken for"
    return f"- This session: named master, the companion {pin}, {duty}; you start no workers."


def core(crew: dict, kind: str, pin: str, reference: Path = REFERENCE) -> str:
    orch = crewlib.holder_name(crew, "orchestrator") or "the Orchestrator"
    label = str(crew.get("question_label") or "QUESTION").strip()
    lines = ["we working mode (crew of this repo):", _session_line(crew, kind, pin)]
    for role, duty in DUTIES.items():
        name = crewlib.holder_name(crew, role)
        if name:
            lines.append(f"- {TITLES[role]}: {name} — {duty}.")
    found = crewlib.member(crew, pin) if pin else None
    is_orch = bool(found) and _held_role(crew, found[0]) == "orchestrator"
    if kind in ("named", "unnamed") and not is_orch:
        lines.append(
            f"- A question only the human answers: one SendMessage to {orch} each, "
            f"`{label} · <KEY> <title> · <question without prior knowledge> · Recommendation: …`; "
            f"each milestone (plan approved, PR open, merged, blocker) one line to {orch}."
        )
    lines.append(f"- Read {reference} before routing, starting a session or moving a ticket.")
    return "\n".join(lines)


def output(hook_input: dict, environ: dict | None = None) -> dict | None:
    env = os.environ if environ is None else environ
    cwd = hook_input.get("cwd") or os.getcwd()
    try:
        _, crew = crewlib.find_and_load(cwd)
    except crewlib.CrewError:
        return None
    if not crew:
        return None
    kind, pin = crewlib.session_kind(env, hook_input.get("agent_type"))
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": core(crew, kind, pin),
        }
    }


def read_input() -> dict:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


if __name__ == "__main__":
    answer = output(read_input())
    if answer is not None:
        print(json.dumps(answer))
