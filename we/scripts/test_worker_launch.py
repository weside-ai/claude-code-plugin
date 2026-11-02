"""worker_launch.py against a real git worktree and a stub `claude` on PATH."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import worker_launch as wl

SCRIPT = Path(__file__).parent / "worker_launch.py"

# A stub `claude`: `agents --json` prints the rows in $STUB_STATE, `stop <id>` drops that row,
# `--bg -n <name> …` adds a row for its cwd. Every call is logged to $STUB_LOG.
STUB = r"""#!/usr/bin/env python3
import json, os, sys
state = os.environ["STUB_STATE"]
rows = json.load(open(state))
with open(os.environ["STUB_LOG"], "a") as fh:
    fh.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}) + "\n")
args = sys.argv[1:]
if args[:2] == ["agents", "--json"]:
    print(json.dumps(rows)); sys.exit(0)
if args[:1] == ["stop"]:
    if os.environ.get("STUB_STOP_FAILS"): sys.exit(5)
    if not os.environ.get("STUB_STOP_IGNORED"):
        rows = [r for r in rows if r["id"] != args[1]]
    json.dump(rows, open(state, "w")); sys.exit(0)
if "--bg" in args:
    if os.environ.get("STUB_LAUNCH_FAILS"): print("boom", file=sys.stderr); sys.exit(7)
    name = args[args.index("-n") + 1]
    rows.append({"id": "bg" + str(len(rows)), "name": name, "cwd": os.getcwd(),
                 "sessionId": "s-" + name, "kind": "background", "pid": 1})
    json.dump(rows, open(state, "w")); print("bg started"); sys.exit(0)
sys.exit(9)
"""

TEMPLATE = "claude --bg -n {name} --agent {agent} {brief}"


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture
def env(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(
        repo,
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "init",
    )
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", "-b", "feat/x", str(wt))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "claude"
    stub.write_text(STUB)
    stub.chmod(0o755)
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            [
                {
                    "id": "lead0",
                    "name": "LEAD-1",
                    "sessionId": "s-lead",
                    "cwd": str(repo),
                    "kind": "interactive",
                    "pid": 1,
                }
            ]
        )
    )
    log = tmp_path / "log.jsonl"
    log.touch()
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("STUB_STATE", str(state))
    monkeypatch.setenv("STUB_LOG", str(log))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s-lead")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    brief = tmp_path / "brief.md"
    brief.write_text('Run Skill("we:develop") for KEY.\n')

    def configure(value):
        (wt / ".weside").mkdir(exist_ok=True)
        cfg = {} if value is None else {"agents": {"worker_launch": value}}
        (wt / ".weside" / "config.json").write_text(json.dumps(cfg))

    return {
        "repo": repo,
        "wt": wt,
        "state": state,
        "log": log,
        "brief": brief,
        "configure": configure,
    }


def _run(*args, capture=True):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=capture, text=True, check=False
    )


def _launch_call(env):
    return next(c for c in _calls(env) if "--bg" in c["argv"])


def _calls(env):
    return [json.loads(line) for line in env["log"].read_text().splitlines()]


def _rows(env):
    return json.loads(env["state"].read_text())


def test_backend_defaults_to_subagent(env, tmp_path):
    assert wl.backend(env["wt"]) == wl.SUBAGENT  # no config file
    env["configure"](None)
    assert wl.backend(env["wt"]) == wl.SUBAGENT  # no key
    env["configure"]("subagent")
    out = _run("backend", "--repo", str(env["wt"]))
    assert (out.returncode, out.stdout.strip()) == (0, "subagent")


@pytest.mark.parametrize(
    ("template", "message"),
    [
        ("x {name} {brief} {model}", "unknown placeholder {model}"),
        ("x {name}", "placeholder {brief} is required"),
        ("x --n={name} {brief}", "must be a token of its own"),
        ("x 'unterminated {name} {brief}", "cannot split"),
    ],
)
def test_invalid_template_refuses_and_launches_nothing(env, template, message):
    env["configure"](template)
    out = _run("backend", "--repo", str(env["wt"]))
    assert out.returncode == 2 and message in out.stderr
    out = _run(
        "launch", "--worktree", str(env["wt"]), "--name", "w1", "--brief-file", str(env["brief"])
    )
    assert out.returncode == 2 and message in out.stderr
    assert not any("--bg" in c["argv"] for c in _calls(env))


def test_launch_writes_brief_and_marker_and_runs_in_the_worktree(env):
    env["configure"](TEMPLATE)
    out = _run(
        "launch",
        "--worktree",
        str(env["wt"]),
        "--name",
        "w1",
        "--agent",
        "we:dev-medium",
        "--brief-file",
        str(env["brief"]),
    )
    assert out.returncode == 0, out.stderr
    gd = wl.git_dir(env["wt"])
    brief = (gd / wl.BRIEF).read_text()
    assert brief.startswith("Lead: LEAD-1 — ") and 'Run Skill("we:develop") for KEY.' in brief
    marker = wl.read_marker(env["wt"])
    assert marker["name"] == "w1" and marker["lead"] == "LEAD-1"
    assert marker["agent"] == "we:dev-medium" and marker["launched_at"] > 0
    assert marker["session_id"] == "s-w1"
    launch = _launch_call(env)
    assert launch["argv"] == [
        "--bg",
        "-n",
        "w1",
        "--agent",
        "we:dev-medium",
        f"Read {gd / wl.BRIEF} and follow it.",
    ]
    assert Path(launch["cwd"]).resolve() == env["wt"].resolve()
    assert [r["cwd"] for r in _rows(env) if r["name"] == "w1"] == [launch["cwd"]]
    timing = list((Path(os.environ["HOME"]) / ".claude" / "we-timing").glob("*.jsonl"))
    assert json.loads(timing[0].read_text().splitlines()[0])["event"] == "WorkerLaunch"


def test_agent_placeholder_needs_an_agent(env):
    env["configure"](TEMPLATE)
    with pytest.raises(wl.LaunchError, match="pass --agent") as exc:
        wl.launch(env["wt"], "w2", env["brief"])
    assert exc.value.code == 2 and wl.read_marker(env["wt"]) is None
    env["configure"]("claude --bg -n {name} {brief}")
    wl.launch(env["wt"], "w2", env["brief"])
    assert _launch_call(env)["argv"][:3] == ["--bg", "-n", "w2"]


def test_lead_in_the_worker_tree_is_no_worker(env):
    env["configure"](TEMPLATE)
    wl.launch(env["wt"], "w1", env["brief"], "we:dev-medium")
    assert wl.worker_marker({"cwd": str(env["wt"]), "session_id": "s-w1"})["name"] == "w1"
    assert wl.worker_marker({"cwd": str(env["wt"]), "session_id": "s-lead"}) is None
    assert wl.worker_marker({"cwd": str(env["wt"])}) is None


def test_unnamed_lead_refuses(env, monkeypatch):
    env["configure"]("claude --bg -n {name} {brief}")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s-unknown")
    with pytest.raises(wl.LaunchError, match="name this session first"):
        wl.launch(env["wt"], "w1", env["brief"])
    assert wl.read_marker(env["wt"]) is None
    assert not any("--bg" in c["argv"] for c in _calls(env))


def test_failed_launch_removes_its_files(env, monkeypatch):
    env["configure"]("claude --bg -n {name} {brief}")
    monkeypatch.setenv("STUB_LAUNCH_FAILS", "1")
    with pytest.raises(wl.LaunchError, match="exited 7: boom"):
        wl.launch(env["wt"], "w1", env["brief"])
    gd = wl.git_dir(env["wt"])
    assert not (gd / wl.MARKER).exists() and not (gd / wl.BRIEF).exists()


def test_launch_refuses_on_the_subagent_backend(env):
    with pytest.raises(wl.LaunchError, match="Agent\\(isolation"):
        wl.launch(env["wt"], "w1", env["brief"])


def test_stop_and_alive(env):
    env["configure"](TEMPLATE)
    wl.launch(env["wt"], "w1", env["brief"], "we:dev-medium")
    assert _run("alive", "--name", "w1").returncode == 0
    out = _run("stop", "--name", "w1", "--worktree", str(env["wt"]))
    assert out.returncode == 0, out.stderr
    assert ["stop", "bg1"] in [c["argv"] for c in _calls(env)]
    assert _run("alive", "--name", "w1").returncode == 1
    gd = wl.git_dir(env["wt"])
    assert not (gd / wl.MARKER).exists() and not (gd / wl.BRIEF).exists()
    out = _run("stop", "--name", "w1")
    assert out.returncode == 1 and "no running session named w1" in out.stderr


def test_stop_of_an_ended_session_clears_its_marker(env):
    env["configure"](TEMPLATE)
    wl.launch(env["wt"], "w1", env["brief"], "we:dev-medium")
    env["state"].write_text(json.dumps([r for r in _rows(env) if r["name"] != "w1"]))
    with pytest.raises(wl.LaunchError, match="no running session"):
        wl.stop("w1", env["wt"])
    assert wl.read_marker(env["wt"]) is None


def test_stop_reports_a_session_that_keeps_running(env, monkeypatch):
    env["configure"](TEMPLATE)
    wl.launch(env["wt"], "w1", env["brief"], "we:dev-medium")
    monkeypatch.setenv("STUB_STOP_IGNORED", "1")
    with pytest.raises(wl.LaunchError, match="still running") as exc:
        wl.stop("w1", wait_s=0)
    assert exc.value.code == 3


def test_read_marker_outside_a_repo_is_none(tmp_path):
    assert wl.read_marker(tmp_path) is None
    assert wl.read_marker(None) is None
