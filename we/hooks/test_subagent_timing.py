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
