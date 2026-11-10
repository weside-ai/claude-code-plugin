#!/usr/bin/env python3
"""SessionStart hook (every source: startup, resume, clear, compact): the crew process L0.

Only in a repo with a crew (``scripts/crew.py find``); no crew → nothing. A crew ``crew.py``
refuses (``CrewError``) is never silence: the text renders from ``crew.fallback`` (the defaults)
and its first line is ``<labels.crew_unreadable>: <reason>``; such a serve is not logged (the
board path is a crew value). A crew with unknown keys renders with the line
``<labels.crew_unknown_keys>: <keys>`` first. The session kind (``crew.session_kind``) picks
the text ``scripts/render_process.py`` renders: a worker (``agent_type``, a process worker, or
``WE_ROLE=worker`` without a pin) the short form ``process/L0-worker.md``, every other session
(a consultation too) the L0 ``process/L0.md``. ``source`` is not read, so every source gets the
same text. Claude Code replaces a hook output over its cap (``AUTHORING.md`` § Measured facts) by
a preview, so the text is gated at ``render_process.BUDGET``: over it, nothing is printed, one
stderr line names the template to read, exit 1.

After printing, it appends ``{ts, session_id, pid, source, by: "plugin", crew}`` (``crew``:
``crew.crew_id``) to ``l0-served.jsonl`` under a flock with a 2 s wait, replaced atomically,
in the crew's state directory (``crew.state_dir``: ``WE_STATE_DIR``, the crew's ``state_dir``, else
``~/.claude/we-state``; the last ``LOG_KEEP`` lines kept), so two crews with their own folders
keep two logs; a write failure is ignored, the log is evidence of doubles, not a gate.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - no flock on Windows
    fcntl = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import crew as crewlib
import render_process

LOG_NAME = "l0-served.jsonl"
LOG_KEEP = 1_000


def claude_pid(start: int | None = None) -> int:
    """The first ancestor whose argv0 is ``claude`` (this session's process), else the parent."""
    pid = start or os.getppid()
    for _ in range(32):
        try:
            argv0 = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0", 1)[0].decode()
            stat = Path(f"/proc/{pid}/stat").read_text()
        except (OSError, UnicodeDecodeError):
            break
        if Path(argv0).name == "claude":
            return pid
        parent = int(stat.rsplit(")", 1)[1].split()[1])
        if parent <= 1:
            break
        pid = parent
    return os.getppid()


def log_served(
    crew: dict, hook_input: dict, by: str = "plugin", crew_path: Path | None = None
) -> None:
    try:
        path = crewlib.state_dir(crew_path, crew) / LOG_NAME
    except crewlib.CrewError:
        return
    line = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "session_id": str(hook_input.get("session_id") or ""),
        "pid": claude_pid(),
        "source": str(hook_input.get("source") or ""),
        "by": by,
    }
    if crew_path is not None:
        with contextlib.suppress(OSError, crewlib.CrewError):
            line["crew"] = crewlib.crew_id(crew_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _locked(path.with_name(path.name + ".lock")):
            old = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
            lines = [*old, json.dumps(line)][-LOG_KEEP:]
            tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
            tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
            os.replace(tmp, path)
    except (OSError, TimeoutError):
        pass  # a log line, never a reason to fail a session start


LOCK_WAIT_S = 2.0


@contextlib.contextmanager
def _locked(lock: Path):
    """An exclusive flock on ``lock``, waiting at most ``LOCK_WAIT_S``; TimeoutError past it."""
    fd = os.open(str(lock), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + LOCK_WAIT_S
        while fcntl is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(str(lock)) from None
                time.sleep(0.05)
        yield
    finally:
        os.close(fd)


def output(hook_input: dict, environ: dict | None = None) -> tuple[str | None, str | None]:
    """(additionalContext or None, stderr line or None)."""
    env = os.environ if environ is None else environ
    cwd = hook_input.get("cwd") or os.getcwd()
    crew_path = None
    try:
        crew_path, crew = crewlib.find_and_load(cwd)
    except crewlib.CrewError as exc:
        crew = crewlib.fallback(crewlib.find(cwd), str(exc))
    if not crew:
        return None, None
    kind, _ = crewlib.session_kind(env, hook_input.get("agent_type"), hook_input)
    form = "worker" if kind == "worker" else "full"
    shown = render_process.PROCESS / ("L0-worker.md" if form == "worker" else "L0.md")
    try:
        text = render_process.render_l0(crew, form)
    except (OSError, render_process.RenderError) as exc:
        return None, f"process_on_start: {shown} not rendered ({exc})"
    if len(text) > render_process.BUDGET:
        return None, (
            f"process_on_start: rendered L0 has {len(text)} chars > {render_process.BUDGET}; "
            f"not loaded, read {shown} (render_process.py --role master)"
        )
    if not crew.get("crew_error"):
        log_served(crew, hook_input, crew_path=crew_path)
    return text, None


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        data = {}
    hook_input = data if isinstance(data, dict) else {}
    text, error = output(hook_input)
    if error:
        print(error, file=sys.stderr)
        return 1
    if text is not None:
        out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
        json.dump(out, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
