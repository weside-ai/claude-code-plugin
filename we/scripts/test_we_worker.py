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
GO = "## Goal\n\nThe hook denies the never-list.\n\n## Output\n\nOne commit, the report.\n"

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
                         "key": os.environ.get("WE_STORY_KEY"), "cwd": os.getcwd(),
                         "queue_turn": os.environ.get("WE_WORKER_QUEUE_TURN")}) + "\n")
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
if sys.argv[1:2] == ["list-windows"]:
    for w in filter(None, os.environ.get("STUB_WINDOWS", "").split(",")):
        print(w)
"""


CSWAP_STUB = r"""#!/usr/bin/env python3
import json, os
pct = float(os.environ.get("STUB_CSWAP_PCT", "10"))
print(json.dumps({"active": {"usage": {"fiveHour": {"pct": pct}}}}))
"""


def setup(tmp_path, rows=(), crew=CREW):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    (bindir / "cswap").write_text(CSWAP_STUB)
    (bindir / "cswap").chmod(0o755)
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
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("TMUX", "WE_WORKER_TIMER", "WE_WORKER_ALLOW_BYPASS")
    }
    env.update(
        PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}",
        HOME=str(tmp_path / "home"),
        STUB_STATE=str(state),
        STUB_LOG=str(tmp_path / "log.jsonl"),
        CLAUDE_CONFIG_DIR=str(tmp_path / "pinned"),
        WESIDE_COMPANION="Ada",
        WE_WORKER_NO_SUPERVISOR="1",
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
            "cwd": "/work/AC-12",
        }
    ]
    project, env = setup(tmp_path, rows)
    proc = run(project, env, "AC-12-impl", "--bg", GO)
    assert proc.returncode == 2 and "already holds the name AC-12-impl" in proc.stderr
    assert "state working, tree /work/AC-12" in proc.stderr
    assert not started(tmp_path)


def test_a_name_held_by_a_living_window_worker_or_a_tmux_window_refuses(tmp_path):
    """A master started a second worker into the same worktree: the first one lived in a tmux
    window, which neither the guard nor status saw (red arm: the start went through)."""
    rows = [{"name": "PROJ-12-impl", "kind": "interactive", "pid": os.getpid(), "sessionId": "s1"}]
    project, env = setup(tmp_path, rows)
    proc = run(project, env, "PROJ-12-impl", "--bg", GO)
    assert proc.returncode == 2 and "already holds the name PROJ-12-impl" in proc.stderr
    (tmp_path / "w").mkdir()
    project, env = setup(tmp_path / "w")
    env["STUB_WINDOWS"] = "main:3 PROJ-12-impl"
    proc = run(project, env, "PROJ-12-impl", "--bg", GO)
    assert (
        proc.returncode == 2 and "tmux window main:3 is already named PROJ-12-impl" in proc.stderr
    )
    assert not started(tmp_path) and not started(tmp_path / "w")


def test_status_lists_a_window_worker_and_leaves_a_master_out(tmp_path):
    tree = tmp_path / "tree"
    subprocess.run(["git", "init", "-q", "-b", "feat/x", str(tree)], check=True)
    gd = subprocess.run(
        ["git", "-C", str(tree), "rev-parse", "--absolute-git-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    Path(gd, "we-worker.json").write_text(json.dumps({"name": "PROJ-12-impl"}))
    worker, master, started_as = (_detached_sleep(r) for r in (None, "master", "worker"))
    try:
        rows = [
            {
                "name": "PROJ-12-impl",
                "kind": "interactive",
                "pid": worker,
                "status": "idle",
                "sessionId": "s-w",
                "cwd": str(tree),
            },
            {
                "name": "master-12",
                "kind": "interactive",
                "pid": master,
                "status": "busy",
                "sessionId": "s-m",
                "cwd": str(tmp_path),
            },
            {
                "name": "PROJ-13-impl",
                "kind": "interactive",
                "pid": started_as,
                "status": "busy",
                "sessionId": "s-x",
                "cwd": str(tmp_path),
            },
        ]
        project, env = setup(tmp_path, rows)
        out = run(project, env, "status").stdout.splitlines()
    finally:
        for pid in (worker, master, started_as):
            subprocess.run(["kill", str(pid)], capture_output=True, check=False)
    assert out[:-1] == [
        f"s-w PROJ-12-impl pid={worker} idle last=- window",
        f"s-x PROJ-13-impl pid={started_as} busy last=- window",
    ]
    assert out[-1].startswith("room for both lanes: ")  # the machine's room, last


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
        ("--bg", "--agent", "we:dev-medium"),
        ("--bg", "## Goal\nx\n## Output\n"),
    ],
)
def test_any_brief_starts_without_a_warning_or_a_brake_line(tmp_path, args):
    """The brief's shape is not checked: no warning, no line in brakes.jsonl."""
    project, env = setup(tmp_path)
    proc = run(project, env, "AC-12-impl", *args)
    assert proc.returncode == 0, proc.stderr
    assert "warning" not in proc.stderr and "brief lacks" not in proc.stderr, proc.stderr
    assert started(tmp_path)
    assert brakes(tmp_path) == []


def brakes(tmp_path):
    log = tmp_path / "home" / ".claude" / "we-state" / "brakes.jsonl"
    return [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []


@pytest.mark.parametrize("blank", ["", "  \n\t"])
def test_a_blank_brief_refuses_before_claude(tmp_path, blank):
    """`we-worker <name> --bg "$(cat brief)"` after a refused command never wrote the file: the
    worker ran without a task until its master noticed. Red arm: it warned and started."""
    project, env = setup(tmp_path)
    proc = run(project, env, "AC-12-impl", "--bg", blank)
    assert proc.returncode == 2
    assert proc.stderr.startswith("we-worker: the brief is empty"), proc.stderr
    assert not started(tmp_path)


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


def test_the_worker_env_names_its_starter_as_answer_address(tmp_path):
    """A worker's question names `WE_STARTER` as the answer address (L0-worker): the starter outlives
    the worker, so a late answer still lands. Red arm: without it the env carries no starter."""
    project, env = setup(tmp_path)
    env["WE_WORKER_STARTER"] = "EPIC-1-master"
    assert run(project, env, "AC-12-impl", "--bg", GO).returncode == 0
    (call,) = started(tmp_path)
    doc = json.loads(Path(call["argv"][call["argv"].index("--settings") + 1]).read_text())
    assert doc["env"]["WE_STARTER"] == "EPIC-1-master"
    run(project, env, "AC-12-win", GO)
    (window,) = [c["tmux"] for c in calls(tmp_path) if c.get("tmux", [""])[0] == "new-window"]
    assert "WE_STARTER=EPIC-1-master" in window[-1]


def test_a_worker_knows_its_name_and_lane_for_its_signature_and_pool(tmp_path):
    """A worker signs its commits and PRs with `WE_WORKER_NAME` (the owner, 22.11.: "von wem ein
    PR ist"), and `--utility` reaches its settings file and window as `WE_WORKER_LANE`."""
    project, env = setup(tmp_path)
    env["WE_WORKER_STARTER"] = "EPIC-1-master"
    proc = run(project, env, "AC-12-fix", "--bg", "--utility", GO)
    assert proc.returncode == 0, proc.stderr
    (call,) = started(tmp_path)
    assert "--utility" not in call["argv"]
    doc = json.loads(Path(call["argv"][call["argv"].index("--settings") + 1]).read_text())
    assert {k: doc["env"][k] for k in ("WE_WORKER_NAME", "WE_WORKER_LANE", "WE_STARTER")} == {
        "WE_WORKER_NAME": "AC-12-fix",
        "WE_WORKER_LANE": "utility",
        "WE_STARTER": "EPIC-1-master",
    }
    run(project, env, "AC-12-win", "--utility", GO)
    (window,) = [c["tmux"] for c in calls(tmp_path) if c.get("tmux", [""])[0] == "new-window"]
    assert "WE_WORKER_NAME=AC-12-win WE_WORKER_LANE=utility" in window[-1]


def test_a_queued_utility_start_waits_in_its_own_lane_of_the_queue(tmp_path):
    """`we-worker --utility --queue` hands its lane to the queue: the entry carries `lane: utility`
    and its position counts only the utility lane, so a queued build start ahead holds it not."""
    busy = [{"id": f"b{i}", "name": f"S{i}", "status": "busy", "pid": 1} for i in range(8)]
    busy.append({"id": "u0", "name": "U-1-fix", "status": "busy", "pid": 1})
    project, env = setup(tmp_path, rows=busy)
    workers = tmp_path / "home/.claude/we-state/workers"
    workers.mkdir(parents=True, exist_ok=True)
    (workers / "pool.json").write_text(json.dumps({"max_utility_sessions": 1}))
    (workers / "U-1-fix.settings.json").write_text(
        json.dumps({"env": {"WE_WORKER_LANE": "utility"}})
    )
    proc = run(project, env, "AC-12-impl", "--bg", "--queue", GO)
    assert "queued (position 1 of the build lane" in proc.stdout, proc.stderr
    proc = run(project, env, "AC-12-fix", "--bg", "--utility", "--queue", GO)
    assert "queued (position 1 of the utility lane" in proc.stdout, proc.stderr
    entry = json.loads((workers / "queue" / "AC-12-fix.json").read_text())
    assert entry["lane"] == "utility"
    assert "lane=utility" in run(project, env, "status").stdout
    for name in ("AC-12-impl", "AC-12-fix"):
        assert run(project, env, "stop", name).returncode == 0
    assert not started(tmp_path)


def test_a_start_without_room_waits_in_its_lane_without_queue(tmp_path):
    """Kiska (22.11.): six kills by the host's memory guard at 94 % working set; a build start
    the room rule halts is no refusal: it waits in the build queue without --queue."""
    project, env = setup(tmp_path)
    host = tmp_path / "host"
    group = host / "sys" / "fs" / "cgroup"
    group.mkdir(parents=True)
    (host / "proc" / "self").mkdir(parents=True)
    (host / "proc" / "self" / "cgroup").write_text("0::/\n")
    mib = 1024 * 1024
    (group / "memory.max").write_text("max\n")  # no limit: MemTotal is the ceiling
    (host / "proc" / "meminfo").write_text("MemTotal: 102400 kB\n")
    (group / "memory.current").write_text(f"{95 * mib}\n")
    (group / "memory.stat").write_text(f"file {10 * mib}\nshmem {1 * mib}\n")  # 86 %
    env["WE_WORKER_HOST_ROOT"] = str(host)
    proc = run(project, env, "AC-12-impl", "--bg", GO)
    assert proc.returncode == 0, proc.stderr
    assert "build lane waits for room on the machine: working set 86%" in proc.stderr
    assert "(needs < 84%)" in proc.stderr
    assert "queued (position 1 of the build lane" in proc.stdout
    status = run(project, env, "status").stdout.splitlines()
    assert status[-1].startswith("room for both lanes: starts wait: working set 86%")
    # the waiter's rerun without room hands the 4 back and queues no second entry
    queue = tmp_path / "home/.claude/we-state/workers/queue"
    entry = (queue / "AC-12-impl.json").read_text()
    rerun = run(project, {**env, "WE_WORKER_QUEUE_TURN": "AC-12-impl"}, "AC-12-impl", "--bg", GO)
    assert rerun.returncode == 4 and "queued (position" not in rerun.stdout, rerun.stderr
    assert sorted(p.name for p in queue.glob("*.json")) == ["AC-12-impl.json"]
    assert (queue / "AC-12-impl.json").read_text() == entry
    # no waiter runs (WE_WORKER_NO_SUPERVISOR): status names it, --restart-waiters starts one
    assert any(x.endswith(" dead waiter") for x in status)
    restarted = run(project, env, "status", "--restart-waiters").stdout
    assert "the waiter of the queued start AC-12-impl restarted" in restarted
    window = run(project, env, "AC-13-win", GO)  # a window cannot wait in the queue
    assert window.returncode == 4 and "start it with --bg" in window.stderr
    assert run(project, env, "stop", "AC-12-impl").returncode == 0
    assert not started(tmp_path)


def test_a_develop_brief_starts_without_the_ticketing_plugin(tmp_path):
    project, env = setup(tmp_path)
    (project / ".weside" / "config.json").write_text(json.dumps({"ticketing": {"tool": "jira"}}))
    plugins = tmp_path / "home" / ".claude" / "plugins"  # the global login's, not the pinned dir
    plugins.mkdir(parents=True)
    (plugins / "installed_plugins.json").write_text(
        json.dumps({"plugins": {"atlassian@claude-plugins-official": []}})
    )
    workers = tmp_path / "home" / ".claude" / "we-state" / "workers"
    assert run(project, env, "AC-12-impl", "--bg", "/we:develop AC-12").returncode == 0
    doc = json.loads((workers / "AC-12-impl.settings.json").read_text())
    assert doc["enabledPlugins"] == {"atlassian@claude-plugins-official": False}
    assert run(project, env, "AC-12-pr", "--bg", "/we:pr AC-12").returncode == 0
    assert "enabledPlugins" not in json.loads((workers / "AC-12-pr.settings.json").read_text())


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


@pytest.mark.skipif(not Path("/proc/locks").exists(), reason="the waiters come from /proc/locks")
def test_status_shows_a_worker_that_waits_on_the_test_slot(tmp_path):
    """Measured 21.11.: a bench held the slot 52 min while 5 workers waited; each counted as busy
    and did no work, and nothing showed it."""
    import fcntl  # noqa: PLC0415

    import slot_lock  # noqa: PLC0415

    lock = tmp_path / "tests.lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o666)
    fcntl.flock(fd, fcntl.LOCK_EX)
    code = f"import fcntl, os; fcntl.flock(os.open({str(lock)!r}, os.O_RDWR), fcntl.LOCK_EX)"
    worker = subprocess.Popen(["bash", "-c", f'python3 -c "{code}"; true'])
    other = subprocess.Popen(["sleep", "60"])
    try:
        rows = [
            {
                "id": "w1",
                "name": "AC-12-impl",
                "kind": "background",
                "pid": worker.pid,
                "state": "working",
                "sessionId": "s-1",
            },
            {
                "id": "w2",
                "name": "AC-13-impl",
                "kind": "background",
                "pid": other.pid,
                "state": "working",
                "sessionId": "s-2",
            },
        ]
        project, env = setup(tmp_path, rows)
        env["WESIDE_TESTS_LOCK"] = str(lock)
        for _ in range(50):
            if slot_lock.waiters(lock):
                break
            time.sleep(0.1)
        out = run(project, env, "status").stdout.splitlines()
        assert out[0] == f"w1 AC-12-impl pid={worker.pid} working last=- waits: test-slot"
        assert out[1] == f"w2 AC-13-impl pid={other.pid} working last=-"
    finally:
        worker.kill()
        other.kill()
        os.close(fd)


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
        settings = tmp_path / "home" / ".claude" / "we-state" / "workers" / "w.settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text("{}")
        # a stale queue entry of the same name (its waiter gone) never shields the living worker
        (settings.parent / "queue").mkdir()
        (settings.parent / "queue" / "w.json").write_text(json.dumps({"name": "w"}))
        proc = run(project, env, "stop", "w")
        assert proc.returncode == 0, proc.stderr
        assert "queued start of w removed" in proc.stdout
        assert f"w (ab12) stopped; also ended: {child} sleep" in proc.stdout
        assert not settings.exists()  # the stop clears the worker's settings file
        assert "session s; resume: we-worker w --bg --resume s" in proc.stdout
    finally:
        worker.kill()


def test_a_stopped_worker_resumes_by_name_after_it_left_the_agent_list(tmp_path):
    worker = subprocess.Popen(["sleep", "60"])
    try:
        rows = [{"id": "ab12", "name": "AC-12-impl", "kind": "background", "pid": worker.pid}]
        rows[0]["sessionId"] = "0f0e0d0c-aaaa-bbbb-cccc-000000000001"
        project, env = setup(tmp_path, rows)
        assert run(project, env, "stop", "AC-12-impl").returncode == 0  # the stub drops the row
        proc = run(project, env, "AC-12-impl", "--bg", "--resume", "AC-12-impl", GO)
        assert proc.returncode == 0, proc.stderr
        (call,) = started(tmp_path)
        assert call["argv"][-3:] == ["--resume", rows[0]["sessionId"], GO]
        proc = run(project, env, "AC-13-impl", "--bg", "--resume", "AC-13-impl", GO)
        assert proc.returncode == 2 and "no stopped worker of that name" in proc.stderr
    finally:
        worker.kill()


def test_a_stopped_worker_resumes_by_a_unique_prefix_of_its_session_id(tmp_path):
    """Red arm (21.11.): `we-worker --resume <short id>` found no stopped worker: only a name or a
    living row resolved. An ambiguous prefix is named, never guessed."""
    project, env = setup(tmp_path)
    state = tmp_path / "home/.claude/we-state/workers"
    state.mkdir(parents=True)
    kept = {
        "AC-12-impl": "4f1e2d3c-aaaa-bbbb-cccc-000000000001",
        "AC-13-impl": "4f1e9999-aaaa-bbbb-cccc-000000000002",
    }
    for name, sid in kept.items():
        (state / f"{name}.resume.json").write_text(json.dumps({"name": name, "session_id": sid}))
    proc = run(project, env, "AC-12-impl", "--bg", "--resume", "4f1e2d", GO)
    assert proc.returncode == 0, proc.stderr
    (call,) = started(tmp_path)
    assert call["argv"][-3:] == ["--resume", kept["AC-12-impl"], GO]
    proc = run(project, env, "AC-12-impl", "--bg", "--resume", "4f1e", GO)
    assert proc.returncode == 2 and "is ambiguous (2 sessions: " in proc.stderr
    assert kept["AC-12-impl"] in proc.stderr and kept["AC-13-impl"] in proc.stderr
    # a session whose files were aged out still has its transcript
    projects = tmp_path / "home/.claude/projects/-some-tree"
    projects.mkdir(parents=True)
    (projects / "9a8b7c6d-0000-1111-2222-333344445555.jsonl").write_text("{}\n")
    proc = run(project, env, "AC-14-impl", "--bg", "--resume", "9a8b7c", GO)
    assert proc.returncode == 0, proc.stderr
    assert started(tmp_path)[-1]["argv"][-2] == "9a8b7c6d-0000-1111-2222-333344445555"
    proc = run(project, env, "AC-15-impl", "--bg", "--resume", "deadbeef", GO)
    assert proc.returncode == 2 and "no session id starting with it" in proc.stderr
    assert len(started(tmp_path)) == 2


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
    assert "we-worker AC-12-impl --tree <tree>" in proc.stderr
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


def test_a_start_over_the_concurrency_cap_is_refused_and_starts_nothing(tmp_path):
    """Red arm: 14 usage-limit stops in 11 sessions within 13 minutes."""
    busy = [{"id": f"b{i}", "name": f"S{i}", "status": "busy", "pid": 1} for i in range(8)]
    project, env = setup(tmp_path, rows=busy)
    proc = run(project, env, "AC-12-impl", "--bg", GO)
    assert proc.returncode == 3
    assert (
        "we-worker: refused, no worker started: build lane: 8 workers busy (limit 8 for the"
        in (proc.stderr)
    )
    assert "active account 5h at 10 % (limit 80 %" in proc.stderr
    assert "add --queue" in proc.stderr
    assert not started(tmp_path)
    # with --queue the refused start waits in the state dir; status lists it, stop removes it
    proc = run(project, env, "AC-12-impl", "--bg", "--queue", "--queue-timeout", "90m", GO)
    assert proc.returncode == 0 and "AC-12-impl queued (position 1" in proc.stdout, proc.stderr
    entry = json.loads(
        (tmp_path / "home/.claude/we-state/workers/queue/AC-12-impl.json").read_text()
    )
    assert entry["argv"] == ["AC-12-impl", "--bg"]
    assert entry["deadline"] - entry["queued_at"] == 90 * 60
    assert entry["repo_limits"] == {}  # the repo lowers no pool limit
    status = run(project, env, "status").stdout
    assert "queued AC-12-impl position=1" in status
    assert run(project, env, "stop", "AC-12-impl").returncode == 0
    assert "queued" not in run(project, env, "status").stdout
    assert not started(tmp_path)
    # the limit is the machine's, in the state dir every repo shares
    (tmp_path / "home/.claude/we-state/workers/pool.json").write_text(
        json.dumps({"max_busy_sessions": 9})
    )
    assert run(project, env, "AC-12-impl", "--bg", GO).returncode == 0


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def git_setup(tmp_path):
    """`setup` with a real main checkout of a repo whose origin has `main`."""
    project, env = setup(tmp_path)
    shutil.rmtree(project / ".git")
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(project, "init", "-q", "-b", "main")
    _git(project, "add", ".")
    _git(project, "commit", "-q", "-m", "init")
    _git(project, "remote", "add", "origin", str(origin))
    _git(project, "push", "-q", "origin", "main")
    _git(project, "remote", "set-head", "origin", "main")
    return project, env


def _marker(tree):
    return json.loads(
        Path(_git(tree, "rev-parse", "--absolute-git-dir"), "we-worker.json").read_text()
    )


def _tree_mode(project, mode):
    (project / ".weside" / "config.json").write_text(json.dumps({"workers": {"tree": mode}}))


def test_under_tree_own_a_build_start_in_the_main_checkout_lands_in_a_new_worktree(tmp_path):
    project, env = git_setup(tmp_path)
    _tree_mode(project, "own")
    proc = run(project, env, "AC-12-impl", "--bg", GO)
    assert proc.returncode == 0, proc.stderr
    tree = tmp_path / "project-AC-12-impl"
    (call,) = started(tmp_path)
    assert call["cwd"] == str(tree) and f"works in {tree}" in proc.stdout
    assert _git(tree, "branch", "--show-current") == "feat/AC-12-impl"
    assert _git(project, "branch", "--show-current") == "main"
    marker = _marker(tree)
    assert {k: marker[k] for k in ("name", "key", "role", "tree", "mode")} == {
        "name": "AC-12-impl",
        "key": "AC-12",
        "role": "worker",
        "tree": str(tree),
        "mode": "bg",
    }
    again = run(project, env, "AC-12-impl", "--bg", GO)
    assert again.returncode == 2 and f"--tree {tree}" in again.stderr
    _git(project, "branch", "feat/AC-12-left")  # a branch left after its tree went: add fails
    left = run(project, env, "AC-12-left", "--bg", GO)
    assert left.returncode == 2 and "no worker started" in left.stderr
    assert len(started(tmp_path)) == 1  # never a start in the main checkout


def test_a_queued_start_from_the_main_checkout_gets_its_own_tree_under_caller(
    tmp_path, monkeypatch
):
    """Red arm (21.11.): a queued infra start ran in the shared checkout (`workers.tree: caller`)
    because the waiter only replays the call. A queued start now gets its own worktree, and its
    queue turn never reaches the worker's environment."""
    import worker_supervisor as sup  # noqa: PLC0415

    project, env = git_setup(tmp_path)
    _tree_mode(project, "caller")
    Path(env["STUB_STATE"]).write_text(
        json.dumps(
            [{"id": f"b{i}", "name": f"S{i}", "status": "busy", "pid": 1} for i in range(8)]
        )
    )
    proc = run(project, env, "AC-12-impl", "--bg", "--queue", GO)
    assert proc.returncode == 0 and "queued (position 1" in proc.stdout, proc.stderr
    doc = json.loads(
        (tmp_path / "home/.claude/we-state/workers/queue/AC-12-impl.json").read_text()
    )
    Path(env["STUB_STATE"]).write_text("[]")  # room now
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    code, out = sup.start_queued(doc)
    assert code == 0, out
    tree = tmp_path / "project-AC-12-impl"
    (call,) = started(tmp_path)
    assert call["cwd"] == str(tree), out
    assert "workers.tree: caller" not in out
    assert _git(project, "branch", "--show-current") == "main"
    assert call["queue_turn"] is None
    # T2 panel on #308: a --queue start that passes the check at once gets its own tree too
    proc = run(project, env, "AC-13-now", "--bg", "--queue", GO)
    assert proc.returncode == 0 and "queued (position" not in proc.stdout, proc.stderr
    now = tmp_path / "project-AC-13-now"
    assert started(tmp_path)[-1]["cwd"] == str(now) and f"works in {now}" in proc.stdout
    assert _git(project, "branch", "--show-current") == "main"


def test_here_a_linked_worktree_and_tree_choose_the_tree_without_creating_one(tmp_path):
    project, env = git_setup(tmp_path)
    assert run(project, env, "AC-12-probe", "--here", "--bg", GO).returncode == 0
    linked = tmp_path / "linked"
    _git(project, "worktree", "add", "-q", "-b", "feat/linked", str(linked))
    assert run(linked, env, "AC-12-legacy", "--bg", GO).returncode == 0
    assert not Path(_git(linked, "rev-parse", "--absolute-git-dir"), "we-worker.json").exists()
    proc = run(project, env, "AC-12-fix", "--tree", str(linked), "--bg", GO)
    assert proc.returncode == 0, proc.stderr
    assert [c["cwd"] for c in started(tmp_path)] == [str(project), str(linked), str(linked)]
    assert _git(project, "worktree", "list").count("\n") == 1  # main checkout and linked only
    assert _marker(linked)["name"] == "AC-12-fix"
    main = run(linked, env, "AC-12-back", "--tree", str(project), "--bg", GO)
    assert main.returncode == 2 and "--here" in main.stderr


def test_under_tree_caller_a_start_in_the_main_checkout_stays_there_with_a_tip(tmp_path):
    project, env = git_setup(tmp_path)
    _tree_mode(project, "caller")
    proc = run(project, env, "AC-12-impl", "--bg", GO)
    assert proc.returncode == 0, proc.stderr
    assert "works in the main checkout" in proc.stderr and "workers.tree: own" in proc.stderr
    assert [c["cwd"] for c in started(tmp_path)] == [str(project)]
    assert not (tmp_path / "project-AC-12-impl").exists()
    assert not Path(_git(project, "rev-parse", "--absolute-git-dir"), "we-worker.json").exists()


@pytest.mark.parametrize(
    "needs, refused",
    [
        ("Needs: sentry, `supabase`", "supabase@claude-plugins-official"),  # a disabled plugin
        ("Needs: playwright", "playwright"),  # a denied MCP server
        ("Needs: sentry", None),
    ],
)
def test_a_brief_that_needs_a_tool_the_context_turns_off_refuses(tmp_path, needs, refused):
    project, env = setup(tmp_path)
    context = {
        "disable_plugins": ["supabase@claude-plugins-official"],
        "deny_mcp_servers": ["playwright"],
    }
    (project / ".weside" / "config.json").write_text(json.dumps({"workers": {"context": context}}))
    proc = run(project, env, "AC-12-impl", "--bg", f"{GO}\n{needs}\n")
    if refused is None:
        assert proc.returncode == 0, proc.stderr
        return
    assert proc.returncode == 2 and f"turns off ({refused})" in proc.stderr
    assert not started(tmp_path)


def test_a_brief_naming_a_skill_whose_ticketing_plugin_is_off_refuses(tmp_path):
    project, env = setup(tmp_path)
    config = {
        "ticketing": {"tool": "jira"},
        "workers": {"context": {"disable_plugins": ["atlassian@claude-plugins-official"]}},
    }
    (project / ".weside" / "config.json").write_text(json.dumps(config))
    proc = run(project, env, "AC-12-refine", "--bg", f"{GO}\nRun Skill we:plan-story for AC-12.\n")
    assert proc.returncode == 2
    assert "/we:plan-story" in proc.stderr and "atlassian@claude-plugins-official" in proc.stderr
    assert not started(tmp_path)


def test_a_crew_member_started_in_the_background_is_no_worker(tmp_path):
    """`start.py launch` starts a member with `claude --bg`; its settings file sets WE_ROLE=master."""
    rows = [{"id": "m1", "name": "Ada", "kind": "background", "pid": "-", "cwd": "-"}]
    project, env = setup(tmp_path, rows)
    state = tmp_path / "workers"
    env["WE_WORKER_STATE_DIR"] = str(state)
    state.mkdir(parents=True, exist_ok=True)
    (state / "Ada.settings.json").write_text(json.dumps({"env": {"WE_ROLE": "master"}}))
    assert run(project, env, "is-worker", "m1").returncode == 1
    (state / "Ada.settings.json").write_text(json.dumps({"env": {"WE_ROLE": "worker"}}))
    assert run(project, env, "is-worker", "m1").returncode == 0


ACCOUNTS_STUB = r"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
need = args[args.index("--need") + 1]
name = args[args.index("--account") + 1] if "--account" in args else None
with open(os.environ["STUB_LOG"], "a") as fh:
    fh.write(json.dumps({"argv": [], "accounts": args}) + "\n")
if os.environ.get("STUB_ACCOUNT_KIND"):
    kind = os.environ["STUB_ACCOUNT_KIND"]
else:
    kind = "claude" if need == "critical" else "other-llm"
print(json.dumps({"name": name or f"{need}-pick", "kind": kind,
                  "env": {"ANTHROPIC_BASE_URL": f"https://{need}.example"},
                  "token_command": "vault-helper read pick", "quota": {"5h": 12}}))
"""


def accounts_setup(tmp_path, command=True):
    project, env = setup(tmp_path)
    stub = tmp_path / "bin" / "accounts"
    stub.write_text(ACCOUNTS_STUB)
    stub.chmod(0o755)
    (project / ".weside").mkdir(exist_ok=True)
    config = {"agents": {"accounts_command": f"{stub} --from-test"}} if command else {}
    (project / ".weside" / "config.json").write_text(json.dumps(config))
    return project, env


def settings_of(tmp_path):
    (call,) = started(tmp_path)
    return json.loads(Path(call["argv"][call["argv"].index("--settings") + 1]).read_text())


def test_account_auto_puts_the_critical_claude_account_into_the_settings(tmp_path):
    project, env = accounts_setup(tmp_path)
    proc = run(project, env, "AC-12-impl", "--bg", "--account", "auto", GO)
    assert proc.returncode == 0, proc.stderr
    assert "runs on account critical-pick (claude, critical" in proc.stdout
    (asked,) = [c["accounts"] for c in calls(tmp_path) if "accounts" in c]
    assert asked == ["--from-test", "--need", "critical"]
    doc = settings_of(tmp_path)
    assert doc["env"]["ANTHROPIC_BASE_URL"] == "https://critical.example"
    assert doc["env"]["WE_ROLE"] == "worker"
    assert doc["apiKeyHelper"] == "vault-helper read pick"
    # the helper command and the env stay in the file, off the command line
    (call,) = started(tmp_path)
    assert not any("vault-helper" in a or "example" in a for a in call["argv"])
    assert not list(
        (tmp_path / "home" / ".claude" / "we-state" / "workers").glob("*.account.json")
    )


def test_an_uncritical_brief_may_land_on_another_llm(tmp_path):
    project, env = accounts_setup(tmp_path)
    brief = GO + "\nAccount: uncritical\n"
    proc = run(project, env, "AC-12-impl", "--bg", "--account=auto", brief)
    assert proc.returncode == 0, proc.stderr
    (asked,) = [c["accounts"] for c in calls(tmp_path) if "accounts" in c]
    assert asked[-2:] == ["--need", "uncritical"]
    assert settings_of(tmp_path)["env"]["ANTHROPIC_BASE_URL"] == "https://uncritical.example"


def test_a_named_account_passes_through_to_the_command(tmp_path):
    project, env = accounts_setup(tmp_path)
    proc = run(project, env, "AC-12-impl", "--bg", "--account", "backup", GO)
    assert proc.returncode == 0, proc.stderr
    (asked,) = [c["accounts"] for c in calls(tmp_path) if "accounts" in c]
    assert asked == ["--from-test", "--need", "critical", "--account", "backup"]


def test_a_critical_worker_on_a_non_claude_account_refuses(tmp_path):
    project, env = accounts_setup(tmp_path)
    env["STUB_ACCOUNT_KIND"] = "other-llm"
    proc = run(project, env, "AC-12-impl", "--bg", "--account", "auto", GO)
    assert proc.returncode == 2
    assert "critical worker runs only on a claude account" in proc.stderr
    assert "no worker started" in proc.stderr
    assert started(tmp_path) == []


def test_account_without_the_option_refuses(tmp_path):
    project, env = accounts_setup(tmp_path, command=False)
    proc = run(project, env, "AC-12-impl", "--bg", "--account", "auto", GO)
    assert proc.returncode == 2
    assert "agents.accounts_command is not set" in proc.stderr
    assert started(tmp_path) == []


def test_without_account_the_command_is_never_asked(tmp_path):
    project, env = accounts_setup(tmp_path)
    proc = run(project, env, "AC-12-impl", "--bg", GO)
    assert proc.returncode == 0, proc.stderr
    assert not [c for c in calls(tmp_path) if "accounts" in c]
    doc = settings_of(tmp_path)
    assert "apiKeyHelper" not in doc and "ANTHROPIC_BASE_URL" not in doc["env"]


# --- the brief survives queue and resume -------------------------------------------------------


def _hook_brief(call, tmp_path):
    """The brief file the worker's SessionStart hook names, run as the hook runs it."""
    doc = json.loads(Path(call["argv"][call["argv"].index("--settings") + 1]).read_text())
    commands = [h["command"] for g in doc["hooks"]["SessionStart"] for h in g["hooks"]]
    out = [
        subprocess.run(["sh", "-c", c], capture_output=True, text=True, check=True).stdout
        for c in commands
    ]
    texts = [json.loads(o)["hookSpecificOutput"]["additionalContext"] for o in out if o.strip()]
    (named,) = [t for t in texts if "your brief is the file" in t]
    path = Path(named.split("your brief is the file ")[1].split(". If")[0])
    return path.read_text()


@pytest.mark.parametrize("args", [("--bg",), ("--bg", "--queue")])
def test_a_background_start_without_a_brief_refuses_before_claude(tmp_path, args):
    """In the background nobody hands the task in later: the worker would idle until someone
    notices. Red arm: it started."""
    project, env = setup(tmp_path)
    proc = run(project, env, "AC-12-impl", *args)
    assert proc.returncode == 2 and "no brief" in proc.stderr, proc.stderr
    assert not started(tmp_path)
    assert not (tmp_path / "home/.claude/we-state/workers/queue/AC-12-impl.json").exists()


def test_a_window_start_without_a_brief_still_opens(tmp_path):
    """A window worker may start empty: a human types its task there, as on main."""
    project, env = setup(tmp_path)
    proc = run(project, env, "AC-12-impl")
    assert proc.returncode == 0, proc.stderr
    (window,) = [c["tmux"] for c in calls(tmp_path) if c.get("tmux", [""])[0] == "new-window"]
    assert "AC-12-impl" in window[-1]


def test_a_queued_start_hands_its_brief_to_claude_and_to_the_start_hook(tmp_path, monkeypatch):
    """Measured 20.11.: a queued start ran without its brief; the waiter told the starter at once
    and the starter's SendMessage reached the new session before its start prompt. Red arm: the
    brief existed only as the prompt argument, the hook named no file."""
    import worker_supervisor as sup  # noqa: PLC0415 (beside the script, as the waiter runs it)

    busy = [{"id": f"b{i}", "name": f"S{i}", "status": "busy", "pid": 1} for i in range(10)]
    project, env = setup(tmp_path, rows=busy)
    brief = "# Brief\n\nDo the cswap thing.\n"
    proc = run(project, env, "AC-12-impl", "--bg", "--queue", brief)
    assert proc.returncode == 0, proc.stderr
    state = tmp_path / "home/.claude/we-state/workers"
    doc = json.loads((state / "queue/AC-12-impl.json").read_text())
    Path(env["STUB_STATE"]).write_text("[]")  # room now
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    code, out = sup.start_queued(doc)
    assert code == 0, out
    (call,) = started(tmp_path)
    assert call["argv"][-1] == brief
    assert _hook_brief(call, tmp_path) == brief


def test_a_resume_passes_its_prompt_and_the_start_hook_names_it(tmp_path):
    """Measured 20.11.: `we-worker <n> --tree … --bg --resume <id> "<prompt>"` started without the
    prompt. Red arm: the prompt lived only in the argument."""
    project, env = setup(tmp_path)
    sid = "0123abcd-0000-0000-0000-000000000000"
    proc = run(project, env, "AC-12-impl", "--bg", "--resume", sid, "go on with phase 2")
    assert proc.returncode == 0, proc.stderr
    (call,) = started(tmp_path)
    assert call["argv"][-3:] == ["--resume", sid, "go on with phase 2"]
    assert _hook_brief(call, tmp_path) == "go on with phase 2\n"


def test_a_resume_without_a_prompt_writes_no_brief(tmp_path):
    """The resume id is the session, not a task: no brief file, no brief hook."""
    project, env = setup(tmp_path)
    sid = "0123abcd-0000-0000-0000-000000000000"
    assert run(project, env, "AC-12-impl", "--bg", "--resume", sid).returncode == 0
    (call,) = started(tmp_path)
    doc = json.loads(Path(call["argv"][call["argv"].index("--settings") + 1]).read_text())
    hooks = [
        h["command"] for g in (doc.get("hooks") or {}).get("SessionStart", []) for h in g["hooks"]
    ]
    assert not any("your brief is the file" in c for c in hooks)
    assert not (tmp_path / "home/.claude/we-state/workers/AC-12-impl.brief.md").exists()


def test_stop_removes_the_brief_file_with_the_settings(tmp_path):
    """`we-worker stop` takes `<name>.brief.md` with the settings file."""
    project, env = setup(
        tmp_path, rows=[{"id": "bg1", "name": "AC-12-impl", "kind": "background", "pid": 999999}]
    )
    state = tmp_path / "home/.claude/we-state/workers"
    state.mkdir(parents=True)
    for suffix in ("settings.json", "brief.md"):
        (state / f"AC-12-impl.{suffix}").write_text("x")
    assert run(project, env, "stop", "AC-12-impl").returncode == 0
    assert not (state / "AC-12-impl.brief.md").exists()
    assert not (state / "AC-12-impl.settings.json").exists()


def test_every_start_lands_in_the_starter_log(tmp_path):
    """A start without a marker (the caller's tree) still leaves its line with the starter."""
    project, env = setup(tmp_path)
    env["WE_WORKER_STARTER"] = "EPIC-1-master"
    env["CLAUDE_CODE_SESSION_ID"] = "sess-starter"
    assert run(project, env, "AC-12-impl", "--bg", GO).returncode == 0
    log = tmp_path / "home/.claude/we-state/workers/launched.jsonl"
    (line,) = [json.loads(x) for x in log.read_text().splitlines()]
    assert line["name"] == "AC-12-impl" and line["key"] == "AC-12"
    assert line["starter"] == "EPIC-1-master" and line["starter_session"] == "sess-starter"
