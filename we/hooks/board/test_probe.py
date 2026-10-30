"""probe.py reads two environment keys of a session and prints neither value as read."""

from __future__ import annotations

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
