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

Name and brief (one owner, read by `launch`, by `check` and through `check` by `we-worker`): a worker
name starts with a match of the crew's `naming.key` (default `[A-Z]+-\\d+`), alone or followed by
`-<chunk>` (`check_name`). A brief carries four fields as Markdown headings outside fenced code, each
with a non-blank body up to the next heading of its level or above (`check_brief`); a heading counts
when its text starts, case-insensitively, with one of the field's two names: `Ziel`/`Goal`,
`Ausgabe`/`Output`, `Werkzeuge und Quellen`/`Tools and sources`, `Grenzen und wann stoppen`/`Limits
and when to stop`. A brief that is exactly `Read <path> and follow it.` is that file's text. The name
check refuses; the brief check warns while `BRIEF_ENFORCED` is false (it prints the finding and
`TEMPLATE`, which passes its own check, and the worker starts) and refuses once a follow-up sets it.
Every checked start is one `brief` line in `brakes.jsonl` (`worker_rights.brake_log`): the switch
is due when the last 30 logged starts pass.

`launch` checks name (and, once enforced, brief) first, then writes two files into the worktree's own git dir (untracked,
removed with the worktree): `we-brief.md` (the brief under a first `Lead:` line) and `we-worker.json`
(the marker: name, key, lead, agent, launched_at, and the worker's `session_id` from `claude agents --json`). The hooks treat a session
as a process worker only when the marker's `session_id` is its own (`worker_marker`), so the Lead
working in the same worktree is never one (`hooks/worker_report_gate.py`,
`hooks/automerge_gate.py`); `scripts/watch-worker.sh` reads the marker by name. `stop` removes both
files, also for a session that already ended.

Usage:
  worker_launch.py backend [--repo <dir>]          prints `subagent` or the template; 2 = invalid
  worker_launch.py check --name <n> (--brief-file <f|-> | --no-brief) [--repo <dir>] [--prefix <p>]
                                                   prints the story key; 2 with the refusal lines
                                                   (and the template) on stderr
  worker_launch.py settings --repo <dir> --key <K> --out <file> [--session-start <command>]
                                                   writes the worker's `--settings` file: the
                                                   granted rights of that repo as permissions.allow,
                                                   the never-list as permissions.deny
                                                   (`worker_rights.py`), the command as its
                                                   SessionStart hook
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


FIELDS = (
    ("Ziel", "Goal", "what is done when you stop; the story key and the plan"),
    ("Ausgabe", "Output", "what you deliver and how you report it, to whom"),
    ("Werkzeuge und Quellen", "Tools and sources", "the tree, the files and commands to use"),
    (
        "Grenzen und wann stoppen",
        "Limits and when to stop",
        "what you never do; when you stop and report",
    ),
)
TEMPLATE = "\n".join(f"## {de} ({en})\n<{hint}>\n" for de, en, hint in FIELDS)
DEFAULT_KEY = "[A-Z]+-\\d+"
BRIEF_ENFORCED = False  # warn first (Vyra 11.11.); a brake-change follow-up sets it
_POINTER = re.compile(r"Read (?P<path>\S.*?) and follow it\.")
_HEADING = re.compile(r"^[ ]{0,3}(?P<level>#{1,6})[ \t]+(?P<text>.*?)[ \t#]*$")
_FENCE = re.compile(r"^[ ]{0,3}(```|~~~)")


def key_pattern(repo: Path | None) -> str:
    """The crew's `naming.key` of the repo holding `repo`, else the default."""
    import crew as crew_mod  # noqa: PLC0415  (lazy: crew.py imports this module)

    try:
        _path, crew = crew_mod.find_and_load(repo or Path.cwd())
    except crew_mod.CrewError:
        crew = None
    value = ((crew or {}).get("naming") or {}).get("key")
    return value if isinstance(value, str) and value else DEFAULT_KEY


def check_name(name: str, key_re: str = DEFAULT_KEY, example: str | None = None) -> str:
    """The story key the worker name starts with; a `LaunchError` (exit 2) without one."""
    try:
        found = re.match(rf"(?P<key>{key_re})(?:-(?P<chunk>.+))?$", name)
    except re.error as exc:
        raise LaunchError(f"naming.key {key_re!r} is no regex ({exc})", 2) from exc
    if found and found.group("key"):
        return found.group("key")
    raise LaunchError(
        f"worker name {name} carries no story key ({key_re}), e.g. {example or 'ABC-123'}-{name}",
        2,
    )


def _brief_text(text: str, base: Path | None = None) -> str:
    """The brief itself: a pointer line `Read <path> and follow it.` becomes that file's text."""
    found = _POINTER.fullmatch(text.strip())
    if not found:
        return text
    path = Path(found.group("path"))
    if not path.is_absolute() and base is not None:
        path = base / path
    try:
        return path.read_text()
    except OSError as exc:
        raise LaunchError(f"brief: {path}: {exc.strerror or exc}", 2) from exc


def check_brief(text: str, base: Path | None = None) -> list[str]:
    """The fields the brief lacks, as `Ziel / Goal`; empty when all four carry a body."""
    lines = _brief_text(text, base).splitlines()
    headings: list[tuple[int, int, str]] = []  # (line, level, text) outside fences
    fence = None
    for i, line in enumerate(lines):
        opened = _FENCE.match(line)
        if fence:
            if opened and opened.group(1) == fence:
                fence = None
            continue
        if opened:
            fence = opened.group(1)
            continue
        found = _HEADING.match(line)
        if found:
            headings.append((i, len(found.group("level")), found.group("text")))
    present = set()
    for n, (i, level, heading) in enumerate(headings):
        end = next((j for j, lv, _t in headings[n + 1 :] if lv <= level), len(lines))
        if not any(line.strip() for line in lines[i + 1 : end] if not _HEADING.match(line)):
            continue
        for de, en, _hint in FIELDS:
            if heading.casefold().startswith((de.casefold(), en.casefold())):
                present.add(de)
    return [f"{de} / {en}" for de, en, _hint in FIELDS if de not in present]


def brief_refusal(missing: list[str]) -> str:
    return (
        f"the brief lacks {', '.join(missing)}; a brief carries four Markdown headings, each with "
        f"a body:\n\n{TEMPLATE}"
    )


def _example_key(repo: Path | None, key_re: str) -> str | None:
    branch = _git(repo or Path.cwd(), "branch", "--show-current") or ""
    try:
        found = re.search(key_re, branch)
    except re.error:
        return None
    return found.group(0) if found else None


def check(name: str, brief: str, repo: Path | None = None, prefix: str = "worker_launch") -> str:
    """`check_name`, then `check_brief`: the key, or a `LaunchError` (exit 2) naming what is wrong;
    a brief finding is a stderr warning while `BRIEF_ENFORCED` is false. Logs one `brief` line."""
    import worker_rights  # noqa: PLC0415

    key_re = key_pattern(repo)
    key = check_name(name, key_re, _example_key(repo, key_re))
    missing = check_brief(brief, repo)
    worker_rights.brake_log(
        repo, {"type": "brief", "name": name, "key": key, "ok": not missing, "missing": missing}
    )
    if missing and BRIEF_ENFORCED:
        raise LaunchError(brief_refusal(missing), 2)
    if missing:
        print(f"{prefix}: warning: {brief_refusal(missing)}", file=sys.stderr)
    return key


def write_settings(repo: Path, key: str, out: Path, session_start: str | None = None) -> dict:
    """The worker's `--settings` file (`worker_rights.settings`), with the timer's hook."""
    import worker_rights  # noqa: PLC0415

    doc = worker_rights.settings(repo, key)
    if session_start:
        doc["hooks"] = {
            "SessionStart": [{"hooks": [{"type": "command", "command": session_start}]}]
        }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    return doc


def launch(worktree: Path, name: str, brief_file: Path, agent: str | None = None) -> Path:
    try:
        brief = brief_file.read_text()
    except OSError as exc:
        raise LaunchError(f"brief: {exc}") from exc
    key = check(name, brief, worktree)
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
    brief_path, marker_path = gd / BRIEF, gd / MARKER
    brief_path.write_text(
        f"Lead: {lead} — send your report as one SendMessage to it; "
        f"your plain text never reaches it.\n\n{brief.rstrip()}\n"
    )
    marker = {"name": name, "key": key, "lead": lead, "agent": agent, "launched_at": time.time()}
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
    `status|stop|logs|waiting|checkpoint`; any other launcher, or a `we-worker` not on `PATH`, is stopped
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


def _ident(row: dict) -> str | None:
    """The handle `we-worker` resolves a row by: its `id`, else (an interactive row of `claude
    agents --json` has none) its `sessionId`; None when the row has neither."""
    for field in ("id", "sessionId"):
        value = str(row.get(field) or "").strip()
        if value and value != "None":
            return value
    return None


def _stop_one(row: dict, launcher: str | None) -> str:
    """Stop one session row; returns its handle (`_ident`). A refusal names the handle and the
    pid. A row without `id` (a window worker) only `we-worker stop` ends: `claude stop` knows
    background jobs alone."""
    rid = _ident(row)
    pid = row.get("pid", "<pid>")
    if rid is None or (row.get("id") in (None, "") and launcher is None):
        raise LaunchError(
            f"{row.get('name')} has no background id (a window worker); `claude stop` cannot end "
            f"it: `kill {pid}` does"
        )
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


def is_worker(row: dict) -> bool:
    """`we-worker is-worker <id>` (the one owner of the rule, beside this file): a background
    session, a worktree with the launcher's marker, or a process started as a worker; never a
    master or companion session. Any failure counts as no worker."""
    script = Path(__file__).resolve().with_name("we-worker")
    ident = _ident(row)
    if ident is None:
        return False
    try:
        out = subprocess.run(
            ["bash", str(script), "is-worker", ident],
            capture_output=True,
            text=True,
            check=False,
            timeout=STOP_VERB_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0


def stop(name: str, worktree: Path | None = None, wait_s: float = STOP_WAIT_S) -> list[str]:
    """Stop every worker session named `name` (in `worktree` when given); returns their ids. A
    session of that name that is no worker (`is_worker`) is never stopped: a typo guard."""
    cwd = str(worktree) if worktree else None
    named = _running(sessions(), name, cwd)
    trees = sorted({str(r.get("cwd") or "-") for r in named})
    if cwd is None and len(trees) > 1:
        raise LaunchError(
            f"{len(named)} sessions are named {name}, in {', '.join(trees)}; stop one with "
            "--worktree <its tree>, never all at once"
        )
    rows = [r for r in named if is_worker(r)]
    if not rows and named:
        r = named[-1]
        raise LaunchError(
            f"{name} ({_ident(r) or 'no id'}, {r.get('kind')}) is no worker; a master or companion "
            "is never stopped by name. To stop it anyway: "
            + (f"claude stop {r['id']}" if r.get("id") else f"kill {r.get('pid', '<pid>')}")
        )
    if not rows:
        clear_marker(worktree)
        raise LaunchError(f"no running session named {name}")
    launcher = launcher_with_verbs(worktree)
    ids = [_stop_one(row, launcher) for row in rows]
    deadline = time.monotonic() + wait_s
    while left := [r for r in _running(sessions(), name, cwd) if is_worker(r)]:
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("backend")
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p = sub.add_parser("check")
    p.add_argument("--name", required=True)
    p.add_argument("--brief-file")
    p.add_argument(
        "--no-brief", action="store_true", help="check the name only (a resumed session)"
    )
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument("--prefix", default="worker_launch")
    p = sub.add_parser("settings")
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--session-start")
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
    return parser


def _check_verb(args: argparse.Namespace) -> int:
    """`check`: the key on stdout, or exit 2 with the refusal under `--prefix`."""
    try:
        if args.no_brief:
            key_re = key_pattern(args.repo)
            print(check_name(args.name, key_re, _example_key(args.repo, key_re)))
            return 0
        if not args.brief_file:
            raise LaunchError("check needs --brief-file <f|-> or --no-brief", 2)
        brief = sys.stdin.read() if args.brief_file == "-" else Path(args.brief_file).read_text()
        print(check(args.name, brief, args.repo, args.prefix))
    except OSError as exc:
        print(f"{args.prefix}: brief: {exc}", file=sys.stderr)
        return 2
    except LaunchError as exc:
        print(f"{args.prefix}: {exc}", file=sys.stderr)
        return exc.code
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.cmd == "check":
        return _check_verb(args)
    try:
        if args.cmd == "backend":
            print(backend(args.repo))
        elif args.cmd == "settings":
            write_settings(args.repo.resolve(), args.key, args.out, args.session_start)
            print(args.out)
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
