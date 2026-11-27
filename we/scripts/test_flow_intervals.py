"""flow_intervals.py: intervals from the sampler, the board logs and the worker markers; the
summary both readers print; the page. Every fixture is written by its test, every window pinned."""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board  # noqa: E402
import flow_intervals as fi  # noqa: E402
import flow_report as fr  # noqa: E402

UTC = timezone.utc


def at(day, h, m, month=3):
    return datetime(2026, month, day, h, m, tzinfo=UTC)


def zt(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def mt(t):
    return t.strftime("%Y-%m-%dT%H:%MZ")


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def s(name, status, key=None, role=None, state=None):
    out = {"name": name, "session_id": "sid-" + name, "key": key, "role": role, "state": state}
    if status is not None:
        out["status"] = status
    return out


CREW = {
    "version": 2,
    "roles": {"product": "pat", "coordinator": "coord"},
    "members": {
        "pat": {"name": "Pat", "workplace": "."},
        "coord": {"name": "Coord", "workplace": "."},
    },
    "state_dir": "state",
    "board": {"file": "state/board.json"},
    "sla": {"tz": "UTC"},
}


PROJECT = "acme/flow-demo"
# the sessions this project's board names; workers belong through their starter
DEFAULT_LINES = tuple(
    {"name": n, "session_id": "sid-" + n} for n in ("alpha-7", "ret-1", "m-1", "ghost-session")
)


def make_state(
    tmp_path,
    first,
    last,
    sessions_at,
    locks_at=lambda _t: {},
    skip=lambda _t: False,
    events=(),
    waits=(),
    questions=(),
    answers=(),
    transitions=(),
    markers=None,
    monkeypatch=None,
    board_lines=DEFAULT_LINES,
):
    """A repo with a crew, a flow log from `first` to `last` (one probe every 5 min), the board
    with its session lines and crew stamp, its logs and the worker markers; returns
    `(root, board, log_dir, marker_dir)`."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    log_dir = tmp_path / "flow"
    crew = dict(CREW, flow={"log_dir": str(log_dir)})
    (root / ".weside").mkdir()
    (root / ".weside" / "crew.json").write_text(json.dumps(crew), encoding="utf-8")
    by_day: dict = {}
    t = first
    while t <= last:
        if not skip(t):
            line = {
                "type": "sample",
                "ts": zt(t),
                "interval_s": 300,
                "locks": locks_at(t),
                "sessions": sessions_at(t),
            }
            by_day.setdefault(t.strftime("%Y-%m-%d"), []).append(line)
        t += timedelta(minutes=5)
    for e in events:
        by_day.setdefault(e["ts"][:10], []).append(e)
    for day, rows in by_day.items():
        jsonl(log_dir / f"sampler-{day}.jsonl", sorted(rows, key=lambda r: r["ts"]))
    state = root / ".weside" / "state"
    board = state / "board.json"
    state.mkdir(parents=True, exist_ok=True)
    board.write_text(json.dumps({"sessions": list(board_lines)}), encoding="utf-8")
    (state / "crew.id").write_text(PROJECT + "\n", encoding="utf-8")
    jsonl(state / "board-waits.jsonl", list(waits))
    jsonl(state / "board-questions.jsonl", list(questions))
    jsonl(state / "board-answers.jsonl", list(answers))
    jsonl(state / "board-transitions.jsonl", list(transitions))
    mdir = tmp_path / "workers"
    mdir.mkdir()
    for name, doc in (markers or {}).items():
        (mdir / f"{name}.json").write_text(json.dumps({"name": name, **doc}), encoding="utf-8")
    (mdir / "ignored.settings.json").write_text("{}", encoding="utf-8")
    if monkeypatch is not None:
        monkeypatch.setenv("WE_WORKER_STATE_DIR", str(mdir))
    return root, board, log_dir, mdir


@pytest.fixture(autouse=True)
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("WE_STATE_DIR", raising=False)


# --- the main fixture: two days, the known cases ------------------------------------------------

SINCE, UNTIL = at(1, 0, 0), at(3, 0, 0)


def main_sessions(t):
    out = [
        s("alpha-7", "busy" if at(1, 9, 3) < t <= at(1, 11, 3) else "idle", role="master"),
        s("Coord", "idle", role="master"),
    ]
    if at(1, 6, 3) <= t <= at(1, 10, 3):
        out.append(s("ABC-101-build", "busy", key="ABC-101"))
    if at(1, 20, 3) <= t <= at(2, 21, 53):
        last = t == at(2, 21, 53)
        out.append(
            s(
                "ABC-102-fix",
                "busy" if t <= at(1, 21, 18) else "idle",
                key="ABC-102",
                state="blocked" if last else "working",
            )
        )
    if at(1, 0, 3) <= t <= at(1, 1, 3) or at(1, 2, 8) <= t <= at(1, 3, 3):
        out.append(s("ret-1", None))  # a probe without status; leaves and returns
    return out


def main_locks(t):
    out = {"gates": {"held": False, "holder": None}, "tests": {"held": False, "holder": None}}
    if t in (at(1, 7, 3), at(1, 7, 8), at(1, 7, 13)):
        out["gates"] = {"held": True, "holder": "abc-101-build"}
    if t in (at(1, 8, 3), at(1, 8, 8)):
        out["tests"] = {"held": True, "holder": "ghost-session"}
    return out


MAIN = {
    "first": at(1, 0, 3),
    "last": at(2, 23, 58),
    "sessions_at": main_sessions,
    "locks_at": main_locks,
    "events": [
        {
            "type": "blocked",
            "ts": zt(at(1, 15, 0)),
            "name": "alpha-7",
            "key": None,
            "kind": "chat",
            "starter": None,
            "waiting_on": "coordinator",
            "since": zt(at(1, 15, 0)),
        },
        {
            "type": "unblocked",
            "ts": zt(at(1, 15, 30)),
            "name": "alpha-7",
            "key": None,
            "kind": "chat",
            "starter": None,
            "waiting_on": "coordinator",
            "since": zt(at(1, 15, 0)),
            "duration_s": 1800,
        },
    ],
    "waits": [
        {
            "key": None,
            "session": "alpha-7",
            "waiting_on": "human",
            "since": mt(at(1, 10, 0)),
            "ended": zt(at(1, 12, 0)),
            "duration_s": 7200,
        },
        {
            "key": None,
            "session": "alpha-7",
            "waiting_on": "coordinator",
            "since": mt(at(1, 13, 0)),
            "ended": zt(at(1, 14, 0)),
            "duration_s": 3600,
        },
        {
            "key": None,
            "session": "alpha-7",
            "waiting_on": "human",
            "since": "garbage",
            "ended": zt(at(1, 14, 0)),
            "duration_s": None,
        },
        {
            "key": None,
            "session": "Coord",
            "waiting_on": "acceptance",
            "since": mt(at(1, 18, 0)),
            "ended": zt(at(1, 18, 30)),
            "duration_s": 1800,
        },
    ],
    "questions": [
        {
            "id": "Q1",
            "ts": zt(at(2, 20, 0)),
            "session": "Coord",
            "outcome": "posted",
            "cause": "info",
        },
        {
            "id": "Q2",
            "ts": zt(at(1, 17, 0)),
            "session": "alpha-7",
            "outcome": "posted",
            "cause": "plan",
        },
    ],
    "answers": [
        {"id": "Q1", "answer": "read", "ts": zt(at(2, 20, 10))},
        {"id": "Q2", "answer": "accept", "ts": zt(at(1, 17, 40))},
        {"id": "Q2", "answer": "accept", "ts": zt(at(1, 17, 20))},
    ],
    "transitions": [
        {"key": "ABC-101", "from": "backlog", "to": "selected", "ts": zt(at(1, 5, 0)), "by": "x"},
        {
            "key": "ABC-101",
            "from": "selected",
            "to": "in_review",
            "ts": zt(at(1, 12, 0)),
            "by": "x",
        },
    ],
    "markers": {
        "ABC-101-build": {"starter": "alpha-7", "started_at": zt(at(1, 6, 0))},
        "ABC-102-fix": {"starter": "alpha-7", "started_at": zt(at(1, 20, 0))},
    },
}


def build_main(tmp_path, monkeypatch, **over):
    root, board, log_dir, mdir = make_state(tmp_path, monkeypatch=monkeypatch, **{**MAIN, **over})
    crew = json.loads((root / ".weside" / "crew.json").read_text())
    return fi.build(board, mdir, log_dir, "UTC", crew, SINCE, UNTIL), root, board


def of(rows, who, kind=None):
    return [r for r in rows if r["who"] == who and (kind is None or r["kind"] == kind)]


def run_cli(root, capsys, *argv):
    """`main` without gh: `--no-ci` unless the test hands its own CI flags."""
    extra = [] if "--ci-fake" in argv else ["--no-ci"]
    code = fi.main([a for a in argv if a != "--ci-fake"] + extra, cwd=root)
    out = capsys.readouterr()
    return code, out.out, out.err


def test_intervals_from_fixture_sources(tmp_path, monkeypatch, capsys):
    root, board, _log, _m = make_state(tmp_path, monkeypatch=monkeypatch, **MAIN)
    code, out, err = run_cli(
        root,
        capsys,
        "--since",
        "2026-03-01",
        "--until",
        "2026-03-03T00:00",
        "--jsonl",
        "--board",
        str(board),
    )
    assert code == 0
    rows = [json.loads(line) for line in out.splitlines()]
    assert rows and all(all(r.get(k) for k in fi.REQUIRED) for r in rows)
    known = {
        "working",
        "waiting:human",
        "waiting:coordinator",
        "waiting:acceptance",
        "blocked",
        "idle-after-end",
        "idle",
        "parked",
        "holding:gates",
        "holding:tests",
    }
    assert {r["kind"] for r in rows if not r["kind"].startswith("stage:")} <= known
    a7 = of(rows, "alpha-7")
    # a busy probe beats an open wait; the idle rest of that wait is the wait
    assert [(r["start"], r["end"]) for r in of(a7, "alpha-7", "working")] == [
        (zt(at(1, 9, 3)), zt(at(1, 11, 3)))
    ]
    human = [(r["start"], r["end"]) for r in of(a7, "alpha-7", "waiting:human")]
    assert (zt(at(1, 11, 3)), zt(at(1, 12, 0))) in human
    # equal neighbours merge: one idle stretch between the wait and the coordinator wait
    assert any(
        r["start"] == zt(at(1, 12, 0)) and r["end"] == zt(at(1, 13, 0))
        for r in of(a7, "alpha-7", "idle")
    )
    # a question answered twice: the earlier answer ends the wait
    assert (zt(at(1, 17, 0)), zt(at(1, 17, 20))) in human
    # a question answered only by `read` stays open to the lane's end in the window
    q1 = of(rows, "Coord", "waiting:human")
    assert [(r["start"], r["end"]) for r in q1] == [(zt(at(2, 20, 0)), zt(at(2, 23, 58)))]
    # a session absent for more than two probe periods is parked in between
    assert [(r["start"], r["end"]) for r in of(rows, "ret-1", "parked")] == [
        (zt(at(1, 1, 3)), zt(at(1, 2, 8)))
    ]
    assert of(rows, "ret-1", "idle")  # probes without status are idle
    # the lock: one holding interval on the holder's lane beside its working
    gates = of(rows, "ABC-101-build", "holding:gates")
    assert [(r["start"], r["end"]) for r in gates] == [(zt(at(1, 7, 3)), zt(at(1, 7, 13)))]
    assert of(rows, "ABC-101-build", "working")
    assert len(of(rows, "ghost-session", "holding:tests")) == 1
    # stderr names every source with its rows and intervals, and the skipped waits row
    for source in ("sampler", "waits", "blocked", "questions", "answers", "transitions", "marker"):
        assert re.search(rf"flow_intervals: {source}: \d+ rows read.*, \d+ intervals", err), source
    # AC3: answers count the question waits an answer ended, transitions the story stages
    answered = re.search(r"flow_intervals: answers: (\d+) rows read.*, (\d+) intervals", err)
    staged = re.search(r"flow_intervals: transitions: (\d+) rows read.*, (\d+) intervals", err)
    assert int(answered.group(1)) > 0 and int(answered.group(2)) > 0, err
    assert int(staged.group(1)) > 0 and int(staged.group(2)) > 0, err
    stage_rows = [r for r in rows if r["kind"].startswith("stage:")]
    assert int(staged.group(2)) == len(stage_rows)
    assert "waits row skipped" in err and "'garbage'" in err


def test_lock_held_across_a_probe_gap_is_two_intervals(tmp_path, monkeypatch):
    def locks(t):
        return (
            {"tests": {"held": True, "holder": "ghost-session"}}
            if at(1, 5, 3) <= t <= at(1, 5, 53)
            else {}
        )

    built, _r, _b = build_main(
        tmp_path,
        monkeypatch,
        sessions_at=lambda _t: [s("alpha-7", "idle")],
        locks_at=locks,
        skip=lambda t: at(1, 5, 13) <= t <= at(1, 5, 43),
    )
    held = of(built["intervals"], "ghost-session", "holding:tests")
    assert [(r["start"], r["end"]) for r in held] == [
        (zt(at(1, 5, 3)), zt(at(1, 5, 8))),
        (zt(at(1, 5, 48)), zt(at(1, 5, 53))),
    ]
    assert built["lanes"]["ghost-session"]["group"] == "lock holders"


def test_known_case_worker_idle_after_end(tmp_path, monkeypatch):
    built, _r, _b = build_main(tmp_path, monkeypatch)
    tail = of(built["intervals"], "ABC-102-fix", "idle-after-end")
    assert len(tail) == 1
    start, end = fi.parse_ts(tail[0]["start"]), fi.parse_ts(tail[0]["end"])
    assert (start, end) == (at(1, 21, 18), at(2, 21, 53))
    assert end - start == timedelta(hours=24, minutes=35)
    assert end - max(start, at(2, 0, 0)) >= timedelta(hours=21)
    assert tail[0]["waiting_on"] == "alpha-7"
    data = fi.page_data(built)
    page_tail = [
        r for r in data["intervals"] if r["who"] == "ABC-102-fix" and r["kind"] == "idle-after-end"
    ]
    assert page_tail[0]["edge_to"] == "alpha-7"
    assert "alpha-7" in [lane["name"] for lane in data["lanes"]]
    row = next(w for w in data["summary"]["workers"]["rows"] if w["who"] == "ABC-102-fix")
    assert row["idle_after_end_h"] == "24.6" and row["blocked_h"] == "0.0"


def test_known_case_master_waits_on_coordinator(tmp_path, monkeypatch):
    built, _r, _b = build_main(tmp_path, monkeypatch)
    data = fi.page_data(built)
    coord = [
        r
        for r in data["intervals"]
        if r["who"] == "alpha-7" and r["kind"] == "waiting:coordinator"
    ]
    assert sorted((r["start"], r["end"], r["source"]) for r in coord) == [
        (zt(at(1, 13, 0)), zt(at(1, 14, 0)), "waits"),
        (zt(at(1, 15, 0)), zt(at(1, 15, 30)), "blocked"),
    ]
    assert {(r["waiting_on"], r["edge_to"]) for r in coord} == {("Coord", "Coord")}
    assert data["summary"]["matrix"]["alpha-7"]["Coord"] == "1.5"
    # a role no session holds stays a column with its role key and no edge
    acc = [r for r in data["intervals"] if r["kind"] == "waiting:acceptance"]
    assert {(r["who"], r["waiting_on"], r["edge_to"]) for r in acc} == {
        ("Coord", "acceptance", None)
    }
    assert data["summary"]["matrix"]["Coord"]["acceptance"] == "0.5"


# --- hand values ----------------------------------------------------------------------------------


def hand_sessions(t):
    out = []
    if t <= at(1, 12, 0, 4):
        out.append(
            s("m-1", "busy" if at(1, 2, 0, 4) < t <= at(1, 5, 0, 4) else "idle", role="master")
        )
    if at(1, 2, 0, 4) <= t <= at(1, 8, 0, 4):
        busy = at(1, 2, 0, 4) < t <= at(1, 4, 0, 4) or at(1, 5, 0, 4) < t <= at(1, 6, 0, 4)
        out.append(s("w-1", "busy" if busy else "idle", key="ABC-9"))
    if at(1, 3, 0, 4) <= t <= at(1, 5, 0, 4):
        out.append(
            s("w-2", "busy" if t <= at(1, 4, 0, 4) and t > at(1, 3, 0, 4) else "idle", key="ABC-9")
        )
    return out


HAND = {
    "first": at(1, 0, 0, 4),
    "last": at(1, 23, 55, 4),
    "sessions_at": hand_sessions,
    "locks_at": lambda t: (
        {"gates": {"held": True, "holder": "m-1"}} if at(1, 2, 0, 4) <= t <= at(1, 3, 0, 4) else {}
    ),
    "events": [
        {
            "type": "blocked",
            "ts": zt(at(1, 4, 0, 4)),
            "name": "w-1",
            "key": "ABC-9",
            "kind": "permission",
            "starter": "m-1",
            "waiting_on": None,
            "since": zt(at(1, 4, 0, 4)),
        },
        {
            "type": "unblocked",
            "ts": zt(at(1, 5, 0, 4)),
            "name": "w-1",
            "key": "ABC-9",
            "kind": "permission",
            "starter": "m-1",
            "waiting_on": None,
            "since": zt(at(1, 4, 0, 4)),
            "duration_s": 3600,
        },
    ],
    "transitions": [
        {"key": "ABC-9", "to": "selected", "ts": zt(at(1, 1, 0, 4))},
        {"key": "ABC-9", "to": "in_progress", "ts": zt(at(1, 2, 0, 4))},
        {"key": "ABC-9", "to": "in_review", "ts": zt(at(1, 6, 0, 4))},
    ],
    "markers": {
        "w-1": {"starter": "m-1", "started_at": zt(at(1, 1, 0, 4))},
        "w-2": {"starter": "m-1"},
    },
}
H_SINCE, H_UNTIL = at(1, 0, 0, 4), at(2, 0, 0, 4)


def build_hand(tmp_path, monkeypatch):
    root, board, log_dir, mdir = make_state(tmp_path, monkeypatch=monkeypatch, **HAND)
    crew = json.loads((root / ".weside" / "crew.json").read_text())
    return fi.build(board, mdir, log_dir, "UTC", crew, H_SINCE, H_UNTIL), root, board


def test_efficiency_matches_hand_values(tmp_path, monkeypatch):
    built, _r, _b = build_hand(tmp_path, monkeypatch)
    f = fi.format_summary(fi.summary(built))
    # story ABC-9: w-1 02-04 and 05-06, w-2 03-04 = 4 h of 01-06 = 5 h
    assert f["stories"]["rows"] == [
        {"key": "ABC-9", "working_h": "4.0", "lead_h": "5.0", "ratio": "0.80", "sessions": "2"}
    ]
    # master m-1: 3 h working of 12 h alive; its workers wait on it 1 h blocked + 2 h + 1 h after end;
    # holding the gates lock (1 h) counts in no ratio
    assert f["masters"]["rows"] == [
        {
            "who": "m-1",
            "working_h": "3.0",
            "alive_h": "12.0",
            "ratio": "0.25",
            "waited_on_h": "4.0",
        }
    ]
    assert f["locks"] == [{"lock": "gates", "holder": "m-1", "hours": "1.0", "n": "1"}]
    w1, w2 = f["workers"]["rows"]
    # w-1: 3 h working of started_at 01:00 → last probe 08:00, blocked and idle after end apart
    assert (w1["who"], w1["working_h"], w1["span_h"], w1["ratio"]) == ("w-1", "3.0", "7.0", "0.43")
    assert (w1["blocked_h"], w1["idle_after_end_h"], w1["start"]) == (
        "1.0",
        "2.0",
        "start = marker",
    )
    # w-2 has no started_at: it starts at its first probe
    assert (w2["who"], w2["working_h"], w2["span_h"], w2["ratio"]) == ("w-2", "1.0", "2.0", "0.50")
    assert (w2["idle_after_end_h"], w2["start"]) == ("1.0", "start = first probe")
    assert f["workers"]["window"].endswith("stop = last probe, ±5 min")
    assert (f["stories"]["n"], f["masters"]["n"], f["workers"]["n"]) == ("1", "1", "2")
    assert built["missing_started"] == 1


# --- readers --------------------------------------------------------------------------------------


def page_json(text):
    found = re.search(r'<script type="application/json" id="flow-data">(.*?)</script>', text, re.S)
    return json.loads(found.group(1))


def md_report(root, board, *extra, since=H_SINCE, until=H_UNTIL):
    args = fr.argparse.Namespace(
        since=since,
        repo=None,
        board=str(board),
        gh_cache=None,
        review_match="review",
        from_=list(extra),
    )
    return fr.build(args, until, root, None, lambda _r: [])


def test_page_and_table_agree(tmp_path, monkeypatch, capsys):
    _built, root, board = build_hand(tmp_path, monkeypatch)
    page = tmp_path / "flow.html"
    code, _out, _err = run_cli(
        root,
        capsys,
        "--since",
        "2026-04-01",
        "--until",
        "2026-04-02T00:00",
        "--board",
        str(board),
        "--html",
        str(page),
    )
    assert code == 0
    data = page_json(page.read_text(encoding="utf-8"))
    report = md_report(root, board)
    md = fr.render_md(report)
    lines = {
        line.split(" | ")[0].lstrip("| "): line
        for line in md.splitlines()
        if line.startswith("| ")
    }
    summ = data["summary"]
    assert report["flow_efficiency"]["summary"] == summ
    for x in summ["stories"]["rows"]:
        line = lines[f"Story efficiency: {x['key']}"]
        assert all(x[k] in line for k in ("ratio", "working_h", "lead_h"))
    for x in summ["masters"]["rows"]:
        line = lines[f"Master efficiency: {x['who']}"]
        assert all(x[k] in line for k in ("ratio", "working_h", "alive_h", "waited_on_h"))
    for x in summ["workers"]["rows"]:
        line = lines[f"Worker efficiency: {x['who']}"]
        assert all(
            f" {x[k]} " in line for k in ("working_h", "span_h", "blocked_h", "idle_after_end_h")
        )
        assert line.split(" | ")[4].startswith(x["ratio"])
    for kind, v in summ["waiting"].items():
        line = lines[f"Waiting by kind: {kind}"]
        assert v["hours"] in line and (v["n"] == "n/a" or f"| {v['n']} |" in line)
    for label in ("Story", "Master", "Worker"):
        part = summ[{"Story": "stories", "Master": "masters", "Worker": "workers"}[label]]
        assert (
            f"| {part['n']} | {part['median']} | {part['p90']} |"
            in lines[f"{label} efficiency (ratio)"]
        )


def test_page_data_is_the_html_pages_data_byte_for_byte(tmp_path, monkeypatch, capsys):
    """`--page-data` (the web view's source) carries the data `--html` embeds: the page rendered
    from it equals the `--html` file byte for byte, so the web view adds no field of its own."""
    _built, root, board = build_hand(tmp_path, monkeypatch)
    window = ("--since", "2026-04-01", "--until", "2026-04-02T00:00", "--board", str(board))
    page = tmp_path / "flow.html"
    assert run_cli(root, capsys, *window, "--html", str(page))[0] == 0
    code, out, _err = run_cli(root, capsys, *window, "--page-data")
    assert code == 0
    assert fi.render_page(json.loads(out)).encode() == page.read_bytes()


def test_no_silent_gap(tmp_path, monkeypatch, capsys):
    root, board, log_dir, _m = make_state(tmp_path, monkeypatch=monkeypatch, **MAIN)
    argv = [
        "--since",
        "2026-03-01",
        "--until",
        "2026-03-03T00:00",
        "--board",
        str(board),
        "--html",
    ]
    page = tmp_path / "a.html"
    run_cli(root, capsys, *argv, str(page))
    control = page_json(page.read_text(encoding="utf-8"))
    report = md_report(root, board, since=SINCE, until=UNTIL)
    assert control["gaps"] == [] and "Flow gap" not in fr.render_md(report)
    # one sampler day gone, the waits log unreadable
    (log_dir / "sampler-2026-03-02.jsonl").unlink()
    waits = board.with_name("board-waits.jsonl")
    waits.unlink()
    waits.mkdir()
    page = tmp_path / "b.html"
    run_cli(root, capsys, *argv, str(page))
    data = page_json(page.read_text(encoding="utf-8"))
    reasons = [g["reason"] for g in data["gaps"]]
    assert "no data: sampler 2026-03-02" in reasons and "source unreadable: waits log" in reasons
    day2 = at(2, 0, 0)
    assert all(fi.parse_ts(r["end"]) <= day2 for r in data["intervals"])
    assert any(g["kind"] == "no-data" and g["start"] == zt(day2) for g in data["gap_rows"])
    md = fr.render_md(md_report(root, board, since=SINCE, until=UNTIL))
    assert "| Flow gap: sampler |  |  |  | n/a (no data: sampler 2026-03-02) |" in md
    assert "n/a (source unreadable: waits log)" in md


def test_harness_neutral_rows_and_from(tmp_path, monkeypatch, capsys):
    _built, root, board = build_hand(tmp_path, monkeypatch)
    foreign = tmp_path / "other.jsonl"
    foreign.write_text(
        json.dumps(
            {
                "id": "x1",
                "start": zt(at(1, 9, 0, 4)),
                "end": zt(at(1, 11, 0, 4)),
                "kind": "review-wait",
                "who": "ext-agent",
                "source": "other-harness",
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": "x2",
                "start": zt(at(1, 9, 0, 4)),
                "end": zt(at(1, 10, 0, 4)),
                "kind": "working",
                "source": "other-harness",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    window = ["--since", "2026-04-01", "--until", "2026-04-02T00:00", "--board", str(board)]
    code, out, err = run_cli(root, capsys, *window, "--from", str(foreign))
    assert code == 0
    rows = [json.loads(line) for line in out.splitlines()]
    assert any(r["who"] == "ext-agent" and r["kind"] == "review-wait" for r in rows)
    assert f"{foreign}:2: missing who" in err
    assert any(r["kind"] == "no-data" and "other.jsonl:2" in r["reason"] for r in rows)
    page = tmp_path / "f.html"
    run_cli(root, capsys, *window, "--from", str(foreign), "--html", str(page))
    data = page_json(page.read_text(encoding="utf-8"))
    lane = next(lane for lane in data["lanes"] if lane["name"] == "ext-agent")
    assert lane["group"] == "foreign"
    assert any(r["kind"] == "review-wait" for r in data["intervals"])
    assert any("other.jsonl:2" in g["reason"] for g in data["gaps"])
    md = fr.render_md(md_report(root, board, str(foreign)))
    assert "| Waiting by kind: review-wait | 1 | 2.0 h | 2.0 h | 2.0 h |" in md
    assert "other.jsonl:2 (missing who)" in md


EVIL_NAME = "<img src=x onerror=alert(1)>"
EVIL_KEY = "</script><script>alert(1)</script>"


def evil_page(tmp_path, monkeypatch, escape):
    root, board, log_dir, mdir = make_state(
        tmp_path,
        monkeypatch=monkeypatch,
        first=at(1, 0, 0, 4),
        last=at(1, 2, 0, 4),
        sessions_at=lambda _t: [s(EVIL_NAME, "busy", key=EVIL_KEY)],
        board_lines=[{"name": EVIL_NAME}],
    )
    crew = json.loads((root / ".weside" / "crew.json").read_text())
    built = fi.build(board, mdir, log_dir, "UTC", crew, H_SINCE, H_UNTIL)
    return fi.render_page(fi.page_data(built, ["see <b>this</b>"]), escape=escape)


def closes_once(text):
    """Exactly one `</script>` between the data block's opening tag and the page's script."""
    start = text.index('<script type="application/json" id="flow-data">')
    end = text.rindex("<script>")
    return text[start:end].count("</script>") == 1


def test_page_self_contained_and_escaped(tmp_path, monkeypatch):
    text = evil_page(tmp_path, monkeypatch, escape=True)
    assert text.count('<script type="application/json"') == 1
    assert closes_once(text)
    assert "\\u003c/script\\u003e" in text
    for banned in ("http://", "https://", "fetch(", "XMLHttpRequest", "<link", "innerHTML"):
        assert banned not in text, banned
    assert not re.search(r"""(src|href)\s*=\s*["']?[^"'\s>]""", text.split('id="flow-data">')[0])
    assert not re.search(r"""(src|href)\s*=\s*["']?//|url\(\s*["']?//""", text)
    assert "textContent" in text
    data = page_json(text)
    assert data["lanes"][0]["name"] == EVIL_NAME and data["intervals"][0]["key"] == EVIL_KEY
    assert data["header"][:3] == [
        "one probe every 300 s: each bar edge ±5 min",
        "Not counted: waiting that only transcripts show; this page has no such source.",
        "CI wait: off (--no-ci)",
    ]
    assert data["header"][3] == "see <b>this</b>" and "<b>" not in text
    # control: without the escaping the key closes the data block early
    assert not closes_once(evil_page(tmp_path / "control", monkeypatch, escape=False))


def test_moved_helpers_have_one_home():
    for name in ("locate_board", "parse_ts", "parse_since", "read_jsonl", "question_waits"):
        assert getattr(fr, name) is getattr(fi, name), name


def test_question_wait_ends_at_the_boards_closing_outcomes():
    """A posted question's wait ends at the first line board.py counts as closing; a refused ask
    (`returned`, `duplicate`) logs no id and leaves the wait to the window end."""
    assert board.QUESTION_CLOSED == board.GONE + board.OFF_BOARD
    until = at(1, 12, 0)
    for outcome in board.QUESTION_CLOSED:
        questions = [
            {"id": "Q1", "ts": zt(at(1, 9, 0)), "outcome": "posted", "session": "m-1"},
            {"ts": zt(at(1, 9, 30)), "outcome": "returned", "session": "m-1"},
            {"id": "Q1", "ts": zt(at(1, 10, 0)), "outcome": outcome},
        ]
        out: dict = defaultdict(list)
        fi._question_rows(SimpleNamespace(until=until), questions, [], out)
        assert [(r[0], r[1]) for r in out["m-1"]] == [(at(1, 9, 0), at(1, 10, 0))], outcome
    out = defaultdict(list)
    fi._question_rows(SimpleNamespace(until=until), questions[:2], [], out)
    assert [(r[0], r[1]) for r in out["m-1"]] == [(at(1, 9, 0), until)]


def _with_queue(board, queue):
    doc = json.loads(board.read_text(encoding="utf-8"))
    board.write_text(json.dumps({**doc, "owner_queue": queue}), encoding="utf-8")


def _rebuild(root, board):
    crew = json.loads((root / ".weside" / "crew.json").read_text())
    mdir = Path(os.environ["WE_WORKER_STATE_DIR"])
    return fi.build(board, mdir, root.parent / "flow", "UTC", crew, SINCE, UNTIL)


def test_question_that_left_the_queue_draws_no_wait(tmp_path, monkeypatch):
    """AC 1 and 2: an unanswered question without a closing line waits on human only while the
    board's `owner_queue` holds it; one that left the queue draws no wait and one gap line counts it."""
    _built, root, board = build_main(tmp_path, monkeypatch)
    _with_queue(board, [{"id": "Q9", "kind": "question"}])
    built = _rebuild(root, board)
    assert of(built["intervals"], "Coord", "waiting:human") == []
    reasons = [g["reason"] for g in built["gaps"]]
    assert "questions: 1 left the queue without an answer or closing line" in reasons
    # the answered question stays as it was
    assert of(built["intervals"], "alpha-7", "waiting:human")

    _with_queue(board, [{"id": "Q1", "kind": "question"}])
    built = _rebuild(root, board)
    q1 = of(built["intervals"], "Coord", "waiting:human")
    assert [(r["start"], r["end"]) for r in q1] == [(zt(at(2, 20, 0)), zt(at(2, 23, 58)))]
    assert not [g for g in built["gaps"] if g["reason"].startswith("questions:")]


def test_question_wait_without_a_readable_queue_runs_to_the_window_end(tmp_path):
    """AC 3: a board that is unreadable, missing or without `owner_queue` keeps the wait open to
    the window end and names no orphan gap."""
    until = at(1, 12, 0)
    questions = [{"id": "Q1", "ts": zt(at(1, 9, 0)), "outcome": "posted", "session": "m-1"}]
    bad = tmp_path / "board.json"
    bad.write_text("{not json", encoding="utf-8")
    plain = tmp_path / "plain.json"
    plain.write_text(json.dumps({"sessions": []}), encoding="utf-8")
    for path in (bad, tmp_path / "missing.json", plain, None):
        src = fi.Sources(at(1, 0, 0), until)
        _lines, queue = fi.read_board(src, path)
        assert queue is None, path
        out: dict = defaultdict(list)
        fi._question_rows(src, questions, [], out, queue)
        assert [(r[0], r[1]) for r in out["m-1"]] == [(at(1, 9, 0), until)], path
        assert not [g for g in src.gaps if g["reason"].startswith("questions:")], path
    # control: the same question with a readable empty queue draws none
    src = fi.Sources(at(1, 0, 0), until)
    out = defaultdict(list)
    fi._question_rows(src, questions, [], out, set())
    assert out["m-1"] == []


def test_ended_worker_without_marker_and_span_in_the_window(tmp_path, monkeypatch):
    """A marker goes when its worker ends: the probe's role and a `blocked` event keep the worker
    and its starter. A span that started before the window is clipped to it."""

    def sessions(t):
        out = [s("m-1", "idle", role="master")]
        if t <= at(1, 3, 0, 4):
            out.append(s("gone-1", "busy" if t <= at(1, 1, 0, 4) else "idle", role="worker"))
        if t <= at(1, 4, 0, 4):
            out.append(s("w-old", "busy" if t <= at(1, 2, 0, 4) else "idle"))
        return out

    root, board, log_dir, mdir = make_state(
        tmp_path,
        monkeypatch=monkeypatch,
        first=at(1, 0, 0, 4),
        last=at(1, 23, 55, 4),
        sessions_at=sessions,
        events=[
            {
                "type": "blocked",
                "ts": zt(at(1, 0, 30, 4)),
                "name": "gone-1",
                "kind": "chat",
                "starter": "m-1",
                "waiting_on": "human",
                "since": zt(at(1, 0, 30, 4)),
            },
            {
                "type": "unblocked",
                "ts": zt(at(1, 0, 40, 4)),
                "name": "gone-1",
                "kind": "chat",
                "starter": "m-1",
                "waiting_on": "human",
                "since": zt(at(1, 0, 30, 4)),
            },
        ],
        markers={"w-old": {"starter": "m-1", "started_at": zt(at(30, 0, 0, 3))}},
    )
    crew = json.loads((root / ".weside" / "crew.json").read_text())
    built = fi.build(board, mdir, log_dir, "UTC", crew, H_SINCE, H_UNTIL)
    assert built["lanes"]["gone-1"]["role"] == "worker"
    assert built["lanes"]["gone-1"]["starter"] == "m-1"
    tail = of(built["intervals"], "gone-1", "idle-after-end")
    assert [(r["start"], r["end"], r["waiting_on"]) for r in tail] == [
        (zt(at(1, 1, 0, 4)), zt(at(1, 3, 0, 4)), "m-1")
    ]
    workers = {w["who"]: w for w in fi.format_summary(fi.summary(built))["workers"]["rows"]}
    # started two days before the window: the span runs from the window's start to the last probe
    assert (workers["w-old"]["span_h"], workers["w-old"]["ratio"]) == ("4.0", "0.50")


# --- one project per page -------------------------------------------------------------------------


def two_projects(t):
    """One host sampler: this project's master and its worker beside another project's sessions."""
    out = [
        s("alpha-7", "busy" if t <= at(1, 6, 0, 4) else "idle", role="master"),
        s("other-1", "busy", role="master"),
        s("stray-9", "idle"),
    ]
    if t <= at(1, 6, 0, 4):
        out += [s("ABC-1-build", "busy", key="ABC-1"), s("XYZ-1-build", "busy", key="XYZ-1")]
        out.append(s("ABC-7-late", "busy", key="ABC-7"))  # no marker, no starter: its key
        out.append({"name": "nosid-1", "status": "busy"})  # an old probe without session_id
    return out


def two_project_state(tmp_path, monkeypatch, stamp=True):
    root, board, _log_dir, _mdir = make_state(
        tmp_path,
        monkeypatch=monkeypatch,
        first=at(1, 0, 0, 4),
        last=at(1, 12, 0, 4),
        sessions_at=two_projects,
        locks_at=lambda t: (
            {"gates": {"held": True, "holder": "other-1"}} if t <= at(1, 1, 0, 4) else {}
        ),
        events=[
            {
                "type": "blocked",
                "ts": zt(at(1, 2, 0, 4)),
                "name": "XYZ-1-build",
                "kind": "chat",
                "starter": "other-1",
                "waiting_on": "human",
                "since": zt(at(1, 2, 0, 4)),
            }
        ],
        waits=[
            {"session": "alpha-7", "waiting_on": "human", "since": mt(at(1, 7, 0, 4))},
            # an old line of the other project in this board's log
            {
                "session": "zed-old",
                "key": "XYZ-9",
                "waiting_on": "human",
                "since": mt(at(1, 7, 0, 4)),
            },
        ],
        transitions=[{"key": "ABC-7", "to": "selected", "ts": zt(at(1, 1, 0, 4))}],
        markers={
            "ABC-1-build": {"starter": "alpha-7", "starter_session": "sid-alpha-7"},
            "XYZ-1-build": {"starter": "other-1", "starter_session": "sid-other-1"},
        },
    )
    if not stamp:
        board.with_name("crew.id").unlink()
    foreign = tmp_path / "rows.jsonl"
    jsonl(
        foreign,
        [
            {
                "id": "f1",
                "start": zt(at(1, 3, 0, 4)),
                "end": zt(at(1, 4, 0, 4)),
                "kind": "working",
                "who": "ext-mine",
                "source": "h",
                "project": PROJECT,
            },
            {
                "id": "f2",
                "start": zt(at(1, 3, 0, 4)),
                "end": zt(at(1, 4, 0, 4)),
                "kind": "working",
                "who": "ext-theirs",
                "source": "h",
                "project": "zeta/other",
            },
            {
                "id": "f3",
                "start": zt(at(1, 3, 0, 4)),
                "end": zt(at(1, 4, 0, 4)),
                "kind": "working",
                "who": "ext-plain",
                "source": "h",
            },
        ],
    )
    return root, board, foreign


def test_one_project_per_page_and_table(tmp_path, monkeypatch, capsys):
    root, board, foreign = two_project_state(tmp_path, monkeypatch)
    page = tmp_path / "p.html"
    window = ["--since", "2026-04-01", "--until", "2026-04-02T00:00", "--board", str(board)]
    code, _out, err = run_cli(root, capsys, *window, "--from", str(foreign), "--html", str(page))
    assert code == 0
    text = page.read_text(encoding="utf-8")
    assert f"<title>Crew flow · {PROJECT}</title>" in text
    assert "'Project: '+D.project" in text
    data = page_json(text)
    assert data["project"] == PROJECT
    lanes = {lane["name"] for lane in data["lanes"] if lane["group"] != "stories"}
    assert lanes == {"alpha-7", "ABC-1-build", "ABC-7-late", "ext-mine", "ext-plain"}
    stories = {lane["name"] for lane in data["lanes"] if lane["group"] == "stories"}
    assert stories == {"ABC-7"}  # its transitions draw the story's stage lane
    assert {r["who"] for r in data["intervals"]} == lanes | stories
    assert not any(r["kind"].startswith("holding:") for r in data["intervals"])
    att = data["attribution"]
    # 145 probes: alpha-7 every probe, ABC-1-build to 06:00; other-1, stray-9, XYZ-1-build dropped
    assert (att["kept_sessions"], att["dropped_sessions"]) == (3, 4)
    assert (att["kept_rows"], att["dropped_rows"]) == (145 + 73 + 73, 145 + 145 + 73 + 73)
    assert (att["dropped_events"], att["dropped_locks"]) == (1, 13)
    assert (att["dropped_log_rows"], att["dropped_foreign"]) == (1, 1)
    assert any(r["who"] == "alpha-7" and r["source"] == "waits" for r in data["intervals"])
    reasons = [g["reason"] for g in data["gaps"]]
    dropped = (
        f"not attributed to {PROJECT}: 436 sampler rows of 4 sessions, "
        "1 blocked events, 13 lock probes, 1 board log waits dropped"
    )
    assert dropped in reasons and "other project: 1 rows of rows.jsonl dropped" in reasons
    assert f"project {PROJECT}: 291 sampler rows of 3 sessions kept, 436 rows" in err
    md = fr.render_md(md_report(root, board, str(foreign)))
    assert f"n/a ({dropped})" in md and "n/a (other project: 1 rows of rows.jsonl dropped)" in md
    assert "Flow project" in md and f"{PROJECT}: 291 sampler rows" in md
    for name in ("other-1", "stray-9", "XYZ-1-build", "zed-old", "nosid-1", "ext-theirs"):
        assert f"efficiency: {name} " not in md, name
    assert "Master efficiency: alpha-7" in md and "Worker efficiency: ABC-1-build" in md


def test_project_name_arrives_as_text(tmp_path, monkeypatch, capsys):
    root, board, _f = two_project_state(tmp_path, monkeypatch, stamp=False)
    evil = '</title><script>alert(1)</script>"&/*JS*/'
    page = tmp_path / "e.html"
    window = ["--since", "2026-04-01", "--until", "2026-04-02T00:00", "--board", str(board)]
    code, _o, _e = run_cli(root, capsys, *window, "--project", evil, "--html", str(page))
    assert code == 0
    text = page.read_text(encoding="utf-8")
    title = "&lt;/title&gt;&lt;script&gt;alert(1)&lt;/script&gt;&quot;&amp;/*JS*/"
    assert f"<title>Crew flow · {title}</title>" in text
    assert text.count("<script>") == 1 and closes_once(text)
    assert page_json(text)["project"] == evil
    # a board stamped for one project refuses another name
    board.with_name("crew.id").write_text(PROJECT + "\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        run_cli(root, capsys, *window, "--project", "zeta/other", "--jsonl")
    assert exc.value.code == 2


def test_launched_log_names_the_starter_of_an_ended_worker(tmp_path, monkeypatch):
    """AC1 of the starter log: no marker, no `blocked` event; the launcher's line keeps the
    starter, the lane's `session_id` feeds `backfill-starters`, and `starterless` names the rest."""

    def sessions(t):
        out = [s("m-1", "idle", role="master")]
        if t <= at(1, 2, 0, 4):
            out.append(s("gone-2", "busy" if t <= at(1, 1, 0, 4) else "idle", role="worker"))
            out.append(s("lost-3", "busy", role="worker"))
        return out

    root, board, log_dir, mdir = make_state(
        tmp_path,
        monkeypatch=monkeypatch,
        first=at(1, 0, 0, 4),
        last=at(1, 23, 55, 4),
        sessions_at=sessions,
        board_lines=(*DEFAULT_LINES, {"name": "lost-3", "session_id": "sid-lost-3"}),
    )
    jsonl(
        mdir / "launched.jsonl",
        [{"name": "gone-2", "key": None, "starter": "m-1", "starter_session": None, "ts": "x"}],
    )
    crew = json.loads((root / ".weside" / "crew.json").read_text())
    built = fi.build(board, mdir, log_dir, "UTC", crew, H_SINCE, H_UNTIL)
    assert built["lanes"]["gone-2"]["starter"] == "m-1"
    assert built["lanes"]["gone-2"]["session_id"] == "sid-gone-2"
    assert built["counts"]["launched"]["rows"] == 1
    assert fi.starterless(built) == [("lost-3", "sid-lost-3")]


def _stage_state(tmp_path, monkeypatch):
    moves = [("selected", at(1, 1, 0, 4)), ("in_progress", at(1, 2, 0, 4))]
    moves += [("in_review", at(1, 6, 0, 4)), ("done", at(1, 9, 0, 4))]
    return make_state(
        tmp_path,
        monkeypatch=monkeypatch,
        first=at(1, 0, 0, 4),
        last=at(1, 23, 55, 4),
        sessions_at=lambda t: [s("m-1", "busy" if t < at(1, 4, 0, 4) else "idle", role="master")],
        transitions=[
            {"ts": zt(ts), "key": "ABC-9", "from": None, "to": to, "by": "m-1"} for to, ts in moves
        ],
    )


def test_story_stage_lanes(tmp_path, monkeypatch):
    """AC4: one lane per story in group `stories`, one `stage:<to>` per stage, In Review reads
    "waits on acceptance"; the stage hours count in no ratio and in no wait."""
    root, board, log_dir, mdir = _stage_state(tmp_path, monkeypatch)
    crew = json.loads((root / ".weside" / "crew.json").read_text())
    built = fi.build(board, mdir, log_dir, "UTC", crew, H_SINCE, H_UNTIL)
    assert built["lanes"]["ABC-9"]["group"] == "stories"
    rows = [(r["kind"], r["start"], r["end"]) for r in of(built["intervals"], "ABC-9")]
    assert rows == [
        ("stage:selected", zt(at(1, 1, 0, 4)), zt(at(1, 2, 0, 4))),
        ("stage:in_progress", zt(at(1, 2, 0, 4)), zt(at(1, 6, 0, 4))),
        ("stage:in_review", zt(at(1, 6, 0, 4)), zt(at(1, 9, 0, 4))),
    ]
    review = of(built["intervals"], "ABC-9", "stage:in_review")[0]
    assert review["label"] == "waits on acceptance" and not review.get("waiting_on")
    assert built["counts"]["transitions"]["intervals"] == 3
    sm = fi.summary(built)
    assert not any(k.startswith("stage:") for k in sm["waiting"])
    assert not any(t["kind"].startswith("stage:") for t in sm["top"])
    assert "ABC-9" not in sm["matrix"] and [x["key"] for x in sm["stories"]] == ["ABC-9"]
    text = fi.render_page(fi.page_data(built))
    assert "'waits on acceptance'" in text and "'Stories (stage)'" in text


def test_flow_intervals_json_snapshot(tmp_path, monkeypatch, capsys):
    """AC7: `--json` is one document whose field list is pinned; `generated_at` and
    `schema_version` lead it; the `now` block names who works and waits at the window's end."""
    root, _board, _log, _m = _stage_state(tmp_path, monkeypatch)
    code, out, _err = run_cli(
        root, capsys, "--since", "2026-04-01", "--until", "2026-04-02T00:00", "--json"
    )
    assert code == 0
    doc = json.loads(out)
    assert list(doc) == [
        "schema_version",
        "generated_at",
        "project",
        "window",
        "header",
        "sources",
        "ci",
        "lanes",
        "now",
        "intervals",
        "gaps",
        "summary",
    ]
    assert doc["schema_version"] == 1 and re.fullmatch(r"\d{4}-.*Z", doc["generated_at"])
    assert doc["ci"] == {"state": "off", "gap": "ci: off (--no-ci)", "fetched_at": None, "prs": []}
    assert sorted(doc["now"][0]) == [
        "board_now",
        "group",
        "key",
        "kind",
        "label",
        "since",
        "starter",
        "topic",
        "waiting_on",
        "who",
    ]
    assert sorted(doc["sources"]["transitions"]) == ["bad", "intervals", "rows"]
    assert any(n["who"] == "m-1" and n["kind"] == "idle" for n in doc["now"])


def test_now_rows_carry_board_topic_and_now(tmp_path, monkeypatch):
    """A lane with a board line carries its `topic` and `now` (as `board_now`, matched
    by name, else by `session_id`, whitespace folded); a lane without one carries None."""
    lines = (
        {"name": "M-1", "session_id": "sid-m-1", "topic": "ABC-9 tune", "now": "step 1\n  home"},
        {"name": "other", "session_id": "sid-w-2", "topic": "by sid", "now": ""},
        {"name": "w-3", "session_id": "sid-x"},
    )
    root, board, log_dir, mdir = make_state(
        tmp_path,
        monkeypatch=monkeypatch,
        first=at(1, 0, 0, 4),
        last=at(1, 23, 55, 4),
        sessions_at=lambda _t: [
            s("m-1", "busy", role="master"),
            s("w-2", "busy"),
            s("w-3", "busy"),
        ],
        board_lines=lines,
    )
    crew = json.loads((root / ".weside" / "crew.json").read_text())
    built = fi.build(board, mdir, log_dir, "UTC", crew, H_SINCE, H_UNTIL)
    rows = {n["who"]: n for n in fi.now_rows(built)}
    assert (rows["m-1"]["topic"], rows["m-1"]["board_now"]) == ("ABC-9 tune", "step 1 home")
    assert (rows["w-2"]["topic"], rows["w-2"]["board_now"]) == ("by sid", None)
    assert (rows["w-3"]["topic"], rows["w-3"]["board_now"]) == (None, None)


def _tree(path: Path) -> dict:
    return {
        str(p.relative_to(path)): p.stat().st_mtime_ns
        for p in sorted(path.rglob("*"))
        if p.is_file()
    }


def test_no_verb_writes_outside_its_snapshot_dir(tmp_path, monkeypatch, capsys):
    """AC7: every verb of `flow_intervals.py` leaves HOME and the state as they were; only
    `--snapshot DIR` writes, and only its two files, through a temp file."""
    root, _board, _log, _m = _stage_state(tmp_path, monkeypatch)
    window = ["--since", "2026-04-01", "--until", "2026-04-02T00:00"]
    before = _tree(tmp_path)
    for verb in ([], ["--jsonl"], ["--json"], ["--snapshot-path"]):
        assert run_cli(root, capsys, *window, *verb)[0] == 0
        assert _tree(tmp_path) == before, verb
    snap = tmp_path / "snap"
    assert run_cli(root, capsys, *window, "--snapshot", str(snap))[0] == 0
    names = sorted(p.name for p in snap.iterdir())
    assert names == [
        f"flow-{PROJECT.replace('/', '-')}.html",
        f"flow-{PROJECT.replace('/', '-')}.json",
    ]
    after = _tree(tmp_path)
    assert {k for k in after if k not in before} == {f"snap/{n}" for n in names}
    doc = json.loads((snap / names[1]).read_text())
    assert doc["page"] == str(snap / names[0])
    # the pane's path: the snapshot dir under HOME, named by the project
    out = run_cli(root, capsys, *window, "--snapshot-path")[1]
    assert out.strip() == str(
        Path(os.environ["HOME"]) / f".claude/we-state/flow/flow-{PROJECT.replace('/', '-')}.json"
    )
