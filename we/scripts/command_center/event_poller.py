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

Per round (``events.poll_interval_s``, default 300 s)
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
import event_routes as routes_mod  # noqa: E402
from event_sources import Round, event_id, iso  # noqa: E402

ROTATE_BYTES = 1 << 20
PRESENCE_FRESH_S = 60
KEEP_ENV = ("HOME", "PATH", "LANG", "WE_STATE_DIR")
BOARD = HERE.parent / "board.py"


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
    config = config_path(start)
    return config.parent.parent if config is not None else None


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
    row: dict, block: dict, crew: dict, live: list[dict]
) -> tuple[list[dict], list[str], bool]:
    """(addressed ``[{session, as}]``, targets without a receiver, escalated to the coordinator)."""
    kind, dmg = row["kind"], row["damage"]
    to: list[dict] = []
    missing: list[str] = []
    for target in routes_mod.targets(block, kind):
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
    if dmg and not to:
        slug = routes_mod.member_of(crew, "coordinator")
        to += [
            {"session": p["name"], "as": "coordinator"}
            for p in live
            if slug and p.get("member") == slug
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
    ):
        self.root = Path(root)
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

    def round(self) -> dict:
        now = self.clock()
        state = read_json(self.dir / "state.json", {})
        if not isinstance(state, dict):
            state = {}
        problems = self.reload(state)
        block = self.block or {"routes": {}}
        rnd = Round(
            block.get("sources") or {},
            state,
            now,
            local_checks=block.get("local_checks"),
            root=str(self.root),
            env=self.env,
            run=self.run,
        )
        found = rnd.run_all() if self.block is not None else []
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
        rows, delta = [], []
        pending = state.setdefault("pending", {})
        for ev in found:
            seq += 1
            row = ev.row(iso(now), routes_mod.damage(block, ev.kind))
            row["seq"] = seq
            to, missing, escalate = route(row, block, self.crew, live)
            row["to"] = to
            line = routes_mod.render(row)
            for target in missing:
                delta.append(self._delta(row, target, line, now, "no running session"))
            if to:
                pending[row["id"]] = {
                    "at": now,
                    "to": [a["session"] for a in to],
                    "kind": row["kind"],
                    "object": row["object"],
                    "line": line,
                    "damage": row["damage"],
                    "as": [a["as"] for a in to],
                }
            if escalate:
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
            "interval_s": int(block.get("poll_interval_s", 300)),
            "routes": {k: routes_mod.targets(block, k) for k in sorted(block.get("routes") or {})},
            "config_error": state.get("config_error"),
        }
        write_json(self.dir / "heartbeat.json", beat)
        self.log(f"round events={len(rows)} delta={len(delta)} errors={len(rnd.errors)}")
        return beat

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
        done = {(r.get("id"), r.get("to")) for r in read_rows(self.dir / "ledger.jsonl")}
        out = []
        for eid in list(pending):
            p = pending[eid]
            left = [s for s in p.get("to", []) if (eid, s) not in done]
            if not left:
                del pending[eid]
            elif now - float(p.get("at") or 0) >= timeout:
                row = {
                    "id": eid,
                    "kind": p.get("kind"),
                    "object": p.get("object"),
                    "damage": p.get("damage"),
                }
                roles = sorted(set(p.get("as") or [])) or ["?"]
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
        try:
            beat = poller.round()
        except Exception as exc:
            log(f"round failed {type(exc).__name__}")
            beat = {"interval_s": 300}
        n += 1
        if rounds is not None and n >= rounds:
            return 0
        time.sleep(max(30, int(beat.get("interval_s") or 300)))


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
    if beat.get("config_error"):
        print(f"config error: {beat['config_error']}")
    for kind, to in (beat.get("routes") or {}).items():
        print(f"route {kind} -> {', '.join(to)}")
    for p in presences(folder, time.time()):
        print(
            f"tail {p.get('name')} · {p.get('member')} · {','.join(p.get('roles') or [])}"
            f"{' · parked' if p.get('parked') else ''}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("ensure", "once", "status", "path"):
        p = sub.add_parser(name)
        p.add_argument("--from", dest="start")
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
