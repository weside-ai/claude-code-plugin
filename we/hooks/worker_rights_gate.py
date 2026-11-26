#!/usr/bin/env python3
"""PreToolUse hook on Bash: the worker rights brake (the rules: `scripts/worker_rights.py`).

No boundary: it catches a process worker's mistake before an action that hurts (secrets, deletion,
prod), not a barrier against one that deliberately goes around it (L0 § Flow first). A script file it writes and
runs, another `gh` binary, `curl` with the token pass every text check here; the boundaries are
server-side (branch rules, the merge gate, the token's app rights, the secret store).

It acts only for a process worker: env `WE_ROLE=worker` (set by `we-worker`) or the marker of
`worker_launch.py` naming this session. A master, a companion and their subagents pass untouched.
For a worker it
  1. denies a never-list item (`worker_rights.never`, a fixed list of patterns searched in the
     command text as typed and with its quotes and backslashes removed, no shell parser):
     `never for a worker (<item>): ask …`;
  2. refuses an arm (under `build.pr_owner: worker`) that does not stand as a command of its own:
     behind a wrapper or an assignment, in `bash -c`, `eval`, `$( … )` or backticks
     (`worker_rights.hidden_right`): `not a worker right (<right> behind env: a right only as a
     command of its own, without env/eval/bash -c): ask …`;
  3. on each part of a chain (`worker_rights.segments`: `&&`, `||`, `;`, `|`, `&`, parentheses,
     newlines outside quotes), judges a `gh pr merge` by the merge line for every owner, and under
     `build.pr_owner: worker` an arm and a `gh pr edit`; it denies one whose conditions fail:
     `not a worker right (<reason>): ask …`, all parts sharing one deadline. It allows a held right
     without a prompt only on a command of its own (`worker_rights.simple_argv`); in a chain a held
     right only passes this gate.
`ask …` names the marker's Lead (`ask your Lead <name>`), else `ask your starter`. A crash is a
defect, not a brake: an exception while judging fails open (`crashed`: one stderr line, one
`crash` line in the brake log naming the exception's class, never its message; the call goes to
the normal permissions), except that a worker's call is still denied on a `worker_rights.HARD`
item (secrets, deletion, a push to main, a merge past the checks), judged on the text alone. Every denial is one `deny` line in
`<state dir>/brakes.jsonl` (`worker_rights.brake_log`), so the false alarms can be counted; a failed
write never changes the decision. A PreToolUse deny holds under
`bypassPermissions`.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
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


def decide(payload: dict, env: dict) -> tuple[str, str] | None:  # noqa: PLR0911
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
    item = wr.never(command, cwd, wr.crew_rights(cwd))
    if item:
        return "deny", f"never for a worker ({item}): {ask}"
    owner = wr.pr_owner_on_default(cwd)
    hidden = wr.hidden_right(command, owner)
    if hidden:
        return "deny", (
            f"not a worker right ({hidden}: a right only as a command of its own, "
            f"without env/eval/bash -c): {ask}"
        )
    deadline = time.monotonic() + wr.MERGE_LINE_BUDGET_S  # one budget across every part
    argv = wr.simple_argv(command)
    held = None
    for part in [argv] if argv else wr.segments(command):
        part = wr.strip_keywords(part)  # noqa: PLW2901
        if not part:
            continue
        right = wr.right_of(part, owner)
        if right is None:
            continue
        reason = wr.right_refusal(part, right, cwd, deadline)
        if reason:
            return "deny", f"not a worker right ({reason}): {ask}"
        held = right
    if held is None or argv is None:
        return None
    return "allow", f"worker right {held} (worker_rights_gate)"


def record(payload: dict, env: dict, reason: str, error: str | None = None) -> None:
    """One line in `brakes.jsonl` (`worker_rights.brake_log` owns the shape): `deny` with the
    reason's `item`, or with `error` a `crash` line naming only the exception's class (its message
    may quote the command); silent on any failure."""
    with contextlib.suppress(Exception):
        import worker_rights as wr  # noqa: PLC0415

        marker: dict = {}
        with contextlib.suppress(Exception):
            marker = _marker(payload) or {}
        command = str((payload.get("tool_input") or {}).get("command", ""))
        head = (
            {"type": "crash", "gate": "worker_rights_gate", "error": error}
            if error
            else {
                "type": "deny",
                "gate": "worker_rights_gate",
                "item": reason.rsplit(": ask ", 1)[0],
            }
        )
        wr.brake_log(
            payload.get("cwd"),
            {
                **head,
                "name": marker.get("name"),
                "key": env.get("WE_STORY_KEY") or marker.get("key"),
                "session_id": payload.get("session_id"),
                "argv0": wr.argv0(command),
            },
        )


def crashed(payload: dict, env: dict, exc: Exception) -> tuple[str, str] | None:
    """A crash is a defect, not a brake: one stderr line, one `crash` row, and the call passes
    to the normal permissions, except a `worker_rights.HARD` item (secrets, deletion, the PROD
    paths), which a worker's call is still denied on. That last check failing too denies."""
    print(
        f"worker_rights_gate: crashed, fails open ({type(exc).__name__}: {exc})", file=sys.stderr
    )
    record(payload, env, "crashed", error=type(exc).__name__)
    if payload.get("tool_name") != "Bash":
        return None
    try:
        worker = env.get("WE_ROLE") == "worker" or bool(_marker(payload))
    except Exception:
        worker = env.get("WE_ROLE") == "worker"
    if not worker:
        return None
    command = str((payload.get("tool_input") or {}).get("command", ""))
    try:
        import worker_rights as wr  # noqa: PLC0415

        item = wr.hard_never(command)
    except Exception:
        return "deny", "never for a worker (the hard check crashed too): ask your starter"
    return ("deny", f"never for a worker ({item}): ask your starter") if item else None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    env = dict(os.environ)
    try:
        verdict = decide(payload, env)
    except Exception as exc:
        verdict = crashed(payload, env, exc)
        if verdict:
            _out(*verdict)
        return
    if verdict:
        if verdict[0] == "deny":
            record(payload, env, verdict[1])
        _out(*verdict)


if __name__ == "__main__":
    main()
