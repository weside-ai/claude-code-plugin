"""Two crews on one HOME (two crews, AC2, AC10, AC11): the real scripts by subprocess, no mocks.

One temp HOME holds two git repos. Crew A sets no `state_dir` (the default folder, as the first
crew of a host does); crew B sets `state_dir` to a folder of its own. Every step of one crew
(`board.py set`, `board.py ask`, a pane answer through `hooks/board/answer.py`, `board.py freeze`,
the SessionStart hook `process_on_start.py`) leaves the other crew's files byte-identical; a freeze
in A stops a merge in A's repo and not in B's; A resolves exactly the paths of 8.10.0 (AC10).
AC11: a session of the other crew, a crewless session, or a pin outside the crew cannot write A's
board.

Red arm: `WE_TWO_CREWS_PLUGIN=<an origin/main checkout>/we python3 -m pytest -q
scripts/test_two_crews.py` runs the same steps against that plugin's scripts.

Run with: python3 -m pytest -q scripts/test_two_crews.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PLUGIN = Path(os.environ.get("WE_TWO_CREWS_PLUGIN") or REPO / "we").resolve()
FIXTURES = REPO / "we" / "scripts" / "fixtures"
BOARD_PY = PLUGIN / "scripts" / "board.py"
ANSWER_PY = PLUGIN / "hooks" / "board" / "answer.py"
PROCESS_HOOK = PLUGIN / "hooks" / "process_on_start.py"
GATE_DIR = PLUGIN / "hooks"

CLEAR = {"decides": "whether the page goes live tonight", "on_yes": "it ships", "form": []}
ASK = [
    "ask",
    "--session",
    "lead-1",
    "--key",
    "PROJ-1",
    "--key-title",
    "Checkout",
    "--ask",
    "Should the checkout page go live for all users tonight?",
    "--recommendation",
    "Yes, tonight; a rollback takes minutes.",
    "--cause",
    "prod",
]
FAKE_CLAUDE = """#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
if args[:2] == ["agents", "--json"]:
    sys.stdout.write(open(os.environ["FAKE_AGENTS"]).read()); sys.exit(0)
if args[:1] == ["-p"]:
    sys.stdin.read(); sys.stdout.write(open(os.environ["FAKE_ANSWER"]).read()); sys.exit(0)
sys.exit(9)
"""
FAKE_GH = "#!/bin/sh\nexit 1\n"  # no GitHub here: freeze keeps its local flag and says so


def _git(where: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(where), *args], check=True, capture_output=True)


@pytest.fixture
def world(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    repos = {}
    for name, fixture in (("a", "crew-two-a.json"), ("b", "crew-two-b.json")):
        repo = tmp_path / f"crew-{name}"
        (repo / ".weside").mkdir(parents=True)
        _git(repo, "init", "-q")
        _git(repo, "remote", "add", "origin", f"git@github.com:acme/crew-{name}.git")
        shutil.copy(FIXTURES / fixture, repo / ".weside" / "crew.json")
        repos[name] = repo
    plain = tmp_path / "plain"
    plain.mkdir()
    _git(plain, "init", "-q")
    fake = tmp_path / "bin"
    fake.mkdir()
    for tool, text in (("claude", FAKE_CLAUDE), ("gh", FAKE_GH)):
        (fake / tool).write_text(text)
        (fake / tool).chmod(0o755)
    (tmp_path / "answer.txt").write_text("Reading it cold.\n" + json.dumps(CLEAR))
    (tmp_path / "agents.json").write_text(json.dumps([{"sessionId": "sid-1", "name": "lead-1"}]))
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("WE_STATE_DIR", "WESIDE_COMPANION", "CLAUDE_PLUGIN_ROOT")
    }
    env.update(
        HOME=str(home),
        PATH=f"{fake}{os.pathsep}{env['PATH']}",
        WE_ROLE="master",
        CLAUDE_CODE_SESSION_ID="sid-1",
        FAKE_AGENTS=str(tmp_path / "agents.json"),
        FAKE_ANSWER=str(tmp_path / "answer.txt"),
    )
    root = home / ".claude" / "we-state"
    return {
        "home": home,
        "env": env,
        "a": repos["a"],
        "b": repos["b"],
        "plain": plain,
        "dir_a": root,
        "dir_b": root / "second",
    }


def board(w, repo, *argv, **env_extra):
    return subprocess.run(
        [sys.executable, str(BOARD_PY), *argv],
        cwd=repo,
        env={**w["env"], **env_extra},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def board_path(w, repo) -> Path:
    out = board(w, repo, "path")
    assert out.returncode == 0, out.stderr
    return Path(out.stdout.strip())


def snapshot(folder: Path) -> dict[str, str]:
    """sha256 of every file directly in `folder` (not below it)."""
    if not folder.is_dir():
        return {}
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.iterdir())
        if p.is_file()
    }


def steps(w, name):
    """Every writing step of crew `name`, in order."""
    repo = w[name]

    def set_line():
        out = board(w, repo, "set", "state=build", "now=phase 1")
        assert out.returncode == 0, out.stderr

    def ask():
        out = board(w, repo, *ASK)
        assert out.returncode == 0, out.stderr

    def answer():
        answers = board_path(w, repo).with_name(board_path(w, repo).stem + "-answers.jsonl")
        out = subprocess.run(
            [sys.executable, str(ANSWER_PY), str(answers), "Q1", "accept", "2026-11-08T10:00Z"],
            env=w["env"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert out.returncode == 0, out.stderr

    def freeze():
        board(w, repo, "freeze", "--reason", f"crew {name} stops")
        flag = board_path(w, repo).with_name("freeze.json")
        assert flag.is_file(), f"crew {name}: no freeze flag at {flag}"

    def unfreeze():
        board(w, repo, "unfreeze")

    def session_start():
        payload = json.dumps({"cwd": str(repo), "session_id": f"s-{name}", "source": "startup"})
        out = subprocess.run(
            [sys.executable, str(PROCESS_HOOK)],
            input=payload,
            cwd=repo,
            env=w["env"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert out.returncode == 0, out.stderr

    return [set_line, ask, answer, freeze, unfreeze, session_start]


def freeze_refusal(w, repo) -> str | None:
    code = (
        "import sys, json; sys.path.insert(0, sys.argv[1]); import automerge_gate as g; "
        "print(json.dumps(g._freeze_refusal(sys.argv[2], sys.argv[3])))"
    )
    slug = f"acme/{repo.name}"
    out = subprocess.run(
        [sys.executable, "-c", code, str(GATE_DIR), str(repo), slug],
        env=w["env"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("actor, other", [("b", "a"), ("a", "b")])
def test_one_crew_acting_leaves_the_other_byte_identical(world, actor, other):
    # Seed both crews first, so the other side has files to keep.
    for name in ("a", "b"):
        for step in steps(world, name)[:3]:
            step()
    for step in steps(world, actor):
        before = snapshot(world[f"dir_{other}"])
        step()
        after = snapshot(world[f"dir_{other}"])
        changed = sorted(n for n in set(before) | set(after) if before.get(n) != after.get(n))
        assert not changed, (
            f"crew {actor}'s {step.__name__} changed crew {other}'s files in "
            f"{world[f'dir_{other}']}: {changed}"
        )


def test_a_question_of_b_never_reaches_as_queue(world):
    assert board(world, world["a"], "set", "state=build").returncode == 0
    out = board(world, world["b"], *ASK)
    assert out.returncode == 0, out.stderr
    a_questions = world["dir_a"] / "board-questions.jsonl"
    assert not a_questions.exists(), f"crew b's question landed in {a_questions}"
    assert (world["dir_b"] / "board-questions.jsonl").is_file()


def test_a_freeze_in_a_stops_a_merge_in_a_and_not_in_b(world):
    board(world, world["a"], "freeze", "--reason", "release")
    assert freeze_refusal(world, world["a"]), "no refusal in crew a's own repo"
    assert freeze_refusal(world, world["b"]) is None
    board(world, world["a"], "unfreeze")
    board(world, world["b"], "freeze", "--reason", "release")
    assert freeze_refusal(world, world["b"])
    assert freeze_refusal(world, world["a"]) is None


def test_crew_a_without_state_dir_keeps_todays_paths(world):
    """AC10: the first crew (no `state_dir`, no `board.file`) resolves the 8.10.0 paths, so the
    readers outside the plugin (`a release`, the flow sampler, the home hooks) keep working."""
    root = world["home"] / ".claude" / "we-state"
    assert board_path(world, world["a"]) == root / "board.json"
    for step in steps(world, "a"):
        step()
    names = set(snapshot(root))
    assert {
        "board.json",
        "board-questions.jsonl",
        "board-answers.jsonl",
        "l0-served.jsonl",
    } <= names
    assert board_path(world, world["b"]) == root / "second" / "board.json"
    steps(world, "b")[-1]()  # crew b's SessionStart logs into its own folder
    assert (root / "second" / "l0-served.jsonl").is_file()


class TestCrewGuard:
    """AC11: writes on crew a's board from outside crew a are refused, and nothing changes."""

    @pytest.fixture
    def stamped(self, world):
        out = board(world, world["a"], "set", "state=build")
        assert out.returncode == 0, out.stderr
        return world

    def _refused(self, w, out):
        before = snapshot(w["dir_a"])
        assert out.returncode != 0, f"the write went through: {out.stdout}{out.stderr}"
        assert "--board" in out.stderr
        assert snapshot(w["dir_a"]) == before
        return out.stderr

    def test_a_crewless_session_without_board_cannot_prune_the_default_board(self, stamped):
        before = snapshot(stamped["dir_a"])
        out = board(stamped, stamped["plain"], "prune")
        assert snapshot(stamped["dir_a"]) == before, "a crewless prune rewrote crew a's board"
        err = self._refused(stamped, out)
        assert "no crew" in err and "acme/crew-a" in err

    def test_a_pin_of_another_crew_in_crew_as_repo_is_refused(self, stamped):
        before = snapshot(stamped["dir_a"])
        out = board(stamped, stamped["a"], "set", "state=idle", WESIDE_COMPANION="Rex")
        assert snapshot(stamped["dir_a"]) == before
        err = self._refused(stamped, out)
        assert "Rex" in err

    def test_crew_b_naming_crew_as_board_is_refused(self, stamped):
        before = snapshot(stamped["dir_a"])
        target = stamped["dir_a"] / "board.json"
        out = board(stamped, stamped["b"], "--board", str(target), "prune")
        assert snapshot(stamped["dir_a"]) == before
        err = self._refused(stamped, out)
        assert "acme/crew-b" in err and "acme/crew-a" in err

    def test_reading_stays_open(self, stamped):
        out = board(
            stamped, stamped["plain"], "--board", str(stamped["dir_a"] / "board.json"), "path"
        )
        assert out.returncode == 0
