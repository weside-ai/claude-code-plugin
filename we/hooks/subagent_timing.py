"""SubagentStart/SubagentStop hook: append one JSON line per event to
~/.claude/we-timing/<session_id>.jsonl. Silent; never blocks (always exit 0)."""

import contextlib
import json
import re
import sys
import time
from pathlib import Path

FIELDS = ("agent_id", "agent_type", "cwd")


def record(payload: dict, home: Path) -> Path | None:
    session = re.sub(r"[^A-Za-z0-9_-]", "_", str(payload.get("session_id") or ""))
    if not session:
        return None
    line = {"ts": time.time(), "event": payload.get("hook_event_name")}
    line.update({k: payload.get(k) for k in FIELDS})
    out = home / ".claude" / "we-timing" / f"{session}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")
    return out


def main() -> None:
    with contextlib.suppress(Exception):  # a timing probe must never block a subagent
        record(json.load(sys.stdin), Path.home())


if __name__ == "__main__":
    main()
    sys.exit(0)
