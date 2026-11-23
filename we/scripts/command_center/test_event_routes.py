"""event_routes.py and the poller's routing: no receiver and damage (AC 4), reload and refusal (AC 5)."""

from __future__ import annotations

import json
import os
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
