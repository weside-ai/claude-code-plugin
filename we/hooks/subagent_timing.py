"""Measurement hook: append one JSON line per event to ~/.claude/we-timing/<session_id>.jsonl.

Events: SubagentStart/SubagentStop (timing), InstructionsLoaded (which rule file loaded and why),
PreToolUse on Skill and UserPromptExpansion (which skill ran, by Claude or typed by the user).
Records names only, never skill arguments or prompts. Silent; never blocks (always exit 0).
A session's file ages out after 45 days (`scripts/state_prune.py`, at most one sweep a day).

Claude Code fires `InstructionsLoaded` for rules only. On `Stop` (the session's transcript) and
`SubagentStop` (the subagent's `agent_transcript_path`) the hook reads the transcript from the byte
offset stored in `<session>[.<agent_id>].offset` (with the last `load_reason`) and adds the rest with `source: "transcript"`:
each file of an `instructions` attachment outside `/.claude/rules/` (`AGENTS.md` and its kin,
`MEMORY.md`), and the L0 and role card in the SessionStart context (`context_load.start_contexts`,
`context_load.plugin_file`), with `chars` and the entry's time; `load_reason` is `compact` after a
compact boundary, also for a later run. `chars` of the L0 and the card is the length of the whole
SessionStart context they arrive in, not of the file. Sizes and paths only, never a file's or hook's text."""

from __future__ import annotations

import contextlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import state_prune

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


RULES = "/.claude/rules/"  # Claude Code's own InstructionsLoaded records these


def _safe(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(value or ""))


def _ts(entry: dict) -> float:
    try:
        return datetime.fromisoformat(str(entry["timestamp"]).replace("Z", "+00:00")).timestamp()
    except (KeyError, ValueError):
        return time.time()


def _loads(entry: dict, reason: str, seen: set[str]) -> list[dict]:
    """The load lines one transcript entry stands for; ``seen`` keeps one line per file and start
    (the SessionStart context stands in two attachment shapes)."""
    import context_load  # noqa: PLC0415 - 90 ms to import; the other events stay light

    att = entry.get("attachment")
    if not isinstance(att, dict):
        return []
    found: list[tuple[str, str, int]] = []
    if att.get("type") == "instructions":
        for f in att.get("files") or []:
            path = f.get("path") if isinstance(f, dict) else None
            if isinstance(path, str) and RULES not in path:
                found.append((path, str(f.get("type") or ""), len(str(f.get("content") or ""))))
    for text in context_load.start_contexts(att):
        part = context_load.plugin_file(text)
        if part:
            found.append((part, "Plugin", len(text)))
    out = []
    for path, kind, chars in found:
        if path in seen:
            continue
        seen.add(path)
        out.append(
            {
                "ts": _ts(entry),
                "event": "InstructionsLoaded",
                "file_path": path,
                "memory_type": kind,
                "load_reason": reason,
                "source": "transcript",
                "chars": chars,
            }
        )
    return out


def transcript_loads(payload: dict, home: Path, session: str) -> Path | None:
    """Append the loads Claude Code fires no event for, from the transcript past the stored
    offset; a second run over the same transcript adds nothing."""
    agent = payload.get("agent_id") if payload.get("hook_event_name") == "SubagentStop" else None
    source = payload.get("agent_transcript_path") if agent else payload.get("transcript_path")
    if not source:
        return None
    folder = home / ".claude" / "we-timing"
    folder.mkdir(parents=True, exist_ok=True)
    mark = folder / f"{session}{'.' + _safe(agent) if agent else ''}.offset"
    try:
        stored = mark.read_text().split()
        offset = int(stored[0])
        reason = stored[1] if len(stored) > 1 else "session_start"
    except (OSError, ValueError, IndexError):
        offset, reason = 0, "session_start"
    with open(source, "rb") as fh:
        fh.seek(0, 2)
        if offset > fh.tell():
            offset, reason = 0, "session_start"  # a rewritten transcript: read it again
        fh.seek(offset)
        data = fh.read()
    data = data[: data.rfind(b"\n") + 1]  # whole lines only; the rest waits for the next run
    lines: list[dict] = []
    seen: set[str] = set()
    for raw in data.splitlines():
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary":
            reason, seen = "compact", set()
            continue
        for line in _loads(entry, reason, seen):
            if agent:
                line.update({k: payload.get(k) for k in AGENT})
            lines.append(line)
    out = folder / f"{session}.jsonl"
    if lines:
        with out.open("a", encoding="utf-8") as fh:
            fh.writelines(json.dumps(x) + "\n" for x in lines)
    mark.write_text(f"{offset + len(data)} {reason}")
    state_prune.prune(folder, ("*.jsonl", "*.offset"))
    return out


def record(payload: dict, home: Path) -> Path | None:
    session = _safe(payload.get("session_id"))
    if not session:
        return None
    event = payload.get("hook_event_name")
    if event == "Stop":
        return transcript_loads(payload, home, session)
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
    state_prune.prune(out.parent, ("*.jsonl", "*.offset"))  # a session's files age out (45 days)
    if event == "SubagentStop":
        with contextlib.suppress(Exception):
            transcript_loads(payload, home, session)
    return out


def main() -> None:
    with contextlib.suppress(Exception):  # a measurement hook must never block
        record(json.load(sys.stdin), Path.home())


if __name__ == "__main__":
    main()
    sys.exit(0)
