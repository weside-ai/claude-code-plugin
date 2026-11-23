#!/usr/bin/env python3
"""A session's event tail: delivers the event lines routed to its roles into its inbox socket.

One tail per Claude Code session of a crew member (keyed by the session's inbox socket), started
by ``hooks/events_on_start.py``. It calls no API: it reads the poller's files
(``event_poller.py``) and writes into its own session only.

Lifecycle
    ``run`` takes a non-blocking ``flock`` on ``<dir>/tails/<socket key>.lock`` (one tail per
    socket; a second start exits). The inbox token comes from ``CLAUDE_CODE_MESSAGING_TOKEN`` and
    is removed from the environment at start: it never reaches argv or a file. A session without a
    member (no ``WESIDE_COMPANION`` the crew knows) gets no tail. The socket gone (the file, or
    ``ECONNREFUSED``/``ENOENT`` on delivery) → the presence file is removed and the tail exits.

Per cycle (15 s)
    Write ``presence/<socket key>.json``: ``name`` (the socket key), ``member``, ``roles`` (every
    crew role key bound to the member), ``parked`` (this session's board line has state
    ``parked``), ``heartbeat``. Then read the event rows (``events.jsonl``, its ``.1`` first) past
    the cursor and keep those addressed to this session (``to[].session``). Per row, in order:

    - a kind the current ``events:`` block does not route to one of the member's roles (or to the
      member; a damage row also as ``coordinator``) → ledger row ``not routed``, no line;
    - the same kind and object delivered within ``fold_s`` → ledger row ``folded``, no line;
    - a ``digest`` route → kept; once an hour all kept lines go as one line;
    - else one line (``event_routes.render``) into the socket, then the ledger row, then the
      cursor. A crash between the line and the cursor repeats one line at most; the fold catches it.

Files: ``tails/<socket key>.json`` (cursor, fold memory, digest), ``ledger.jsonl`` (``{id, to,
delivered, delivered_at, reason}``), the presence file. Delivery is ``worker_supervisor.deliver``
(auth line, then one user line).

Usage:
  event_tail.py run --root DIR       the tail of this session (socket and token from the environment)
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import crew as crew_mod  # noqa: E402
import event_poller as ep  # noqa: E402
import event_routes as routes_mod  # noqa: E402
from event_sources import iso  # noqa: E402
from worker_supervisor import deliver  # noqa: E402

CYCLE_S = 15
DIGEST_S = 3600
FOLD_KEEP = 200


def socket_key(socket_path: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(socket_path))[:80] or "session"


class SessionGoneError(Exception):
    """The session's socket is gone."""


class Tail:
    def __init__(
        self,
        root: Path,
        folder: Path,
        socket_path: str,
        token: str,
        member: str,
        roles: list[str],
        *,
        session_id: str = "",
        clock: Callable[[], float] = time.time,
        send: Callable[[str, str, str], None] = deliver,
    ):
        self.root, self.dir = Path(root), Path(folder)
        self.sock, self._token = socket_path, token
        self.member, self.roles = member, list(roles)
        self.session_id = session_id
        self.clock, self.send = clock, send
        self.key = socket_key(socket_path)
        self.names = {member.lower()}
        self.config = self.root / ".weside" / "config.json"
        self.block: dict = {"routes": {}}
        self.mtime: float | None = None
        (self.dir / "tails").mkdir(parents=True, exist_ok=True)
        (self.dir / "presence").mkdir(parents=True, exist_ok=True)
        self.state_file = self.dir / "tails" / f"{self.key}.json"
        self.state = ep.read_json(self.state_file, None)
        if not isinstance(self.state, dict):
            # a new tail starts at the newest row: what came before was addressed to others
            rows = ep.read_rows(self.dir / "events.jsonl")
            self.state = {"cursor": max((int(r.get("seq") or 0) for r in rows), default=0)}

    # --- presence ---------------------------------------------------------------------------

    def parked(self) -> bool:
        try:
            board = json.loads(crew_mod.resolve_board(self.root).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        lines = (
            [x for x in (board.get("sessions") or []) if isinstance(x, dict)]
            if isinstance(board, dict)
            else []
        )
        # this session's line by its id; else (a line the coordinator wrote without an id, an id
        # that changed with /clear) by the member's slug or name
        hit = next(
            (x for x in lines if self.session_id and x.get("session_id") == self.session_id), None
        )
        if hit is None:
            hit = next(
                (x for x in lines if str(x.get("name") or "").strip().lower() in self.names), None
            )
        return bool(hit) and hit.get("state") == "parked"

    def presence_path(self) -> Path:
        return self.dir / "presence" / f"{self.key}.json"

    def write_presence(self) -> None:
        doc = {
            "name": self.key,
            "member": self.member,
            "roles": self.roles,
            "parked": self.parked(),
            "heartbeat": self.clock(),
        }
        ep.write_json(self.presence_path(), doc)

    def leave(self) -> None:
        with contextlib.suppress(OSError):
            self.presence_path().unlink()

    # --- one cycle ----------------------------------------------------------------------------

    def reload(self) -> None:
        try:
            mtime = self.config.stat().st_mtime
        except OSError:
            return
        if mtime == self.mtime:
            return
        self.mtime = mtime
        _, crew = ep.load_crew(self.root)
        entry = (crew.get("members") or {}).get(self.member) or {}
        self.names = {self.member.lower(), str(entry.get("name") or self.member).strip().lower()}
        with contextlib.suppress(routes_mod.EventsError):
            self.block = routes_mod.validate(
                ep.read_block(self.config), crew
            )  # invalid: keep the last

    def routed(self, row: dict, as_roles: list[str]) -> bool:
        allowed = set(routes_mod.targets(self.block, row.get("kind", "")))
        if row.get("damage"):
            allowed.add("coordinator")
        mine = set(self.roles) | {self.member}
        return bool(allowed & mine & set(as_roles))

    def _send(self, text: str) -> None:
        try:
            self.send(self.sock, self._token, text)
        except OSError as exc:
            if isinstance(exc, (FileNotFoundError, ConnectionRefusedError)) or exc.errno in (
                errno.ENOENT,
                errno.ECONNREFUSED,
            ):
                raise SessionGoneError() from None
            raise

    def cycle(self) -> int:
        """One cycle; the number of lines delivered. ``SessionGoneError`` when the socket is gone."""
        if not os.path.exists(self.sock):
            raise SessionGoneError()
        self.reload()
        self.write_presence()
        now = self.clock()
        fold_s = int(self.block.get("fold_s", 600))
        cursor = int(self.state.get("cursor") or 0)
        fold = self.state.setdefault("fold", {})
        kept = self.state.setdefault("digest", [])
        sent = 0
        for row in ep.read_rows(self.dir / "events.jsonl"):
            seq = int(row.get("seq") or 0)
            if seq <= cursor:
                continue
            as_roles = [a.get("as") for a in row.get("to") or [] if a.get("session") == self.key]
            if as_roles:
                reason = self.handle(row, as_roles, now, fold, fold_s, kept)
                sent += reason == "delivered"
            cursor = seq
            self.state["cursor"] = cursor
            self.save()
        if kept and not self.state.get("last_digest"):
            self.state["last_digest"] = now  # the hour starts with the first kept line
        if kept and now - float(self.state.get("last_digest") or 0) >= DIGEST_S:
            self._send(routes_mod.digest(kept))
            self.state["digest"], self.state["last_digest"] = [], now
            sent += 1
            self.save()
        return sent

    def handle(
        self, row: dict, as_roles: list[str], now: float, fold: dict, fold_s: int, kept: list
    ) -> str:
        line = routes_mod.render(row)
        fkey = f"{row.get('kind')}|{row.get('object')}"
        if not self.routed(row, as_roles):
            reason, delivered = "not routed", False
        elif now - float(fold.get(fkey) or 0) < fold_s:
            reason, delivered = "folded", False
        elif routes_mod.mode(self.block, row.get("kind", "")) == "digest":
            kept.append(line)
            reason, delivered = "digest", False
        else:
            self._send(line)
            fold[fkey] = now
            if len(fold) > FOLD_KEEP:
                for k in sorted(fold, key=fold.get)[: len(fold) - FOLD_KEEP]:
                    del fold[k]
            reason, delivered = "delivered", True
        ep.append_rows(
            self.dir / "ledger.jsonl",
            [
                {
                    "id": row.get("id"),
                    "to": self.key,
                    "delivered": delivered,
                    "delivered_at": iso(now),
                    "reason": reason,
                    "source_at": row.get("source_at"),
                }
            ],
        )
        return reason

    def save(self) -> None:
        ep.write_json(self.state_file, self.state)

    def run(self, cycles: int | None = None) -> str:
        n = 0
        try:
            while True:
                try:
                    self.cycle()
                except SessionGoneError:
                    raise
                except OSError:
                    pass  # a socket hiccup: the cursor stays, the next cycle tries again
                n += 1
                if cycles is not None and n >= cycles:
                    return "cycles"
                time.sleep(CYCLE_S)
        except SessionGoneError:
            self.leave()
            return "gone"


def member_and_roles(root: Path, environ: dict) -> tuple[str | None, list[str]]:
    """The crew member this session is (its pin) and every role key bound to it."""
    pin = str(environ.get("WESIDE_COMPANION") or "").strip()
    if not pin or str(environ.get("WE_ROLE") or "").strip() == "worker":
        return None, []
    _, crew = ep.load_crew(root)
    found = crew_mod.member(crew, pin) if crew else None
    if not found:
        return None, []
    slug = found[0]
    roles = sorted(k for k, v in (crew.get("roles") or {}).items() if v == slug)
    return slug, roles


def take_lock(folder: Path, key: str) -> int | None:
    (folder / "tails").mkdir(parents=True, exist_ok=True)
    fd = os.open(str(folder / "tails" / f"{key}.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--root", required=True)
    r.add_argument("--cycles", type=int)
    a = ap.parse_args(argv)
    token = os.environ.pop("CLAUDE_CODE_MESSAGING_TOKEN", "")
    sock = os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET", "")
    root = Path(a.root)
    member, roles = member_and_roles(root, dict(os.environ))
    if fcntl is None or not sock or not token or not member:
        return 2
    folder = ep.events_dir(root)
    fd = take_lock(folder, socket_key(sock))
    if fd is None:
        return 0
    tail = Tail(
        root,
        folder,
        sock,
        token,
        member,
        roles,
        session_id=os.environ.get("CLAUDE_CODE_SESSION_ID", ""),
    )
    tail.run(a.cycles)
    return 0


def spawn(root: Path, environ: dict[str, Any]) -> str:
    """Start this session's tail detached; the token travels in its environment only."""
    import subprocess  # noqa: PLC0415

    member, _ = member_and_roles(root, environ)
    if not member:
        return "events: no tail (this session is no crew member)"
    if not environ.get("CLAUDE_CODE_MESSAGING_SOCKET") or not environ.get(
        "CLAUDE_CODE_MESSAGING_TOKEN"
    ):
        return "events: no tail (this Claude Code has no inbox socket)"
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "run", "--root", str(root)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
        env=dict(environ),
    )
    return f"events: tail {proc.pid} for {member}"


if __name__ == "__main__":
    sys.exit(main())
