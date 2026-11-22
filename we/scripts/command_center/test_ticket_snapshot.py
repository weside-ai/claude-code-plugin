"""ticket_snapshot.py: the one atomic write, its fields, no other write path, stale and missing."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import ticket_snapshot as ts  # noqa: E402
from test_open_ends import CREW, UNTIL, at, build, jsonl, make_board  # noqa: E402

SCRIPT = HERE / "ticket_snapshot.py"
MINIMAL = {
    "version": 2,
    "roles": {"coordinator": "coord"},
    "members": {"coord": {"name": "Coord"}},
}
SEARCH = {
    "issues": [
        {
            "key": "ABC-15",
            "fields": {
                "status": {"name": "In Progress"},
                "summary": "x",
                "parent": {"key": "ABC-1"},
                "components": [{"name": "Platform"}],
                "labels": ["backend", "owner-ada"],
                "priority": {"name": "High"},
                "updated": "2026-11-21T10:00:00.000+0100",  # Jira's offset form
                "issuetype": {"name": "Story"},
            },
        },
        {"key": "ABC-16", "fields": {"status": {"name": "Selected for Development"}}},
        {
            "key": "ABC-1",
            "fields": {"status": {"name": "In Progress"}, "issuetype": {"name": "Epic"}},
        },
    ]
}


def run_write(board: Path, stdin: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "write", "--board", str(board)],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def test_write_is_atomic_with_its_fields(tmp_path, monkeypatch):
    board = tmp_path / "board.json"
    out = run_write(board, json.dumps(SEARCH))
    assert out.returncode == 0, out.stderr
    target = tmp_path / "board-tickets.json"
    assert out.stdout.strip() == str(target)
    doc = json.loads(target.read_text())
    assert list(doc) == ["schema_version", "@taken", "stories", "epics"]  # the field snapshot
    assert doc["schema_version"] == 2
    assert doc["stories"] == {
        "ABC-15": {
            "status": "In Progress",
            "summary": "x",
            "epic": "ABC-1",
            "components": ["Platform"],
            "owners": ["owner-ada"],
            "priority": "High",
            "updated": "2026-11-21T09:00:00Z",
        },
        "ABC-16": {"status": "Selected for Development"},
    }
    assert doc["epics"] == {"ABC-1": {"status": "In Progress"}}  # an epic is no story
    # the readers: records for the new fields, key → status of the stories for the old ones
    taken = ts.fi.parse_ts(doc["@taken"])
    stories, epics, _line, fresh = ts.read_records(target, taken, 45)
    assert (stories, epics, fresh) == (doc["stories"], doc["epics"], True)
    assert ts.read(target, taken, 45)[0] == {
        "ABC-15": "In Progress",
        "ABC-16": "Selected for Development",
    }
    assert [p.name for p in tmp_path.iterdir()] == ["board-tickets.json"]  # no temp left
    # the write goes through os.replace from a temp file in the same folder
    seen = []
    real = os.replace
    monkeypatch.setattr(
        ts.os, "replace", lambda a, b: seen.append((Path(a).parent, b)) or real(a, b)
    )
    ts.write(board, {"ABC-1": {"status": "Done"}}, UNTIL)
    assert seen == [(tmp_path, target)]
    # a failing replace leaves the old file whole and no temp behind
    monkeypatch.setattr(ts.os, "replace", lambda *_a: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        ts.write(board, {"ABC-2": {"status": "Done"}}, UNTIL)
    assert json.loads(target.read_text())["stories"]["ABC-1"] == {"status": "Done"}
    assert [p.name for p in tmp_path.iterdir()] == ["board-tickets.json"]


@pytest.mark.parametrize("stdin", ["[1]", '{"ABC-1": 3}', '"text"', "not json"])
def test_a_strange_answer_writes_nothing(tmp_path, stdin):
    out = run_write(tmp_path / "board.json", stdin)
    assert list(tmp_path.iterdir()) == []
    assert out.returncode == 2 and "refused, nothing written" in out.stderr, out.stderr


def test_no_other_write_path():
    """One write in the module (`write`: mkstemp, fdopen, os.replace); no ticket system call."""
    tree = ast.parse(SCRIPT.read_text())
    writers = {
        "write_text",
        "write_bytes",
        "open",
        "replace",
        "rename",
        "mkstemp",
        "fdopen",
        "unlink",
    }
    found = {}
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for call in [c for c in ast.walk(fn) if isinstance(c, ast.Call)]:
            name = getattr(call.func, "attr", getattr(call.func, "id", None))
            if name in writers:
                found.setdefault(fn.name, set()).add(name)
    assert found == {"write": {"mkstemp", "fdopen", "replace", "unlink"}}
    text = SCRIPT.read_text()
    for word in ("subprocess", "urllib", "http", "requests", "socket"):
        assert f"import {word}" not in text


def test_stale_and_missing(tmp_path):
    board = make_board(tmp_path)
    jsonl(tmp_path / "board-transitions.jsonl", [])
    target = ts.path_for(board)
    assert "tickets: not read (no snapshot)" in build(board)["gaps"]
    ts.write(board, {"ABC-15": {"status": "In Progress"}}, UNTIL - timedelta(minutes=44))
    fresh = build(board)
    assert "ABC-15" in {r["item"] for r in fresh["rows"]}
    assert not [g for g in fresh["gaps"] if g.startswith("tickets")]
    ts.write(board, {"ABC-15": {"status": "In Progress"}}, UNTIL - timedelta(minutes=46))
    stale = build(board)
    assert f"tickets: stale since {at(46)}" in stale["gaps"]
    assert "ABC-15" not in {r["item"] for r in stale["rows"]}
    assert CREW["flow"]["tickets_stale_min"] == 45
    doc = json.loads(target.read_text())
    target.write_text(json.dumps({k: v for k, v in doc.items() if k != "@taken"}))
    assert "tickets: stale since unknown (no @taken)" in build(board)["gaps"]  # never current
    target.write_text(json.dumps({"schema_version": 1, "@taken": at(1), "ABC-15": "In Progress"}))
    assert "tickets: not read (schema_version 1)" in build(board)["gaps"]


@pytest.mark.parametrize(
    ("flow", "ok"), [({"tickets_stale_min": 60}, True), ({"tickets_stale": 60}, False)]
)
def test_tickets_stale_min_key_strict(tmp_path, flow, ok):
    (tmp_path / ".weside").mkdir()
    (tmp_path / ".weside" / "crew.json").write_text(json.dumps({**MINIMAL, "flow": flow}))
    out = subprocess.run(
        [
            sys.executable,
            str(HERE.parent / "crew.py"),
            "validate",
            "--strict",
            "--from",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (out.returncode == 0) is ok, out.stderr
