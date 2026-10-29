#!/usr/bin/env python3
"""Wake poller: tells a running companion session that its WESIDE side handed something over.

One poller per Claude Code session (keyed by the session's inbox socket), started detached by
``identity_cache.py bind`` and by the SessionStart hook for a session already bound to its pin.
It runs no model: once a minute it asks the weside MCP tool ``news_since`` "which handoffs to this
Claude Code side are pending since my cursor?" and, per pending handoff, writes one content-free
line into the session's inbox socket; the session then reads the note itself with
``news_since(handoff=<id>)`` and the source room with ``read_timeline``. Lines addressed to the
companion in a room wake nothing: its WESIDE side answers those, and hands over what belongs
here. Contract: ``references/companion-session.md`` § Wake.

Lifecycle
    Start: a non-blocking ``flock`` on ``<dir>/poller-<socket basename>.lock`` (one poller per
    socket; a second start exits at once). Every cycle first checks that the session lives: the
    socket file exists and, when its name is a process id, that process exists; otherwise exit.
    The wait between cycles is sliced to the poll interval, so a poller in back-off still exits
    within two intervals after its session ended.

Per cycle
    ``weside auth token --api-url <origin of the MCP URL>`` (stdout kept in memory only) →
    JSON-RPC ``tools/call news_since`` at ``WESIDE_MCP_URL`` (default the plugin's MCP URL) with
    ``X-Weside-Companion: <companion>``. The CLI keeps credentials per environment, so the token
    always comes for the origin the poller calls, never for the CLI config's default ``api_url``.
    Handoff answer ``{"cursor": N, "handoffs": [{"id": <id>, "from": "room:<id>" | null}]}``: the
    call sends ``after=<handoff_cursor>`` (0 when the file has none, so a cursor file of the
    room-news poller is ignored), every listed handoff gets one line of one wake, and
    ``handoff_cursor`` takes the answer's ``cursor`` as given (a server that met a cursor above
    every handoff lists from 0 and answers a lower one). After a wake attempt the hold-off key
    ``claude_code`` holds the next wake for 10 min; handoffs listed meanwhile wait, cursor kept.
    Server compatibility (delete once every weside server answers ``handoffs``): a
    server that still answers ``rooms`` gets the room-news rule below. The answer's shape sets
    ``server_shape``; a shape that differs from the one the call was made for is asked again in
    the same cycle with the other shape's cursor.
    Room-news rule: a room whose lines the companion's WESIDE side already took up wakes nobody: a server that
    answers ``unanswered`` per room (with ``unanswered_newest``, a row id, and
    ``unanswered_age_s``) wakes a room only for an unanswered line newer than the one last
    delivered there, and only once the newest unanswered line is ``GRACE_S`` (10 min) old; the
    WESIDE side usually answers within that. A server without the field gets the count rule
    (server compatibility until every environment runs the field).
    No news, or only rooms in their hold-off or grace → no socket contact. Otherwise one connection:
    ``{"type":"auth","token":…}`` then ``{"type":"user","message":{"role":"user","content":…}}``.
    The wake text is built from room refs (``room:<digits>``), integers and fixed words only.
    A handoff line reads ``weside: handoff for <Name> from room:<id> (#<h>). Read it with
    news_since(handoff=<h>), then read_timeline(room="room:<id>"). This note carries no content.``
    ``ECONNREFUSED``/``ENOENT`` on the socket = the session is gone: exit, cursor kept. Any other
    delivery failure → a pending note ``<dir>/pending-<socket basename>.json`` for the prompt hook
    (``hooks/news_on_prompt.py``), cursor kept.

Cursor file ``<dir>/<companion slug>.json`` (mode 600, read-modify-write under ``flock`` on
``<file>.lock``, atomic replace), shared by every session of that companion:
    ``handoff_cursor`` int or null — every handoff id up to it is delivered
    ``server_shape`` ``handoffs`` (default) or ``rooms`` — the shape the last answer had
    ``cursor``     int or null — room-news rule: every addressed row up to it is handed off; it
                   advances only when no room in the answer still holds a line not yet delivered
    ``delivered``  room → count already delivered against ``cursor`` (reset when it advances;
                   a server without ``unanswered``)
    ``delivered_row`` room → newest unanswered row id already delivered (reset with ``cursor``)
    ``holdoff``    ``claude_code`` or a room → epoch seconds; no second wake before then (10 min)
    ``started``    ISO time the newest poller started
    ``last_ok``    ISO time of the last successful ``news_since``
    ``last_error`` ``{"class": auth|network|http|socket|format, "at": ISO}`` — a class, never a text;
                   an auth error adds ``"detail": token`` (the token command failed) or ``401``
                   (``/mcp`` refused the bearer)
    ``days``       UTC date → ``polls``, ``errors``, ``wakes``, ``hook_delivered`` (7 days kept)

Back-off and exit
    A failed cycle doubles the wait (60 s → … ≤ 900 s), a success resets it. Five consecutive auth
    failures (``weside auth token`` non-zero or missing, HTTP 401 from ``/mcp``) write
    ``last_error: auth`` and exit.

Secrets
    The inbox token comes from ``CLAUDE_CODE_MESSAGING_TOKEN`` in the inherited environment and
    is removed from it at start; it never reaches argv, a file or the log. The bearer lives only
    in memory. The log (``<dir>/poller-<socket basename>.log``) holds event classes and counts.

Override the directory with ``WE_NEWS_DIR``; ``WE_WAKE_INTERVAL_S`` shortens the interval (tests).
Usage: ``wake_poller.py --companion NAME [--once]``. Python stdlib only, ≥ 3.9, POSIX.
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows has no flock
    fcntl = None  # type: ignore[assignment]

DEFAULT_MCP_URL = "https://api.weside.ai/mcp/"
INTERVAL_S = 60
MAX_INTERVAL_S = 900
HOLDOFF_S = 600
GRACE_S = 600
AUTH_EXIT_AFTER = 5
DAYS_KEPT = 7
TOKEN_TIMEOUT_S = 30
HTTP_TIMEOUT_S = 30
LOG_MAX_BYTES = 256 * 1024

ERROR_CLASSES = ("auth", "network", "http", "socket", "format")
AUTH_DETAILS = {"token": "token command failed", "401": "401 from /mcp"}
COUNTERS = ("polls", "errors", "wakes", "hook_delivered")
ROOM_RE = re.compile(r"room:[0-9]{1,18}")
HANDOFF_KEY = "claude_code"
SHAPES = ("handoffs", "rooms")
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}")

TEXT_TAIL = "This note carries no content; your WESIDE side may already have answered there."
HANDOFF_TAIL = "This note carries no content."


class PollError(Exception):
    """A failed cycle, carrying one class from ``ERROR_CLASSES`` (auth: a key of ``AUTH_DETAILS``)."""

    def __init__(self, cls: str, detail: str | None = None):
        super().__init__(cls)
        self.cls = cls
        self.detail = detail


class SessionGoneError(Exception):
    """The session's socket refused or vanished."""


# --- paths and the cursor file -------------------------------------------------------------


def news_dir() -> Path:
    override = os.environ.get("WE_NEWS_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "we" / "news"


def slug(companion: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", companion.strip().lower()).strip("-")
    return s or "companion"


def state_path(companion: str) -> Path:
    return news_dir() / f"{slug(companion)}.json"


def socket_key(socket_path: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.basename(socket_path)) or "socket"


def pending_path(socket_path: str) -> Path:
    return news_dir() / f"pending-{socket_key(socket_path)}.json"


def poller_lock_path(socket_path: str) -> Path:
    return news_dir() / f"poller-{socket_key(socket_path)}.lock"


def log_path(socket_path: str) -> Path:
    return news_dir() / f"poller-{socket_key(socket_path)}.log"


def iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def utc_day(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).date().isoformat()


def empty_state() -> dict:
    return {
        "handoff_cursor": None,
        "server_shape": "handoffs",
        "cursor": None,
        "delivered": {},
        "delivered_row": {},
        "holdoff": {},
        "started": None,
        "last_ok": None,
        "last_error": None,
        "days": {},
    }


def read_state(companion: str) -> dict:
    """The cursor file, normalised; a missing or broken file reads as empty."""
    state = empty_state()
    try:
        data = json.loads(state_path(companion).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return state
    if not isinstance(data, dict):
        return state
    for key in ("cursor", "handoff_cursor"):
        if _plain_int(data.get(key)):
            state[key] = data[key]
    if data.get("server_shape") in SHAPES:
        state["server_shape"] = data["server_shape"]
    for key in ("delivered", "delivered_row", "holdoff"):
        state[key] = _keyed_numbers(data.get(key), allow_handoff=key == "holdoff")
    for key in ("started", "last_ok"):
        if parse_iso(data.get(key)) is not None:
            state[key] = data[key]
    err = data.get("last_error")
    if isinstance(err, dict) and err.get("class") in ERROR_CLASSES and parse_iso(err.get("at")):
        state["last_error"] = {"class": err["class"], "at": err["at"]}
        if err["class"] == "auth" and err.get("detail") in AUTH_DETAILS:
            state["last_error"]["detail"] = err["detail"]
    state["days"] = _day_counters(data.get("days"))
    return state


def _day_counters(days: Any) -> dict:
    if not isinstance(days, dict):
        return {}
    return {
        day: {
            c: int(counts.get(c, 0))
            if isinstance(counts.get(c, 0), int) and not isinstance(counts.get(c), bool)
            else 0
            for c in COUNTERS
        }
        for day, counts in days.items()
        if isinstance(day, str) and isinstance(counts, dict)
    }


def _keyed_numbers(value: Any, *, allow_handoff: bool) -> dict:
    """A ``room:<id>`` (or ``claude_code``) → number map; anything else is dropped."""
    if not isinstance(value, dict):
        return {}
    return {
        k: v
        for k, v in value.items()
        if isinstance(k, str)
        and (ROOM_RE.fullmatch(k) or (allow_handoff and k == HANDOFF_KEY))
        and isinstance(v, (int, float))
        and not isinstance(v, bool)
    }


def _write_atomic(target: Path, payload: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(payload)
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)


def write_state(companion: str, state: dict) -> None:
    days = state.get("days", {})
    for day in sorted(days)[:-DAYS_KEPT]:
        del days[day]
    _write_atomic(state_path(companion), json.dumps(state, sort_keys=True))


@contextlib.contextmanager
def locked_state(companion: str):
    """Yield the cursor file's state under its lock; the state is written back on exit."""
    target = state_path(companion)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.with_name(target.name + ".lock")
    fd = os.open(str(lock), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        state = read_state(companion)
        yield state
        write_state(companion, state)
    finally:
        os.close(fd)


def bump(state: dict, counter: str, now: float, by: int = 1) -> None:
    day = state["days"].setdefault(utc_day(now), dict.fromkeys(COUNTERS, 0))
    day[counter] = day.get(counter, 0) + by


# --- the wake text -------------------------------------------------------------------------


def render(companion: str, rooms: list[dict], since_last_session: bool = False) -> str:
    """The wake line from room refs, integers and fixed words; anything else is refused."""
    if not NAME_RE.fullmatch(companion):
        raise ValueError("companion name is not plain")
    parts, reads = [], []
    for item in rooms:
        room, count = item["room"], item["count"]
        if not ROOM_RE.fullmatch(room) or not isinstance(count, int) or count < 0:
            raise ValueError("room ref or count is not plain")
        parts.append(f"{room} ({count}{'+' if item.get('saturated') else ''})")
        reads.append(f'read_timeline(room="{room}")')
    since = " since your last session" if since_last_session else ""
    return (
        f"weside: new for {companion}{since} in {', '.join(parts)}. "
        f"Read it yourself with {', '.join(reads)}. {TEXT_TAIL}"
    )


def render_handoffs(companion: str, handoffs: list[dict]) -> str:
    """One line per handoff from its id, its source ref and fixed words; no note text."""
    if not NAME_RE.fullmatch(companion):
        raise ValueError("companion name is not plain")
    lines = []
    for item in handoffs:
        hid, source = item["id"], item["from"]
        if not _plain_int(hid) or not (source is None or ROOM_RE.fullmatch(str(source))):
            raise ValueError("handoff id or source is not plain")
        if source is None:
            lines.append(
                f"weside: handoff for {companion} (#{hid}). "
                f"Read it with news_since(handoff={hid}). {HANDOFF_TAIL}"
            )
        else:
            lines.append(
                f"weside: handoff for {companion} from {source} (#{hid}). "
                f'Read it with news_since(handoff={hid}), then read_timeline(room="{source}"). '
                f"{HANDOFF_TAIL}"
            )
    return "\n".join(lines)


def shape_of(answer: dict) -> str:
    """``handoffs`` when the answer lists handoffs (any ``rooms`` beside it is ignored)."""
    return "handoffs" if "handoffs" in answer else "rooms"


# --- the three outside calls ---------------------------------------------------------------


def child_env() -> dict:
    """The environment for ``weside``: everything but the inbox token."""
    return {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_MESSAGING_TOKEN"}


def api_origin(mcp_url: str) -> str:
    """``https://api.weside.ai/mcp/`` → ``https://api.weside.ai``: the CLI's ``--api-url``."""
    parts = urllib.parse.urlsplit(mcp_url)
    return f"{parts.scheme}://{parts.netloc}"


def describe_error(err: dict | None) -> str:
    """``last_error`` for a person: ``auth (401 from /mcp) at <ISO>``, ``none``."""
    if not err:
        return "none"
    detail = AUTH_DETAILS.get(err.get("detail", ""))
    return f"{err['class']}{f' ({detail})' if detail else ''} at {err['at']}"


def weside_token(api_url: str) -> str:
    """``weside auth token --api-url <api_url>``'s stdout; any failure is an auth failure."""
    exe = shutil.which("weside")
    if not exe:
        raise PollError("auth", "token")
    try:
        done = subprocess.run(
            [exe, "auth", "token", "--api-url", api_url],
            capture_output=True,
            text=True,
            timeout=TOKEN_TIMEOUT_S,
            env=child_env(),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise PollError("auth", "token") from None
    token = done.stdout.strip()
    if done.returncode != 0 or not token or any(c.isspace() for c in token):
        raise PollError("auth", "token")
    return token


def _rpc_payload(body: bytes, content_type: str) -> dict:
    text = body.decode("utf-8")
    if "text/event-stream" in content_type:
        datas = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        for data in reversed(datas):
            if data:
                text = data
                break
        else:
            raise PollError("format")
    try:
        payload = json.loads(text)
    except ValueError:
        raise PollError("format") from None
    if not isinstance(payload, dict):
        raise PollError("format")
    return payload


def parse_news(payload: dict) -> dict:
    """Validate a ``news_since`` JSON-RPC answer down to cursor and handoffs (or rooms)."""
    if "error" in payload:
        raise PollError("http")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise PollError("format")
    if result.get("isError"):
        raise PollError("http")
    content = result.get("content")
    if not isinstance(content, list) or not content or not isinstance(content[0], dict):
        raise PollError("format")
    try:
        news = json.loads(content[0].get("text", ""))
    except (TypeError, ValueError):
        raise PollError("format") from None
    if not isinstance(news, dict):
        raise PollError("format")
    cursor = news.get("cursor")
    if not _plain_int(cursor):
        raise PollError("format")
    if shape_of(news) == "handoffs":
        handoffs = news["handoffs"]
        if not isinstance(handoffs, list):
            raise PollError("format")
        return {"cursor": cursor, "handoffs": [_clean_handoff(item) for item in handoffs]}
    rooms = news.get("rooms")
    if not isinstance(rooms, list):
        raise PollError("format")
    return {"cursor": cursor, "rooms": [_clean_room(item) for item in rooms]}


def _clean_handoff(item: Any) -> dict:
    if not isinstance(item, dict) or not _plain_int(item.get("id")):
        raise PollError("format")
    source = item.get("from")
    if source is not None and not (isinstance(source, str) and ROOM_RE.fullmatch(source)):
        raise PollError("format")
    return {"id": item["id"], "from": source}


def _plain_int(value: Any, *, nullable: bool = False) -> bool:
    if value is None:
        return nullable
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _clean_room(item: Any) -> dict:
    if not isinstance(item, dict):
        raise PollError("format")
    room, count, sat = item.get("room"), item.get("count"), item.get("saturated", False)
    if not isinstance(room, str) or not ROOM_RE.fullmatch(room):
        raise PollError("format")
    if not _plain_int(count):
        raise PollError("format")
    if not isinstance(sat, bool):
        raise PollError("format")
    clean = {"room": room, "count": count, "saturated": sat}
    if "unanswered" in item:
        newest, age = item.get("unanswered_newest"), item.get("unanswered_age_s")
        if not _plain_int(item["unanswered"]):
            raise PollError("format")
        if not _plain_int(newest, nullable=True) or not _plain_int(age, nullable=True):
            raise PollError("format")
        if item["unanswered"] and (newest is None or age is None):
            raise PollError("format")
        clean.update(unanswered=item["unanswered"], unanswered_newest=newest, unanswered_age_s=age)
    return clean


def call_news_since(url: str, bearer: str, companion: str, after: int | None) -> dict:
    arguments = {} if after is None else {"after": after}
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "news_since", "arguments": arguments},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-Weside-Companion": companion,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise PollError("auth", "401") from None
        raise PollError("http") from None
    except (urllib.error.URLError, OSError, ValueError):
        raise PollError("network") from None
    try:
        return parse_news(_rpc_payload(raw, ctype))
    except UnicodeDecodeError:
        raise PollError("format") from None


def deliver(socket_path: str, token: str, text: str) -> None:
    """Write auth + one user line into the inbox socket. Gone → ``SessionGoneError``."""
    lines = (
        json.dumps({"type": "auth", "token": token})
        + "\n"
        + json.dumps({"type": "user", "message": {"role": "user", "content": text}})
        + "\n"
    ).encode("utf-8")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(10)
    try:
        try:
            sock.connect(socket_path)
        except OSError as exc:
            if exc.errno in (errno.ENOENT, errno.ECONNREFUSED):
                raise SessionGoneError() from None
            raise PollError("socket") from None
        try:
            sock.sendall(lines)
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            raise PollError("socket") from None
    finally:
        sock.close()


def session_alive(socket_path: str) -> bool:
    """The socket file exists and, when its name is a process id, that process exists."""
    try:
        if not os.path.exists(socket_path):
            return False
    except OSError:
        return False
    stem = os.path.basename(socket_path).split(".")[0]
    if stem.isdigit():
        try:
            os.kill(int(stem), 0)
        except ProcessLookupError:
            return False
        except (PermissionError, OverflowError, OSError):
            return True
    return True


def write_pending(socket_path: str, companion: str, news: dict, now: float):
    """The note for the prompt hook: ``handoffs`` or (room-news rule) ``rooms`` + ``since``."""
    payload = dict(news, companion=companion, at=iso(now))
    _write_atomic(pending_path(socket_path), json.dumps(payload, sort_keys=True))


# --- the poller ----------------------------------------------------------------------------


def wake_interval(environ: dict | None = None) -> int:
    raw = (os.environ if environ is None else environ).get("WE_WAKE_INTERVAL_S", "")
    if raw.isdigit() and int(raw) >= 1:
        return int(raw)
    return INTERVAL_S


class Poller:
    """One poller; every outside effect is injectable so the suite runs on a fake clock."""

    def __init__(
        self,
        companion: str,
        socket_path: str,
        token: str,
        *,
        mcp_url: str = DEFAULT_MCP_URL,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        get_bearer: Callable[[str], str] = weside_token,
        news: Callable[[str, str, str, Any], dict] = call_news_since,
        send: Callable[[str, str, str], None] = deliver,
        alive: Callable[[str], bool] = session_alive,
        log: Callable[[str], None] = lambda _line: None,
        interval: int = INTERVAL_S,
        grace: int = GRACE_S,
    ):
        self.companion = companion
        self.socket_path = socket_path
        self._token = token
        self.mcp_url = mcp_url
        self.clock = clock
        self.sleep = sleep
        self.get_bearer = get_bearer
        self.news = news
        self.send = send
        self.alive = alive
        self.log = log
        self.interval = interval
        self.grace = grace
        self.max_interval = max(interval, MAX_INTERVAL_S * interval // INTERVAL_S)
        self.auth_failures = 0
        self.first = True
        self.resumed = False

    def start(self) -> None:
        with locked_state(self.companion) as state:
            self.resumed = state["cursor"] is not None
            state["started"] = iso(self.clock())

    def _fail(self, cls: str, detail: str | None = None) -> str:
        now = self.clock()
        with locked_state(self.companion) as state:
            state["last_error"] = {"class": cls, "at": iso(now)}
            if detail:
                state["last_error"]["detail"] = detail
            bump(state, "errors", now)
        self.log(f"error {cls}{f' {detail}' if detail else ''}")
        if cls == "auth":
            self.auth_failures += 1
            if self.auth_failures >= AUTH_EXIT_AFTER:
                self.log("exit auth")
                return "auth-exit"
        else:
            self.auth_failures = 0
        return f"error:{cls}"

    def poll_once(self) -> str:
        """One cycle; returns ``ok``, ``error:<class>``, ``auth-exit`` or ``gone``."""
        now = self.clock()
        with locked_state(self.companion) as state:
            shape = state["server_shape"]
            bases = {"handoffs": state["handoff_cursor"], "rooms": state["cursor"]}
            bump(state, "polls", now)

        def ask(bearer: str, shape: str) -> dict:
            base = bases[shape]
            after = (base or 0) if shape == "handoffs" else base
            return self.news(self.mcp_url, bearer, self.companion, after)

        try:
            bearer = self.get_bearer(api_origin(self.mcp_url))
            answer = ask(bearer, shape)
            if shape_of(answer) != shape:
                shape = shape_of(answer)
                answer = ask(bearer, shape)
                if shape_of(answer) != shape:
                    raise PollError("format")
                with locked_state(self.companion) as state:
                    state["server_shape"] = shape
                self.log(f"server shape {shape}")
        except PollError as exc:
            return self._fail(exc.cls, exc.detail)
        self.auth_failures = 0
        since = self.first and self.resumed
        self.first = False
        if shape == "handoffs":
            return self._apply_handoffs(bases["handoffs"], answer)
        return self._apply(bases["rooms"], answer, since)

    def _apply_handoffs(self, base: int | None, answer: dict) -> str:
        now = self.clock()
        with locked_state(self.companion) as state:
            state["last_ok"] = iso(now)
            if state["handoff_cursor"] != base:
                self.log("ok skipped (cursor moved by another poller)")
                return "ok"
            state["holdoff"] = {r: t for r, t in state["holdoff"].items() if t > now}
            handoffs = answer["handoffs"]
            if not handoffs:
                state["handoff_cursor"] = answer["cursor"]
                self.log("ok handoffs=0")
                return "ok"
            if state["holdoff"].get(HANDOFF_KEY, 0) > now:
                self.log(f"ok handoffs={len(handoffs)} held")
                return "ok"
            text = render_handoffs(self.companion, handoffs)
            try:
                self.send(self.socket_path, self._token, text)
            except SessionGoneError:
                self.log("exit session gone")
                return "gone"
            except PollError:
                write_pending(self.socket_path, self.companion, {"handoffs": handoffs}, now)
                state["holdoff"][HANDOFF_KEY] = now + HOLDOFF_S
                state["last_error"] = {"class": "socket", "at": iso(now)}
                bump(state, "errors", now)
                self.log(f"pending note handoffs={len(handoffs)}")
                return "error:socket"
            state["handoff_cursor"] = answer["cursor"]
            state["holdoff"][HANDOFF_KEY] = now + HOLDOFF_S
            bump(state, "wakes", now)
            self.log(f"wake delivered handoffs={len(handoffs)}")
            return "ok"

    def _apply(self, base: int | None, answer: dict, since: bool) -> str:
        now = self.clock()
        with locked_state(self.companion) as state:
            state["last_ok"] = iso(now)
            if state["cursor"] != base:
                self.log("ok skipped (cursor moved by another poller)")
                return "ok"
            state["holdoff"] = {r: t for r, t in state["holdoff"].items() if t > now}
            delivered, delivered_row = state["delivered"], state["delivered_row"]
            fresh = self._fresh(answer["rooms"], delivered, delivered_row)
            wakeable = [
                f for f in fresh if not f["waiting"] and state["holdoff"].get(f["room"], 0) <= now
            ]
            if not wakeable:
                if not fresh:
                    self._advance(state, base, answer["cursor"])
                self.log(f"ok rooms={len(answer['rooms'])} held={len(fresh)}")
                return "ok"
            rooms = [
                {"room": f["room"], "count": f["new"], "saturated": f["saturated"]}
                for f in wakeable
            ]
            text = render(self.companion, rooms, since)
            try:
                self.send(self.socket_path, self._token, text)
            except SessionGoneError:
                self.log("exit session gone")
                return "gone"
            except PollError:
                news = {"rooms": rooms, "since_last_session": since}
                write_pending(self.socket_path, self.companion, news, now)
                for f in wakeable:
                    state["holdoff"][f["room"]] = now + HOLDOFF_S
                state["last_error"] = {"class": "socket", "at": iso(now)}
                bump(state, "errors", now)
                self.log(f"pending note rooms={len(rooms)}")
                return "error:socket"
            for f in wakeable:
                if "unanswered" in f:
                    delivered_row[f["room"]] = f["unanswered_newest"]
                else:
                    delivered[f["room"]] = f["count"]
                state["holdoff"][f["room"]] = now + HOLDOFF_S
            bump(state, "wakes", now)
            if len(wakeable) == len(fresh):
                self._advance(state, base, answer["cursor"])
            self.log(f"wake delivered rooms={len(rooms)}")
            return "ok"

    def _fresh(self, rooms: list[dict], delivered: dict, delivered_row: dict) -> list[dict]:
        """The rooms with a line not yet delivered; ``waiting`` marks one still in its grace.

        A room with ``unanswered`` counts only an unanswered row newer than the one delivered
        there; a room without it (an older server) every line beyond the delivered count.
        """
        fresh = []
        for item in rooms:
            if "unanswered" in item:
                newest = item["unanswered_newest"]
                if newest is not None and newest > int(delivered_row.get(item["room"], 0)):
                    waiting = item["unanswered_age_s"] < self.grace
                    fresh.append(dict(item, new=item["unanswered"], waiting=waiting))
                continue
            new = item["count"] - int(delivered.get(item["room"], 0))
            if new > 0:
                fresh.append(dict(item, new=new, waiting=False))
        return fresh

    @staticmethod
    def _advance(state: dict, base: int | None, cursor: int) -> None:
        state["cursor"] = cursor if base is None else max(base, cursor)
        state["delivered"] = {}
        state["delivered_row"] = {}

    def run(self, max_cycles: int | None = None) -> str:
        """Poll until the session ends or auth gives up; returns the exit reason."""
        self.start()
        wait = self.interval
        cycles = 0
        while True:
            if not self.alive(self.socket_path):
                self.log("exit session gone")
                return "gone"
            outcome = self.poll_once()
            cycles += 1
            if outcome in ("gone", "auth-exit"):
                return outcome
            if outcome.startswith("error:") and outcome != "error:socket":
                wait = min(wait * 2, self.max_interval)
            else:
                wait = self.interval
            if max_cycles is not None and cycles >= max_cycles:
                return "max-cycles"
            remaining = wait
            while remaining > 0:
                step = min(remaining, self.interval)
                self.sleep(step)
                remaining -= step
                if not self.alive(self.socket_path):
                    self.log("exit session gone")
                    return "gone"


# --- spawn (bind, SessionStart) ------------------------------------------------------------


def lock_held(socket_path: str) -> bool:
    """Whether a poller holds this socket's lock (probe: take it and release at once).

    Never creates the file: only ``main`` does, so its existence means a poller started on this
    socket (``hooks/news_on_prompt.py`` gates the stale line on it).
    """
    if fcntl is None:
        return False
    target = poller_lock_path(socket_path)
    try:
        fd = os.open(str(target), os.O_RDWR)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return True
    finally:
        os.close(fd)
    return False


def mcp_url(environ: dict) -> str:
    return environ.get("WESIDE_MCP_URL") or DEFAULT_MCP_URL


def prerequisite_gap(companion: str, environ: dict, check_login: bool) -> str | None:
    """The reason the wake cannot run, or None."""
    if fcntl is None:
        return "no file lock on this platform"
    if not NAME_RE.fullmatch(companion):
        return "the companion name is not plain (letters, digits, space, . _ -)"
    sock = environ.get("CLAUDE_CODE_MESSAGING_SOCKET", "")
    if not sock:
        return "CLAUDE_CODE_MESSAGING_SOCKET is unset (this Claude Code has no inbox socket)"
    if not environ.get("CLAUDE_CODE_MESSAGING_TOKEN"):
        return "CLAUDE_CODE_MESSAGING_TOKEN is unset"
    if not os.path.exists(sock):
        return "the inbox socket does not exist"
    exe = shutil.which("weside", path=environ.get("PATH"))
    if not exe:
        return "the weside CLI is not installed"
    if check_login:
        origin = api_origin(mcp_url(environ))
        not_logged_in = (
            f"the weside CLI is not logged in for {origin} (weside auth login --api-url {origin})"
        )
        try:
            done = subprocess.run(
                [exe, "auth", "token", "--api-url", origin],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=TOKEN_TIMEOUT_S,
                env={k: v for k, v in environ.items() if k != "CLAUDE_CODE_MESSAGING_TOKEN"},
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return not_logged_in
        if done.returncode != 0:
            return not_logged_in
    return None


def spawn(companion: str, environ: dict | None = None, check_login: bool = True) -> str:
    """Start the detached poller for this session's socket; returns one ``wake …`` line."""
    env = dict(os.environ if environ is None else environ)
    gap = prerequisite_gap(companion, env, check_login)
    if gap:
        return f"wake off: {gap}"
    sock = env["CLAUDE_CODE_MESSAGING_SOCKET"]
    news_dir().mkdir(parents=True, exist_ok=True)
    if lock_held(sock):
        return "wake on: a poller already runs for this session"
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--companion", companion],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
        env=env,
    )
    return f"wake on: poller {proc.pid} asks weside every {wake_interval(env)} s for {companion}"


# --- entry point ---------------------------------------------------------------------------


def _open_log(socket_path: str) -> Callable[[str], None]:
    target = log_path(socket_path)
    with contextlib.suppress(OSError):
        if target.stat().st_size > LOG_MAX_BYTES:
            target.unlink()

    def log(line: str) -> None:
        with contextlib.suppress(OSError):
            fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as fh:
                fh.write(f"{iso(time.time())} {line}\n")

    return log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--companion", required=True)
    parser.add_argument("--once", action="store_true", help="one cycle, then exit (tests)")
    args = parser.parse_args(argv)

    token = os.environ.pop("CLAUDE_CODE_MESSAGING_TOKEN", "")
    sock = os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET", "")
    if fcntl is None or not sock or not token or not NAME_RE.fullmatch(args.companion):
        return 2
    news_dir().mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(str(poller_lock_path(sock)), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(lock_fd)
        return 0
    log = _open_log(sock)
    interval = wake_interval()
    poller = Poller(
        args.companion,
        sock,
        token,
        mcp_url=mcp_url(dict(os.environ)),
        log=log,
        interval=interval,
    )
    log(f"start companion={slug(args.companion)} interval={interval}")
    reason = poller.run(max_cycles=1 if args.once else None)
    log(f"stop {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
