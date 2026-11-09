#!/usr/bin/env python3
"""The worker launch backend: a dev worker as an `Agent` subagent or as a session of its own.

One owner of the template: in a repo with a crew, the crew's `launch.worker` (`scripts/crew.py`);
`.weside/config.json` → `agents.worker_launch` counts only where the crew sets none (a repo without
a crew, or a crew written before the move). Both set and different: one stderr line, the crew wins.
The value is `"subagent"` (the default, also when nothing is set) or a command template. A subagent
bills the account of the session that calls it; a template starts the worker as its own process,
on whatever login the command starts it with. `backend()` is the one reader; the master's boot
check and `/we:accept` read it through `worker_launch.py backend`.
Contract and Lead steps: `references/worker-dispatch.md` § Worker launch backend.

Template grammar: split like a shell line (`shlex`), then a token that is exactly `{name}`,
`{agent}` or `{brief}` becomes that value as one argv element. Any other `{…}` refuses, so is a
placeholder inside a token (`--x={name}`). `{name}` and `{brief}` are required. `{brief}` is the
one-line prompt `Read <git-dir>/we-brief.md and follow it.`: the brief never passes through a
shell. The command runs without a shell, cwd = the worker's worktree.

`launch` writes two files into the worktree's own git dir (untracked, removed with the worktree):
`we-brief.md` (the brief under a first `Lead:` line) and `we-worker.json` (the marker: name, lead, agent,
launched_at, and the worker's `session_id` from `claude agents --json`). The hooks treat a session
as a process worker only when the marker's `session_id` is its own (`worker_marker`), so the Lead
working in the same worktree is never one (`hooks/worker_report_gate.py`,
`hooks/automerge_gate.py`); `scripts/watch-worker.sh` reads the marker by name. `stop` removes both
files, also for a session that already ended.

Usage:
  worker_launch.py backend [--repo <dir>]          prints `subagent` or the template; 2 = invalid
  worker_launch.py launch --worktree <wt> --name <n> --brief-file <f> [--agent <we:dev-…>]
  worker_launch.py stop --name <n> [--worktree <wt>] exit 0 stopped · 1 failed · 3 still running;
                                                   with --worktree it removes marker and brief;
                                                   several sessions of that name all stop (ids
                                                   printed), a refusal names the pid; a
                                                   template whose launcher has a `stop` verb
                                                   (`we-worker`) stops through it
  worker_launch.py alive --name <n>                exit 0 running · 1 not · 2 cannot tell
  worker_launch.py checkpoint --name <n>           commit the worker's changes (via we-worker), push them to
                                                   wip/<branch without its type prefix>
Exit 1 on a failed launch (files removed again), 2 on an invalid template.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shlex
import shutil
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


GIT_TIMEOUT_S = 30


def _git(cwd: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
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


CONFIG_KEY = "agents.worker_launch"
CREW_KEY = "launch.worker"


def validate(template: str, source: str = CONFIG_KEY) -> list[str]:
    try:
        tokens = shlex.split(template)
    except ValueError as exc:
        raise LaunchError(f"{source}: cannot split the template ({exc})", 2) from exc
    if not tokens:
        raise LaunchError(f"{source}: empty template", 2)
    for token in tokens:
        for found in re.findall(r"\{([^{}]*)\}", token):
            if found not in PLACEHOLDERS:
                raise LaunchError(f"{source}: unknown placeholder {{{found}}}", 2)
            if token != f"{{{found}}}":
                raise LaunchError(
                    f"{source}: placeholder {{{found}}} must be a token of its own, "
                    f"not part of {token!r}",
                    2,
                )
    for name in REQUIRED:
        if f"{{{name}}}" not in tokens:
            raise LaunchError(f"{source}: placeholder {{{name}}} is required", 2)
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


def _config_template(top: Path) -> str | None:
    """`agents.worker_launch` of the repo's config.json, None when the file or key is missing."""
    path = top / ".weside" / "config.json"
    try:
        config = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise LaunchError(f"{path}: unreadable ({exc})") from exc
    agents = config.get("agents") if isinstance(config, dict) else None
    value = agents.get("worker_launch") if isinstance(agents, dict) else None
    if value is not None and not isinstance(value, str):
        raise LaunchError(f'{CONFIG_KEY}: must be "subagent" or a command string', 2)
    return value


def _crew_template(top: Path) -> str | None:
    """The crew's `launch.worker`, None without a crew or without the key."""
    import crew as crew_mod  # noqa: PLC0415  (lazy: crew.py imports this module)

    try:
        _path, crew = crew_mod.find_and_load(top)
    except crew_mod.CrewError as exc:
        print(f"worker_launch: crew unreadable ({exc}); {CONFIG_KEY} decides", file=sys.stderr)
        return None
    value = ((crew or {}).get("launch") or {}).get("worker")
    return value if isinstance(value, str) and value.strip() else None


def backend(repo: Path) -> str:
    """`subagent` or the validated template of the repo holding `repo` (crew first, see above)."""
    top = Path(_git(repo, "rev-parse", "--show-toplevel") or repo)
    from_crew = _crew_template(top)
    from_config = _config_template(top)
    if from_crew is not None:
        if from_config not in (None, SUBAGENT, from_crew):
            print(
                f"worker_launch: {CREW_KEY} and {CONFIG_KEY} differ; the crew wins "
                f"({from_crew!r}); drop {CONFIG_KEY} from .weside/config.json",
                file=sys.stderr,
            )
        validate(from_crew, CREW_KEY)
        return from_crew
    if from_config in (None, SUBAGENT):
        return SUBAGENT
    validate(from_config)
    return from_config


AGENTS_TIMEOUT_S = 30


def sessions() -> list[dict]:
    """`claude agents --json`: interactive and background sessions on this machine."""
    try:
        out = subprocess.run(
            ["claude", "agents", "--json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=AGENTS_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        raise LaunchError(f"claude agents --json timed out after {AGENTS_TIMEOUT_S} s") from None
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
    if agent and "{agent}" not in tokens:
        print(
            f"worker_launch: warning: --agent {agent} is dropped: the template has no {{agent}}, so "
            "the worker starts without its effort and model; add `--agent {agent}` to the template",
            file=sys.stderr,
        )
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
        f"Lead: {lead} — send your report as one SendMessage to it; "
        f"your plain text never reaches it.\n\n{brief.rstrip()}\n"
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


STOP_VERB_TIMEOUT_S = 60


def launcher_with_verbs(repo: Path | None) -> str | None:
    """The template's first word when it is a launcher with its own `stop` verb, else None.

    Only `we-worker` (this plugin's launcher, `scripts/we-worker`) is known to carry
    `status|stop|logs|waiting`; any other launcher, or a `we-worker` not on `PATH`, is stopped
    with `claude stop`.
    """
    try:
        template = backend(repo or Path.cwd())
    except LaunchError:
        return None
    if template == SUBAGENT:
        return None
    first = shlex.split(template)[0]
    if Path(first).name != "we-worker" or shutil.which(first) is None:
        return None  # not ours, or not on this host: `claude stop` does it
    return first


def _stop_one(row: dict, launcher: str | None) -> str:
    """Stop one session row; returns its id. A refusal names the id and the pid."""
    rid = str(row.get("id"))
    argv = [launcher or "claude", "stop", rid]
    try:
        out = subprocess.run(
            argv, capture_output=True, text=True, check=False, timeout=STOP_VERB_TIMEOUT_S
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LaunchError(f"{argv[0]} stop {rid}: {exc}") from exc
    if out.returncode != 0:
        raise LaunchError(
            f"{argv[0]} stop {rid} exited {out.returncode}: {out.stderr.strip()} "
            f"(pid {row.get('pid', '?')}: `kill {row.get('pid', '<pid>')}` ends it)"
        )
    return rid


def stop(name: str, worktree: Path | None = None, wait_s: float = STOP_WAIT_S) -> list[str]:
    """Stop every session named `name` (in `worktree` when given); returns their ids."""
    cwd = str(worktree) if worktree else None
    rows = _running(sessions(), name, cwd)
    if not rows:
        clear_marker(worktree)
        raise LaunchError(f"no running session named {name}")
    launcher = launcher_with_verbs(worktree)
    ids = [_stop_one(row, launcher) for row in rows]
    deadline = time.monotonic() + wait_s
    while left := _running(sessions(), name, cwd):
        if time.monotonic() >= deadline:
            pids = ", ".join(f"{r.get('id')} pid {r.get('pid', '?')}" for r in left)
            raise LaunchError(f"{name} still running {wait_s:.0f} s after stop ({pids})", 3)
        time.sleep(1)
    clear_marker(worktree)
    _timing("WorkerStop", name=name, cwd=cwd, ids=ids)
    return ids


def checkpoint(name: str) -> str:
    """`we-worker checkpoint <name>` (the one owner of the procedure, beside this file): commit
    the worker's changes and push them to wip/<branch sans type>; returns its line."""
    script = Path(__file__).resolve().with_name("we-worker")
    try:
        out = subprocess.run(
            ["bash", str(script), "checkpoint", name],
            capture_output=True,
            text=True,
            check=False,
            timeout=STOP_VERB_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LaunchError(f"we-worker checkpoint {name}: {exc}") from exc
    if out.returncode != 0:
        raise LaunchError(
            out.stderr.strip() or f"we-worker checkpoint {name} exited {out.returncode}"
        )
    return out.stdout.strip().removeprefix("we-worker: ")


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
    p = sub.add_parser("checkpoint")
    p.add_argument("--name", required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "backend":
            print(backend(args.repo))
        elif args.cmd == "launch":
            marker = launch(args.worktree.resolve(), args.name, args.brief_file, args.agent)
            print(f"launched: {args.name} · marker {marker}")
        elif args.cmd == "stop":
            ids = stop(args.name, args.worktree.resolve() if args.worktree else None)
            print(f"stopped: {args.name} ({', '.join(ids)})")
        elif args.cmd == "checkpoint":
            print(checkpoint(args.name))
        else:
            return 0 if alive(args.name) else 1
    except LaunchError as exc:
        print(f"worker_launch: {exc}", file=sys.stderr)
        return 2 if args.cmd == "alive" else exc.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
