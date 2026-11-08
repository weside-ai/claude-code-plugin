"""probe.py reads two environment keys of a session and prints neither value as read."""

from __future__ import annotations

import json
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

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: Run())
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
