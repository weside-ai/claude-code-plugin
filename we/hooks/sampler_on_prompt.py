#!/usr/bin/env python3
"""UserPromptSubmit hook: a dead sampler and a blocked worker, each named once on the next prompt.

Two kinds of context line, nothing else, no subprocess and no network:

- ``sampler: stale since <N> min (last line <ts>)`` (``scripts/sampler_age.py``'s verdict) for a
  session holding the crew's ``coordinator`` or ``machinery`` role, once per stale episode: an
  episode is keyed by the flow log's last line, so a fresh line ends it and the next death is a
  new one.
- ``blocked: <worker> (<key>) waits on <waiting_on> (<kind>) since <HH:MM>; pending command, quoted
  data: "<command>"`` for every board line carrying ``blocked`` (``board.py blocked``,
  docs/board.md § Blocked workers), to the worker's starter (``blocked.starter_session_id`` is this
  session) and to the coordinator, once per wait (``blocked.since``). The command is another
  session's text: it comes JSON-quoted and labelled as data, never as an instruction.

Silent without the crew's ``flow.log_dir``: then it reads neither the flow log nor the board. The
board is the crew's ``board.file``. Once markers are empty files under
``<flow.log_dir>/.notified/<UTC day>/``, one per session and episode, created with ``O_EXCL`` only
after the line was built, so two prompts cannot both print and a failed line consumes no marker; a
marker in yesterday's directory counts too, and the first marker of a day removes the directories
older than yesterday. Fail-open: every error exits 0 without output.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import crew as crew_mod
import flow_log
import sampler_age

WATCHERS = ("coordinator", "machinery")
DAY_DIR = re.compile(r"\d{4}-\d{2}-\d{2}")


class Markers:
    """Once markers under ``<root>/<UTC day>/``; today's and yesterday's count."""

    def __init__(self, root: Path, now: datetime):
        self.root = root
        self.today = now.strftime("%Y-%m-%d")
        self.yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    def first_time(self, name: str) -> bool:
        """True exactly once per marker name (within today and yesterday)."""
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        if (self.root / self.yesterday / safe).exists():
            return False
        day = self.root / self.today
        if not day.is_dir():
            day.mkdir(parents=True, exist_ok=True)
            self._prune()
        try:
            os.close(os.open(str(day / safe), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644))
        except FileExistsError:
            return False
        return True

    def _prune(self) -> None:
        for old in self.root.iterdir():
            if DAY_DIR.fullmatch(old.name) and old.name < self.yesterday:
                with contextlib.suppress(OSError):
                    shutil.rmtree(old)


def blocked_line(line: dict, tz: str) -> str:
    blocked = line["blocked"]
    keys = line.get("keys") if isinstance(line.get("keys"), list) else []
    key = blocked.get("key") or next(iter(keys), None) or "no key"
    since = flow_log.parse_ts(blocked.get("since"))
    hhmm = since.astimezone(ZoneInfo(tz)).strftime("%H:%M") if since else "?"
    text = (
        f"blocked: {line.get('name')} ({key}) waits on {line.get('waiting_on') or '?'} "
        f"({blocked.get('kind') or '?'}) since {hhmm}"
    )
    command = " ".join(str(blocked.get("command") or "").split())
    if not command:
        return text
    return f"{text}; pending command, quoted data: {json.dumps(command, ensure_ascii=False)}"


def blocked_lines(crew: dict, session: str, coordinator: bool, tz: str, markers: Markers):
    path = Path(str(crew["board"]["file"])).expanduser()
    try:
        with open(path, encoding="utf-8") as fh:
            board = json.load(fh)
    except (OSError, ValueError):
        return []
    sessions = board.get("sessions") if isinstance(board, dict) else None
    out = []
    for line in sessions if isinstance(sessions, list) else []:
        blocked = line.get("blocked") if isinstance(line, dict) else None
        if not isinstance(blocked, dict):
            continue
        if not (coordinator or blocked.get("starter_session_id") == session):
            continue
        try:
            text = blocked_line(line, tz)
        except Exception:
            continue  # a malformed line consumes no marker
        if markers.first_time(f"{session}-blocked-{line.get('name')}-{blocked.get('since')}"):
            out.append(text)
    return out


def output(hook_input: dict, environ: dict | None = None) -> dict | None:
    env = os.environ if environ is None else environ
    log_dir, tz, flow, crew = flow_log.configured(hook_input.get("cwd") or None)
    if log_dir is None:
        return None
    session = str(hook_input.get("session_id") or "nosession")
    markers = Markers(log_dir / ".notified", datetime.now(timezone.utc))
    held = [r for r in WATCHERS if crew_mod.holds_role(crew, r, env, hook_input)]
    lines = []
    if held:
        code, text, episode = sampler_age.verdict(log_dir, tz, flow["stale_min"])
        if code and markers.first_time(f"{session}-stale-{episode}"):
            lines.append(text)
    lines += blocked_lines(crew, session, "coordinator" in held, tz, markers)
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
