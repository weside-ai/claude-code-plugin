#!/usr/bin/env python3
"""PreToolUse hook on Bash: the worker rights brake (the rules: `scripts/worker_rights.py`).

No boundary: a brake against a misguided process worker (a wrong brief, a prompt injection in a PR
comment), not a barrier against one that deliberately goes around it. A script file it writes and
runs, another `gh` binary, `curl` with the token pass every text check here; the boundaries are
server-side (branch rules, the merge gate, the token's app rights, the secret store).

It acts only for a process worker: env `WE_ROLE=worker` (set by `we-worker`) or the marker of
`worker_launch.py` naming this session. A master, a companion and their subagents pass untouched.
For a worker it
  1. denies a never-list item (`worker_rights.never`): `never for a worker (<item>): ask …`;
  2. denies a right (`gh pr ready`, `gh pr comment`, the crew's `branch_rc`) whose conditions fail:
     `not a worker right (<reason>): ask …`;
  3. allows a held right that is the whole command, without a prompt; a held right inside a
     compound command only passes this gate.
`ask …` names the marker's Lead (`ask your Lead <name>`), else `ask your starter`. Fail closed: an
exception while judging a worker's command denies it. A PreToolUse deny holds under
`bypassPermissions`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def _out(decision: str, reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def _marker(payload: dict) -> dict | None:
    from worker_launch import worker_marker  # noqa: PLC0415

    return worker_marker(payload)


def decide(payload: dict, env: dict) -> tuple[str, str] | None:
    """(decision, reason) for a worker's Bash call, None to stay out."""
    import worker_rights as wr  # noqa: PLC0415

    if payload.get("tool_name") != "Bash":
        return None
    marker = _marker(payload)
    if env.get("WE_ROLE") != "worker" and not marker:
        return None
    command = str((payload.get("tool_input") or {}).get("command", ""))
    cwd = payload.get("cwd")
    lead = (marker or {}).get("lead")
    ask = f"ask your Lead {lead}" if lead else "ask your starter"
    rights = wr.crew_rights(cwd)
    parsed = wr.parse(command)
    item = wr.never(command, cwd, rights, parsed)
    if item:
        return "deny", f"never for a worker ({item}): {ask}"
    key = env.get("WE_STORY_KEY") or (marker or {}).get("key")
    held = []
    for argv in parsed.commands:
        right = wr.right_of(argv, rights)
        if right is None:
            continue
        reason = wr.right_refusal(argv, right, rights, key, cwd)
        if reason:
            return "deny", f"not a worker right ({reason}): {ask}"
        held.append(right)
    if held and not parsed.compound and len(parsed.commands) == 1:
        return "allow", f"worker right {held[0]} (worker_rights_gate)"
    return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    try:
        verdict = decide(payload, dict(os.environ))
    except Exception as exc:  # fail closed for a worker, stay out for everyone else
        try:
            worker = os.environ.get("WE_ROLE") == "worker" or bool(_marker(payload))
        except Exception:
            worker = os.environ.get("WE_ROLE") == "worker"
        if not worker or payload.get("tool_name") != "Bash":
            print(f"worker_rights_gate: skipped ({type(exc).__name__}: {exc})", file=sys.stderr)
            return
        verdict = (
            "deny",
            f"worker_rights_gate failed ({type(exc).__name__}: {exc}); fail closed: ask your starter",
        )
    if verdict:
        _out(*verdict)


if __name__ == "__main__":
    main()
