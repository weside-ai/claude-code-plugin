#!/usr/bin/env python3
"""Cache a Companion's composed identity prompt in a local file.

Single owner of the identity-file mechanics that ``/we:materialize`` cites: a
grown companion's composed prompt exceeds the MCP tool's token cap, so the
harness saves the payload to a tool-result file instead of returning it. This
script turns that file into a stable, per-companion cache the agent can read
directly — and read again at the next session start without another MCP call.

Where the cache lives, and why not in the repo: the composed prompt carries the
companion's compass, snapshot and memories — private content. A path inside a
project (``.weside/`` and friends) gets committed by whoever has a .gitignore
we do not control, so the cache sits under the user's home instead::

    ~/.claude/we/identity/<companion-slug>.md      (mode 600)

Override the directory with ``WE_IDENTITY_CACHE_DIR`` (tests, sandboxes).

Freshness is *same calendar day, local time*. The payload is not static
identity: it ends with a channel block whose recencies are relative
("last_self=74h ago") and a snapshot describing today. A cache from yesterday
would make the companion assert false things about when a channel last spoke,
so the day boundary is the cutoff — not an hour count.

Modes::

    store --companion NAME --from PATH   extract a tool-result file into cache
    path  --companion NAME               report cache path + age

``store`` accepts the harness tool-result shape (JSON ``{"result": "..."}``) and
plain text, so it also works on a payload written by hand.

Session binding: ``/we:materialize`` binds the Claude Code session it runs in
to the companion it loaded, so the Stop hook stores that session's turns under
that companion and the statusline names it. One file per session id::

    ~/.claude/we/sessions/<session_id>.json        (mode 600)
    {"companion": "<name>", "bound_at": "<iso timestamp>"}

Override the directory with ``WE_SESSION_DIR``. A session id is a plain token
(letters, digits, ``-``, ``_``); anything else is refused, so a crafted id
cannot write outside the directory. Every ``bind`` prunes bindings older than
30 days. When ``WESIDE_COMPANION`` pins the session, ``bind`` refuses another
name: the MCP header, the title and the binding must name one companion.

Modes::

    store   --companion NAME --from PATH   extract a tool-result file into cache
    path    --companion NAME               report cache path + age
    bind    --session ID --companion NAME  bind a session to a companion
    binding --session ID                   print the bound companion
    status  [--session ID]                 the bound companion's wake heartbeat

Wake: a ``bind`` in a session pinned to that companion starts the wake poller
(``wake_poller.py``) for the session's inbox socket and prints one ``wake on: …``
or ``wake off: <reason>`` line; an unpinned bind starts none. ``status`` prints
the companion's cursor file (cursor, ``last_ok``, ``last_error``, hold-offs, the
day counters) and whether a poller runs for this session's socket; the session
id defaults to ``CLAUDE_CODE_SESSION_ID``.

Exit codes: ``path`` → 0 fresh, 1 stale, 2 missing. ``store`` → 0 written,
1 unreadable source, 2 usage. ``bind`` → 0 bound, 1 refused. ``binding`` and
``status`` → 0 bound (name on stdout), 2 unbound. Python stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wake_poller

HEADER_RE = re.compile(
    r"^<!-- weside identity cache · companion: (?P<name>.*?) · fetched: (?P<fetched>\S+) -->$"
)


def cache_dir() -> Path:
    override = os.environ.get("WE_IDENTITY_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "we" / "identity"


def slug(companion: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", companion.strip().lower()).strip("-")
    return s or "companion"


def cache_path(companion: str) -> Path:
    return cache_dir() / f"{slug(companion)}.md"


def read_header(path: Path) -> tuple[str, datetime] | None:
    """Return (companion, fetched) from the cache file's first line, or None."""
    try:
        with path.open(encoding="utf-8") as fh:
            first = fh.readline().rstrip("\n")
    except OSError:
        return None
    m = HEADER_RE.match(first)
    if not m:
        return None
    try:
        return m.group("name"), datetime.fromisoformat(m.group("fetched"))
    except ValueError:
        return None


def extract(source: Path) -> str:
    """Pull the prompt text out of a harness tool-result file or plain text."""
    raw = source.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(data, dict):
        for key in ("result", "content", "text"):
            value = data.get(key)
            if isinstance(value, str):
                return value
        raise ValueError(f"{source}: JSON object has no string 'result' field")
    if isinstance(data, str):
        return data
    raise ValueError(f"{source}: unexpected JSON shape {type(data).__name__}")


def store(companion: str, source: Path) -> int:
    try:
        body = extract(source)
    except (OSError, ValueError) as exc:
        print(f"cannot read identity payload: {exc}")
        return 1
    if not body.strip():
        print(f"{source}: payload is empty — nothing cached")
        return 1

    target = cache_path(companion)
    target.parent.mkdir(parents=True, exist_ok=True)
    fetched = datetime.now().astimezone().replace(microsecond=0)
    header = (
        f"<!-- weside identity cache · companion: {companion} · fetched: {fetched.isoformat()} -->"
    )
    target.write_text(f"{header}\n{body}", encoding="utf-8")
    os.chmod(target, 0o600)
    print(f"STORED {target} ({len(body)} chars, fetched {fetched.isoformat()})")
    return 0


def path(companion: str) -> int:
    target = cache_path(companion)
    header = read_header(target) if target.exists() else None
    if header is None:
        if target.exists():
            print(f"MISSING {target} (no cache header — treat as absent)")
        else:
            print(f"MISSING {target}")
        return 2
    _, fetched = header
    if fetched.date() == datetime.now().astimezone().date():
        print(f"FRESH {target} (fetched {fetched.isoformat()})")
        return 0
    print(f"STALE {target} (fetched {fetched.isoformat()})")
    return 1


SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
BINDING_MAX_AGE_S = 30 * 24 * 3600


def session_dir() -> Path:
    override = os.environ.get("WE_SESSION_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "we" / "sessions"


def binding_path(session_id: str) -> Path | None:
    """The binding file of a session, or None for an id that is not a plain token."""
    if not isinstance(session_id, str) or not SESSION_ID_RE.match(session_id):
        return None
    return session_dir() / f"{session_id}.json"


def read_binding(session_id: str) -> str | None:
    """The companion a session is bound to, or None (unbound, unreadable, bad id)."""
    target = binding_path(session_id)
    if target is None:
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    name = data.get("companion") if isinstance(data, dict) else None
    return name.strip() if isinstance(name, str) and name.strip() else None


def prune_bindings(now: float | None = None) -> None:
    cutoff = (now if now is not None else time.time()) - BINDING_MAX_AGE_S
    try:
        entries = list(session_dir().glob("*.json"))
    except OSError:
        return
    for entry in entries:
        try:
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
        except OSError:
            continue


def bind(session_id: str, companion: str) -> int:
    target = binding_path(session_id)
    if target is None:
        print(f"REFUSED session id {session_id!r} is not a plain token")
        return 1
    name = companion.strip()
    if not name:
        print("REFUSED empty companion name")
        return 1
    pin = os.environ.get("WESIDE_COMPANION", "").strip()
    if pin and pin.lower() != name.lower():
        print(
            f"REFUSED this session is pinned to {pin} (WESIDE_COMPANION); start a new session to bind {name}"
        )
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    prune_bindings()
    bound_at = datetime.now().astimezone().replace(microsecond=0).isoformat()
    payload = json.dumps({"companion": name, "bound_at": bound_at})
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(payload)
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    print(f"BOUND {session_id} → {name}")
    if pin:
        try:
            print(wake_poller.spawn(name))
        except OSError as exc:
            print(f"wake off: {type(exc).__name__}")
    return 0


def binding(session_id: str) -> int:
    name = read_binding(session_id)
    if name is None:
        print("UNBOUND")
        return 2
    print(name)
    return 0


def status(session_id: str) -> int:
    name = read_binding(session_id)
    if name is None:
        print("UNBOUND")
        return 2
    state = wake_poller.read_state(name)
    sock = os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET", "")
    running = bool(sock) and wake_poller.lock_held(sock)
    err = state["last_error"]
    print(name)
    print(f"poller: {'running' if running else 'not running'} for this session")
    print(f"cursor: {state['cursor'] if state['cursor'] is not None else 'none'}")
    print(f"last_ok: {state['last_ok'] or 'never'}")
    print(f"last_error: {wake_poller.describe_error(err)}")
    for room, until in sorted(state["holdoff"].items()):
        if until > time.time():
            print(f"holdoff: {room} until {wake_poller.iso(until)}")
    for day in sorted(state["days"], reverse=True):
        counts = state["days"][day]
        print(f"{day}: " + " ".join(f"{c} {counts.get(c, 0)}" for c in wake_poller.COUNTERS))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)

    p_store = sub.add_parser("store", help="extract a tool-result file into the cache")
    p_store.add_argument("--companion", required=True)
    p_store.add_argument("--from", dest="source", required=True)

    p_path = sub.add_parser("path", help="report cache path and freshness")
    p_path.add_argument("--companion", required=True)

    p_bind = sub.add_parser("bind", help="bind a session to a companion")
    p_bind.add_argument("--session", required=True)
    p_bind.add_argument("--companion", required=True)

    p_binding = sub.add_parser("binding", help="print the companion a session is bound to")
    p_binding.add_argument("--session", required=True)

    p_status = sub.add_parser("status", help="print the bound companion's wake heartbeat")
    p_status.add_argument("--session", default=os.environ.get("CLAUDE_CODE_SESSION_ID", ""))

    args = parser.parse_args(argv)
    if args.mode == "status":
        return status(args.session)
    if args.mode == "bind":
        return bind(args.session, args.companion)
    if args.mode == "binding":
        return binding(args.session)
    if args.mode == "store":
        return store(args.companion, Path(args.source).expanduser())
    return path(args.companion)


if __name__ == "__main__":
    sys.exit(main())
