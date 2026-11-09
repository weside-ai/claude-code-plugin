#!/usr/bin/env python3
"""The crew's main companion (``roles.coordinator``): plan its start, check a started session.

Usage:
  start.py plan [--from DIR] [--fresh]   one line "<name>\\t<pin 0|1>\\t<workplace>\\t<session id or empty>"
                                         for ``wclaude --start``; exit 1 (reason on stderr) without a
                                         crew, without a coordinator, or while the coordinator runs
  start.py check [--from DIR]            in the session (``/we:start``): one line per check of
                                         WESIDE_COMPANION, WE_ROLE and the pin against the crew, exit 1
                                         on a mismatch
  start.py restore [--from DIR]          the crew's ``launch.restore`` command, exit 1 when unset

The crew decides, never this code: who starts (``roles.coordinator``), pinned or not
(``members.<slug>.pin``), where (``members.<slug>.workplace``), the restore command
(``launch.restore``). The last session is the newest transcript under
``<config>/projects/<workplace slug>/`` whose title or agent name is the coordinator's name
(``--name`` writes both); ``--fresh`` skips the lookup. Python stdlib only, 3.9.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

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


def coordinator(start: str | Path | None) -> tuple[Path, dict[str, Any], str, dict[str, Any]]:
    path = crewlib.find(start)
    if path is None:
        raise StartError("no .weside/crew.json here; run /we:setup")
    try:
        crew = crewlib.load(path)
    except crewlib.CrewError as exc:
        raise StartError(str(exc)) from exc
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


def plan(start: str | Path | None, fresh: bool, env: Any = None, sessions: Any = None) -> str:
    path, crew, slug, member = coordinator(start)
    name = member["name"]
    if running(name, sessions):
        raise StartError(
            f"{name} runs already (claude agents); attach to it instead of starting a second one"
        )
    try:
        place = crewlib.workplace_path(path, crew, slug)
    except crewlib.CrewError as exc:
        raise StartError(str(exc)) from exc
    sid = "" if fresh else last_session(name, place, projects_dir(env))
    return "\t".join((name, "1" if member.get("pin") else "0", str(place), sid))


def check(start: str | Path | None, env: Any = None) -> tuple[list[str], bool]:
    env = os.environ if env is None else env
    _, _, _, member = coordinator(start)
    name, want_pin = member["name"], bool(member.get("pin"))
    pinned = bool(env.get("CLAUDE_CONFIG_DIR"))
    rows = [
        (
            env.get("WESIDE_COMPANION") == name,
            f"companion {env.get('WESIDE_COMPANION') or '(none)'}, crew: {name}",
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
            print(plan(start, "--fresh" in rest))
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
