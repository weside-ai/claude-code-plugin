"""we-worker against a stub `claude` on PATH: start flags, guards, status, logs, stop."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "we-worker"
FLAG = "--allow-dangerously-skip-permissions"

pytestmark = pytest.mark.skipif(not shutil.which("bash"), reason="we-worker is a bash script")

STUB = r"""#!/usr/bin/env python3
import json, os, sys
state = os.environ["STUB_STATE"]
rows = json.load(open(state))
args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as fh:
    fh.write(json.dumps({"argv": args, "role": os.environ.get("WE_ROLE"),
                         "config_dir": os.environ.get("CLAUDE_CONFIG_DIR"),
                         "companion": os.environ.get("WESIDE_COMPANION")}) + "\n")
if args[:2] == ["agents", "--json"]:
    print(json.dumps(rows)); sys.exit(0)
if args[:1] == ["stop"]:
    json.dump([r for r in rows if r["id"] != args[1]], open(state, "w")); sys.exit(0)
if args[:1] == ["logs"]:
    print("\x1b[1mhello\x1b[0m world\r"); sys.exit(0)
sys.exit(0)
"""

CREW = {"version": 2, "roles": {"product": "po"}, "members": {"po": {"name": "Ada"}}}


def setup(tmp_path, rows=(), crew=CREW):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    (bindir / "claude").write_text(STUB)
    (bindir / "claude").chmod(0o755)
    state = tmp_path / "state.json"
    state.write_text(json.dumps(list(rows)))
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True, exist_ok=True)
    (project / "docs" / "plans").mkdir(parents=True, exist_ok=True)
    (project / "docs" / "plans" / "launch-owner-story.md").write_text("plan\n")
    if crew is not None:
        (project / ".weside").mkdir(exist_ok=True)
        (project / ".weside" / "crew.json").write_text(json.dumps(crew))
    env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "WE_WORKER_TIMER")}
    env.update(
        PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}",
        HOME=str(tmp_path / "home"),
        STUB_STATE=str(state),
        STUB_LOG=str(tmp_path / "log.jsonl"),
        CLAUDE_CONFIG_DIR=str(tmp_path / "pinned"),
        WESIDE_COMPANION="Ada",
    )
    return project, env


def run(project, env, *args):
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=project,
        env=env,
        timeout=60,
        check=False,
    )


def calls(tmp_path):
    log = tmp_path / "log.jsonl"
    return [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []


def started(tmp_path):
    return [c for c in calls(tmp_path) if "--bg" in c["argv"]]


def test_help_is_english_and_names_every_verb(tmp_path):
    out = subprocess.run(
        ["bash", str(SCRIPT), "--help"], capture_output=True, text=True, check=False
    ).stdout
    assert out.startswith("we-worker — start and steer a process worker")
    for verb in ("status", "stop <name|id>", "logs <name|id>", "waiting"):
        assert verb in out


def test_a_flag_is_no_worker_name(tmp_path):
    project, env = setup(tmp_path)
    proc = run(project, env, "--nope")
    assert proc.returncode == 2 and "no worker name" in proc.stderr
    assert not started(tmp_path)


def test_bg_start_drops_the_callers_claude_variables_and_needs_no_timer(tmp_path):
    project, env = setup(tmp_path)
    proc = run(project, env, "AC-12-impl", "--bg", "do it")
    assert proc.returncode == 0, proc.stderr
    (call,) = started(tmp_path)
    assert call["argv"] == ["--bg", "-n", "AC-12-impl", "do it"]
    assert call["role"] == "worker" and call["config_dir"] is None and call["companion"] is None
    assert "warning" not in proc.stderr


def test_allow_bypass_of_the_crew_adds_the_flag(tmp_path):
    project, env = setup(tmp_path, crew={**CREW, "launch": {"allow_bypass": True}})
    run(project, env, "AC-12-impl", "--bg", "go")
    (call,) = started(tmp_path)
    assert FLAG in call["argv"]


def test_the_timer_registers_and_arms_a_session_start_hook(tmp_path):
    timer = tmp_path / "timer.py"
    timer.write_text(
        "import sys, json\n"
        f"open({str(tmp_path / 'timer.args')!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
        "print('/state/w.json')\n"
    )
    project, env = setup(tmp_path, crew={**CREW, "launch": {"worker_timer": str(timer)}})
    proc = run(project, env, "AC-12-impl", "--bg", "--limit", "90m", "go")
    assert proc.returncode == 0, proc.stderr
    args = json.loads((tmp_path / "timer.args").read_text())
    assert args[:5] == ["register", "--name", "AC-12-impl", "--limit", "90m"]
    (call,) = started(tmp_path)
    settings = json.loads(call["argv"][call["argv"].index("--settings") + 1])
    hook = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert hook.endswith("arm /state/w.json")


def test_a_missing_timer_warns_and_still_starts(tmp_path):
    project, env = setup(tmp_path)
    env["WE_WORKER_TIMER"] = str(tmp_path / "absent.py")
    proc = run(project, env, "AC-12-impl", "--bg", "go")
    assert proc.returncode == 0 and "starts without a time limit" in proc.stderr
    assert started(tmp_path)


def test_a_name_held_by_a_living_session_refuses(tmp_path):
    rows = [
        {
            "id": "ab12",
            "name": "AC-12-impl",
            "kind": "background",
            "pid": os.getpid(),
            "state": "working",
            "sessionId": "s1",
        }
    ]
    project, env = setup(tmp_path, rows)
    proc = run(project, env, "AC-12-impl", "--bg", "go")
    assert proc.returncode == 2 and "already holds the name AC-12-impl" in proc.stderr
    assert not started(tmp_path)


def test_a_name_held_by_a_dead_session_starts(tmp_path):
    rows = [
        {
            "id": "ab12",
            "name": "AC-12-impl",
            "kind": "background",
            "pid": 999999999,
            "state": "blocked",
            "sessionId": "s1",
        }
    ]
    project, env = setup(tmp_path, rows)
    assert run(project, env, "AC-12-impl", "--bg", "go").returncode == 0
    assert started(tmp_path)


@pytest.mark.parametrize(
    "name,warns", [("AC-12-impl", False), ("launch-owner-p1", False), ("helper", True)]
)
def test_a_name_without_key_or_plan_slug_warns_but_starts(tmp_path, name, warns):
    project, env = setup(tmp_path)
    proc = run(project, env, name, "--bg", "go")
    assert proc.returncode == 0
    assert ("carries no story key" in proc.stderr) is warns
    assert started(tmp_path)


def _transcript(tmp_path, sid, entries):
    folder = tmp_path / "home" / ".claude" / "projects" / "-p"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{sid}.jsonl").write_text("\n".join(json.dumps(e) for e in entries) + "\n")


def _say(text, ts="2026-11-09T10:15:00Z", **extra):
    return {
        "type": "assistant",
        "timestamp": ts,
        "message": {"content": [{"type": "text", "text": text}]},
        **extra,
    }


def test_status_marks_the_usage_limit_apart_from_the_time_limit_and_prints_the_resume(tmp_path):
    rows = [
        {
            "id": "ab12",
            "name": "AC-12-impl",
            "kind": "background",
            "pid": 999999999,
            "state": "blocked",
            "sessionId": "s-1",
        }
    ]
    project, env = setup(tmp_path, rows)
    _transcript(
        tmp_path,
        "s-1",
        [
            _say("work"),
            _say(
                "You've hit your limit",
                ts="2026-11-09T11:40:00Z",
                isApiErrorMessage=True,
                error="rate_limit",
            ),
        ],
    )
    states = tmp_path / "home" / ".claude" / "we-state" / "workers"
    states.mkdir(parents=True)
    (states / "AC-12-impl.json").write_text(json.dumps({"deadline": "2000-01-01T00:00:00Z"}))
    out = run(project, env, "status").stdout.splitlines()
    assert (
        out[0]
        == "ab12 AC-12-impl pid=999999999 exited(blocked) last=11:40 usage-limit time-limit=reached"
    )
    assert out[1] == "  resume after the reset: we-worker AC-12-impl --bg --resume s-1"


def test_logs_prints_the_last_assistant_texts_plain(tmp_path):
    rows = [{"id": "ab12", "name": "w", "kind": "background", "pid": 1, "sessionId": "s-1"}]
    project, env = setup(tmp_path, rows)
    _transcript(tmp_path, "s-1", [_say(f"step {i}") for i in range(8)])
    out = run(project, env, "logs", "w", "-n", "2").stdout
    assert out == "[10:15] step 6\n\n[10:15] step 7\n\n"


def test_logs_raw_strips_ansi(tmp_path):
    rows = [{"id": "ab12", "name": "w", "kind": "background", "pid": 1, "sessionId": "s-1"}]
    project, env = setup(tmp_path, rows)
    assert run(project, env, "logs", "w", "--raw").stdout == "hello world\n"


def test_stop_waits_until_the_row_is_gone(tmp_path):
    rows = [
        {"id": "ab12", "name": "w", "kind": "background", "pid": os.getpid(), "sessionId": "s"}
    ]
    project, env = setup(tmp_path, rows)
    proc = run(project, env, "stop", "w")
    assert proc.returncode == 0 and "w (ab12) stopped" in proc.stdout


@pytest.mark.parametrize(("name", "warns"), [("AC-12-impl", False), ("helper", True)])
def test_without_a_crew_the_default_key_pattern_decides(tmp_path, name, warns):
    project, env = setup(tmp_path, crew=None)
    proc = run(project, env, name, "--bg", "go")
    assert proc.returncode == 0
    assert ("carries no story key ([A-Z]+-\\d+)" in proc.stderr) is warns
