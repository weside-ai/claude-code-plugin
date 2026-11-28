#!/usr/bin/env python3
"""A session's transcript, read for the tool call a permission prompt waits on and the model it runs on.

The one reader of "the tool call a session waits on": ``worker_supervisor.prompt_id`` (a worker's
prompt held for 15 min) and ``event_sources.Round.session_waiting`` (an open prompt in any
session) both call ``pending_tool_use``. A transcript is
``<projects>/<any project folder>/<session id>.jsonl``; it is read from its end in growing chunks,
so a long session costs only its tail.

The pending call is the first ``tool_use`` of the newest assistant message that has no
``tool_result`` yet: parallel calls prompt one after another, and each answered one gets its
result, so each prompt gets its own id. While the main transcript waits on a subagent (an
``Agent`` call without result), the newest subagent transcript (``<session id>/subagents/``) is
read the same way: its prompt is the one shown.

The one reader of "the model a session runs on" (``session_model``): the ``message.model`` of the
newest assistant entry of the main transcript that names a real model (``<synthetic>``, the entry
of a usage limit or an API error, is skipped). The brief or the launch flags only say what was
asked for; the transcript says what answered. Read by ``worker_supervisor.status_records``
(``we-worker status``), ``crew_view`` (the Zentrale's section Working) and, as the PR body's
``Model:`` line, by this file's command line:

    transcript.py model     prints `Model: <id>` for $CLAUDE_CODE_SESSION_ID, or
                            `Model: absent (<reason>)`; exit 0 either way
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from pathlib import Path

_SESSION = re.compile(r"^[A-Za-z0-9-]{1,80}$")
CHUNK = 256 * 1024
SUBAGENT_TOOLS = ("Agent", "Task")
NOT_A_MODEL = {"", "<synthetic>"}


def transcript_file(projects: Path, session_id: str | None) -> str | None:
    if not session_id or not _SESSION.match(session_id):  # never a glob pattern or a path
        return None
    files = glob.glob(str(Path(projects) / "*" / f"{session_id}.jsonl"))
    return files[0] if files else None


def _entries(lines: list[str]) -> list[dict]:
    out = []
    for line in lines:
        if '"tool_use"' not in line and '"tool_result"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


def _pending(entries: list[dict]) -> tuple[str, str] | None:
    """The first unanswered call of the newest message with calls, else that message's last call."""
    calls: list[tuple[str, str, str]] = []  # (message id, tool_use id, name)
    answered: set[str] = set()
    for entry in entries:
        message = entry.get("message") or {}
        content = message.get("content")
        for part in content if isinstance(content, list) else []:
            if not isinstance(part, dict):
                continue
            if (
                part.get("type") == "tool_use"
                and part.get("id")
                and entry.get("type") == "assistant"
            ):
                calls.append(
                    (str(message.get("id") or ""), str(part["id"]), str(part.get("name") or ""))
                )
            elif part.get("type") == "tool_result" and part.get("tool_use_id"):
                answered.add(str(part["tool_use_id"]))
    if not calls:
        return None
    newest = calls[-1][0]
    batch = [c for c in calls if c[0] == newest] if newest else [calls[-1]]
    for _, cid, name in batch:
        if cid not in answered:
            return cid, name
    return batch[-1][1], batch[-1][2]


def _read_pending(path: str) -> tuple[str, str] | None:
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
                hit = _pending(_entries(lines))
                if hit or start == 0:
                    return hit
                span *= 4
    except OSError:
        return None


def pending_tool_use(projects: Path, session_id: str | None) -> tuple[str, str] | None:
    """``(tool_use id, tool name)`` of the call the session waits on, None without one."""
    path = transcript_file(projects, session_id)
    if path is None:
        return None
    hit = _read_pending(path)
    if hit and hit[1] in SUBAGENT_TOOLS:
        subs = glob.glob(str(Path(path[: -len(".jsonl")]) / "subagents" / "*.jsonl"))
        try:
            inner = _read_pending(max(subs, key=os.path.getmtime)) if subs else None
        except OSError:  # a subagent file removed between the listing and the stat
            inner = None
        if inner:
            return inner
    return hit


def _model_in(lines: list[str]) -> str | None:
    for line in reversed(lines):
        if '"model"' not in line or '"assistant"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("type") != "assistant":
            continue
        model = str((entry.get("message") or {}).get("model") or "")
        if model not in NOT_A_MODEL:
            return model
    return None


def session_model(projects: Path, session_id: str | None) -> str | None:
    """The model id the session's newest real assistant entry ran on, None when unknown."""
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
                model = _model_in(lines)
                if model or start == 0:
                    return model
                span *= 4
    except OSError:
        return None


def model_line(projects: Path, session_id: str | None) -> str:
    """`Model: <id>`, or `Model: absent (<reason>)`: a value nobody read is never guessed."""
    if not session_id:
        return "Model: absent (no CLAUDE_CODE_SESSION_ID)"
    if transcript_file(projects, session_id) is None:
        return "Model: absent (no transcript)"
    model = session_model(projects, session_id)
    return f"Model: {model}" if model else "Model: absent (no assistant entry with a model)"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args != ["model"]:
        print("usage: transcript.py model", file=sys.stderr)
        return 2
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import claude_home  # noqa: PLC0415

    projects = claude_home.config_dir() / "projects"
    print(model_line(projects, os.environ.get("CLAUDE_CODE_SESSION_ID")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
