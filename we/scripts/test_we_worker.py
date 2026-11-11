"""we-worker against a stub `claude` on PATH: start flags, guards, status, logs, stop."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "we-worker"
FLAG = "--allow-dangerously-skip-permissions"
GO = (Path(__file__).parent / "fixtures" / "briefs" / "complete-en.md").read_text()

pytestmark = pytest.mark.skipif(not shutil.which("bash"), reason="we-worker is a bash script")

STUB = r"""#!/usr/bin/env python3
import json, os, sys
state = os.environ["STUB_STATE"]
rows = json.load(open(state))
args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as fh:
    fh.write(json.dumps({"argv": args, "role": os.environ.get("WE_ROLE"),
                         "config_dir": os.environ.get("CLAUDE_CONFIG_DIR"),
                         "companion": os.environ.get("WESIDE_COMPANION"),
                         "key": os.environ.get("WE_STORY_KEY")}) + "\n")
if args[:2] == ["agents", "--json"]:
    print(json.dumps(rows)); sys.exit(0)
if args[:1] == ["stop"]:
    json.dump([r for r in rows if r["id"] != args[1]], open(state, "w")); sys.exit(0)
if args[:1] == ["--help"]:
    if os.environ.get("STUB_NO_HELP"):
        sys.exit(1)
    print("Options:\n  --bg  --agent <a>  --permission-mode <m>  -n, --name <n>  --resume  --settings  --allow-dangerously-skip-permissions"); sys.exit(0)
if args[:1] == ["logs"]:
    print("\x1b[1mhello\x1b[0m world\r"); sys.exit(0)
sys.exit(0)
"""

CREW = {"version": 2, "roles": {"product": "po"}, "members": {"po": {"name": "Ada"}}}


TMUX_STUB = r"""#!/usr/bin/env python3
import json, os, sys
with open(os.environ["STUB_LOG"], "a") as fh:
    fh.write(json.dumps({"argv": [], "tmux": sys.argv[1:]}) + "\n")
if sys.argv[1:2] == ["list-sessions"]:
    print("1 stub")
"""


def setup(tmp_path, rows=(), crew=CREW):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    (bindir / "claude").write_text(STUB)
    (bindir / "claude").chmod(0o755)
    # a stub tmux: a window launch never reaches a real tmux server (and its real claude)
    (bindir / "tmux").write_text(TMUX_STUB)
    (bindir / "tmux").chmod(0o755)
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
    proc = run(project, env, "AC-12-impl", "--bg", GO)
    assert proc.returncode == 0, proc.stderr
    (call,) = started(tmp_path)
    settings = str(
        tmp_path / "home" / ".claude" / "we-state" / "workers" / "AC-12-impl.settings.json"
    )
    assert call["argv"] == ["--bg", "-n", "AC-12-impl", "--settings", settings, GO]
    assert call["role"] == "worker" and call["config_dir"] is None and call["companion"] is None
    assert "warning" not in proc.stderr


def test_allow_bypass_of_the_crew_adds_the_flag(tmp_path):
    project, env = setup(tmp_path, crew={**CREW, "launch": {"allow_bypass": True}})
    run(project, env, "AC-12-impl", "--bg", GO)
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
    proc = run(project, env, "AC-12-impl", "--bg", "--limit", "90m", GO)
    assert proc.returncode == 0, proc.stderr
    args = json.loads((tmp_path / "timer.args").read_text())
    assert args[:5] == ["register", "--name", "AC-12-impl", "--limit", "90m"]
    (call,) = started(tmp_path)
    settings = json.loads(Path(call["argv"][call["argv"].index("--settings") + 1]).read_text())
    hook = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert hook.endswith("arm /state/w.json")


def test_a_missing_timer_warns_and_still_starts(tmp_path):
    project, env = setup(tmp_path)
    env["WE_WORKER_TIMER"] = str(tmp_path / "absent.py")
    proc = run(project, env, "AC-12-impl", "--bg", GO)
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
    proc = run(project, env, "AC-12-impl", "--bg", GO)
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
    assert run(project, env, "AC-12-impl", "--bg", GO).returncode == 0
    assert started(tmp_path)


@pytest.mark.parametrize("name", ["AC-12-impl", "AC-12"])
def test_a_name_with_the_story_key_starts(tmp_path, name):
    project, env = setup(tmp_path)
    proc = run(project, env, name, "--bg", GO)
    assert proc.returncode == 0, proc.stderr
    assert started(tmp_path)


@pytest.mark.parametrize("name", ["build-fix", "launch-owner-p1", "helper"])
def test_a_name_without_the_story_key_refuses_before_claude(tmp_path, name):
    project, env = setup(tmp_path)
    proc = run(project, env, name, "--bg", GO)
    assert proc.returncode == 2
    assert proc.stderr.startswith(
        f"we-worker: worker name {name} carries no story key ([A-Z]+-\\d+), e.g. "
    )
    assert not started(tmp_path)


@pytest.mark.parametrize(
    "args",
    [
        ("--bg", "fix it"),
        ("--bg",),
        ("--bg", "--agent", "we:dev-medium"),
        ("--bg", "## Goal\nx\n## Output\n"),
    ],
)
def test_an_incomplete_brief_refuses_with_the_template(tmp_path, args):
    project, env = setup(tmp_path)
    proc = run(project, env, "AC-12-impl", *args)
    assert proc.returncode == 2 and proc.stderr.startswith("we-worker: the brief lacks ")
    assert "## Grenzen und wann stoppen (Limits and when to stop)" in proc.stderr
    assert not started(tmp_path)


def test_a_pointer_brief_is_read_from_its_file(tmp_path):
    project, env = setup(tmp_path)
    good = Path(__file__).parent / "fixtures" / "briefs" / "complete-de.md"
    assert run(project, env, "AC-12-impl", "--bg", f"Read {good} and follow it.").returncode == 0
    bad = good.with_name("missing-goal.md")
    proc = run(project, env, "AC-12-other", "--bg", f"Read {bad} and follow it.")
    assert proc.returncode == 2 and "Ziel / Goal" in proc.stderr


def test_a_resumed_worker_checks_the_name_only(tmp_path):
    project, env = setup(tmp_path)
    sid = "0123abcd-0000-0000-0000-000000000000"
    assert run(project, env, "AC-12-impl", "--bg", "--resume", sid).returncode == 0
    assert run(project, env, "helper", "--bg", "--resume", sid).returncode == 2


def test_the_worker_gets_its_settings_file_and_key(tmp_path):
    project, env = setup(tmp_path)
    proc = run(project, env, "AC-12-impl", "--bg", GO)
    assert proc.returncode == 0, proc.stderr
    (call,) = started(tmp_path)
    path = Path(call["argv"][call["argv"].index("--settings") + 1])
    assert (
        path == tmp_path / "home" / ".claude" / "we-state" / "workers" / "AC-12-impl.settings.json"
    )
    doc = json.loads(path.read_text())
    assert (
        "Bash(*gh secret *)" in doc["permissions"]["deny"]
        and doc["env"]["WE_STORY_KEY"] == "AC-12"
    )
    assert call["key"] == "AC-12"


def test_a_window_worker_carries_settings_and_key_too(tmp_path):
    project, env = setup(tmp_path)
    run(project, env, "AC-12-impl", GO)
    (window,) = [c["tmux"] for c in calls(tmp_path) if c.get("tmux", [""])[0] == "new-window"]
    assert "WE_STORY_KEY=AC-12" in window[-1] and "--settings" in window[-1]


def test_without_the_plugin_script_no_worker_starts(tmp_path):
    project, env = setup(tmp_path)
    lone = tmp_path / "lone"
    lone.mkdir()
    (lone / "we-worker").write_text(SCRIPT.read_text())
    proc = subprocess.run(
        ["bash", str(lone / "we-worker"), "AC-12-impl", "--bg", GO],
        capture_output=True,
        text=True,
        cwd=project,
        env=env,
        check=False,
    )
    assert proc.returncode == 2 and "plugin we not installed" in proc.stderr
    assert not started(tmp_path)


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


def _fake_worker():
    """A process with one child, standing in for a worker session and the watcher it left."""
    proc = subprocess.Popen(["bash", "-c", "sleep 60 & wait"])
    for _ in range(50):
        kids = subprocess.run(
            ["pgrep", "-P", str(proc.pid)], capture_output=True, text=True, check=False
        )
        if kids.stdout.strip():
            return proc, int(kids.stdout.split()[0])
        time.sleep(0.05)
    raise AssertionError("no child")


def test_stop_waits_until_the_row_is_gone_and_ends_what_it_left(tmp_path):
    worker, child = _fake_worker()
    try:
        rows = [
            {"id": "ab12", "name": "w", "kind": "background", "pid": worker.pid, "sessionId": "s"}
        ]
        project, env = setup(tmp_path, rows)
        proc = run(project, env, "stop", "w")
        assert proc.returncode == 0, proc.stderr
        assert f"w (ab12) stopped; also ended: {child} sleep" in proc.stdout
    finally:
        worker.kill()


def _detached_sleep(role: str | None) -> int:
    """A detached `sleep` (init reaps it, as a real session's parent would), started as a worker
    (`WE_ROLE=worker`) or as no worker at all."""
    env = {k: v for k, v in os.environ.items() if k != "WE_ROLE"}
    if role:
        env["WE_ROLE"] = role
    out = subprocess.run(
        ["bash", "-c", "sleep 60 >/dev/null 2>&1 & echo $!"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return int(out.stdout)


@pytest.mark.skipif(not Path("/proc/self/environ").exists(), reason="WE_ROLE read from /proc")
def test_stop_of_a_window_worker_sends_sigterm_to_its_pid(tmp_path):
    pid = _detached_sleep("worker")
    try:
        rows = [{"id": "cd34", "name": "w", "kind": "interactive", "pid": pid, "sessionId": "s"}]
        project, env = setup(tmp_path, rows)
        env["WE_WORKER_STOP_WAIT"] = "5"
        proc = run(project, env, "stop", "w")
        assert proc.returncode == 0 and "w (cd34) stopped" in proc.stdout, proc.stderr
        assert not any(c["argv"][:1] == ["stop"] for c in calls(tmp_path))
    finally:
        subprocess.run(["kill", str(pid)], capture_output=True, check=False)


@pytest.mark.parametrize("role", [None, "master"])
def test_stop_never_ends_a_session_that_is_no_worker(tmp_path, role):
    """A name that hits a master or companion (no marker, no WE_ROLE=worker) is a
    typo; stop refuses and names `claude stop <id>`."""
    pid = _detached_sleep(role)
    try:
        rows = [
            {"id": "ma01", "name": "Samu", "kind": "interactive", "pid": pid, "sessionId": "s"}
        ]
        project, env = setup(tmp_path, rows)
        proc = run(project, env, "stop", "Samu")
        assert proc.returncode == 1
        assert "is no worker" in proc.stderr and "claude stop ma01" in proc.stderr
        assert subprocess.run(["kill", "-0", str(pid)], check=False).returncode == 0
    finally:
        subprocess.run(["kill", str(pid)], capture_output=True, check=False)


@pytest.mark.parametrize(("name", "code"), [("AC-12-impl", 0), ("helper", 2)])
def test_without_a_crew_the_default_key_pattern_decides(tmp_path, name, code):
    project, env = setup(tmp_path, crew=None)
    proc = run(project, env, name, "--bg", GO)
    assert proc.returncode == code
    assert ("carries no story key ([A-Z]+-\\d+)" in proc.stderr) is bool(code)


def test_an_unknown_flag_before_the_claude_args_refuses(tmp_path):
    project, env = setup(tmp_path)
    proc = run(project, env, "AC-12-impl", "--bg", "--cwd", "/x", GO)
    assert proc.returncode == 2 and "--cwd is neither a we-worker flag" in proc.stderr
    assert "cd <tree> && we-worker AC-12-impl" in proc.stderr
    assert not started(tmp_path)


def test_an_unknown_flag_later_among_the_claude_args_refuses(tmp_path):
    project, env = setup(tmp_path)
    proc = run(project, env, "AC-12-impl", "--bg", "--agent", "x", "--cwd", "/x", GO)
    assert proc.returncode == 2 and "--cwd is neither a we-worker flag" in proc.stderr
    assert not started(tmp_path)


def test_a_claude_flag_passes(tmp_path):
    project, env = setup(tmp_path)
    assert run(project, env, "AC-12-impl", "--bg", "--agent", "we:dev-medium", GO).returncode == 0
    assert started(tmp_path)[0]["argv"][-3:] == ["--agent", "we:dev-medium", GO]


@pytest.mark.parametrize(
    ("mode", "args", "bypass"),
    [("bypass", ["--bg"], True), ("bypass", [], False), ("auto", ["--bg"], False)],
)
def test_worker_mode_bypass_starts_only_a_bg_worker_in_bypass(tmp_path, mode, args, bypass):
    project, env = setup(tmp_path, crew={**CREW, "launch": {"worker_mode": mode}})
    env["TMUX"] = ""
    run(project, env, "AC-12-impl", *args, GO)
    argv = [c["argv"] for c in calls(tmp_path) if c["argv"] and c["argv"][0] in ("--bg", "-n")]
    if args:
        assert ("--permission-mode" in argv[0]) is bypass
    else:
        windows = [c["tmux"] for c in calls(tmp_path) if c.get("tmux", [""])[0] == "new-window"]
        assert len(windows) == 1 and "-n" in windows[0]
        assert "--permission-mode" not in windows[0][-1]


def test_a_permission_mode_of_the_caller_wins(tmp_path):
    project, env = setup(tmp_path, crew={**CREW, "launch": {"worker_mode": "bypass"}})
    run(project, env, "AC-12-impl", "--bg", "--permission-mode", "plan", GO)
    (call,) = started(tmp_path)
    assert call["argv"].count("--permission-mode") == 1 and "plan" in call["argv"]


def test_checkpoint_commits_tracked_changes_and_pushes_a_wip_branch(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    tree = tmp_path / "tree"
    subprocess.run(["git", "init", "-q", "-b", "feat/AC-12-slug", str(tree)], check=True)
    git = ["git", "-C", str(tree), "-c", "user.email=t@t", "-c", "user.name=t"]
    (tree / "a.txt").write_text("one\n")
    subprocess.run([*git, "add", "a.txt"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "one"], check=True)
    subprocess.run([*git, "remote", "add", "origin", str(origin)], check=True)
    (tree / "a.txt").write_text("two\n")
    (tree / "untracked.txt").write_text("x\n")
    rows = [
        {
            "id": "ab12",
            "name": "w",
            "kind": "background",
            "pid": 1,
            "cwd": str(tree),
            "sessionId": "s",
        }
    ]
    project, env = setup(tmp_path, rows)
    env.update(
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@t",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@t",
    )
    proc = run(project, env, "checkpoint", "w")
    assert proc.returncode == 0, proc.stderr
    assert "pushed to wip/AC-12-slug" in proc.stdout
    shown = subprocess.run(
        ["git", "--git-dir", str(origin), "show", "wip/AC-12-slug:a.txt"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert shown.stdout == "two\n"
    # a new file may be a scratch dump or a local secret: named, never pushed
    assert "not in it (new, untracked): untracked.txt" in proc.stdout
    missing = subprocess.run(
        ["git", "--git-dir", str(origin), "show", "wip/AC-12-slug:untracked.txt"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode != 0


def _checkpoint_tree(tmp_path, branch):
    tree = tmp_path / "tree"
    subprocess.run(["git", "init", "-q", "-b", branch, str(tree)], check=True)
    git = ["git", "-C", str(tree), "-c", "user.email=t@t", "-c", "user.name=t"]
    (tree / "a.txt").write_text("one\n")
    subprocess.run([*git, "add", "a.txt"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "one"], check=True)
    (tree / "a.txt").write_text("two\n")
    return tree


def test_checkpoint_refuses_a_session_that_is_no_worker(tmp_path):
    tree = _checkpoint_tree(tmp_path, "feat/x")
    rows = [{"id": "ma1", "name": "Samu", "kind": "interactive", "pid": "-", "cwd": str(tree)}]
    project, env = setup(tmp_path, rows)
    proc = run(project, env, "checkpoint", "Samu")
    assert proc.returncode == 1 and "is no worker" in proc.stderr
    assert "two" in (tree / "a.txt").read_text()
    log = subprocess.run(
        ["git", "-C", str(tree), "log", "--oneline"], capture_output=True, text=True, check=True
    )
    assert "checkpoint" not in log.stdout


def test_checkpoint_never_commits_on_main(tmp_path):
    tree = _checkpoint_tree(tmp_path, "main")
    rows = [{"id": "ab1", "name": "w", "kind": "background", "pid": 1, "cwd": str(tree)}]
    project, env = setup(tmp_path, rows)
    proc = run(project, env, "checkpoint", "w")
    assert proc.returncode == 1 and "is on main" in proc.stderr


def test_a_flag_as_the_last_word_is_checked_too(tmp_path):
    """With no prompt, the last word is a flag, not the prompt."""
    project, env = setup(tmp_path)
    proc = run(project, env, "AC-12-impl", "--bg", "--agent", "a", "--cwd")
    assert proc.returncode == 2 and "--cwd is neither a we-worker flag" in proc.stderr


@pytest.mark.parametrize(("kind", "code"), [("background", 0), ("interactive", 1)])
def test_is_worker_is_the_one_owner_of_the_rule(tmp_path, kind, code):
    rows = [{"id": "x1", "name": "x", "kind": kind, "pid": "-", "cwd": "-"}]
    project, env = setup(tmp_path, rows)
    assert run(project, env, "is-worker", "x1").returncode == code


@pytest.mark.parametrize(
    ("kind", "field", "state"),
    [("background", "state", "working"), ("interactive", "status", "busy")],
)
def test_checkpoint_refuses_a_worker_that_is_still_working(tmp_path, kind, field, state):
    """One writer per worktree: a checkpoint commits only in an idle or stopped worker's tree."""
    tree = _checkpoint_tree(tmp_path, "feat/x")
    if kind == "interactive":  # a window worker, recognised by the launcher's marker
        gd = subprocess.run(
            ["git", "-C", str(tree), "rev-parse", "--absolute-git-dir"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        Path(gd, "we-worker.json").write_text(json.dumps({"name": "w"}))
    rows = [
        {
            "id": "ab1",
            "name": "w",
            "kind": kind,
            "pid": 1,
            field: state,  # claude agents: background rows say state, interactive rows status
            "cwd": str(tree),
        }
    ]
    project, env = setup(tmp_path, rows)
    proc = run(project, env, "checkpoint", "w")
    assert proc.returncode == 1 and f"is {state}" in proc.stderr
    log = subprocess.run(
        ["git", "-C", str(tree), "log", "--oneline"], capture_output=True, text=True, check=True
    )
    assert "checkpoint" not in log.stdout


@pytest.mark.parametrize(("value", "flag"), [("1", True), (None, False)])
def test_without_a_crew_the_allow_bypass_variable_adds_the_flag(tmp_path, value, flag):
    """Red arm: in a repo without a crew, WE_WORKER_ALLOW_BYPASS=1 adds the flag; unset, it does not."""
    project, env = setup(tmp_path, crew=None)
    if value:
        env["WE_WORKER_ALLOW_BYPASS"] = value
    run(project, env, "AC-12-impl", "--bg", GO)
    (call,) = started(tmp_path)
    assert (FLAG in call["argv"]) is flag


def test_a_crew_value_wins_over_the_allow_bypass_variable(tmp_path):
    project, env = setup(tmp_path, crew={**CREW, "launch": {"allow_bypass": False}})
    env["WE_WORKER_ALLOW_BYPASS"] = "1"
    run(project, env, "AC-12-impl", "--bg", GO)
    (call,) = started(tmp_path)
    assert FLAG not in call["argv"]


def test_a_permission_mode_with_equals_wins_too(tmp_path):
    project, env = setup(tmp_path, crew={**CREW, "launch": {"worker_mode": "bypass"}})
    run(project, env, "AC-12-impl", "--bg", "--permission-mode=plan", GO)
    (call,) = started(tmp_path)
    assert "bypassPermissions" not in call["argv"] and "--permission-mode=plan" in call["argv"]


def test_checkpoint_refuses_a_background_worker_blocked_on_a_prompt(tmp_path):
    """Red arm: a background row blocked on a prompt says `idle` in status, `blocked` in state."""
    tree = _checkpoint_tree(tmp_path, "feat/x")
    rows = [
        {
            "id": "ab1",
            "name": "w",
            "kind": "background",
            "pid": 1,
            "status": "idle",
            "state": "blocked",
            "cwd": str(tree),
        }
    ]
    project, env = setup(tmp_path, rows)
    proc = run(project, env, "checkpoint", "w")
    assert proc.returncode == 1 and "is blocked" in proc.stderr


def _wip_tree(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    tree = _checkpoint_tree(tmp_path, "feat/AC-12-slug")
    subprocess.run(["git", "-C", str(tree), "remote", "add", "origin", str(origin)], check=True)
    rows = [{"id": "ab12", "name": "w", "kind": "background", "pid": 1, "cwd": str(tree)}]
    project, env = setup(tmp_path, rows)
    env.update(
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@t",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@t",
    )
    return origin, tree, project, env


def _shown(origin, path):
    return subprocess.run(
        ["git", "--git-dir", str(origin), "show", f"wip/AC-12-slug:{path}"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_checkpoint_leaves_a_staged_new_file_out(tmp_path):
    """Red arm: `git add secret.env` before the pause stays local; only tracked changes go."""
    origin, tree, project, env = _wip_tree(tmp_path)
    (tree / "secret.env").write_text("X=1\n")
    subprocess.run(["git", "-C", str(tree), "add", "secret.env"], check=True)
    proc = run(project, env, "checkpoint", "w")
    assert proc.returncode == 0, proc.stderr
    assert _shown(origin, "a.txt").stdout == "two\n"
    assert _shown(origin, "secret.env").returncode != 0
    assert "secret.env" in proc.stdout


def test_checkpoint_without_a_tracked_change_pushes_the_commits(tmp_path):
    origin, tree, project, env = _wip_tree(tmp_path)
    subprocess.run(["git", "-C", str(tree), "checkout", "-q", "a.txt"], check=True)
    proc = run(project, env, "checkpoint", "w")
    assert proc.returncode == 0 and "no tracked change" in proc.stdout
    assert _shown(origin, "a.txt").stdout == "one\n"


def test_checkpoint_refuses_a_detached_head_and_a_failed_push(tmp_path):
    _origin, tree, project, env = _wip_tree(tmp_path)
    head = subprocess.run(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    subprocess.run(["git", "-C", str(tree), "checkout", "-q", "--detach", head], check=True)
    proc = run(project, env, "checkpoint", "w")
    assert proc.returncode == 1 and "detached HEAD" in proc.stderr
    subprocess.run(["git", "-C", str(tree), "checkout", "-q", "feat/AC-12-slug"], check=True)
    subprocess.run(
        ["git", "-C", str(tree), "remote", "set-url", "origin", str(tmp_path / "gone")], check=True
    )
    proc = run(project, env, "checkpoint", "w")
    assert proc.returncode == 1 and "push of wip/AC-12-slug failed" in proc.stderr


def test_checkpoint_names_a_failed_commit_and_pushes_nothing(tmp_path):
    origin, tree, project, env = _wip_tree(tmp_path)
    hook = tree / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    proc = run(project, env, "checkpoint", "w")
    assert proc.returncode == 1 and "checkpoint commit" in proc.stderr
    assert _shown(origin, "a.txt").returncode != 0


def test_a_marker_counts_only_for_the_session_it_names(tmp_path):
    """Red arm: a master sitting in a worker's tree is no worker because the tree has a marker."""
    tree = _checkpoint_tree(tmp_path, "feat/x")
    gd = subprocess.run(
        ["git", "-C", str(tree), "rev-parse", "--absolute-git-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    Path(gd, "we-worker.json").write_text(json.dumps({"name": "w"}))
    rows = [
        {"id": "m1", "name": "lead", "kind": "interactive", "pid": "-", "cwd": str(tree)},
        {"sessionId": "s-w", "name": "w", "kind": "interactive", "pid": "-", "cwd": str(tree)},
    ]
    project, env = setup(tmp_path, rows)
    assert run(project, env, "is-worker", "m1").returncode == 1
    # an interactive row has no id: its sessionId resolves it
    assert run(project, env, "is-worker", "s-w").returncode == 0


def test_an_unreadable_claude_help_refuses_no_flag(tmp_path):
    """Fail-open by design: without claude's own help nothing is refused (and nothing is named)."""
    project, env = setup(tmp_path)
    env["STUB_NO_HELP"] = "1"
    proc = run(project, env, "AC-12-impl", "--bg", "--cwd", GO)
    assert proc.returncode == 0, proc.stderr
    (call,) = started(tmp_path)
    assert "--cwd" in call["argv"]


def test_stop_never_ends_a_reused_pid(tmp_path):
    """Red arm: a descendant pid read before the stop that runs another command by the kill (the
    pid was reused) is left alone. A stub `ps` reports another command for that pid."""
    worker, child = _fake_worker()
    try:
        rows = [
            {"id": "ab12", "name": "w", "kind": "background", "pid": worker.pid, "sessionId": "s"}
        ]
        project, env = setup(tmp_path, rows)
        real = shutil.which("ps")
        stub = tmp_path / "bin" / "ps"
        stub.write_text(
            "#!/usr/bin/env bash\n"
            f'if [ "$*" = "-o comm= -p {child}" ]; then echo postgres; exit 0; fi\n'
            f'exec {real} "$@"\n'
        )
        stub.chmod(0o755)
        proc = run(project, env, "stop", "w")
        assert proc.returncode == 0, proc.stderr
        assert "also ended" not in proc.stdout
        assert subprocess.run(["kill", "-0", str(child)], check=False).returncode == 0
    finally:
        worker.kill()
        subprocess.run(["kill", str(child)], capture_output=True, check=False)


def test_a_window_worker_whose_tree_path_holds_a_space_is_still_a_worker(tmp_path):
    """Review: fields are tab-separated, so a space in the cwd keeps the marker check right."""
    tree = tmp_path / "my tree"
    subprocess.run(["git", "init", "-q", "-b", "feat/x", str(tree)], check=True)
    gd = subprocess.run(
        ["git", "-C", str(tree), "rev-parse", "--absolute-git-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    Path(gd, "we-worker.json").write_text(json.dumps({"name": "w"}))
    rows = [{"sessionId": "s-w", "name": "w", "kind": "interactive", "pid": "-", "cwd": str(tree)}]
    project, env = setup(tmp_path, rows)
    assert run(project, env, "is-worker", "w").returncode == 0
