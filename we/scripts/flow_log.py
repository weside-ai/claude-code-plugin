#!/usr/bin/env python3
"""The flow log: one JSONL file per day, the one owner of its path and its line format.

Usage:
  flow_log.py [--log-dir DIR] [--tz TZ] append '<json object>'   prints the file it wrote to
  flow_log.py [--log-dir DIR] [--tz TZ] newest                    prints `<ts> <age_s>`, exit 1 if none

Path: ``<flow.log_dir>/sampler-<YYYY-MM-DD>.jsonl``, the day of the line's ``ts`` in the crew's
``sla.tz`` (a crew in Europe/Berlin writes Berlin days). Without ``--log-dir`` / ``--tz`` both come
from the crew in force for the cwd (``crew.py``, ``flow.log_dir`` and ``sla.tz``); an unset
``flow.log_dir`` exits 2.

Writers: the workspace sampler (one ``append`` subprocess per line), ``board.py log`` (the
coordinator's ``correction`` lines). Readers: ``sampler_age.py``, the prompt hook
``hooks/sampler_on_prompt.py`` and the weekly flow report. Every write is one whole line in one
``write`` on a file opened ``O_APPEND``: nothing in the file is ever rewritten.

Line schema (this docstring owns it; the report codes against it). Every line: ``ts`` (UTC ISO,
``YYYY-MM-DDTHH:MM:SSZ``; stamped by ``append`` when absent) and ``type``, one of ``TYPES``:

- ``sample`` (every 300 s): ``interval_s``; ``pod`` {``memory_max``, ``memory_current``,
  ``working_set``: bytes}; ``locks`` {``gates``, ``tests``: {``held``, ``holder``}};
  ``sessions[]`` {``name``, ``session_id``, ``key`` (by ``naming.key`` or null), ``role`` (board
  line, else ``worker`` with a marker, else null), ``status`` (``busy``/``idle``), ``state``,
  ``pid``, ``rss`` (bytes of its process tree)}, a master's entry also ``context`` {``fill``,
  ``compactions_today``, ``strands``, ``missed``, ``missed_ids``}.
- ``heartbeat`` (every 60 s): ``error?``, ``log_error?``.
- ``kill``: ``working_set``, ``root_pid``, ``tree_rss``, ``cwd``, ``command`` (first 140 chars).
- ``blocked`` / ``unblocked``: ``name``, ``key``, ``kind`` (``permission``/``chat``), ``starter``,
  ``waiting_on``, ``since``, ``duration_s`` (``unblocked`` only).
- ``escalated``: ``name``, ``key``, ``kind``, ``outcome`` (``posted``/``returned``/``error``), ``qid?``.
- ``correction``: ``session``, ``kind`` (one lower-case token), ``by``.

``append`` refuses a line whose ``type`` is not in ``TYPES`` or whose ``ts`` is no UTC ISO time; the
fields beyond ``ts`` and ``type`` are the writer's promise, not checked here.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import crew as crew_mod  # noqa: E402  (the one reader of crew.json)

TYPES = ("sample", "heartbeat", "kill", "blocked", "unblocked", "escalated", "correction")
TS_FMT = "%Y-%m-%dT%H:%M:%SZ"
PREFIX = "sampler-"
TAIL_BYTES = 64 * 1024


class FlowLogError(Exception):
    """A refused line or an unusable configuration; `code` is the CLI's exit code."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def _utc_now():
    return datetime.now(timezone.utc)


def parse_ts(text):
    """The aware UTC time of a line's ``ts``, or None."""
    try:
        return datetime.strptime(str(text), TS_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _zone(tz):
    try:
        return ZoneInfo(tz)
    except (ValueError, KeyError, OSError):
        raise FlowLogError(f'tz "{tz}" is no time zone') from None


def path_for(log_dir, ts, tz):
    """The file a line stamped ``ts`` (aware) belongs in."""
    day = ts.astimezone(_zone(tz)).strftime("%Y-%m-%d")
    return Path(log_dir).expanduser() / f"{PREFIX}{day}.jsonl"


def append(log_dir, record, tz, now=None):
    """Append one line; returns the file's path. Refuses (FlowLogError) before any write."""
    if not isinstance(record, dict):
        raise FlowLogError("a line is a JSON object")
    if record.get("type") not in TYPES:
        raise FlowLogError(f"type {record.get('type')!r} is not one of {', '.join(TYPES)}")
    record = dict(record)
    if "ts" not in record:
        record["ts"] = (now or _utc_now()).astimezone(timezone.utc).strftime(TS_FMT)
    ts = parse_ts(record["ts"])
    if ts is None:
        raise FlowLogError(f"ts {record['ts']!r} is no UTC ISO time ({TS_FMT})")
    path = path_for(log_dir, ts, tz)
    line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)
    return path


def _last_ts(path):
    """The ``ts`` of the last whole line of ``path`` that carries one, read from the end in
    ``TAIL_BYTES`` blocks; None for a missing file or one without such a line."""
    try:
        with open(path, "rb") as fh:
            return _tail_ts(fh)
    except OSError:
        return None


def _tail_ts(fh):
    pos, tail = fh.seek(0, os.SEEK_END), b""
    while pos > 0:
        step = min(TAIL_BYTES, pos)
        pos -= step
        fh.seek(pos)
        tail = fh.read(step) + tail
        parts = tail.split(b"\n")
        # the first part may be cut by the block edge unless we are at the file's start
        whole = parts if pos == 0 else parts[1:]
        for raw in reversed(whole):
            try:
                item = json.loads(raw.decode("utf-8"))
            except ValueError:
                continue
            if isinstance(item, dict) and parse_ts(item.get("ts")) is not None:
                return item["ts"]
        tail = parts[0] if pos else b""
    return None


def newest(log_dir, tz, now=None):
    """(``ts``, age in whole seconds) of the newest line in today's or yesterday's file (zone
    ``tz``), or None when neither holds a line."""
    now = now or _utc_now()
    found = []
    for back in (0, 1):
        ts = _last_ts(path_for(log_dir, now - timedelta(days=back), tz))
        if ts is not None:
            found.append(ts)
    if not found:
        return None
    ts = max(found, key=parse_ts)
    return ts, int((now - parse_ts(ts)).total_seconds())


def configured(cwd=None):
    """(``flow.log_dir`` expanded or None, ``sla.tz``, the merged ``flow`` block, the crew) of
    the crew in force for ``cwd``; an unreadable crew counts as none, and the loader's stderr
    notes are swallowed (a hook calls this on every prompt)."""
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            _, crew = crew_mod.find_and_load(cwd)
        except crew_mod.CrewError:
            crew = None
    crew = crew or crew_mod.DEFAULTS
    return (*settings(crew), crew)


def settings(crew):
    """(``flow.log_dir`` expanded or None, ``sla.tz``, the merged ``flow`` block) of a loaded
    crew: the one place these defaults are applied."""
    flow = {**crew_mod.DEFAULTS["flow"], **(crew.get("flow") or {})}
    tz = (crew.get("sla") or {}).get("tz") or crew_mod.DEFAULTS["sla"]["tz"]
    log_dir = flow.get("log_dir")
    return (Path(log_dir).expanduser() if log_dir else None), tz, flow


def main(argv=None):
    p = argparse.ArgumentParser(prog="flow_log.py", description="The flow log's one writer.")
    p.add_argument("--log-dir", dest="log_dir")
    p.add_argument("--tz")
    verbs = p.add_subparsers(dest="verb", required=True)
    a = verbs.add_parser("append", help="append one JSON line")
    a.add_argument("line")
    verbs.add_parser("newest", help="the newest line's ts and age")
    args = p.parse_args(argv)
    try:
        log_dir, tz = args.log_dir, args.tz
        if log_dir is None or tz is None:
            crew_dir, crew_tz, _flow, _crew = configured()
            log_dir = log_dir or crew_dir
            tz = tz or crew_tz
        if not log_dir:
            raise FlowLogError("flow.log_dir is unset (crew) and no --log-dir given", 2)
        if args.verb == "append":
            try:
                record = json.loads(args.line)
            except ValueError:
                raise FlowLogError("the line is no JSON") from None
            print(append(log_dir, record, tz))
            return 0
        found = newest(log_dir, tz)
        if found is None:
            print(f"no line in {log_dir}")
            return 1
        print(f"{found[0]} {found[1]}")
        return 0
    except FlowLogError as exc:
        print(f"flow_log.py: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
