"""crew_view.py: the crew's live sessions, once each, grouped and ordered; read-only, versioned."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import crew_view
import worker_supervisor

NOW = 1_763_668_800.0  # 2025-11-20T20:00:00Z
LIVE_PIDS = {101, 102, 103, 104, 105}


def at(minutes_ago):
    return crew_view._iso(NOW - minutes_ago * 60)


def minute(minutes_ago):
    return at(minutes_ago)[:16] + "Z"


@pytest.fixture(autouse=True)
def pids(monkeypatch):
    monkeypatch.setattr(worker_supervisor.wl, "_pid_lives", lambda pid: int(pid) in LIVE_PIDS)


ROWS = [
    {
        "name": "samu",
        "sessionId": "s-samu",
        "pid": 101,
        "kind": "interactive",
        "status": "idle",
        "startedAt": 1,
    },
    # the same session listed twice (a resumed row): the newest start counts, once
    {
        "name": "samu",
        "sessionId": "s-samu",
        "pid": 101,
        "kind": "interactive",
        "status": "idle",
        "startedAt": 2,
    },
    {
        "name": "lead",
        "sessionId": "s-lead",
        "pid": 102,
        "kind": "interactive",
        "status": "busy",
        "startedAt": 1,
    },
    {
        "name": "w-old",
        "sessionId": "s-w1",
        "pid": 103,
        "kind": "background",
        "state": "idle",
        "startedAt": 1,
    },
    {
        "name": "w-new",
        "sessionId": "s-w2",
        "pid": 104,
        "kind": "background",
        "state": "working",
        "startedAt": 1,
    },
    {
        "name": "w-lost",
        "sessionId": "s-w3",
        "pid": 105,
        "kind": "background",
        "state": "working",
        "startedAt": 1,
    },
    # stopped: its board line still stands
    {
        "name": "w-dead",
        "sessionId": "s-w4",
        "pid": 999,
        "kind": "background",
        "state": "idle",
        "startedAt": 1,
    },
]
ROLL = [
    {"name": "samu", "role": "coordinator", "loaded": "9.14.0", "workers": []},
    {"name": "lead", "role": "master", "loaded": "9.13.1", "workers": ["w-old", "w-new"]},
    {"name": "w-old", "role": "worker", "loaded": "9.14.0", "workers": []},
    {"name": "w-new", "role": "worker", "loaded": "9.14.0", "workers": []},
    {"name": "w-lost", "role": "worker", "loaded": "9.14.0", "workers": []},
]
LINES = [
    {
        "name": "samu",
        "session_id": "s-samu",
        "now": "Q-Triage PROJ-31",
        "waiting_on": "human",
        "since": minute(12),
        "updated_at": minute(3),
    },
    {"name": "lead", "session_id": "s-lead", "topic": "epic PROJ-1", "updated_at": minute(90)},
    {
        "name": "w-old",
        "keys": ["PROJ-2"],
        "waiting_on": "master",
        "since": minute(40),
        "blocked": {"kind": "chat", "since": at(45)},
        "updated_at": minute(5),
    },
    {"name": "w-new", "now": "tests", "updated_at": minute(20)},
    {"name": "w-dead", "now": "stopped long ago", "updated_at": minute(600)},
]


@pytest.fixture
def board(tmp_path):
    path = tmp_path / "board.json"
    path.write_text(json.dumps({"sessions": LINES}), encoding="utf-8")
    return path


def doc_of(board):
    return crew_view.document(rows=ROWS, roll=ROLL, board=board, now=NOW)


def test_each_live_session_once_and_a_stopped_worker_never(board):
    names = [e["name"] for e in doc_of(board)["sessions"]]
    assert sorted(names) == ["lead", "samu", "w-lost", "w-new", "w-old"]


def test_live_is_what_we_worker_status_shows(board, tmp_path):
    # the same rows through `we-worker status`: exactly the workers it does not mark exited are live
    status = worker_supervisor.status_lines([dict(r) for r in ROWS], None, tmp_path, tmp_path, NOW)
    running = {line.split()[1] for line in status if "exited(" not in line}
    exited = {line.split()[1] for line in status if "exited(" in line}
    shown = {e["name"] for e in doc_of(board)["sessions"] if e["kind"] == "background"}
    assert shown == running and exited == {"w-dead"}


def test_waiting_first_oldest_first_workers_under_their_starter(board):
    rows = doc_of(board)["sessions"]
    assert [(e["group"], e["name"]) for e in rows] == [
        ("samu", "samu"),  # waits
        ("lead", "lead"),
        ("lead", "w-old"),  # waits, under its starter
        ("lead", "w-new"),
        (crew_view.NO_STARTER, "w-lost"),  # no starter: its own group, last
    ]
    samu = rows[0]
    assert (samu["doing"], samu["waiting_on"], samu["age_s"], samu["plugin"]) == (
        "Q-Triage PROJ-31",
        "human",
        12 * 60,
        "9.14.0",
    )
    w_old = rows[2]
    assert (w_old["blocked_kind"], w_old["since"], w_old["doing"], w_old["starter"]) == (
        "chat",
        at(45),
        "PROJ-2",
        "lead",
    )
    assert (
        crew_view.text_line(samu)
        == "samu · coordinator · Q-Triage PROJ-31 · since 0h12 · waits: human · 9.14.0"
    )


def test_json_carries_schema_version_and_the_frozen_field_list(board):
    doc = doc_of(board)
    # Changing a field without raising SCHEMA_VERSION turns this red: the pane and the web read it.
    assert crew_view.SCHEMA_VERSION == 2
    assert sorted(doc) == ["board", "generated_at", "schema_version", "sessions"]
    assert doc["schema_version"] == 2
    assert crew_view.FIELDS == (
        "name",
        "session_id",
        "kind",
        "role",
        "state",
        "doing",
        "keys",
        "waiting_on",
        "blocked_kind",
        "since",
        "age_s",
        "plugin",
        "model",
        "starter",
        "group",
        "waits",
    )
    assert all(tuple(e) == crew_view.FIELDS for e in doc["sessions"])


def test_the_view_has_no_verb_and_writes_nothing(board, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(crew_view.worker_launch, "sessions", lambda: ROWS)
    monkeypatch.setattr(crew_view.session_refresh, "roll_call", lambda *_a, **_k: ROLL)
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")}
    assert crew_view.main(["--json", "--board", str(board)]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == 2
    assert {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")} == before
    with pytest.raises(SystemExit):
        crew_view.main(["set", "x"])  # no verb exists, a writing one least of all


def test_a_failed_roll_call_is_named_not_an_empty_crew(board, monkeypatch):
    def boom():
        raise crew_view.worker_launch.LaunchError("claude agents --json: exit 1")

    monkeypatch.setattr(crew_view.worker_launch, "sessions", boom)
    doc = crew_view.document(board=board, now=NOW)
    assert doc["sessions"] == [] and "exit 1" in doc["error"]


def test_a_missing_board_still_lists_the_live_sessions(tmp_path):
    doc = crew_view.document(rows=ROWS, roll=ROLL, board=tmp_path / "none.json", now=NOW)
    assert len(doc["sessions"]) == 5 and all(e["doing"] is None for e in doc["sessions"])


def test_age_text():
    assert [crew_view.age_text(s) for s in (None, 59, 720, 7800)] == ["?", "0h00", "0h12", "2h10"]
