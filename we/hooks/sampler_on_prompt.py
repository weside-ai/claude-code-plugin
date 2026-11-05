#!/usr/bin/env python3
"""UserPromptSubmit hook: a dead sampler and a blocked worker, each named once on the next prompt.

Two kinds of context line, nothing else, no subprocess and no network:

- ``sampler: stale since <N> min (last line <ts>)`` (``scripts/sampler_age.py``'s verdict) for a
  session holding the crew's ``coordinator`` or ``machinery`` role, once per stale episode: an
  episode is keyed by the flow log's last line, so a fresh line ends it and the next death is a
  new one.
- ``blocked: <worker> (<key>) waits on <waiting_on> (<kind>) since <HH:MM>: <command>`` for every
  board line carrying ``blocked`` (``board.py blocked``, docs/board.md § Blocked workers), to the
  worker's starter (``blocked.starter_session_id`` is this session) and to the coordinator, once
  per wait (``blocked.since``).

Silent without the crew's ``flow.log_dir``: then it reads neither the flow log nor the board. Once
markers are empty files under ``<flow.log_dir>/.notified/``, one per session and episode, created
with ``O_EXCL`` so two prompts cannot both print. The board file is the plugin option
``boardFile`` (``CLAUDE_PLUGIN_OPTION_BOARDFILE``, else ``pluginConfigs`` in
``~/.claude/settings.json``), default ``~/.claude/we-state/board.json``; ``~/`` and a relative
path count from the home folder. Fail-open: every error exits 0 without output.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import crew as crew_mod
import flow_log
import sampler_age

DEFAULT_BOARD = "~/.claude/we-state/board.json"
WATCHERS = ("coordinator", "machinery")


def board_file(environ: dict) -> Path:
    value = environ.get("CLAUDE_PLUGIN_OPTION_BOARDFILE")
    if not value:
        try:
            with open(Path.home() / ".claude" / "settings.json", encoding="utf-8") as fh:
                settings = json.load(fh)
            value = settings["pluginConfigs"]["we@weside-ai"]["options"]["boardFile"]
        except (OSError, ValueError, KeyError, TypeError):
            value = None
    path = Path(str(value or DEFAULT_BOARD)).expanduser()
    return path if path.is_absolute() else Path.home() / path


def first_time(notified: Path, name: str) -> bool:
    """True exactly once per marker name."""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    notified.mkdir(parents=True, exist_ok=True)
    try:
        os.close(os.open(str(notified / safe), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644))
    except FileExistsError:
        return False
    return True


def blocked_line(line: dict, tz: str) -> str:
    blocked = line["blocked"]
    key = blocked.get("key") or next(iter(line.get("keys") or []), None) or "no key"
    try:
        since = flow_log.parse_ts(blocked.get("since"))
        hhmm = since.astimezone(ZoneInfo(tz)).strftime("%H:%M")
    except (AttributeError, ValueError, KeyError):
        hhmm = "?"
    text = (
        f"blocked: {line.get('name')} ({key}) waits on {line.get('waiting_on') or '?'} "
        f"({blocked.get('kind') or '?'}) since {hhmm}"
    )
    command = " ".join(str(blocked.get("command") or "").split())
    return f"{text}: {command}" if command else text


def blocked_lines(environ: dict, session: str, coordinator: bool, tz: str, notified: Path):
    try:
        with open(board_file(environ), encoding="utf-8") as fh:
            board = json.load(fh)
    except (OSError, ValueError):
        return []
    sessions = board.get("sessions") if isinstance(board, dict) else None
    out = []
    for line in sessions if isinstance(sessions, list) else []:
        blocked = line.get("blocked") if isinstance(line, dict) else None
        if not isinstance(blocked, dict):
            continue
        mine = bool(session) and blocked.get("starter_session_id") == session
        if not (mine or coordinator):
            continue
        if first_time(notified, f"{session}-blocked-{line.get('name')}-{blocked.get('since')}"):
            out.append(blocked_line(line, tz))
    return out


def output(hook_input: dict, environ: dict | None = None) -> dict | None:
    env = os.environ if environ is None else environ
    log_dir, tz, flow, crew = flow_log.configured(hook_input.get("cwd") or None)
    if log_dir is None:
        return None
    session = str(hook_input.get("session_id") or "nosession")
    notified = log_dir / ".notified"
    held = [r for r in WATCHERS if crew_mod.holds_role(crew, r, env, hook_input)]
    lines = []
    if held:
        code, text, episode = sampler_age.verdict(log_dir, tz, flow["stale_min"])
        if code and first_time(notified, f"{session}-stale-{episode}"):
            lines.append(text)
    lines += blocked_lines(env, session, "coordinator" in held, tz, notified)
    if not lines:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(lines),
        }
    }


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        result = output(data if isinstance(data, dict) else {})
    except Exception:
        return 0
    if result:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
