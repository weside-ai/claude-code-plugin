#!/usr/bin/env python3
"""we-crewd: the command centre as a read-only web page, served from the workspace host.

Usage:
  crewd.py serve --bind IP [--port 8787]   the server (the launcher passes the pod IP)
  crewd.py pod-ip                           the address `serve` binds to, for the launcher
  crewd.py probe                            `{url, alive, bind}` for the Zentrale pane

Seam: the server renders what `zentrale.py --json` prints (every section, so what lies with the
owner is in it) and the data block `flow_intervals.py --page-data` prints; it has no source of its
own and no control. A background thread runs both with a fixed argv and a timeout, the full read
every `TTL_S` seconds; requests only read the rendered snapshot in memory: no subprocess, no
`open()` per request. The page answers at once from the last snapshot: at start the thread loads
the cache file (`cache_path()`, mode 600 from its first byte, rendered fields and `fetched_at`
only; loaded back through the same allowlist and redaction), then the fast read
(`zentrale.py --fast`), then the full reads.

Bind. Only the pod IP: `serve` refuses a loopback or wildcard address. Loopback stays closed on
purpose, because a userspace tailscaled hands incoming tailnet connections to 127.0.0.1, a path
past the proxy's tailnet gate. The gate is the network policy in front (only the proxy reaches the
port); the peer check here is the second line: a connection from an address outside
`zentrale.peers` (crew file, the proxy's networks) and the server's own address is closed unanswered,
its address named once on stderr. The crew file is the local one every reader on the host uses
(`crew.find`), read again in the background when it changes (`CrewWatch`), so a pulled checkout
reaches the peer check without a restart.

Fields. Every row passes a field allowlist (`ROW_FIELDS`, `SESSION_FIELDS`, `ACCOUNT_FIELDS`);
accounts show only their profile name. Every free text passes `redaction.redact` (marker
`[redacted]`) and `html.escape`; the flow page's data block is JSON with `<`, `>`, `&` escaped, its
values reach the DOM through `textContent` only (`flow_intervals.JS`). Every href is a fixed route
or a GitHub pull request URL whose owner is in `zentrale.link_hosts`, never a copied field. An
unknown `schema_version` renders an error row instead of data.

Routes, GET and HEAD only (every other verb 405, unknown path 404, the raw path matched exactly,
never decoded, never mapped onto the disk, so no file server): `/crew/`, `/crew/flow`,
`/crew/healthz`, `/crew/static/{crew.css,flow.css,flow.js}` from strings in memory; `/crew`
redirects to `/crew/`. Every response carries `HEADERS` (CSP without inline script or style).
Limits: `THREADS` worker threads, a socket timeout of `TIMEOUT_S`, a body cap of `MAX_BODY`.
"""

from __future__ import annotations

import argparse
import contextlib
import html
import http.server
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import crew as crew_mod  # noqa: E402
import flow_intervals as fi  # noqa: E402
import redaction  # noqa: E402

PORT = 8787
SCHEMA_VERSION = 1  # zentrale.py's document this renders
TTL_S = 60
FAST_TIMEOUT_S = 20
FULL_TIMEOUT_S = 90
THREADS = 8
TIMEOUT_S = 5
MAX_BODY = 4 * 1024 * 1024
MAX_TEXT = 300
RELOAD_S = 30
CREW_CHECK_S = 10
MAX_REFUSED_LOGGED = 1024  # refused peers named on stderr, once each; past it, silence
MARKER = "[redacted]"

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
HEADERS = {
    "Content-Security-Policy": CSP,
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

ROW_FIELDS = ("kind", "item", "title", "holder", "for", "master", "age", "since_note", "classes")
SESSION_FIELDS = ("name", "role", "doing", "age", "waits", "waiting_on", "blocked_kind", "starter")
SESSION_FIELDS += ("plugin",)
ACCOUNT_FIELDS = ("name", "active", "in_rotation", "threshold", "status", "stale", "red")
PR_ITEM = re.compile(r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)#([0-9]{1,7})")


# --- address --------------------------------------------------------------------------------


def pod_ip() -> str:
    """The host's own non-loopback address: the hostname's, else the default route's source."""
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ipaddress.ip_address(ip).is_loopback:
            return ip
    except (OSError, ValueError):
        pass
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("192.0.2.1", 9))  # UDP connect sends nothing; it only picks the route
        return s.getsockname()[0]


def check_bind(ip: str) -> str:
    """`ip` when it is one concrete, non-loopback address; ValueError otherwise."""
    addr = ipaddress.ip_address(ip)
    if addr.is_loopback or addr.is_unspecified:
        raise ValueError(f"refusing to bind {ip}: loopback and wildcard stay closed")
    return str(addr)


def peers_of(crew: dict, bind: str) -> list:
    nets = [
        ipaddress.ip_network(p, strict=False)
        for p in (crew.get("zentrale") or {}).get("peers") or []
    ]
    return [*nets, ipaddress.ip_network(bind)]


def peer_allowed(addr: str, peers: list) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in net for net in peers)


class CrewWatch:
    """The crew file in force for the server's cwd (`crew.find`, the file every reader on the host
    uses), read again when its stat (path, mtime, size, inode) changes; `crew_loop` looks every
    `CREW_CHECK_S` seconds, never a request. A file that no longer loads keeps the last good peers
    and link hosts, so a broken edit does not shut the proxy out, and is named once on stderr."""

    def __init__(self, bind: str, cwd: Path | None = None):
        self.bind, self.cwd = bind, cwd
        self.key: tuple | None = None
        self.peers: list = peers_of({}, bind)
        self.link_hosts: list = []

    def _stat_key(self) -> tuple | None:
        path = crew_mod.find(self.cwd)
        if path is None:
            return None
        try:
            st = path.stat()
        except OSError:
            return (str(path),)
        return (str(path), st.st_mtime_ns, st.st_size, st.st_ino)

    def check(self) -> bool:
        """Read the crew again when its file changed; True when peers or link hosts were set."""
        key = self._stat_key()
        if key == self.key:
            return False
        self.key = key
        if key is None:
            crew: dict = crew_mod.DEFAULTS
        else:
            try:
                crew = crew_mod.load(Path(key[0]))
            except crew_mod.CrewError as exc:
                print(f"we-crewd: crew not reloaded, kept the last peers: {exc}", file=sys.stderr)
                return False
        self.peers = peers_of(crew, self.bind)
        self.link_hosts = list((crew.get("zentrale") or {}).get("link_hosts") or [])
        print(
            f"we-crewd: crew {key[0] if key else '(none)'}: {len(self.peers) - 1} peer networks",
            file=sys.stderr,
        )
        return True


def crew_tick(watch: CrewWatch, server, state) -> None:
    """One look at the crew file; a change goes to the server's peer check and the pages' links."""
    if watch.check():
        server.peers = watch.peers  # one attribute swap: a request reads the old or the new list
        state.relink(watch.link_hosts)


def crew_loop(watch: CrewWatch, server, state, stop: threading.Event) -> None:
    while not stop.wait(CREW_CHECK_S):
        try:
            crew_tick(watch, server, state)
        except Exception as exc:  # the loop outlives one bad read
            print(f"we-crewd: crew check failed: {type(exc).__name__}", file=sys.stderr)


# --- fields ---------------------------------------------------------------------------------


def clean(value) -> str:
    text = redaction.redact(str(value if value is not None else ""), MARKER)
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


def deep_clean(value):
    """Every string of a JSON value redacted (the flow page's data block)."""
    if isinstance(value, str):
        return redaction.redact(value, MARKER)
    if isinstance(value, list):
        return [deep_clean(v) for v in value]
    if isinstance(value, dict):
        return {k: deep_clean(v) for k, v in value.items()}
    return value


def _pick(row: dict, fields) -> dict:
    out = {}
    for f in fields:
        v = row.get(f) if isinstance(row, dict) else None
        if isinstance(v, bool) or v is None or isinstance(v, (int, float)):
            out[f] = v
        elif isinstance(v, list):
            out[f] = [clean(x) for x in v]
        else:
            out[f] = clean(v)
    return out


# the flow page's data block (`flow_intervals.page_data`): the keys its JS reads, per list
FLOW_LISTS = {
    "intervals": (
        "who",
        "kind",
        "start",
        "end",
        "id",
        "key",
        "label",
        "role",
        "source",
        "waiting_on",
        "edge_to",
    ),
    "lanes": (
        "name",
        "group",
        "parent",
        "role",
        "session_id",
        "started_at",
        "starter",
        "first",
        "last",
    ),
    "gaps": ("reason", "start", "end", "source"),
    "gap_rows": ("who", "kind", "start", "end", "id", "reason", "source"),
}
FLOW_KEYS = ("project", "attribution", "window", "interval_s", "header", "reserved", "summary")


def flow_of(data: dict) -> dict:
    """The allowlisted, redacted fields of `flow_intervals.py --page-data`; the lists' rows keep
    only `FLOW_LISTS` keys, the rest only `FLOW_KEYS` (the summary is computed numbers and names)."""
    if not isinstance(data, dict):
        return {}
    out = {k: deep_clean(data.get(k)) for k in FLOW_KEYS}
    for key, fields in FLOW_LISTS.items():
        out[key] = [
            {f: deep_clean(r.get(f)) for f in fields if f in r}
            for r in data.get(key) or []
            if isinstance(r, dict)
        ]
    return out


def snapshot_of(doc: dict) -> dict:
    """The allowlisted, redacted fields of a `zentrale.py --json` document."""
    if not isinstance(doc, dict) or doc.get("schema_version") != SCHEMA_VERSION:
        return {
            "error": f"zentrale.py schema_version {clean(doc.get('schema_version') if isinstance(doc, dict) else None)}"
            f", this server reads {SCHEMA_VERSION}"
        }
    sec = doc.get("sections") or {}
    ci = sec.get("ci") or {}
    accounts = []
    for a in sec.get("accounts") or []:
        acc = _pick(a, ACCOUNT_FIELDS)
        for window in ("five_hour", "seven_day"):
            pct = (a.get(window) or {}).get("pct") if isinstance(a, dict) else None
            acc[window] = (
                pct if isinstance(pct, (int, float)) and not isinstance(pct, bool) else None
            )
        accounts.append(acc)
    sources = {}
    for name, s in (doc.get("sources") or {}).items():
        if isinstance(s, dict):
            sources[clean(name)] = {
                "fetched_at": clean(s.get("fetched_at") or ""),
                "gap": clean(s.get("gap") or ""),
            }
    return {
        "project": clean(doc.get("project")),
        "generated_at": clean(doc.get("built_at")),
        "fast": bool(doc.get("fast")),
        "header": [clean(h) for h in doc.get("header") or []],
        "gaps": [clean(g) for g in doc.get("gaps") or []],
        "sources": sources,
        "owner": [_pick(r, ROW_FIELDS) for r in sec.get("owner") or []],
        "red": [_pick(r, ROW_FIELDS) for r in sec.get("red") or []],
        "waiting": [_pick(r, ROW_FIELDS) for r in sec.get("waiting") or []],
        "working": [_pick(r, SESSION_FIELDS) for r in sec.get("working") or []],
        "ci": {
            "repos": [
                {
                    "repo": clean(r.get("repo")),
                    "default_head": clean(r.get("default_head")),
                    "checks": [
                        _pick(c, ("pr", "name", "status", "age")) for c in r.get("checks") or []
                    ],
                }
                for r in ci.get("repos") or []
                if isinstance(r, dict)
            ],
            "locks": clean(ci.get("locks")),
        },
        "accounts": accounts,
    }


def pr_href(item: str, link_hosts) -> str | None:
    """`https://github.com/<owner>/<repo>/pull/<n>` for an item `owner/repo#n` whose owner (or
    owner/repo) is in `link_hosts`; None otherwise."""
    m = PR_ITEM.fullmatch(item or "")
    if not m:
        return None
    owner, repo, num = m.groups()
    allowed = {h.rstrip("/") for h in link_hosts or []}
    if f"github.com/{owner}" not in allowed and f"github.com/{owner}/{repo}" not in allowed:
        return None
    return f"https://github.com/{owner}/{repo}/pull/{num}"


# --- pages ----------------------------------------------------------------------------------

e = html.escape


def _row_html(r: dict, link_hosts, cls: str = "") -> str:
    parts = [r.get("holder")]
    if r.get("for"):
        parts.append(f"for {r['for']}" + (f" ({r['master']})" if r.get("master") else ""))
    parts.append(" ".join(x for x in (r.get("age") or "?", r.get("since_note")) if x))
    if r.get("classes"):
        parts.append(", ".join(r["classes"]))
    href = pr_href(r.get("item", ""), link_hosts) if r.get("kind") == "pr" else None
    item = f'<a href="{e(href)}">{e(r["item"])}</a>' if href else e(r.get("item") or "")
    meta = " · ".join(e(p) for p in parts if p)
    title = f'<div class="title">{e(r["title"])}</div>' if r.get("title") else ""
    return f'<li class="row {cls}"><div class="head"><b>{item}</b> <span class="meta">{meta}</span></div>{title}</li>'


def _session_html(s: dict) -> str:
    waits = (
        f" · waits: {s.get('waiting_on') or '?'}"
        + (f" ({s['blocked_kind']})" if s.get("blocked_kind") else "")
        if s.get("waits")
        else ""
    )
    meta = f"{s.get('role') or ''} · since {s.get('age') or '?'}{waits} · {s.get('plugin') or ''}"
    if s.get("starter"):
        meta += f" · started by {s['starter']}"
    cls = "row waits" if s.get("waits") else "row"
    lead = "└ " if s.get("role") == "worker" else ""
    return (
        f'<li class="{cls}"><div class="head"><b>{e(lead + (s.get("name") or "?"))}</b> '
        f'<span class="meta">{e(meta)}</span></div><div class="title">{e(s.get("doing") or "-")}</div></li>'
    )


def _section(label: str, items: list) -> str:
    body = "".join(items) or '<li class="row none">nothing</li>'
    return f"<section><h2>{e(label)}</h2><ul>{body}</ul></section>"


def _pct(v) -> str:
    return "?" if v is None else f"{round(v)} %"


def render_crew(snap: dict | None, status: dict, link_hosts) -> str:
    """The crew view: with the owner, red, waiting, working, CI, accounts, and the page's state."""
    state = [f"generated_at {status.get('generated_at') or '-'}"]
    if status.get("error"):
        state.append(f"last refresh failed: {status['error']}")
    out = []
    if snap is None:
        out.append('<p class="gap">No snapshot yet.</p>')
    elif snap.get("error"):
        out.append(f'<p class="gap">{e(snap["error"])}</p>')
    else:
        out += [f'<p class="hd">{e(h)}</p>' for h in snap["header"]]
        out += [f'<p class="gap">⚠ {e(g)}</p>' for g in snap["gaps"]]
        out.append(
            _section("With the owner", [_row_html(r, link_hosts, "owner") for r in snap["owner"]])
        )
        out.append(_section("Red", [_row_html(r, link_hosts, "red") for r in snap["red"]]))
        out.append(_section("Waiting", [_row_html(r, link_hosts) for r in snap["waiting"]]))
        out.append(_section("Working", [_session_html(s) for s in snap["working"]]))
        ci = []
        for repo in snap["ci"]["repos"]:
            checks = "".join(
                f'<div class="title">#{e(str(c.get("pr") or ""))} {e(c.get("name") or "")} {e(str(c.get("status") or "").lower())} · {e(c.get("age") or "?")}</div>'
                for c in repo["checks"]
            )
            ci.append(
                f'<li class="row"><div class="head"><b>{e(repo["repo"])}</b> <span class="meta">{e(repo["default_head"])}</span></div>{checks}</li>'
            )
        if ci:
            ci.append(f'<li class="row none">{e(snap["ci"]["locks"])}</li>')
        out.append(_section("CI", ci))
        acc = []
        for a in snap["accounts"]:
            flags = (" (active)" if a.get("active") else "") + (
                "" if a.get("in_rotation") else " (off)"
            )
            limit = (
                f" · limit {round(a['threshold'])} %"
                if isinstance(a.get("threshold"), (int, float))
                else ""
            )
            text = f"5h {_pct(a['five_hour'])} · 7d {_pct(a['seven_day'])}{limit} · {'stale' if a.get('stale') else a.get('status') or '?'}"
            cls = "row red" if a.get("red") else "row"
            acc.append(
                f'<li class="{cls}"><div class="head"><b>{e((a.get("name") or "?") + flags)}</b> <span class="meta">{e(text)}</span></div></li>'
            )
        out.append(_section("Accounts", acc))
        fetched = [
            f"{name} fetched_at {s['fetched_at']}"
            for name, s in snap["sources"].items()
            if s.get("fetched_at")
        ]
        state.append(
            f"zentrale built_at {snap['generated_at']}" + (" (fast)" if snap["fast"] else "")
        )
        state += fetched
    project = (snap or {}).get("project") or "?"
    return _page(
        f"Zentrale · {project}",
        "crew.css",
        f'<header><h1>{e(f"Zentrale · {project}")}</h1><nav><a href="/crew/flow">Flow</a></nav></header>'
        + "".join(out)
        + "<footer>"
        + "".join(f"<div>{e(s)}</div>" for s in state)
        + "</footer>",
        refresh=True,
    )


def render_flow(data: dict | None, status: dict) -> str:
    """The flow page: `flow_intervals.py`'s page under the CSP: CSS and JS as same-origin assets,
    the data as a non-executing JSON block with `<`, `>`, `&` escaped."""
    nav = '<header><nav><a href="/crew/">← Zentrale</a></nav></header>'
    if data is None:
        return _page("Crew flow", "flow.css", nav + '<p class="gap">No flow snapshot yet.</p>')
    body = (
        nav
        + '<main id="app"></main>'
        + f'<script type="application/json" id="flow-data">{fi.embed_json(data)}</script>'
        + '<script src="/crew/static/flow.js"></script>'
        + f"<footer><div>{e('generated_at ' + (status.get('flow_at') or '-'))}</div></footer>"
    )
    return _page(f"Crew flow · {data.get('project') or '?'}", "flow.css", body)


def _page(title: str, css: str, body: str, refresh: bool = False) -> str:
    meta = f'<meta http-equiv="refresh" content="{RELOAD_S}">' if refresh else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"{meta}<title>{e(title)}</title>"
        f'<link rel="stylesheet" href="/crew/static/{css}"></head><body>{body}</body></html>'
    )


CREW_CSS = """
:root{--bg:#fbfbf9;--fg:#1d1d1b;--mut:#6b6b66;--line:#e2e2dc;--red:#c23b31;--warn:#b5730f;--link:#2a5db0}
@media (prefers-color-scheme:dark){:root{--bg:#151514;--fg:#ececea;--mut:#a0a09a;--line:#2e2e2b;
--red:#ef6b60;--warn:#e3a443;--link:#7aa7ef}}
*{box-sizing:border-box}
body{margin:0;padding:12px 16px;background:var(--bg);color:var(--fg);
font:15px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;overflow-wrap:anywhere}
header{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:baseline}
h1{font-size:18px;margin:0}h2{font-size:15px;margin:16px 0 4px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}
a{color:var(--link)}ul{list-style:none;margin:0;padding:0}
.row{padding:6px 0;border-bottom:1px solid var(--line)}.row.none{color:var(--mut)}
.meta{color:var(--mut)}.title{margin-top:2px}
.red b,.red .title{color:var(--red)}.owner b,.waits b{color:var(--warn)}
.gap{color:var(--warn)}.hd{color:var(--mut);margin:2px 0}
footer{margin-top:20px;color:var(--mut);font-size:13px}
"""

ASSETS = {
    "/crew/static/crew.css": ("text/css; charset=utf-8", CREW_CSS),
    "/crew/static/flow.css": (
        "text/css; charset=utf-8",
        fi.CSS
        + "header{padding:8px 16px}header a{color:inherit}footer{padding:8px 16px;font-size:13px;opacity:.7}",
    ),
    "/crew/static/flow.js": ("text/javascript; charset=utf-8", fi.JS),
}


# --- state and refresh ----------------------------------------------------------------------


def cache_path() -> Path:
    return Path(tempfile.gettempdir()) / f"we-crewd-{os.getuid()}.json"


def write_cache(path: Path, payload: dict) -> None:
    """`payload` to `path` with mode 600 from its first byte: a temp file opened with `O_EXCL` and
    mode 600, then `os.replace`."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def read_cache(path: Path) -> dict | None:
    try:
        if path.stat().st_uid != os.getuid():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


class State:
    """The rendered pages in memory; the refresh thread is its only writer."""

    def __init__(self, link_hosts=()):
        self.lock = threading.Lock()
        self.link_hosts = list(link_hosts)
        self.snap: dict | None = None
        self.flow: dict | None = None
        self.status: dict = {"generated_at": None, "error": None, "flow_at": None}
        self.pages: dict = {}

    def set(self, snap=None, flow=None, error=None, at=None):
        with self.lock:
            if snap is not None:
                self.snap = snap
                self.status["generated_at"] = at
            if flow is not None:
                self.flow = flow
                self.status["flow_at"] = at
            self.status["error"] = error
            self.pages = (
                {
                    "/crew/": render_crew(self.snap, self.status, self.link_hosts).encode("utf-8"),
                    "/crew/flow": render_flow(self.flow, self.status).encode("utf-8"),
                }
                if (self.snap is not None or self.flow is not None)
                else {}
            )

    def fail(self, error: str) -> None:
        """Name `error` on the pages; a snapshot that no longer renders is dropped (503)."""
        with self.lock:
            self.status["error"] = error
            try:
                self.pages = {
                    "/crew/": render_crew(self.snap, self.status, self.link_hosts).encode("utf-8"),
                    "/crew/flow": render_flow(self.flow, self.status).encode("utf-8"),
                }
            except Exception:  # a broken snapshot is dropped, not served
                self.snap = self.flow = None
                self.pages = {}

    def page(self, path: str) -> bytes | None:
        with self.lock:
            return self.pages.get(path)

    def relink(self, link_hosts) -> None:
        """New link hosts from a reloaded crew; the next `set` renders with them."""
        with self.lock:
            self.link_hosts = list(link_hosts)

    def cache_payload(self) -> dict:
        with self.lock:
            return {
                "fetched_at": self.status["generated_at"],
                "flow_at": self.status["flow_at"],
                "snap": self.snap,
                "flow": self.flow,
            }


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_json(argv: list, timeout: float, cwd: str | None) -> dict:
    """One read layer: a fixed argv with a timeout, its stdout as JSON."""
    out = subprocess.run(
        argv, capture_output=True, text=True, timeout=timeout, cwd=cwd, check=False
    )
    if out.returncode != 0:
        raise RuntimeError(f"{Path(argv[2]).name} exit {out.returncode}")
    return json.loads(out.stdout)


ZENTRALE = HERE / "zentrale.py"
FLOW = HERE.parent / "flow_intervals.py"


def refresh_once(
    state: State, cwd: str | None, *, fast: bool, cache: Path, runner=run_json
) -> None:
    """One read of the layers into `state` and the cache file; a failure keeps the last snapshot
    and names the error."""
    py = [sys.executable, "-I"]
    error = None
    snap = flow = None
    try:
        doc = runner(
            [*py, str(ZENTRALE), "--json", *(["--fast"] if fast else [])],
            FAST_TIMEOUT_S if fast else FULL_TIMEOUT_S,
            cwd,
        )
        snap = snapshot_of(doc)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        error = f"zentrale: {clean(exc)}"
    if not fast:
        try:
            flow = flow_of(
                runner([*py, str(FLOW), "--page-data", "--since", "1d"], FULL_TIMEOUT_S, cwd)
            )
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            error = (error + "; " if error else "") + f"flow: {clean(exc)}"
    state.set(snap=snap, flow=flow, error=error, at=_now())
    try:
        write_cache(cache, state.cache_payload())
    except OSError as exc:
        print(f"we-crewd: cache not written: {exc}", file=sys.stderr)


def _guarded(state: State, step, *args, **kwargs) -> None:
    """One refresh step; an error no step foresaw keeps the thread alive and shows as the page's
    "last refresh failed" line (a page it cannot render answers 503, never a 200 with old data)."""
    try:
        step(*args, **kwargs)
    except Exception as exc:  # the refresh thread must not die silently
        print(f"we-crewd: refresh: {type(exc).__name__}: {clean(exc)}", file=sys.stderr)
        state.fail(f"{type(exc).__name__}: {clean(exc)}")


SNAP_KEYS = ("project", "generated_at", "fast", "header", "gaps", "sources", "owner", "red")
SNAP_KEYS += ("waiting", "working", "ci", "accounts")


def restore_snapshot(snap) -> dict | None:
    """A cached snapshot through `snapshot_of` again (allowlist and redaction), so the cache file
    is never trusted as rendered; None for a payload without the snapshot's shape."""
    if not isinstance(snap, dict):
        return None
    if set(snap) == {"error"}:
        return {"error": clean(snap["error"])}
    if not set(SNAP_KEYS) <= set(snap):
        return None
    accounts = [
        {
            **a,
            "five_hour": {"pct": a.get("five_hour")},
            "seven_day": {"pct": a.get("seven_day")},
        }
        for a in snap.get("accounts") or []
        if isinstance(a, dict)
    ]
    return snapshot_of(
        {
            "schema_version": SCHEMA_VERSION,
            "project": snap.get("project"),
            "built_at": snap.get("generated_at"),
            "fast": snap.get("fast"),
            "header": snap.get("header"),
            "gaps": snap.get("gaps"),
            "sources": snap.get("sources"),
            "sections": {
                **{k: snap.get(k) for k in ("owner", "red", "waiting", "working", "ci")},
                "accounts": accounts,
            },
        }
    )


def _load_cache(state: State, cache: Path) -> None:
    """The cache file into `state`, both parts through their allowlist again."""
    cached = read_cache(cache)
    if not cached:
        return
    snap = restore_snapshot(cached.get("snap"))
    flow = flow_of(cached["flow"]) if isinstance(cached.get("flow"), dict) else None
    if snap is not None or flow is not None:
        state.set(snap=snap, flow=flow, at=cached.get("fetched_at"))


def refresh_loop(state: State, cwd: str | None, cache: Path, stop: threading.Event) -> None:
    _guarded(state, _load_cache, state, cache)
    _guarded(state, refresh_once, state, cwd, fast=True, cache=cache)
    while not stop.is_set():
        _guarded(state, refresh_once, state, cwd, fast=False, cache=cache)
        stop.wait(TTL_S)


# --- HTTP -----------------------------------------------------------------------------------


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "we-crewd"
    sys_version = ""
    timeout = TIMEOUT_S
    protocol_version = "HTTP/1.0"

    def end_headers(self):
        for k, v in HEADERS.items():
            self.send_header(k, v)
        super().end_headers()

    def log_request(self, code="-", size="-"):
        pass  # no access log: a request line is not worth a line on the session's stderr

    def _send(
        self, code: int, body: bytes = b"", ctype: str = "text/plain; charset=utf-8", extra=None
    ):
        if len(body) > MAX_BODY:
            code, body = 500, b""
            print("we-crewd: response over the cap", file=sys.stderr)
        self.send_response(code)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _route(self):
        try:
            path = self.path
            if path == "/crew":
                return self._send(301, extra={"Location": "/crew/"})
            if path == "/crew/healthz":
                return self._send(200, b"ok\n")
            if path in ASSETS:
                ctype, text = ASSETS[path]
                return self._send(200, text.encode("utf-8"), ctype)
            if path in ("/crew/", "/crew/flow"):
                body = self.server.state.page(path)
                if body is None:
                    return self._send(503, b"no snapshot yet\n")
                return self._send(200, body, "text/html; charset=utf-8")
            return self._send(404, b"not found\n")
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            raise
        except Exception as exc:
            print(f"we-crewd: {type(exc).__name__}", file=sys.stderr)
            with contextlib.suppress(OSError):
                self._send(500)

    do_GET = _route  # noqa: N815 - http.server's names
    do_HEAD = _route  # noqa: N815

    def _not_allowed(self):
        self._send(405, b"method not allowed\n", extra={"Allow": "GET, HEAD"})

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_TRACE = do_CONNECT = _not_allowed  # noqa: N815


class Server(http.server.HTTPServer):
    """An HTTP server with a bounded thread pool and the peer check."""

    daemon_threads = True

    def __init__(self, addr, state: State, peers: list):
        if ipaddress.ip_address(addr[0]).version == 6:
            self.address_family = socket.AF_INET6
        self.state = state
        self.peers = peers
        self.refused: set[str] = set()
        self.refused_lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=THREADS, thread_name_prefix="crewd")
        super().__init__(addr, Handler)

    def verify_request(self, request, client_address):  # noqa: ARG002 - socketserver's signature
        addr = str(client_address[0])
        if peer_allowed(addr, self.peers):
            return True
        # the connection stays unanswered; the log names the address once, so a proxy outside
        # `zentrale.peers` reads as one line instead of a silent 502
        with self.refused_lock:
            first = addr not in self.refused and len(self.refused) < MAX_REFUSED_LOGGED
            if first:
                self.refused.add(addr)
        if first:
            print(f"we-crewd: refused peer {addr[:64]} (not in zentrale.peers)", file=sys.stderr)
        return False

    def process_request(self, request, client_address):
        self.pool.submit(self._work, request, client_address)

    def _work(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            pass
        finally:
            self.shutdown_request(request)

    def server_close(self):
        super().server_close()
        self.pool.shutdown(wait=False)


def make_server(bind: str, port: int, state: State, peers: list) -> Server:
    check_bind(bind)
    return Server((bind, port), state, peers)


def _crew(cwd: Path | None = None) -> dict:
    try:
        _path, crew = crew_mod.find_and_load(cwd)
    except crew_mod.CrewError:
        crew = None
    return crew or crew_mod.DEFAULTS


def serve(bind: str, port: int) -> int:
    try:
        check_bind(bind)
    except ValueError as exc:
        print(f"we-crewd: {exc}", file=sys.stderr)
        return 2
    watch = CrewWatch(bind)
    watch.check()
    state = State(watch.link_hosts)
    server = make_server(bind, port, state, watch.peers)
    stop = threading.Event()
    threading.Thread(
        target=refresh_loop, args=(state, None, cache_path(), stop), daemon=True
    ).start()
    threading.Thread(target=crew_loop, args=(watch, server, state, stop), daemon=True).start()
    print(f"we-crewd: serving http://{bind}:{port}/crew/", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
    return 0


def probe(port: int = PORT, timeout: float = 2.0) -> dict:
    """What the Zentrale pane shows: the configured URL and whether the server answers here. The
    request goes direct, never through a proxy the session's environment names."""
    crew = _crew()
    url = (crew.get("zentrale") or {}).get("web_url")
    bind, alive = None, False
    direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        bind = check_bind(pod_ip())
        with direct.open(f"http://{bind}:{port}/crew/healthz", timeout=timeout) as r:
            alive = r.status == 200
    except (OSError, ValueError):
        alive = False
    return {"url": url, "alive": alive, "bind": bind, "port": port}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="crewd.py", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--bind", required=True)
    s.add_argument("--port", type=int, default=PORT)
    sub.add_parser("pod-ip")
    pr = sub.add_parser("probe")
    pr.add_argument("--port", type=int, default=PORT)
    args = p.parse_args(argv)
    if args.cmd == "serve":
        return serve(args.bind, args.port)
    if args.cmd == "pod-ip":
        try:
            print(check_bind(pod_ip()))
        except (OSError, ValueError) as exc:
            print(f"we-crewd: {exc}", file=sys.stderr)
            return 2
        return 0
    print(json.dumps(probe(args.port)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
