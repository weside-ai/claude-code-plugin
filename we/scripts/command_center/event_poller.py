#!/usr/bin/env python3
"""The crew's event poller: one process per crew project finds release-path and CI events.

It is the only process that calls GitHub (``gh`` through the host's shim, no credential of its
own) and ``kubectl`` (read only); every session's tail (``event_tail.py``) reads its local files
and calls no API, so N sessions cost the quota of one.

Lifecycle
    ``ensure`` (the SessionStart hook, or by hand): only in a project whose ``.weside/config.json``
    has ``events:``. A held ``flock`` on ``<dir>/poller.lock`` means a poller runs: exit 0.
    Otherwise it starts ``run`` detached (``setsid``), cwd the events folder, environment reduced
    to ``HOME``, ``PATH``, ``LANG`` (and ``WE_STATE_DIR`` when set), every ``CLAUDE_*`` removed:
    the poller never holds a session's inbox token. ``run`` takes the lock itself, so two
    ``ensure`` at once leave one poller. ``once`` runs one round under the same lock.

Per round (the loop ticks at the smallest interval: ``events.poll_interval_s``, default 300 s,
and ``events.sources.sessions.interval_s``, default 60 s; each source group runs when its own
interval is due, so GitHub is still read every ``poll_interval_s``)
    Reload ``events:`` when the config's mtime changed: an invalid block keeps the last valid one
    and sends one ``config_error`` (per distinct error) to ``machinery``. Run the sources
    (``event_sources.Round``; dedupe in ``state.json``, 14 days). Route each new event
    (``route``): per target of its kind, the presence files of running tails holding the target's
    member; a fresh, non-parked presence (any presence for a damage kind) is addressed in the row's
    ``to``; a target without one gets one row in ``delta.jsonl``, the coordinator's delta. A damage
    event no running session receives also goes at once to the coordinator's presence and as one
    board news item (``board.py news worker --kind gate``, idempotent by the event id). An
    addressed event without a ledger row after ``deliver_timeout_s`` (the tail died) lands in the
    delta too. Write ``heartbeat.json``.

An open prompt (``permission_prompt``, ``event_sources.Round.session_waiting``)
    A receiver whose own session is the waiting one is skipped for that event (it cannot read a
    line while it waits); without any other receiver the event escalates (``damage`` or not) to
    the coordinator's and the ``machinery`` member's running tails and as one board item. A route with
    ``push: true`` posts the line once through ``events.push`` (``push_notify.py`` under the
    project's wrapper, no model step) before the row is written; the row's ``push`` is ``sent`` or
    the reason there was none, and a missing push also makes the board item. Nothing here answers,
    approves or writes to the waiting session.

Latency bound (``LATENCY_BOUND_S``, 300 s): from the prompt's first sample (the row's
``source_at``) the second sample comes one sessions interval later (60 s), the tail's next cycle
within 15 s; the ledger's ``delivered_at - source_at`` is the live number.

Files under ``<crew state dir>/events/<crew id slug>/`` (``path``)
    ``poller.lock`` · ``state.json`` (dedupe, routes mtime, pending deliveries; atomic replace) ·
    ``events.jsonl`` (one row per event: ``{seq, id, kind, object, source_at, observed_at, fields,
    damage, to}``; rotated to ``.1`` at 1 MB) · ``delta.jsonl`` (``{id, kind, object, role, line,
    at, damage, reason}``) · ``ledger.jsonl`` (the tails' rows) · ``presence/<key>.json`` (the
    tails') · ``heartbeat.json`` · ``poller.log``.

Usage:
  event_poller.py ensure [--from DIR]          start the project's poller unless one runs
  event_poller.py run --root DIR [--rounds N]  the loop, in the foreground
  event_poller.py once [--from DIR]            one round, then exit (refused while a poller runs)
  event_poller.py status [--from DIR]          the poller, its last round, its mapping, the tails
  event_poller.py owners [--from DIR] [--since 24h]
                                               every red event of the window (``RED_KINDS``) with
                                               its owner: the receiving session and its ledger
                                               ``delivered_at`` (minutes from ``source_at``), else
                                               ``delta: coordinator · <epic or role>``, else
                                               ``owner none``
  event_poller.py path [--from DIR] [--delta | --ledger | --events]
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

try:
    import fcntl
except ImportError:  # pragma: no cover - no flock on this platform
    fcntl = None  # type: ignore[assignment]

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import crew as crew_mod  # noqa: E402
import epic_owner  # noqa: E402
import event_routes as routes_mod  # noqa: E402
from event_sources import Round, event_id, iso, list_sessions  # noqa: E402

ROTATE_BYTES = 1 << 20
PRESENCE_FRESH_S = 60
KEEP_ENV = ("HOME", "PATH", "LANG", "WE_STATE_DIR")
BOARD = HERE.parent / "board.py"
NOTIFIER = HERE / "push_notify.py"
LATENCY_BOUND_S = 300
SELF_SKIP_KINDS = ("permission_prompt",)  # an event about a session never goes to that session
PUSH_TIMEOUT_S = 60
_PUSH_STATUS = re.compile(
    r"^(sent|HTTP \d{3}|timeout|unreachable|no url|bad url|error [A-Za-z]{1,40})$"
)


# --- the project and its files --------------------------------------------------------------


def config_path(start: str | Path | None = None) -> Path | None:
    here = Path(start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        path = folder / ".weside" / "config.json"
        if path.is_file():
            return path
    return None


def read_block(config: Path) -> Any:
    """The raw ``events`` value of the config, None when it has none (or cannot be read)."""
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data.get("events") if isinstance(data, dict) else None


def load_crew(root: Path) -> tuple[Path | None, dict[str, Any]]:
    """The crew of ``root`` with its raw ``roles`` (transition keys included): routes may name
    any key the crew file binds."""
    try:
        crew_path, crew = crew_mod.find_and_load(root)
    except crew_mod.CrewError:
        return None, {}
    crew = dict(crew or {})
    if crew_path is not None:
        with contextlib.suppress(OSError, ValueError):
            raw = json.loads(crew_path.read_text(encoding="utf-8")).get("roles")
            if isinstance(raw, dict):
                crew["roles"] = {**raw, **(crew.get("roles") or {})}
    return crew_path, crew


def events_dir(root: Path, env: dict | None = None) -> Path:
    crew_path, crew = load_crew(root)
    base = crew_mod.state_dir(crew_path, crew or None, env)
    ident = crew_mod.crew_id(crew_path) if crew_path is not None else str(root.resolve())
    slug = re.sub(r"[^a-z0-9]+", "-", ident.lower()).strip("-") or "project"
    return base / "events" / slug


def project_root(start: str | Path | None = None) -> Path | None:
    """The project as its main worktree holds it: a poller started from a worker's worktree must
    not die with that worktree (its lock and state are the crew's, shared by every worktree)."""
    config = config_path(start)
    if config is None:
        return None
    main = crew_mod._main_worktree_dir(config) / "config.json"
    return main.parent.parent if main.is_file() else config.parent.parent


def clean_env(env: dict | None = None) -> dict[str, str]:
    """The poller's environment: ``HOME``, ``PATH``, ``LANG`` (and ``WE_STATE_DIR``) only."""
    src = os.environ if env is None else env
    out = {k: src[k] for k in KEEP_ENV if src.get(k)}
    out.setdefault("LANG", "C.UTF-8")
    return {k: v for k, v in out.items() if not k.startswith("CLAUDE")}


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, doc: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def append_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with contextlib.suppress(OSError):
        if path.stat().st_size > ROTATE_BYTES:
            os.replace(path, path.with_name(path.name + ".1"))
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def read_rows(path: Path) -> list[dict]:
    """Rows of a jsonl file and its rotated ``.1`` (older first); broken lines skipped."""
    rows: list[dict] = []
    for p in (path.with_name(path.name + ".1"), path):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            with contextlib.suppress(ValueError):
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
    return rows


def presences(folder: Path, now: float) -> list[dict]:
    """Presence files of running tails, fresh ones only."""
    out = []
    for p in sorted((folder / "presence").glob("*.json")):
        doc = read_json(p, None)
        if isinstance(doc, dict) and now - float(doc.get("heartbeat") or 0) <= PRESENCE_FRESH_S:
            out.append(doc)
    return out


# --- routing ------------------------------------------------------------------------------


def route(
    row: dict,
    block: dict,
    crew: dict,
    live: list[dict],
    owners: Callable[[str, dict, list[dict]], epic_owner.Owners] | None = None,
) -> tuple[list[dict], list[str], bool]:
    """(addressed ``[{session, as}]``, targets without a receiver, escalated to the coordinator).

    ``epic_master`` goes to the sessions ``owners`` finds (``epic_owner.Resolver.owners``); none
    found leaves it missing with ``row["owner_epic"]`` (the epic, or why there is none) for the
    delta row. A ``main_red`` row also gets ``owner``: the receiving board lines' names."""
    kind, dmg = row["kind"], row["damage"]
    if kind in SELF_SKIP_KINDS:
        waiting = (row.get("fields") or {}).get("sid")
        live = [p for p in live if not waiting or p.get("session_id") != waiting]
    to: list[dict] = []
    missing: list[str] = []
    for target in routes_mod.targets(block, kind, row.get("fields") or {}):
        if target == routes_mod.EPIC_MASTER:
            found = owners(kind, row.get("fields") or {}, live) if owners else None
            hits = found.to if found else []
            to += [
                {"session": n, "as": target}
                for n in hits
                if {"session": n, "as": target} not in to
            ]
            row["owner"] = found.names if found and hits else []
            if not hits:
                row["owner_epic"] = (found.epic or found.reason) if found else "epic unknown"
                row["owner_reason"] = found.reason if found else "epic unknown"
                missing.append(target)
            continue
        slug = routes_mod.member_of(crew, target)
        hits = [
            p for p in live if slug and p.get("member") == slug and (dmg or not p.get("parked"))
        ]
        if hits:
            to += [
                {"session": p["name"], "as": target}
                for p in hits
                if {"session": p["name"], "as": target} not in to
            ]
        else:
            missing.append(target)
    escalate = False
    routed_prompt = kind in SELF_SKIP_KINDS and bool(
        routes_mod.targets(block, kind, row.get("fields") or {})
    )
    if (dmg or routed_prompt) and not to:  # an unrouted kind stays silent
        roles = ("coordinator", "machinery") if kind in SELF_SKIP_KINDS else ("coordinator",)
        for role in roles:
            slug = routes_mod.member_of(crew, role)
            to += [
                {"session": p["name"], "as": role}
                for p in live
                if slug
                and p.get("member") == slug
                and {"session": p["name"], "as": role} not in to
            ]
        escalate = True
    return to, missing, escalate


class Poller:
    def __init__(
        self,
        root: Path,
        folder: Path,
        *,
        clock: Callable[[], float] = time.time,
        run: Callable[..., Any] = subprocess.run,
        env: dict | None = None,
        log: Callable[[str], None] | None = None,
        sessions: Callable[[], list[dict]] = list_sessions,
    ):
        self.root = Path(root)
        self.sessions = sessions
        self.dir = Path(folder)
        self.clock = clock
        self.run = run
        self.env = clean_env(env) if env is None else dict(env)
        self.log = log or (lambda _line: None)
        self.config = self.root / ".weside" / "config.json"
        self.block: dict | None = None
        self.mtime: float | None = None
        self.crew: dict = {}
        (self.dir / "presence").mkdir(parents=True, exist_ok=True)

    def reload(self, state: dict) -> list[str]:
        """Re-read ``events:`` when the config changed; the errors to report (each once)."""
        try:
            mtime = self.config.stat().st_mtime
        except OSError:
            return []
        if mtime == self.mtime and self.block is not None:
            return []
        self.mtime = mtime
        _, self.crew = load_crew(self.root)
        try:
            self.block = routes_mod.validate(read_block(self.config), self.crew)
            state.pop("config_error", None)
            return []
        except routes_mod.EventsError as exc:
            text = " ".join(str(exc).split())[:200]  # one line; the text is the repo's own config
            if state.get("config_error") == text:
                return []
            state["config_error"] = text
            return [text]

    def due(self, state: dict, block: dict, now: float) -> set[str]:
        """The source groups whose interval has passed (a few seconds early counts: the loop's
        sleep and the round's own time never line up exactly)."""
        last = state.setdefault("ran", {})
        out = set()
        intervals = {"main": int(block.get("poll_interval_s", 300))}
        sessions = routes_mod.sessions_interval(block)
        if sessions:
            intervals["sessions"] = sessions
        for group, every in intervals.items():
            if now - float(last.get(group) or 0) >= every - 5:
                out.add(group)
                last[group] = now
        return out

    def push(self, eid: str, text: str, block: dict, now: float) -> str:
        """One post of ``text`` through the project's wrapper; ``sent`` or the reason why not.
        The URL never passes here: only the wrapper's child sees it. A sent event id is written
        to ``pushed.json`` at once: a round that fails after the post never posts it again."""
        cfg = block.get("push")
        if not cfg:
            return "not configured"
        pushed_file = self.dir / "pushed.json"
        pushed = read_json(pushed_file, {})
        pushed = pushed if isinstance(pushed, dict) else {}
        if eid in pushed:
            return "sent"
        status = self._post(text, cfg)
        if status == "sent":
            pushed = {k: v for k, v in pushed.items() if now - float(v or 0) < 14 * 86400}
            pushed[eid] = now
            with contextlib.suppress(OSError):
                write_json(pushed_file, pushed)
        return status

    def _post(self, text: str, cfg: dict) -> str:
        argv = [
            *cfg["wrapper"],
            "--",
            sys.executable,
            str(NOTIFIER),
            "--env",
            cfg["url_env"],
            "--body-key",
            str(cfg.get("body_key") or "text"),
        ]
        try:
            out = self.run(
                argv,
                cwd=str(self.root),
                input=text,
                capture_output=True,
                text=True,
                timeout=PUSH_TIMEOUT_S,
                check=False,
                env=self.env,
            )
        except subprocess.TimeoutExpired:
            return "timeout"
        except (OSError, subprocess.SubprocessError):
            return "wrapper missing"
        status = (out.stdout or "").strip().splitlines()[-1:] or [""]
        if _PUSH_STATUS.match(status[0]):
            return status[0]
        return f"wrapper exit {out.returncode}" if out.returncode else "error"

    def round(self) -> dict:
        now = self.clock()
        state = read_json(self.dir / "state.json", {})
        if not isinstance(state, dict):
            state = {}
        problems = self.reload(state)
        block = self.block or {"routes": {}}
        due = self.due(state, block, now)
        rnd = Round(
            block.get("sources") or {},
            state,
            now,
            local_checks=block.get("local_checks"),
            root=str(self.root),
            env=self.env,
            run=self.run,
            due=due,
            sessions=self.sessions,
            key_rx=epic_owner.key_rx(self.crew),
        )
        found = rnd.run_all() if self.block is not None else []
        resolver = self.resolver(block, found)
        for text in problems:
            rnd.emit(
                "config_error",
                f"config:{int(now)}:{event_id(text)}",
                "config",
                iso(now),
                error=text,
            )
            found = rnd.events
        live = presences(self.dir, now)
        seq = int(state.get("seq") or 0)
        if "seq" not in state:  # a lost state file: continue past the rows the tails have seen
            seq = max(
                (int(r.get("seq") or 0) for r in read_rows(self.dir / "events.jsonl")), default=0
            )
        rows, delta = [], []
        pending = state.setdefault("pending", {})
        for ev in found:
            seq += 1
            row = ev.row(iso(now), routes_mod.damage(block, ev.kind))
            row["seq"] = seq
            to, missing, escalate = route(
                row, block, self.crew, live, resolver.owners if resolver else None
            )
            row["to"] = to
            if routes_mod.push(block, ev.kind):
                row["push"] = self.push(row["id"], routes_mod.line(row), block, now)
                if row["push"] != "sent":
                    escalate = True  # no push: the human learns of it on the board
            line = routes_mod.render(row)
            delta += [self._missing(row, target, line, now) for target in missing]
            if to:
                pending[row["id"]] = {
                    "at": now,
                    "to": [[a["session"], a["as"]] for a in to],
                    "kind": row["kind"],
                    "object": row["object"],
                    "line": line,
                    "damage": row["damage"],
                }
            if escalate:
                row["escalated"] = True
                state.setdefault("news", {})[row["id"]] = line
            rows.append(row)
        state["seq"] = seq
        append_rows(self.dir / "events.jsonl", rows)
        delta += self._timeouts(state, now, int(block.get("deliver_timeout_s", 180)))
        append_rows(self.dir / "delta.jsonl", delta)
        self._news(state)
        write_json(self.dir / "state.json", state)
        beat = {
            "pid": os.getpid(),
            "last_round": iso(now),
            "events": len(rows),
            "delta": len(delta),
            "errors": len(rnd.errors),
            "interval_s": self.tick(block),
            "poll_interval_s": int(block.get("poll_interval_s", 300)),
            "sessions_interval_s": routes_mod.sessions_interval(block),
            "push": "configured" if block.get("push") else "off",
            "routes": {k: routes_mod.targets(block, k) for k in sorted(block.get("routes") or {})},
            "sources": sorted(block.get("sources") or {}),
            "config_error": state.get("config_error"),
        }
        write_json(self.dir / "heartbeat.json", beat)
        self.log(f"round events={len(rows)} delta={len(delta)} errors={len(rnd.errors)}")
        return beat

    def resolver(self, block: dict, found: list) -> epic_owner.Resolver | None:
        """The round's view of board and snapshot, only when a found kind routes to its master."""
        if any(
            routes_mod.EPIC_MASTER in routes_mod.targets(block, e.kind, e.fields) for e in found
        ):
            return epic_owner.Resolver(self.root, self.crew)
        return None

    def _missing(self, row: dict, target: str, line: str, now: float) -> dict:
        """The delta row of a target without a receiver; ``epic_master``'s names the epic (or
        ``epic unknown`` with the PR number)."""
        if target != routes_mod.EPIC_MASTER:
            return self._delta(row, target, line, now, "no running session")
        d = self._delta(row, target, line, now, row.get("owner_reason") or "?")
        d["epic"] = row.get("owner_epic")
        fields = row.get("fields") or {}
        pr = fields.get("number") or fields.get("pr")
        if isinstance(pr, int):
            d["pr"] = pr
        return d

    @staticmethod
    def tick(block: dict) -> int:
        """The loop's sleep: the smallest interval of the configured source groups."""
        every = [int(block.get("poll_interval_s", 300)), routes_mod.sessions_interval(block) or 0]
        return min(e for e in every if e)

    @staticmethod
    def _delta(row: dict, role: str, line: str, now: float, reason: str) -> dict:
        return {
            "id": row["id"],
            "kind": row["kind"],
            "object": row["object"],
            "role": role,
            "line": line,
            "at": iso(now),
            "damage": bool(row.get("damage")),
            "reason": reason,
        }

    def _timeouts(self, state: dict, now: float, timeout: int) -> list[dict]:
        pending = state.get("pending") or {}
        if not pending:
            return []
        # handled: a line went out, or folded into one that did, or waits for the digest; a tail
        # that judged the row "not routed" (its routes differ) leaves it undelivered
        done = {
            (r.get("id"), r.get("to"))
            for r in read_rows(self.dir / "ledger.jsonl")
            if r.get("delivered") or r.get("reason") in ("folded", "digest")
        }
        out = []
        for eid in list(pending):
            p = pending[eid]
            left = [pair for pair in p.get("to", []) if (eid, pair[0]) not in done]
            if not left:
                del pending[eid]
            elif now - float(p.get("at") or 0) >= timeout:
                row = {
                    "id": eid,
                    "kind": p.get("kind"),
                    "object": p.get("object"),
                    "damage": p.get("damage"),
                }
                roles = sorted({pair[1] for pair in left}) or ["?"]
                out += [
                    self._delta(row, r, p.get("line", ""), now, "not delivered") for r in roles
                ]
                del pending[eid]
            else:
                p["to"] = left
        return out

    def _news(self, state: dict) -> None:
        """One board news item per escalated damage event, retried next round on failure."""
        news = state.get("news") or {}
        for eid in list(news):
            argv = [
                sys.executable,
                str(BOARD),
                "news",
                "worker",
                "--id",
                f"W-ev-{eid}",
                "--title",
                news[eid],
                "--kind",
                "gate",
            ]
            try:
                out = self.run(
                    argv,
                    cwd=str(self.root),
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                    env=self.env,
                    stdin=subprocess.DEVNULL,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if out.returncode == 0:
                del news[eid]


# --- lock and CLI -----------------------------------------------------------------------------


def take_lock(folder: Path) -> int | None:
    """The held lock's fd, or None when another poller holds it."""
    folder.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(folder / "poller.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def lock_held(folder: Path) -> bool:
    fd = take_lock(folder)
    if fd is None:
        return True
    os.close(fd)
    return False


def _log_to(folder: Path) -> Callable[[str], None]:
    target = folder / "poller.log"

    def log(line: str) -> None:
        with contextlib.suppress(OSError):
            if target.exists() and target.stat().st_size > ROTATE_BYTES:
                target.unlink()
            with target.open("a", encoding="utf-8") as fh:
                fh.write(f"{iso(time.time())} {line}\n")

    return log


def ensure(start: str | Path | None = None, env: dict | None = None) -> str:
    root = project_root(start)
    if root is None or read_block(root / ".weside" / "config.json") is None:
        return "events: off (no events: block)"
    if fcntl is None:
        return "events: off (no file lock on this platform)"
    folder = events_dir(root, env)
    if lock_held(folder):
        return "events: poller runs"
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "run", "--root", str(root)],
        cwd=str(folder),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
        env=clean_env(env),
    )
    return f"events: poller {proc.pid} started"


def run_loop(root: Path, rounds: int | None = None) -> int:
    folder = events_dir(root)
    fd = take_lock(folder)
    if fd is None:
        print("events: another poller holds the lock", file=sys.stderr)
        return 0
    log = _log_to(folder)
    poller = Poller(root, folder, log=log)
    log(f"start pid={os.getpid()}")
    n = 0
    while True:
        if not poller.config.is_file():
            log("stop: the project's config is gone")
            os.close(fd)  # frees the lock for the next ensure
            return 0
        try:
            beat = poller.round()
        except Exception as exc:
            log(f"round failed {type(exc).__name__}")
            beat = {"interval_s": 300}
        n += 1
        if rounds is not None and n >= rounds:
            return 0
        time.sleep(max(30, int(beat.get("interval_s") or 300)))


RED_KINDS = ("main_red", "rc_verdict_red")


def parse_since(text: str) -> float:
    """``24h``, ``90m``, ``2d`` or plain seconds → seconds."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([smhd]?)", str(text).strip())
    if not m:
        raise ValueError(f"since: {text!r} is no duration (24h, 90m, 2d)")
    return float(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]


def owners_report(folder: Path, now: float, since_s: float) -> list[str]:
    """One line per red event of the window: ``<source_at> <kind> <object> · owner …``."""
    from event_sources import epoch  # noqa: PLC0415

    ledger: dict[str, list[dict]] = {}
    for r in read_rows(folder / "ledger.jsonl"):
        if r.get("delivered"):
            ledger.setdefault(str(r.get("id")), []).append(r)
    delta: dict[str, list[dict]] = {}
    for r in read_rows(folder / "delta.jsonl"):
        delta.setdefault(str(r.get("id")), []).append(r)
    out = []
    for row in read_rows(folder / "events.jsonl"):
        if row.get("kind") not in RED_KINDS:
            continue
        at = epoch(row.get("source_at")) or epoch(row.get("observed_at"))
        if at is None or now - at > since_s:
            continue
        head = f"{row.get('source_at') or row.get('observed_at')} {row.get('kind')} {row.get('object')}"
        hits = ledger.get(str(row.get("id"))) or []
        if hits:
            parts = []
            for h in hits:
                done = epoch(h.get("delivered_at"))
                mins = f" ({int((done - at) // 60)} min)" if done is not None else ""
                parts.append(f"{h.get('to')} delivered {h.get('delivered_at')}{mins}")
            out.append(f"{head} · owner " + "; ".join(parts))
        elif delta.get(str(row.get("id"))):
            names = sorted(
                {str(d.get("epic") or d.get("role") or "?") for d in delta[str(row["id"])]}
            )
            out.append(f"{head} · delta: coordinator · {', '.join(names)}")
        else:
            out.append(f"{head} · owner none")
    return out


def status(start: str | Path | None = None) -> int:
    root = project_root(start)
    if root is None:
        print("events: no .weside/config.json")
        return 1
    folder = events_dir(root)
    beat = read_json(folder / "heartbeat.json", {})
    print(f"poller: {'runs' if lock_held(folder) else 'not running'} · {folder}")
    print(
        f"last round: {beat.get('last_round', 'never')} · interval {beat.get('interval_s', '?')} s"
    )
    if beat.get("sessions_interval_s"):
        print(
            f"source sessions · interval {beat['sessions_interval_s']} s · "
            f"github every {beat.get('poll_interval_s', '?')} s · push {beat.get('push', 'off')}"
        )
    if beat.get("config_error"):
        print(f"config error: {beat['config_error']}")
    if beat.get("sources"):
        print(f"sources {', '.join(beat['sources'])}")
    for kind, to in (beat.get("routes") or {}).items():
        print(f"route {kind} -> {', '.join(to)}")
    for p in presences(folder, time.time()):
        print(
            f"tail {p.get('name')} · {p.get('member') or 'master'} · {','.join(p.get('roles') or [])}"
            f"{' · parked' if p.get('parked') else ''}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("ensure", "once", "status", "path", "owners"):
        p = sub.add_parser(name)
        p.add_argument("--from", dest="start")
        if name == "owners":
            p.add_argument("--since", default="24h")
        if name == "path":
            g = p.add_mutually_exclusive_group()
            for f in ("delta", "ledger", "events"):
                g.add_argument(f"--{f}", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--root", required=True)
    r.add_argument("--rounds", type=int)
    a = ap.parse_args(argv)
    if a.cmd == "ensure":
        print(ensure(a.start))
        return 0
    if a.cmd == "run":
        return run_loop(Path(a.root), a.rounds)
    if a.cmd == "status":
        return status(a.start)
    root = project_root(a.start)
    if root is None:
        print("events: no .weside/config.json", file=sys.stderr)
        return 1
    folder = events_dir(root)
    if a.cmd == "owners":
        for text in owners_report(folder, time.time(), parse_since(a.since)):
            print(text)
        return 0
    if a.cmd == "path":
        name = next((f for f in ("delta", "ledger", "events") if getattr(a, f)), None)
        print(folder / f"{name}.jsonl" if name else folder)
        return 0
    fd = take_lock(folder)  # once
    if fd is None:
        print("events: a poller runs; its next round comes within its interval", file=sys.stderr)
        return 1
    beat = Poller(root, folder, log=_log_to(folder)).round()
    print(json.dumps(beat, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
