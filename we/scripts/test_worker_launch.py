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


def test_a_hanging_claude_agents_times_out(monkeypatch):
    seen = {}

    def hang(argv, **kwargs):
        seen.update(kwargs)
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(wl.subprocess, "run", hang)
    with pytest.raises(wl.LaunchError, match=r"claude agents --json timed out after 30 s"):
        wl.sessions()
    assert seen["timeout"] == wl.AGENTS_TIMEOUT_S


# --- one owner of the worker template: the crew's launch.worker -------------------------------


def _crew(env, launch):
    (env["wt"] / ".weside").mkdir(exist_ok=True)
    crew = {
        "version": 2,
        "roles": {"product": "po"},
        "members": {"po": {"name": "Ada"}},
        "launch": launch,
    }
    (env["wt"] / ".weside" / "crew.json").write_text(json.dumps(crew))


def test_the_crew_template_wins_and_a_differing_config_warns_once(env, capsys):
    env["configure"]("claude --bg -n {name} {brief}")
    _crew(env, {"worker": TEMPLATE})
    assert wl.backend(env["wt"]) == TEMPLATE
    err = capsys.readouterr().err
    assert err.count("launch.worker and agents.worker_launch differ; the crew wins") == 1


def test_equal_templates_do_not_warn(env, capsys):
    env["configure"](TEMPLATE)
    _crew(env, {"worker": TEMPLATE})
    assert wl.backend(env["wt"]) == TEMPLATE
    assert "differ" not in capsys.readouterr().err


def test_a_crew_without_launch_worker_falls_back_to_the_config(env):
    env["configure"](TEMPLATE)
    _crew(env, {"subagent_fallback": False})
    assert wl.backend(env["wt"]) == TEMPLATE


def test_an_invalid_crew_template_names_the_crew_key(env):
    _crew(env, {"worker": "claude --bg {name}"})
    with pytest.raises(wl.LaunchError, match=r"launch\.worker: placeholder \{brief\} is required"):
        wl.backend(env["wt"])


def test_stop_goes_through_the_we_worker_stop_verb(env, tmp_path):
    bindir = tmp_path / "bin"
    ww = bindir / "we-worker"
    ww.write_text(
        "#!/usr/bin/env python3\nimport json, os, sys\n"
        "with open(os.environ['STUB_LOG'], 'a') as fh:\n"
        "    fh.write(json.dumps({'argv': ['we-worker'] + sys.argv[1:], 'cwd': os.getcwd()}) + '\\n')\n"
        "state = os.environ['STUB_STATE']\n"
        "rows = [r for r in json.load(open(state)) if r['id'] != sys.argv[2]]\n"
        "json.dump(rows, open(state, 'w'))\n"
    )
    ww.chmod(0o755)
    env["configure"](TEMPLATE)
    wl.launch(env["wt"], "w1", env["brief"], "we:dev-medium")
    _crew(env, {"worker": "we-worker {name} --bg --agent {agent} {brief}"})
    wl.stop("w1", env["wt"])
    argvs = [c["argv"] for c in _calls(env)]
    assert ["we-worker", "stop", "bg1"] in argvs
    assert ["stop", "bg1"] not in argvs


def test_a_broken_crew_leaves_the_config_in_charge(env, capsys):
    env["configure"](TEMPLATE)
    (env["wt"] / ".weside" / "crew.json").write_text('{"version": 7}')
    assert wl.backend(env["wt"]) == TEMPLATE
    assert "crew unreadable" in capsys.readouterr().err


def test_stop_falls_back_to_claude_stop_when_we_worker_is_not_on_path(env):
    env["configure"](TEMPLATE)
    wl.launch(env["wt"], "w1", env["brief"], "we:dev-medium")
    _crew(env, {"worker": "we-worker {name} --bg --agent {agent} {brief}"})
    wl.stop("w1", env["wt"])
    assert ["stop", "bg1"] in [c["argv"] for c in _calls(env)]


# Several sessions of one name, a dropped --agent, checkpoint.


def test_stop_ends_every_session_of_the_name_and_names_their_ids(env):
    rows = [
        *_rows(env),
        {"id": "w1a", "name": "w1", "cwd": "/a", "kind": "background", "pid": 1},
        {"id": "w1b", "name": "w1", "cwd": "/a", "kind": "background", "pid": 2},
    ]
    env["state"].write_text(json.dumps(rows))
    assert wl.stop("w1") == ["w1a", "w1b"]
    argvs = [c["argv"] for c in _calls(env)]
    assert ["stop", "w1a"] in argvs and ["stop", "w1b"] in argvs


def test_stop_without_worktree_refuses_one_name_in_several_trees(env):
    """Red arm: `stop --name w1` without --worktree never ends the w1 of another tree too."""
    rows = [
        *_rows(env),
        {"id": "w1a", "name": "w1", "cwd": "/a", "kind": "background", "pid": 1},
        {"id": "w1b", "name": "w1", "cwd": "/b", "kind": "background", "pid": 2},
    ]
    env["state"].write_text(json.dumps(rows))
    with pytest.raises(wl.LaunchError, match=r"2 sessions are named w1, in /a, /b.*--worktree"):
        wl.stop("w1")
    assert not any(c["argv"][:1] == ["stop"] for c in _calls(env))


def test_a_row_without_id_is_named_by_its_session_never_none(env, monkeypatch):
    """Red arm: an interactive row of `claude agents --json` has no `id`; the refusal names its
    pid, never `claude stop None`, and is-worker is asked by its sessionId."""
    asked = []
    pid = os.getpid()
    row = {
        "name": "Wina",
        "cwd": "/nowhere",
        "kind": "interactive",
        "pid": pid,
        "sessionId": "s-77",
    }
    with monkeypatch.context() as m:
        m.setattr(
            wl.subprocess,
            "run",
            lambda argv, **_kw: (
                asked.append(argv) or wl.subprocess.CompletedProcess(argv, 1, "", "")
            ),
        )
        assert wl.is_worker(row) is False and asked[-1][-1] == "s-77"
        assert wl.is_worker({"name": "x"}) is False and len(asked) == 1
    env["state"].write_text(json.dumps([*_rows(env), row]))
    with pytest.raises(wl.LaunchError) as exc:
        wl.stop("Wina")
    assert "None" not in str(exc.value) and f"kill {pid}" in str(exc.value)
    with pytest.raises(wl.LaunchError, match=rf"no background id .*`kill {pid}` does"):
        wl._stop_one(row, None)


def test_stop_refuses_a_session_of_the_name_that_is_no_worker(env):
    rows = [*_rows(env), {"id": "ma1", "name": "Pia", "cwd": "/nowhere", "kind": "interactive"}]
    env["state"].write_text(json.dumps(rows))
    with pytest.raises(
        wl.LaunchError, match=r"Pia \(ma1, interactive\) is no worker.*claude stop ma1"
    ):
        wl.stop("Pia")
    assert not any(c["argv"][:1] == ["stop"] for c in _calls(env))


def test_a_refused_stop_names_the_pid(env, monkeypatch):
    monkeypatch.setenv("STUB_STOP_FAILS", "1")
    rows = [
        *_rows(env),
        {"id": "w9", "name": "w9", "cwd": "/a", "kind": "background", "pid": 4242},
    ]
    env["state"].write_text(json.dumps(rows))
    with pytest.raises(wl.LaunchError, match=r"pid 4242: `kill 4242` ends it"):
        wl.stop("w9")


def test_an_agent_the_template_cannot_carry_is_named(env, capsys):
    env["configure"]("claude --bg -n {name} {brief}")
    wl.launch(env["wt"], "w1", env["brief"], "we:dev-high")
    assert "--agent we:dev-high is dropped" in capsys.readouterr().err


def test_checkpoint_pushes_the_tracked_changes_to_a_wip_branch(env, tmp_path, monkeypatch):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    _git(env["wt"], "remote", "add", "origin", str(origin))
    (env["wt"] / "a.txt").write_text("one\n")
    _git(env["wt"], "add", "a.txt")
    _git(env["wt"], "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "a")
    (env["wt"] / "a.txt").write_text("two\n")
    rows = [*_rows(env), {"id": "w1", "name": "w1", "cwd": str(env["wt"]), "kind": "background"}]
    env["state"].write_text(json.dumps(rows))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")
    line = wl.checkpoint("w1")
    assert line.endswith("pushed to wip/x")
    shown = subprocess.run(
        ["git", "--git-dir", str(origin), "show", "wip/x:a.txt"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert shown.stdout == "two\n"
