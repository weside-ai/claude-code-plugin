#!/usr/bin/env python3
"""Stop hook: a process worker ends no turn without sending its report to the Lead.

A worker started through `agents.worker_launch` (`scripts/worker_launch.py`) is a session of its
own: its plain text never reaches the Lead, and no `SubagentStop` fires, so the prompt hook on
`^we:dev-(medium|high)$` never sees it. The worktree's marker (`<git-dir>/we-worker.json`) names
the Lead; a turn that sent no `SendMessage` to it is blocked once with the report instruction.

  * No marker in the session's worktree, or one naming another session (the Lead working in the
    worker's tree) → pass at once.
  * The turn is the transcript after the last user entry that is not only a tool result (the
    brief, a steer, a cross-session message). A `SendMessage` whose `to` is the Lead, with or
    without its ` [ref]`, passes.
  * Deterministic, no LLM judgement: a Stop prompt hook would run on every stop of every session.
  * `stop_hook_active` passes (one block per stop); every read error passes (fail-open).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from worker_launch import worker_marker

TAIL_BYTES = 4_000_000
BLOCK = (
    "Your turn ended without your report to the Lead. Finish the remaining steps of your brief, "
    "then send the report your brief asks for (worker-dispatch.md § Report fields) as one "
    "SendMessage to `{lead}`; your plain text never reaches it."
)


def _turn_start(entry: dict) -> bool:
    if entry.get("type") != "user":
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    return isinstance(content, list) and any(
        isinstance(p, dict) and p.get("type") != "tool_result" for p in content
    )


def _sent_to(entry: dict, lead: str) -> bool:
    if entry.get("type") != "assistant":
        return False
    for part in (entry.get("message") or {}).get("content") or []:
        if isinstance(part, dict) and part.get("type") == "tool_use":
            if part.get("name") != "SendMessage":
                continue
            to = str((part.get("input") or {}).get("to", ""))
            if to == lead or to.startswith(f"{lead} ["):
                return True
    return False


def reported(transcript: str, lead: str) -> bool:
    """True when the current turn of the transcript sent a SendMessage to `lead`."""
    with open(transcript, "rb") as fh:
        size = os.path.getsize(transcript)
        if size > TAIL_BYTES:
            fh.seek(size - TAIL_BYTES)
            fh.readline()  # skip the cut line
        entries = []
        for raw in fh:
            try:
                entries.append(json.loads(raw))
            except ValueError:
                continue
    for entry in reversed(entries):
        if _sent_to(entry, lead):
            return True
        if _turn_start(entry):
            return False
    return False


def decide(payload: dict) -> str | None:
    if payload.get("stop_hook_active") or payload.get("agent_id"):
        return None
    marker = worker_marker(payload)
    if not marker or not marker.get("lead") or not payload.get("transcript_path"):
        return None
    try:
        if reported(payload["transcript_path"], str(marker["lead"])):
            return None
    except OSError:
        return None
    return BLOCK.format(lead=marker["lead"])


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    reason = decide(payload)
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
    sys.exit(0)
