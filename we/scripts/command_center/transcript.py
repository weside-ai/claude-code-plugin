#!/usr/bin/env python3
"""A session's transcript, read for the tool call a permission prompt waits on.

The one reader of "the last ``tool_use`` of a session": ``worker_supervisor.prompt_id`` (a worker's
prompt held for 15 min) and ``event_sources.Round.sessions`` (an open prompt in any session) both
call ``last_tool_use``. A transcript is ``<projects>/<any project folder>/<session id>.jsonl``;
the file is read from its end in growing chunks, so a long session costs only its tail.
"""

from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

_SESSION = re.compile(r"^[A-Za-z0-9-]{1,80}$")
CHUNK = 256 * 1024


def projects_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def transcript_file(projects: Path, session_id: str | None) -> str | None:
    if not session_id or not _SESSION.match(session_id):  # never a glob pattern or a path
        return None
    files = glob.glob(str(Path(projects) / "*" / f"{session_id}.jsonl"))
    return files[0] if files else None


def _tool_use(line: str) -> tuple[str, str] | None:
    if '"tool_use"' not in line:
        return None
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    if not isinstance(entry, dict) or entry.get("type") != "assistant":
        return None
    content = (entry.get("message") or {}).get("content")
    for part in reversed(content if isinstance(content, list) else []):
        if isinstance(part, dict) and part.get("type") == "tool_use" and part.get("id"):
            return str(part["id"]), str(part.get("name") or "")
    return None


def last_tool_use(projects: Path, session_id: str | None) -> tuple[str, str] | None:
    """``(tool_use id, tool name)`` of the session's last tool call, None without one."""
    path = transcript_file(projects, session_id)
    if path is None:
        return None
    try:
        with open(path, "rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            span = CHUNK
            while True:
                start = max(0, size - span)
                fh.seek(start)
                lines = fh.read(size - start).decode("utf-8", "replace").splitlines()
                if start > 0:
                    lines = lines[1:]  # the first line is cut
                for line in reversed(lines):
                    hit = _tool_use(line)
                    if hit:
                        return hit
                if start == 0:
                    return None
                span *= 4
    except OSError:
        return None
