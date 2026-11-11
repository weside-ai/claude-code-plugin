"""probe.py reads two environment keys of a session and prints neither value as read."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe


def test_env_keys_keeps_only_we_role_and_config_dir(tmp_path, monkeypatch):
    environ = tmp_path / "environ"
    environ.write_bytes(
        b"API_TOKEN=secret\0WE_ROLE=master\0CLAUDE_CONFIG_DIR=/x/y\0WE_ROLE_X=no\0"
    )
    real_open = open
    monkeypatch.setattr(
        "builtins.open",
        lambda path, *a, **k: real_open(
            environ if str(path) == "/proc/7/environ" else path, *a, **k
        ),
    )
    assert probe.env_keys(7) == {"WE_ROLE": "master", "CLAUDE_CONFIG_DIR": "/x/y"}


def test_env_keys_of_an_unreadable_process_is_none():
    assert probe.env_keys(-1) is None


def test_mode_is_read_under_the_session_config_dir(tmp_path):
    folder = tmp_path / "projects" / "-work-repo"
    folder.mkdir(parents=True)
    (folder / "s1.jsonl").write_text('{"permissionMode":"default"}\n{"permissionMode":"auto"}\n')
    assert probe.mode_of(str(tmp_path), "/work/repo", "s1") == "auto"
    assert probe.mode_of(str(tmp_path), "/work/repo", "missing") is None


def test_role_and_profile_print_classes_not_values():
    assert probe.role_class("master") == "master"
    assert probe.role_class("anything") == "other"
    assert probe.role_class(None) is None
    assert probe.profile_of(probe.SWAP_SESSIONS + "3-me_example.com") == "3-me_example.com"
    assert probe.profile_of("/home/me/.claude-secret-place") == "other"
    assert probe.profile_of(None) is None


def _agents(monkeypatch, rows):
    class Run:
        returncode = 0
        stdout = json.dumps(rows)

    real = subprocess.run

    def fake(argv, *a, **k):
        return Run() if list(argv[:2]) == ["claude", "agents"] else real(argv, *a, **k)

    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.setattr(probe, "env_keys", lambda _pid: {})


def _crew(root, name):
    (root / name / ".git").mkdir(parents=True)
    (root / name / ".weside").mkdir()
    crew_file = root / name / ".weside" / "crew.json"
    crew_file.write_text('{"version": 2, "roles": {}, "members": {}}')
    return root / name, crew_file


def test_crew_keeps_its_own_sessions_and_marks_an_unreadable_cwd(tmp_path, monkeypatch, capsys):
    """two crews, AC4: two crews' sessions on one host; /board of crew a lists crew a only."""
    a, crew_a = _crew(tmp_path, "a")
    b, _ = _crew(tmp_path, "b")
    (a / "sub").mkdir()
    plain = tmp_path / "plain"
    (plain / ".git").mkdir(parents=True)
    _agents(
        monkeypatch,
        [
            {"name": "a-coord", "cwd": str(a)},
            {"name": "a-worker", "cwd": str(a / "sub")},
            {"name": "b-coord", "cwd": str(b)},
            {"name": "loose", "cwd": str(plain)},
            {"name": "gone", "cwd": str(tmp_path / "removed-worktree")},
            {"name": "nocwd"},
        ],
    )
    assert probe.main(["--crew", str(crew_a)]) == 0
    rows = json.loads(capsys.readouterr().out)["sessions"]
    assert [r["name"] for r in rows] == ["a-coord", "a-worker", "gone", "nocwd"]
    assert [r.get("crew") for r in rows] == [None, None, "unknown", "unknown"]


def test_without_crew_every_session_is_listed(tmp_path, monkeypatch, capsys):
    a, _ = _crew(tmp_path, "a")
    b, _ = _crew(tmp_path, "b")
    _agents(monkeypatch, [{"name": "x", "cwd": str(a)}, {"name": "y", "cwd": str(b)}])
    assert probe.main([]) == 0
    assert [r["name"] for r in json.loads(capsys.readouterr().out)["sessions"]] == ["x", "y"]


def _git(*args):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", *args], check=True, capture_output=True, env=env)


def test_a_worker_in_a_worktree_of_the_crew_repo_stays(tmp_path, monkeypatch, capsys):
    """Each worktree carries its own copy of the tracked crew file: same crew by crew id."""
    repo = tmp_path / "repo"
    (repo / ".weside").mkdir(parents=True)
    _git("init", "-q", str(repo))
    (repo / ".weside" / "crew.json").write_text('{"version": 2, "roles": {}, "members": {}}')
    _git("-C", str(repo), "add", ".")
    _git("-C", str(repo), "commit", "-q", "-m", "crew")
    tree = tmp_path / "repo-KEY-1"
    _git("-C", str(repo), "worktree", "add", "-q", str(tree))
    other, _ = _crew(tmp_path, "other")
    _agents(
        monkeypatch,
        [
            {"name": "master", "cwd": str(repo)},
            {"name": "worker", "cwd": str(tree)},
            {"name": "foreign", "cwd": str(other)},
        ],
    )
    assert probe.main(["--crew", str(repo / ".weside" / "crew.json")]) == 0
    rows = json.loads(capsys.readouterr().out)["sessions"]
    assert [r["name"] for r in rows] == ["master", "worker"]


def test_an_answer_that_is_no_list_is_an_error_not_an_empty_host(monkeypatch, capsys):
    """Red arm: `{"agents": [...]}` from a changed CLI read as no session at all."""
    _agents(monkeypatch, {"agents": [{"name": "x"}]})
    assert probe.main([]) == 0
    assert json.loads(capsys.readouterr().out) == {"error": "claude agents --json printed no list"}
