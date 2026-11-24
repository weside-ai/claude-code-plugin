"""event_poller.py: one poller per project (AC 6), its environment, state and heartbeat."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import event_poller as ep  # noqa: E402
import test_event_routes as ter  # noqa: E402  (its crew and project builder)

SCRIPT = HERE / "event_poller.py"


def env_for(tmp: Path) -> dict:
    return {
        "HOME": str(tmp),
        "PATH": os.environ["PATH"],
        "WE_STATE_DIR": str(tmp / "state"),
        "CLAUDE_CODE_MESSAGING_TOKEN": "secret-token",
        "CLAUDE_CODE_MESSAGING_SOCKET": str(tmp / "sock"),
        "CLAUDE_CONFIG_DIR": str(tmp / "cfg"),
    }


def wait_for(predicate, timeout: float = 10.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_one_poller_per_project(tmp_path):
    """Two starts at once leave one poller; a second `run` exits on the held lock."""
    root = ter.project(tmp_path)
    env = env_for(tmp_path)
    folder = ep.events_dir(root, env)
    starts = [
        subprocess.Popen(
            [sys.executable, str(SCRIPT), "ensure", "--from", str(root)],
            env=env,
            stdout=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    said = [p.communicate(timeout=30)[0].strip() for p in starts]
    started = [s for s in said if s.startswith("events: poller ") and s.endswith(" started")]
    assert started, said
    pids = [int(s.split()[2]) for s in started]
    try:
        assert wait_for(lambda: ep.lock_held(folder))
        assert wait_for((folder / "heartbeat.json").exists)
        # a start that lost the race exits on the lock; the winner keeps running
        assert wait_for(lambda: sum(1 for p in pids if _alive(p)) == 1)
        assert ep.ensure(root, env) == "events: poller runs"
        second = subprocess.run(
            [sys.executable, str(SCRIPT), "run", "--root", str(root), "--rounds", "1"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert (second.returncode, second.stderr.strip()) == (
            0,
            "events: another poller holds the lock",
        )
        once = subprocess.run(
            [sys.executable, str(SCRIPT), "once", "--from", str(root)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert once.returncode == 1
        winner = next(p for p in pids if _alive(p))
        environ = Path(f"/proc/{winner}/environ")
        if environ.exists():
            names = {kv.split("=", 1)[0] for kv in environ.read_bytes().decode().split("\0") if kv}
            assert not any(n.startswith("CLAUDE") for n in names)
            assert names <= set(ep.KEEP_ENV)
    finally:
        for pid in pids:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(pid, signal.SIGTERM)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # a zombie child of a finished start counts as gone
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return True


def test_clean_env_keeps_home_path_lang_and_the_state_dir_only(tmp_path):
    env = env_for(tmp_path)
    env["GH_TOKEN"] = "x"
    assert ep.clean_env(env) == {
        "HOME": str(tmp_path),
        "PATH": os.environ["PATH"],
        "WE_STATE_DIR": str(tmp_path / "state"),
        "LANG": "C.UTF-8",
    }


def test_ensure_is_off_without_an_events_block(tmp_path):
    root = tmp_path / "repo"
    (root / ".weside").mkdir(parents=True)
    (root / ".weside" / "config.json").write_text(json.dumps({"stack": []}))
    assert ep.ensure(root, env_for(tmp_path)) == "events: off (no events: block)"


def test_once_writes_state_and_heartbeat(tmp_path):
    root = ter.project(tmp_path)
    env = env_for(tmp_path)
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "once", "--from", str(root)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    beat = json.loads(out.stdout)
    assert beat["routes"]["release_pr_blocked"] == ["tester"] and beat["interval_s"] == 300
    folder = ep.events_dir(root, env)
    assert json.loads((folder / "state.json").read_text())["seq"] == 0
    status = subprocess.run(
        [sys.executable, str(SCRIPT), "status", "--from", str(root)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert "route release_pr_blocked -> tester" in status.stdout
    path = subprocess.run(
        [sys.executable, str(SCRIPT), "path", "--delta", "--from", str(root)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert path.stdout.strip() == str(folder / "delta.jsonl")


def test_sessions_source_runs_on_its_own_interval(tmp_path):
    """The loop ticks at the sessions interval (60 s); GitHub and the local checks keep theirs
    (300 s): over five minutes six samples of the sessions, two main rounds."""
    root = ter.project(tmp_path, {})
    config = root / ".weside" / "config.json"
    config.write_text(
        json.dumps(
            {
                "events": {
                    "sources": {"sessions": {"interval_s": 60}},
                    "local_checks": ["true"],
                    "routes": {},
                }
            }
        )
    )
    now = [ter.NOW]
    samples: list[float] = []
    calls = ter.Calls()

    def sessions():
        samples.append(now[0])
        return []

    p = ep.Poller(
        root, tmp_path / "events", clock=lambda: now[0], run=calls, env={}, sessions=sessions
    )
    beats = []
    for _ in range(6):
        beats.append(p.round())
        now[0] += 60
    assert len(samples) == 6
    assert len([a for a in calls.argv if a[:2] == ["sh", "-c"]]) == 2
    assert {b["interval_s"] for b in beats} == {60}
    assert beats[0]["poll_interval_s"] == 300 and beats[0]["sessions_interval_s"] == 60


# --- the epic's master (epic_master) and the owner report -------------------------------------

import shutil  # noqa: E402

import event_sources as es  # noqa: E402

EVENTS = HERE / "fixtures" / "events"
NOW = ter.NOW
MASTER_ROUTES = {
    "main_red": {"to": ["epic_master", "machinery"]},
    "pr_checks_red": {"to": ["epic_master"]},
}


def marker_red(run: int = 9001) -> es.Event:
    return es.Event(
        "main_red",
        f"marker:acme/app:{run}",
        f"run:{run}",
        es.iso(NOW - 120),
        {
            "repo": "acme/app",
            "sha": "abc1234",
            "failing": ["tests/test_a.py::test_one", "tests/test_b.py::test_two[x]"],
            "unreadable": False,
            "run_id": run,
            "epics": ["ACME-3215"],
            "origin": "marker",
        },
    )


def crew_board(tmp: Path, monkeypatch, drop: str | None = None) -> Path:
    state = tmp / "state"
    state.mkdir(exist_ok=True)
    monkeypatch.setenv("WE_STATE_DIR", str(state))
    board = json.loads((EVENTS / "board.json").read_text())
    board["sessions"] = [s for s in board["sessions"] if s["name"] != drop]
    (state / "board.json").write_text(json.dumps(board))
    shutil.copy(EVENTS / "board-tickets.json", state / "board-tickets.json")
    return state


def master_presence(folder: Path, name: str, sid: str) -> None:
    (folder / "presence").mkdir(parents=True, exist_ok=True)
    doc = {
        "name": name,
        "member": None,
        "session_id": sid,
        "roles": [],
        "parked": False,
        "heartbeat": NOW,
    }
    (folder / "presence" / f"{name}.json").write_text(json.dumps(doc))


def test_route_epic_master(tmp_path, monkeypatch):
    """The marker's epic reaches its running master with the owner in the line; without that
    master's board line one delta row names the epic and no other master gets a line."""
    root = ter.project(tmp_path, MASTER_ROUTES)
    folder = tmp_path / "events"
    crew_board(tmp_path, monkeypatch)
    master_presence(folder, "sock-master-1", "sid-master-1")
    master_presence(folder, "sock-master-2", "sid-master-2")
    master_presence(folder, "sock-owl", "sid-owl")  # a companion's line holding the story key
    ter.poller(tmp_path, root, [marker_red()], monkeypatch).round()
    (row,) = ter.rows(folder, "events.jsonl")
    assert row["to"] == [{"session": "sock-master-1", "as": "epic_master"}]
    assert ep.routes_mod.render(row) == (
        "main red acme/app · abc1234 · failing: tests/test_a.py::test_one, "
        "tests/test_b.py::test_two[x] · run https://github.com/acme/app/actions/runs/9001"
        " · owner kleinzeug-3215"
    )
    delta = ter.rows(folder, "delta.jsonl")
    assert [d["role"] for d in delta] == ["machinery"]  # no running machinery session

    other = tmp_path / "second"
    other.mkdir()
    root2 = ter.project(other, MASTER_ROUTES)
    folder2 = other / "events"
    crew_board(other, monkeypatch, drop="kleinzeug-3215")
    master_presence(folder2, "sock-master-2", "sid-master-2")
    ter.poller(other, root2, [marker_red()], monkeypatch).round()
    (row2,) = ter.rows(folder2, "events.jsonl")
    assert row2["to"] == []
    masters = [d for d in ter.rows(folder2, "delta.jsonl") if d["role"] == "epic_master"]
    assert [(d["epic"], d["reason"]) for d in masters] == [("ACME-3215", "no running master")]
    assert masters[0]["line"].endswith(" · owner delta: coordinator · ACME-3215")


def test_route_epic_master_from_a_story_key(tmp_path, monkeypatch):
    """A PR's story key → its epic over the ticket snapshot; a parked master gets no PR line (delta);
    a key nobody knows is `epic unknown` with the PR number."""
    root = ter.project(tmp_path, MASTER_ROUTES)
    folder = tmp_path / "events"
    state = crew_board(tmp_path, monkeypatch)
    master_presence(folder, "sock-master-1", "sid-master-1")

    def red(n: int, story: str) -> es.Event:
        return es.Event(
            "pr_checks_red",
            f"prred:acme/app#{n}:1",
            f"pr:acme/app#{n}",
            None,
            {"repo": "acme/app", "number": n, "story": story, "check": "test", "check_id": n},
        )

    ter.poller(tmp_path, root, [red(7, "ACME-3216"), red(9, "ZZZ-1")], monkeypatch).round()
    rows = {r["object"]: r for r in ter.rows(folder, "events.jsonl")}
    assert rows["pr:acme/app#7"]["to"] == [{"session": "sock-master-1", "as": "epic_master"}]
    (unknown,) = ter.rows(folder, "delta.jsonl")
    assert (unknown["reason"], unknown["pr"]) == ("epic unknown", 9)
    board = json.loads((state / "board.json").read_text())
    board["sessions"][0]["state"] = "parked"
    (state / "board.json").write_text(json.dumps(board))
    ter.poller(tmp_path, root, [red(8, "ACME-3216"), marker_red(9004)], monkeypatch).round()
    rows = {r["object"]: r for r in ter.rows(folder, "events.jsonl")}
    assert rows["pr:acme/app#8"]["to"] == []  # parked: the PR line goes to the delta
    assert rows["run:9004"]["to"] == [{"session": "sock-master-1", "as": "epic_master"}]


def test_owners_report(tmp_path):
    """Every red event of the window has an owner: a delivery, a delta row, else `owner none`."""
    folder = tmp_path / "events"
    folder.mkdir()
    at = es.iso(NOW - 3600)
    ep.append_rows(
        folder / "events.jsonl",
        [
            {"seq": 1, "id": "a", "kind": "main_red", "object": "run:1", "source_at": at},
            {"seq": 2, "id": "b", "kind": "rc_verdict_red", "object": "run:2", "source_at": at},
            {"seq": 3, "id": "c", "kind": "main_red", "object": "run:3", "source_at": at},
            {"seq": 4, "id": "d", "kind": "pr_green", "object": "pr:x#1", "source_at": at},
            {
                "seq": 5,
                "id": "e",
                "kind": "main_red",
                "object": "run:5",
                "source_at": es.iso(NOW - 30 * 3600),
            },
        ],
    )
    ep.append_rows(
        folder / "ledger.jsonl",
        [
            {
                "id": "a",
                "to": "sock-master-1",
                "delivered": True,
                "delivered_at": es.iso(NOW - 3300),
            },
        ],
    )
    ep.append_rows(
        folder / "delta.jsonl",
        [
            {"id": "b", "role": "epic_master", "epic": "ACME-3215", "reason": "no running master"},
        ],
    )
    assert ep.owners_report(folder, NOW, ep.parse_since("24h")) == [
        f"{at} main_red run:1 · owner sock-master-1 delivered {es.iso(NOW - 3300)} (5 min)",
        f"{at} rc_verdict_red run:2 · delta: coordinator · ACME-3215",
        f"{at} main_red run:3 · owner none",
    ]
