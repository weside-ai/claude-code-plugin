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
            "command_name": "we:master",
            "command_source": "plugin",
            "command_args": "private text",
            "prompt": "/we:master private text",
        },
        tmp_path,
    )
    text = out.read_text()
    tool, typed = (json.loads(x) for x in text.splitlines())
    assert (tool["event"], tool["skill"]) == ("PreToolUse", "we:retro")
    assert (typed["command_name"], typed["command_source"]) == ("we:master", "plugin")
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


L0 = "# The crew process (L0)\n\nL0-SECRET-TEXT"
CARD = "# Role card: product\n\n## Cornerstone\nCARD-SECRET-TEXT"


def _transcript(path: Path) -> None:
    def att(a, ts="2026-11-25T09:00:00.000Z"):
        return {"type": "attachment", "timestamp": ts, "attachment": a}

    stdout = json.dumps(
        {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": L0}}
    )
    entries = [
        att(
            {
                "type": "hook_success",
                "hookEvent": "SessionStart",
                "hookName": "SessionStart:startup",
                "command": "command hook 3",
                "stdout": stdout,
            }
        ),
        att(
            {
                "type": "hook_additional_context",
                "hookEvent": "SessionStart",
                "content": [L0, CARD, "other hook"],
            }
        ),
        att(
            {
                "type": "instructions",
                "files": [
                    {"path": "/w/AGENTS.md", "type": "Project", "content": "A" * 11},
                    {"path": "/w/.claude/rules/r.md", "type": "Project", "content": "R" * 5},
                    {
                        "path": "/cfg/projects/w/memory/MEMORY.md",
                        "type": "AutoMem",
                        "content": "M" * 7,
                    },
                ],
            }
        ),
        {"type": "user", "message": {"content": "hi"}},
    ]
    path.write_text("".join(json.dumps(e) + "\n" for e in entries) + "not json\n")


def test_stop_records_the_loads_claude_code_fires_no_event_for(tmp_path):
    transcript = tmp_path / "t.jsonl"
    _transcript(transcript)
    payload = {"session_id": "s1", "hook_event_name": "Stop", "transcript_path": str(transcript)}
    out = record(payload, tmp_path)
    text = out.read_text()
    lines = [json.loads(x) for x in text.splitlines()]
    got = {x["file_path"]: (x["memory_type"], x["chars"], x["load_reason"]) for x in lines}
    assert got == {
        "process/L0.md": ("Plugin", len(L0), "session_start"),
        "roles/product.md": ("Plugin", len(CARD), "session_start"),
        "/w/AGENTS.md": ("Project", 11, "session_start"),
        "/cfg/projects/w/memory/MEMORY.md": ("AutoMem", 7, "session_start"),
    }
    assert {x["source"] for x in lines} == {"transcript"}
    assert {x["event"] for x in lines} == {"InstructionsLoaded"}
    assert lines[0]["ts"] == 1795597200.0
    for secret in ("SECRET", "AAA", "MMM", "other hook"):
        assert secret not in text
    record(payload, tmp_path)  # a second run over the same transcript adds no line
    assert out.read_text() == text
    with transcript.open("a") as fh:  # a compact appends a boundary and a new load
        fh.write(json.dumps({"type": "system", "subtype": "compact_boundary"}) + "\n")
        fh.write(
            json.dumps(
                {
                    "type": "attachment",
                    "attachment": {
                        "type": "instructions",
                        "files": [
                            {"path": "/w/AGENTS.md", "type": "Project", "content": "A" * 12}
                        ],
                    },
                }
            )
            + "\n"
        )
    record(payload, tmp_path)
    last = json.loads(out.read_text().splitlines()[-1])
    assert (last["file_path"], last["chars"], last["load_reason"]) == (
        "/w/AGENTS.md",
        12,
        "compact",
    )
    assert len(out.read_text().splitlines()) == 5


def test_subagent_stop_reads_the_agent_transcript_under_its_own_offset(tmp_path):
    transcript = tmp_path / "agent.jsonl"
    _transcript(transcript)
    base = {"session_id": "s1", "agent_id": "a1", "agent_type": "we:dev-medium", "cwd": "/w"}
    payload = {**base, "hook_event_name": "SubagentStop", "agent_transcript_path": str(transcript)}
    out = record(payload, tmp_path)
    lines = [json.loads(x) for x in out.read_text().splitlines()]
    assert lines[0]["event"] == "SubagentStop"
    loads = [x for x in lines if x.get("source") == "transcript"]
    assert len(loads) == 4 and {x["agent_id"] for x in loads} == {"a1"}
    assert (tmp_path / ".claude" / "we-timing" / "s1.a1.offset").is_file()


def _instructions(chars: int) -> str:
    att = {"type": "instructions", "files": [{"path": "/w/AGENTS.md", "type": "Project"}]}
    att["files"][0]["content"] = "A" * chars
    return json.dumps({"type": "attachment", "attachment": att}) + "\n"


BOUNDARY = json.dumps({"type": "system", "subtype": "compact_boundary"}) + "\n"


def _stop(tmp_path, transcript):
    payload = {"session_id": "s1", "hook_event_name": "Stop", "transcript_path": str(transcript)}
    record(payload, tmp_path)
    out = tmp_path / ".claude" / "we-timing" / "s1.jsonl"
    return [json.loads(x) for x in out.read_text().splitlines()] if out.exists() else []


def test_a_load_after_a_boundary_read_by_a_later_run_is_labelled_compact(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(_instructions(3) + BOUNDARY)
    assert [x["load_reason"] for x in _stop(tmp_path, transcript)] == ["session_start"]
    with transcript.open("a") as fh:
        fh.write(_instructions(4))
    assert [(x["chars"], x["load_reason"]) for x in _stop(tmp_path, transcript)][-1] == (
        4,
        "compact",
    )


def test_a_rewritten_shorter_transcript_is_read_from_the_start(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(_instructions(3) + BOUNDARY + _instructions(4))
    assert [x["load_reason"] for x in _stop(tmp_path, transcript)] == [
        "session_start",
        "compact",
    ]
    transcript.write_text(_instructions(5))
    last = _stop(tmp_path, transcript)[-1]
    assert (last["chars"], last["load_reason"]) == (5, "session_start")


def test_an_unfinished_last_line_waits_and_is_read_whole_next_run(tmp_path):
    transcript = tmp_path / "t.jsonl"
    line = _instructions(6)
    transcript.write_text(_instructions(3) + line[:20])
    assert [x["chars"] for x in _stop(tmp_path, transcript)] == [3]
    with transcript.open("a") as fh:
        fh.write(line[20:])
    lines = _stop(tmp_path, transcript)
    assert [x["chars"] for x in lines] == [3, 6]
