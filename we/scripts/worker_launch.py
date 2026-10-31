#!/usr/bin/env python3
"""The worker launch backend: a dev worker as an `Agent` subagent or as a session of its own.

`.weside/config.json` → `agents.worker_launch` is `"subagent"` (the default, also when the file or
key is missing) or a command template. A subagent bills the account of the session that calls it;
a template starts the worker as its own process, on whatever login the command starts it with.
Contract and Lead steps: `references/worker-dispatch.md` § Worker launch backend.

Template grammar: split like a shell line (`shlex`), then a token that is exactly `{name}`,
`{agent}` or `{brief}` becomes that value as one argv element. Any other `{…}` refuses, so is a
placeholder inside a token (`--x={name}`). `{name}` and `{brief}` are required. `{brief}` is the
one-line prompt `Read <git-dir>/we-brief.md and follow it.`: the brief never passes through a
shell. The command runs without a shell, cwd = the worker's worktree.

`launch` writes two files into the worktree's own git dir (untracked, removed with the worktree):
`we-brief.md` (the brief plus a `Lead:` line) and `we-worker.json` (the marker: name, lead, agent,
launched_at, and the worker's `session_id` from `claude agents --json`). The hooks treat a session
as a process worker only when the marker's `session_id` is its own (`worker_marker`), so the Lead
working in the same worktree is never one (`hooks/worker_report_gate.py`,
`hooks/automerge_gate.py`); `scripts/watch-worker.sh` reads the marker by name. `stop` removes both
files, also for a session that already ended.

Usage:
  worker_launch.py backend [--repo <dir>]          prints `subagent` or the template; 2 = invalid
  worker_launch.py launch --worktree <wt> --name <n> --brief-file <f> [--agent <we:dev-…>]
  worker_launch.py stop --name <n> [--worktree <wt>] exit 0 stopped · 1 failed · 3 still running;
                                                   with --worktree it removes marker and brief
  worker_launch.py alive --name <n>                exit 0 running · 1 not · 2 cannot tell
Exit 1 on a failed launch (files removed again), 2 on an invalid template.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

PLACEHOLDERS = ("name", "agent", "brief")
REQUIRED = ("name", "brief")
SUBAGENT = "subagent"
MARKER = "we-worker.json"
BRIEF = "we-brief.md"
STOP_WAIT_S = 30
SESSION_WAIT_S = 10


class LaunchError(Exception):
    """A refusal with the message the Lead reads; `code` is the exit code."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def _git(cwd: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def git_dir(cwd: Path | str) -> Path | None:
    out = _git(Path(cwd), "rev-parse", "--absolute-git-dir")
    return Path(out) if out else None


def read_marker(cwd: Path | str | None) -> dict | None:
    """The process-worker marker of the worktree holding `cwd`, or None (also on any read error)."""
    if not cwd:
        return None
    gd = git_dir(cwd)
    if gd is None:
        return None
    try:
        data = json.loads((gd / MARKER).read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and data.get("name") else None


def worker_marker(payload: dict) -> dict | None:
    """The marker when the hook payload's session is the process worker it names, else None."""
    marker = read_marker(payload.get("cwd"))
    session = payload.get("session_id")
    if marker and session and marker.get("session_id") == session:
        return marker
    return None


def clear_marker(worktree: Path | None) -> None:
    gd = git_dir(worktree) if worktree else None
    for path in (gd / MARKER, gd / BRIEF) if gd else ():
        with contextlib.suppress(OSError):
            path.unlink()


def validate(template: str) -> list[str]:
    try:
        tokens = shlex.split(template)
    except ValueError as exc:
        raise LaunchError(f"agents.worker_launch: cannot split the template ({exc})", 2) from exc
    if not tokens:
        raise LaunchError("agents.worker_launch: empty template", 2)
    for token in tokens:
        for found in re.findall(r"\{([^{}]*)\}", token):
            if found not in PLACEHOLDERS:
                raise LaunchError(f"agents.worker_launch: unknown placeholder {{{found}}}", 2)
            if token != f"{{{found}}}":
                raise LaunchError(
                    f"agents.worker_launch: placeholder {{{found}}} must be a token of its own, "
                    f"not part of {token!r}",
                    2,
                )
    for name in REQUIRED:
        if f"{{{name}}}" not in tokens:
            raise LaunchError(f"agents.worker_launch: placeholder {{{name}}} is required", 2)
    return tokens


def render(tokens: list[str], values: dict[str, str]) -> list[str]:
    argv = []
    for token in tokens:
        key = token[1:-1] if token.startswith("{") and token.endswith("}") else None
        if key in PLACEHOLDERS:
            argv.append(values[key])
        else:
            argv.append(token)
    return argv


def backend(repo: Path) -> str:
    """`subagent` or the validated template of the repo holding `repo`."""
    top = _git(repo, "rev-parse", "--show-toplevel")
    path = Path(top or repo) / ".weside" / "config.json"
    try:
        config = json.loads(path.read_text())
    except FileNotFoundError:
        return SUBAGENT
    except (OSError, json.JSONDecodeError) as exc:
        raise LaunchError(f"{path}: unreadable ({exc})") from exc
    agents = config.get("agents") if isinstance(config, dict) else None
    value = agents.get("worker_launch", SUBAGENT) if isinstance(agents, dict) else SUBAGENT
    if value == SUBAGENT:
        return SUBAGENT
    if not isinstance(value, str):
        raise LaunchError('agents.worker_launch: must be "subagent" or a command string', 2)
    validate(value)
    return value


def sessions() -> list[dict]:
    """`claude agents --json`: interactive and background sessions on this machine."""
    try:
        out = subprocess.run(
            ["claude", "agents", "--json"], capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise LaunchError(f"claude agents --json: {exc}") from exc
    if out.returncode != 0:
        raise LaunchError(f"claude agents --json exited {out.returncode}: {out.stderr.strip()}")
    try:
        rows = json.loads(out.stdout)
    except json.JSONDecodeError as exc:
        raise LaunchError("claude agents --json printed no JSON") from exc
    return [r for r in rows if isinstance(r, dict)]


def lead_address(rows: list[dict], session_id: str | None) -> str:
    for row in rows:
        if session_id and row.get("sessionId") == session_id and row.get("name"):
            return str(row["name"])
    raise LaunchError(
        "name this session first (`/rename <KEY>`): a process worker reports to the Lead by name"
    )


def _timing(event: str, **fields) -> None:
    session = re.sub(r"[^A-Za-z0-9_-]", "_", os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
    if not session:
        return
    with contextlib.suppress(OSError):  # measurement only, as hooks/subagent_timing.py
        out = Path.home() / ".claude" / "we-timing" / f"{session}.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.time(), "event": event, **fields}) + "\n")


def launch(worktree: Path, name: str, brief_file: Path, agent: str | None = None) -> Path:
    template = backend(worktree)
    if template == SUBAGENT:
        raise LaunchError(
            'agents.worker_launch is `subagent`: dispatch with Agent(isolation="worktree")', 2
        )
    tokens = validate(template)
    if "{agent}" in tokens and not agent:
        raise LaunchError("the template has {agent}: pass --agent <we:dev-…>", 2)
    gd = git_dir(worktree)
    if gd is None:
        raise LaunchError(f"{worktree} is no git worktree")
    lead = lead_address(sessions(), os.environ.get("CLAUDE_CODE_SESSION_ID"))
    try:
        brief = brief_file.read_text()
    except OSError as exc:
        raise LaunchError(f"brief: {exc}") from exc
    brief_path, marker_path = gd / BRIEF, gd / MARKER
    brief_path.write_text(
        f"{brief.rstrip()}\n\nLead: {lead} — send your report as one SendMessage to it; "
        "your plain text never reaches it.\n"
    )
    marker = {"name": name, "lead": lead, "agent": agent, "launched_at": time.time()}
    marker_path.write_text(json.dumps(marker, indent=2) + "\n")
    argv = render(
        tokens,
        {"name": name, "agent": agent or "", "brief": f"Read {brief_path} and follow it."},
    )
    try:
        out = subprocess.run(argv, cwd=worktree, capture_output=True, text=True, check=False)
        failed = out.returncode != 0
        detail = f"exited {out.returncode}: {out.stderr.strip()}"
    except OSError as exc:
        failed, detail = True, str(exc)
    if failed:
        clear_marker(worktree)
        raise LaunchError(f"{argv[0]} {detail}")
    marker["session_id"] = _session_of(name, worktree)
    marker_path.write_text(json.dumps(marker, indent=2) + "\n")
    if not marker["session_id"]:
        print(
            f"worker_launch: {name} not listed by claude agents --json within {SESSION_WAIT_S} s; "
            "its report and merge gates stay off",
            file=sys.stderr,
        )
    _timing("WorkerLaunch", name=name, agent_type=agent, cwd=str(worktree))
    if out.stdout.strip():
        print(out.stdout.strip())
    return marker_path


def _running(rows: list[dict], name: str, cwd: str | None = None) -> list[dict]:
    return [r for r in rows if r.get("name") == name and (cwd is None or r.get("cwd") == cwd)]


def _session_of(name: str, worktree: Path) -> str | None:
    deadline = time.monotonic() + SESSION_WAIT_S
    while True:
        try:
            rows = _running(sessions(), name, str(worktree))
        except LaunchError:
            rows = []
        if rows and rows[0].get("sessionId"):
            return str(rows[0]["sessionId"])
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.5)


def alive(name: str) -> bool:
    return bool(_running(sessions(), name))


def stop(name: str, worktree: Path | None = None, wait_s: float = STOP_WAIT_S) -> None:
    cwd = str(worktree) if worktree else None
    rows = _running(sessions(), name, cwd)
    if not rows:
        clear_marker(worktree)
        raise LaunchError(f"no running session named {name}")
    if len(rows) > 1:
        raise LaunchError(f"{len(rows)} sessions named {name}: pass --worktree")
    out = subprocess.run(
        ["claude", "stop", str(rows[0]["id"])], capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        raise LaunchError(f"claude stop exited {out.returncode}: {out.stderr.strip()}")
    deadline = time.monotonic() + wait_s
    while _running(sessions(), name, cwd):
        if time.monotonic() >= deadline:
            raise LaunchError(f"{name} still running {wait_s:.0f} s after claude stop", 3)
        time.sleep(1)
    clear_marker(worktree)
    _timing("WorkerStop", name=name, cwd=cwd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("backend")
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p = sub.add_parser("launch")
    p.add_argument("--worktree", type=Path, required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--brief-file", type=Path, required=True)
    p.add_argument("--agent")
    p = sub.add_parser("stop")
    p.add_argument("--name", required=True)
    p.add_argument("--worktree", type=Path)
    p = sub.add_parser("alive")
    p.add_argument("--name", required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "backend":
            print(backend(args.repo))
        elif args.cmd == "launch":
            marker = launch(args.worktree.resolve(), args.name, args.brief_file, args.agent)
            print(f"launched: {args.name} · marker {marker}")
        elif args.cmd == "stop":
            stop(args.name, args.worktree.resolve() if args.worktree else None)
            print(f"stopped: {args.name}")
        else:
            return 0 if alive(args.name) else 1
    except LaunchError as exc:
        print(f"worker_launch: {exc}", file=sys.stderr)
        return 2 if args.cmd == "alive" else exc.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
