#!/usr/bin/env python3
"""The crew view: who of the crew runs, on what, since when, waiting on whom, with which plugin.

Read-only, one verb: this script reads `claude agents --json`, the board file and the plugin
installs, and prints; it writes no file and sends nothing. The Zentrale (`command_center/zentrale.py`,
the /board pane's **Zentrale** button) shows its sessions as section Working; a later web front
reads the same document.

Usage: crew_view.py [--json] [--board FILE]

A session is live when its process runs: `worker_supervisor.lives`, the test `we-worker status`
marks `exited(...)` by. Each live session appears once (two rows with one session id: the newest
`startedAt`). Role and loaded plugin version come from `session_refresh.roll_call`; a worker's
starter is the one `roll_call` counts it under (launcher marker `starter`/`lead`, else its timer
file). The board line is the one with the session's `session_id`, else its `name`.

Per session (`sessions[]`, flat, in display order):
- `name`, `session_id`, `kind` (`background`/`interactive`), `role`, `state` (`busy`/`idle`/`blocked`)
- `doing`: the board line's `now`, else `topic`, else its `keys` joined; `keys`
- `waiting_on`: the board line's `waiting_on`; `blocked_kind`: its `blocked.kind`
  (`permission`/`chat`), or `permission` for a row blocked on a prompt with no board mark
- `since`: when the current state began (`blocked.since`, else the line's `since` while it waits,
  else its `updated_at`, else the process start), ISO UTC; `age_s` seconds from then to `generated_at`
- `plugin`: the version the process loaded (`?` unknown)
- `model`: the model id the session's transcript shows (`transcript.session_model`), null unknown
- `starter`: the starter's name for a worker, null otherwise; `group`: the name of the session it
  is listed under: its own for a non-worker, its starter's for a worker whose starter is live,
  `NO_STARTER` for a worker without a live starter (never hidden, never guessed)
- `waits`: true when `waiting_on` or `blocked_kind` is set, or the row is blocked

Order: groups whose head waits first, then the oldest head; inside a group the head, then its
workers, waiting first, then oldest. The `NO_STARTER` group comes last.

`schema_version` counts the document's shape: a field added, removed or renamed raises it
(`test_crew_view.py` holds the field list). `error` names a failed `claude agents --json`; the
document then carries no sessions.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import board as boardlib  # noqa: E402
import session_refresh  # noqa: E402
import worker_launch  # noqa: E402
import worker_supervisor  # noqa: E402

SCHEMA_VERSION = 2
NO_STARTER = "(no starter)"
FIELDS = (
    "name",
    "session_id",
    "kind",
    "role",
    "state",
    "doing",
    "keys",
    "waiting_on",
    "blocked_kind",
    "since",
    "age_s",
    "plugin",
    "model",
    "starter",
    "group",
    "waits",
)


def _ts(text) -> float | None:
    """Epoch seconds of a board stamp (`…T17:23Z`, `…T17:23:41Z`, `…T17:23:41.123Z`)."""
    if not isinstance(text, str) or not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%MZ"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def board_lines(path: Path) -> list[dict]:
    try:
        doc = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    lines = doc.get("sessions") if isinstance(doc, dict) else None
    return [x for x in lines if isinstance(x, dict)] if isinstance(lines, list) else []


def live_rows(rows: list[dict]) -> list[dict]:
    """The live rows, one per session id (the newest start)."""
    by_id: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict) or not worker_supervisor.lives(row):
            continue
        sid = str(row.get("sessionId") or row.get("id") or row.get("pid"))
        had = by_id.get(sid)
        if had is None or (row.get("startedAt") or 0) >= (had.get("startedAt") or 0):
            by_id[sid] = row
    return list(by_id.values())


def _line_for(lines: list[dict], sid: str, name: str) -> dict:
    return next((x for x in lines if sid and x.get("session_id") == sid), None) or next(
        (x for x in lines if x.get("name") == name), {}
    )


def _since(line: dict, row: dict, blocked: dict | None, waiting: bool) -> float | None:
    for value in (
        (blocked or {}).get("since"),
        line.get("since") if waiting else None,
        line.get("updated_at"),
    ):
        at = _ts(value)
        if at is not None:
            return at
    started = row.get("startedAt")
    return float(started) / 1000 if isinstance(started, (int, float)) else None


def entries(rows: list[dict], roll: list[dict], lines: list[dict], now: float) -> list[dict]:
    """One flat entry per live session (module docstring), unordered."""
    by_name = {r["name"]: r for r in roll}
    starter_of = {w: s for r in roll for s in [r["name"]] for w in r.get("workers") or []}
    out = []
    for row in live_rows(rows):
        sid = str(row.get("sessionId") or "")
        name = str(row.get("name") or sid or row.get("pid"))
        rc = by_name.get(name, {})
        line = _line_for(lines, sid, name)
        blocked = line.get("blocked") if isinstance(line.get("blocked"), dict) else None
        state = session_refresh.state_of(row)
        kind = (blocked or {}).get("kind") or ("permission" if state == "blocked" else None)
        waiting_on = line.get("waiting_on") or None
        waits = bool(waiting_on or kind)
        at = _since(line, row, blocked, waits)
        keys = [k for k in line.get("keys") or [] if isinstance(k, str)]
        role = rc.get("role") or "?"
        if role == "?" and line.get("role"):
            role = str(line["role"])
        starter = starter_of.get(name) if role == "worker" else None
        out.append(
            {
                "name": name,
                "session_id": sid,
                "kind": row.get("kind") or "",
                "role": role,
                "state": state,
                "doing": line.get("now") or line.get("topic") or ", ".join(keys) or None,
                "keys": keys,
                "waiting_on": waiting_on,
                "blocked_kind": kind,
                "since": _iso(at) if at is not None else None,
                "age_s": int(now - at) if at is not None else None,
                "plugin": rc.get("loaded") or "?",
                "model": worker_supervisor.session_model(worker_supervisor.projects_dir(), sid),
                "starter": starter,
                "group": None,
                "waits": waits,
            }
        )
    return out


def _rank(e: dict):
    return (not e["waits"], -(e["age_s"] if e["age_s"] is not None else -1))


def ordered(flat: list[dict]) -> list[dict]:
    """The display order with `group` set (module docstring § Order)."""
    heads = [e for e in flat if e["role"] != "worker"]
    workers = [e for e in flat if e["role"] == "worker"]
    out = []
    for head in sorted(heads, key=_rank):
        out.append({**head, "group": head["name"]})
        mine = [w for w in workers if w["starter"] == head["name"]]
        out += [{**w, "group": head["name"]} for w in sorted(mine, key=_rank)]
    listed = {h["name"] for h in heads}
    orphans = [w for w in workers if w["starter"] not in listed]
    return out + [{**w, "group": NO_STARTER} for w in sorted(orphans, key=_rank)]


def document(
    rows: list[dict] | None = None,
    roll: list[dict] | None = None,
    board: Path | None = None,
    now: float | None = None,
) -> dict:
    now = time.time() if now is None else now
    board = Path(board) if board is not None else Path(boardlib.default_board())
    doc = {"schema_version": SCHEMA_VERSION, "generated_at": _iso(now), "board": str(board)}
    try:
        rows = worker_launch.sessions() if rows is None else rows
    except worker_launch.LaunchError as exc:
        return {**doc, "sessions": [], "error": str(exc)}
    live = live_rows(rows)
    roll = session_refresh.roll_call(live, now=now) if roll is None else roll
    doc["sessions"] = ordered(entries(live, roll, board_lines(board), now))
    return doc


def age_text(seconds: int | None) -> str:
    if seconds is None:
        return "?"
    minutes = max(0, seconds) // 60
    return f"{minutes // 60}h{minutes % 60:02d}"


def text_line(e: dict) -> str:
    """`samu · coordinator · Q-Triage PROJ-31 · since 0h12 · waits: human · 9.14.0 · claude-opus-5-5`."""
    parts = [e["name"], e["role"], e["doing"] or "-", f"since {age_text(e['age_s'])}"]
    if e["waits"]:
        why = e["waiting_on"] or "?"
        parts.append(f"waits: {why}" + (f" ({e['blocked_kind']})" if e["blocked_kind"] else ""))
    parts.append(e["plugin"])
    if e["model"]:
        parts.append(e["model"])
    return ("  " if e["role"] == "worker" else "") + " · ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--json", action="store_true", help="the document as JSON")
    parser.add_argument("--board", help="the board file (default: the crew's, board.py path)")
    args = parser.parse_args(argv)
    doc = document(board=Path(args.board).expanduser() if args.board else None)
    if args.json:
        print(json.dumps(doc, ensure_ascii=False))
        return 0
    if doc.get("error"):
        print(f"crew_view: {doc['error']}", file=sys.stderr)
        return 1
    group = None
    for e in doc["sessions"]:
        if e["group"] == NO_STARTER and group != NO_STARTER:
            print(NO_STARTER)
        group = e["group"]
        print(text_line(e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
