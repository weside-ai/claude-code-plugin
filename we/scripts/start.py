#!/usr/bin/env python3
"""The crew's main companion (``roles.coordinator``): plan its start, check a started session.

Usage:
  start.py plan [--from DIR] [--fresh] [--role ROLE]
                                         one line "<name>\t<pin 0|1>\t<workplace>\t<human>\t<role>\t
                                         <session id or empty>" for ``wclaude --start``; exit 1
                                         (reason on stderr) without a crew, without the role's member,
                                         for a role the human does not run, or while it runs
  start.py check [--from DIR]            in the session (``/we:start``): one line per check of the
                                         human, WESIDE_COMPANION, WE_ROLE and the pin against the
                                         crew, exit 1 on a mismatch
  start.py restore [--from DIR]          the crew's ``launch.restore`` command, exit 1 when unset

The crew decides, never this code: whose machine this is (``crew.current_human``: ``WE_HUMAN``,
else ``git config user.email``), what starts here (``humans.<me>.runs``; a crew without ``humans``
runs every role on one machine), which role ``--start`` opens (``--role``, else
``roles.coordinator`` when the human runs it, else the first role key of ``runs``), under which
name (``crew.display_name``), pinned or not (``members.<slug>.pin``), where
(``members.<slug>.workplace``), the restore command (``launch.restore``). ``plan`` names the
human's other roles on stderr, one ``wclaude --start --role <key>`` each. The last session is the
newest transcript under ``<config>/projects/<workplace slug>/`` whose title or agent name is the
display name (``--name`` writes both); ``--fresh`` skips the lookup. Python stdlib only, 3.9.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import claude_home  # noqa: E402
import crew as crewlib  # noqa: E402
import worker_launch  # noqa: E402

HEAD_BYTES = 64 * 1024
TAIL_BYTES = 256 * 1024
MAX_TRANSCRIPTS = 200


class StartError(Exception):
    pass


class Target(NamedTuple):
    """What ``plan`` and ``check`` start or check: the human, the role and its member."""

    path: Path
    crew: dict
    human: str
    human_entry: dict
    role: str
    slug: str
    member: dict
    name: str


def _crew(start: str | Path | None) -> tuple[Path, dict[str, Any]]:
    path = crewlib.find(start)
    if path is None:
        raise StartError("no .weside/crew.json here; run /we:setup")
    try:
        return path, crewlib.load(path)
    except crewlib.CrewError as exc:
        raise StartError(str(exc)) from exc


def startable(crew: dict[str, Any], human: str) -> list[str]:
    """The roles ``human`` runs that a session opens as (``masters`` is no session of its own)."""
    return [r for r in crewlib.runs(crew, human) if r != crewlib.MASTERS]


def target(start: str | Path | None, role: str | None = None, env: Any = None) -> Target:
    env = os.environ if env is None else env
    path, crew = _crew(start)
    try:
        found = crewlib.current_human(crew, env, path.parent)
    except crewlib.CrewError as exc:
        raise StartError(str(exc)) from exc
    if found is None:
        raise StartError(
            "several humans and none is you: set WE_HUMAN=<slug> or git config user.email to "
            f"one of humans.*.email ({', '.join(crewlib.humans(crew))})"
        )
    human, entry = found
    mine = startable(crew, human)
    if role is None and not crewlib.several_humans(crew):
        role = "coordinator"  # one human: the main companion is the coordinator, as ever
    elif role is None:
        role = "coordinator" if "coordinator" in mine else next(iter(mine), None)
        if role is None:
            raise StartError(f"humans.{human}.runs names no role to start")
    elif role not in mine and crewlib.several_humans(crew):
        raise StartError(f"{human} does not run {role} (humans.{human}.runs: {', '.join(mine)})")
    slug = (crew.get("roles") or {}).get(role, role if role not in crewlib.ROLE_KEYS else "")
    member = (crew.get("members") or {}).get(slug or "")
    if not member:
        raise StartError(f"{path}: roles.{role} names no member")
    name = crewlib.display_name(crew, role, human) or member["name"]
    return Target(path, crew, human, entry, role, slug, member, name)


def coordinator(start: str | Path | None) -> tuple[Path, dict[str, Any], str, dict[str, Any]]:
    path, crew = _crew(start)
    slug = (crew.get("roles") or {}).get("coordinator")
    member = (crew.get("members") or {}).get(slug or "")
    if not member:
        raise StartError(f"{path}: roles.coordinator names no member")
    return path, crew, slug, member


def projects_dir(env: Any = None) -> Path:
    env = os.environ if env is None else env
    return claude_home.config_dir(env) / "projects"


def project_slug(cwd: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def _holds_name(path: Path, needle: re.Pattern) -> bool:
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            head = fh.read(HEAD_BYTES)
            if needle.search(head):
                return True
            if size > HEAD_BYTES:
                fh.seek(max(HEAD_BYTES, size - TAIL_BYTES))
                return bool(needle.search(fh.read()))
    except OSError:
        return False
    return False


def last_session(name: str, workplace: Path, projects: Path) -> str:
    folder = projects / project_slug(workplace)
    try:
        files = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return ""
    quoted = re.escape(json.dumps(name)[1:-1]).encode()
    needle = re.compile(rb'"(?:customTitle|agentName)":\s*"' + quoted + rb'"')
    for path in files[:MAX_TRANSCRIPTS]:
        if _holds_name(path, needle):
            return path.stem
    return ""


def running(name: str, sessions: Any = None) -> bool:
    """A live session of that name (a ``(N)`` suffix is the same companion twice). The list comes from
    ``worker_launch.sessions()``, the one reader of ``claude agents --json``; a list that cannot be
    read refuses the start (``StartError``) rather than risk a second main companion."""
    try:
        rows = (sessions or worker_launch.sessions)()
    except worker_launch.LaunchError as exc:
        raise StartError(
            f"cannot tell whether {name} runs ({exc}); start it by hand or retry"
        ) from exc
    return any(
        r.get("pid") and re.sub(r" \(\d+\)$", "", r.get("name") or "") == name for r in rows
    )


def plan(
    start: str | Path | None,
    fresh: bool,
    env: Any = None,
    sessions: Any = None,
    role: str | None = None,
) -> str:
    t = target(start, role, env)
    if running(t.name, sessions):
        raise StartError(
            f"{t.name} runs already (claude agents); attach to it instead of starting a second one"
        )
    try:
        place = crewlib.workplace_path(t.path, t.crew, t.slug)
    except crewlib.CrewError as exc:
        raise StartError(str(exc)) from exc
    sid = "" if fresh else last_session(t.name, place, projects_dir(env))
    return "\t".join(
        (t.name, "1" if t.member.get("pin") else "0", str(place), t.human, t.role, sid)
    )


def others(start: str | Path | None, role: str | None = None, env: Any = None) -> list[str]:
    """One line per further role the human runs: how to start it."""
    t = target(start, role, env)
    if not crewlib.several_humans(t.crew):
        return []
    return [
        f"{t.human} also runs {r} ({crewlib.display_name(t.crew, r, t.human) or r}): "
        f"wclaude --start --role {r}"
        for r in startable(t.crew, t.human)
        if r != t.role
    ]


def check(start: str | Path | None, env: Any = None) -> tuple[list[str], bool]:
    env = os.environ if env is None else env
    try:
        t = target(start, str(env.get("WE_ROLE_ID") or "").strip() or None, env)
    except StartError as exc:
        return [f"FAIL  human: {exc}"], False
    want_pin = bool(t.member.get("pin"))
    pinned = bool(env.get("CLAUDE_CONFIG_DIR"))
    rows = [
        (
            True,
            f"human {t.human} ({t.human_entry['name']}), runs "
            + ", ".join(crewlib.runs(t.crew, t.human)),
        ),
        (
            env.get("WESIDE_COMPANION") == t.name,
            f"companion {env.get('WESIDE_COMPANION') or '(none)'}, crew: {t.name}",
        ),
        (
            env.get("WE_ROLE") == "master",
            f"WE_ROLE {env.get('WE_ROLE') or '(unset)'}, wanted: master",
        ),
        (
            pinned == want_pin,
            f"pin {'yes' if pinned else 'no'}, crew: {'yes' if want_pin else 'no'}"
            + ("" if pinned == want_pin else f" — /we:pin {'on' if want_pin else 'off'}"),
        ),
    ]
    return [("ok    " if ok else "FAIL  ") + text for ok, text in rows], all(ok for ok, _ in rows)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("plan", "check", "restore"):
        print(__doc__, file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    start = rest[rest.index("--from") + 1] if "--from" in rest[:-1] else None
    try:
        if cmd == "plan":
            role = rest[rest.index("--role") + 1] if "--role" in rest[:-1] else None
            print(plan(start, "--fresh" in rest, role=role))
            for line in others(start, role):
                print(f"wclaude: {line}", file=sys.stderr)
            return 0
        if cmd == "check":
            lines, ok = check(start)
            print("\n".join(lines))
            return 0 if ok else 1
        path, crew, _, _ = coordinator(start)
        command = (crew.get("launch") or {}).get("restore")
        if not command:
            print(f"start: {path} sets no launch.restore", file=sys.stderr)
            return 1
        print(command)
        return 0
    except StartError as exc:
        print(f"start: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
