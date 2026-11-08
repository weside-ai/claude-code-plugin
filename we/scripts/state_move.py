#!/usr/bin/env python3
"""Move a crew's board family out of a shared folder into the crew's own ``state_dir``.

Usage:
  state_move.py [--from DIR] [--board FILE] [--apply]

The source is the crew's ``board.file`` (``--board FILE`` names it once the crew file no longer
does); the target folder is the crew's ``state_dir`` (``crew.state_dir``). The board family is the
board file, its lock (``<name>.lock``), every ``<stem>-*.jsonl`` beside it, its freeze flag
(``board_freeze.flag_path``) and its crew stamp (``crew.stamp_path``); each target takes the stem
``board`` (``acme-board-answers.jsonl`` → ``board-answers.jsonl``, ``acme-board-freeze.json`` →
``freeze.json``).

Without ``--apply`` it prints one line ``<source> -> <target>`` per file and changes nothing.
With ``--apply`` it takes the board lock, copies each file, checks the copy by sha256, then renames
each source to ``<name>.migrated-<YYYY-MM-DD>``; it deletes nothing (deleting data is the owner's
call). A failed copy or hash removes that partial target and leaves every source untouched; a
failed rename after good copies leaves both and exits 1 naming them.

Refused (exit 2, the reason named): the crew sets no ``state_dir``; the board is already in it;
a target exists; a live session of this crew runs (``claude agents --json``, its ``cwd`` resolving
to this crew file; the calling session, ``CLAUDE_CODE_SESSION_ID``, does not count); the session
list cannot be read; the board lock is held. After the move the crew drops ``board.file``, so its
sessions resolve ``<state_dir>/board.json``; the script says so.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board_freeze
import crew as crewlib


class RefusedError(Exception):
    """A reason not to move; nothing was changed."""


def family(board: Path) -> list[Path]:
    """Every existing file of the board family of ``board``."""
    stem = board.stem
    found = [board, board.with_name(board.name + ".lock")]
    found += sorted(board.parent.glob(f"{stem}-*.jsonl"))
    found += [board_freeze.flag_path(board), crewlib.stamp_path(board)]
    seen: list[Path] = []
    for path in found:
        if path.is_file() and path not in seen:
            seen.append(path)
    return seen


def target_name(source: Path, board: Path) -> str:
    """``source``'s name with the board's stem renamed to ``board``."""
    if source == board:
        return crewlib.BOARD_NAME
    if source == board.with_name(board.name + ".lock"):
        return crewlib.BOARD_NAME + ".lock"
    if source == board_freeze.flag_path(board):
        return board_freeze.FLAG_NAME
    if source == crewlib.stamp_path(board):
        return crewlib.CREW_ID_NAME
    return "board" + source.name[len(board.stem) :]


def plan(crew_path: Path, crew: dict, board_arg: str | None, env=None) -> list[tuple[Path, Path]]:
    """(source, target) per file; raises RefusedError."""
    own = (crew or {}).get("state_dir")
    if not (isinstance(own, str) and own.strip()):
        raise RefusedError(
            f"{crew_path} sets no state_dir: name the crew's own folder there first"
        )
    folder = crewlib.state_dir(crew_path, crew, env).resolve()
    if board_arg:
        board = Path(board_arg).expanduser().resolve()
    else:
        named = ((crew or {}).get("board") or {}).get("file")
        if not (isinstance(named, str) and named.strip()):
            raise RefusedError(
                f"{crew_path} names no board.file: pass --board FILE (the board to move)"
            )
        board = crewlib.board_file(crew_path, crew, env).resolve()
    if board.parent == folder and board.name == crewlib.BOARD_NAME:
        raise RefusedError(f"{board} already is the crew's board in {folder}: nothing to move")
    pairs = [(src, folder / target_name(src, board)) for src in family(board)]
    if not pairs:
        raise RefusedError(f"no file of the board family of {board} exists")
    taken = [str(dst) for _, dst in pairs if dst.exists()]
    if taken:
        raise RefusedError(f"target exists: {', '.join(taken)}")
    return pairs


def live_sessions(crew_path: Path, env=None) -> list[str]:
    """Names of live sessions of this crew other than the caller; raises RefusedError when the list
    cannot be read."""
    env = os.environ if env is None else env
    try:
        run = subprocess.run(
            ["claude", "agents", "--json"], capture_output=True, text=True, timeout=20, check=False
        )
        rows = json.loads(run.stdout) if run.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        rows = None
    if not isinstance(rows, list):
        raise RefusedError("the session list (`claude agents --json`) cannot be read")
    me = str(env.get("CLAUDE_CODE_SESSION_ID") or "")
    want = crew_path.resolve()
    names = []
    for row in rows:
        if not isinstance(row, dict) or (me and row.get("sessionId") == me):
            continue
        cwd = row.get("cwd")
        found = crewlib.find(cwd) if cwd and os.path.isdir(cwd) else None
        if found is not None and Path(found).resolve() == want:
            names.append(str(row.get("name") or row.get("sessionId") or "?"))
    return names


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply(pairs: list[tuple[Path, Path]], board: Path, today: str) -> list[str]:
    """Copy, verify, rename under the board lock; returns the lines to print."""
    lock = board.with_name(board.name + ".lock")
    fd = os.open(str(lock), os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RefusedError(
                f"the board lock {lock} is held: a session writes the board"
            ) from None
        pairs[0][1].parent.mkdir(parents=True, exist_ok=True)
        done: list[Path] = []
        for src, dst in pairs:
            try:
                shutil.copy2(src, dst)
                ok = _sha(src) == _sha(dst)
            except OSError:
                ok = False
            if not ok:
                for path in [*done, dst]:
                    path.unlink(missing_ok=True)
                raise RuntimeError(f"copy of {src} to {dst} failed its check; nothing moved")
            done.append(dst)
        lines, stuck = [], []
        for src, dst in pairs:
            gone = src.with_name(f"{src.name}.migrated-{today}")
            try:
                src.rename(gone)
                lines.append(f"{src} -> {dst} (source kept as {gone.name})")
            except OSError:
                stuck.append(f"{src} (copy at {dst})")
        if stuck:
            raise RuntimeError(f"copied but not renamed, both stand: {', '.join(stuck)}")
        return lines
    finally:
        os.close(fd)


def main(argv=None, env=None, today: str | None = None) -> int:
    p = argparse.ArgumentParser(prog="state_move.py", description=__doc__.splitlines()[0])
    p.add_argument("--from", dest="start", help="the repo whose crew moves (default: the cwd)")
    p.add_argument("--board", help="the board to move (default: the crew's board.file)")
    p.add_argument("--apply", action="store_true", help="move; without it only list")
    args = p.parse_args(argv)
    env = os.environ if env is None else env
    try:
        crew_path, crew = crewlib.find_and_load(args.start)
        if crew_path is None:
            raise RefusedError("no crew file found: run it in the crew's repo or pass --from DIR")
        pairs = plan(crew_path, crew, args.board, env)
        if not args.apply:
            for src, dst in pairs:
                print(f"{src} -> {dst}")
            print("dry run: nothing moved; --apply moves")
            return 0
        live = live_sessions(crew_path, env)
        if live:
            raise RefusedError(
                f"live sessions of this crew run: {', '.join(live)}; stop them first"
            )
        board = pairs[0][0]
        lines = apply(pairs, board, today or datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    except (RefusedError, crewlib.CrewError) as exc:
        print(f"state_move.py: refused: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"state_move.py: {exc}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    print(f"moved; now drop board.file from {crew_path}, so the crew resolves its state_dir")
    return 0


if __name__ == "__main__":
    sys.exit(main())
