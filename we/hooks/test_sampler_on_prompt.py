"""UserPromptSubmit sampler_on_prompt.py: a stale sampler for coordinator and machinery, a blocked
worker for its starter and the coordinator, each once per episode; silent everywhere else.

Run with: python3 -m pytest -q we/hooks/test_sampler_on_prompt.py
The hook runs as a subprocess, as Claude Code runs it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent / "sampler_on_prompt.py"
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
CREW = SCRIPTS / "fixtures" / "crew-v2-generic.json"
sys.path.insert(0, str(SCRIPTS))
import flow_log  # noqa: E402

TZ = "Europe/Berlin"


def iso(minutes_ago):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime(flow_log.TS_FMT)


@pytest.fixture
def ws(tmp_path):
    """A repo with the generic crew bound to a flow dir, a board file and a `claude` that logs."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".weside").mkdir()
    crew = json.loads(CREW.read_text(encoding="utf-8"))
    crew["flow"] = {"log_dir": str(tmp_path / "flow")}
    (repo / ".weside" / "crew.json").write_text(json.dumps(crew), encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "claude"
    fake.write_text(
        "#!/bin/sh\necho called >> " + str(tmp_path / "claude-calls") + "\n", encoding="utf-8"
    )
    fake.chmod(0o755)
    (tmp_path / "board.json").write_text(json.dumps({"sessions": []}), encoding="utf-8")
    return tmp_path


def bind(ws, log_dir="flow"):
    path = ws / "repo" / ".weside" / "crew.json"
    crew = json.loads(path.read_text(encoding="utf-8"))
    crew["flow"] = {"log_dir": str(ws / log_dir)} if log_dir else {}
    path.write_text(json.dumps(crew), encoding="utf-8")


def heartbeat(ws, minutes_ago):
    ts = iso(minutes_ago)
    flow_log.append(ws / "flow", {"type": "heartbeat", "ts": ts}, TZ)
    return ts


def board(ws, *lines):
    (ws / "board.json").write_text(json.dumps({"sessions": list(lines)}), encoding="utf-8")


def hook(ws, pin=None, session="sid-me"):
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CLAUDE_", "WESIDE_COMPANION", "WE_ROLE"))
    }
    env.update(
        PATH=f"{ws / 'bin'}{os.pathsep}{env['PATH']}",
        HOME=str(ws),
        CLAUDE_PLUGIN_OPTION_BOARDFILE=str(ws / "board.json"),
    )
    if pin:
        env.update(WESIDE_COMPANION=pin, WE_ROLE="master")
    payload = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": session,
        "cwd": str(ws / "repo"),
    }
    done = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(ws / "repo"),
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stderr == ""
    if not done.stdout.strip():
        return []
    out = json.loads(done.stdout)
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    return out["hookSpecificOutput"]["additionalContext"].splitlines()


BLOCKED = {
    "name": "proj-12-build",
    "keys": ["PROJ-12"],
    "waiting_on": "human",
    "blocked": {
        "kind": "permission",
        "starter": "lead-12",
        "starter_session_id": "sid-lead",
        "key": "PROJ-12",
        "since": "2026-11-05T09:05:00Z",
        "waiting_for": "permission prompt",
        "command": "make deploy-prod",
    },
}
BLOCKED_LINE = (
    "blocked: proj-12-build (PROJ-12) waits on human (permission) since 10:05: make deploy-prod"
)


class TestStale:
    @pytest.mark.parametrize("pin", ["otto", "kit"])  # coordinator, machinery
    def test_a_stale_sampler_is_named_once_per_episode(self, ws, pin):
        ts = heartbeat(ws, 20)
        assert hook(ws, pin) == [f"sampler: stale since 20 min (last line {ts})"]
        assert hook(ws, pin) == []  # the same episode stays quiet
        assert hook(ws, pin, session="sid-other") != []  # another session hears it too

    def test_a_fresh_line_ends_the_episode_and_the_next_one_is_named(self, ws):
        heartbeat(ws, 40)
        assert len(hook(ws, "otto")) == 1
        # a newer last line (the sampler ran again, then died again) is a new episode
        ts = heartbeat(ws, 30)
        assert hook(ws, "otto") == [f"sampler: stale since 30 min (last line {ts})"]
        heartbeat(ws, 1)
        assert hook(ws, "otto") == []

    def test_no_line_at_all_is_stale(self, ws):
        assert hook(ws, "otto") == [f"sampler: stale, no line today or yesterday in {ws / 'flow'}"]

    @pytest.mark.parametrize("pin", [None, "ada"])  # unnamed, product
    def test_other_roles_hear_nothing(self, ws, pin):
        heartbeat(ws, 20)
        assert hook(ws, pin) == []

    def test_a_fresh_sampler_is_silent(self, ws):
        heartbeat(ws, 1)
        assert hook(ws, "otto") == []


class TestBlocked:
    def test_the_starter_hears_its_blocked_worker_once_per_wait(self, ws):
        board(ws, BLOCKED)
        heartbeat(ws, 1)
        assert hook(ws, session="sid-lead") == [BLOCKED_LINE]
        assert hook(ws, session="sid-lead") == []
        again = {**BLOCKED, "blocked": {**BLOCKED["blocked"], "since": "2026-11-05T11:00:00Z"}}
        board(ws, again)  # a new wait
        assert len(hook(ws, session="sid-lead")) == 1

    def test_the_coordinator_hears_it_too_and_others_do_not(self, ws):
        board(ws, BLOCKED)
        heartbeat(ws, 1)
        assert hook(ws, "otto") == [BLOCKED_LINE]
        assert hook(ws, "ada", session="sid-ada") == []
        assert hook(ws, session="sid-stranger") == []

    def test_a_chat_wait_names_its_role_and_a_missing_command_ends_the_line(self, ws):
        chat = {
            "name": "proj-12-build",
            "waiting_on": "coordinator",
            "blocked": {
                "kind": "chat",
                "starter_session_id": "sid-lead",
                "since": "2026-11-05T09:05:00Z",
            },
        }
        board(ws, chat)
        heartbeat(ws, 1)
        assert hook(ws, session="sid-lead") == [
            "blocked: proj-12-build (no key) waits on coordinator (chat) since 10:05"
        ]

    def test_stale_and_blocked_come_in_one_context(self, ws):
        board(ws, BLOCKED)
        ts = heartbeat(ws, 20)
        assert hook(ws, "otto") == [f"sampler: stale since 20 min (last line {ts})", BLOCKED_LINE]


class TestSilence:
    def test_an_unbound_crew_is_silent_and_reads_nothing(self, ws):
        bind(ws, log_dir=None)
        board(ws, BLOCKED)
        assert hook(ws, "otto") == []
        assert not (ws / "flow").exists()

    def test_it_never_runs_a_subprocess(self, ws):
        board(ws, BLOCKED)
        heartbeat(ws, 20)
        hook(ws, "otto")
        hook(ws, session="sid-lead")
        assert not (ws / "claude-calls").exists()

    @pytest.mark.parametrize("text", ["{not json", '["a list"]', '{"sessions": "x"}'])
    def test_a_broken_board_is_silent(self, ws, text):
        (ws / "board.json").write_text(text, encoding="utf-8")
        heartbeat(ws, 1)
        assert hook(ws, "otto") == []

    def test_garbage_on_stdin_is_silent(self):
        done = subprocess.run(
            [sys.executable, str(HOOK)], input="nope", capture_output=True, text=True, check=False
        )
        assert (done.returncode, done.stdout, done.stderr) == (0, "", "")
