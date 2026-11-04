"""cold_reader.py: the agent file it reads and the answer it takes (the run itself: test_board.TestAsk)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cold_reader  # noqa: E402


def test_the_agent_file_pins_a_small_model_and_no_tools():
    meta, body = cold_reader.agent_parts()
    assert (meta["model"], meta["effort"], meta["tools"]) == ("haiku", "low", "[]")
    assert not body.startswith("---")
    for rule in ("One decision per question", "recommendation is stated", "At most 3 options"):
        assert rule in body


def test_the_argv_names_every_isolation_flag(tmp_path):
    argv = cold_reader.argv({"model": "haiku", "effort": "low"}, tmp_path)
    assert argv[:2] == ["claude", "-p"]
    for flag in (
        "--no-session-persistence",
        "--strict-mcp-config",
        "--disable-slash-commands",
    ):
        assert flag in argv
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert argv[argv.index("--mcp-config") + 1] == str(tmp_path / "mcp.json")


def test_settings_turn_hooks_off_and_enable_no_plugin():
    assert cold_reader.SETTINGS == {"disableAllHooks": True, "enabledPlugins": {}}


def test_a_question_missing_a_key_is_a_caller_bug():
    with pytest.raises(ValueError, match="question lacks recommendation_label"):
        cold_reader.read(dict.fromkeys(cold_reader.QUESTION_KEYS[:-1], "x"))


def test_the_last_json_object_is_the_answer(tmp_path, monkeypatch):
    fake = tmp_path / "claude"
    answer = {"decides": "a", "on_yes": "b", "form": []}
    fake.write_text(
        "#!/bin/sh\n/bin/cat >/dev/null\n"
        f"echo 'draft {{\"decides\": \"\"}}'\necho '{json.dumps(answer)}'\n"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    got = cold_reader.read(dict.fromkeys(cold_reader.QUESTION_KEYS, "x"))
    assert got == answer
