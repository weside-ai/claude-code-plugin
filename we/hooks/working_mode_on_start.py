#!/usr/bin/env python3
"""SessionStart hook: the working mode's core for this session, only when the repo has a crew.

Prints at most ten short lines (``MAX_CHARS``, asserted by the test): this session's role, who the
Product Owner and the Orchestrator are, where questions and milestones go, and the path of
``references/working-mode.md``, which owns the rules. No crew (``scripts/crew.py find``) → nothing.

The role comes from the environment:

- ``WE_ROLE=worker`` or a session started with ``--agent``: a worker.
- ``WESIDE_COMPANION`` set (``WE_ROLE`` master or unset): a named master, the companion.
- otherwise (``WE_ROLE=master`` without a pin, or a plain ``claude``): an unnamed master.

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
MAX_CHARS = 900


def role_of(hook_input: dict, env: dict) -> tuple[str, str]:
    """(kind, pin): kind is ``worker``, ``named`` or ``unnamed``."""
    pin = env.get("WESIDE_COMPANION", "").strip()
    if env.get("WE_ROLE", "").strip() == "worker" or hook_input.get("agent_type"):
        return "worker", pin
    if pin:
        return "named", pin
    return "unnamed", ""


def _components(entry: dict | None) -> str:
    items = [str(c) for c in (entry or {}).get("components") or []]
    return ", ".join(items)


def core(crew: dict, kind: str, pin: str, reference: Path = REFERENCE) -> str:
    po = crewlib.holder_name(crew, "product_owner") or "the Product Owner"
    orch = crewlib.holder_name(crew, "orchestrator") or "the Orchestrator"
    label = str(crew.get("question_label") or "QUESTION").strip()
    lines = ["we working mode (crew of this repo):"]
    is_orch = False
    if kind == "worker":
        lines.append(
            "- This session: a worker. Build your brief; report to the starter its first line "
            "names. You are never a companion and start no masters."
        )
    elif kind == "named":
        found = crewlib.member(crew, pin)
        entry = found[1] if found else None
        role = str((entry or {}).get("title") or (entry or {}).get("role") or "not in the crew")
        comps = _components(entry)
        is_orch = bool(found) and crew.get("roles", {}).get("orchestrator") == found[0]
        lines.append(
            f"- This session: named master, the companion {pin} ({role}"
            + (f"; components: {comps}" if comps else "")
            + "). You judge, review and accept; you steer no workers."
        )
        if is_orch:
            lines.append(
                "- You keep questions, sessions and news for the human on the board (/board)."
            )
    else:
        lines.append(
            "- This session: unnamed master (build master or helper). The WHAT comes from the "
            "Product Owner, the HOW from the component owner."
        )
    lines.append(f"- Product Owner: {po} (WHAT, order, plan approval). Orchestrator: {orch}.")
    if not is_orch:
        lines.append(
            f"- Questions for the human: one SendMessage to {orch} each, "
            f"`{label} · <KEY> <title> · <question without prior knowledge> · Recommendation: …`; "
            "milestones (plan approved, PR open, merged, blocker) one line to the same."
        )
    lines.append(f"- Rules: {reference}")
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
    kind, pin = role_of(hook_input, env)
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
