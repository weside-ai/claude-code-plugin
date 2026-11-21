#!/usr/bin/env python3
"""Roll-call of the live sessions' plugin versions, and the refresh plan for one that is behind.

A session keeps the plugin version it started with; only a fresh start loads the installed one
(``references/companion-session.md`` § Refresh). Read-only: this script never sends, stops or
starts anything; the coordinator carries a plan out.

Usage:
  session_refresh.py list [--json] [--due]
      one line per live session of ``claude agents --json`` (``worker_launch.sessions``): name,
      role, loaded and installed plugin version, state, ``behind``, ``at_rest`` (with the live
      workers it started and its queued starts), and ``due: <reason>`` when a refresh is due;
      ``--due`` keeps only those; ``--json`` the same rows as a JSON list
  session_refresh.py plan <name> [--from DIR]
      the steps for one session that is behind and at rest: the message that makes it save its
      state, how it stops, how it starts fresh; exit 1 (reason on stderr) for a session that is
      not live, not behind, not at rest, or a worker (a worker ends, it is not refreshed)

Fields:
- ``role``: a background session or one whose worktree's launcher marker names it is ``worker``
  (the rule of ``we-worker is-worker``), but for a background crew member ``start.py launch``
  started (its settings file sets ``WE_ROLE=master``; role key from that file); else ``WE_ROLE_ID`` (the crew role key) or ``WE_ROLE``
  from the process environment (``start.env_values``, three keys, nothing else read); else ``?``.
- ``loaded``: the newest version the process holds (``plugin_install.loaded_versions``),
  ``?`` when unreadable. ``installed``: what a fresh start in the session's cwd loads
  (``plugin_install.install_for``). ``behind``: ``yes`` when loaded < installed, ``?`` when either
  is unknown.
- ``state``: ``blocked`` or ``busy`` from the row (a background row's ``state`` ``working`` is
  busy), else ``idle``. ``at_rest``: idle, no live worker it started (the worker's launcher marker
  ``starter``/``lead``, else its timer file's ``starter`` in ``worker_supervisor.state_dir``), no
  queued start for it (``worker_supervisor.queued`` with a living waiter).
- ``due`` (the coordinator's trigger): behind, at rest, no worker, and (a) the release between the
  two versions changed ``process/``, ``roles/`` or ``hooks/`` (the two cache folders compared file
  by file; an old folder gone: every minor or major bump counts), or (b) the session started
  ``sessions.refresh_after_days`` (crew, default 3) days ago or more.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import crew as crewlib  # noqa: E402
import plugin_install  # noqa: E402
import start as startlib  # noqa: E402
import worker_launch  # noqa: E402
import worker_supervisor  # noqa: E402

WATCHED = ("process", "roles", "hooks")
DEFAULT_DAYS = 3
SCRIPTS = "${CLAUDE_PLUGIN_ROOT}/scripts"


def _env() -> dict:
    """The global login's view (``worker_launch.claude_env``): the cache and installs every session
    of this machine shares, also from a pinned coordinator."""
    return worker_launch.claude_env()


def launched_env(state: Path, name: str) -> dict[str, str]:
    """The ``env`` of the settings file a ``--bg`` start wrote for ``name`` (``we-worker`` or
    ``start.py launch``); {} when there is none."""
    try:
        doc = json.loads(
            (state / f"{worker_supervisor.safe_name(name)}.settings.json").read_text()
        )
    except (OSError, ValueError, worker_launch.LaunchError):
        return {}
    env = doc.get("env") if isinstance(doc, dict) else None
    return env if isinstance(env, dict) else {}


def role_of(
    row: dict, marker: dict | None, environ: dict[str, str] | None, launched: dict | None = None
) -> str:
    """The rule of ``we-worker is-worker``: a background session is a worker unless its settings
    file sets ``WE_ROLE=master`` (a crew member ``start.py launch`` started; its role key then
    comes from that file, the daemon's environment says nothing about it)."""
    launched = launched or {}
    member = row.get("kind") == "background" and launched.get("WE_ROLE") == "master"
    if (row.get("kind") == "background" and not member) or (
        marker and marker.get("name") == row.get("name")
    ):
        return "worker"
    if member:
        return launched.get("WE_ROLE_ID") or "master"
    environ = environ or {}
    return environ.get("WE_ROLE_ID") or environ.get("WE_ROLE") or "?"


def state_of(row: dict) -> str:
    if row.get("state") == "blocked":
        return "blocked"
    if row.get("status") == "busy" or row.get("state") == "working":
        return "busy"
    return "idle"


def _tree_digest(root: Path) -> dict[str, str] | None:
    if not root.is_dir():
        return None
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            try:
                out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                return None
    return out


def changed(old_root: Path | None, new_root: Path | None, old: str, new: str) -> list[str]:
    """The folders of ``WATCHED`` that differ between the two versions; without both folders,
    every bump of the minor or major number counts as all of them."""
    if old_root is not None and new_root is not None and old_root.is_dir() and new_root.is_dir():
        hits = []
        for part in WATCHED:
            a, b = _tree_digest(old_root / part), _tree_digest(new_root / part)
            if a is None or b is None or a != b:
                hits.append(part)
        return hits
    ok, nk = plugin_install.version_key(old) or (), plugin_install.version_key(new) or ()
    return list(WATCHED) if ok[:2] != nk[:2] else []


def refresh_days(cwd: str | None) -> float:
    try:
        _, crew = crewlib.find_and_load(cwd)
    except crewlib.CrewError:
        crew = None
    value = ((crew or {}).get("sessions") or {}).get("refresh_after_days")
    return float(value) if isinstance(value, (int, float)) else float(DEFAULT_DAYS)


def _starters(rows: list[dict], read_marker: Callable, state: Path) -> dict[str, list[str]]:
    """starter name -> the live workers it started."""
    out: dict[str, list[str]] = {}
    for row in rows:
        if not row.get("pid") or not worker_launch._pid_lives(row["pid"]):
            continue
        name = row.get("name") or ""
        marker = read_marker(row.get("cwd"))
        starter = None
        if marker and marker.get("name") == name:
            starter = marker.get("starter") or marker.get("lead")
        if not starter:
            try:
                timer = json.loads(
                    (state / f"{worker_supervisor.safe_name(name)}.json").read_text()
                )
                starter = timer.get("starter") if isinstance(timer, dict) else None
            except (OSError, ValueError, worker_launch.LaunchError):
                starter = None
        if starter and starter != name:
            out.setdefault(str(starter), []).append(name)
    return out


def _queued(state: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for q in worker_supervisor.queued(state):
        if q.get("starter") and worker_supervisor.waiter_lives(q):
            out.setdefault(str(q["starter"]), []).append(str(q["name"]))
    return out


def roll_call(
    rows: list[dict] | None = None,
    env: Any = None,
    now: float | None = None,
    read_marker: Callable = worker_launch.read_marker,
    read_env: Callable = startlib.env_values,
    state: Path | None = None,
) -> list[dict]:
    """One dict per live session (module docstring § Fields)."""
    env = _env() if env is None else env
    rows = worker_launch.sessions() if rows is None else rows
    now = time.time() if now is None else now
    state = worker_supervisor.state_dir() if state is None else state
    roots = plugin_install.cache_roots(env)
    entries = plugin_install.installs(env)
    starters, queued = _starters(rows, read_marker, state), _queued(state)
    out = []
    for row in rows:
        pid = row.get("pid")
        if not pid or not worker_launch._pid_lives(pid):
            continue
        name = str(row.get("name") or row.get("sessionId") or pid)
        cwd = row.get("cwd")
        role = role_of(row, read_marker(cwd), read_env(pid), launched_env(state, name))
        loaded = plugin_install.loaded_versions(pid, roots)
        old = loaded[-1] if loaded else None
        entry = plugin_install.install_for(cwd or "/", env, entries) if cwd else None
        new = str(entry.get("version")) if entry and entry.get("version") else None
        key = plugin_install.version_key
        if old and new and key(old) and key(new):
            behind = "yes" if key(old) < key(new) else "no"
        else:
            behind = "?"
        state_ = state_of(row)
        workers, waits = starters.get(name, []), queued.get(name, [])
        rest = state_ == "idle" and not workers and not waits
        started = row.get("startedAt")
        age = (now - float(started) / 1000) / 86400 if isinstance(started, (int, float)) else None
        due = ""
        if behind == "yes" and rest and role != "worker":
            old_root = next((r / old for r in roots if (r / old).is_dir()), None)
            new_root = Path(str(entry["installPath"])) if entry.get("installPath") else None
            parts = changed(old_root, new_root, old, new)
            if parts:
                due = "changed " + ", ".join(parts)
            elif age is not None and age >= refresh_days(cwd):
                due = f"started {age:.1f} days ago"
        out.append(
            {
                "name": name,
                "session_id": row.get("sessionId") or "",
                "id": row.get("id") or "",
                "pid": pid,
                "kind": row.get("kind") or "",
                "cwd": cwd or "",
                "role": role,
                "loaded": old or "?",
                "installed": new or "?",
                "state": state_,
                "behind": behind,
                "at_rest": rest,
                "workers": workers,
                "queued": waits,
                "age_days": round(age, 1) if age is not None else None,
                "due": due,
            }
        )
    return out


def line(r: dict) -> str:
    rest = "yes" if r["at_rest"] else "no"
    held = [f"workers: {', '.join(r['workers'])}"] if r["workers"] else []
    held += [f"queued: {', '.join(r['queued'])}"] if r["queued"] else []
    rest += f" ({'; '.join(held)})" if held else ""
    due = f"  due: {r['due']}" if r["due"] else ""
    return (
        f"{r['name']}  role={r['role']}  loaded={r['loaded']}  installed={r['installed']}  "
        f"{r['state']}  behind={r['behind']}  at_rest={rest}{due}"
    )


class PlanError(Exception):
    pass


def _crew_member(r: dict, start: str | None) -> tuple[str, dict] | None:
    """(role key or member slug, crew) of a crew member's session, else None."""
    try:
        path, crew = crewlib.find_and_load(start or r["cwd"] or None)
    except crewlib.CrewError:
        return None
    if not crew or path is None:
        return None
    role = r["role"] if r["role"] in (crew.get("roles") or {}) else None
    found = crewlib.member(crew, r["name"])
    if role is None and found is None:
        return None
    if role is None:
        held = [k for k, s in (crew.get("roles") or {}).items() if s == found[0]]
        role = held[0] if held else found[0]
    return role, crew


def plan(name: str, rows: list[dict], start: str | None = None) -> str:
    r = next((x for x in rows if x["name"] == name), None)
    if r is None:
        raise PlanError(f"{name} is no live session (session_refresh.py list)")
    if r["role"] == "worker":
        raise PlanError(f"{name} is a worker: it is not refreshed, it ends after its report")
    if r["behind"] != "yes":
        raise PlanError(f"{name} is not behind (loaded {r['loaded']}, installed {r['installed']})")
    if not r["at_rest"]:
        held = [r["state"], *r["workers"], *(f"queued {q}" for q in r["queued"])]
        raise PlanError(f"{name} is not at rest ({', '.join(held)}); wait for its break")
    member = _crew_member(r, start)
    ready = "ready"
    if member:
        ready = str((member[1].get("labels") or {}).get("ready") or ready)
    message = (
        f"Plugin refresh: you run we {r['loaded']}, {r['installed']} is installed. At this break, "
        "save your state: your own memory file with every open commitment, your board line "
        f"(`board.py set`), unfinished work committed in git. Then reply `{ready}` and start "
        "nothing new; you are started fresh and read that state."
    )
    if r["kind"] == "background":
        stop = f"`env -u CLAUDE_CONFIG_DIR claude stop {r['id'] or r['session_id']}`"
    else:
        stop = (
            "the human types `/exit` in its window (a script never stops the human's own session)"
        )
    out = [
        f"{name}: role {r['role']}, plugin {r['loaded']} loaded, {r['installed']} installed, at rest",
        f"1. SendMessage to {name}: {message}",
        f"2. Wait for its reply `{ready}`.",
        f"3. Stop it: {stop}.",
    ]
    if member and member[0] == "coordinator":
        out.append(
            "4. Start it fresh in the human's own terminal: `wclaude --start --fresh` (the main "
            "companion runs in the human's window, never in the background)."
        )
    elif member:
        role = member[0]
        out.append(
            f"4. Start it fresh: `python3 {SCRIPTS}/start.py launch {role} --fresh` (background, "
            f"first message: read your state); in the human's own terminal instead: "
            f"`wclaude --start --role {role} --fresh`."
        )
    else:
        out.append(
            f"4. Start it fresh in its folder: `cd {r['cwd']} && claude --name {name} "
            f'"{startlib.READ_STATE}"`.'
        )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--due", action="store_true")
    pl = sub.add_parser("plan")
    pl.add_argument("name")
    pl.add_argument("--from", dest="start")
    args = parser.parse_args(argv)
    try:
        rows = roll_call()
    except worker_launch.LaunchError as exc:
        print(f"session_refresh: {exc}", file=sys.stderr)
        return 1
    if args.verb == "plan":
        try:
            print(plan(args.name, rows, args.start))
        except PlanError as exc:
            print(f"session_refresh: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.due:
        rows = [r for r in rows if r["due"]]
    if args.json:
        json.dump(rows, sys.stdout, indent=2)
        print()
    else:
        for r in rows:
            print(line(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
