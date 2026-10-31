"""question_gate.py as Claude Code runs it: a subprocess with a synthetic transcript."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "question_gate.py"
sys.path.insert(0, str(HOOK.parent))
import question_gate as g  # noqa: E402

QUESTION = "PR #7 ist offen. Soll ich den Fix als eigenen PR bauen oder auf den Branch legen?"


def _use(name: str, args: dict, uid: str) -> dict:
    block = {"type": "tool_use", "id": uid, "name": name, "input": args}
    return {"type": "assistant", "message": {"content": [block]}}


def _result(uid: str, result: dict) -> dict:
    block = {"type": "tool_result", "tool_use_id": uid, "content": "ok"}
    return {"type": "user", "message": {"content": [block]}, "toolUseResult": result}


def _notification(task: str, status: str | None) -> dict:
    inner = f"<task-id>{task}</task-id>" + (f"<status>{status}</status>" if status else "")
    return {
        "type": "user",
        "message": {"content": f"<task-notification>{inner}</task-notification>"},
    }


LAUNCH_AGENT = [
    _use("Agent", {"subagent_type": "we:dev-medium", "run_in_background": True}, "u1"),
    _result("u1", {"status": "async_launched", "agentId": "a1", "isAsync": True}),
]
LAUNCH_BASH = [
    _use("Bash", {"command": "watch.sh", "run_in_background": True}, "u2"),
    _result("u2", {"backgroundTaskId": "b2", "stdout": ""}),
]
LAUNCH_MONITOR = [
    _use("Monitor", {"command": "x"}, "u3"),
    _result("u3", {"taskId": "m3", "persistent": False, "timeoutMs": 1000}),
]
TEAMMATE = [
    _use("Agent", {"subagent_type": "we:dev-medium", "name": "w1"}, "u4"),
    _result("u4", {"status": "teammate_spawned", "name": "w1", "agentId": "w1@t"}),
]
IDLE = {
    "type": "user",
    "message": {
        "content": '<teammate-message teammate_id="w1" color="blue">'
        '{"type":"idle_notification","from":"w1"}</teammate-message>'
    },
}


def _env(tmp: Path) -> dict:
    """User and project settings point into tmp: the developer's own settings stay out."""
    for sub in ("config", "project"):
        (tmp / sub).mkdir(exist_ok=True)
    return {
        **os.environ,
        "CLAUDE_CONFIG_DIR": str(tmp / "config"),
        "CLAUDE_PROJECT_DIR": str(tmp / "project"),
    }


def _deny(path: Path, rules: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"permissions": {"deny": rules}}))


def run(tmp: Path, entries: list[dict], text: str = QUESTION, **extra) -> dict | None:
    env = _env(tmp)
    path = tmp / "t.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    payload = {
        "hook_event_name": "Stop",
        "last_assistant_message": text,
        "transcript_path": str(path),
        **extra,
    }
    res = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
        env=env,
    )
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout) if res.stdout.strip() else None


def test_question_while_agent_runs_is_sent_back(tmp_path):
    out = run(tmp_path, LAUNCH_AGENT)
    assert out["decision"] == "block"
    assert "AskUserQuestion, recommendation as the first option" in out["reason"]


def test_denied_tool_never_blocks(tmp_path):
    # User settings: the session cannot call AskUserQuestion, plain text is the right form.
    _deny(tmp_path / "config" / "settings.json", ["Bash(rm:*)", "AskUserQuestion"])
    assert run(tmp_path, LAUNCH_AGENT) is None


def test_denied_tool_in_project_settings_never_blocks(tmp_path):
    _deny(tmp_path / "project" / ".claude" / "settings.local.json", ["AskUserQuestion(*)"])
    assert run(tmp_path, LAUNCH_AGENT) is None


def test_other_deny_rules_keep_the_block(tmp_path):
    _deny(tmp_path / "config" / "settings.json", ["AskUserQuestionnaire", "Bash(rm:*)"])
    assert run(tmp_path, LAUNCH_AGENT)["decision"] == "block"


def test_unreadable_settings_fail_open(tmp_path):
    bad = tmp_path / "config" / "settings.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("{not json")
    assert run(tmp_path, LAUNCH_AGENT) is None


def test_question_after_completion_passes(tmp_path):
    assert run(tmp_path, [*LAUNCH_AGENT, _notification("a1", "completed")]) is None


def test_background_command_and_monitor_count(tmp_path):
    assert run(tmp_path, LAUNCH_BASH)["decision"] == "block"
    # A Monitor event without a status ends nothing; a terminal one does.
    assert run(tmp_path, [*LAUNCH_MONITOR, _notification("m3", None)])["decision"] == "block"
    assert run(tmp_path, [*LAUNCH_MONITOR, _notification("m3", "failed")]) is None


def test_task_stop_ends_a_task_and_a_teammate(tmp_path):
    assert run(tmp_path, [*LAUNCH_BASH, _use("TaskStop", {"task_id": "b2"}, "s")]) is None
    assert run(tmp_path, [*TEAMMATE, _use("TaskStop", {"task_id": "w1"}, "s")]) is None


def test_teammate_busy_until_idle_and_again_after_a_message(tmp_path):
    assert run(tmp_path, TEAMMATE)["decision"] == "block"
    assert run(tmp_path, [*TEAMMATE, IDLE]) is None
    resumed = [*TEAMMATE, IDLE, _use("SendMessage", {"to": "w1", "message": "go"}, "s")]
    assert run(tmp_path, resumed)["decision"] == "block"


def test_notification_in_queue_operation_counts(tmp_path):
    note = _notification("a1", "completed")["message"]["content"]
    queued = {"type": "queue-operation", "operation": "enqueue", "content": note}
    assert run(tmp_path, [*LAUNCH_AGENT, queued]) is None


def test_idle_notification_in_attachment_counts(tmp_path):
    # An attachment carries the message as a string value; a JSON dump would escape its quotes.
    attached = {
        "type": "attachment",
        "attachment": {"type": "queued_command", "prompt": IDLE["message"]["content"]},
    }
    assert run(tmp_path, [*TEAMMATE, attached]) is None
    assert IDLE["message"]["content"] in g._text_of(attached)


def test_statement_with_work_running_passes(tmp_path):
    assert (
        run(tmp_path, LAUNCH_AGENT, text="Worker läuft, ich melde mich mit dem Ergebnis.") is None
    )


def test_once_per_turn_and_never_in_subagents(tmp_path):
    assert run(tmp_path, LAUNCH_AGENT, stop_hook_active=True) is None
    assert run(tmp_path, LAUNCH_AGENT, agent_id="x") is None
    assert run(tmp_path, LAUNCH_AGENT, hook_event_name="SubagentStop") is None


def test_unreadable_transcript_fails_open(tmp_path):
    payload = {"last_assistant_message": QUESTION, "transcript_path": str(tmp_path / "missing")}
    res = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env=_env(tmp_path),
    )
    assert res.returncode == 0 and not res.stdout.strip()


def test_question_detection_ignores_code_quotes_and_urls():
    assert g.ends_in_question("Mergen? **Soll ich?**")
    assert g.ends_in_question("Welche Variante nimmst du (A empfohlen)?")
    assert not g.ends_in_question("Done.\n\n```bash\nfoo?\n```")
    assert not g.ends_in_question("Er fragte „geht das?“")
    assert not g.ends_in_question("Fertig.\n> Soll ich?")
    assert not g.ends_in_question("Siehe https://x.test/a?b")
    assert not g.ends_in_question("Gate `x?`")
