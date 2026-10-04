import json
import subprocess
import sys
from pathlib import Path

from subagent_timing import record

HOOK = Path(__file__).with_name("subagent_timing.py")


def test_appends_one_line_per_event(tmp_path):
    base = {"session_id": "s1", "cwd": "/w", "agent_id": "a1", "agent_type": "we:dev-medium"}
    record({**base, "hook_event_name": "SubagentStart"}, tmp_path)
    out = record(
        {**base, "hook_event_name": "SubagentStop", "last_assistant_message": "x"}, tmp_path
    )
    lines = [json.loads(x) for x in out.read_text().splitlines()]
    assert out == tmp_path / ".claude" / "we-timing" / "s1.jsonl"
    assert [x["event"] for x in lines] == ["SubagentStart", "SubagentStop"]
    assert set(lines[1]) == {"ts", "event", "agent_id", "agent_type", "cwd"}
    assert lines[0]["agent_type"] == "we:dev-medium"


def test_session_id_cannot_escape_the_directory(tmp_path):
    out = record({"session_id": "../../etc/x", "hook_event_name": "SubagentStart"}, tmp_path)
    assert out.parent == tmp_path / ".claude" / "we-timing"


def test_bad_input_is_silent_and_exits_zero(tmp_path):
    res = subprocess.run(
        [sys.executable, str(HOOK)],
        input="not json",
        capture_output=True,
        text=True,
        env={"HOME": str(tmp_path)},
        check=False,
    )
    assert (res.returncode, res.stdout, res.stderr) == (0, "", "")
    assert not (tmp_path / ".claude").exists()


def test_instructions_loaded_records_why_a_file_loaded(tmp_path):
    out = record(
        {
            "session_id": "s1",
            "hook_event_name": "InstructionsLoaded",
            "file_path": "/w/.claude/rules/api.md",
            "load_reason": "path_glob_match",
            "memory_type": "Project",
            "globs": ["src/api/**"],
            "trigger_file_path": "/w/src/api/x.py",
        },
        tmp_path,
    )
    line = json.loads(out.read_text())
    assert line["event"] == "InstructionsLoaded"
    assert line["file_path"] == "/w/.claude/rules/api.md"
    assert line["load_reason"] == "path_glob_match"
    assert line["globs"] == ["src/api/**"]
    assert line["trigger_file_path"] == "/w/src/api/x.py"
    assert line["parent_file_path"] is None


def test_skill_runs_record_the_name_never_the_arguments(tmp_path):
    record(
        {
            "session_id": "s1",
            "hook_event_name": "PreToolUse",
            "tool_name": "Skill",
            "tool_input": {"skill": "we:retro", "args": "private text"},
        },
        tmp_path,
    )
    out = record(
        {
            "session_id": "s1",
            "hook_event_name": "UserPromptExpansion",
            "command_name": "we:orchestrate",
            "command_source": "plugin",
            "command_args": "private text",
            "prompt": "/we:orchestrate private text",
        },
        tmp_path,
    )
    text = out.read_text()
    tool, typed = (json.loads(x) for x in text.splitlines())
    assert (tool["event"], tool["skill"]) == ("PreToolUse", "we:retro")
    assert (typed["command_name"], typed["command_source"]) == ("we:orchestrate", "plugin")
    assert "private text" not in text


def test_unknown_event_writes_nothing(tmp_path):
    assert record({"session_id": "s1", "hook_event_name": "Stop"}, tmp_path) is None
    assert not (tmp_path / ".claude").exists()


def test_skill_hook_prints_no_decision_and_exits_zero(tmp_path):
    payload = {"session_id": "s1", "hook_event_name": "PreToolUse", "tool_input": {"skill": "x"}}
    res = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"HOME": str(tmp_path)},
        check=False,
    )
    assert (res.returncode, res.stdout, res.stderr) == (0, "", "")
    assert (tmp_path / ".claude" / "we-timing" / "s1.jsonl").exists()
