#!/usr/bin/env python3
"""The launcher's supervisor of one process worker, its queue, its status and its garbage collection.

`we-worker` starts one supervisor per worker (`spawn`, detached, no model). It waits until
`claude agents --json` lists a living session of the worker's name, then polls it every 30 s,
holding the row by its session id (a starting background row lists no pid yet):

- a permission prompt (`waitingFor: "permission prompt"`, what `we-worker waiting` reads) that
  stays on the same tool call for 15 minutes becomes one board news item for the human
  (`board.py news worker`), once per prompt;
- when the session's process is gone, the end reason comes from the transcript's last assistant
  entry (`usage-limit`, `auth`) or the timer file's passed `deadline` (`time-limit`): `end_reason`
  and `api_mark`, which `we-worker status` reads too (`status_lines`). With a
  reason, one line with the resume command goes to the starter: into its inbox socket (the
  starter's `CLAUDE_CODE_MESSAGING_SOCKET` and `_TOKEN`, inherited at the spawn and never written
  to a file), else as a board news item, and `<name>.resume.json` keeps the session id for
  `we-worker <name> --resume <name>` (`keep_resume`; `we-worker stop` writes it too). A worker
  stopped with `we-worker stop` (its settings file is already gone) ends without a line;
- a worker whose `state` stays `blocked` for `workers.blocked_notify_minutes` (default 15) gets one
  line to its starter, once per block: `<name> blocked since <HH:MM> UTC: <its last text line>`,
  over the same inbox socket, else as a board news item; 312 of 485 measured worker hours were
  `blocked`, and the starter did not know;
- a worker whose report is in (`state` `done`, or a window worker idle after its turn sent the
  report to its marker's starter, `hooks/worker_report_gate.py`'s test) and idle for
  `workers.idle_stop_minutes` (default 30) is stopped with `we-worker stop`, its tree stays (close
  owns the teardown) and the starter gets one line; 161 workers sat idle after their end, median
  0.84 h. Never a worker that is `blocked` or `working`, has a queued start of its name, whose
  launcher marker carries `parked` (work parked for a checkpoint), or whose job still runs a
  background task (`tasks_in_flight`: a worker that reported and waits on its CI watcher reads
  `done`; 30 of 844 `done` job states carried one). `0` or `null` turns a key off;
- then it removes the worker's settings file and timer file, unless a living session of the same
  name holds them again, or the worker ended on a usage limit or an auth error: a resumable worker
  keeps both (the timer file names its starter, limit and deadline), `gc` ages them out after 7 days. A worker never seen within 5 minutes keeps its files (a start
  held by a dialog may still read them); `gc` ages them out.

`gc` touches only the plugin's own files of sessions that no longer live (older than 10 minutes;
a worker whose last transcript entry is a usage limit or an auth error is resumable, its files stay
7 days, as does every `<name>.resume.json`): the settings files
`<name>.settings.json` and timer files `<name>.json` of the state dir, queued starts whose waiter
is gone and whose deadline passed (entry and brief), and the launcher's marker
(with brief and settings beside it, `worker_launch.clear_marker`) in the repo's worktrees. A
merged, clean worktree whose marker names no living session keeps its marker and is listed with
the repo's remove command (`workers.remove_worktree`, else `git worktree remove`); gc never
removes a worktree. Claude Code's own job directories (`~/.claude/jobs/<id>`) are only counted:
whether `--resume` still needs one cannot be told from outside. Without `--apply` it only prints
what it would remove (the default). A file younger than 10 minutes stays (a start in flight). When
`claude agents --json` cannot be read, gc refuses: nothing is judged dead on a guess.

The queue (`we-worker <name> --bg --queue`): see the comment above `queue_dir`.

Usage:
  worker_supervisor.py spawn --name <n> --tree <dir>   the supervisor, detached
  worker_supervisor.py run --name <n> --tree <dir>     the supervisor in the foreground
  worker_supervisor.py gc [--repo <dir>] [--apply | --dry-run]
  worker_supervisor.py status [--key <name|id>] [--json]  `we-worker status`, `claude agents --json` on stdin
  worker_supervisor.py queue --name <n> --tree <dir> [--starter S] [--timeout 2h] [--has-brief]
                            [--lane build|utility]
                                                       registers a refused start (its we-worker
                                                       call NUL-separated on stdin, the brief
                                                       last) and spawns its waiter
  worker_supervisor.py unqueue --name <n>              removes a queued start; exit 1 without one
  worker_supervisor.py wait-queue --name <n>           the waiter, in the foreground
  worker_supervisor.py stopped --name <n> --session <id> [--tree <dir>]
                                                       keeps the resume file, prints the resume line
  worker_supervisor.py resolve --key <id|prefix|name>  the session id a --resume resumes
                                                       (`resolve_session`, `claude agents --json`
                                                       on stdin); exit 1 none, 4 ambiguous
State dir: `$WE_WORKER_STATE_DIR`, else `~/.claude/we-state/workers`.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import glob
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import worker_launch as wl

sys.path.insert(0, str(Path(__file__).resolve().parent / "command_center"))
from transcript import pending_tool_use

POLL_S = 30
APPEAR_S = 300
PROMPT_AGE_S = 15 * 60
GRACE_S = 10 * 60
RESUMABLE = ("usage-limit", "auth")  # the ends `we-worker status` prints a resume command for
RESUMABLE_AGE_S = 7 * 24 * 3600
RESUME_SUFFIX = ".resume.json"
BOARD_TIMEOUT_S = 60


def state_dir() -> Path:
    return Path(
        os.environ.get("WE_WORKER_STATE_DIR") or Path.home() / ".claude" / "we-state" / "workers"
    )


def projects_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def jobs_dir() -> Path:
    return Path.home() / ".claude" / "jobs"


def _text(entry: dict) -> str:
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return str(content or "")


def last_assistant(projects: Path, session_id: str | None) -> dict | None:
    """The transcript's last assistant entry; reads the tail only, widening until it finds one."""
    files = glob.glob(str(projects / "*" / f"{session_id}.jsonl")) if session_id else []
    if not files:
        return None
    with open(files[0], "rb") as fh:
        size, n = fh.seek(0, 2), 1 << 16
        while True:
            fh.seek(max(0, size - n))
            lines = fh.read().splitlines()
            if size > n:
                lines = lines[1:]  # the first line may be cut
            for line in reversed(lines):
                if b'"assistant"' not in line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if isinstance(entry, dict) and entry.get("type") == "assistant":
                    return entry
            if size <= n:
                return None
            n *= 4


def api_mark(entry: dict | None) -> str | None:
    """`usage-limit`, `auth` or None for the last assistant entry: the one owner of the end
    reason's API part, read by `end_reason`, `gc` and `we-worker status` (`status_lines`)."""
    if not entry:
        return None
    err = entry.get("error") if entry.get("isApiErrorMessage") else None
    if err == "rate_limit":
        return "usage-limit"
    if err in ("authentication_failed", "oauth_org_not_allowed"):
        return "auth"
    return "usage-limit" if re.search(r"(hit|reached) your .*limit", _text(entry)) else None


def prompt_id(projects: Path, session_id: str | None) -> str | None:
    """The id of the tool call a permission prompt waits on (``transcript.pending_tool_use``)."""
    hit = pending_tool_use(projects, session_id)
    return hit[0] if hit else None


def timer_deadline(state: Path, name: str) -> float | None:
    try:
        data = json.loads((state / f"{name}.json").read_text())
        when = dt.datetime.fromisoformat(str(data["deadline"]).replace("Z", "+00:00"))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return when.timestamp()


def end_reason(projects: Path, state: Path, name: str, session_id: str | None, now: float):
    """Why a worker ended: `usage-limit` or `auth` (`api_mark`), else `time-limit` once the timer's
    deadline passed, else None."""
    mark = api_mark(last_assistant(projects, session_id))
    if mark:
        return mark
    deadline = timer_deadline(state, name)
    return "time-limit" if deadline is not None and deadline <= now else None


WHEN = {
    "usage-limit": "after the reset",
    "auth": "once the login is back",
    "time-limit": "if needed",
}


def resume_command(name: str, session_id: str | None, tree: str | None = None) -> str:
    """The command that resumes the worker `name` (the one owner: the supervisor's notice,
    `we-worker status` and `we-worker stop` print it); without a tree it resumes where it is
    run."""
    if not tree:
        where = f"we-worker {name}"
    elif wl.main_checkout(Path(tree)):
        where = f"cd {tree} && we-worker {name} --here"
    else:
        where = f"we-worker {name} --tree {tree}"
    return f"{where} --bg --resume {session_id or '<session id>'}"


def notice(name: str, reason: str, session_id: str | None, tree: str) -> str:
    resume = resume_command(name, session_id, tree)
    return f"we-worker: {name} ended ({reason}) in {tree}. Resume {WHEN[reason]}: {resume}"


def keep_resume(state: Path, name: str, session_id: str | None, tree: str | None) -> None:
    """`<state>/<name>.resume.json`: the session a `we-worker <name> --resume <name>` finds once
    `claude agents` no longer lists it; `gc` ages it out after `RESUMABLE_AGE_S`."""
    if not session_id:
        return
    with contextlib.suppress(OSError):
        state.mkdir(parents=True, exist_ok=True)
        doc = {"name": name, "session_id": session_id, "tree": tree, "ended_at": time.time()}
        (state / f"{name}{RESUME_SUFFIX}").write_text(json.dumps(doc, indent=2) + "\n")


def kept_session(state: Path, name: str) -> str | None:
    """The session id of `keep_resume`'s file of `name`, None without one."""
    try:
        doc = json.loads((state / f"{name}{RESUME_SUFFIX}").read_text())
    except (OSError, ValueError):
        return None
    sid = doc.get("session_id") if isinstance(doc, dict) else None
    return str(sid) if sid else None


def deliver(sock_path: str, token: str, text: str) -> None:
    """One user line into a session's inbox socket (the format of `wake_poller.deliver`)."""
    lines = (
        json.dumps({"type": "auth", "token": token})
        + "\n"
        + json.dumps({"type": "user", "message": {"role": "user", "content": text}})
        + "\n"
    )
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(10)
    try:
        conn.connect(sock_path)
        conn.sendall(lines.encode("utf-8"))
        conn.shutdown(socket.SHUT_WR)
    finally:
        conn.close()


def to_starter(text: str, environ: dict | None = None) -> bool:
    env = os.environ if environ is None else environ
    sock, token = env.get("CLAUDE_CODE_MESSAGING_SOCKET"), env.get("CLAUDE_CODE_MESSAGING_TOKEN")
    if not (sock and token):
        return False
    try:
        deliver(sock, token, text)
    except OSError:
        return False
    return True


def board_news(tree: str, item_id: str, title: str, body: str = "") -> bool:
    """One `board.py news worker` item (idempotent by id), run in the worker's tree."""
    script = Path(__file__).resolve().with_name("board.py")
    argv = [sys.executable, str(script), "news", "worker", "--id", item_id, "--title", title]
    if body:
        argv += ["--body", body]
    try:
        out = subprocess.run(
            argv, cwd=tree, capture_output=True, text=True, check=False, timeout=BOARD_TIMEOUT_S
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0


def _named(rows: list[dict], name: str) -> list[dict]:
    return [r for r in rows if r.get("name") == name]


def _living(rows: list[dict], name: str) -> list[dict]:
    return [r for r in _named(rows, name) if wl._pid_lives(r.get("pid", "-"))]


def _remove_files(state: Path, name: str) -> list[str]:
    gone = []
    # the brief file (`worker_launch.write_brief`) goes too; launched.jsonl stays
    for path in (
        state / f"{name}.settings.json",
        state / f"{name}.json",
        state / f"{name}.brief.md",
    ):
        with contextlib.suppress(OSError):
            path.unlink()
            gone.append(path.name)
    return gone


def _watch_prompt(row, name, tree, sid, projects, now, first_seen, reported, board) -> None:
    """One board item per permission prompt that holds the same tool call for `PROMPT_AGE_S`."""
    if row.get("waitingFor") != "permission prompt":
        first_seen.clear()
        return
    prompt = prompt_id(projects, sid) or f"{sid}:prompt"
    since = first_seen.setdefault(prompt, now)
    if now - since < PROMPT_AGE_S or prompt in reported:
        return
    reported.add(prompt)
    board(
        tree,
        f"W-{name}-{prompt[-8:]}",
        f"{name} waits on a permission prompt for {int((now - since) // 60)} min",
        f"Answer it: claude attach {row.get('id') or sid}; the tool call: we-worker waiting",
    )


IDLE_DEFAULTS = {"blocked_notify_minutes": 15, "idle_stop_minutes": 30}


def idle_limits(tree: str) -> dict[str, float | None]:
    """`workers.blocked_notify_minutes` and `workers.idle_stop_minutes` in seconds, None when off
    (`0` or `null`); a missing or unreadable value keeps its default: a typo must not silence it."""
    try:
        block = wl.workers_block(Path(tree))
    except wl.LaunchError:
        block = {}
    out: dict[str, float | None] = {}
    for key, default in IDLE_DEFAULTS.items():
        value = block.get(key, default)
        if value is None or value == 0:
            out[key] = None
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            out[key] = default * 60.0
        else:
            out[key] = float(value) * 60.0
    return out


def last_line(projects: Path, session_id: str | None) -> str:
    """The last non-blank line of the transcript's last assistant text, cut to 200 characters."""
    text = _text(last_assistant(projects, session_id) or {})
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[-1][:200] if lines else ""


def report_in(row: dict, marker: dict | None, projects: Path, sid: str | None) -> bool:
    """A background worker's `done`, or a window worker idle after its turn sent the report."""
    if row.get("state") == "done":
        return True
    if row.get("state") or row.get("status") != "idle":
        return False
    lead = (marker or {}).get("starter")
    files = glob.glob(str(projects / "*" / f"{sid}.jsonl")) if sid and lead else []
    if not files:
        return False
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
    try:
        from worker_report_gate import reported  # noqa: PLC0415 (a window worker alone needs it)
    finally:
        sys.path.pop(0)
    try:
        return reported(files[0], str(lead))
    except OSError:
        return False


def stop_by_launcher(row: dict) -> bool:
    """`we-worker stop <id>`: the launcher's stop (settings file, resume file, left processes)."""
    script = Path(__file__).resolve().with_name("we-worker")
    ident = wl._ident(row)
    if not ident:
        return False
    try:
        out = subprocess.run(
            ["bash", str(script), "stop", ident],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            env=wl.claude_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0


def tasks_in_flight(jobs: Path, row: dict) -> int:
    """The background tasks (shells, monitors) a background session's job still runs: Claude Code's
    `<jobs>/<short id>/state.json` `inFlight.tasks`; `claude agents --json` does not show them, its
    `state` reads `done` while a watcher runs. 0 without a readable job file (a window worker)."""
    short = str(row.get("id") or "") or str(row.get("sessionId") or "")[:8]
    if not short or "/" in short:
        return 0
    try:
        doc = json.loads((jobs / short / "state.json").read_text())
        tasks = (doc.get("inFlight") or {}).get("tasks") or 0
    except (OSError, ValueError, AttributeError):
        return 0
    return tasks if isinstance(tasks, int) and not isinstance(tasks, bool) else 0


class Idle:
    """The blocked notice and the idle stop of one supervised worker, one `poll` per sample."""

    def __init__(
        self, name, tree, sid, limits, projects, state, send, board, stop, log, jobs=None
    ):
        self.name, self.tree, self.sid, self.limits = name, tree, sid, limits
        self.projects, self.state, self.jobs = projects, state, jobs or jobs_dir()
        self.send, self.board, self.stop, self.log = send, board, stop, log
        self.blocked_since: float | None = None
        self.blocked_said = False
        self.idle_since: float | None = None
        self.stop_tried = False

    def poll(self, row: dict, now: float) -> None:
        self._blocked(row, now)
        self._idle(row, now)

    def _blocked(self, row: dict, now: float) -> None:
        limit = self.limits.get("blocked_notify_minutes")
        if row.get("state") != "blocked":
            self.blocked_since, self.blocked_said = None, False
            return
        if self.blocked_since is None:
            self.blocked_since = now
        if limit is None or self.blocked_said or now - self.blocked_since < limit:
            return
        self.blocked_said = True
        hhmm = dt.datetime.fromtimestamp(self.blocked_since, dt.timezone.utc).strftime("%H:%M")
        why = last_line(self.projects, self.sid) or str(row.get("waitingFor") or "no status line")
        line = f"{self.name} blocked since {hhmm} UTC: {why}"
        if not self.send(f"we-worker: {line}"):
            self.board(self.tree, f"W-{self.name}-blocked-{int(self.blocked_since)}", line)

    def _idle(self, row: dict, now: float) -> None:
        limit = self.limits.get("idle_stop_minutes")
        marker = wl.read_marker(self.tree) if limit is not None else None
        if (
            limit is None
            or not report_in(row, marker, self.projects, self.sid)
            or tasks_in_flight(self.jobs, row)
        ):
            self.idle_since = None
            return
        if self.idle_since is None:
            self.idle_since = now
        if self.stop_tried or now - self.idle_since < limit:
            return
        if (marker or {}).get("parked") or any(
            q.get("name") == self.name for q in queued(self.state)
        ):
            return
        self.stop_tried = True  # one try: a refused stop is logged, never repeated every poll
        minutes = int((now - self.idle_since) // 60)
        if self.stop(row):
            self.send(
                f"we-worker: {self.name} stopped after {minutes} min idle with its report in; "
                f"its tree stays: {self.tree}"
            )
        else:
            self.log(f"{self.name}: idle {minutes} min, we-worker stop failed")


def supervise(
    name: str,
    tree: str,
    *,
    sessions: Callable[[], list[dict]] = wl.sessions,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
    send: Callable[[str], bool] = to_starter,
    board: Callable[..., bool] = board_news,
    state: Path | None = None,
    projects: Path | None = None,
    log: Callable[[str], None] = lambda _line: None,
    stop: Callable[[dict], bool] = stop_by_launcher,
    limits: dict | None = None,
    jobs: Path | None = None,
) -> str:
    """Watch the worker `name` until its process ends; returns what happened as one word."""
    state = state or state_dir()
    projects = projects or projects_dir()
    limits = idle_limits(tree) if limits is None else limits
    give_up = clock() + APPEAR_S
    row = None
    while row is None:
        with contextlib.suppress(wl.LaunchError):
            found = _living(sessions(), name)
            row = found[-1] if found else None
        if row is None:
            if clock() >= give_up:
                # its files stay: a start held by a dialog may still read them; gc ages them out
                log(f"{name}: no living session within {APPEAR_S} s")
                return "never-seen"
            sleep(POLL_S)
    pid, sid = row.get("pid"), row.get("sessionId")
    first_seen: dict[str, float] = {}
    reported: set[str] = set()
    idle = Idle(name, tree, sid, limits, projects, state, send, board, stop, log, jobs)
    while True:
        # A starting `claude --bg` row lists no pid and gets it a moment later (measured 22.11.:
        # `pid: null`, then a number). Bound to that first `null`, the next poll found no row and
        # the supervisor ended after 35 s with its worker still running: no idle stop, no blocked
        # notice. The session id holds the row; a pid it gets later is taken over.
        try:
            mine = [
                r
                for r in _named(sessions(), name)
                if r.get("pid") == pid or (sid and r.get("sessionId") == sid)
            ]
        except wl.LaunchError:
            mine = [row]
        if mine and mine[-1].get("pid") not in (None, "", "-"):
            pid = mine[-1].get("pid")
        if not mine or not wl._pid_lives(pid):
            break
        row = mine[-1]
        _watch_prompt(row, name, tree, sid, projects, clock(), first_seen, reported, board)
        idle.poll(row, clock())
        sleep(POLL_S)
    stopped = not (state / f"{name}.settings.json").exists()
    reason = None if stopped else end_reason(projects, state, name, sid, clock())
    if reason:
        keep_resume(state, name, sid, tree)
        line = notice(name, reason, sid, tree)
        if not send(line):
            board(tree, f"W-{name}-end-{(sid or 'x')[:8]}", line.removeprefix("we-worker: "))
    try:
        again = bool(_living(sessions(), name))
    except wl.LaunchError:
        again = True
    if not again and reason not in RESUMABLE:
        _remove_files(state, name)
    return reason or ("stopped" if stopped else "ended")


def spawn(name: str, tree: str) -> int:
    """Start `run` detached (own session, no tty); it inherits this environment, the starter's
    inbox socket and token with it. Returns the child's pid."""
    state = state_dir()
    state.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, os.path.abspath(__file__), "run", "--name", name, "--tree", tree]
    with open(state / "supervisor.log", "a", encoding="utf-8") as log:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
            env={k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"},
        )
    return proc.pid


# --- status --------------------------------------------------------------------------------


def _window_worker(row: dict) -> bool:
    """A non-background row started as a worker: `WE_ROLE=worker` in its environment, or the
    launcher's marker in its tree naming it."""
    try:
        with open(f"/proc/{int(row.get('pid'))}/environ", "rb") as fh:
            if b"WE_ROLE=worker" in fh.read().split(b"\0"):
                return True
    except (OSError, TypeError, ValueError):
        pass
    marker = wl.read_marker(row.get("cwd")) if row.get("name") else None
    return bool(marker) and marker.get("name") == row.get("name")


def time_limit(state: Path, name: str, now: float) -> str | None:
    deadline = timer_deadline(state, name)
    if deadline is None:
        return None
    if deadline <= now:
        return "time-limit=reached"
    return "time-limit=" + dt.datetime.fromtimestamp(deadline, dt.timezone.utc).strftime("%H:%M")


def lives(row: dict) -> bool:
    """Whether a `claude agents --json` row's process runs: the one test `we-worker status` marks
    `exited(...)` by, also the crew view's "live" (`crew_view.py`)."""
    pid = str(row.get("pid", "-"))
    return pid.isdigit() and int(pid) > 0 and wl._pid_lives(pid)


STATUS_SCHEMA_VERSION = 1


def status_records(
    rows: list[dict], key: str | None, projects: Path, state: Path, now: float
) -> list[dict]:
    """The loop of `we-worker status` as objects: one per worker (background, or a window worker)
    `{name, id, pid, state, alive, last, end, time_limit, window, resume, waits, lane}`; `state` is the
    row's state, `exited(<state>)` when the process is gone; `end` the `api_mark`; `resume` the
    resume command of an exited worker with a resumable end, else null; `waits` is `test-slot`
    while a process of the worker is blocked on the host's test slot (it counts as busy and does
    no work), else null."""
    out = []
    slot_waits = _slot_waiting(rows)
    for row in rows:
        row["id"] = row.get("id") or row.get("sessionId")
        if key and key not in (row.get("name"), row.get("id")):
            continue
        window = row.get("kind") != "background"
        if window and not _window_worker(row):
            continue
        entry = last_assistant(projects, row.get("sessionId"))
        hm = str((entry or {}).get("timestamp") or "")[11:16] or "-"
        mark = api_mark(entry)
        st = (
            (row.get("status") or row.get("state"))
            if window
            else (row.get("state") or row.get("status"))
        )
        pid = str(row.get("pid", "-"))
        gone = not lives(row)  # no pid: exited
        if gone:
            st = f"exited({st})"
        resume = None
        if gone and mark in RESUMABLE and row.get("sessionId"):
            resume = resume_command(str(row.get("name")), str(row["sessionId"]), row.get("cwd"))
        out.append(
            {
                "name": str(row.get("name")),
                "id": str(row.get("id")),
                "pid": pid,
                "state": str(st),
                "alive": not gone,
                "last": hm,
                "end": mark,
                "time_limit": time_limit(state, row.get("name") or "", now),
                "window": window,
                "resume": resume,
                "waits": "test-slot" if not gone and pid in slot_waits else None,
                "lane": wl.lane_of(state, row.get("name"), row.get("cwd")),
            }
        )
    return out


def _slot_waiting(rows: list[dict]) -> set[str]:
    """The pids (as text) of the rows with a process below them blocked on the host's test slot
    (`slot_lock.waiting_roots`, from `/proc/locks`)."""
    import slot_lock  # noqa: PLC0415

    roots = {int(str(r.get("pid"))) for r in rows if str(r.get("pid", "")).isdigit()}
    return {str(pid) for pid in slot_lock.waiting_roots(roots)} if roots else set()


def status_lines(
    rows: list[dict], key: str | None, projects: Path, state: Path, now: float
) -> list[str]:
    """`we-worker status`: one line per worker of `status_records`, its end mark, the timer's
    `time_limit` and `waits: test-slot`; an exited worker with a resumable mark gets its resume command; then one line
    per queued start (`queued`)."""
    out = []
    for r in status_records(rows, key, projects, state, now):
        waits = f"waits: {r['waits']}" if r["waits"] else None
        lane = "lane=utility" if r["lane"] == wl.UTILITY else None
        extra = [
            x
            for x in ("window" if r["window"] else None, lane, r["end"], r["time_limit"], waits)
            if x
        ]
        head = [r["id"], r["name"], f"pid={r['pid']}", r["state"], f"last={r['last']}"]
        out.append(" ".join([*head, *extra]))
        if r["resume"]:
            when = "the reset" if r["end"] == "usage-limit" else "the login is back"
            out.append(f"  resume after {when}: {r['resume']}")
    positions = dict.fromkeys(wl.LANES, 0)  # each lane is its own queue
    dead = False
    for q in queued(state):
        lane = wl.entry_lane(q)
        positions[lane] += 1
        if key and key != q.get("name"):
            continue
        since = dt.datetime.fromtimestamp(q.get("queued_at", now), dt.timezone.utc)
        until = dt.datetime.fromtimestamp(q.get("deadline", now), dt.timezone.utc)
        waiter = "" if waiter_lives(q) else " dead waiter"
        dead = dead or bool(waiter)
        out.append(
            f"queued {q.get('name')} position={positions[lane]} since={since:%H:%M}"
            f" until={until:%H:%M} tree={q.get('tree')} starter={q.get('starter') or '-'}"
            f" lane={lane}{waiter}"
        )
    if dead:
        out.append(
            "  a dead waiter starts nothing: `we-worker status --restart-waiters` restarts it"
        )
    return out


def restart_waiters(state: Path, spawn: Callable[[str], int] | None = None) -> list[str]:
    """Start a new waiter for every queued start whose waiter is dead (a crash, a pod restart);
    the entry keeps its place (`queue_order`) and deadline. Returns the names."""
    spawn = spawn_waiter if spawn is None else spawn
    names = [str(q["name"]) for q in queued(state) if not waiter_lives(q)]
    for name in names:
        spawn(name)
    return names


ROOM_PREFIX = "room for both lanes: "


def resource_line(
    state: Path,
    cgroup: Path | None = None,
    meminfo: Path | None = None,
) -> str:
    """`we-worker status`'s last line: the machine's room for a start of either lane
    (`worker_launch.resources`), `n/a` for a value it cannot read."""
    try:
        limits = wl.pool_limits(state)
    except wl.LaunchError as exc:
        return f"{ROOM_PREFIX}unknown ({exc})"
    rows = wl.resources(limits, cgroup, meminfo)
    verdict = "ok" if all(r["ok"] for r in rows) else "starts wait"
    return f"{ROOM_PREFIX}{verdict}: {wl.resource_text(rows)}"


# --- queue -----------------------------------------------------------------------------------
#
# `we-worker <name> --bg --queue` registers a start the capacity check refused (`enqueue`) and
# spawns one detached waiter per entry (`wait_queue`). The queue is the machine's, one directory for
# every repo. Only the oldest entry whose waiter lives tries to start (or one behind entries that
# only their own repo's lower limit may hold back, `_may_try`), by running the same
# `we-worker` call again without `--queue` and with `$WE_WORKER_QUEUE_TURN` = its name, once the
# machine has room (`worker_launch.resources`, the rule the start checks too): its exit 3 (the cap)
# or 4 (the room) is "still no room", any other exit ends the wait. A start the room rule halts is
# queued without `--queue`. First come, first served across waiters and
# repos: a start that is not queued is refused while any living entry waits
# (`worker_launch.queued_ahead`). Each lane (`build`, `utility`: the entry's `lane`) is its own
# queue: a utility start never waits behind a build start. After a start the next one waits `SETTLE_S`, so the new worker
# counts as busy before the next check. A queued start from a main checkout gets its own worktree
# (`worker_launch.auto_tree`).

QUEUE_POLL_S = 30
SETTLE_S = 60
CAPACITY_REFUSED = 3
STILL_WAITING = (CAPACITY_REFUSED, wl.RESOURCE_HALT)
QUEUE_TIMEOUT = "2h"
START_TIMEOUT_S = 300


def queue_dir(state: Path) -> Path:
    return state / "queue"


def proc_start(pid: int) -> int | None:
    """The start time of process `pid` in clock ticks since boot (`/proc/<pid>/stat` field 22),
    None where it cannot be read (no such process, no /proc)."""
    try:
        stat = Path(f"/proc/{int(pid)}/stat").read_text()
        return int(stat.rsplit(")", 1)[1].split()[19])
    except (OSError, ValueError, IndexError):
        return None


def _waiter_lives(pid: object, start: object = None) -> bool:
    """A queue entry's waiter: a missing or non-positive pid is no waiter (unlike `_pid_lives`,
    which keeps an unreadable session row alive). With the `start` recorded at `set_waiter`, a
    process of that pid with another start time is a reused pid, not the waiter; an entry without
    it (or a host without /proc) keeps the pid check alone."""
    try:
        num = int(str(pid))
    except ValueError:
        return False
    if num <= 0 or not wl._pid_lives(num):
        return False
    if isinstance(start, int) and not isinstance(start, bool):
        now = proc_start(num)
        return now is None or now == start
    return True


def waiter_lives(doc: dict) -> bool:
    """The waiter of queue entry `doc` lives (`_waiter_lives` with its recorded start time)."""
    return _waiter_lives(doc.get("waiter_pid"), doc.get("waiter_start"))


NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def safe_name(name: str) -> str:
    """A worker name as a file name in the state dir; a path (`/`, `..`) refuses (exit 2)."""
    if not NAME_RE.fullmatch(name) or ".." in name:
        raise wl.LaunchError(f"{name!r} is no worker name (letters, digits, . _ -)", 2)
    return name


def parse_duration(text: str) -> float:
    """Seconds of `2h`, `90m`, `2h30m` or a bare number of minutes; `ValueError` otherwise."""
    text = text.strip()
    if text.isdigit():
        return int(text) * 60.0
    found = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?", text)
    if not text or not found:
        raise ValueError(f"no duration: {text!r} (2h, 90m, 2h30m)")
    return int(found.group(1) or 0) * 3600.0 + int(found.group(2) or 0) * 60.0


def _read(path: Path) -> dict | None:
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) and doc.get("name") else None


def _write(path: Path, text: str) -> None:
    """Replace `path` whole (a temp file beside it, then `os.replace`): the waiter polls a queue
    entry, and a read between truncate and write finds no entry and exits as removed."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def queued(state: Path) -> list[dict]:
    """The queued starts, oldest first."""
    rows = [d for d in map(_read, sorted(queue_dir(state).glob("*.json"))) if d]
    return sorted(rows, key=lambda d: (wl.queue_order(d), d["name"]))


def enqueue(
    state: Path,
    name: str,
    tree: str,
    argv: list[str],
    brief: str | None,
    starter: str | None,
    timeout_s: float,
    now: float,
    repo_limits: dict | None = None,
    lane: str = wl.BUILD,
) -> dict:
    """Register a refused start; a name already queued with a living waiter refuses (exit 2).
    `repo_limits` are the pool limits its repo lowers (`worker_launch.repo_limits`): a start that
    only they hold back holds no other start up (`worker_launch.queued_limits`)."""
    qdir = queue_dir(state)
    qdir.mkdir(parents=True, exist_ok=True)
    held = _read(qdir / f"{name}.json")
    if held and waiter_lives(held):
        raise wl.LaunchError(
            f"{name} is already queued (since {held.get('queued_at', 0):.0f}); "
            f"`we-worker stop {name}` removes it",
            2,
        )
    brief_file = None
    if brief is not None:
        brief_file = qdir / f"{name}.brief.md"
        brief_file.write_text(brief)
    doc = {
        "name": name,
        "tree": tree,
        "argv": argv,
        "brief_file": str(brief_file) if brief_file else None,
        "starter": starter or None,
        "queued_at": now,
        "deadline": now + timeout_s,
        "repo_limits": repo_limits or {},
        "lane": lane,
    }
    (qdir / f"{name}.json").write_text(json.dumps(doc, indent=2) + "\n")
    return doc


def set_waiter(state: Path, name: str, pid: int) -> None:
    path = queue_dir(state) / f"{name}.json"
    doc = _read(path)
    if doc:
        doc["waiter_pid"] = pid
        doc["waiter_start"] = proc_start(pid)
        _write(path, json.dumps(doc, indent=2) + "\n")


def _drop(state: Path, name: str) -> dict | None:
    qdir = queue_dir(state)
    doc = _read(qdir / f"{name}.json")
    for path in (qdir / f"{name}.json", qdir / f"{name}.brief.md"):
        with contextlib.suppress(OSError):
            path.unlink()
    return doc


def unqueue(state: Path, name: str) -> dict | None:
    """`we-worker stop <name>` of a queued start: removes the entry and ends its waiter."""
    doc = _drop(state, name)
    pid = (doc or {}).get("waiter_pid")
    if pid != os.getpid() and _waiter_lives(pid, (doc or {}).get("waiter_start")):
        with contextlib.suppress(OSError):
            os.kill(int(pid), 15)
    return doc


def _may_try(state: Path, me: str) -> bool:
    """`me` tries its start when it is the head of its lane's queue, or when every living entry
    of that lane ahead of it carries a repo limit below the machine's: the capacity check lets it
    past an entry that only such a limit holds back (`worker_launch.queued_limits`), and decides.
    An entry of the other lane never holds it."""
    try:
        machine = wl.pool_limits(state)
    except wl.LaunchError:
        machine = None
    rows = queued(state)
    mine = next((d for d in rows if d["name"] == me), None)
    lane = wl.entry_lane(mine or {})
    cap = wl.lane_key(lane)
    full = None if machine is None else (machine[cap], machine[wl.PCT_KEY])
    for doc in rows:
        if doc["name"] == me:
            return True
        if not waiter_lives(doc) or wl.entry_lane(doc) != lane:
            continue
        if full is None or wl.queued_limits(doc, machine) == full:
            return False
    return False


def start_queued(doc: dict) -> tuple[int, str]:
    """Run the queued `we-worker` call again, without `--queue`, in its tree."""
    argv = list(doc.get("argv") or [])
    if doc.get("brief_file"):
        argv.append(Path(doc["brief_file"]).read_text())
    env = dict(os.environ)
    env[wl.QUEUE_TURN_ENV] = str(doc["name"])  # its own entry is no start ahead of it
    if doc.get("starter"):
        env["WE_WORKER_STARTER"] = str(doc["starter"])
    script = Path(__file__).resolve().with_name("we-worker")
    try:
        out = subprocess.run(
            ["bash", str(script), *argv],
            cwd=doc.get("tree") or None,
            capture_output=True,
            text=True,
            check=False,
            timeout=START_TIMEOUT_S,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return out.returncode, (out.stdout + out.stderr).strip()


def _tell(doc: dict, text: str, send, board, tag: str) -> None:
    if not send(text) and doc.get("tree"):
        board(doc["tree"], f"W-{doc['name']}-queue-{tag}", text.removeprefix("we-worker: "))


def machine_room(state: Path) -> bool:
    """Every condition of the resource rule holds (`worker_launch.resources`); an unreadable
    `pool.json` leaves the decision to the start's own check."""
    try:
        limits = wl.pool_limits(state)
    except wl.LaunchError:
        return True
    return all(r["ok"] for r in wl.resources(limits))


def wait_queue(
    state: Path,
    name: str,
    *,
    start: Callable[[dict], tuple[int, str]] = start_queued,
    room: Callable[[Path], bool] = machine_room,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
    send: Callable[[str], bool] = to_starter,
    board: Callable[..., bool] = board_news,
) -> str:
    """Wait for the queued start `name`'s turn and room; returns `started`, `timeout`, `failed`
    or `removed` (stopped while it waited). The starter gets one line on start, timeout or
    failure."""
    last = queue_dir(state) / ".last-start"
    while True:
        doc = _read(queue_dir(state) / f"{name}.json")
        if doc is None:
            return "removed"
        now = clock()
        waited = int((now - doc.get("queued_at", now)) // 60)
        if now >= doc.get("deadline", now):
            _drop(state, name)
            _tell(
                doc,
                f"we-worker: the queued start of {name} timed out after {waited} min without"
                f" room; nothing started. Start it again: we-worker {name} --bg --queue …",
                send,
                board,
                "timeout",
            )
            return "timeout"
        try:
            settled = now - last.stat().st_mtime >= SETTLE_S
        except OSError:
            settled = True
        if settled and _may_try(state, name) and room(state):
            code, out = start(doc)
            if code not in STILL_WAITING:
                _drop(state, name)
                tail = out.splitlines()[-1] if out else ""
                if code == 0:
                    with contextlib.suppress(OSError):
                        last.touch()
                        os.utime(last, (now, now))
                    text = f"we-worker: the queued start of {name} started after {waited} min"
                else:
                    text = f"we-worker: the queued start of {name} failed (exit {code})"
                _tell(doc, f"{text}: {tail}" if tail else text, send, board, str(code))
                return "started" if code == 0 else "failed"
        sleep(QUEUE_POLL_S)


def spawn_waiter(name: str) -> int:
    """Start `wait-queue` detached (as `spawn`); it inherits the starter's inbox socket.
    `$WE_WORKER_NO_SUPERVISOR=1` skips it as it skips the supervisor (the entry stays)."""
    state = state_dir()
    if os.environ.get("WE_WORKER_NO_SUPERVISOR") == "1":
        return 0
    argv = [sys.executable, os.path.abspath(__file__), "wait-queue", "--name", name]
    with open(state / "supervisor.log", "a", encoding="utf-8") as log:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
        )
    set_waiter(state, name, proc.pid)
    return proc.pid


# --- gc --------------------------------------------------------------------------------------


def _resumable_names(rows: list[dict], living: set[str], projects: Path) -> set[str]:
    """Dead names whose newest session ended on a usage limit or an auth error."""
    newest = {}
    for r in sorted(rows, key=lambda r: r.get("startedAt") or 0):
        if r.get("name"):
            newest[str(r["name"])] = r.get("sessionId")
    return {n for n, sid in newest.items() if n not in living and _resumable(projects, sid)}


def _resumable(projects: Path, session_id: str | None) -> bool:
    return api_mark(last_assistant(projects, session_id)) in RESUMABLE


def _old(path: Path, now: float, floor: float = GRACE_S) -> bool:
    try:
        return now - path.stat().st_mtime >= floor
    except OSError:
        return False


def _remove(path: Path, apply: bool) -> None:
    if not apply:
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        with contextlib.suppress(OSError):
            path.unlink()


def _worktrees(repo: Path) -> list[dict]:
    out = wl._git(repo, "worktree", "list", "--porcelain") or ""
    trees, cur = [], {}
    for line in [*out.splitlines(), ""]:
        if not line:
            if cur:
                trees.append(cur)
            cur = {}
        elif line.startswith("worktree "):
            cur["path"] = line[len("worktree ") :]
        elif line.startswith("branch refs/heads/"):
            cur["branch"] = line[len("branch refs/heads/") :]
    return trees[1:]  # the first is the main checkout


def merged(repo: Path, branch: str, base: str) -> bool:
    """The branch's head, with commits of its own (it moved since its reflog's first entry), is in
    `origin/<base>`, or GitHub lists a merged PR from it. A branch with no commit of its own sits in
    `origin/<base>` too and is never merged by that alone."""
    head = wl._git(repo, "rev-parse", f"refs/heads/{branch}")
    born = (wl._git(repo, "reflog", "show", "--format=%H", f"refs/heads/{branch}") or "").split()
    own = bool(head and born and born[-1] != head)
    if own and wl._git(repo, "merge-base", "--is-ancestor", head, f"origin/{base}") is not None:
        return True
    if not shutil.which("gh"):
        return False
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        out = subprocess.run(
            ["gh", "pr", "list", "--head", branch, "--state", "merged", "--json", "number"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=BOARD_TIMEOUT_S,
        )
        return out.returncode == 0 and out.stdout.strip() not in ("", "[]")
    return False


def _gc_queue(state: Path, now: float, apply: bool, verb: str) -> list[str]:
    """Queued starts whose waiter died and whose deadline passed: entry and brief go."""
    lines = []
    for doc in queued(state):
        if waiter_lives(doc) or doc.get("deadline", 0) > now:
            continue
        if apply:
            _drop(state, doc["name"])
        lines.append(f"{verb} the queued start of {doc['name']} (its waiter is gone)")
    return lines


def gc(
    repo: Path,
    apply: bool = False,
    *,
    sessions: Callable[[], list[dict]] = wl.sessions,
    state: Path | None = None,
    jobs: Path | None = None,
    projects: Path | None = None,
    now: float | None = None,
) -> list[str]:
    state = state or state_dir()
    projects = projects or projects_dir()
    jobs = jobs or jobs_dir()
    now = time.time() if now is None else now
    rows = sessions()  # a LaunchError refuses: nothing is judged dead on a guess
    living = {
        str(r.get("name")) for r in rows if r.get("name") and wl._pid_lives(r.get("pid", "-"))
    }
    listed = {str(r.get(f)) for r in rows for f in ("id", "sessionId") if r.get(f)}
    verb = "removed" if apply else "would remove"
    lines = []
    resumable = _resumable_names(rows, living, projects)
    for path in sorted(state.glob("*.json")):
        kept = path.name.endswith(RESUME_SUFFIX)
        name = next(
            (
                path.name[: -len(x)]
                for x in (".settings.json", RESUME_SUFFIX)
                if path.name.endswith(x)
            ),
            path.stem,
        )
        floor = RESUMABLE_AGE_S if kept or name in resumable else GRACE_S
        if name in living or not _old(path, now, floor):
            continue
        _remove(path, apply)
        lines.append(f"{verb} {path}")
    lines += _gc_queue(state, now, apply, verb)
    unlisted = 0
    for job in (p for p in jobs.glob("*") if p.is_dir()):
        try:
            sid = json.loads((job / "state.json").read_text()).get("sessionId")
        except (OSError, ValueError, AttributeError):
            sid = None
        unlisted += not ({job.name, str(sid or "")} & listed)
    top = wl.main_checkout(repo) or Path(wl._git(repo, "rev-parse", "--show-toplevel") or repo)
    base = wl.default_branch(top)
    for tree in _worktrees(top):
        path, branch = tree.get("path"), tree.get("branch")
        marker = wl.read_marker(path)
        if not (path and marker) or marker.get("name") in living:
            continue
        gd = wl.git_dir(path)
        if gd is None or not _old(gd / wl.MARKER, now):
            continue
        clean = wl._git(Path(path), "status", "--porcelain") == ""
        if clean and branch and merged(top, branch, base):
            lines.append(
                f"worktree {path} ({branch} merged, {marker.get('name')} not living): remove with "
                + wl.remove_command(top, path)
            )
            continue
        if apply:
            wl.clear_marker(Path(path))
        lines.append(f"{verb} the marker of {marker.get('name')} in {path}")
        if not clean:
            lines.append(f"keep {path}: uncommitted changes")
    if unlisted:
        lines.append(
            f"{unlisted} job directories under {jobs} belong to no listed session; gc leaves "
            "them to Claude Code"
        )
    return lines


def _status_verb(args: argparse.Namespace, state: Path) -> int:
    try:  # `claude agents --json` on stdin
        rows = [r for r in json.load(sys.stdin) if isinstance(r, dict)]
    except ValueError:
        print("we-worker status: claude agents --json printed no JSON", file=sys.stderr)
        return 1
    if args.restart_waiters:
        for name in restart_waiters(state):
            print(f"we-worker: the waiter of the queued start {name} restarted")
    if args.json:
        records = status_records(rows, args.key, projects_dir(), state, time.time())
        print(json.dumps({"schema_version": STATUS_SCHEMA_VERSION, "workers": records}))
        return 0
    lines = status_lines(rows, args.key, projects_dir(), state, time.time())
    print("\n".join([*lines, resource_line(state)] if not args.key else lines))
    return 0


def _queue_verb(args: argparse.Namespace, state: Path) -> int:
    argv = sys.stdin.read().split("\0")[:-1]  # the we-worker call, NUL-separated
    brief = argv.pop() if args.has_brief and argv else None
    try:
        timeout_s = parse_duration(args.timeout)
        own = wl.repo_limits(Path(args.tree))
        doc = enqueue(
            state,
            args.name,
            args.tree,
            argv,
            brief,
            args.starter,
            timeout_s,
            time.time(),
            own,
            args.lane,
        )
    except ValueError as exc:
        print(f"we-worker: --queue-timeout: {exc}", file=sys.stderr)
        return 2
    except wl.LaunchError as exc:
        print(f"we-worker: {exc}", file=sys.stderr)
        return exc.code
    spawn_waiter(args.name)
    pos = [d["name"] for d in queued(state) if wl.entry_lane(d) == args.lane].index(args.name) + 1
    until = dt.datetime.fromtimestamp(doc["deadline"], dt.timezone.utc)
    print(
        f"we-worker: {args.name} queued (position {pos} of the {args.lane} lane, until"
        f" {until:%H:%M} UTC); it starts"
        " when the check passes and tells its starter; `we-worker status` lists it,"
        f" `we-worker stop {args.name}` removes it"
    )
    return 0


def amend(state: Path, name: str, brief: str) -> dict | None:
    """Replace the brief of the queued start `name` (the waiter reads it only at the start, so the
    start runs with the newest one); None when no such entry waits."""
    path = queue_dir(state) / f"{name}.json"
    doc = _read(path)
    if doc is None:
        return None
    brief_file = queue_dir(state) / f"{name}.brief.md"
    _write(brief_file, brief)
    if doc.get("brief_file") != str(brief_file):
        doc["brief_file"] = str(brief_file)
        _write(path, json.dumps(doc, indent=2) + "\n")
    return doc


def reorder(state: Path, name: str, after: str | None) -> int:
    """Move the queued start `name` to the head of its lane (`after` None) or right behind the
    queued start `after` of the same lane, by its `order_at`; `queued_at` (the waited minutes),
    deadline and waiter stay. Returns its
    new position in the lane; raises `LaunchError` (exit 1) for an entry that is not queued or of
    another lane."""
    doc = _read(queue_dir(state) / f"{name}.json")
    if doc is None:
        raise wl.LaunchError(f"{name} is not queued", 1)
    lane = wl.entry_lane(doc)
    rows = [d for d in queued(state) if wl.entry_lane(d) == lane and d["name"] != name]
    if after is None:
        at = (wl.queue_order(rows[0]) - 1.0) if rows else wl.queue_order(doc)
    else:
        k = next((i for i, d in enumerate(rows) if d["name"] == after), None)
        if k is None:
            raise wl.LaunchError(f"{after} is not queued in the {lane} lane", 1)
        here = wl.queue_order(rows[k])
        nxt = wl.queue_order(rows[k + 1]) if k + 1 < len(rows) else here + 2.0
        at = (here + nxt) / 2
    doc["order_at"] = at
    _write(queue_dir(state) / f"{name}.json", json.dumps(doc, indent=2) + "\n")
    return [d["name"] for d in queued(state) if wl.entry_lane(d) == lane].index(name) + 1


def start_now(state: Path, name: str, reason: str, start=None) -> tuple[int, str]:
    """Start the queued `name` at once, past the lane cap and the room rule, on the owner's word
    (`reason`): one `override` line in the brakes log, the entry and its waiter go on success."""
    doc = _read(queue_dir(state) / f"{name}.json")
    if doc is None:
        return 1, f"{name} is not queued"
    os.environ[wl.OVER_LIMIT_ENV] = reason
    try:
        code, out = (start or start_queued)(doc)
    finally:
        os.environ.pop(wl.OVER_LIMIT_ENV, None)
    import worker_rights  # noqa: PLC0415

    worker_rights.brake_log(
        doc.get("tree"),
        {
            "type": "override",
            "gate": "worker capacity",
            "name": name,
            "reason": reason[:200],
            "outcome": "started" if code == 0 else f"exit {code}",
        },
    )
    if code == 0:
        unqueue(state, name)
    return code, out


def _amend_verb(args: argparse.Namespace, state: Path) -> int:
    try:
        brief = Path(args.brief_file).read_text()
    except OSError as exc:
        print(f"we-worker: amend: {exc}", file=sys.stderr)
        return 2
    if not brief.strip():
        print("we-worker: amend: the brief file is empty; the queued brief stays", file=sys.stderr)
        return 2
    if amend(state, args.name, brief) is None:
        print(
            f"we-worker: {args.name} is not queued; steer a running worker with SendMessage",
            file=sys.stderr,
        )
        return 1
    print(f"we-worker: the queued start of {args.name} now carries the brief of {args.brief_file}")
    return 0


def _prio_verb(args: argparse.Namespace, state: Path) -> int:
    try:
        pos = reorder(state, args.name, args.after)
    except wl.LaunchError as exc:
        print(f"we-worker: prio: {exc}", file=sys.stderr)
        return exc.code
    print(f"we-worker: {args.name} is now position {pos} of its lane")
    return 0


def _start_now_verb(args: argparse.Namespace, state: Path) -> int:
    code, out = start_now(state, args.name, args.reason)
    print(out)
    return code


def _unqueue_verb(args: argparse.Namespace, state: Path) -> int:
    if unqueue(state, args.name) is None:
        return 1
    print(f"we-worker: the queued start of {args.name} removed; nothing started")
    return 0


def _wait_verb(args: argparse.Namespace, state: Path) -> int:
    done = wait_queue(state, args.name)
    print(f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ} {args.name}: queue {done}")
    return 0


UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
PREFIX_RE = re.compile(r"[0-9a-f][0-9a-f-]{3,35}")


def resolve_session(
    rows: list[dict], key: str, state: Path, projects: Path
) -> tuple[str | None, list[str]]:
    """The full session id `we-worker --resume <key>` resumes: a full UUID as is; else the
    sessions of `claude agents` whose id or name is `key`, else the kept session of the stopped
    worker named `key` (`kept_session`), else, for a key of at least four hex digits, every
    session id starting with it among `claude agents`, the kept resume files and the transcripts.
    Returns `(id, [])` for one, `(None, candidates)` for several, `(None, [])` for none."""
    if UUID_RE.fullmatch(key):
        return key, []
    named = sorted(
        {
            str(r["sessionId"])
            for r in rows
            if key in (r.get("id"), r.get("name")) and r.get("sessionId")
        }
    )
    if len(named) == 1:
        return named[0], []
    if named:
        return None, named
    kept = kept_session(state, key)
    if kept:
        return kept, []
    if not PREFIX_RE.fullmatch(key):
        return None, []
    ids = {str(r.get("sessionId") or "") for r in rows}
    for path in state.glob(f"*{RESUME_SUFFIX}"):
        ids.add(kept_session(state, path.name[: -len(RESUME_SUFFIX)]) or "")
    ids |= {Path(f).stem for f in glob.glob(str(projects / "*" / f"{glob.escape(key)}*.jsonl"))}
    found = sorted(i for i in ids if UUID_RE.fullmatch(i) and i.startswith(key))
    return (found[0], []) if len(found) == 1 else (None, found)


def _resolve_verb(args: argparse.Namespace, state: Path) -> int:
    try:  # `claude agents --json` on stdin; unreadable counts as no rows
        rows = [r for r in json.load(sys.stdin) if isinstance(r, dict)]
    except ValueError:
        rows = []
    sid, several = resolve_session(rows, args.key, state, projects_dir())
    if sid:
        print(sid)
        return 0
    if several:
        shown = " ".join(several[:5]) + (" …" if len(several) > 5 else "")
        print(
            f"we-worker: --resume '{args.key}' is ambiguous ({len(several)} sessions: {shown});"
            " give a longer prefix or the full UUID",
            file=sys.stderr,
        )
        return 4
    print(
        f"we-worker: --resume '{args.key}': no session with that id or name in claude agents, no"
        f" stopped worker of that name ({args.key}{RESUME_SUFFIX} in the state dir) and no"
        " session id starting with it; give the full UUID",
        file=sys.stderr,
    )
    return 1


def _stopped_verb(args: argparse.Namespace, state: Path) -> int:
    keep_resume(state, args.name, args.session, args.tree)
    cmd = resume_command(args.name, args.session, args.tree)
    print(f"  session {args.session}; resume: {cmd}")
    return 0


VERBS = {
    "status": _status_verb,
    "queue": _queue_verb,
    "unqueue": _unqueue_verb,
    "wait-queue": _wait_verb,
    "amend": _amend_verb,
    "prio": _prio_verb,
    "start-now": _start_now_verb,
    "resolve": _resolve_verb,
    "stopped": _stopped_verb,
}


def _add_queue_edit_verbs(sub) -> None:
    """`amend`, `prio` and `start-now` of a queued start (`we-worker` passes them through)."""
    p = sub.add_parser("amend")
    p.add_argument("--name", required=True)
    p.add_argument("--brief-file", required=True)
    p = sub.add_parser("prio")
    p.add_argument("--name", required=True)
    where = p.add_mutually_exclusive_group(required=True)
    where.add_argument("--first", action="store_true")
    where.add_argument("--after")
    p = sub.add_parser("start-now")
    p.add_argument("--name", required=True)
    p.add_argument("--reason", required=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="worker_supervisor.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for verb in ("spawn", "run"):
        p = sub.add_parser(verb)
        p.add_argument("--name", required=True)
        p.add_argument("--tree", required=True)
    p = sub.add_parser("gc")
    p.add_argument("--repo", type=Path, default=Path.cwd())
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("status")
    p.add_argument("--key")
    p.add_argument("--json", action="store_true", help="the workers as objects (schema_version)")
    p.add_argument("--restart-waiters", action="store_true", help="a new waiter per dead one")
    p = sub.add_parser("queue")
    p.add_argument("--name", required=True)
    p.add_argument("--tree", required=True)
    p.add_argument("--starter")
    p.add_argument("--timeout", default=QUEUE_TIMEOUT)
    p.add_argument("--has-brief", action="store_true")
    p.add_argument("--lane", choices=wl.LANES, default=wl.BUILD)
    for verb in ("unqueue", "wait-queue"):
        sub.add_parser(verb).add_argument("--name", required=True)
    _add_queue_edit_verbs(sub)
    sub.add_parser("resolve").add_argument("--key", required=True)
    p = sub.add_parser("stopped")
    p.add_argument("--name", required=True)
    p.add_argument("--session", required=True)
    p.add_argument("--tree")
    args = ap.parse_args(argv)
    if args.cmd == "spawn":
        print(spawn(args.name, args.tree))
        return 0
    if args.cmd in VERBS:
        try:
            if getattr(args, "name", None) is not None:
                safe_name(args.name)
        except wl.LaunchError as exc:
            print(f"we-worker: {exc}", file=sys.stderr)
            return exc.code
        return VERBS[args.cmd](args, state_dir())
    if args.cmd == "run":

        def log(line: str) -> None:
            print(f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ} {line}", flush=True)

        log(f"{args.name}: {supervise(args.name, args.tree, log=log)}")
        return 0
    try:
        lines = gc(args.repo.resolve(), apply=args.apply)
    except wl.LaunchError as exc:
        print(f"we-worker gc: refused, {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines) if lines else "we-worker gc: nothing to remove")
    if not args.apply and any(x.startswith("would remove") for x in lines):
        print("(dry run: we-worker gc --apply removes them)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
