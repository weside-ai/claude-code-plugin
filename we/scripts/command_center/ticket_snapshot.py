#!/usr/bin/env python3
"""The ticket snapshot beside the board: its one writer and its one reader.

Usage:
  ticket_snapshot.py write [--board FILE]     ticket MCP JSON on stdin; prints the file it wrote

The ticket system is read by a session through its ticket MCP (the coordinator on its tick); this
script calls no ticket system. `write` takes that answer on stdin and writes
`<board stem>-tickets.json` beside the board (`--board`, else the crew's board) in one atomic step:
a temp file in the same folder, then `os.replace`, so a reader sees the old file or the new one,
never half of one. The file is `{"schema_version": 2, "@taken": <UTC now>, "stories": {<KEY>:
<record>…}, "epics": {<KEY>: <record>…}}`; a record carries `status` and, where the answer has
them, `summary`, `epic` (the parent's key), `components`, `owners` (the `owner-*` labels),
`priority` and `updated` (UTC). There is no other write path: `ticket_fetch.py` (the scheduled
fetch from the ticket system's REST search) calls `write` as a function.

Input shapes (`records`): an object `{KEY: status name}`; a list of issues `[{key, fields: {status:
{name}, summary, parent: {key}, components: [{name}], labels, priority: {name}, updated,
issuetype: {name}}}]` or `[{key, status}]`; or `{"issues": [...]}` as a search answer carries it.
An issue whose `issuetype` is `Epic` goes to `epics`, every other one to `stories`. Anything else is
refused with exit 2 and nothing is written.

`read_records` (`(stories, epics, header line, fresh)`) and `read` (the stories' key → status, the
Zentrale's and the standup's reader: `(mapping, header line, fresh)`). Without a file the line is
`tickets: not read (no snapshot)`, a file of another `schema_version` is `tickets: not read
(schema_version N)`; a snapshot whose `@taken` is older than `flow.tickets_stale_min` (`crew.py`,
default 45), or that has none, is `tickets: stale since <@taken>` and is not fresh: its stories
are not shown as current.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import crew as crew_mod  # noqa: E402
import flow_intervals as fi  # noqa: E402

SCHEMA_VERSION = 2
ISO = "%Y-%m-%dT%H:%M:%SZ"
RESERVED = ("schema_version", "@taken")
EPIC = "epic"  # issuetype name, case-insensitive


def path_for(board: Path) -> Path:
    return board.with_name(f"{board.stem}-tickets.json")


def _name(value):
    return value.get("name") if isinstance(value, dict) else value


def _record(item: dict) -> dict:
    """One issue's record: `status` always, the other fields where the answer carries them."""
    fields = item.get("fields") or {}
    status = fields.get("status")
    name = _name(status if status is not None else item.get("status"))
    if not isinstance(name, str):
        raise ValueError(f"{item['key']}: no status name")
    rec = {"status": name}
    if isinstance(fields.get("summary"), str):
        rec["summary"] = fields["summary"]
    parent = fields.get("parent")
    if isinstance(parent, dict) and isinstance(parent.get("key"), str):
        rec["epic"] = parent["key"]
    if isinstance(fields.get("components"), list):
        rec["components"] = [n for n in map(_name, fields["components"]) if isinstance(n, str)]
    if isinstance(fields.get("labels"), list):
        rec["owners"] = [
            x for x in fields["labels"] if isinstance(x, str) and x.startswith("owner-")
        ]
    if isinstance(_name(fields.get("priority")), str):
        rec["priority"] = _name(fields["priority"])
    updated = fields.get("updated")  # Jira writes `+0100`; Python 3.9 reads only `+01:00`
    updated = (
        fi.parse_ts(re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", updated))
        if isinstance(updated, str)
        else None
    )
    if updated is not None:
        rec["updated"] = updated.astimezone(timezone.utc).strftime(ISO)
    return rec


def records(data) -> tuple:
    """`(stories, epics)`, each `{KEY: record}`, from the ticket MCP's answer (module docstring §
    Input shapes)."""
    if isinstance(data, dict) and isinstance(data.get("issues"), list):
        data = data["issues"]
    if isinstance(data, dict):
        out = {k: v for k, v in data.items() if k not in RESERVED}
        if all(isinstance(k, str) and isinstance(v, str) for k, v in out.items()):
            return {k: {"status": v} for k, v in out.items()}, {}
        raise ValueError("an object of key → status name is needed")
    if isinstance(data, list):
        stories, epics = {}, {}
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("key"), str):
                raise ValueError("an issue without a key")
            kind = _name((item.get("fields") or {}).get("issuetype"))
            is_epic = isinstance(kind, str) and kind.casefold() == EPIC
            (epics if is_epic else stories)[item["key"]] = _record(item)
        return stories, epics
    raise ValueError("no object and no list of issues")


def write(board: Path, stories: dict, now: datetime, epics: dict | None = None) -> Path:
    """The one write: a temp file beside the target, then `os.replace`."""
    target = path_for(board)
    doc = {
        "schema_version": SCHEMA_VERSION,
        "@taken": now.strftime(ISO),
        "stories": stories,
        "epics": epics or {},
    }
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target


def _records_of(value) -> dict:
    if not isinstance(value, dict):
        return {}
    return {
        k: v for k, v in value.items() if isinstance(v, dict) and isinstance(v.get("status"), str)
    }


def _load(path: Path | None) -> tuple:
    """(the snapshot's object or None, why not read)."""
    if path is None or not path.is_file():
        return None, "no snapshot"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, type(exc).__name__
    if not isinstance(data, dict):
        return None, "no object"
    if data.get("schema_version") != SCHEMA_VERSION:
        return None, f"schema_version {data.get('schema_version')}"
    return data, ""


def read_records(path: Path | None, until: datetime, stale_min: float) -> tuple:
    """(stories, epics, header line, fresh); `stale_min` is the crew's flow.tickets_stale_min."""
    data, why = _load(path)
    if data is None:
        return {}, {}, f"tickets: not read ({why})", False
    stories, epics = _records_of(data.get("stories")), _records_of(data.get("epics"))
    taken = fi.parse_ts(data.get("@taken"))
    if taken is None:
        return stories, epics, "tickets: stale since unknown (no @taken)", False
    if until - taken > timedelta(minutes=stale_min):
        return stories, epics, f"tickets: stale since {taken.strftime(ISO)}", False
    minutes = int((until - taken).total_seconds() // 60)
    return stories, epics, f"tickets: taken {taken.strftime(ISO)} ({minutes} min old)", True


def read(path: Path | None, until: datetime, stale_min: float) -> tuple:
    """(the stories' key → status name, header line, fresh)."""
    stories, _epics, line, fresh = read_records(path, until, stale_min)
    return {k: v["status"] for k, v in stories.items()}, line, fresh


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
        stories, epics = records(json.load(sys.stdin))
    except ValueError as exc:
        print(f"ticket_snapshot: refused, nothing written ({exc})", file=sys.stderr)
        return 2
    board, _ = locate(args.board)
    if board is None:
        print("ticket_snapshot: no board (no crew, no --board), nothing written", file=sys.stderr)
        return 2
    print(write(board, stories, datetime.now(timezone.utc), epics))
    return 0


if __name__ == "__main__":
    sys.exit(main())
