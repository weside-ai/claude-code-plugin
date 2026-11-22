"""open_ends.py over fixture boards and a fake GitHub runner (`body -> response`); no network."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import crew as crew_mod  # noqa: E402
import gh_source  # noqa: E402
import open_ends  # noqa: E402

UTC = timezone.utc
UNTIL = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
HEAD = "a" * 40


def at(minutes_before: float) -> str:
    return (UNTIL - timedelta(minutes=minutes_before)).strftime("%Y-%m-%dT%H:%M:%SZ")


CREW = {
    **crew_mod.DEFAULTS,
    "roles": {"coordinator": "coord"},
    "members": {"coord": {"name": "Coord"}},
}


def jsonl(path: Path, rows: list) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def make_board(tmp: Path, project="acme", name="board.json", **extra) -> Path:
    """A stamped board with the sessions of the ACs."""
    board = tmp / name
    sessions = [
        {
            "name": "alpha-7",
            "role": "master",
            "keys": ["ABC-1"],
            "waiting_on": "coordinator",
            "since": at(170),
        },
        {"name": "ABC-12-fix", "role": "worker", "parent": "alpha-7", "keys": ["ABC-12"]},
        {"name": "beta-3", "role": "master", "waiting_on": "release", "since": at(60)},
        {"name": "Coord", "role": "coordinator"},
    ]
    doc = {"sessions": sessions, "owner_queue": [], **extra}
    board.write_text(json.dumps(doc), encoding="utf-8")
    crew_mod.stamp_path(board).write_text(project + "\n")
    return board


def question(qid, minutes, **extra):
    return {
        "id": qid,
        "ts": at(minutes),
        "since": at(minutes)[:10],
        "session": "ABC-12-fix",
        "key": "ABC-12",
        "key_title": f"title {qid}",
        **extra,
    }


def snapshot(taken, statuses):
    """A ticket snapshot as `ticket_snapshot.write` lays it out."""
    stories = {k: {"status": v} for k, v in statuses.items()}
    return {"schema_version": 2, "@taken": taken, "stories": stories, "epics": {}}


def build(board, **kw):
    return open_ends.build(board, None, CREW, UNTIL, **kw)


def by_section(doc):
    """The sections the aggregate shows (zentrale.py): owner, red, waiting."""
    owner = [r["item"] for r in doc["rows"] if r["holder"] == "owner"]
    red = [r["item"] for r in doc["rows"] if r["red"]]
    waiting = [r["item"] for r in doc["rows"] if r["holder"] != "owner" and not r["red"]]
    return owner, red, waiting


# --- a fake GitHub ---------------------------------------------------------------------------


def ctx(name, status="COMPLETED", conclusion="SUCCESS", started=None, created=None, done=None):
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "isRequired": False,
        "startedAt": started,
        "completedAt": done,
        "checkSuite": {"createdAt": created or at(120)},
    }


def pr(number, contexts, *, draft=False, armed=False, body="", title=None):
    return {
        "id": f"PR_{number}",
        "number": number,
        "title": title or f"feat: thing ABC-{number}",
        "body": body,
        "state": "OPEN",
        "isDraft": draft,
        "createdAt": at(600),
        "headRefName": f"feat/ABC-{number}",
        "headRefOid": HEAD,
        "baseRefName": "main",
        "mergeStateStatus": "BLOCKED",
        "reviewDecision": None,
        "labels": {"nodes": []},
        "autoMergeRequest": {"enabledAt": at(100)} if armed else None,
        "commits": {
            "nodes": [
                {
                    "commit": {
                        "oid": HEAD,
                        "committedDate": at(130),
                        "statusCheckRollup": {"contexts": {"nodes": contexts}},
                    }
                }
            ]
        },
    }


def fake_runner(prs: list, default_state="SUCCESS", default_contexts=()):
    calls = []

    def run(body):
        calls.append(body)
        q = body["query"]
        if "pullRequests(" in q:
            return {
                "data": {
                    "repository": {
                        "defaultBranchRef": {
                            "name": "main",
                            "target": {
                                "oid": "d" * 40,
                                "statusCheckRollup": {
                                    "state": default_state,
                                    "contexts": {"nodes": list(default_contexts)},
                                },
                            },
                        },
                        "pullRequests": {"nodes": [{"number": p["number"]} for p in prs]},
                    }
                }
            }
        return {"data": {"repository": {f"pr{p['number']}": p for p in prs}}}

    run.calls = calls  # type: ignore[attr-defined]
    run.fetched = []  # type: ignore[attr-defined]
    return run


def repo_doc(prs, required=("test",)):
    return gh_source.read_repo(fake_runner(prs), "acme/app", lambda _r, _b: list(required))


AC2_PRS = [
    pr(21, [ctx("test")], draft=True),
    pr(22, [ctx("test", conclusion="FAILURE", done=at(30))]),
    pr(25, [ctx("test", done=at(20))]),
    pr(27, [ctx("test", status="IN_PROGRESS", conclusion=None, started=at(59))], armed=True),
    pr(28, [ctx("test", status="QUEUED", conclusion=None, created=at(61))], armed=True),
    pr(29, [ctx("test", done=at(10))], armed=True),
]


# --- AC 1 ------------------------------------------------------------------------------------


def test_foxy_section(tmp_path):
    board = make_board(
        tmp_path,
        owner_queue=[
            question("Q4", 50),
            question("Q5", 40),
            question("Q6", 30, obsolete="prompt resolved"),
            question(
                "Q8",
                20,
                cause="merge-go",
                one_way="secrets",
                pr_url="https://github.com/acme/app/pull/23",
            ),
        ],
    )
    jsonl(tmp_path / "board-answers.jsonl", [{"id": "Q5", "answer": "accept", "ts": at(5)}])
    prs = [
        pr(23, [ctx("test", done=at(15))]),  # green, not armed, but the owner holds it (Q8)
        pr(24, [ctx("test", done=at(15))], body="## What\n\nuser merge: secrets\n"),
    ]
    doc = build(board, repos=[repo_doc(prs)])
    owner, _red, _waiting = by_section(doc)
    assert owner == ["acme/app#24", "Q4", "Q8"]  # oldest first: #24 opened 600 min ago
    q4 = next(r for r in doc["rows"] if r["item"] == "Q4")
    assert (q4["holder"], q4["for"], q4["master"], q4["since"]) == (
        "owner",
        "ABC-12-fix",
        "alpha-7",
        at(50),
    )
    assert q4["age_s"] == 50 * 60
    p24 = next(r for r in doc["rows"] if r["item"] == "acme/app#24")
    assert p24["classes"] == ["user merge"]
    assert "obsolete questions: 1" in doc["header"]
    assert not [r for r in doc["rows"] if r["item"] in ("Q5", "Q6", "acme/app#23")]
    # a question dated by day only: the day starts at midnight in the crew's time.zone
    day_only = make_board(tmp_path, owner_queue=[question("Q7", 0, ts=None, since="2026-04-01")])
    berlin = open_ends.build(day_only, None, CREW, UNTIL, zone=ZoneInfo("Europe/Berlin"))
    q7 = next(r for r in berlin["rows"] if r["item"] == "Q7")
    assert (q7["since"], q7["since_note"]) == ("2026-03-31T22:00:00Z", "day")


# --- AC 2 ------------------------------------------------------------------------------------


def test_pr_classes(tmp_path):
    doc = build(make_board(tmp_path), repos=[repo_doc(AC2_PRS)])
    prs = {r["item"]: r for r in doc["rows"] if r["kind"] == "pr"}
    _owner, red, waiting = by_section({"rows": list(prs.values())})
    assert red == ["acme/app#22"]
    assert sorted(waiting) == ["acme/app#21", "acme/app#25", "acme/app#28"]
    assert prs["acme/app#21"]["classes"] == ["draft"]
    assert prs["acme/app#25"]["classes"] == ["green, not armed"]
    assert prs["acme/app#28"]["classes"] == ["waiting on CI"]
    assert prs["acme/app#28"]["since"] == at(61)
    assert "acme/app#27" not in prs and "acme/app#29" not in prs
    assert "open PRs acme/app: 6, waiting: 4" in doc["header"]


def test_absent_required_check_is_waiting_not_green(tmp_path):
    """A required name with no check on the head is pending (absent is not green): after the
    limit the PR waits on CI, never `green, not armed`."""
    lone = [pr(30, [ctx("lint", done=at(100))])]
    doc = build(make_board(tmp_path), repos=[repo_doc(lone, required=("test",))])
    [row] = [r for r in doc["rows"] if r["kind"] == "pr"]
    assert row["classes"] == ["waiting on CI"] and row["since"] == at(130)


# --- AC 5 ------------------------------------------------------------------------------------


def test_waits_stories_tickets(tmp_path):
    board = make_board(tmp_path)
    jsonl(
        tmp_path / "board-escalations.jsonl",
        [
            {
                "id": "E2",
                "event": "open",
                "key": "ABC-1",
                "question": "which seam",
                "stage": "advice",
                "waiting_on": "coordinator",
                "since": at(90),
            },
            {"id": "E3", "event": "open", "key": "ABC-1", "stage": "advice", "since": at(80)},
            {"id": "E3", "event": "settle", "outcome": "a", "by": "x"},
        ],
    )
    jsonl(
        tmp_path / "board-transitions.jsonl",
        [
            {"key": "ABC-12", "from": "selected", "to": "in_progress", "ts": at(200)},
            {"key": "ABC-14", "from": "selected", "to": "in_progress", "ts": at(190)},
            {"key": "ABC-13", "from": "in_progress", "to": "in_review", "ts": at(180)},
        ],
    )
    snap = tmp_path / "board-tickets.json"
    snap.write_text(
        json.dumps(snapshot(at(10), {"ABC-12": "In Progress", "ABC-15": "In Progress"}))
    )
    doc = build(board)
    rows = {r["item"]: r for r in doc["rows"]}
    assert rows["alpha-7"]["holder"] == "Coord" and rows["alpha-7"]["since"] == at(170)
    assert rows["beta-3"]["holder"] == "release (no session)"
    assert rows["E2"]["holder"] == "Coord" and "E3" not in rows
    assert rows["ABC-12"]["holder"] == "ABC-12-fix" and rows["ABC-12"]["master"] == "alpha-7"
    assert rows["ABC-14"]["holder"] == "no holder"
    assert rows["ABC-15"]["source"] == "tickets" and rows["ABC-15"]["since"] == "unknown"
    assert "ABC-13" not in rows
    assert doc["rows"][0]["item"] == "ABC-15"  # unknown since first
    assert not [g for g in doc["gaps"] if g.startswith("tickets")]  # control: 10 min, not stale
    snap.write_text(json.dumps(snapshot(at(46), {"ABC-15": "In Progress"})))
    stale = build(board)
    assert f"tickets: stale since {at(46)}" in stale["gaps"]
    assert "ABC-15" not in {r["item"] for r in stale["rows"]}  # no story of a stale snapshot
    snap.unlink()
    doc = build(board)
    assert "tickets: not read (no snapshot)" in doc["gaps"]
    assert "ABC-15" not in {r["item"] for r in doc["rows"]}


# --- AC 11 -----------------------------------------------------------------------------------


def test_one_project(tmp_path):
    acme = make_board(
        tmp_path, owner_queue=[question("Q4", 50), question("Q9", 40, session="z-1", key="ZET-9")]
    )
    zeta = tmp_path / "zeta"
    zeta.mkdir()
    make_board(zeta, project="zeta", owner_queue=[question("Q1", 10, session="z-1")])
    doc = build(acme)
    assert doc["project"] == "acme" and "Project: acme" in doc["header"]
    items = {r["item"] for r in doc["rows"]}
    assert "Q4" in items and "Q9" not in items and "Q1" not in items
    assert doc["attribution"] == "not attributed to acme: 1 question (Q9)"


def test_unread_board_and_repo_are_gaps(tmp_path):
    doc = build(tmp_path / "missing.json", repos=[{"repo": "acme/app", "gap": "gh: down"}])
    assert doc["gaps"] == ["board: not found", "PRs acme/app: not read (gh: down)"]
    assert doc["rows"] == []


def test_more_open_prs_than_read_is_a_gap(tmp_path):
    doc = repo_doc([pr(50, [ctx("test", done=at(5))], armed=True)])
    doc["more"] = True
    out = build(make_board(tmp_path), repos=[doc])
    assert "PRs acme/app: only the oldest 1 open PRs read" in out["gaps"]
