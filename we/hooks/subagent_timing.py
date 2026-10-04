"""Measurement hook: append one JSON line per event to ~/.claude/we-timing/<session_id>.jsonl.

Events: SubagentStart/SubagentStop (timing), InstructionsLoaded (which rule file loaded and why),
PreToolUse on Skill and UserPromptExpansion (which skill ran, by Claude or typed by the user).
Records names only, never skill arguments or prompts. Silent; never blocks (always exit 0)."""

from __future__ import annotations

import contextlib
import json
import re
import sys
import time
from pathlib import Path

AGENT = ("agent_id", "agent_type")
FIELDS = {
    "SubagentStart": (*AGENT, "cwd"),
    "SubagentStop": (*AGENT, "cwd"),
    "InstructionsLoaded": (
        *AGENT,
        "file_path",
        "load_reason",
        "memory_type",
        "globs",
        "trigger_file_path",
        "parent_file_path",
    ),
    "PreToolUse": AGENT,
    "UserPromptExpansion": (*AGENT, "command_name", "command_source"),
}


def record(payload: dict, home: Path) -> Path | None:
    session = re.sub(r"[^A-Za-z0-9_-]", "_", str(payload.get("session_id") or ""))
    if not session:
        return None
    event = payload.get("hook_event_name")
    if event not in FIELDS:
        return None
    line = {"ts": time.time(), "event": event}
    line.update({k: payload.get(k) for k in FIELDS[event]})
    if event == "PreToolUse":
        line["skill"] = (payload.get("tool_input") or {}).get("skill")
    out = home / ".claude" / "we-timing" / f"{session}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")
    return out


def main() -> None:
    with contextlib.suppress(Exception):  # a measurement hook must never block
        record(json.load(sys.stdin), Path.home())


if __name__ == "__main__":
    main()
    sys.exit(0)
