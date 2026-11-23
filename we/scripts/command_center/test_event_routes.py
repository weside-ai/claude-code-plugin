"""event_routes.py and the poller's routing: no receiver and damage (AC 4), reload and refusal (AC 5)."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import event_poller as ep  # noqa: E402
import event_routes  # noqa: E402
import event_sources as es  # noqa: E402

NOW = 1_795_176_000.0
CREW = {
    "version": 2,
    "roles": {
        "machinery": "kiska",
        "acceptance": "smoke",
        "tester": "smoke",
        "coordinator": "samu",
    },
    "members": {
        "kiska": {"name": "Kiska", "workplace": "."},
        "smoke": {"name": "Smoke", "workplace": "."},
        "samu": {"name": "Samu", "workplace": "."},
    },
}
ROUTES = {
    "release_pr_blocked": {"to": ["tester"]},
    "prod_gate_blocked": {"to": ["tester"], "damage": True},
    "main_red": {"to": ["machinery"]},
}


def project(tmp: Path, routes: dict | None = None) -> Path:
    root = tmp / "repo"
    (root / ".weside").mkdir(parents=True, exist_ok=True)
    (root / ".weside" / "crew.json").write_text(json.dumps(CREW))
    write_routes(root, ROUTES if routes is None else routes)
    return root


def write_routes(root: Path, routes: dict, bump: float = 0) -> None:
    config = root / ".weside" / "config.json"
    config.write_text(json.dumps({"events": {"routes": routes}}))
    if bump:
        st = config.stat()
        os.utime(config, (st.st_atime, st.st_mtime + bump))


def presence(folder: Path, name: str, member: str, parked: bool = False, at: float = NOW) -> None:
    (folder / "presence").mkdir(parents=True, exist_ok=True)
    doc = {"name": name, "member": member, "roles": [], "parked": parked, "heartbeat": at}
    (folder / "presence" / f"{name}.json").write_text(json.dumps(doc))


class Calls:
    def __init__(self):
        self.argv: list[list[str]] = []

    def __call__(self, argv, **_kw):
        self.argv.append(list(argv))
        return type("Done", (), {"returncode": 0, "stdout": "", "stderr": ""})()


def poller(
    tmp: Path, root: Path, events: list[es.Event], monkeypatch, clock=lambda: NOW
) -> ep.Poller:
    """A poller whose round finds ``events`` (the sources are tested in test_event_sources)."""
    pending = list(events)

    class Found(es.Round):
        def run_all(self):
            self.events, pending[:] = list(pending), []
            return self.events

    monkeypatch.setattr(ep, "Round", Found)
    return ep.Poller(
        root, tmp / "events", clock=clock, run=Calls(), env={"PATH": os.environ["PATH"]}
    )


def rows(folder: Path, name: str) -> list[dict]:
    return ep.read_rows(folder / name)


def release_pr(n: int) -> es.Event:
    return es.Event(
        "release_pr_blocked",
        f"rchang:acme/app:pr:{n}:age",
        f"pr:acme/app#{n}",
        None,
        {"repo": "acme/app", "number": n, "tag": "v1.2.3-rc.2", "mins": 31},
    )


def prod_pr(n: int) -> es.Event:
    return es.Event(
        "prod_gate_blocked",
        f"rchang:acme/app:pr:{n}:age",
        f"pr:acme/app#{n}",
        None,
        {"repo": "acme/app", "number": n, "tag": "v1.2.3", "mins": 31},
    )


# --- AC 4 ----------------------------------------------------------------------------------


def test_no_receiver_and_damage(tmp_path, monkeypatch):
    """No running tester, then a parked one: one delta row each, nothing addressed; the prod event
    goes at once to the coordinator's running session and as one gate news item."""
    root = project(tmp_path)
    folder = tmp_path / "events"
    p = poller(tmp_path, root, [release_pr(1)], monkeypatch)
    p.round()
    presence(folder, "smoke-1", "smoke", parked=True)
    presence(folder, "samu-1", "samu")
    p = poller(tmp_path, root, [release_pr(2), prod_pr(3)], monkeypatch)
    p.round()
    delta = rows(folder, "delta.jsonl")
    assert [(d["object"], d["role"], d["reason"]) for d in delta] == [
        ("pr:acme/app#1", "tester", "no running session"),
        ("pr:acme/app#2", "tester", "no running session"),
    ]
    events = {r["object"]: r for r in rows(folder, "events.jsonl")}
    assert events["pr:acme/app#1"]["to"] == [] and events["pr:acme/app#2"]["to"] == []
    # damage reaches the parked tester's running session; nothing for the coordinator then
    assert events["pr:acme/app#3"]["to"] == [{"session": "smoke-1", "as": "tester"}]
    assert events["pr:acme/app#3"]["damage"] is True


def test_damage_without_any_receiver_goes_to_the_coordinator_and_the_board(tmp_path, monkeypatch):
    root = project(tmp_path)
    folder = tmp_path / "events"
    presence(folder, "samu-1", "samu")
    p = poller(tmp_path, root, [prod_pr(3)], monkeypatch)
    p.round()
    row = rows(folder, "events.jsonl")[0]
    assert row["to"] == [{"session": "samu-1", "as": "coordinator"}]
    news = [a for a in p.run.argv if "news" in a]
    assert len(news) == 1
    argv = news[0]
    assert argv[argv.index("--id") + 1] == f"W-ev-{row['id']}"
    assert argv[argv.index("--kind") + 1] == "gate"
    assert argv[argv.index("--title") + 1] == (
        "prod gate blocked · release PR #3 v1.2.3 waiting 31 min · https://github.com/acme/app/pull/3"
    )
    assert [d["role"] for d in rows(folder, "delta.jsonl")] == ["tester"]
    p.round()  # the item went out: no second one
    assert len([a for a in p.run.argv if "news" in a]) == 1


def test_a_running_session_is_addressed_and_a_dead_tail_lands_in_the_delta(tmp_path, monkeypatch):
    root = project(tmp_path)
    folder = tmp_path / "events"
    presence(folder, "kiska-1", "kiska")
    now = [NOW]
    p = poller(
        tmp_path,
        root,
        [es.Event("main_red", "red:acme/app:9", "run:9", None, {"repo": "acme/app", "run_id": 9})],
        monkeypatch,
        clock=lambda: now[0],
    )
    p.round()
    assert rows(folder, "events.jsonl")[0]["to"] == [{"session": "kiska-1", "as": "machinery"}]
    assert rows(folder, "delta.jsonl") == []
    now[0] = NOW + 181  # no ledger row within deliver_timeout_s
    presence(folder, "kiska-1", "kiska", at=now[0])
    p.round()
    assert [(d["role"], d["reason"]) for d in rows(folder, "delta.jsonl")] == [
        ("machinery", "not delivered")
    ]


def test_a_delivered_event_leaves_no_delta(tmp_path, monkeypatch):
    root = project(tmp_path)
    folder = tmp_path / "events"
    presence(folder, "kiska-1", "kiska")
    now = [NOW]
    ev = es.Event("main_red", "red:acme/app:9", "run:9", None, {"repo": "acme/app", "run_id": 9})
    p = poller(tmp_path, root, [ev], monkeypatch, clock=lambda: now[0])
    p.round()
    ep.append_rows(folder / "ledger.jsonl", [{"id": ev.id, "to": "kiska-1", "delivered": True}])
    now[0] = NOW + 400
    p.round()
    assert rows(folder, "delta.jsonl") == []


# --- AC 5 ----------------------------------------------------------------------------------


def test_reload_and_refusal(tmp_path, monkeypatch):
    """A changed block routes the next round without a restart; a wrong entry is refused by name,
    the last valid mapping stays, and the error goes once to machinery."""
    root = project(tmp_path)
    folder = tmp_path / "events"
    queue: list[es.Event] = []

    class Found(es.Round):
        def run_all(self):
            self.events, queue[:] = list(queue), []
            return self.events

    monkeypatch.setattr(ep, "Round", Found)
    p = ep.Poller(root, folder, clock=lambda: NOW, run=Calls(), env={})
    queue.append(release_pr(1))
    p.round()
    assert rows(folder, "delta.jsonl")[-1]["role"] == "tester"

    write_routes(root, {"release_pr_blocked": {"to": ["machinery"]}}, bump=10)
    queue.append(release_pr(2))
    p.round()
    assert rows(folder, "delta.jsonl")[-1]["role"] == "machinery"

    for wrong, refusal in (
        ({"release_pr_blocke": {"to": ["tester"]}}, "events: unknown event 'release_pr_blocke'"),
        ({"release_pr_blocked": {"to": ["testr"]}}, "events: unknown role 'testr'"),
    ):
        write_routes(root, wrong, bump=20 if "testr" not in json.dumps(wrong) else 30)
        queue.append(release_pr(3 if "testr" not in json.dumps(wrong) else 4))
        p.round()
        delta = rows(folder, "delta.jsonl")
        errors = [d for d in delta if d["kind"] == "config_error" and d["line"] == refusal]
        assert [d["role"] for d in errors] == ["machinery"]
        last = [d for d in delta if d["kind"] == "release_pr_blocked"][-1]
        assert last["role"] == "machinery"  # the last valid mapping still routes
        assert json.loads((folder / "heartbeat.json").read_text())["config_error"] == refusal
        p.round()  # the same error is not sent again
        assert len([d for d in rows(folder, "delta.jsonl") if d["line"] == refusal]) == 1


def test_validate_refuses_unknown_keys_and_bad_repos():
    with pytest.raises(event_routes.EventsError, match="unknown key 'route'"):
        event_routes.validate({"route": {}}, CREW)
    with pytest.raises(event_routes.EventsError, match="is not owner/name"):
        event_routes.validate({"sources": {"rc": {"repo": "app; rm"}}}, CREW)
    with pytest.raises(event_routes.EventsError, match="mode must be"):
        event_routes.validate({"routes": {"main_red": {"to": ["kiska"], "mode": "x"}}}, CREW)
    with pytest.raises(event_routes.EventsError, match="status_contexts must be a list"):
        event_routes.validate(
            {"sources": {"rc": {"repo": "a/b", "status_contexts": "suite/rc"}}}, CREW
        )
    block = event_routes.validate(
        {"routes": {"issue_new": {"to": ["kiska"], "mode": "digest"}}}, CREW
    )
    assert block["poll_interval_s"] == 300 and event_routes.mode(block, "issue_new") == "digest"
    assert event_routes.targets(block, "poll_error") == ["machinery"]


def test_events_rotate_at_one_megabyte(tmp_path):
    target = tmp_path / "events.jsonl"
    target.write_text("x" * (ep.ROTATE_BYTES + 1))
    ep.append_rows(target, [{"seq": 1}])
    assert (tmp_path / "events.jsonl.1").stat().st_size > ep.ROTATE_BYTES
    assert ep.read_rows(target) == [{"seq": 1}]


def test_presence_older_than_a_minute_is_no_receiver(tmp_path):
    presence(tmp_path, "old", "kiska", at=time.time() - 120)
    presence(tmp_path, "new", "kiska", at=time.time())
    assert [p["name"] for p in ep.presences(tmp_path, time.time())] == ["new"]


def test_a_lost_state_file_continues_the_sequence(tmp_path, monkeypatch):
    root = project(tmp_path)
    folder = tmp_path / "events"
    poller(tmp_path, root, [release_pr(1)], monkeypatch).round()
    (folder / "state.json").unlink()
    poller(tmp_path, root, [release_pr(2)], monkeypatch).round()
    assert [r["seq"] for r in rows(folder, "events.jsonl")] == [1, 2]


def test_a_timeout_names_only_the_roles_not_delivered_and_counts_not_routed_as_undelivered(
    tmp_path, monkeypatch
):
    root = project(tmp_path, {**ROUTES, "rc_verdict_red": {"to": ["machinery", "tester"]}})
    folder = tmp_path / "events"
    presence(folder, "kiska-1", "kiska")
    presence(folder, "smoke-1", "smoke")
    now = [NOW]
    ev = es.Event(
        "rc_verdict_red", "rc:acme/app:1", "run:1", None, {"repo": "acme/app", "run_id": 1}
    )
    p = poller(tmp_path, root, [ev], monkeypatch, clock=lambda: now[0])
    p.round()
    ep.append_rows(
        folder / "ledger.jsonl",
        [
            {"id": ev.id, "to": "kiska-1", "delivered": True, "reason": "delivered"},
            {"id": ev.id, "to": "smoke-1", "delivered": False, "reason": "not routed"},
        ],
    )
    now[0] = NOW + 200
    p.round()
    assert [(d["role"], d["reason"]) for d in rows(folder, "delta.jsonl")] == [
        ("tester", "not delivered")
    ]


def test_the_loop_ends_when_its_project_config_is_gone(tmp_path, monkeypatch):
    monkeypatch.setenv("WE_STATE_DIR", str(tmp_path / "state"))
    root = project(tmp_path)
    (root / ".weside" / "config.json").unlink()
    assert ep.run_loop(root, rounds=5) == 0
    assert not ep.lock_held(ep.events_dir(root))


# --- open prompts: route, fallback, render, push ---------------------------------------------

import contextlib  # noqa: E402
import http.server  # noqa: E402
import threading  # noqa: E402
from typing import ClassVar  # noqa: E402

import test_event_sources as tes  # noqa: E402  (the agents samples and transcripts)

PROMPT_ROUTE = {"to": ["coordinator"], "damage": True, "push": True}
SAMU_SID = "33333333-aaaa-4bbb-8ccc-000000000003"


def prompt_event(name: str = "rust_waiting", tmp: Path | None = None) -> es.Event:
    """The event the sessions source makes of two samples of ``name`` (test_event_sources)."""
    env, state = tes.prompt_home(tmp), {}
    tes.sample(env, state, name, NOW - 60)
    [ev] = tes.sample(env, state, name, NOW)
    return ev


def presence_of(folder: Path, name: str, member: str, session_id: str = "") -> None:
    presence(folder, name, member)
    path = folder / "presence" / f"{name}.json"
    doc = json.loads(path.read_text())
    path.write_text(json.dumps({**doc, "session_id": session_id}))


def news_calls(p: ep.Poller) -> list[list[str]]:
    return [a for a in p.run.argv if "news" in a]


def test_permission_prompt_route(tmp_path, monkeypatch):
    """AC 3: without the route the event goes nowhere; routed to machinery it reaches Kiska's tail
    with ``push: true`` kept on that route (one rendering, ending `· push`) and without the
    suffix once the route drops push; ``push: "yes"`` is refused by name."""
    ev = prompt_event(tmp=tmp_path / "home")
    root = project(tmp_path, {})
    folder = tmp_path / "events"
    presence_of(folder, "kiska-1", "kiska")
    presence_of(folder, "samu-1", "samu")
    p = poller(tmp_path, root, [ev], monkeypatch)
    p.round()
    [row] = rows(folder, "events.jsonl")
    assert (row["to"], rows(folder, "delta.jsonl"), news_calls(p)) == ([], [], [])

    for push, line in (
        (
            True,
            "permission prompt · session rust · window rust · tool Bash · open since 11:59Z · push",
        ),
        (False, "permission prompt · session rust · window rust · tool Bash · open since 11:59Z"),
    ):
        sub = tmp_path / f"push-{push}"
        root = project(sub, {"permission_prompt": {"to": ["machinery"], "push": push}})
        folder = sub / "events"
        presence_of(folder, "kiska-1", "kiska")
        p = poller(sub, root, [ev], monkeypatch)
        monkeypatch.setattr(ep.Poller, "push", lambda *_a: "sent")
        p.round()
        [row] = rows(folder, "events.jsonl")
        assert row["to"] == [{"session": "kiska-1", "as": "machinery"}]
        assert ("push" in row) is push
        assert event_routes.render(row) == line

    with pytest.raises(event_routes.EventsError) as err:
        event_routes.validate(
            {"routes": {"permission_prompt": {"to": ["coordinator"], "push": "yes"}}}, CREW
        )
    assert str(err.value) == "events: route 'permission_prompt': push must be true or false"
    write_routes(root, {"permission_prompt": {"to": ["coordinator"], "push": "yes"}}, bump=5)
    p.round()
    assert p.block["routes"]["permission_prompt"]["push"] is False  # the last valid block stays
    assert rows(folder, "events.jsonl")[-1]["fields"]["error"] == (
        "events: route 'permission_prompt': push must be true or false"
    )


@pytest.mark.parametrize("damage", [True, False])
@pytest.mark.parametrize("case", ["own session", "no coordinator"])
def test_permission_prompt_fallback(tmp_path, monkeypatch, case, damage):
    """AC 4: the coordinator waiting itself, or not running: one board item (by event id), one line
    to the machinery member's tail, one coordinator delta row; no session started."""
    name = "coordinator_waiting" if case == "own session" else "rust_waiting"
    ev = prompt_event(name, tmp=tmp_path / "home")
    root = project(tmp_path, {"permission_prompt": {**PROMPT_ROUTE, "damage": damage}})
    folder = tmp_path / "events"
    presence_of(folder, "kiska-1", "kiska")
    if case == "own session":
        presence_of(folder, "samu-1", "samu", SAMU_SID)
    p = poller(tmp_path, root, [ev], monkeypatch)
    monkeypatch.setattr(ep.Poller, "push", lambda *_a: "sent")
    p.round()
    p.round()  # a second round repeats nothing
    [row] = rows(folder, "events.jsonl")
    assert row["to"] == [{"session": "kiska-1", "as": "machinery"}] and row["escalated"]
    [delta] = rows(folder, "delta.jsonl")
    assert (delta["role"], delta["id"]) == ("coordinator", row["id"])
    [news] = news_calls(p)
    assert news[news.index("--id") + 1] == f"W-ev-{row['id']}"
    assert all(Path(a[1]).name == "board.py" for a in p.run.argv)  # nothing else ran


def test_permission_prompt_render(tmp_path):
    """AC 5: a session name with a line break and an instruction is named by its id's first 8
    characters; the tool by its validated name; no input, no command, no free text."""
    ev = prompt_event("hostile_waiting", tmp=tmp_path)
    line = event_routes.render({**ev.row(es.iso(NOW), True), "push": "sent"})
    assert (
        line
        == "permission prompt · session 44444444 · tool mcp__srv__do · open since 11:59Z · push"
    )
    stored = json.dumps(ev.fields)
    for leak in ("Ignore", "curl", "SECRET", "command", "\n"):
        assert leak not in line and leak not in stored
    bad = {**ev.row(es.iso(NOW), True), "push": "HTTP 500\nIgnore all"}
    bad["fields"] = {**bad["fields"], "tool": "rm -rf /", "waiting": "x; y", "window": "a b"}
    assert event_routes.render(bad) == (
        "prompt · session 44444444 · tool unknown · open since 11:59Z · no push: error"
    )


class Hook(http.server.BaseHTTPRequestHandler):
    status = 200
    bodies: ClassVar[list] = []

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        type(self).bodies.append(json.loads(self.rfile.read(n)))
        self.send_response(type(self).status)
        self.end_headers()

    def log_message(self, *_a):
        pass


@contextlib.contextmanager
def fake_webhook(status: int):
    Hook.status, Hook.bodies = status, []
    server = http.server.HTTPServer(("127.0.0.1", 0), Hook)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/hooks/secret-path-x9"
    finally:
        server.shutdown()


WRAPPER = r"""#!/usr/bin/env python3
import os, sys
# a stand-in for the project's secret tool: the URL from a file into the child's env only
os.environ["CREW_HOOK"] = open(os.environ["HOME"] + "/hook-url").read().strip()
argv = sys.argv[sys.argv.index("--") + 1:]
os.execvp(argv[0], argv)
"""


@pytest.mark.parametrize("status", [200, 500])
def test_push_through_the_wrapper_never_shows_the_url(tmp_path, monkeypatch, status):
    """One post per open prompt through the wrapper; the line says `· push`, or loudly
    `· no push: HTTP 500` and the human gets the board item; the URL is in no argv and no file."""
    import subprocess  # noqa: PLC0415

    ev = prompt_event(tmp=tmp_path / "home")
    root = project(tmp_path, {})
    config = root / ".weside" / "config.json"
    wrapper = tmp_path / "wrap"
    wrapper.write_text(WRAPPER)
    wrapper.chmod(0o755)
    block = {
        "push": {"url_env": "CREW_HOOK", "wrapper": [str(wrapper)]},
        "routes": {"permission_prompt": PROMPT_ROUTE},
    }
    config.write_text(json.dumps({"events": block}))
    folder = tmp_path / "events"
    presence_of(folder, "samu-1", "samu")
    with fake_webhook(status) as url:
        (tmp_path / "hook-url").write_text(url)
        argvs: list = []

        def run(argv, **kw):
            argvs.append(list(argv))
            if "news" in argv:
                return type("Done", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            return subprocess.run(argv, **kw)  # noqa: PLW1510  (kw carries check)

        p = poller(tmp_path, root, [ev], monkeypatch)
        p.run = run
        p.env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path)}
        p.round()
    base = "permission prompt · session rust · window rust · tool Bash · open since 11:59Z"
    assert Hook.bodies == [{"text": base}]
    [row] = rows(folder, "events.jsonl")
    line = event_routes.render(row)
    news = [a for a in argvs if "news" in a]
    if status == 200:
        assert (line, news) == (base + " · push", [])
    else:
        assert line == base + " · no push: HTTP 500" and len(news) == 1
    assert row["to"] == [{"session": "samu-1", "as": "coordinator"}]
    assert not any(url in " ".join(a) for a in argvs)
    for path in folder.rglob("*"):
        if path.is_file():
            assert "secret-path" not in path.read_text(errors="replace"), path


def test_push_not_configured_is_loud(tmp_path, monkeypatch):
    ev = prompt_event(tmp=tmp_path / "home")
    root = project(tmp_path, {"permission_prompt": PROMPT_ROUTE})
    folder = tmp_path / "events"
    presence_of(folder, "samu-1", "samu")
    p = poller(tmp_path, root, [ev], monkeypatch)
    p.round()
    [row] = rows(folder, "events.jsonl")
    assert event_routes.render(row).endswith(" · no push: not configured")
    assert len(news_calls(p)) == 1


def test_validate_push_block():
    ok = event_routes.validate(
        {"push": {"url_env": "CREW_HOOK", "wrapper": ["vault", "run"]}}, CREW
    )
    assert ok["push"]["body_key"] == "text"
    for bad, text in (
        ({"url_env": "https://x"}, "push.url_env"),
        ({"url_env": "A", "wrapper": "vault run"}, "push.wrapper"),
        ({"url_env": "A", "wrapper": ["v"], "url": "x"}, "unknown key 'url'"),
    ):
        with pytest.raises(event_routes.EventsError, match=text):
            event_routes.validate({"push": bad}, CREW)
    with pytest.raises(event_routes.EventsError, match=r"sources\.sessions\.interval_s"):
        event_routes.validate({"sources": {"sessions": {"interval_s": 5}}}, CREW)


def test_push_on_another_kind_posts_that_kinds_line_and_never_twice(tmp_path, monkeypatch):
    """`push: true` on any route posts that event's own line; a sent event id is never posted
    again, even when the round failed before its state was written."""
    root = project(tmp_path, {})
    (root / ".weside" / "config.json").write_text(
        json.dumps(
            {
                "events": {
                    "push": {"url_env": "CREW_HOOK", "wrapper": ["vault"]},
                    "routes": {"release_pr_blocked": {"to": ["tester"], "push": True}},
                }
            }
        )
    )
    folder = tmp_path / "events"
    presence(folder, "smoke-1", "smoke")
    p = poller(tmp_path, root, [release_pr(7)], monkeypatch)
    posts: list[str] = []
    monkeypatch.setattr(ep.Poller, "_post", lambda _s, text, _c: posts.append(text) or "sent")
    p.round()
    [row] = rows(folder, "events.jsonl")
    assert posts == [event_routes.line(row)] and posts[0].startswith("release PR #7")
    assert event_routes.render(row) == posts[0] + " · push"
    assert p.push(row["id"], "again", p.block, NOW + 60) == "sent" and len(posts) == 1


def prod_run(run_id: int) -> es.Event:
    return es.Event(
        "prod_gate_blocked",
        f"prod:acme/app:{run_id}",
        f"run:{run_id}",
        None,
        {
            "repo": "acme/app",
            "tag": "v1.2.4",
            "run_id": run_id,
            "conclusion": "failure",
            "gate": "Release gate",
            "jobs": ["Release gate"],
        },
    )


def test_prod_tag_run_without_a_tester_goes_to_the_coordinator_and_the_board(
    tmp_path, monkeypatch
):
    root = project(tmp_path)
    folder = tmp_path / "events"
    presence(folder, "samu-1", "samu")
    p = poller(tmp_path, root, [prod_run(702)], monkeypatch)
    p.round()
    row = rows(folder, "events.jsonl")[0]
    assert row["damage"] is True
    assert row["to"] == [{"session": "samu-1", "as": "coordinator"}]
    news = [a for a in p.run.argv if "news" in a]
    assert len(news) == 1 and news[0][news[0].index("--kind") + 1] == "gate"
    assert news[0][news[0].index("--title") + 1] == (
        "prod gate blocked · release v1.2.4 failure · gate refused: Release gate · cause: "
        "Release gate · run https://github.com/acme/app/actions/runs/702"
    )


PROD_OK = {"repo": "acme/app", "workflow": "release.yml", "gate_job": "Release gate"}


@pytest.mark.parametrize(
    "cfg, error",
    [
        (dict(PROD_OK, tag="x"), "sources.prod_release has unknown key 'tag'"),
        (dict(PROD_OK, workflow="../x"), "sources.prod_release.workflow must be"),
        (dict(PROD_OK, tag_pattern="v("), "sources.prod_release.tag_pattern must be"),
        (dict(PROD_OK, tag_pattern=r"^v\S+$"), "takes the RC tag 'v1.2.3-rc.1'"),
        (dict(PROD_OK, wait_min=0), "sources.prod_release.wait_min must be"),
        (dict(PROD_OK, gate_job=" "), "sources.prod_release.gate_job must be"),
        (dict(PROD_OK, repo="app"), "source repo 'app' is not owner/name"),
    ],
)
def test_prod_release_source_refused_by_name(cfg, error):
    with pytest.raises(event_routes.EventsError, match=re.escape(error)):
        event_routes.validate({"sources": {"prod_release": cfg}}, CREW)
    event_routes.validate({"sources": {"prod_release": PROD_OK}}, CREW)
