#!/usr/bin/env python3
"""The ticket snapshot beside the board: its one writer and its one reader.

Usage:
  ticket_snapshot.py write [--board FILE]     ticket MCP JSON on stdin; prints the file it wrote

The ticket system is read by a session through its ticket MCP (the coordinator on its tick); this
script calls no ticket system. `write` takes that answer on stdin and writes
`<board stem>-tickets.json` beside the board (`--board`, else the crew's board) in one atomic step:
a temp file in the same folder, then `os.replace`, so a reader sees the old file or the new one,
never half of one. The file is `{"schema_version": 1, "@taken": <UTC now>, <KEY>: <status name>…}`.
There is no other write path: `ticket_fetch.py` (the scheduled fetch from the ticket system's REST
search) calls `write` as a function.

Input shapes (`stories`): an object `{KEY: status name}`; a list of issues `[{key, fields: {status:
{name}}}]` or `[{key, status}]`; or `{"issues": [...]}` as a search answer carries it. Anything
else is refused with exit 2 and nothing is written.

`read` (the Zentrale's reader, `open_ends.py`): `(mapping, header line, fresh)`. Without a file the
line is `tickets: not read (no snapshot)`; a snapshot whose `@taken` is older than
`flow.tickets_stale_min` (`crew.py`, default 45), or that has none, is `tickets: stale since <@taken>` and is not fresh: its
stories are not shown as current.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import crew as crew_mod  # noqa: E402
import flow_intervals as fi  # noqa: E402

SCHEMA_VERSION = 1
ISO = "%Y-%m-%dT%H:%M:%SZ"
RESERVED = ("schema_version", "@taken")


def path_for(board: Path) -> Path:
    return board.with_name(f"{board.stem}-tickets.json")


def stories(data) -> dict:
    """`{KEY: status name}` from the ticket MCP's answer (module docstring § Input shapes)."""
    if isinstance(data, dict) and isinstance(data.get("issues"), list):
        data = data["issues"]
    if isinstance(data, dict):
        out = {k: v for k, v in data.items() if k not in RESERVED}
        if all(isinstance(k, str) and isinstance(v, str) for k, v in out.items()):
            return out
        raise ValueError("an object of key → status name is needed")
    if isinstance(data, list):
        out = {}
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("key"), str):
                raise ValueError("an issue without a key")
            status = (item.get("fields") or {}).get("status")
            status = status if status is not None else item.get("status")
            name = status.get("name") if isinstance(status, dict) else status
            if not isinstance(name, str):
                raise ValueError(f"{item['key']}: no status name")
            out[item["key"]] = name
        return out
    raise ValueError("no object and no list of issues")


def write(board: Path, mapping: dict, now: datetime) -> Path:
    """The one write: a temp file beside the target, then `os.replace`."""
    target = path_for(board)
    doc = {"schema_version": SCHEMA_VERSION, "@taken": now.strftime(ISO), **mapping}
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target


def read(path: Path | None, until: datetime, stale_min: float) -> tuple:
    # stale_min: the crew's flow.tickets_stale_min
    """(mapping key → status name, header line, fresh)."""
    if path is None or not path.is_file():
        return {}, "tickets: not read (no snapshot)", False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, f"tickets: not read ({type(exc).__name__})", False
    if not isinstance(data, dict):
        return {}, "tickets: not read (no object)", False
    taken = fi.parse_ts(data.get("@taken"))
    mapping = {k: v for k, v in data.items() if k not in RESERVED and isinstance(v, str)}
    if taken is None:
        return mapping, "tickets: stale since unknown (no @taken)", False
    if until - taken > timedelta(minutes=stale_min):
        return mapping, f"tickets: stale since {taken.strftime(ISO)}", False
    minutes = int((until - taken).total_seconds() // 60)
    return mapping, f"tickets: taken {taken.strftime(ISO)} ({minutes} min old)", True


def locate(board_arg: str | None) -> tuple:
    """`(board file or None, crew or None)` from `--board`, else the crew found from the cwd."""
    try:
        crew_path, crew = crew_mod.find_and_load(Path.cwd())
    except crew_mod.CrewError:
        crew_path, crew = None, None
    board, _ = fi.locate_board(SimpleNamespace(board=board_arg), Path.cwd(), crew_path, crew)
    return board, crew


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ticket_snapshot.py", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write", help="ticket MCP JSON on stdin → <board stem>-tickets.json")
    w.add_argument("--board")
    args = p.parse_args(argv)
    try:
        mapping = stories(json.load(sys.stdin))
    except ValueError as exc:
        print(f"ticket_snapshot: refused, nothing written ({exc})", file=sys.stderr)
        return 2
    board, _ = locate(args.board)
    if board is None:
        print("ticket_snapshot: no board (no crew, no --board), nothing written", file=sys.stderr)
        return 2
    print(write(board, mapping, datetime.now(timezone.utc)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
