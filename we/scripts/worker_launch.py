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

The name (one owner, read by `launch`, by `check` and through `check` by `we-worker`): a worker
name starts with a match of the crew's `naming.key` (default `[A-Z]+-\\d+`), alone or followed by
`-<chunk>` (`check_name`); a name without one refuses. The brief's shape is not checked (its four
fields: `references/worker-dispatch.md`).

`launch` checks the name first, then writes two files into the worktree's own git dir (untracked,
removed with the worktree): `we-brief.md` (the brief under a first `Lead:` line) and `we-worker.json`
(the marker: name, key, lead, agent, launched_at, and the worker's `session_id` from `claude agents --json`). The hooks treat a session
as a process worker only when the marker's `session_id` is its own (`worker_marker`), so the Lead
working in the same worktree is never one (`hooks/worker_report_gate.py`,
`hooks/worker_rights_gate.py`); `scripts/watch-worker.sh` reads the marker by name. `stop` removes both
files, also for a session that already ended. Every start, `launch`'s and `we-worker`'s, appends one
line to `<state dir>/launched.jsonl` (§ the starter log, above `record_launch`).

Usage:
  worker_launch.py backend [--repo <dir>]          prints `subagent` or the template; 2 = invalid
  worker_launch.py pr-owner [--repo <dir>]         prints `master` or `worker` (`build.pr_owner`,
                                                   `pr_owner`); 2 = another value
  worker_launch.py check --name <n> [--repo <dir>] [--prefix <p>]
                                                   prints the story key; 2 with the refusal line
                                                   on stderr (`--brief-file`, `--no-brief`: accepted
                                                   and ignored, an older `we-worker` copy passes
                                                   them); a living session
                                                   of the same key is named on stderr as the
                                                   SendMessage target of a follow-up
  worker_launch.py pool-path                        prints the machine's pool file
                                                   (<state dir>/pool.json; $WE_WORKER_STATE_DIR
                                                   first), whether it exists or not
  worker_launch.py capacity [--repo <dir>] [--prefix <p>]
                                                   exit 0: a worker may start; 3: refused while
                                                   a queued start of any repo waits ahead of it
                                                   (first come, first served), the busy workers
                                                   (background or window) on the machine reach
                                                   the machine's limit (<state dir>/pool.json
                                                   max_busy_sessions, default 8) or no account in
                                                   rotation (`cswap list --json`) has 7d under 95 %
                                                   and 5h at or under pool.json
                                                   max_active_5h_percent (default 80; unreadable
                                                   list: the active account's 5h decides); a
                                                   repo's .weside/config.json `workers` may only
                                                   lower either limit; both values named;
                                                   an unreadable value skips its check (stderr;
                                                   silent without cswap on PATH); `we-worker
                                                   --queue` waits instead of refusing;
                                                   2: a limit that is no number
  worker_launch.py needs [--repo <dir>] [--prefix <p>] < brief
                                                   exit 2 when the brief's `Needs:` line, or the
                                                   frontmatter `needs:` of a /we:<skill> the
                                                   brief names, holds a plugin or MCP server
                                                   `workers.context` turns off (`check_needs`),
                                                   else 0
  worker_launch.py needs --all [--repo <dir>]      one line per plugin skill whose need
                                                   `workers.context` turns off, exit 2; else 0
  worker_launch.py settings --repo <dir> --key <K> --out <file> [--session-start <command>] [--name <n>]
                           [--brief-stdin < brief]
                                                   writes the worker's `--settings` file: the
                                                   granted rights of that repo as permissions.allow,
                                                   the never-list as permissions.deny
                                                   (`worker_rights.py`), the command as its
                                                   SessionStart hook, the lean context of
                                                   `workers.context` (`apply_context`); with the
                                                   brief, the ticketing plugin off when its
                                                   skills need no ticket (`ticketing_unneeded`);
                                                   --account-file adds the chosen account
                                                   (`apply_account`)
  worker_launch.py account --account auto|<name> [--need critical|uncritical] --out <file> [--repo <dir>]
                                                   asks `agents.accounts_command` (`choose_account`),
                                                   writes its checked answer to <file>, prints one
                                                   line naming it; 2 = refused (no option, failed
                                                   command, a critical worker on a non-Claude account)
  worker_launch.py account-need < brief            prints `uncritical` when one of the brief's
                                                   first ten lines is `Account: uncritical`,
                                                   else `critical`
  worker_launch.py tree --repo <dir> --name <n> [--branch <b>] [--auto [--queued] | --main-checkout]
                                                   creates the worker's own worktree beside the
                                                   main checkout (`add_tree`) and prints its path;
                                                   --auto only under `workers.tree: own` or
                                                   with --queued (`auto_tree`), exit 3 when it
                                                   creates none
                                                   (any other non-zero: the start stops);
                                                   --main-checkout only prints the main
                                                   checkout's top, exit 1 when <dir> is none
  worker_launch.py marker --tree <wt> --name <n> [--key K] [--role R] [--starter S] [--mode M]
                          [--starter-session <id>]
                                                   writes the launcher's marker (`write_marker`)
                                                   and its line in launched.jsonl
  worker_launch.py launched --name <n> [--key K] [--starter S] [--starter-session <id>]
                                                   only the line in launched.jsonl (a start
                                                   without a marker; `record_launch`)
  worker_launch.py starters [--json]               the newest launched.jsonl line per worker;
                                                   --json: {schema_version, generated_at, path,
                                                   unreadable, starters}
  worker_launch.py backfill-starters [--since 14d] [--apply]
                                                   the worker lanes of flow_intervals.py without a
                                                   starter: per worker the source it would use
                                                   (`timing`: a WorkerLaunch line of
                                                   ~/.claude/we-timing; `transcript`: the starter
                                                   line in the head of its transcript, only the
                                                   name kept) or `unrecoverable`; writes nothing
                                                   without --apply, which appends one line per
                                                   recovered worker with `backfill: <source>`
  worker_launch.py launch --worktree <wt> --name <n> --brief-file <f> [--agent <we:dev-…>]
  worker_launch.py stop --name <n> [--worktree <wt>] exit 0 stopped · 1 failed · 3 still running;
                                                   with --worktree it removes marker and brief;
                                                   several sessions of that name all stop (ids
                                                   printed), a refusal names the pid; a
                                                   template whose launcher has a `stop` verb
                                                   (`we-worker`) stops through it
  worker_launch.py alive --name <n>                exit 0 running · 1 not (no row, or its pid is gone) · 2 cannot tell
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
SETTINGS = "we-worker.settings.json"
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
    for path in (gd / MARKER, gd / BRIEF, gd / SETTINGS) if gd else ():
        with contextlib.suppress(OSError):
            path.unlink()


CONFIG_KEY = "agents.worker_launch"
CREW_KEY = "launch.worker"


def validate(
    template: str,
    source: str = CONFIG_KEY,
    placeholders: tuple[str, ...] = PLACEHOLDERS,
    required: tuple[str, ...] = REQUIRED,
) -> list[str]:
    try:
        tokens = shlex.split(template)
    except ValueError as exc:
        raise LaunchError(f"{source}: cannot split the template ({exc})", 2) from exc
    if not tokens:
        raise LaunchError(f"{source}: empty template", 2)
    for token in tokens:
        for found in re.findall(r"\{([^{}]*)\}", token):
            if found not in placeholders:
                raise LaunchError(f"{source}: unknown placeholder {{{found}}}", 2)
            if token != f"{{{found}}}":
                raise LaunchError(
                    f"{source}: placeholder {{{found}}} must be a token of its own, "
                    f"not part of {token!r}",
                    2,
                )
    for name in required:
        if f"{{{name}}}" not in tokens:
            raise LaunchError(f"{source}: placeholder {{{name}}} is required", 2)
    return tokens


def render(tokens: list[str], values: dict[str, str]) -> list[str]:
    argv = []
    for token in tokens:
        key = token[1:-1] if token.startswith("{") and token.endswith("}") else None
        if key in values:
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
# The worker pool: one limit for every repo on the machine. Busy sessions are counted machine-wide,
# so the limit is a property of the machine too: it lives in `<state dir>/pool.json`
# (`{"max_busy_sessions": N, "max_active_5h_percent": P}`), the directory the queue and every
# worker's files already share. A repo's `workers` block may only lower either value: a repo above
# the machine started past a repo whose queued start waited. The busy default comes from the
# workspace measured on 21.11.: 13 busy workers drove swap to 5.4 of 5.5 GiB and load15 to 24 on
# 16 CPUs; 7 gave 3.0 GiB swap and a memory stall of 7 s/h (yellow).
POOL_FILE = "pool.json"
POOL_KEY = "max_busy_sessions"
PCT_KEY = "max_active_5h_percent"
POOL_DEFAULTS = {POOL_KEY: 8, PCT_KEY: 80}
QUEUE_TURN_ENV = "WE_WORKER_QUEUE_TURN"
CSWAP_TIMEOUT_S = 20


def workers_block(repo: Path) -> dict:
    """The `workers` block of the repo's `.weside/config.json` (`{}` without file or key); an
    unreadable file refuses (exit 2)."""
    top = Path(_git(repo, "rev-parse", "--show-toplevel") or repo)
    path = top / ".weside" / "config.json"
    try:
        config = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        raise LaunchError(f"{path}: unreadable ({exc})", 2) from exc
    block = config.get("workers") if isinstance(config, dict) else None
    return block if isinstance(block, dict) else {}


PR_OWNERS = ("master", "worker")
PR_OWNER_LINE = "PR owner: worker"


def pr_owner_of(config: object) -> str:
    """`build.pr_owner` of a parsed `.weside/config.json`: `master` (the default, also without the
    file, the block or the key) or `worker`; another value refuses (exit 2).

    `master`: a build worker ends with its report and the master pushes, opens, arms and watches the
    PR. `worker`: a single-chunk build worker carries its own PR to one of three end lines
    (`references/worker-dispatch.md` § PR-carrying worker); the master writes `PR_OWNER_LINE` into
    that worker's brief, and `worker_rights.py` reads the same key from the default branch to open
    the worker's PR rights."""
    block = config.get("build") if isinstance(config, dict) else None
    value = block.get("pr_owner", "master") if isinstance(block, dict) else "master"
    if value not in PR_OWNERS:
        raise LaunchError(f"build.pr_owner: one of {', '.join(PR_OWNERS)}, not {value!r}", 2)
    return value


def pr_owner(repo: Path) -> str:
    """`build.pr_owner` of the repo's `.weside/config.json` in the worktree (`pr_owner_of`)."""
    top = Path(_git(repo, "rev-parse", "--show-toplevel") or repo)
    path = top / ".weside" / "config.json"
    try:
        config = json.loads(path.read_text())
    except FileNotFoundError:
        return "master"
    except (OSError, json.JSONDecodeError) as exc:
        raise LaunchError(f"{path}: unreadable ({exc})", 2) from exc
    return pr_owner_of(config)


def _limit(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise LaunchError(f"{label}: needs a positive number, not {value!r}", 2)
    return value


def repo_limits(repo: Path) -> dict[str, float]:
    """The pool keys the repo's `.weside/config.json` `workers` block sets (`{}` without them); a
    value that is no positive number refuses (exit 2)."""
    block = workers_block(repo)
    return {k: _limit(block[k], f"workers.{k}") for k in POOL_DEFAULTS if k in block}


def cap_limits(
    repo: Path, note: bool = True, sources: dict[str, str] | None = None
) -> dict[str, float]:
    """The limits a start from `repo` must pass: per key the machine's (`pool_limits`), lowered
    by the repo's `workers` value where it is lower; a repo never lifts one. With `note`, a repo
    value above the machine's gets one stderr line: it is not read. A `sources` dict gets, per
    key, where the value came from (the repo's config or the machine's `pool.json`)."""
    machine, own = pool_limits(), repo_limits(repo)
    limits = {}
    for key, value in machine.items():
        limits[key] = min(value, own.get(key, value))
        if sources is not None:
            sources[key] = (
                f"workers.{key} in {repo}/.weside/config.json"
                if own.get(key, value) < value
                else f"{key} of {pool_path()}"
            )
        if note and own.get(key, value) > value:
            print(
                f"we-worker: note: workers.{key} {own[key]:g} in {repo}/.weside/config.json is"
                f" above the machine's {value:g} ({pool_path()}) and not read; a repo can only"
                f" lower it: remove workers.{key} from that file",
                file=sys.stderr,
            )
    return limits


def pool_path(state: Path | None = None) -> Path:
    return (_state_dir() if state is None else state) / POOL_FILE


def pool_limits(state: Path | None = None) -> dict[str, float]:
    """The machine's limits: `pool.json`'s `max_busy_sessions` and `max_active_5h_percent`, each
    else its `POOL_DEFAULTS` value; an unreadable file or a value that is no positive number
    refuses (exit 2)."""
    path = pool_path(state)
    try:
        doc = json.loads(path.read_text())
    except FileNotFoundError:
        return dict(POOL_DEFAULTS)
    except (OSError, json.JSONDecodeError) as exc:
        raise LaunchError(f"{path}: unreadable ({exc})", 2) from exc
    if not isinstance(doc, dict):
        doc = {POOL_KEY: doc}
    return {k: _limit(doc.get(k, d), f"{path} {k}") for k, d in POOL_DEFAULTS.items()}


def queued_ahead(state: Path, me: str | None) -> list[dict]:
    """The queued starts (`worker_supervisor.queued`) whose waiter lives and that came before `me`
    (the waiter's own entry, `$WE_WORKER_QUEUE_TURN`); for a start that is not queued, every
    living one. Oldest first."""
    import worker_supervisor  # noqa: PLC0415 (it imports this module)

    rows = [d for d in worker_supervisor.queued(state) if worker_supervisor.waiter_lives(d)]
    if not me:
        return rows
    mine = next((d for d in rows if d["name"] == me), None)
    if mine is None:
        return rows
    # the name breaks a tie in `queued_at`: two entries of the same second must not each see the
    # other ahead of it, or both wait out their timeout
    turn = (mine.get("queued_at", 0), me)
    return [d for d in rows if d["name"] != me and (d.get("queued_at", 0), d["name"]) < turn]


def queued_limits(doc: dict, machine: dict[str, float]) -> tuple[float, float]:
    """A queued start's own `(max_busy_sessions, max_active_5h_percent)`: the machine's, lowered
    by its repo's values recorded at queue time (`repo_limits`); an entry without them has the
    machine's."""
    own = doc.get("repo_limits") if isinstance(doc.get("repo_limits"), dict) else {}
    out = []
    for key in (POOL_KEY, PCT_KEY):
        value = own.get(key)
        ok = isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
        out.append(min(machine[key], value) if ok else machine[key])
    return out[0], out[1]


def five_hour_percent() -> float | None:
    """The active account's 5h window in percent (`cswap status --json`), None when unreadable."""
    try:
        out = subprocess.run(
            ["cswap", "status", "--json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=CSWAP_TIMEOUT_S,
        )
        pct = json.loads(out.stdout)["active"]["usage"]["fiveHour"]["pct"]
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError):
        return None
    return float(pct) if isinstance(pct, (int, float)) and not isinstance(pct, bool) else None


SEVEN_DAY_FULL = 95


def _pct(window: object) -> float | None:
    pct = window.get("pct") if isinstance(window, dict) else None
    return float(pct) if isinstance(pct, (int, float)) and not isinstance(pct, bool) else None


def rotation_accounts() -> list[dict] | None:
    """The accounts in rotation of `cswap list --json` (`accounts[]` without `disabled: true`);
    None when unreadable or without the list."""
    try:
        out = subprocess.run(
            ["cswap", "list", "--json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=CSWAP_TIMEOUT_S,
        )
        rows = json.loads(out.stdout)["accounts"]
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError):
        return None
    if not isinstance(rows, list) or not rows:
        return None
    return [r for r in rows if isinstance(r, dict) and r.get("disabled") is not True]


def room_in(accounts: list[dict], max_pct: float) -> tuple[int, int]:
    """`(with room, in rotation)`: an account has room when its `usage.sevenDay.pct` is under
    `SEVEN_DAY_FULL` and its `usage.fiveHour.pct` is at or under `max_pct`. An account without a
    readable reading has no room. Never reads a name."""
    room = 0
    for row in accounts:
        usage = row.get("usage") if isinstance(row.get("usage"), dict) else {}
        five, seven = _pct(usage.get("fiveHour")), _pct(usage.get("sevenDay"))
        if five is not None and seven is not None and seven < SEVEN_DAY_FULL and five <= max_pct:
            room += 1
    return room, len(accounts)


def capacity(repo: Path, prefix: str) -> None:
    """Refuse a new worker (`LaunchError`, exit 3) while a queued start of any repo on this machine
    waits ahead of it (`queued_ahead`: first come, first served across repos), while the busy
    background sessions on this machine and busy window workers (`claude agents --json`, `status`
    busy; an interactive row counts only when `is_worker` says so: a companion or master is busy
    whenever it answers its human) reach the limit (`cap_limits`: the machine's, lowered by the
    repo's), or while no account in rotation has room (`room_in`: 7d under 95 %, 5h at or under
    `max_active_5h_percent`; one with room is enough, the rotation switches to it). A queued
    start ahead that only its own repo's lower limit holds back holds nobody up while the machine
    has room (`queued_limits`). When
    `cswap list --json` is unreadable the active account's 5h window decides as the fallback
    (`five_hour_percent`, refused above the limit). The refusal names the measured values, never an
    account. A value that cannot be read skips its check with one stderr warning; without `cswap`
    on PATH (it is optional) the 5h check is skipped silently."""
    machine = pool_limits()
    sources: dict[str, str] = {}
    limits = cap_limits(repo, sources=sources)
    max_busy, max_pct = limits[POOL_KEY], limits[PCT_KEY]
    ahead = queued_ahead(_state_dir(), os.environ.get(QUEUE_TURN_ENV))
    try:
        busy: int | None = sum(
            1
            for r in sessions()
            if r.get("status") == "busy" and (r.get("kind") != "interactive" or is_worker(r))
        )
    except LaunchError as exc:
        busy = None
        print(
            f"{prefix}: warning: busy sessions unreadable ({exc}); that check is skipped",
            file=sys.stderr,
        )
    have_cswap = bool(shutil.which("cswap"))
    accounts = rotation_accounts() if have_cswap else None
    room = None if accounts is None else room_in(accounts, max_pct)
    pct = five_hour_percent() if have_cswap and room is None else None
    if have_cswap and room is None and pct is None:
        print(
            f"{prefix}: warning: the accounts' 5h windows are unreadable"
            " (cswap list --json and cswap status --json failed); that check is skipped",
            file=sys.stderr,
        )

    def held(busy_limit: float, pct_limit: float) -> bool:
        if busy is not None and busy >= busy_limit:
            return True
        if accounts is not None:
            return room_in(accounts, pct_limit)[0] == 0
        return pct is not None and pct > pct_limit

    full = held(float("inf"), max_pct)
    if ahead and not held(machine[POOL_KEY], machine[PCT_KEY]):
        # the machine has room: a queued start that only its own repo's lower limit holds back
        # stays first in line and holds nobody else up (`queued_limits`)
        ahead = [d for d in ahead if not held(*queued_limits(d, machine))]
    if ahead:
        first = ahead[0]
        since = time.strftime("%H:%M", time.gmtime(first.get("queued_at", time.time())))
        shown_busy = "?" if busy is None else str(busy)
        raise LaunchError(
            f"refused, no worker started: {len(ahead)} queued start(s) ahead (first"
            f" {first['name']}, queued {since} UTC; {shown_busy} workers busy, limit"
            f" {max_busy:g} for the machine); the queue starts in arrival order across repos:"
            " add --queue to the we-worker start",
            3,
        )
    if (busy is not None and busy >= max_busy) or full:
        shown_busy = "?" if busy is None else str(busy)
        if room is not None:
            quota = (
                f"no account in rotation has room (0 of {room[1]} with 7d under"
                f" {SEVEN_DAY_FULL} % and 5h at or under {max_pct:g} %"
                if room[0] == 0
                else f"{room[0]} of {room[1]} accounts in rotation with room (5h limit {max_pct:g} %"
            )
        else:
            shown_pct = "?" if pct is None else f"{pct:g}"
            quota = f"active account 5h at {shown_pct} % (limit {max_pct:g} %"
        raise LaunchError(
            f"refused, no worker started: {shown_busy} workers busy (limit {max_busy:g} for the"
            f" machine, {pool_path()}), {quota}, {sources[PCT_KEY]});"
            " try again later, or add --queue to the we-worker start: it starts as soon as"
            " the check passes",
            3,
        )


def claude_env() -> dict:
    """The environment of every `claude` call here, without `CLAUDE_CONFIG_DIR`: a pinned master
    runs on its own config dir, whose supervisor knows none of the workers on the global login
    (the same as `we-worker`'s `env -u CLAUDE_CONFIG_DIR`)."""
    return {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}


def sessions() -> list[dict]:
    """`claude agents --json`: interactive and background sessions on this machine."""
    try:
        out = subprocess.run(
            ["claude", "agents", "--json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=AGENTS_TIMEOUT_S,
            env=claude_env(),
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


DEFAULT_KEY = "[A-Z]+-\\d+"


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
    """The story key the worker name starts with; a `LaunchError` (exit 2) without one. Close, the
    board and the supervisor find a story's workers by the key in the name, so a keyless worker
    would be invisible to all three."""
    try:
        found = re.match(rf"(?P<key>{key_re})(?:-(?P<chunk>.+))?$", name)
    except re.error as exc:
        raise LaunchError(f"naming.key {key_re!r} is no regex ({exc})", 2) from exc
    if found and found.group("key"):
        return found.group("key")
    raise LaunchError(
        f"worker name {name} carries no story key ({key_re}), e.g. {example or 'ABC-123'}-{name}"
        " (close, the board and the supervisor find a story's workers by that key)",
        2,
    )


def _example_key(repo: Path | None, key_re: str) -> str | None:
    branch = _git(repo or Path.cwd(), "branch", "--show-current") or ""
    try:
        found = re.search(key_re, branch)
    except re.error:
        return None
    return found.group(0) if found else None


def check(name: str, repo: Path | None = None) -> str:
    """`check_name` against the repo's `naming.key`: the key, or a `LaunchError` (exit 2)."""
    key_re = key_pattern(repo)
    return check_name(name, key_re, _example_key(repo, key_re))


TREE_PLACEHOLDERS = ("path", "branch")
TREE_KEY = "workers.add_worktree"
REMOVE_KEY = "workers.remove_worktree"
BRANCH_TYPE = "feat"
TREE_TIMEOUT_S = 600


def main_checkout(cwd: Path) -> Path | None:
    """The top of the repo when `cwd` lies in its main checkout (git dir = common dir), else None:
    a linked worktree, a bare repo or no repo at all."""
    gd = _git(cwd, "rev-parse", "--absolute-git-dir")
    common = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    top = _git(cwd, "rev-parse", "--show-toplevel")
    if not (gd and common and top) or Path(gd).resolve() != Path(common).resolve():
        return None
    return Path(top)


def default_branch(top: Path) -> str:
    """`origin/HEAD`'s branch, else `main`."""
    ref = _git(top, "symbolic-ref", "--short", "refs/remotes/origin/HEAD") or ""
    return ref.split("/", 1)[1] if "/" in ref else "main"


def tree_path(top: Path, name: str) -> Path:
    return top.parent / f"{top.name}-{name}"


TREE_MODES = ("caller", "own")
NO_TREE = 3  # `tree --auto`: no tree to create, the start stays where it is


def tree_mode(repo: Path) -> str:
    """`workers.tree` of the repo's `.weside/config.json`: `caller` (default: a start stays where
    the caller stands) or `own` (a start from the main checkout gets its own worktree)."""
    mode = workers_block(repo).get("tree", "caller")
    if mode not in TREE_MODES:
        raise LaunchError(f"workers.tree: one of {', '.join(TREE_MODES)}, not {mode!r}", 2)
    return mode


def auto_tree(
    repo: Path, name: str, branch: str | None = None, queued: bool = False
) -> Path | None:
    """The tree a start without `--tree`/`--here` gets: under `workers.tree: own`, and for a
    queued start (`--queue`) under any mode, a start from the main checkout gets a new one
    (`add_tree`): a queued start begins when its waiter finds room, with the caller's checkout
    long moved on. Otherwise None, the start stays where it is; under `caller` a start from the
    main checkout prints one warning on stderr."""
    main = main_checkout(repo)
    if main is None:
        return None
    if queued or tree_mode(repo) == "own":
        return add_tree(repo, name, branch)
    print(
        f"we-worker: warning: {name} works in the main checkout {main} (workers.tree: caller); "
        "a building worker takes its own tree: --tree <worktree>, or workers.tree: own in "
        ".weside/config.json; a reading worker says so with --here",
        file=sys.stderr,
    )
    return None


def add_tree(repo: Path, name: str, branch: str | None = None) -> Path:
    """Create the worker's own worktree beside the main checkout holding `repo`: the repo's
    `workers.add_worktree` (a template with the tokens `{path}` and `{branch}`, run without a shell
    in the main checkout), else `git worktree add <top>-<name> -b <branch> origin/<default>`. The
    branch defaults to `feat/<name>`. An existing path refuses (exit 2): start in it with
    `--tree`."""
    top = main_checkout(repo)
    if top is None:
        raise LaunchError(f"{repo} is no main checkout of a git repo; pass --tree or --here", 2)
    path = tree_path(top, name)
    if path.exists():
        raise LaunchError(
            f"{path} exists; start in it with --tree {path}, or pick another name", 2
        )
    branch = branch or f"{BRANCH_TYPE}/{name}"
    template = workers_block(top).get("add_worktree")
    if template is not None and not isinstance(template, str):
        raise LaunchError(f"{TREE_KEY}: must be a command string", 2)
    if template:
        tokens = validate(template, TREE_KEY, TREE_PLACEHOLDERS, ("path",))
        argv = render(tokens, {"path": str(path), "branch": branch})
    else:
        base = default_branch(top)
        _git(top, "fetch", "--quiet", "origin", base)
        argv = ["git", "worktree", "add", "--quiet", str(path), "-b", branch, f"origin/{base}"]
    try:
        out = subprocess.run(
            argv, cwd=top, capture_output=True, text=True, check=False, timeout=TREE_TIMEOUT_S
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LaunchError(f"{argv[0]}: {exc}") from exc
    if out.returncode != 0 or git_dir(path) is None:
        raise LaunchError(
            f"the worktree {path} was not created ({' '.join(argv[:3])} exited "
            f"{out.returncode}: {out.stderr.strip()})"
        )
    return path


def remove_command(repo: Path, path: str) -> str:
    """The repo's command that removes a worktree (`workers.remove_worktree` with `{path}`), else
    `git worktree remove <path>`; printed by `gc`, never run."""
    template = workers_block(repo).get("remove_worktree")
    if isinstance(template, str) and template.strip():
        tokens = validate(template, REMOVE_KEY, ("path",), ("path",))
        return shlex.join(render(tokens, {"path": path}))
    return shlex.join(["git", "worktree", "remove", path])


def write_marker(tree: Path, starter_session: str | None = None, **fields: object) -> Path:
    """The launcher's marker in the tree's own git dir: name, key, role, starter, tree, mode,
    launched_at. It carries no `session_id`, so the marker-bound worker gates stay as they were.
    The start also goes into `launched.jsonl` (`record_launch`), which outlives the marker."""
    gd = git_dir(tree)
    if gd is None:
        raise LaunchError(f"{tree} is no git worktree")
    doc = {k: v for k, v in fields.items() if v not in (None, "")}
    doc["tree"] = str(tree)
    doc["launched_at"] = time.time()
    (gd / MARKER).write_text(json.dumps(doc, indent=2) + "\n")
    record_launch(
        str(fields.get("name") or ""),
        fields.get("key"),  # type: ignore[arg-type]
        fields.get("starter"),  # type: ignore[arg-type]
        starter_session,
    )
    return gd / MARKER


# --- the starter log ---------------------------------------------------------------------------
#
# `<state_dir>/launched.jsonl` (`state_dir` of `worker_supervisor.py`) keeps one line per start:
# `name, key, starter, starter_session, ts`, a backfilled line also `backfill: <source>`. The
# marker `<state_dir>/<name>.json` goes when its worker ends (`worker_supervisor._remove_files`
# names two files, never this one), so this file is where an ended worker's starter stays.
# `starter_session` is the starting shell's `$CLAUDE_CODE_SESSION_ID`; before this file only the
# external timer (`worker_timer register --starter-session`) received it. Each line is one
# `os.write` on an `O_APPEND` descriptor: parallel launchers leave whole lines without a lock.

LAUNCHED = "launched.jsonl"
STARTERS_SCHEMA = 1
STARTER_RX = re.compile(
    r"Dein Starter ist ([A-Za-z0-9][A-Za-z0-9._-]*)|Lead: ([A-Za-z0-9][A-Za-z0-9._-]*) \u2014"
)
TRANSCRIPT_HEAD_LINES = 200


def _state_dir() -> Path:
    import worker_supervisor  # noqa: PLC0415 (it imports this module)

    return worker_supervisor.state_dir()


def _utc(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if ts is None else ts))


def append_line(path: Path, doc: dict) -> None:
    """One JSON line in one `os.write` on an `O_APPEND` descriptor."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(doc, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def record_launch(
    name: str,
    key: str | None = None,
    starter: str | None = None,
    starter_session: str | None = None,
    state: Path | None = None,
    **extra: object,
) -> None:
    """Append the start of `name` to `launched.jsonl`; a failed write is one stderr line, the
    start goes on."""
    doc = {
        "name": name,
        "key": key or None,
        "starter": starter or None,
        "starter_session": starter_session or None,
        "ts": _utc(),
        **extra,
    }
    import worker_rights  # noqa: PLC0415

    path = (state or _state_dir()) / LAUNCHED
    if worker_rights.forbidden_write(path, doc):
        return
    try:
        append_line(path, doc)
    except OSError as exc:
        print(f"worker_launch: {LAUNCHED} not written ({exc})", file=sys.stderr)


def read_launched(state: Path) -> tuple[list[dict], int]:
    """`(lines, unreadable)` of `launched.jsonl`, oldest first."""
    rows, bad = [], 0
    try:
        text = (state / LAUNCHED).read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            doc = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(doc, dict) and isinstance(doc.get("name"), str) and doc["name"]:
            rows.append(doc)
        else:
            bad += 1
    return rows, bad


def starters_doc(state: Path) -> dict:
    """`starters --json`: the newest line per worker name."""
    rows, bad = read_launched(state)
    newest: dict = {}
    for doc in sorted(rows, key=lambda d: str(d.get("ts"))):
        newest[doc["name"]] = doc
    return {
        "schema_version": STARTERS_SCHEMA,
        "generated_at": _utc(),
        "path": str(state / LAUNCHED),
        "unreadable": bad,
        "starters": [newest[n] for n in sorted(newest)],
    }


def timing_launches(timing: Path) -> dict[str, str]:
    """`{worker name: starter session}` of the `WorkerLaunch` lines in `~/.claude/we-timing`
    (`_timing`: the file stem is the starting session)."""
    out: dict[str, str] = {}
    for path in sorted(timing.glob("*.jsonl")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "WorkerLaunch" not in text:
            continue
        for line in text.splitlines():
            try:
                doc = json.loads(line)
            except ValueError:
                continue
            if isinstance(doc, dict) and doc.get("event") == "WorkerLaunch" and doc.get("name"):
                out.setdefault(str(doc["name"]), path.stem)
    return out


def transcript_starter(projects: Path, session_id: str | None) -> str | None:
    """The starter named in the head of the session's transcript (`Dein Starter ist <X>`, the
    timer's start line, or a brief's `Lead: <X> —`): only the captured name leaves this function,
    never the line; reads at most `TRANSCRIPT_HEAD_LINES` lines."""
    if not session_id or not re.fullmatch(r"[A-Za-z0-9-]+", session_id):
        return None
    for path in projects.glob(f"*/{session_id}.jsonl"):
        try:
            with path.open(encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh):
                    if i >= TRANSCRIPT_HEAD_LINES:
                        break
                    found = STARTER_RX.search(line)
                    if found:
                        return (found.group(1) or found.group(2)).rstrip(".")
        except OSError:
            return None
    return None


def backfill_starters(
    workers: list[tuple[str, str | None]],
    apply: bool,
    *,
    state: Path,
    timing: Path,
    projects: Path,
    session_names: dict[str, str],
) -> list[str]:
    """One line per starterless worker: the source it would use (`timing`, `transcript`) and the
    starter, or `unrecoverable`; with `apply`, one `launched.jsonl` line per recovered worker with
    `backfill: <source>`. Reads only the starter line of a transcript (`transcript_starter`)."""
    launches = timing_launches(timing)
    lines = []
    for name, sid in workers:
        starter, source, starter_session = None, None, None
        if name in launches:
            starter_session = launches[name]
            starter = session_names.get(starter_session)
            source = "timing" if starter else None
        if starter is None:
            starter = transcript_starter(projects, sid)
            source = "transcript" if starter else None
        if starter is None:
            lines.append(f"{name}: unrecoverable")
            continue
        verb = "recovered" if apply else "would use"
        lines.append(f"{name}: {verb} {source} -> {starter}")
        if apply:
            record_launch(
                name,
                None,
                starter,
                starter_session if source == "timing" else None,
                state,
                backfill=source,
            )
    return lines


def _starter_verbs(args: argparse.Namespace) -> int:
    """`launched`, `starters` and `backfill-starters`."""
    state = _state_dir()
    if args.cmd == "launched":
        record_launch(args.name, args.key, args.starter, args.starter_session, state)
        return 0
    if args.cmd == "starters":
        doc = starters_doc(state)
        if args.json:
            print(json.dumps(doc, indent=2, ensure_ascii=False))
        else:
            for x in doc["starters"]:
                print(f"{x['name']} {x.get('starter') or '-'} {x.get('ts') or '-'}")
        return 0
    import datetime as dt  # noqa: PLC0415

    import flow_intervals  # noqa: PLC0415 (the reader owns which lanes are workers)
    import worker_supervisor  # noqa: PLC0415

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    built = flow_intervals.load(Path.cwd(), args.since, now)
    names = {}
    for name, lane in built["lanes"].items():
        if lane.get("session_id"):
            names.setdefault(lane["session_id"], name)
    workers = flow_intervals.starterless(built)
    timing = Path.home() / ".claude" / "we-timing"
    lines = backfill_starters(
        workers,
        args.apply,
        state=state,
        timing=timing,
        projects=worker_supervisor.projects_dir(),
        session_names=names,
    )
    for line in lines:
        print(line)
    gone = sum(1 for x in lines if x.endswith(": unrecoverable"))
    print(
        f"backfill-starters: {len(workers)} workers without a starter, {gone} unrecoverable"
        + ("" if args.apply else "; dry run, nothing written (--apply writes)")
    )
    return 0


AUTO_MEMORY = ("off", "own", "shared")
COMPACT_RANGE = (100_000, 1_000_000)


def _names(ctx: dict, key: str) -> list[str]:
    value = ctx.get(key) or []
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise LaunchError(f"workers.context.{key}: needs a list of names", 2)
    return value


def apply_context(doc: dict, repo: Path, name: str | None, state: Path) -> dict:
    """Lean settings from `workers.context` of the repo's `.weside/config.json`; without the block
    the document stays as it is. `auto_memory` `off` (default) sets
    `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, `own` points `autoMemoryDirectory` at
    `<state>/<name>.memory`, `shared` leaves memory alone; `disable_plugins` → `enabledPlugins`
    false, `deny_mcp_servers` → `deniedMcpServers` by `serverName`, `auto_compact_window` →
    `autoCompactWindow`."""
    ctx = workers_block(repo).get("context")
    if ctx is None:
        return doc
    if not isinstance(ctx, dict):
        raise LaunchError("workers.context: needs an object", 2)
    memory = ctx.get("auto_memory", "off")
    if memory not in AUTO_MEMORY:
        raise LaunchError(f"workers.context.auto_memory: one of {', '.join(AUTO_MEMORY)}", 2)
    if memory == "off":
        doc.setdefault("env", {})["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    elif memory == "own":
        if not name:
            raise LaunchError("workers.context.auto_memory own: the settings need --name", 2)
        own = state / f"{name}.memory"
        own.mkdir(parents=True, exist_ok=True)
        doc["autoMemoryDirectory"] = str(own)
    plugins = _names(ctx, "disable_plugins")
    if plugins:
        doc["enabledPlugins"] = dict.fromkeys(plugins, False)
    servers = _names(ctx, "deny_mcp_servers")
    if servers:
        doc["deniedMcpServers"] = [{"serverName": s} for s in servers]
    window = ctx.get("auto_compact_window")
    if window is not None:
        low, high = COMPACT_RANGE
        if isinstance(window, bool) or not isinstance(window, int) or not low <= window <= high:
            raise LaunchError(
                f"workers.context.auto_compact_window: a number of tokens {low}-{high}", 2
            )
        doc["autoCompactWindow"] = window
    return doc


NEEDS_RE = re.compile(r"^\s*Needs:\s*(.*)$", re.MULTILINE)


def brief_needs(brief: str) -> list[str]:
    """The names of a brief's `Needs: <plugin or MCP server>, …` lines, in order."""
    names = []
    for line in NEEDS_RE.findall(brief):
        names += [n.strip().strip("`") for n in line.split(",") if n.strip().strip("`")]
    return names


SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
SKILL_RE = re.compile(r"(?<![\w/-])/?we:([a-z][a-z0-9-]*)")
SKILL_NEEDS_RE = re.compile(r"^needs:\s*\[(.*)\]\s*$", re.MULTILINE)
TICKETING = "ticketing"  # the symbolic need: the project's ticketing plugin
# `.weside/config.json` `ticketing.tool` → the plugin or MCP server that serves it, by bare name;
# `ticketing.plugin` overrides it. A tool without an entry (`github-issues`, `none`) needs none.
TICKETING_DEFAULTS = {"jira": ["atlassian"]}


def skill_needs(skill: str, skills_dir: Path | None = None) -> list[str]:
    """The `needs: [<name>, …]` of a plugin skill's frontmatter; `[]` for a skill without one or
    a name that is no skill."""
    try:
        text = ((skills_dir or SKILLS_DIR) / skill / "SKILL.md").read_text()
    except OSError:
        return []
    head = text.split("\n---", 1)[0] if text.startswith("---") else ""
    found = SKILL_NEEDS_RE.search(head)
    if not found:
        return []
    return [n.strip().strip("'\"") for n in found.group(1).split(",") if n.strip().strip("'\"")]


def brief_skills(brief: str) -> list[str]:
    """The plugin skills a brief names (`/we:plan-story`, `Skill we:develop`), in order, once each."""
    return list(dict.fromkeys(SKILL_RE.findall(brief)))


def _config(repo: Path) -> dict:
    top = Path(_git(repo, "rev-parse", "--show-toplevel") or repo)
    try:
        config = json.loads((top / ".weside" / "config.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {}  # workers_block already refused an unreadable file
    return config if isinstance(config, dict) else {}


def resolve_need(need: str, repo: Path) -> list[str]:
    """A declared need as plugin or MCP server names: `ticketing` through `.weside/config.json`
    (`ticketing.plugin`, a name or a list, else `TICKETING_DEFAULTS[ticketing.tool]`), every
    other name as itself."""
    if need != TICKETING:
        return [need]
    block = _config(repo).get("ticketing")
    if not isinstance(block, dict):
        return []
    named = block.get("plugin")
    if isinstance(named, str) and named:
        return [named]
    if isinstance(named, list):
        return [n for n in named if isinstance(n, str) and n]
    return list(TICKETING_DEFAULTS.get(str(block.get("tool") or ""), []))


def _hit(need: str, plugins: list[str], servers: list[str]) -> tuple[str, str] | None:
    """`(key, entry)` of the `workers.context` entry that turns `need` off, else None."""
    hit = next((p for p in plugins if need in (p, p.split("@", 1)[0])), None)
    if hit is not None:
        return "disable_plugins", hit
    if need in servers:
        return "deny_mcp_servers", need
    return None


def check_needs(brief: str, repo: Path) -> None:
    """Refuse (exit 2) a brief that needs a plugin `workers.context.disable_plugins` disables (by
    its id `<plugin>@<marketplace>` or its bare name) or a server `deny_mcp_servers` denies: the
    worker would start without a tool its brief needs. The needs are the brief's `Needs:` lines
    and the frontmatter `needs:` of every plugin skill the brief names. Refusing at launch is the
    point: without it the missing tool shows only after the worker has run its chunk."""
    needs, skills = brief_needs(brief), brief_skills(brief)
    if not needs and not any(skill_needs(s) for s in skills):
        return
    ctx = workers_block(repo).get("context")
    if not isinstance(ctx, dict):
        return
    plugins, servers = _names(ctx, "disable_plugins"), _names(ctx, "deny_mcp_servers")
    if not plugins and not servers:
        return
    for need in needs:
        found = next(
            (f for n in resolve_need(need, repo) if (f := _hit(n, plugins, servers))), None
        )
        if found is not None:
            key, hit = found
            raise LaunchError(
                f"the brief needs {need}, which workers.context.{key} turns off ({hit}) for"
                " every worker; drop it from the brief's Needs line or from"
                f" workers.context.{key}; no worker started",
                2,
            )
    for skill in skills:
        line = skill_conflict(skill, repo, plugins, servers)
        if line:
            raise LaunchError(f"{line}; no worker started", 2)


def skill_conflict(skill: str, repo: Path, plugins: list[str], servers: list[str]) -> str | None:
    """The refusal text when a need of plugin skill `skill` is turned off, else None."""
    for need in skill_needs(skill):
        for name in resolve_need(need, repo):
            found = _hit(name, plugins, servers)
            if found is not None:
                key, hit = found
                what = f"{name} (the project's ticketing plugin)" if need == TICKETING else name
                return (
                    f"the brief names /we:{skill}, which needs {what}, and"
                    f" workers.context.{key} turns it off ({hit}) for every worker; drop it from"
                    f" workers.context.{key} or start the worker without /we:{skill}"
                )
    return None


POINTER_RE = re.compile(r"^\s*Read (\S+) and follow it\.?\s*$", re.MULTILINE)


def brief_text(brief: str) -> str:
    """The brief with the files its `Read <path> and follow it.` lines point at appended: most
    briefs are such a pointer, and the skills stand in the file."""
    parts = [brief]
    for path in POINTER_RE.findall(brief):
        with contextlib.suppress(OSError, UnicodeDecodeError):
            parts.append(Path(path).expanduser().read_text())
    return "\n".join(parts)


def ticketing_unneeded(brief: str, repo: Path) -> list[str]:
    """The project's ticketing plugins or servers a worker starts without: the brief names
    `/we:<skill>`s and neither one of them (frontmatter `needs:`) nor a `Needs:` line asks for
    ticketing. A brief without a skill keeps every tool, since nothing says what it does."""
    brief = brief_text(brief)
    skills = brief_skills(brief)
    names = resolve_need(TICKETING, repo) if skills else []
    if not names:
        return []
    wanted = {
        n.split("@", 1)[0]
        for need in brief_needs(brief) + [n for s in skills for n in skill_needs(s)]
        for n in resolve_need(need, repo)
    }
    return [] if wanted & {n.split("@", 1)[0] for n in names} else names


def installed_plugin_ids(env: dict | None = None) -> list[str]:
    """The plugin ids (`<plugin>@<marketplace>`) of Claude Code's `installed_plugins.json`."""
    import claude_home  # noqa: PLC0415

    try:
        path = claude_home.config_dir(env) / "plugins" / "installed_plugins.json"
        data = json.loads(path.read_text())
        return [k for k in data.get("plugins") or {} if isinstance(k, str)]
    except (OSError, ValueError, AttributeError):
        return []


def turn_off(doc: dict, names: list[str], installed: list[str] | None = None) -> dict:
    """Turn `names` off in a settings document: an installed plugin (by id or bare name) through
    `enabledPlugins` false, which drops its MCP servers and its skills; any other name through
    `deniedMcpServers`. A plugin's server is `plugin:<plugin>:<server>` to Claude Code, so a deny
    by the bare plugin name would not hold (measured with `claude -p` 2026-11-19)."""
    installed = installed_plugin_ids() if installed is None else installed
    for name in names:
        ids = [i for i in installed if name in (i, i.split("@", 1)[0])]
        if ids:
            doc.setdefault("enabledPlugins", {}).update(dict.fromkeys(ids, False))
        else:
            denied = doc.setdefault("deniedMcpServers", [])
            if {"serverName": name} not in denied:
                denied.append({"serverName": name})
    return doc


def check_all_skills(repo: Path) -> list[str]:
    """One line per plugin skill whose need `workers.context` turns off (`/we:setup` warns)."""
    ctx = workers_block(repo).get("context")
    if not isinstance(ctx, dict):
        return []
    plugins, servers = _names(ctx, "disable_plugins"), _names(ctx, "deny_mcp_servers")
    lines = []
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        line = skill_conflict(skill_md.parent.name, repo, plugins, servers)
        if line:
            lines.append(line)
    return lines


# ---------------------------------------------------------------- accounts
# `.weside/config.json` `agents.accounts_command`: the project's own tool chooses the account a
# worker runs on. The plugin runs it as `<cmd> --need critical|uncritical [--account <name>]`
# (no shell, cwd = the repo) and reads one JSON object from stdout:
# `{name, kind, env, token_command?, quota?}`. The policy (`off|backup|uncritical|free`) lives in
# that tool, never here; the plugin only refuses what breaks its own rule below.
ACCOUNTS_KEY = "agents.accounts_command"
ACCOUNT_NEEDS = ("critical", "uncritical")
ACCOUNT_AUTO = "auto"
CLAUDE_KIND = "claude"
ACCOUNTS_TIMEOUT_S = 30
ACCOUNT_LINE_RE = re.compile(r"^\s*Account:\s*uncritical\b", re.MULTILINE | re.IGNORECASE)
# only the brief's head counts: a brief often carries ticket or PR text verbatim further down
ACCOUNT_HEAD_LINES = 10


# `we-worker` drops every CLAUDE* variable so a worker never books on the starter's (pinned)
# account, and WE_*/WESIDE_* steer the crew machinery: an account's `env` may not set them back.
# `CLAUDE_CODE_*` stays open: those are the CLI's settings (provider switch, output limits).
def _reserved_env(name: str) -> bool:
    upper = name.upper()
    if upper.startswith(("WE_", "WESIDE_")):
        return True
    return upper.startswith("CLAUDE") and not upper.startswith("CLAUDE_CODE_")


# a settings file is no place for a credential: a secret reaches the worker only through
# `token_command`, which becomes `apiKeyHelper` and runs inside the worker
# (a whole `_`-separated segment: `MAX_OUTPUT_TOKENS` or `API_KEY_HELPER_TTL_MS` are settings, not
# secrets, and the CLI's `CLAUDE_CODE_SKIP_*_AUTH` flags carry none)
SECRET_NAME_RE = re.compile(
    r"^(?!CLAUDE_CODE_SKIP_\w+_AUTH$).*?(?:^|_)(?:KEY|APIKEY|TOKEN|SECRET|PASSWORD|PASSWD|PAT|AUTH|CREDENTIALS?)(?:_|$)(?!HELPER)",
    re.IGNORECASE,
)


def brief_account_need(brief: str) -> str:
    """`uncritical` when one of the brief's first lines is `Account: uncritical`, else
    `critical`: a worker is critical unless its brief's head says otherwise."""
    head = "\n".join(brief.splitlines()[:ACCOUNT_HEAD_LINES])
    return "uncritical" if ACCOUNT_LINE_RE.search(head) else "critical"


def choose_account(repo: Path, account: str, need: str) -> dict:
    """The account the project's `agents.accounts_command` returns for `need` (`auto`) or by
    `account` name; refuses (exit 2) without the option, on a failed command or a malformed
    answer, and when a critical worker would land on a non-Claude account."""
    if need not in ACCOUNT_NEEDS:
        raise LaunchError(f"--need {need!r}: one of {', '.join(ACCOUNT_NEEDS)}", 2)
    agents = _config(repo).get("agents")
    command = agents.get("accounts_command") if isinstance(agents, dict) else None
    if not command or not isinstance(command, str):
        raise LaunchError(
            f"--account {account}: {ACCOUNTS_KEY} is not set in .weside/config.json; "
            "start without --account",
            2,
        )
    argv = [*shlex.split(command), "--need", need]
    if account != ACCOUNT_AUTO:
        argv += ["--account", account]
    try:
        out = subprocess.run(
            argv,
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=ACCOUNTS_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LaunchError(f"{ACCOUNTS_KEY} failed to run ({type(exc).__name__})", 2) from exc
    if out.returncode != 0:
        # its stderr is not echoed: a tool that handles credentials may print one there
        raise LaunchError(
            f"{ACCOUNTS_KEY} exited {out.returncode} for --need {need}; no account", 2
        )
    try:
        chosen = json.loads(out.stdout)
    except json.JSONDecodeError as exc:
        raise LaunchError(f"{ACCOUNTS_KEY} printed no JSON object", 2) from exc
    return _checked_account(chosen, account, need)


def _checked_account(chosen: object, account: str, need: str) -> dict:
    if not isinstance(chosen, dict):
        raise LaunchError(f"{ACCOUNTS_KEY} printed no JSON object", 2)
    name, kind, env = chosen.get("name"), chosen.get("kind"), chosen.get("env", {})
    helper = chosen.get("token_command")
    if not isinstance(name, str) or not name or not isinstance(kind, str) or not kind:
        raise LaunchError(f"{ACCOUNTS_KEY}: the answer needs a `name` and a `kind`", 2)
    if account not in (ACCOUNT_AUTO, name):
        raise LaunchError(f"{ACCOUNTS_KEY} answered {name} for --account {account}", 2)
    if not isinstance(env, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in env.items()
    ):
        raise LaunchError(f"{ACCOUNTS_KEY}: `env` of {name} is no object of strings", 2)
    reserved = sorted(k for k in env if _reserved_env(k))
    if reserved:
        raise LaunchError(
            f"{ACCOUNTS_KEY}: `env` of {name} sets {', '.join(reserved)}; the worker's own "
            "launch owns CLAUDE* and WE_* variables",
            2,
        )
    secret = sorted(k for k in env if SECRET_NAME_RE.search(k))
    if secret:
        raise LaunchError(
            f"{ACCOUNTS_KEY}: `env` of {name} names {', '.join(secret)}; a credential goes "
            "through `token_command`, never into the settings file",
            2,
        )
    if helper is not None and (not isinstance(helper, str) or not helper.strip()):
        raise LaunchError(f"{ACCOUNTS_KEY}: `token_command` of {name} is no command", 2)
    # The owner's decision: work that matters runs on Claude. Another LLM (or a raw API key
    # outside the Claude login) may only take a worker its brief marks uncritical.
    if need == "critical" and kind != CLAUDE_KIND:
        raise LaunchError(
            f"{ACCOUNTS_KEY} chose {name} (kind {kind}) for a critical worker; a critical "
            f"worker runs only on a {CLAUDE_KIND} account (mark the brief `Account: uncritical` "
            "in its first ten lines, or name a claude account)",
            2,
        )
    doc = {"name": name, "kind": kind, "env": dict(env), "need": need}
    if helper:
        doc["token_command"] = helper
    if "quota" in chosen:
        doc["quota"] = chosen["quota"]
    return doc


def _write_private(path: Path, text: str) -> None:
    """Write `text` readable by the owner only: a settings or account file names the
    account's environment."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)


def apply_account(doc: dict, chosen: dict) -> dict:
    """The chosen account in a worker's settings: its `env` under the worker's own variables
    (those win), its `token_command` as `apiKeyHelper`."""
    doc["env"] = {**chosen.get("env", {}), **doc.get("env", {})}
    if chosen.get("token_command"):
        doc["apiKeyHelper"] = chosen["token_command"]
    return doc


def account_line(chosen: dict) -> str:
    """One line naming the account, never a value of its `env` nor its helper's output."""
    quota = f", quota {json.dumps(chosen['quota'])}" if "quota" in chosen else ""
    return f"account {chosen['name']} ({chosen['kind']}, {chosen['need']}{quota})"


def write_settings(
    repo: Path,
    key: str,
    out: Path,
    session_start: str | None = None,
    name: str | None = None,
    account: dict | None = None,
    brief: str | None = None,
    starter: str | None = None,
) -> dict:
    """The worker's `--settings` file (`worker_rights.settings`), with the timer's hook, the
    lean context of `workers.context` (`apply_context`), the chosen account (`apply_account`)
    and, for a brief whose skills need no ticket, the ticketing plugin turned off
    (`ticketing_unneeded`)."""
    import worker_rights  # noqa: PLC0415

    doc = apply_context(worker_rights.settings(repo, key, starter), repo, name, out.parent)
    if account:
        apply_account(doc, account)
    if brief:
        turn_off(doc, ticketing_unneeded(brief, repo))
    commands = [session_start] if session_start else []
    out.parent.mkdir(parents=True, exist_ok=True)
    if brief and brief.strip() and name:
        commands.append(brief_hook(write_brief(out.parent, name, brief)))
    if commands:
        doc["hooks"] = {
            "SessionStart": [{"hooks": [{"type": "command", "command": c} for c in commands]}]
        }
    _write_private(out, json.dumps(doc, indent=2) + "\n")
    return doc


# The brief also as a file: `claude --bg` drops its prompt argument when a SendMessage reaches the
# new session before it submitted that prompt (measured 20.11.: a queued start, whose waiter tells
# the starter at once, and a resume). The worker's SessionStart hook names the file, so the next
# turn finds the brief whichever message starts it.
BRIEF_SUFFIX = ".brief.md"


def write_brief(state: Path, name: str, brief: str) -> Path:
    """`<state>/<name>.brief.md`, private; the next start of that name overwrites it."""
    path = state / f"{name}{BRIEF_SUFFIX}"
    _write_private(path, brief if brief.endswith("\n") else brief + "\n")
    return path


def brief_hook(path: Path) -> str:
    """The SessionStart command that names the brief file as additional context."""
    text = (
        f"we-worker: your brief is the file {path}. If this conversation does not start with it"
        " (a message that reaches a new session first can push the start prompt out), read that"
        " file now and follow it."
    )
    payload = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
    return "printf '%s\\n' " + shlex.quote(json.dumps(payload, ensure_ascii=False))


def launch(worktree: Path, name: str, brief_file: Path, agent: str | None = None) -> Path:
    try:
        brief = brief_file.read_text()
    except OSError as exc:
        raise LaunchError(f"brief: {exc}") from exc
    key = check(name, worktree)
    check_needs(brief, worktree)
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
    if Path(argv[0]).name == "claude" and "--bg" in argv and "--settings" not in argv:
        # a `claude --bg` session takes the daemon's environment, not this one: the worker's
        # variables go in as settings (`we-worker` writes its own)
        import worker_rights  # noqa: PLC0415

        settings_path = gd / SETTINGS
        off = ticketing_unneeded(brief, worktree)  # read on the worker's login, as `claude_env`
        doc = turn_off(
            {"env": worker_rights.worker_env(key, starter=lead)},
            off,
            installed_plugin_ids(claude_env()),
        )
        settings_path.write_text(json.dumps(doc, indent=2) + "\n")
        argv[1:1] = ["--settings", str(settings_path)]
    try:
        out = subprocess.run(
            argv, cwd=worktree, capture_output=True, text=True, check=False, env=claude_env()
        )
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
            "its worker gates stay off",
            file=sys.stderr,
        )
    _timing("WorkerLaunch", name=name, agent_type=agent, cwd=str(worktree))
    record_launch(name, key, lead, os.environ.get("CLAUDE_CODE_SESSION_ID"))
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


def _pid_lives(pid: object) -> bool:
    """A row without a readable pid counts as living; a pid no process holds does not."""
    try:
        num = int(str(pid))
    except ValueError:
        return True
    if num <= 0:
        return True
    try:
        os.kill(num, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def alive(name: str) -> bool:
    """A session of that name whose process lives: `claude agents` keeps the row of a background
    worker that died (an auth error, a usage limit), and the watchdog must see it end."""
    return any(_pid_lives(r.get("pid", "-")) for r in _running(sessions(), name))


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
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=STOP_VERB_TIMEOUT_S,
            env=claude_env(),
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
    p = sub.add_parser("pr-owner")
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p = sub.add_parser("check")
    p.add_argument("--name", required=True)
    p.add_argument("--brief-file", help=argparse.SUPPRESS)  # an older we-worker copy passes it
    p.add_argument("--no-brief", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument("--prefix", default="worker_launch")
    sub.add_parser("pool-path")
    p = sub.add_parser("capacity")
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument("--prefix", default="worker_launch")
    p = sub.add_parser("needs")
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument("--all", action="store_true")
    p.add_argument("--prefix", default="worker_launch")
    _settings_parsers(sub)
    p = sub.add_parser("tree")
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument("--name", required=True)
    p.add_argument("--branch")
    p.add_argument("--main-checkout", action="store_true")
    p.add_argument("--auto", action="store_true")
    p.add_argument("--queued", action="store_true")
    p = sub.add_parser("marker")
    p.add_argument("--tree", type=Path, required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--key")
    p.add_argument("--role", default="worker")
    p.add_argument("--starter")
    p.add_argument("--mode")
    p.add_argument("--starter-session")
    _starter_parsers(sub)
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


def _starter_parsers(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("launched")
    p.add_argument("--name", required=True)
    p.add_argument("--key")
    p.add_argument("--starter")
    p.add_argument("--starter-session")
    p = sub.add_parser("starters")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("backfill-starters")
    p.add_argument("--since", default="14d")
    p.add_argument("--apply", action="store_true")


def _settings_parsers(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("settings")
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--session-start")
    p.add_argument("--name")
    p.add_argument("--account-file", type=Path)
    p.add_argument("--brief-stdin", action="store_true")
    p.add_argument("--starter")
    p = sub.add_parser("account")
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument("--account", required=True)
    p.add_argument("--need", default="critical")
    p.add_argument("--out", type=Path, required=True)
    sub.add_parser("account-need")


def _settings_verbs(args: argparse.Namespace) -> None:
    """`settings` (with the chosen account of `--account-file`), `account` and `account-need`."""
    if args.cmd == "account-need":
        print(brief_account_need(sys.stdin.read()))
    elif args.cmd == "account":
        chosen = choose_account(args.repo.resolve(), args.account, args.need)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        _write_private(args.out, json.dumps(chosen, indent=2) + "\n")
        print(account_line(chosen))
    else:
        chosen = None
        if args.account_file:
            try:
                chosen = json.loads(args.account_file.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise LaunchError(f"--account-file: {exc}", 2) from exc
        brief = sys.stdin.read() if args.brief_stdin else None
        write_settings(
            args.repo.resolve(),
            args.key,
            args.out,
            args.session_start,
            args.name,
            chosen,
            brief,
            args.starter,
        )
        print(args.out)


def same_key_hint(name: str, key: str, prefix: str) -> None:
    """One stderr hint per living session of the same story key (its name is the key or starts
    with `<key>-`) other than `name`: a follow-up goes to it by `SendMessage`. Best effort: when
    `claude agents --json` fails, nothing is printed."""
    try:
        rows = sessions()
    except LaunchError:
        return
    for row in rows:
        other = str(row.get("name") or "")
        if other == name or not (other == key or other.startswith(f"{key}-")):
            continue
        if not _pid_lives(row.get("pid", "-")):
            continue
        print(
            f"{prefix}: hint: {other} ({row.get('status') or 'running'}) works on {key} and"
            f" lives: a follow-up goes to it by SendMessage, not to a new worker {name}",
            file=sys.stderr,
        )


def _check_verb(args: argparse.Namespace) -> int:
    """`check`: the key on stdout, or exit 2 with the refusal under `--prefix`; a living
    worker of the same key is named as the follow-up's target (`same_key_hint`)."""
    try:
        key = check(args.name, args.repo)
        same_key_hint(args.name, key, args.prefix)
        print(key)
    except LaunchError as exc:
        print(f"{args.prefix}: {exc}", file=sys.stderr)
        return exc.code
    return 0


def _tree_verbs(args: argparse.Namespace) -> int:
    """`tree` (create, or with --main-checkout only name the main checkout) and `marker`."""
    if args.cmd == "marker":
        write_marker(
            args.tree.resolve(),
            name=args.name,
            key=args.key,
            role=args.role,
            starter=args.starter,
            mode=args.mode,
            starter_session=args.starter_session,
        )
        return 0
    if args.main_checkout:
        top = main_checkout(args.repo.resolve())
    elif args.auto:
        # 3, never 1: an exit 1 is also a failed creation, which must stop the start
        top = auto_tree(args.repo.resolve(), args.name, args.branch, args.queued)
        if top is None:
            return NO_TREE
    else:
        top = add_tree(args.repo.resolve(), args.name, args.branch)
    if top is None:
        return 1
    print(top)
    return 0


def _gate_verb(args: argparse.Namespace) -> int:
    """`capacity` and `needs`: exit 0, or the refusal under `--prefix` with its code."""
    try:
        if args.cmd == "needs" and args.all:
            lines = check_all_skills(args.repo)
            for line in lines:
                print(line)
            return 2 if lines else 0
        if args.cmd == "needs":
            check_needs(sys.stdin.read(), args.repo)
        else:
            capacity(args.repo, args.prefix)
    except LaunchError as exc:
        print(f"{args.prefix}: {exc}", file=sys.stderr)
        return exc.code
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.cmd == "check":
        return _check_verb(args)
    if args.cmd in ("capacity", "needs"):
        return _gate_verb(args)
    if args.cmd in ("launched", "starters", "backfill-starters"):
        return _starter_verbs(args)
    code = 0
    try:
        if args.cmd in ("backend", "pr-owner", "pool-path"):
            read = {"backend": backend, "pr-owner": pr_owner}.get(args.cmd)
            print(read(args.repo) if read else pool_path())
        elif args.cmd in ("settings", "account", "account-need"):
            _settings_verbs(args)
        elif args.cmd in ("tree", "marker"):
            code = _tree_verbs(args)
        elif args.cmd == "launch":
            marker = launch(args.worktree.resolve(), args.name, args.brief_file, args.agent)
            print(f"launched: {args.name} · marker {marker}")
        elif args.cmd == "stop":
            ids = stop(args.name, args.worktree.resolve() if args.worktree else None)
            print(f"stopped: {args.name} ({', '.join(ids)})")
        elif args.cmd == "checkpoint":
            print(checkpoint(args.name))
        else:
            code = 0 if alive(args.name) else 1
    except LaunchError as exc:
        print(f"worker_launch: {exc}", file=sys.stderr)
        code = 2 if args.cmd == "alive" else exc.code
    return code


if __name__ == "__main__":
    sys.exit(main())
