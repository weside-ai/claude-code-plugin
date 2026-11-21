"""we-crewd: bind and peers (AC3), XSS (AC4), verbs and paths (AC5), fields and redaction (AC6),
limits and no subprocess per request (AC7), headers and the cache file (AC8), reload and state
labels (AC11). Each red arm runs against a control variant that must go red."""

from __future__ import annotations

import builtins
import html
import http.client
import io
import json
import os
import re
import socket
import stat
import subprocess
import sys
import threading
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import crewd  # noqa: E402
import flow_intervals as fi  # noqa: E402

XSS = '"><img src=x onerror=alert(1)>'
BREAK = "</script><img src=x onerror=alert(1)><!--"
DUMMIES = [
    "ghp_" + "a" * 36,
    "ghs_" + "b" * 36,
    "gho_" + "c" * 36,
    "ghu_" + "d" * 36,
    "ghr_" + "e" * 36,
    "github_pat_" + "f" * 40,
    "sk-ant-" + "g" * 40,
    "sk-" + "h" * 32,
    "Bearer " + "i" * 30,
    "eyJ" + "j" * 20 + "." + "k" * 20 + "." + "l" * 20,
]
MARKER = "MARKER-7f3a"
EMAIL = "foxy@example.org"


def row(item, **extra):
    base = {
        "kind": "question",
        "item": item,
        "title": f"title {item}",
        "holder": "owner",
        "for": "ABC-1",
        "master": "alpha-7",
        "since": "2026-11-20T20:20:00Z",
        "since_note": "",
        "age_s": 3000,
        "age": "0h50",
        "source": "questions",
        "classes": [],
        "red": False,
    }
    return {**base, **extra}


def session(name, **extra):
    base = {
        "name": name,
        "session_id": f"s-{name}",
        "kind": "interactive",
        "role": "master",
        "state": "idle",
        "doing": "epic PROJ-1",
        "keys": [],
        "waiting_on": None,
        "blocked_kind": None,
        "since": None,
        "age_s": 7800,
        "age": "2h10",
        "plugin": "9.20.0",
        "starter": None,
        "group": name,
        "waits": False,
    }
    return {**base, **extra}


def account(name, **extra):
    base = {
        "name": name,
        "active": False,
        "in_rotation": True,
        "five_hour": {"pct": 40, "resets_at": None},
        "seven_day": {"pct": 70, "resets_at": None},
        "threshold": 80,
        "status": "ok",
        "measured_at": "2026-11-20T21:08:00Z",
        "age_s": 120,
        "stale": False,
        "red": False,
    }
    return {**base, **extra}


def doc(**sections):
    base = {
        "owner": [row("Q4"), row("acme/app#24", kind="pr", title=XSS, classes=["user merge"])],
        "red": [row("acme/app#22", kind="pr", red=True, url="javascript:alert(1)")],
        "waiting": [row("Q9", title=f"question for {EMAIL}: {XSS}")],
        "working": [session("lead", doing=XSS), session("w-1", role="worker", doing=BREAK)],
        "ci": {
            "repos": [{"repo": "acme/app", "default_head": "green", "checks": []}],
            "locks": "locks: none",
        },
        "accounts": [account("dev", active=True)],
    }
    base.update(sections)
    return {
        "schema_version": 1,
        "project": "acme",
        "built_at": "2026-11-20T21:10:00Z",
        "fast": False,
        "header": ["Project: acme"],
        "gaps": [],
        "sources": {"github acme/app": {"fetched_at": "2026-11-20T21:09:00Z", "gap": None}},
        "sections": base,
    }


FLOW = {
    "project": "acme",
    "window": {"since": "2026-11-20T00:00:00Z", "until": "2026-11-21T00:00:00Z"},
    "intervals": [{"who": BREAK, "kind": "working", "label": XSS}],
    "header": ["javascript:alert(1)"],
}


def state_with(d=None, flow=FLOW, hosts=("github.com/acme",)):
    st = crewd.State(hosts)
    st.set(snap=crewd.snapshot_of(d or doc()), flow=crewd.flow_of(flow), at="2026-11-20T21:10:05Z")
    return st


def unsafe(page: str) -> list:
    """What makes a page unsafe: an element with an event handler or an `<img`, a `javascript:`
    href, inline script or style, a raw `<`, `>` or `&` inside the JSON data block."""
    found = []
    if "<img" in page:
        found.append("<img")
    if re.search(r"<[a-zA-Z][^>]*\son[a-z]+\s*=", page):
        found.append("event handler attribute")
    if re.search(r"""href\s*=\s*["']?\s*javascript:""", page, re.I):
        found.append("javascript: href")
    for href in re.findall(r'href="([^"]*)"', page):
        if not href.startswith(("/crew/", "https://github.com/acme/")):
            found.append(f"href {href}")
    if re.search(r"<style", page) or re.search(
        r"<script(?![^>]*(type=\"application/json\"|src=))", page
    ):
        found.append("inline script or style")
    block = re.search(r'<script type="application/json" id="flow-data">(.*?)</script>', page, re.S)
    if block and re.search(r"[<>&]", block.group(1)):
        found.append("raw <>& in the data block")
    if block is None and "flow-data" in page:
        found.append("data block broken")
    return found


def unsafe_js(js: str) -> bool:
    """A script that writes markup instead of text."""
    return any(
        sink in js for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write")
    )


# --- AC3: bind and peers --------------------------------------------------------------------


@pytest.mark.parametrize("ip", ["127.0.0.1", "127.8.8.8", "::1", "0.0.0.0", "::"])
def test_loopback_and_wildcard_binds_are_refused(ip, capsys):
    with pytest.raises(ValueError):
        crewd.check_bind(ip)
    assert crewd.main(["serve", "--bind", ip]) == 2
    assert "refusing to bind" in capsys.readouterr().err


def test_the_peer_check_admits_the_measured_set_and_the_own_address():
    peers = crewd.peers_of({"zentrale": {"peers": ["10.42.0.0/16"]}}, "10.43.2.164")
    assert crewd.peer_allowed("10.42.9.194", peers)  # a proxy pod
    assert crewd.peer_allowed("10.43.2.164", peers)  # the pane's probe from the same host
    for other in ("10.43.2.165", "192.168.1.10", "100.64.0.1", "not-an-ip"):
        assert not crewd.peer_allowed(other, peers), other
    assert crewd.peers_of({}, "10.43.2.164") == [crewd.ipaddress.ip_network("10.43.2.164")]


# --- a live server on loopback, built past check_bind for the test only ------------------------


@pytest.fixture
def serve():
    servers = []

    def start(state, peers=("127.0.0.1/32",)):
        srv = crewd.Server(("127.0.0.1", 0), state, [crewd.ipaddress.ip_network(p) for p in peers])
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return srv.server_address[1]

    yield start
    for srv in servers:
        srv.shutdown()
        srv.server_close()


def request(port, method, path, raw=False):
    if raw:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            s.sendall(f"{method} {path} HTTP/1.0\r\n\r\n".encode())
            data = b""
            while chunk := s.recv(65536):
                data += chunk
        head, _, body = data.partition(b"\r\n\r\n")
        lines = head.decode().split("\r\n")
        status = int(lines[0].split()[1]) if lines[0] else 0
        headers = dict(line.split(": ", 1) for line in lines[1:] if ": " in line)
        return status, headers, body
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path)
    r = conn.getresponse()
    body = r.read()
    conn.close()
    return r.status, dict(r.getheaders()), body


def test_a_peer_outside_the_set_gets_no_answer(serve, capsys):
    port = serve(state_with(), peers=("10.0.0.0/8",))
    for _ in range(3):
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            s.sendall(b"GET /crew/ HTTP/1.0\r\n\r\n")
            assert s.recv(1024) == b""
    # 21.11.: a proxy outside the set got a silent 502; the address is named once, never per request
    lines = [x for x in capsys.readouterr().err.splitlines() if "refused peer" in x]
    assert lines == ["we-crewd: refused peer 127.0.0.1 (not in zentrale.peers)"]


def _write_crew(repo: Path, peers=None, raw=None):
    path = repo / ".weside" / "crew.json"
    path.parent.mkdir(exist_ok=True)
    body = {"version": crewd.crew_mod.VERSION, "roles": {}, "members": {}}
    if peers is not None:
        body["zentrale"] = {"peers": peers}
    old = path.stat().st_mtime_ns if path.exists() else 0
    path.write_text(raw if raw is not None else json.dumps(body))
    os.utime(path, ns=(old + 10**9, old + 10**9))  # a new mtime even within one clock tick


def test_the_crew_is_read_again_when_its_file_changes(tmp_path, capsys):
    # 21.11.: a crew file without `zentrale.peers`, read once at the start, kept the proxy out
    # (502) after the file had been fixed; the server reads it again on a change
    (tmp_path / ".git").mkdir()
    _write_crew(tmp_path)
    watch = crewd.CrewWatch("10.43.2.164", cwd=tmp_path)
    state, server = crewd.State(), type("S", (), {"peers": None})()
    crewd.crew_tick(watch, server, state)
    assert not crewd.peer_allowed("10.42.9.194", server.peers)
    crewd.crew_tick(watch, server, state)  # unchanged: no reload line
    _write_crew(tmp_path, peers=["10.42.0.0/16"])
    crewd.crew_tick(watch, server, state)
    assert crewd.peer_allowed("10.42.9.194", server.peers)
    assert crewd.peer_allowed("10.43.2.164", server.peers)  # the own address stays
    _write_crew(tmp_path, raw="{broken")  # a broken edit keeps the last good peers
    crewd.crew_tick(watch, server, state)
    assert crewd.peer_allowed("10.42.9.194", server.peers)
    err = capsys.readouterr().err
    assert err.count("peer networks") == 2 and "crew not reloaded" in err


# --- AC4: XSS -------------------------------------------------------------------------------


def test_payloads_render_inert_on_every_route(serve):
    port = serve(state_with())
    for path in ("/crew/", "/crew/flow"):
        status, _h, body = request(port, "GET", path)
        page = body.decode()
        assert status == 200
        assert unsafe(page) == [], (path, unsafe(page))
    crew = request(port, "GET", "/crew/")[2].decode()
    assert html.escape(XSS) in crew  # the payload is there, as text
    assert '<a href="https://github.com/acme/app/pull/24">' in crew
    flow = request(port, "GET", "/crew/flow")[2].decode()
    data = re.search(r'id="flow-data">(.*?)</script>', flow, re.S).group(1)
    assert json.loads(data)["intervals"][0]["who"] == BREAK
    js = request(port, "GET", "/crew/static/flow.js")[2].decode()
    assert not unsafe_js(js)


def test_the_controls_go_red(monkeypatch):
    """The checks above see what they guard: an unescaped page, an `innerHTML` script and a data
    block from raw `json.dumps` each fail them."""
    monkeypatch.setattr(crewd, "e", lambda s, **_k: s)
    assert "<img" in unsafe(crewd.render_crew(crewd.snapshot_of(doc()), {}, ["github.com/acme"]))
    monkeypatch.undo()
    raw = crewd.render_flow(FLOW, {}).replace(
        fi.embed_json(FLOW), fi.embed_json(FLOW, escape=False)
    )
    assert unsafe(raw)
    assert unsafe_js("e.innerHTML=v") and not unsafe_js(fi.JS)
    # a link field is never copied: an href from a field would show here
    page = crewd.render_crew(crewd.snapshot_of(doc()), {}, ["github.com/acme"])
    assert "javascript:" not in page
    assert crewd.pr_href("evil/app#1", ["github.com/acme"]) is None
    assert crewd.pr_href("acme/app#1 onclick", ["github.com/acme"]) is None
    # a link host may name one repo: that repo links, its owner's other repos do not
    assert (
        crewd.pr_href("acme/app#7", ["github.com/acme/app/"])
        == "https://github.com/acme/app/pull/7"
    )
    assert crewd.pr_href("acme/other#7", ["github.com/acme/app"]) is None


# --- AC5: verbs, paths, no open() or subprocess per request ----------------------------------


def test_verbs_paths_and_no_io_per_request(serve, monkeypatch):
    port = serve(state_with())
    counts = {"open": 0, "popen": 0}

    def count(name, real):
        def wrapped(*a, **k):
            counts[name] += 1
            return real(*a, **k)

        return wrapped

    monkeypatch.setattr(builtins, "open", count("open", builtins.open))
    monkeypatch.setattr(io, "open", count("open", io.open))
    monkeypatch.setattr(os, "open", count("open", os.open))
    monkeypatch.setattr(subprocess, "Popen", count("popen", subprocess.Popen))
    for verb in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE"):
        status, headers, _b = request(port, verb, "/crew/", raw=True)
        assert status == 405, verb
        assert headers.get("Allow") == "GET, HEAD"
    for path in (
        "/crew/../../.claude/.credentials.json",
        "/crew/%2e%2e/%2e%2e/.claude/.credentials.json",
        "/crew/?file=/etc/passwd",
        "/crew/static/../crewd.py",
        "/etc/passwd",
        "/",
        "/crew/nope",
    ):
        assert request(port, "GET", path, raw=True)[0] == 404, path
    for path in ("/crew/", "/crew/flow", "/crew/healthz", "/crew/static/crew.css"):
        assert request(port, "GET", path)[0] == 200
        status, _h, body = request(port, "HEAD", path)
        assert status == 200 and body == b""
    status, headers, _b = request(port, "GET", "/crew")
    assert status == 301 and headers["Location"] == "/crew/"
    for _ in range(200):
        request(port, "GET", "/crew/")
    assert counts == {"open": 0, "popen": 0}


# --- AC6: fields and redaction --------------------------------------------------------------


def test_only_allowlisted_fields_reach_a_page_and_every_secret_reads_redacted(
    serve, tmp_path, monkeypatch
):
    home = tmp_path / "home"
    (home / ".claude" / "projects" / "p").mkdir(parents=True)
    (home / ".claude" / ".credentials.json").write_text(json.dumps({"token": MARKER}))
    transcript = home / ".claude" / "projects" / "p" / "s.jsonl"
    transcript.write_text(json.dumps({"text": MARKER}) + "\n")
    monkeypatch.setenv("HOME", str(home))
    d = doc(
        working=[
            session(
                "lead",
                doing="now: " + " ".join(DUMMIES),
                transcript=str(transcript),
                secret=MARKER,
            )
        ],
        # accounts.py names an account without alias by its slot, never its email
        accounts=[
            account("account 1", token=MARKER, email=EMAIL),
            account("account 2", email=EMAIL),
        ],
        waiting=[row("Q9", title=f"ask {EMAIL} please", extra=MARKER)],
    )
    port = serve(
        state_with(
            d,
            flow={
                **FLOW,
                "intervals": [
                    {
                        "who": "w",
                        "label": " ".join(DUMMIES),
                        "path": str(transcript),
                        "note": MARKER,
                    }
                ],
            },
        )
    )
    pages = [
        request(port, "GET", p)[2].decode() for p in ("/crew/", "/crew/flow", "/crew/healthz")
    ]
    for page in pages:
        assert MARKER not in page and EMAIL not in page and str(home) not in page
        for dummy in DUMMIES:
            assert dummy.split()[-1] not in page, dummy
    crew_page = pages[0]
    assert crew_page.count("[redacted]") >= len(DUMMIES) + 1
    assert "account 1" in crew_page and "account 2" in crew_page  # two accounts, told apart
    assert "ask [redacted] please" in crew_page
    snap = crewd.snapshot_of(d)
    assert set(snap["working"][0]) == set(crewd.SESSION_FIELDS)
    assert set(snap["accounts"][0]) == set(crewd.ACCOUNT_FIELDS) | {"five_hour", "seven_day"}
    # a clean row equals the read layer's fields
    clean = doc()["sections"]["owner"][0]
    assert crewd.snapshot_of(doc())["owner"][0] == {f: clean[f] for f in crewd.ROW_FIELDS}


def test_an_unknown_schema_version_renders_an_error_row():
    snap = crewd.snapshot_of({**doc(), "schema_version": 2})
    page = crewd.render_crew(snap, {}, [])
    assert "schema_version 2" in page and "Q4" not in page


# --- AC7: limits, the refresh off the request path ------------------------------------------


def test_limits_and_the_background_refresh(tmp_path):
    assert crewd.Handler.timeout <= 5
    assert crewd.THREADS <= 16 and crewd.TTL_S >= 60
    calls = []

    def runner(argv, timeout, cwd):
        calls.append((tuple(argv[1:]), timeout))
        return FLOW if "--page-data" in argv else doc()

    st = crewd.State([])
    crewd.refresh_once(st, None, fast=True, cache=tmp_path / "c.json", runner=runner)
    crewd.refresh_once(st, None, fast=False, cache=tmp_path / "c.json", runner=runner)
    assert [c[0][1:] for c in calls] == [
        (str(crewd.ZENTRALE), "--json", "--fast"),
        (str(crewd.ZENTRALE), "--json"),
        (str(crewd.FLOW), "--page-data", "--since", "1d"),
    ]
    assert all(c[0][0] == "-I" and 0 < c[1] <= 120 for c in calls)

    def failing(argv, timeout, cwd):
        raise subprocess.TimeoutExpired(argv, timeout)

    crewd.refresh_once(st, None, fast=False, cache=tmp_path / "c.json", runner=failing)
    page = st.page("/crew/").decode()
    assert (
        "Q4" in page and "last refresh failed" in page
    )  # the last snapshot stays, the error shows


def test_a_body_over_the_cap_is_a_500_without_body(serve, monkeypatch):
    st = state_with()
    port = serve(st)
    monkeypatch.setattr(crewd, "MAX_BODY", 10)
    status, _h, body = request(port, "GET", "/crew/")
    assert status == 500 and body == b""


def test_no_snapshot_yet_is_a_503(serve):
    port = serve(crewd.State([]))
    status, headers, body = request(port, "GET", "/crew/")
    assert status == 503 and body == b"no snapshot yet\n"
    assert headers["Cache-Control"] == "no-store"


# --- AC8: headers and the cache file --------------------------------------------------------


def test_every_response_carries_the_csp_without_inline(serve, monkeypatch):
    st = state_with()
    port = serve(st)
    seen = []
    for method, path in (
        ("GET", "/crew/"),
        ("GET", "/crew/flow"),
        ("HEAD", "/crew/healthz"),
        ("GET", "/nope"),  # 404
        ("POST", "/crew/"),  # 405
    ):
        status, headers, _b = request(port, method, path, raw=True)
        seen.append((status, headers))
    monkeypatch.setattr(st, "page", lambda _path: 1 / 0)
    seen.append(request(port, "GET", "/crew/", raw=True)[:2])  # 500
    assert [code for code, _h in seen] == [200, 200, 200, 404, 405, 500]
    for code, headers in seen:
        csp = headers.get("Content-Security-Policy", "")
        directives = dict(d.strip().split(" ", 1) for d in csp.split(";") if d.strip())
        assert directives.get("default-src") == "'none'", code
        assert directives.get("script-src") == "'self'" and directives.get("style-src") == "'self'"
        assert "unsafe-inline" not in csp and "unsafe-eval" not in csp, code
        assert headers.get("X-Content-Type-Options") == "nosniff", code
        assert headers.get("Cache-Control") == "no-store", code


def test_an_unforeseen_route_error_is_a_500_without_body(serve, monkeypatch, capsys):
    st = state_with()
    port = serve(st)
    monkeypatch.setattr(st, "page", lambda _path: {}["boom"])
    status, _h, body = request(port, "GET", "/crew/")
    assert status == 500 and body == b""
    assert "we-crewd: KeyError" in capsys.readouterr().err
    assert request(port, "GET", "/crew/healthz")[0] == 200  # the server keeps serving


def test_the_cache_file_is_mode_600_from_its_first_byte(tmp_path, monkeypatch):
    opened = []
    real = os.open

    def spy(path, flags, mode=0o777, *a, **k):
        opened.append((flags, mode))
        return real(path, flags, mode, *a, **k)

    monkeypatch.setattr(os, "open", spy)
    st = state_with()
    path = tmp_path / "crewd.json"
    crewd.write_cache(path, st.cache_payload())
    monkeypatch.undo()
    assert opened and opened[0][0] & os.O_EXCL and opened[0][1] == 0o600
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    payload = json.loads(path.read_text())
    assert payload["fetched_at"] == "2026-11-20T21:10:05Z"
    assert set(payload) == {"fetched_at", "flow_at", "snap", "flow"}
    # a restart answers from it at once (Klick bis Inhalt < 3 s)
    st2 = crewd.State([])
    crewd._load_cache(st2, path)
    assert b"Q4" in st2.page("/crew/") and b"dev" in st2.page("/crew/")
    assert st2.snap == st.snap and st2.flow == st.flow  # a clean cache restores unchanged
    # a file of another uid is not read
    monkeypatch.setattr(os, "getuid", lambda: path.stat().st_uid + 1)
    assert crewd.read_cache(path) is None
    st3 = crewd.State([])
    crewd._load_cache(st3, path)
    assert st3.page("/crew/") is None


def test_a_restored_cache_passes_the_allowlist_and_the_redaction_again(tmp_path):
    """The cache file is not trusted as rendered: a field outside the allowlist or an unredacted
    secret written into it does not reach a page after a restart."""
    st = state_with()
    payload = st.cache_payload()
    payload["snap"]["owner"][0]["extra"] = MARKER
    payload["snap"]["owner"][0]["title"] = "ghp_" + "a" * 36
    payload["snap"]["working"][0]["transcript"] = MARKER
    payload["snap"]["accounts"][0]["email"] = EMAIL
    payload["snap"]["secret"] = MARKER
    payload["flow"]["intervals"][0]["note"] = MARKER
    payload["flow"]["intervals"][0]["label"] = EMAIL
    payload["flow"]["token"] = MARKER
    path = tmp_path / "crewd.json"
    crewd.write_cache(path, payload)
    restored = crewd.State([])
    crewd._load_cache(restored, path)
    for page in (restored.page("/crew/"), restored.page("/crew/flow")):
        text = page.decode()
        assert MARKER not in text and EMAIL not in text and "ghp_" not in text
    assert b"Q4" in restored.page("/crew/")
    assert set(restored.snap["owner"][0]) == set(crewd.ROW_FIELDS)
    assert restored.snap["accounts"][0]["five_hour"] == 40
    # control: the same payload set raw, as before, shows what the restore keeps out
    raw = crewd.State([])
    raw.set(snap=payload["snap"], flow=payload["flow"], at="x")
    assert MARKER in raw.page("/crew/flow").decode()


# --- AC11: reload and state labels ----------------------------------------------------------


def test_the_page_reloads_every_30_s_and_names_its_state():
    page = state_with().page("/crew/").decode()
    assert '<meta http-equiv="refresh" content="30">' in page
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in page
    assert "generated_at 2026-11-20T21:10:05Z" in page
    assert "github acme/app fetched_at 2026-11-20T21:09:00Z" in page


# --- review round: the refresh thread, the probe, pod-ip ------------------------------------


def test_an_unforeseen_refresh_error_keeps_the_thread_and_shows(tmp_path):
    st = state_with()

    def broken(argv, timeout, cwd):
        return {**doc(), "sources": ["not", "a", "dict"]}

    crewd._guarded(
        st, crewd.refresh_once, st, None, fast=True, cache=tmp_path / "c.json", runner=broken
    )
    page = st.page("/crew/").decode()
    assert "Q4" in page and "last refresh failed: AttributeError" in page
    # a cached snapshot that no longer renders is dropped: 503, not old data
    bad = tmp_path / "bad.json"
    crewd.write_cache(bad, {"fetched_at": "x", "snap": {"project": "p"}, "flow": None})
    fresh = crewd.State([])
    crewd._guarded(fresh, crewd._load_cache, fresh, bad)
    assert fresh.page("/crew/") is None


def test_probe_goes_direct_on_its_port_and_pod_ip_refuses_loopback(serve, monkeypatch, capsys):
    port = serve(state_with())
    monkeypatch.setattr(crewd, "pod_ip", lambda: "127.0.0.1")
    monkeypatch.setattr(crewd, "check_bind", lambda ip: ip)
    monkeypatch.setenv("http_proxy", "http://192.0.2.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://192.0.2.1:9")
    assert crewd.probe(port)["alive"] is True
    assert crewd.probe(port + 1 if port < 65535 else port - 1)["alive"] is False
    monkeypatch.undo()
    monkeypatch.setattr(crewd, "pod_ip", lambda: "127.0.0.1")
    assert crewd.main(["pod-ip"]) == 2
    assert "refusing to bind 127.0.0.1" in capsys.readouterr().err
