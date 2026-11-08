"""state_move.py (two crews, AC8): a second crew's board family moves into its own state_dir."""

from __future__ import annotations

import fcntl
import json
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import state_move  # noqa: E402

FAMILY = {
    "acme-board.json": '{"news": []}\n',
    "acme-board.json.lock": "",
    "acme-board-answers.jsonl": '{"id": "Q1"}\n',
    "acme-board-questions.jsonl": '{"id": "Q1"}\n',
    "acme-board-freeze.json": '{"reason": "x"}\n',
    "acme-board-crew.id": "acme/second\n",
}
TARGETS = {
    "acme-board.json": "board.json",
    "acme-board.json.lock": "board.json.lock",
    "acme-board-answers.jsonl": "board-answers.jsonl",
    "acme-board-questions.jsonl": "board-questions.jsonl",
    "acme-board-freeze.json": "freeze.json",
    "acme-board-crew.id": "crew.id",
}


@pytest.fixture
def world(tmp_path, monkeypatch):
    shared = tmp_path / "shared"
    shared.mkdir()
    for name, body in FAMILY.items():
        (shared / name).write_text(body)
    (shared / "board.json").write_text('{"first": "crew"}\n')  # the other crew's board stays
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".weside").mkdir()
    crew = {
        "version": 2,
        "roles": {"coordinator": "rex"},
        "members": {"rex": {"name": "Rex"}},
        "board": {"file": str(shared / "acme-board.json")},
        "state_dir": str(tmp_path / "own"),
    }
    (repo / ".weside" / "crew.json").write_text(json.dumps(crew))
    agents = tmp_path / "agents.json"
    agents.write_text("[]")
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "claude").write_text(
        '#!/bin/sh\n[ -n "$FAKE_AGENTS_EXIT" ] && exit 3\ncat "$FAKE_AGENTS"\n'
    )
    (fake / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_AGENTS", str(agents))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "me")
    monkeypatch.delenv("WE_STATE_DIR", raising=False)
    monkeypatch.chdir(repo)
    return {"shared": shared, "own": tmp_path / "own", "repo": repo, "agents": agents}


def test_a_dry_run_lists_every_file_and_its_target_and_moves_nothing(world, capsys):
    before = sorted(p.name for p in world["shared"].iterdir())
    assert state_move.main([]) == 0
    out = capsys.readouterr().out.splitlines()
    pairs = dict(line.split(" -> ") for line in out if " -> " in line)
    assert {Path(s).name: Path(t).name for s, t in pairs.items()} == TARGETS
    assert all(Path(t).parent == world["own"] for t in pairs.values())
    assert sorted(p.name for p in world["shared"].iterdir()) == before
    assert not world["own"].exists()


def test_apply_copies_verifies_and_keeps_each_source_renamed(world, capsys):
    assert state_move.main(["--apply"], today="2026-11-08") == 0
    for name, body in FAMILY.items():
        assert (world["own"] / TARGETS[name]).read_text() == body
        assert not (world["shared"] / name).exists()
        assert (world["shared"] / f"{name}.migrated-2026-11-08").read_text() == body
    assert (world["shared"] / "board.json").read_text() == '{"first": "crew"}\n'
    assert "drop board.file" in capsys.readouterr().out


def test_an_existing_target_is_refused(world, capsys):
    world["own"].mkdir()
    (world["own"] / "board-answers.jsonl").write_text("mine\n")
    assert state_move.main(["--apply"]) == 2
    assert "target exists" in capsys.readouterr().err
    assert (world["shared"] / "acme-board.json").exists()


def test_a_crew_without_state_dir_is_refused(world, capsys):
    path = world["repo"] / ".weside" / "crew.json"
    data = json.loads(path.read_text())
    del data["state_dir"]
    path.write_text(json.dumps(data))
    assert state_move.main([]) == 2
    assert "sets no state_dir" in capsys.readouterr().err


def test_a_live_session_of_the_crew_is_refused_but_the_caller_is_not(world, capsys):
    world["agents"].write_text(
        json.dumps(
            [
                {"name": "self", "sessionId": "me", "cwd": str(world["repo"])},
                {"name": "elsewhere", "sessionId": "x", "cwd": str(world["shared"])},
            ]
        )
    )
    assert state_move.main(["--apply"], today="2026-11-08") == 0
    capsys.readouterr()


def test_a_live_session_of_the_crew_refuses_the_move(world, capsys):
    world["agents"].write_text(
        json.dumps([{"name": "Rex", "sessionId": "other", "cwd": str(world["repo"])}])
    )
    assert state_move.main(["--apply"]) == 2
    assert "live sessions of this crew run: Rex" in capsys.readouterr().err
    assert (world["shared"] / "acme-board.json").exists()


def test_an_unreadable_session_list_refuses(world, monkeypatch, capsys):
    monkeypatch.setenv("FAKE_AGENTS_EXIT", "1")
    assert state_move.main(["--apply"]) == 2
    assert "cannot be read" in capsys.readouterr().err


def test_a_held_lock_refuses(world, capsys):
    lock = world["shared"] / "acme-board.json.lock"
    fd = os.open(str(lock), os.O_WRONLY)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        assert state_move.main(["--apply"]) == 2
    finally:
        os.close(fd)
    assert "lock" in capsys.readouterr().err
    assert (world["shared"] / "acme-board.json").exists()
    assert not (world["own"] / "board.json").exists()
