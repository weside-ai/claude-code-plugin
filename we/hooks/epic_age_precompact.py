#!/usr/bin/env python3
"""PreCompact hook: flag a master whose epic's Updates Log is stale before it compacts.

Only for a master (``crew.role_of_session`` = ``master``) in a repo with a crew that loads. Reads
the epic plan's newest Updates Log date (``scripts/epic_state.py``; board line as in
``compact_on_start.py``); when it is older than yesterday in the crew's ``sla.tz`` (or the plan has
no Updates Log), writes the flag ``<board dir>/epic-age/<session_id>``.
``compact_on_start.py`` reads and deletes it and opens with "Epic update first". No timer,
no other output.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import compact_on_start as cos
import crew as crewlib
import epic_state


def _master_crew(hook_input: dict, env: Any) -> tuple[Path, dict] | None:
    """(crew path, crew) when this session is a master in a repo with a crew, else None."""
    try:
        crew_path, crew = crewlib.find_and_load(hook_input.get("cwd") or os.getcwd())
    except crewlib.CrewError:
        return None
    if crew is None or crew_path is None:
        return None
    return (
        (crew_path, crew) if crewlib.role_of_session(crew, env, hook_input) == "master" else None
    )


def flag(hook_input: dict, env: Any, runner: cos.Runner = subprocess.run) -> Path | None:
    """The flag file written, or None."""
    session_id = str(hook_input.get("session_id") or "")
    found = _master_crew(hook_input, env) if session_id and "/" not in session_id else None
    if found is None:
        return None
    crew_path, crew = found
    cwd = Path(str(hook_input.get("cwd") or os.getcwd()))
    board = cos.load_board(cos.board_path(crew))
    line = cos.find_session(board, session_id, "", cos.tmux_window(env, runner)) if board else None
    roots = list(dict.fromkeys([cos.git_root(cwd, runner) or cwd, crew_path.parent.parent]))
    try:
        plan = epic_state.resolve(line or {}, roots)
        log = epic_state.updates_log(plan.read_text(encoding="utf-8"))
    except (epic_state.EpicError, OSError):
        return None
    if not epic_state.is_stale(log[-1][0] if log else None, str(crew["sla"]["tz"])):
        return None
    target = cos.board_path(crew).parent / cos.FLAG_DIR / session_id
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(plan) + "\n", encoding="utf-8")
    except OSError:
        return None
    return target


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        data = {}
    flag(data if isinstance(data, dict) else {}, os.environ)
    return 0


if __name__ == "__main__":
    sys.exit(main())
