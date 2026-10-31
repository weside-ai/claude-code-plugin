"""tmux_attention.py as Claude Code runs it: a subprocess with a fake `tmux` on PATH.

The fake `tmux` keeps the window options in a JSON file, so a test reads the style a real
status bar would draw.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent / "tmux_attention.py"
sys.path.insert(0, str(HOOK.parent))
import tmux_attention as t  # noqa: E402

FAKE_TMUX = """#!/usr/bin/env python3
import json, os, sys
state = os.environ["FAKE_TMUX_STATE"]
opts = json.load(open(state)) if os.path.exists(state) else {}
args = sys.argv[1:]
assert args[0] == "set-window-option", args
args = args[1:]
unset = args[0] == "-u"
if unset:
    args = args[1:]
assert args[0] == "-t", args
key = args[1] + " " + args[2]
if unset:
    opts.pop(key, None)
else:
    opts[key] = args[3]
json.dump(opts, open(state, "w"))
"""

ASK = {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion"}
ANSWERED = {"hook_event_name": "PostToolUse", "tool_name": "AskUserQuestion"}
PERMISSION = {"hook_event_name": "Notification", "notification_type": "permission_prompt"}
IDLE = {"hook_event_name": "Notification", "notification_type": "idle_prompt"}
PROMPT = {"hook_event_name": "UserPromptSubmit", "prompt": "ja"}
WHITE = {"%3 window-status-style": t.STYLE, "%3 window-status-current-style": t.STYLE}


@pytest.fixture
def tmux(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "tmux"
    fake.write_text(FAKE_TMUX)
    fake.chmod(0o755)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    state = tmp_path / "tmux.json"
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("TMUX_PANE", "CLAUDE_JOB_DIR", "FAKE_TMUX_STATE")
        and not k.startswith("CLAUDE_PLUGIN_OPTION_")
    }
    env.update(
        PATH=f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
        HOME=str(home),
        TMUX_PANE="%3",
        FAKE_TMUX_STATE=str(state),
    )

    class Tmux:
        def __init__(self) -> None:
            self.env = env

        def options(self) -> dict:
            return json.loads(state.read_text()) if state.exists() else {}

        def settings(self, options: dict) -> None:
            body = {"pluginConfigs": {"we@weside-ai": {"options": options}}}
            (home / ".claude" / "settings.json").write_text(json.dumps(body))

        def hook(self, payload: dict, **env_extra: str) -> None:
            res = subprocess.run(
                [sys.executable, str(HOOK)],
                input=json.dumps(payload),
                env={**self.env, **env_extra},
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
            assert res.returncode == 0, res.stderr
            assert res.stdout == "" and res.stderr == ""

    return Tmux()


@pytest.mark.parametrize("wait", [ASK, PERMISSION, IDLE])
def test_waiting_turns_the_window_white(tmux, wait):
    tmux.hook(wait)
    assert tmux.options() == WHITE


@pytest.mark.parametrize(
    "answer",
    [
        ANSWERED,
        {"hook_event_name": "PostToolUse", "tool_name": "Bash"},
        PROMPT,
        {"hook_event_name": "Stop"},
        {"hook_event_name": "SessionStart", "source": "resume"},
        {"hook_event_name": "SessionEnd"},
    ],
)
def test_an_answer_clears_the_window(tmux, answer):
    tmux.hook(ASK)
    tmux.hook(answer)
    assert tmux.options() == {}


def test_red_arm_without_the_off_the_style_stays(tmux, tmp_path):
    """The control: a copy of the hook with the off path cut leaves an answered window white."""
    source = HOOK.read_text()
    mutated = source.replace(
        'OFF = ("UserPromptSubmit", "PostToolUse", "Stop", "SessionStart", "SessionEnd")',
        "OFF = ()",
    )
    assert mutated != source
    cut = tmp_path / "tmux_attention_cut.py"
    cut.write_text(mutated)
    for payload in (ASK, PROMPT):
        subprocess.run(
            [sys.executable, str(cut)],
            input=json.dumps(payload),
            env=tmux.env,
            text=True,
            check=True,
        )
    assert tmux.options() == WHITE
    tmux.hook(PROMPT)
    assert tmux.options() == {}


def test_other_notifications_and_tools_leave_the_window_alone(tmux):
    tmux.hook({"hook_event_name": "Notification", "notification_type": "auth_success"})
    tmux.hook({"hook_event_name": "PreToolUse", "tool_name": "Bash"})
    assert tmux.options() == {}


@pytest.mark.parametrize(
    "case",
    [
        ({**ASK, "agent_id": "a1"}, {}),
        (ASK, {"TMUX_PANE": ""}),
        (ASK, {"CLAUDE_JOB_DIR": "/tmp/job"}),
    ],
    ids=["subagent", "no-tmux", "background-session"],
)
def test_subagent_no_tmux_and_background_do_nothing(tmux, case):
    payload, env = case
    tmux.hook(payload, **env)
    assert tmux.options() == {}


def test_option_off_does_nothing(tmux):
    tmux.settings({"tmuxAttention": False})
    tmux.hook(ASK)
    assert tmux.options() == {}


@pytest.mark.parametrize("value", ["false", "0"])
def test_option_off_from_the_environment(tmux, value):
    tmux.hook(ASK, CLAUDE_PLUGIN_OPTION_TMUXATTENTION=value)
    assert tmux.options() == {}


def test_environment_option_wins_over_settings(tmux):
    tmux.settings({"tmuxAttention": False, "tmuxAttentionStyle": "bg=red"})
    tmux.hook(
        ASK,
        CLAUDE_PLUGIN_OPTION_TMUXATTENTION="true",
        CLAUDE_PLUGIN_OPTION_TMUXATTENTIONSTYLE="bg=blue",
    )
    assert set(tmux.options().values()) == {"bg=blue"}


def test_style_option(tmux):
    tmux.settings({"tmuxAttentionStyle": "bg=yellow"})
    tmux.hook(ASK)
    assert set(tmux.options().values()) == {"bg=yellow"}


@pytest.mark.parametrize("stdin", ["", "not json", "[]"])
def test_bad_input_and_missing_tmux_exit_silently(tmux, stdin):
    for env in ({}, {"PATH": "/nonexistent"}):
        res = subprocess.run(
            [sys.executable, str(HOOK)],
            input=stdin,
            env={**tmux.env, **env},
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        assert (res.returncode, res.stdout, res.stderr) == (0, "", "")
    tmux.hook(ASK, PATH="/nonexistent")
