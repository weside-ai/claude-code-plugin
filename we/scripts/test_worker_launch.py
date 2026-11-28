"""worker_launch.py against a real git worktree and a stub `claude` on PATH."""

import json
import os
import re
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
    fh.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(),
                         "config_dir": os.environ.get("CLAUDE_CONFIG_DIR")}) + "\n")
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
BRIEF_TEXT = "## Goal\n\nThe hook denies the never-list.\n\n## Output\n\nOne commit, the report.\n"


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
    monkeypatch.setenv("WE_WORKER_STATE_DIR", str(tmp_path / "state"))  # launched.jsonl
    monkeypatch.setenv("STUB_STATE", str(state))
    monkeypatch.setenv("STUB_LOG", str(log))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s-lead")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    brief = tmp_path / "brief.md"
    brief.write_text('Run Skill("we:develop") for KEY.\n\n' + BRIEF_TEXT)

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
        ("x {name} {brief} {effort}", "unknown placeholder {effort}"),
        ("x {name}", "placeholder {brief} is required"),
        ("x --n={name} {brief}", "must be a token of its own"),
        ("x 'unterminated {name} {brief}", "cannot split"),
        # claude knows no --utility: a claude --bg worker carries its lane in its settings
        ("claude --bg -n {name} {lane} {brief}", "{lane} becomes --utility"),
    ],
)
def test_invalid_template_refuses_and_launches_nothing(env, template, message):
    env["configure"](template)
    out = _run("backend", "--repo", str(env["wt"]))
    assert out.returncode == 2 and message in out.stderr
    out = _run(
        "launch",
        "--worktree",
        str(env["wt"]),
        "--name",
        "KEY-1-w1",
        "--brief-file",
        str(env["brief"]),
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
        "KEY-1-w1",
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
    assert marker["name"] == "KEY-1-w1" and marker["lead"] == "LEAD-1"
    assert marker["agent"] == "we:dev-medium" and marker["launched_at"] > 0
    assert marker["session_id"] == "s-KEY-1-w1"
    launch = _launch_call(env)
    assert launch["argv"] == [
        "--settings",
        str(gd / wl.SETTINGS),
        "--bg",
        "-n",
        "KEY-1-w1",
        "--agent",
        "we:dev-medium",
        f"Read {gd / wl.BRIEF} and follow it.",
    ]
    assert Path(launch["cwd"]).resolve() == env["wt"].resolve()
    assert [r["cwd"] for r in _rows(env) if r["name"] == "KEY-1-w1"] == [launch["cwd"]]
    timing = list((Path(os.environ["HOME"]) / ".claude" / "we-timing").glob("*.jsonl"))
    assert json.loads(timing[0].read_text().splitlines()[0])["event"] == "WorkerLaunch"


def test_a_claude_bg_template_states_the_worker_env_as_settings(env, monkeypatch):
    """`claude --bg` takes the daemon's environment (measured: WE_ROLE=worker and
    another story's key), so the launcher's variables never arrive; the worker's own go in as
    `--settings`. Red arm: without them the worker runs as the daemon's story."""
    env["configure"]("claude --bg -n {name} {brief}")
    monkeypatch.setenv("WE_HUMAN", "ana")
    wl.launch(env["wt"], "KEY-1-w1", env["brief"])
    argv = _launch_call(env)["argv"]
    assert "--settings" in argv, f"claude --bg started without --settings: {argv}"
    doc = json.loads(Path(argv[argv.index("--settings") + 1]).read_text())
    assert doc == {
        "env": {
            "WE_ROLE": "worker",
            "WE_STORY_KEY": "KEY-1",
            "WESIDE_COMPANION": "",
            "WE_ROLE_ID": "",
            "WE_START": "",
            "WE_WORKER_STARTER": "",
            "WE_STARTER": "LEAD-1",
            "WE_WORKER_NAME": "KEY-1-w1",
            "WE_WORKER_LANE": "build",
            "WE_HUMAN": "ana",
        }
    }
    assert not any(k.startswith("ANTHROPIC") for k in doc["env"])  # never a credential on disk
    state = Path(os.environ["WE_WORKER_STATE_DIR"])
    assert wl.read_launched(state)[0][-1]["lane"] == "build"  # the start log keeps the lane
    assert wl.lane_of(state, "KEY-1-w1", str(env["wt"])) == "build"
    wl.clear_marker(env["wt"])
    assert not (wl.git_dir(env["wt"]) / wl.SETTINGS).exists()
    # a utility worker counts in the utility lane through its tree's settings file, and only
    # under its own name (the file in the git dir belongs to the tree's newest worker)
    wl.launch(env["wt"], "KEY-1-w2", env["brief"], utility=True)
    assert wl.lane_of(state, "KEY-1-w2", str(env["wt"])) == "utility"
    assert wl.lane_of(state, "KEY-1-w2") == "build"  # no tree: nothing to read
    assert wl.lane_of(state, "KEY-1-other", str(env["wt"])) == "build"
    assert wl.read_launched(state)[0][-1]["lane"] == "utility"


def test_a_launcher_template_brings_its_own_settings(env, tmp_path):
    """`we-worker` writes the worker's settings itself; the launch adds none. `{lane}` hands a
    utility start on as `--utility` (Claude Review on #320: the master's fix rounds started in
    the build lane) and vanishes for a build start."""
    stub = tmp_path / "bin" / "we-worker"
    stub.write_text((tmp_path / "bin" / "claude").read_text())
    stub.chmod(0o755)
    env["configure"]("we-worker --bg -n {name} {lane} {brief}")
    wl.launch(env["wt"], "KEY-1-w1", env["brief"])
    assert not {"--settings", "--utility", ""} & set(_launch_call(env)["argv"])
    wl.launch(env["wt"], "KEY-1-w2", env["brief"], utility=True)
    argv = [c["argv"] for c in _calls(env) if "--bg" in c["argv"]][-1]
    assert argv[argv.index("KEY-1-w2") + 1] == "--utility"


def test_a_template_start_hands_the_masters_model_choice_on(env, tmp_path):
    """The master picks Sonnet or Opus per worker (owner 28.11.2026); a crew starts its workers
    through the template, which had no way to pass it (Claude Review on the PR): `{model}` becomes
    `--model=<m>` and vanishes without one; a `--model` into a template without it refuses."""
    stub = tmp_path / "bin" / "we-worker"
    stub.write_text((tmp_path / "bin" / "claude").read_text())
    stub.chmod(0o755)
    env["configure"]("we-worker --bg -n {name} {model} {brief}")
    wl.launch(env["wt"], "KEY-1-w1", env["brief"], model="sonnet")
    assert "--model=sonnet" in _launch_call(env)["argv"]
    wl.launch(env["wt"], "KEY-1-w2", env["brief"])
    argv = [c["argv"] for c in _calls(env) if "--bg" in c["argv"]][-1]
    assert not [a for a in argv if a.startswith("--model") or a == ""]
    env["configure"]("we-worker --bg -n {name} {brief}")
    with pytest.raises(wl.LaunchError, match=r"no \{model\}") as exc:
        wl.launch(env["wt"], "KEY-1-w3", env["brief"], model="opus")
    assert exc.value.code == 2


def test_a_pinned_lead_reads_and_starts_on_the_global_supervisor(env, monkeypatch):
    """a pinned master carries CLAUDE_CONFIG_DIR; `claude agents` under it asks
    another supervisor (too few busy workers, a marker without session_id). Red arm: the
    variable reaches the stub."""
    env["configure"]("claude --bg -n {name} {brief}")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/pinned/profile")
    wl.launch(env["wt"], "KEY-1-w1", env["brief"])
    leaked = [c["argv"][:2] for c in _calls(env) if c["config_dir"]]
    assert not leaked, f"CLAUDE_CONFIG_DIR reached claude in {leaked}"


def test_agent_placeholder_needs_an_agent(env):
    env["configure"](TEMPLATE)
    with pytest.raises(wl.LaunchError, match="pass --agent") as exc:
        wl.launch(env["wt"], "KEY-1-w2", env["brief"])
    assert exc.value.code == 2 and wl.read_marker(env["wt"]) is None
    env["configure"]("claude --bg -n {name} {brief}")
    wl.launch(env["wt"], "KEY-1-w2", env["brief"])
    assert _launch_call(env)["argv"][2:5] == ["--bg", "-n", "KEY-1-w2"]


def test_lead_in_the_worker_tree_is_no_worker(env):
    env["configure"](TEMPLATE)
    wl.launch(env["wt"], "KEY-1-w1", env["brief"], "we:dev-medium")
    assert (
        wl.worker_marker({"cwd": str(env["wt"]), "session_id": "s-KEY-1-w1"})["name"] == "KEY-1-w1"
    )
    assert wl.worker_marker({"cwd": str(env["wt"]), "session_id": "s-lead"}) is None
    assert wl.worker_marker({"cwd": str(env["wt"])}) is None


def test_unnamed_lead_refuses(env, monkeypatch):
    env["configure"]("claude --bg -n {name} {brief}")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s-unknown")
    with pytest.raises(wl.LaunchError, match="name this session first"):
        wl.launch(env["wt"], "KEY-1-w1", env["brief"])
    assert wl.read_marker(env["wt"]) is None
    assert not any("--bg" in c["argv"] for c in _calls(env))


def test_failed_launch_removes_its_files(env, monkeypatch):
    env["configure"]("claude --bg -n {name} {brief}")
    monkeypatch.setenv("STUB_LAUNCH_FAILS", "1")
    with pytest.raises(wl.LaunchError, match="exited 7: boom"):
        wl.launch(env["wt"], "KEY-1-w1", env["brief"])
    gd = wl.git_dir(env["wt"])
    assert not (gd / wl.MARKER).exists() and not (gd / wl.BRIEF).exists()


def test_launch_refuses_on_the_subagent_backend(env):
    with pytest.raises(wl.LaunchError, match="Agent\\(isolation"):
        wl.launch(env["wt"], "KEY-1-w1", env["brief"])


def test_stop_and_alive(env):
    env["configure"](TEMPLATE)
    wl.launch(env["wt"], "KEY-1-w1", env["brief"], "we:dev-medium")
    assert _run("alive", "--name", "KEY-1-w1").returncode == 0
    out = _run("stop", "--name", "KEY-1-w1", "--worktree", str(env["wt"]))
    assert out.returncode == 0, out.stderr
    assert ["stop", "bg1"] in [c["argv"] for c in _calls(env)]
    assert _run("alive", "--name", "KEY-1-w1").returncode == 1
    gd = wl.git_dir(env["wt"])
    assert not (gd / wl.MARKER).exists() and not (gd / wl.BRIEF).exists()
    out = _run("stop", "--name", "KEY-1-w1")
    assert out.returncode == 1 and "no running session named KEY-1-w1" in out.stderr


def test_a_row_whose_process_died_is_not_alive(env):
    """`claude agents` keeps the row of a background worker that died on an auth error; the
    watchdog read it as alive and never reported the end (red arm: alive exited 0)."""
    env["configure"](TEMPLATE)
    wl.launch(env["wt"], "KEY-1-w1", env["brief"], "we:dev-medium")
    rows = _rows(env)
    for r in rows:
        if r["name"] == "KEY-1-w1":
            r["pid"] = 999999999
    env["state"].write_text(json.dumps(rows))
    assert _run("alive", "--name", "KEY-1-w1").returncode == 1


def test_stop_of_an_ended_session_clears_its_marker(env):
    env["configure"](TEMPLATE)
    wl.launch(env["wt"], "KEY-1-w1", env["brief"], "we:dev-medium")
    env["state"].write_text(json.dumps([r for r in _rows(env) if r["name"] != "KEY-1-w1"]))
    with pytest.raises(wl.LaunchError, match="no running session"):
        wl.stop("KEY-1-w1", env["wt"])
    assert wl.read_marker(env["wt"]) is None


def test_stop_reports_a_session_that_keeps_running(env, monkeypatch):
    env["configure"](TEMPLATE)
    wl.launch(env["wt"], "KEY-1-w1", env["brief"], "we:dev-medium")
    monkeypatch.setenv("STUB_STOP_IGNORED", "1")
    with pytest.raises(wl.LaunchError, match="still running") as exc:
        wl.stop("KEY-1-w1", wait_s=0)
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
    wl.launch(env["wt"], "KEY-1-w1", env["brief"], "we:dev-medium")
    _crew(env, {"worker": "we-worker {name} --bg --agent {agent} {brief}"})
    wl.stop("KEY-1-w1", env["wt"])
    argvs = [c["argv"] for c in _calls(env)]
    assert ["we-worker", "stop", "bg1"] in argvs
    assert ["stop", "bg1"] not in argvs


def test_a_broken_crew_leaves_the_config_in_charge(env, capsys):
    env["configure"](TEMPLATE)
    (env["wt"] / ".weside" / "crew.json").write_text('{"version": 7}')
    assert wl.backend(env["wt"]) == TEMPLATE
    assert "crew unreadable" in capsys.readouterr().err


def test_stop_falls_back_to_claude_stop_when_we_worker_is_not_on_path(env, monkeypatch):
    path = [d for d in os.environ["PATH"].split(os.pathsep) if not Path(d, "we-worker").exists()]
    monkeypatch.setenv("PATH", os.pathsep.join(path))
    env["configure"](TEMPLATE)
    wl.launch(env["wt"], "KEY-1-w1", env["brief"], "we:dev-medium")
    _crew(env, {"worker": "we-worker {name} --bg --agent {agent} {brief}"})
    wl.stop("KEY-1-w1", env["wt"])
    assert ["stop", "bg1"] in [c["argv"] for c in _calls(env)]


# Several sessions of one name, a dropped --agent, checkpoint.


def test_stop_ends_every_session_of_the_name_and_names_their_ids(env):
    rows = [
        *_rows(env),
        {"id": "w1a", "name": "KEY-1-w1", "cwd": "/a", "kind": "background", "pid": 1},
        {"id": "w1b", "name": "KEY-1-w1", "cwd": "/a", "kind": "background", "pid": 2},
    ]
    env["state"].write_text(json.dumps(rows))
    assert wl.stop("KEY-1-w1") == ["w1a", "w1b"]
    argvs = [c["argv"] for c in _calls(env)]
    assert ["stop", "w1a"] in argvs and ["stop", "w1b"] in argvs


def test_stop_without_worktree_refuses_one_name_in_several_trees(env):
    """Red arm: `stop --name KEY-1-w1` without --worktree never ends the KEY-1-w1 of another tree too."""
    rows = [
        *_rows(env),
        {"id": "w1a", "name": "KEY-1-w1", "cwd": "/a", "kind": "background", "pid": 1},
        {"id": "w1b", "name": "KEY-1-w1", "cwd": "/b", "kind": "background", "pid": 2},
    ]
    env["state"].write_text(json.dumps(rows))
    with pytest.raises(
        wl.LaunchError, match=r"2 sessions are named KEY-1-w1, in /a, /b.*--worktree"
    ):
        wl.stop("KEY-1-w1")
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


def test_an_agent_the_template_cannot_carry_is_named(env, capsys, tmp_path):
    env["configure"]("claude --bg -n {name} {brief}")
    wl.launch(env["wt"], "KEY-1-w1", env["brief"], "we:dev-high", utility=True)
    err = capsys.readouterr().err
    assert "--agent we:dev-high is dropped" in err
    assert "--utility is dropped" not in err  # a claude --bg worker's settings carry the lane
    stub = tmp_path / "bin" / "we-worker"
    stub.write_text((tmp_path / "bin" / "claude").read_text())
    stub.chmod(0o755)
    env["configure"]("we-worker --bg -n {name} {brief}")
    wl.launch(env["wt"], "KEY-1-w2", env["brief"], utility=True)
    assert "--utility is dropped" in capsys.readouterr().err  # we-worker counts it in build


def test_checkpoint_pushes_the_tracked_changes_to_a_wip_branch(env, tmp_path, monkeypatch):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    _git(env["wt"], "remote", "add", "origin", str(origin))
    (env["wt"] / "a.txt").write_text("one\n")
    _git(env["wt"], "add", "a.txt")
    _git(env["wt"], "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "a")
    (env["wt"] / "a.txt").write_text("two\n")
    rows = [
        *_rows(env),
        {"id": "KEY-1-w1", "name": "KEY-1-w1", "cwd": str(env["wt"]), "kind": "background"},
    ]
    env["state"].write_text(json.dumps(rows))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")
    line = wl.checkpoint("KEY-1-w1")
    assert line.endswith("pushed to wip/x")
    shown = subprocess.run(
        ["git", "--git-dir", str(origin), "show", "wip/x:a.txt"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert shown.stdout == "two\n"


# ---------------------------------------------------------------- name, brief, settings


class TestCheckName:
    @pytest.mark.parametrize(
        "name,key", [("AB-2856-hook", "AB-2856"), ("AB-2856", "AB-2856"), ("XY-1-p2-x", "XY-1")]
    )
    def test_a_name_with_a_key_gives_the_key(self, name, key):
        assert wl.check_name(name) == key

    @pytest.mark.parametrize("name", ["build-fix", "fix-AB-2856", "wa-2856-hook", "AB-2856hook"])
    def test_a_name_without_a_leading_key_refuses(self, name):
        with pytest.raises(wl.LaunchError) as exc:
            wl.check_name(name, example="AB-2856")
        assert exc.value.code == 2
        assert str(exc.value) == (
            f"worker name {name} carries no story key ([A-Z]+-\\d+), e.g. AB-2856-{name}"
            " (close, the board and the supervisor find a story's workers by that key)"
        )

    def test_the_crews_key_pattern_decides(self, env):
        (env["wt"] / ".weside").mkdir(exist_ok=True)
        crew = {
            "version": 2,
            "roles": {"product": "po"},
            "members": {"po": {"name": "Ada"}},
            "naming": {"key": "#\\d+"},
        }
        (env["wt"] / ".weside" / "crew.json").write_text(json.dumps(crew))
        assert wl.key_pattern(env["wt"]) == "#\\d+"
        out = _run(
            "check",
            "--name",
            "#12-fix",
            "--repo",
            str(env["wt"]),
        )
        assert out.returncode == 0 and out.stdout.strip() == "#12"

    def test_launch_refuses_before_writing_a_file(self, env):
        env["configure"](TEMPLATE)
        out = _run(
            "launch",
            "--worktree",
            str(env["wt"]),
            "--name",
            "build-fix",
            "--agent",
            "we:dev-medium",
            "--brief-file",
            str(env["brief"]),
        )
        assert (
            out.returncode == 2
            and "worker_launch: worker name build-fix carries no story key" in out.stderr
        )
        gd = wl.git_dir(env["wt"])
        assert not (gd / wl.BRIEF).exists() and not (gd / wl.MARKER).exists()
        assert not any("--bg" in c["argv"] for c in _calls(env))


class TestCheck:
    def test_a_one_line_brief_starts_without_a_warning_or_a_brake_line(
        self, env, tmp_path, monkeypatch
    ):
        """A start with a one-line brief prints no warning and writes no line to the brake log."""
        state = tmp_path / "we-state"
        env_vars = {**os.environ, "WE_STATE_DIR": str(state)}
        out = subprocess.run(
            [sys.executable, str(SCRIPT), "check", "--name", "AB-1-x", "--prefix", "we-worker"],
            capture_output=True,
            text=True,
            env=env_vars,
            check=False,
        )
        assert (out.returncode, out.stdout.strip(), out.stderr) == (0, "AB-1", "")
        env["configure"](TEMPLATE)
        one_line = tmp_path / "one-line.md"
        one_line.write_text("fix it")
        monkeypatch.setenv("WE_STATE_DIR", str(state))
        wl.launch(env["wt"], "KEY-1-w1", one_line, "we:dev-medium")
        assert not (state / "brakes.jsonl").exists()

    def test_an_older_we_worker_copy_still_passes_its_brief_flags(self):
        for flags in (["--brief-file", "-"], ["--no-brief"]):
            out = subprocess.run(
                [sys.executable, str(SCRIPT), "check", "--name", "AB-1-x", *flags],
                input="fix it",
                capture_output=True,
                text=True,
                check=False,
            )
            assert (out.returncode, out.stdout.strip(), out.stderr) == (0, "AB-1", ""), flags

    def test_check_names_a_living_worker_of_the_same_key_as_the_sendmessage_target(self, env):
        """Red arm: five workers on one ticket, three of them follow-ups the refiner could have
        taken by SendMessage."""
        rows = json.loads(env["state"].read_text())
        rows += [
            {"name": "KEY-1-refiner", "status": "idle", "pid": os.getpid(), "sessionId": "a"},
            {"name": "KEY-1-gone", "status": "idle", "pid": 999999999, "sessionId": "b"},
            {"name": "KEY-12-other", "status": "idle", "pid": os.getpid(), "sessionId": "c"},
        ]
        env["state"].write_text(json.dumps(rows))
        out = _run("check", "--name", "KEY-1-planfix", "--no-brief", "--prefix", "we-worker")
        assert out.returncode == 0 and out.stdout.strip() == "KEY-1"
        assert out.stderr.splitlines() == [
            "we-worker: hint: KEY-1-refiner (idle) works on KEY-1 and lives: a follow-up goes to"
            " it by SendMessage, not to a new worker KEY-1-planfix"
        ]

    def test_the_marker_carries_the_key(self, env):
        env["configure"](TEMPLATE)
        wl.launch(env["wt"], "KEY-1-w1", env["brief"], "we:dev-medium")
        assert wl.read_marker(env["wt"])["key"] == "KEY-1"


class TestSettings:
    def test_settings_writes_the_rights_file_with_the_timer_hook(self, env, tmp_path):
        out_file = tmp_path / "state" / "KEY-1-w1.settings.json"
        out = _run(
            "settings",
            "--repo",
            str(env["wt"]),
            "--key",
            "KEY-1",
            "--out",
            str(out_file),
            "--session-start",
            "timer arm x",
        )
        assert out.returncode == 0, out.stderr
        doc = json.loads(out_file.read_text())
        # no crew: only the unconditional allow rules (ready and comment), no branch_rc
        assert doc["permissions"]["allow"][0] == "Bash(gh pr ready*)"
        assert doc["permissions"]["allow"][-1] == "Bash(gh pr comment*)"
        assert len(doc["permissions"]["allow"]) == 4
        assert "Bash(*gh secret *)" in doc["permissions"]["deny"]
        assert doc["env"] == {
            "WE_ROLE": "worker",
            "WE_STORY_KEY": "KEY-1",
            "WESIDE_COMPANION": "",
            "WE_ROLE_ID": "",
            "WE_START": "",
            "WE_WORKER_STARTER": "",
            "WE_STARTER": "",
            "WE_WORKER_NAME": "",
            "WE_WORKER_LANE": "build",
        }
        assert doc["hooks"]["SessionStart"][0]["hooks"][0]["command"] == "timer arm x"
        assert not {"enabledPlugins", "autoMemoryDirectory", "autoCompactWindow"} & set(doc)

    @pytest.mark.parametrize(
        "context, keys",
        [
            ({}, {}),
            (
                {
                    "auto_memory": "shared",
                    "disable_plugins": ["sentry@market"],
                    "deny_mcp_servers": ["vault"],
                    "auto_compact_window": 200000,
                    "advisor_model": "opus",
                },
                {
                    "enabledPlugins": {"sentry@market": False},
                    "deniedMcpServers": [{"serverName": "vault"}],
                    "autoCompactWindow": 200000,
                    "advisorModel": "opus",
                },
            ),
            ({"auto_compact_window": 5000}, None),
            ({"advisor_model": ""}, None),
        ],
    )
    def test_workers_context_makes_the_settings_lean(self, env, tmp_path, context, keys):
        (env["wt"] / ".weside").mkdir(exist_ok=True)
        (env["wt"] / ".weside" / "config.json").write_text(
            json.dumps({"workers": {"context": context}})
        )
        out_file = tmp_path / "state" / "KEY-1-w1.settings.json"
        args = ("--repo", str(env["wt"]), "--key", "KEY-1", "--name", "KEY-1-w1")
        out = _run("settings", *args, "--out", str(out_file))
        if keys is None:
            assert out.returncode == 2 and "workers.context" in out.stderr
            return
        assert out.returncode == 0, out.stderr
        doc = json.loads(out_file.read_text())
        assert doc["autoMemoryEnabled"] is False  # every worker, whatever the context says
        assert {k: doc.get(k) for k in keys} == keys
        assert (
            "autoMemoryDirectory" not in doc
            and "CLAUDE_CODE_DISABLE_AUTO_MEMORY" not in doc["env"]
        )

    def _settings(self, env, tmp_path, context, *brief):
        if context is not None:
            (env["wt"] / ".weside").mkdir(exist_ok=True)
            (env["wt"] / ".weside" / "config.json").write_text(
                json.dumps({"workers": {"context": context}})
            )
        out_file = tmp_path / "state" / "KEY-1-w1.settings.json"
        args = ("--repo", str(env["wt"]), "--key", "KEY-1", "--out", str(out_file))
        if brief:
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "settings", *args, "--brief-stdin"],
                input=brief[0],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            proc = _run("settings", *args)
        return proc, (json.loads(out_file.read_text()) if proc.returncode == 0 else None)

    def test_deny_tools_and_skills_off_land_in_the_worker_settings(self, env, tmp_path):
        _, plain = self._settings(env, tmp_path, None)
        never = plain["permissions"]["deny"]
        context = {"deny_tools": ["Artifact", "Workflow", "Artifact"], "skills_off": ["dataviz"]}
        proc, doc = self._settings(env, tmp_path, context)
        assert proc.returncode == 0, proc.stderr
        assert doc["permissions"]["deny"] == [*never, "Artifact", "Workflow"]
        assert doc["skillOverrides"] == {"dataviz": "off"}
        for key, value in [
            ("deny_tools", "Artifact"),
            ("deny_tools", ["Artifact", ""]),
            ("skills_off", [3]),
            ("skills_off", {"dataviz": "off"}),
        ]:
            proc, _ = self._settings(env, tmp_path, {key: value})
            assert proc.returncode == 2 and f"workers.context.{key}" in proc.stderr, (key, value)

    @pytest.mark.parametrize("context", [None, {}, {"disable_plugins": [], "deny_tools": []}])
    def test_a_context_without_the_two_keys_writes_the_same_document(self, env, tmp_path, context):
        import worker_rights  # noqa: PLC0415

        proc, doc = self._settings(env, tmp_path, context, "Needs: Artifact, dataviz\n")
        assert proc.returncode == 0, proc.stderr
        want = worker_rights.settings(env["wt"], "KEY-1", None, None, None)
        want["autoMemoryEnabled"] = False
        assert doc == want

    def test_a_needs_line_gives_a_denied_tool_and_skill_back(self, env, tmp_path):
        _, plain = self._settings(env, tmp_path, None)
        never = plain["permissions"]["deny"]
        guarded = next(d for d in never if d.startswith("Bash("))
        context = {
            "deny_tools": ["Artifact", "Workflow", guarded],
            "skills_off": ["dataviz", "init"],
            "disable_plugins": ["sentry@market"],
        }
        pointer = tmp_path / "brief.md"
        pointer.write_text(f"Build it.\nNeeds: Artifact, dataviz, {guarded}\n")
        proc, doc = self._settings(env, tmp_path, context, f"Read {pointer} and follow it.\n")
        assert proc.returncode == 0, proc.stderr
        assert doc["permissions"]["deny"] == [*never, "Workflow"]  # the never-list stays
        assert doc["skillOverrides"] == {"init": "off"}
        proc, doc = self._settings(env, tmp_path, context, "Needs: dataviz, init\n")
        assert "skillOverrides" not in doc and "Artifact" in doc["permissions"]["deny"]
        proc = _needs(env["wt"], "Needs: Artifact, sentry\n")  # a plugin need still refuses
        assert proc.returncode == 2 and "turns off (sentry@market)" in proc.stderr
        assert _needs(env["wt"], "Needs: Artifact, dataviz\n").returncode == 0


def test_add_tree_runs_the_repos_template_with_path_and_branch(env, tmp_path):
    (env["repo"] / ".weside").mkdir()
    log = tmp_path / "tree.args"
    script = (
        f"import sys,subprocess; open({str(log)!r},'w').write(' '.join(sys.argv[1:])); "
        "subprocess.run(['git','worktree','add','-q','-b',sys.argv[2],sys.argv[1]],check=True)"
    )
    (env["repo"] / ".weside" / "config.json").write_text(
        json.dumps(
            {
                "workers": {
                    "add_worktree": f"{sys.executable} -c {json.dumps(script)} {{path}} {{branch}}",
                    "remove_worktree": "a worktree remove {path}",
                }
            }
        )
    )
    path = wl.add_tree(env["repo"], "KEY-1-w2", "fix/KEY-1-w2")
    assert path == tmp_path / "repo-KEY-1-w2" and log.read_text() == f"{path} fix/KEY-1-w2"
    assert wl.remove_command(env["repo"], str(path)) == f"a worktree remove {path}"
    with pytest.raises(wl.LaunchError, match="no main checkout"):
        wl.add_tree(env["wt"], "KEY-1-w3")


# The concurrency cap: busy sessions and room in the account rotation.

CSWAP = r"""#!/usr/bin/env python3
import os, sys
if os.environ.get("STUB_CSWAP_FAILS"): sys.exit(1)
if sys.argv[1] == "list":
    print(os.environ.get("STUB_CSWAP_LIST", "{}"))
else:
    print(os.environ["STUB_CSWAP_JSON"])
"""


def _account(number, five, seven, active=False, disabled=False):
    """One `cswap list --json` row in the recorded shape, name fields redacted."""
    row = {
        "number": number,
        "email": "redacted@example.com",
        "organizationName": "",
        "organizationUuid": "",
        "isOrganization": False,
        "active": active,
        "usageStatus": "ok",
        "usage": {"fiveHour": {"pct": five}, "sevenDay": {"pct": seven}},
    }
    if disabled:
        row["disabled"] = True
    return row


def _rotation(*rows):
    return json.dumps({"schemaVersion": 1, "activeAccountNumber": 1, "accounts": list(rows)})


@pytest.fixture
def cap(env, monkeypatch, tmp_path):
    """`env` with `count` busy sessions, a stub `cswap` at `pct` and a config block."""
    stub = tmp_path / "bin" / "cswap"
    stub.write_text(CSWAP)
    stub.chmod(0o755)

    def setup(busy, pct, workers=None, pool=None):
        state_dir = tmp_path / "state"
        state_dir.mkdir(exist_ok=True)
        if pool is not None:
            (state_dir / "pool.json").write_text(json.dumps(pool))
        else:
            (state_dir / "pool.json").unlink(missing_ok=True)
        rows = [{"name": f"S{i}", "status": "busy", "pid": 1} for i in range(busy)]
        rows.append({"name": "idle", "status": "idle", "pid": 1})
        env["state"].write_text(json.dumps(rows))
        usage = {"active": {"usage": {"fiveHour": {"pct": pct}}}}
        monkeypatch.setenv("STUB_CSWAP_JSON", json.dumps(usage))
        (env["wt"] / ".weside").mkdir(exist_ok=True)
        cfg = {} if workers is None else {"workers": workers}
        (env["wt"] / ".weside" / "config.json").write_text(json.dumps(cfg))
        return _run("capacity", "--repo", str(env["wt"]), "--prefix", "we-worker")

    return setup


def test_capacity_refuses_above_either_limit_and_names_both_values(cap, tmp_path):
    """Red arm: 14 usage-limit stops in 11 sessions within 13 minutes."""
    out = cap(8, 50.0)
    assert out.returncode == 3
    assert out.stderr.strip().startswith(
        "we-worker: refused, no worker started: build lane: 8 workers busy (limit 8 for the"
        f" machine, max_busy_sessions of {tmp_path / 'state' / 'pool.json'}; utility lane 0 busy,"
        " limit 5), active account 5h at 50 % (limit 80 %,"
        f" max_active_5h_percent of {tmp_path / 'state' / 'pool.json'}); try again later"
    )
    out = cap(2, 81.0)
    assert out.returncode == 3 and "active account 5h at 81 % (limit 80 %" in out.stderr


def test_capacity_below_the_limits_starts(cap):
    """The machine's default is 8: 13 busy workers measured 5.4 of 5.5 GiB swap, load15 24."""
    out = cap(7, 80.0)
    assert out.returncode == 0 and out.stderr == ""


def test_capacity_reads_the_limits_from_the_machine_and_a_repo_only_lowers_them(cap):
    """Red arm (21.11.): core's `workers.max_busy_sessions` 16 started a worker at 13 busy while
    infra's queued start (limit 10) waited; the busy count is the machine's, so is its limit.
    T2 panel on #308: a public repo's lower value (3) must hold, not be lifted to the machine's."""
    out = cap(8, 10.0, {"max_busy_sessions": 16})  # a repo value lifts nothing
    assert out.returncode == 3 and "8 workers busy (limit 8 for the machine" in out.stderr
    assert "workers.max_busy_sessions 16 in " in out.stderr and "not read" in out.stderr
    out = cap(3, 10.0, {"max_busy_sessions": 3})  # it lowers, silently
    assert out.returncode == 3 and "3 workers busy (limit 3" in out.stderr
    assert "note" not in out.stderr
    assert cap(2, 10.0, {"max_busy_sessions": 3}).returncode == 0
    assert cap(3, 10.0, pool={"max_busy_sessions": 3}).returncode == 3
    out = cap(3, 10.0, {"max_active_5h_percent": 5}, pool={"max_busy_sessions": 4})
    assert out.returncode == 3
    out = cap(3, 10.0, {"max_active_5h_percent": 50}, pool={"max_busy_sessions": 4})
    assert out.returncode == 0
    out = _run("pool-path")
    assert out.returncode == 0 and out.stdout.strip().endswith("/state/pool.json"), out.stderr
    # the 5h limit is the machine's too: pool.json sets it, a repo above it is not read
    out = cap(1, 50.0, pool={"max_active_5h_percent": 40})
    assert out.returncode == 3 and "(limit 40 %" in out.stderr
    out = cap(1, 50.0, {"max_active_5h_percent": 90}, pool={"max_active_5h_percent": 40})
    assert out.returncode == 3 and "workers.max_active_5h_percent 90 in " in out.stderr
    # T2 panel on #308: the refusal names where the 5h limit came from, the repo or the machine
    assert "(limit 40 %, max_active_5h_percent of " in out.stderr
    out = cap(1, 50.0, {"max_active_5h_percent": 30}, pool={"max_active_5h_percent": 40})
    assert out.returncode == 3
    assert "(limit 30 %, workers.max_active_5h_percent in " in out.stderr


def test_capacity_skips_the_window_check_without_cswap_and_says_so(cap, monkeypatch):
    monkeypatch.setenv("STUB_CSWAP_FAILS", "1")
    out = cap(1, 99.0)
    assert out.returncode == 0
    assert out.stderr.strip() == (
        "we-worker: warning: the accounts' 5h windows are unreadable (cswap list --json and cswap"
        " status --json failed); that check is skipped"
    )


def test_capacity_starts_while_another_account_in_rotation_has_room(cap, monkeypatch):
    """The active account is full, another has room: the rotation switches, no refusal."""
    monkeypatch.setenv(
        "STUB_CSWAP_LIST",
        _rotation(_account(1, 91.0, 32.0, active=True), _account(2, 0.0, 77.0)),
    )
    out = cap(1, 91.0)
    assert out.returncode == 0 and out.stderr == ""


def test_capacity_refuses_when_no_account_in_rotation_has_room(cap, monkeypatch, tmp_path):
    monkeypatch.setenv(
        "STUB_CSWAP_LIST",
        _rotation(
            _account(1, 91.0, 32.0, active=True),
            _account(2, 0.0, 100.0),  # 7d spent
            _account(3, 0.0, 95.0),  # 7d at the cap
            _account(4, 0.0, 10.0, disabled=True),  # out of rotation
            {**_account(5, 0.0, 0.0), "usage": None, "usageStatus": "error"},  # no reading
        ),
    )
    out = cap(1, 2.0)
    assert out.returncode == 3
    assert out.stderr.strip().startswith(
        "we-worker: refused, no worker started: build lane: 1 workers busy (limit 8 for the"
        f" machine, max_busy_sessions of {tmp_path / 'state' / 'pool.json'}; utility lane 0 busy,"
        " limit 5), no account in rotation has room (0 of 4 with 7d"
        " under 95 %"
        f" and 5h at or under 80 %, max_active_5h_percent of {tmp_path / 'state' / 'pool.json'});"
        " try again later"
    )
    assert "redacted" not in out.stderr


def test_capacity_an_account_at_the_5h_limit_has_room(cap, monkeypatch):
    monkeypatch.setenv("STUB_CSWAP_LIST", _rotation(_account(1, 80.0, 94.0, active=True)))
    assert cap(1, 99.0).returncode == 0


def test_capacity_busy_limit_holds_with_room_in_rotation(cap, monkeypatch):
    monkeypatch.setenv("STUB_CSWAP_LIST", _rotation(_account(1, 0.0, 0.0, active=True)))
    out = cap(10, 0.0)
    assert out.returncode == 3
    assert (
        "10 workers busy" in out.stderr and "1 of 1 accounts in rotation with room" in out.stderr
    )


@pytest.mark.parametrize("listing", ["not json", "{}", '{"accounts": []}', '{"accounts": "x"}'])
def test_capacity_falls_back_to_the_active_account_without_a_list(cap, monkeypatch, listing):
    monkeypatch.setenv("STUB_CSWAP_LIST", listing)
    out = cap(1, 81.0)
    assert out.returncode == 3 and "active account 5h at 81 % (limit 80 %" in out.stderr
    assert cap(1, 79.0).returncode == 0


def test_capacity_refuses_a_limit_that_is_no_number(cap):
    out = cap(1, 1.0, pool={"max_busy_sessions": "ten"})
    assert out.returncode == 2 and "max_busy_sessions: needs a positive number" in out.stderr
    assert cap(1, 1.0, pool={"max_busy_sessions": 0}).returncode == 2
    out = cap(1, 1.0, {"max_active_5h_percent": "x"})
    assert out.returncode == 2 and "workers.max_active_5h_percent: needs a positive" in out.stderr
    assert cap(1, 1.0, {"max_busy_sessions": 0}).returncode == 2
    assert cap(1, 1.0, pool={"max_active_5h_percent": True}).returncode == 2


def test_pool_json_with_an_old_key_names_its_new_name(tmp_path, capsys):
    (tmp_path / "pool.json").write_text(json.dumps({"utility_max_pressure_full_avg60": 2}))
    assert wl.pool_limits(tmp_path)["max_pressure_full_avg60"] == 1  # not read
    err = capsys.readouterr().err
    assert "utility_max_pressure_full_avg60 is renamed to max_pressure_full_avg60" in err


def test_a_retired_load5_key_is_ignored_with_a_note(tmp_path, capsys):
    (tmp_path / "pool.json").write_text(json.dumps({"max_load5": 1000, "utility_max_load5": 30}))
    limits = wl.pool_limits(tmp_path)
    assert "max_load5" not in limits and limits == wl.POOL_DEFAULTS
    err = capsys.readouterr().err
    assert "max_load5 is no longer read" in err and "utility_max_load5 is no longer read" in err


def test_a_host_root_outside_a_test_run_warns_once(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(wl, "_host_root_told", [])
    monkeypatch.setenv(wl.HOST_ROOT_ENV, str(tmp_path))
    assert wl._host("/proc/meminfo") == tmp_path / "proc" / "meminfo"
    assert capsys.readouterr().err == ""  # the test run (conftest.py) sets WE_TEST_RUN
    monkeypatch.delenv(wl.TEST_RUN_ENV)
    wl._host("/proc/meminfo")
    wl._host("/proc/self/cgroup")
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and f"WE_WORKER_HOST_ROOT={tmp_path} outside a test run" in err


def test_queued_limits_take_the_lane_cap_and_only_the_repo_keys(tmp_path):
    machine = wl.POOL_DEFAULTS
    own = {"max_busy_sessions": 3, "max_utility_sessions": 2, "max_active_5h_percent": 50}
    assert wl.queued_limits({"repo_limits": own}, machine) == (3, 50)
    assert wl.queued_limits({"repo_limits": own, "lane": "utility"}, machine) == (2, 50)
    assert wl.queued_limits({"repo_limits": {"max_busy_sessions": 99}}, machine) == (8, 80)
    assert wl.queued_limits({"repo_limits": {"max_busy_sessions": True}}, machine) == (8, 80)
    # a repo lowers the caps and the 5h limit; the resource thresholds stay the machine's
    (tmp_path / ".weside").mkdir()
    (tmp_path / ".weside" / "config.json").write_text(
        json.dumps({"workers": {**own, "max_load5": 5, "max_working_set_ratio": 0.5}})
    )
    assert wl.repo_limits(tmp_path) == own


def _queue_entry(state_dir, name, queued_at, waiter_pid, repo_limits=None):
    (state_dir / "queue").mkdir(parents=True, exist_ok=True)
    doc = {"name": name, "queued_at": queued_at, "waiter_pid": waiter_pid}
    if repo_limits is not None:
        doc["repo_limits"] = repo_limits
    (state_dir / "queue" / f"{name}.json").write_text(json.dumps(doc))


def test_capacity_starts_the_queue_in_arrival_order_across_repos(cap, tmp_path, monkeypatch):
    """Red arm (21.11.): a start in core ran at once while infra's queued start sat at position 1
    since 01:20. A start that is not queued now waits behind every living queued one."""
    state_dir = tmp_path / "state"
    _queue_entry(state_dir, "INFRA-1-old", 100.0, os.getpid())
    out = cap(1, 10.0)
    assert out.returncode == 3
    assert "1 queued start(s) ahead (first INFRA-1-old, queued 00:01 UTC; 1 workers busy" in (
        out.stderr
    )
    # the waiter of that entry starts it (its own entry is no start ahead of it)
    monkeypatch.setenv("WE_WORKER_QUEUE_TURN", "INFRA-1-old")
    assert cap(1, 10.0).returncode == 0
    # a younger entry waits behind the older one, whatever its repo
    _queue_entry(state_dir, "CORE-2-new", 200.0, os.getpid())
    assert cap(1, 10.0).returncode == 0
    monkeypatch.setenv("WE_WORKER_QUEUE_TURN", "CORE-2-new")
    assert cap(1, 10.0).returncode == 3
    # an entry whose waiter is gone holds nobody up
    _queue_entry(state_dir, "INFRA-1-old", 100.0, 0)
    assert cap(1, 10.0).returncode == 0


def test_two_starts_queued_in_the_same_second_take_turns_by_name(cap, tmp_path, monkeypatch):
    """T2 panel on #308: with `<=` on `queued_at` two entries of the same second each saw the
    other ahead and both waited out their timeout. The name breaks the tie."""
    state_dir = tmp_path / "state"
    _queue_entry(state_dir, "AC-1-a", 100.0, os.getpid())
    _queue_entry(state_dir, "AC-2-b", 100.0, os.getpid())
    monkeypatch.setenv("WE_WORKER_QUEUE_TURN", "AC-1-a")
    assert cap(1, 10.0).returncode == 0
    monkeypatch.setenv("WE_WORKER_QUEUE_TURN", "AC-2-b")
    out = cap(1, 10.0)
    assert out.returncode == 3 and "(first AC-1-a," in out.stderr


def test_a_queued_start_held_only_by_its_own_repo_limit_holds_nobody_up(
    cap, tmp_path, monkeypatch
):
    """T2 panel on #308: a head from a repo with a lower 5h limit held every other repo's start
    for up to 2 h. While the machine has room, such a head stays first and lets others pass."""
    state_dir = tmp_path / "state"
    _queue_entry(state_dir, "PUB-1-strict", 100.0, os.getpid(), {"max_active_5h_percent": 30})
    assert cap(1, 50.0).returncode == 0  # 50 % is over the head's 30, under the machine's 80
    assert cap(1, 20.0).returncode == 3  # the head's limit passes: it goes first
    assert cap(1, 90.0).returncode == 3  # the machine is full: first come, first served
    _queue_entry(state_dir, "PUB-1-strict", 100.0, os.getpid(), {"max_busy_sessions": 2})
    assert cap(2, 10.0).returncode == 0  # its busy limit is its own too
    assert cap(1, 10.0).returncode == 3
    _queue_entry(state_dir, "PUB-1-strict", 100.0, os.getpid())  # without its own: it holds
    assert cap(1, 50.0).returncode == 3
    # the head's own waiter still checks its own limit
    _queue_entry(state_dir, "PUB-1-strict", 100.0, os.getpid(), {"max_active_5h_percent": 30})
    monkeypatch.setenv("WE_WORKER_QUEUE_TURN", "PUB-1-strict")
    assert cap(1, 50.0, {"max_active_5h_percent": 30}).returncode == 3
    assert cap(1, 20.0, {"max_active_5h_percent": 30}).returncode == 0


def test_capacity_without_cswap_on_path_skips_the_window_check_silently(
    monkeypatch, tmp_path, capsys
):
    """Claude Review on #229: cswap is optional; its absence is no warning on every start."""
    monkeypatch.setattr(wl.shutil, "which", lambda _name: None)
    monkeypatch.setattr(wl, "sessions", list)
    monkeypatch.setenv("WE_WORKER_STATE_DIR", str(tmp_path / "state"))  # no live queue
    wl.capacity(tmp_path, "we-worker")
    assert capsys.readouterr().err == ""


def test_capacity_counts_busy_background_sessions_only(cap, env):
    """Interactive companions answering their humans are busy too. Red arm: five busy
    companions let the default limit of 10 start only five workers."""
    rows = [{"name": f"C{i}", "kind": "interactive", "status": "busy", "pid": 1} for i in range(5)]
    rows += [{"name": f"W{i}", "kind": "background", "status": "busy", "pid": 1} for i in range(5)]
    cap(0, 10.0)
    env["state"].write_text(json.dumps(rows))
    out = _run("capacity", "--repo", str(env["wt"]), "--prefix", "we-worker")
    assert out.returncode == 0, out.stderr
    env["state"].write_text(json.dumps(rows + rows[5:]))
    out = _run("capacity", "--repo", str(env["wt"]), "--prefix", "we-worker")
    assert out.returncode == 3 and "10 workers busy" in out.stderr
    # a window worker is interactive too, and still counts: its tree carries the launcher marker
    gd = subprocess.run(
        ["git", "-C", str(env["wt"]), "rev-parse", "--absolute-git-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    Path(gd, "we-worker.json").write_text(json.dumps({"name": "KEY-1-win"}))
    win = {
        "name": "KEY-1-win",
        "sessionId": "s-win",
        "kind": "interactive",
        "status": "busy",
        "pid": 1,
        "cwd": str(env["wt"]),
    }
    env["state"].write_text(json.dumps([*rows, *rows[5:9], win]))  # 5 companions, 9 + 1 workers
    out = _run("capacity", "--repo", str(env["wt"]), "--prefix", "we-worker")
    assert out.returncode == 3 and "10 workers busy" in out.stderr, out.stderr


# --- the utility lane ------------------------------------------------------------------------


@pytest.fixture
def lanes(tmp_path, monkeypatch):
    """In-process `capacity` with `build` and `utility` busy workers, no cswap, room on the
    machine; returns `(code, stderr)` of a start in `lane`."""
    state = tmp_path / "lanes"
    state.mkdir()
    monkeypatch.setenv("WE_WORKER_STATE_DIR", str(state))
    monkeypatch.setattr(wl.shutil, "which", lambda _name: None)
    group = tmp_path / "cg"
    group.mkdir()

    def run(build, utility, lane, done=0, pool=None, cgroup=group):
        rows = []
        for i in range(utility):
            name = f"U-{i}-fix"
            (state / f"{name}.settings.json").write_text(
                json.dumps({"env": {wl.LANE_ENV: wl.UTILITY}})
            )
            rows.append({"name": name, "status": "busy", "state": "working", "pid": 1})
        rows += [{"name": f"B-{i}-build", "status": "busy", "pid": 1} for i in range(build)]
        rows += [
            {"name": f"D-{i}-card", "status": "busy", "state": "done", "pid": 1}
            for i in range(done)
        ]
        monkeypatch.setattr(wl, "sessions", lambda: rows)
        if pool is not None:
            (state / "pool.json").write_text(json.dumps(pool))
        try:
            wl.capacity(tmp_path, "we-worker", lane, cgroup, tmp_path / "meminfo")
        except wl.LaunchError as exc:
            return exc.code, str(exc)
        return 0, ""

    return {"run": run, "state": state, "cgroup": group}


def test_a_utility_start_passes_a_full_build_lane_and_has_its_own_cap_and_queue(lanes):
    """Red arm (22.11.): a fix round for two review warnings waited over an hour behind build
    starts in the one pool. Default 5 without pool.json; a `done` worker counts in no lane."""
    run = lanes["run"]
    assert run(8, 0, "build")[0] == 3
    assert run(8, 4, "utility") == (0, "")
    code, err = run(8, 5, "utility")
    assert code == 3 and "utility lane: 5 workers busy (limit 5 for the machine" in err
    assert "max_utility_sessions" in err and "build lane 8 busy, limit 8" in err
    assert run(8, 4, "utility", done=3) == (0, "")  # a reported worker works no more
    assert run(7, 0, "build", done=3) == (0, "")
    assert run(2, 2, "utility", pool={"max_utility_sessions": 2})[0] == 3
    # each lane waits only behind its own queue
    _queue_entry(lanes["state"], "B-9-queued", 100.0, os.getpid())
    assert run(1, 0, "utility") == (0, "")
    assert run(1, 0, "build")[0] == 3
    _queue_entry(lanes["state"], "U-9-queued", 100.0, os.getpid())
    doc = json.loads((lanes["state"] / "queue" / "U-9-queued.json").read_text())
    (lanes["state"] / "queue" / "U-9-queued.json").write_text(
        json.dumps({**doc, "lane": "utility"})
    )
    code, err = run(1, 0, "utility")
    assert code == 3 and "utility lane: 1 queued start(s) ahead (first U-9-queued" in err


def _cgroup(group, used_pct=50, file_mib=0, shmem_mib=0, full_avg60=0.0, limit_mib=8192):
    """A cgroup whose working set is `used_pct` % of `limit_mib`; `file_mib` page cache and
    `shmem_mib` shared memory come on top of `memory.current` as the kernel counts them."""
    (group / "memory.max").write_text(f"{limit_mib * wl.MIB}\n")
    current = (limit_mib * used_pct // 100 + file_mib - shmem_mib) * wl.MIB
    (group / "memory.current").write_text(f"{current}\n")
    (group / "memory.stat").write_text(
        f"anon 1\nfile {file_mib * wl.MIB}\nshmem {shmem_mib * wl.MIB}\n"
        f"inactive_file {file_mib // 2 * wl.MIB}\n"
    )
    (group / "memory.pressure").write_text(
        "some avg10=0.00 avg60=0.00 avg300=0.00 total=1\n"
        f"full avg10=0.00 avg60={full_avg60:.2f} avg300=0.00 total=1\n"
    )


def test_the_working_set_drops_page_cache_and_keeps_shmem(tmp_path):
    """Kiska (22.11.): `current - file + shmem`; `current - inactive_file` read 10 GiB high
    through active_file."""
    group = tmp_path / "cg"
    group.mkdir()
    (group / "memory.max").write_text(f"{1000 * wl.MIB}\n")
    (group / "memory.current").write_text(f"{900 * wl.MIB}\n")
    (group / "memory.stat").write_text(
        f"file {300 * wl.MIB}\nshmem {50 * wl.MIB}\ninactive_file {100 * wl.MIB}\n"
    )
    assert wl.working_set(group, tmp_path / "meminfo") == (650 * wl.MIB, 1000 * wl.MIB)
    # no limit: MemTotal of /proc/meminfo is the ceiling
    (group / "memory.max").write_text("max\n")
    (tmp_path / "meminfo").write_text("MemTotal:        2048000 kB\nMemFree:  1 kB\n")
    assert wl.working_set(group, tmp_path / "meminfo") == (650 * wl.MIB, 2048000 * 1024)
    rows = wl.resources(wl.POOL_DEFAULTS, group, tmp_path / "meminfo")
    assert rows[0]["value"] == "32% (0.6 of 2.0 GiB)" and rows[0]["ok"]
    (tmp_path / "meminfo").unlink()  # neither a limit nor meminfo: n/a, met
    assert wl.working_set(group, tmp_path / "meminfo") is None


def test_a_start_of_either_lane_waits_for_room_and_names_the_missed_condition(lanes, tmp_path):
    """Kiska's rule (22.11.): working set < 84 % of memory.max and pressure full avg60 < 1, for
    both lanes; an unreadable source counts as met and reads `n/a`. No load average condition."""
    run, group = lanes["run"], lanes["cgroup"]
    _cgroup(group, used_pct=77, file_mib=3000, shmem_mib=100)  # page cache is no load
    assert run(0, 0, "utility") == (0, "")
    assert run(0, 0, "build") == (0, "")
    _cgroup(group, used_pct=86)
    for lane in wl.LANES:
        code, err = run(0, 0, lane)
        assert code == wl.RESOURCE_HALT, err
        assert f"{lane} lane waits for room" in err and "refused" not in err
        assert "working set 86% (6.9 of 8.0 GiB) (needs < 84%)" in err
        assert "pressure" not in err  # only the missed condition
    assert run(0, 0, "build", pool={"max_working_set_ratio": 0.9}) == (0, "")
    assert run(0, 0, "build", pool={"max_working_set_ratio": 1}) == (0, "")  # the ceiling itself
    code, err = run(0, 0, "build", pool={"max_working_set_ratio": 84})  # a percent, not a share
    assert code == 2 and "0 < r <= 1, not 84" in err
    (lanes["state"] / "pool.json").unlink()
    _cgroup(group, full_avg60=1.0)
    assert "memory pressure full avg60 1 (needs < 1)" in run(0, 0, "build")[1]
    _cgroup(group)
    assert run(0, 0, "utility") == (0, "")  # a busy CPU alone never holds a start
    # the cap is checked first and still refuses with 3
    assert run(8, 0, "build")[0] == 3
    # no cgroup v2, no meminfo: met, shown as n/a
    rows = wl.resources(wl.pool_limits(lanes["state"]), tmp_path / "none", tmp_path / "none")
    assert all(r["ok"] for r in rows) and [r["value"] for r in rows] == [None, None]
    assert wl.resource_text(rows[:1]) == "working set n/a (needs < 84%)"
    assert run(0, 0, "build", cgroup=tmp_path / "none") == (0, "")


# --- needs: a skill's frontmatter `needs:` against workers.context ------------------------------


def _needs(repo, brief, *extra):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "needs",
            "--repo",
            str(repo),
            "--prefix",
            "we-worker",
            *extra,
        ],
        input=brief,
        capture_output=True,
        text=True,
        check=False,
    )


def _config(repo, ticketing=None, disable=(), deny=()):
    (repo / ".weside").mkdir(exist_ok=True)
    cfg = {
        "workers": {"context": {"disable_plugins": list(disable), "deny_mcp_servers": list(deny)}}
    }
    if ticketing is not None:
        cfg["ticketing"] = ticketing
    (repo / ".weside" / "config.json").write_text(json.dumps(cfg))


def test_brief_skills_reads_every_form_once():
    brief = 'Skill("we:plan-story")\n/we:plan-story then /we:develop; agent we:dev-medium\n'
    assert wl.brief_skills(brief) == ["plan-story", "develop", "dev-medium"]
    assert wl.brief_skills("see https://example.org/x/we:pr and wewe:pr") == []


def test_the_ticketing_skills_declare_the_need():
    for skill in ("plan-story", "merged", "pr", "epic", "master", "accept", "standup"):
        assert wl.skill_needs(skill) == ["ticketing"], skill
    for skill in ("grill", "develop", "ci-review"):  # build and fix workers touch no ticket
        assert wl.skill_needs(skill) == [], skill
    assert wl.skill_needs("no-such-skill") == []


def test_a_named_skill_whose_ticketing_plugin_is_disabled_refuses(env):
    # key absent, tool mapped (jira → atlassian), the plugin disabled by its id
    _config(env["wt"], {"tool": "jira"}, disable=["atlassian@claude-plugins-official"])
    proc = _needs(env["wt"], 'Run Skill("we:plan-story") for KEY-1.\n')
    assert proc.returncode == 2
    assert (
        "/we:plan-story" in proc.stderr
        and "atlassian (the project's ticketing plugin)" in proc.stderr
    )
    assert "disable_plugins turns it off (atlassian@claude-plugins-official)" in proc.stderr
    assert proc.stderr.startswith("we-worker: ") and "no worker started" in proc.stderr


def test_ticketing_plugin_overrides_the_default_map(env):
    _config(
        env["wt"],
        {"tool": "jira", "plugin": "tracker"},
        disable=["atlassian@claude-plugins-official"],
    )
    assert _needs(env["wt"], "/we:pr KEY-1\n").returncode == 0  # the map is not consulted
    _config(env["wt"], {"tool": "jira", "plugin": ["tracker"]}, disable=["tracker@market"])
    proc = _needs(env["wt"], "/we:pr KEY-1\n")
    assert proc.returncode == 2 and "turns it off (tracker@market)" in proc.stderr


def test_a_ticketing_server_the_context_denies_refuses(env):
    _config(env["wt"], {"tool": "jira", "plugin": "tickets"}, deny=["tickets"])
    proc = _needs(env["wt"], "/we:merged\n")
    assert proc.returncode == 2
    assert "deny_mcp_servers turns it off (tickets)" in proc.stderr and "/we:merged" in proc.stderr


@pytest.mark.parametrize(
    "ticketing",
    [{"tool": "github-issues"}, {"tool": "none"}, None],  # unmapped tool, no ticketing, no block
)
def test_an_unmapped_ticketing_tool_needs_nothing(env, ticketing):
    _config(env["wt"], ticketing, disable=["atlassian@claude-plugins-official"])
    assert _needs(env["wt"], "/we:plan-story\n").returncode == 0


def test_a_skill_without_needs_and_a_repo_without_context_pass(env):
    _config(env["wt"], {"tool": "jira"}, disable=["atlassian@claude-plugins-official"])
    assert _needs(env["wt"], "/we:grill the plan\n").returncode == 0
    (env["wt"] / ".weside" / "config.json").write_text(json.dumps({"ticketing": {"tool": "jira"}}))
    assert _needs(env["wt"], "/we:plan-story\n").returncode == 0


def test_a_skill_naming_a_plugin_itself_refuses(env, tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    (skills / "grill").mkdir(parents=True)
    (skills / "grill" / "SKILL.md").write_text(
        "---\nname: grill\ndescription: x\nneeds: [sentry, 'ticketing']\n---\n# grill\n"
    )
    monkeypatch.setattr(wl, "SKILLS_DIR", skills)
    assert wl.skill_needs("grill", skills) == ["sentry", "ticketing"]
    _config(env["wt"], deny=["sentry"])
    with pytest.raises(wl.LaunchError) as refused:
        wl.check_needs("/we:grill\n", env["wt"])
    assert refused.value.code == 2 and "/we:grill, which needs sentry," in str(refused.value)


def test_needs_all_lists_every_skill_the_context_starves(env):
    _config(env["wt"], {"tool": "jira"}, disable=["atlassian"])
    proc = _needs(env["wt"], "", "--all")
    assert proc.returncode == 2
    named = {line.split("/we:")[1].split(",")[0] for line in proc.stdout.splitlines()}
    assert {"plan-story", "merged", "pr", "epic"} <= named and "develop" not in named
    _config(env["wt"], {"tool": "github-issues"}, disable=["atlassian"])
    proc = _needs(env["wt"], "", "--all")
    assert (proc.returncode, proc.stdout) == (0, "")


# --- ticketing_unneeded: the ticketing plugin loads only for a brief that needs it ---------------

INSTALLED = ["atlassian@claude-plugins-official", "sentry@claude-plugins-official"]


@pytest.mark.parametrize(
    ("brief", "off"),
    [
        ("/we:develop KEY-1\n", ["atlassian"]),  # build worker: no ticket
        ("/we:ci-review on #12\n", ["atlassian"]),
        ("/we:develop KEY-1\nNeeds: ticketing\n", []),  # the brief asks for it
        ("/we:develop KEY-1\nNeeds: `atlassian@claude-plugins-official`\n", []),
        ("/we:develop then /we:pr\n", []),  # one skill needs it
        ('Run Skill("we:develop")\nPR owner: worker — open the PR with /we:pr\n', []),
        ('Run Skill("we:plan-story") for KEY-1.\n', []),
        ("Fix the flaky test in board.py.\n", []),  # no skill: every tool stays
        ("", []),
    ],
)
def test_ticketing_unneeded_follows_the_briefs_skills(env, brief, off):
    _config(env["wt"], {"tool": "jira"})
    assert wl.ticketing_unneeded(brief, env["wt"]) == off


@pytest.mark.parametrize("ticketing", [{"tool": "github-issues"}, {"tool": "none"}, None])
def test_no_ticketing_plugin_turns_nothing_off(env, ticketing):
    _config(env["wt"], ticketing)
    assert wl.ticketing_unneeded("/we:develop KEY-1\n", env["wt"]) == []


def test_the_configured_ticketing_plugin_is_the_one_turned_off(env):
    _config(env["wt"], {"tool": "jira", "plugin": ["tracker", "tracker-mcp"]})
    assert wl.ticketing_unneeded("/we:develop\n", env["wt"]) == ["tracker", "tracker-mcp"]
    assert wl.ticketing_unneeded("/we:develop\nNeeds: tracker\n", env["wt"]) == []


def test_a_pointer_brief_is_read_through_its_file(env, tmp_path):
    _config(env["wt"], {"tool": "jira"})
    (tmp_path / "b.md").write_text("/we:develop\nPlugin we, one PR.\n")
    pointer = f"Read {tmp_path / 'b.md'} and follow it.\n"
    assert wl.ticketing_unneeded(pointer, env["wt"]) == ["atlassian"]
    (tmp_path / "b.md").write_text("/we:merged\n")
    assert wl.ticketing_unneeded(pointer, env["wt"]) == []
    missing = f"Read {tmp_path / 'gone.md'} and follow it.\n"
    assert wl.ticketing_unneeded(missing, env["wt"]) == []  # unreadable: no skill, all stays


def test_turn_off_disables_an_installed_plugin_and_denies_any_other_server():
    doc = wl.turn_off({"env": {}}, ["atlassian", "tickets"], INSTALLED)
    assert doc["enabledPlugins"] == {"atlassian@claude-plugins-official": False}
    assert doc["deniedMcpServers"] == [{"serverName": "tickets"}]
    assert wl.turn_off({}, [], INSTALLED) == {}


def test_settings_verb_turns_the_ticketing_plugin_off_for_a_develop_brief(env, tmp_path):
    _config(env["wt"], {"tool": "jira"})
    home = tmp_path / "claude-home"
    (home / "plugins").mkdir(parents=True)
    (home / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"plugins": {i: [] for i in INSTALLED}})
    )
    out = tmp_path / "w.settings.json"

    def settings(brief):
        subprocess.run(
            [sys.executable, str(SCRIPT), "settings", "--repo", str(env["wt"]), "--key", "KEY-1",
             "--out", str(out), "--brief-stdin"],
            input=brief, text=True, check=True, capture_output=True,
            env={**os.environ, "CLAUDE_CONFIG_DIR": str(home)},
        )  # fmt: skip
        return json.loads(out.read_text())

    assert settings("/we:develop KEY-1\n")["enabledPlugins"] == {
        "atlassian@claude-plugins-official": False
    }
    assert "enabledPlugins" not in settings("/we:pr KEY-1\n")
    assert "enabledPlugins" not in settings("")


# ---------------------------------------------------------------- build.pr_owner


@pytest.mark.parametrize(
    ("config", "owner"),
    [
        ({}, "master"),
        ({"build": {}}, "master"),
        ({"build": "x"}, "master"),
        ({"build": {"pr_owner": "master"}}, "master"),
        ({"build": {"pr_owner": "worker"}}, "worker"),
    ],
)
def test_pr_owner_reads_the_switch_with_master_as_default(config, owner):
    assert wl.pr_owner_of(config) == owner


def test_pr_owner_refuses_another_value():
    with pytest.raises(wl.LaunchError) as exc:
        wl.pr_owner_of({"build": {"pr_owner": "everyone"}})
    assert exc.value.code == 2 and "build.pr_owner" in str(exc.value)


def test_pr_owner_verb_prints_the_worktrees_value(tmp_path, capsys):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert wl.main(["pr-owner", "--repo", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == "master"
    (tmp_path / ".weside").mkdir()
    (tmp_path / ".weside" / "config.json").write_text(
        json.dumps({"build": {"pr_owner": "worker"}})
    )
    assert wl.main(["pr-owner", "--repo", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == "worker"
    (tmp_path / ".weside" / "config.json").write_text(json.dumps({"build": {"pr_owner": "x"}}))
    assert wl.main(["pr-owner", "--repo", str(tmp_path)]) == 2


class TestAccountAnswer:
    @pytest.mark.parametrize(
        "answer, account, need, refusal",
        [
            ({"name": "a", "kind": "api", "env": {}}, "auto", "critical", "only on a claude"),
            (
                {"name": "a", "kind": "claude", "env": {"ANTHROPIC_API_KEY": "x"}},
                "auto",
                "critical",
                "token_command",
            ),
            ({"name": "b", "kind": "claude"}, "a", "critical", "answered b for --account a"),
            ({"kind": "claude"}, "auto", "critical", "a `name` and a `kind`"),
            (["a"], "auto", "critical", "no JSON object"),
            (
                {"name": "a", "kind": "claude", "env": {"CLAUDE_CONFIG_DIR": "/p"}},
                "auto",
                "critical",
                "sets CLAUDE_CONFIG_DIR",
            ),
            (
                {"name": "a", "kind": "claude", "env": {"WE_WORKER_NO_SUPERVISOR": "1"}},
                "auto",
                "critical",
                "sets WE_WORKER_NO_SUPERVISOR",
            ),
            (
                {"name": "a", "kind": "claude", "env": {"WESIDE_COMPANION": "x"}},
                "auto",
                "critical",
                "sets WESIDE_COMPANION",
            ),
        ],
    )
    def test_a_bad_or_forbidden_answer_refuses(self, answer, account, need, refusal):
        with pytest.raises(wl.LaunchError, match=re.escape(refusal)) as exc:
            wl._checked_account(answer, account, need)
        assert exc.value.code == 2

    @pytest.mark.parametrize(
        "name, secret",
        [
            ("ANTHROPIC_API_KEY", True),
            ("ANTHROPIC_AUTH_TOKEN", True),
            ("DB_PASSWORD", True),
            ("CLAUDE_CODE_MAX_OUTPUT_TOKENS", False),
            ("CLAUDE_CODE_API_KEY_HELPER_TTL_MS", False),
            ("ANTHROPIC_BASE_URL", False),
            ("OPENAI_APIKEY", True),
            ("GITHUB_PAT", True),
            ("DB_PASSWD", True),
            ("PROXY_AUTH", True),
            ("CLAUDE_CODE_SKIP_BEDROCK_AUTH", False),
            ("CLAUDE_CODE_SKIP_VERTEX_AUTH", False),
        ],
    )
    def test_only_a_credential_name_counts_as_secret(self, name, secret):
        assert bool(wl.SECRET_NAME_RE.search(name)) is secret

    def test_the_cli_settings_stay_open(self):
        chosen = wl._checked_account(
            {"name": "a", "kind": "claude", "env": {"CLAUDE_CODE_USE_BEDROCK": "1"}},
            "auto",
            "critical",
        )
        assert chosen["env"] == {"CLAUDE_CODE_USE_BEDROCK": "1"}

    def test_the_account_file_is_private(self, tmp_path):
        out = tmp_path / "a.json"
        wl._write_private(out, "{}\n")
        assert out.stat().st_mode & 0o777 == 0o600

    def test_an_uncritical_need_takes_another_llm(self):
        chosen = wl._checked_account(
            {"name": "g", "kind": "other-llm", "env": {"X_URL": "u"}, "token_command": "h"},
            "auto",
            "uncritical",
        )
        doc = wl.apply_account({"env": {"WE_ROLE": "worker", "X_URL": "mine"}}, chosen)
        assert doc == {"env": {"X_URL": "mine", "WE_ROLE": "worker"}, "apiKeyHelper": "h"}

    @pytest.mark.parametrize(
        "brief, need",
        [
            ("## Goal\n\nx\n", "critical"),
            ("## Goal\n\nAccount: uncritical\n", "uncritical"),
            ("## Goal\n" + "ticket text\n" * 12 + "Account: uncritical\n", "critical"),
        ],
    )
    def test_the_brief_names_the_need(self, brief, need):
        assert wl.brief_account_need(brief) == need


# --- the starter log -------------------------------------------------------


def _append_many(args):
    state, i = args
    for j in range(5):
        wl.record_launch(f"AC-{i}-w{j}", f"AC-{i}", "m-1", "sid-m", Path(state), pad="x" * 30000)


def test_launched_log_survives_marker_and_parallel_writers(tmp_path, monkeypatch):
    """AC1: the marker goes when its worker ends, the starter stays in `launched.jsonl`; 20
    launchers at once leave whole lines. Red arm: a split write interleaves the 30 kB lines."""
    import multiprocessing  # noqa: PLC0415

    import flow_intervals as fi  # noqa: PLC0415
    import worker_supervisor as sup  # noqa: PLC0415

    state = tmp_path / "state"
    monkeypatch.setenv("WE_WORKER_STATE_DIR", str(state))
    tree = tmp_path / "tree"
    tree.mkdir()
    _git(tree, "init", "-q")
    wl.write_marker(
        tree, name="AC-9-build", key="AC-9", role="worker", starter="m-1", starter_session="sid-m"
    )
    (state / "AC-9-build.json").write_text('{"name": "AC-9-build", "starter": "m-1"}')
    sup._remove_files(state, "AC-9-build")
    assert not (state / "AC-9-build.json").exists()
    src = fi.Sources(None, None)
    line = fi.read_launched(src, state)["AC-9-build"]
    assert (line["starter"], line["starter_session"], line["key"]) == ("m-1", "sid-m", "AC-9")
    assert set(line) == {"name", "key", "starter", "starter_session", "ts"}

    with multiprocessing.get_context("fork").Pool(20) as pool:
        pool.map(_append_many, [(str(state), i) for i in range(20)])
    rows, bad = wl.read_launched(state)
    assert bad == 0 and len(rows) == 1 + 100
    assert all(r["pad"] == "x" * 30000 for r in rows[1:])


def test_backfill_starters_dry_apply_and_no_transcript_text(tmp_path, capsys):
    """AC2: timing line first, then the transcript's starter line (only its name), else
    `unrecoverable`; dry writes nothing. Red arm: a transcript line reaches stdout or the log."""
    state, timing, projects = tmp_path / "state", tmp_path / "timing", tmp_path / "projects"
    timing.mkdir()
    (timing / "sid-master.jsonl").write_text(
        json.dumps({"ts": 1, "event": "WorkerLaunch", "name": "AC-1-a", "cwd": "/x"}) + "\n"
    )
    (projects / "p").mkdir(parents=True)
    secret = "ghp_" + "S3cr3tT0k3n" * 3
    (projects / "p" / "sid-b.jsonl").write_text(
        json.dumps({"type": "user", "message": {"content": f"token {secret}"}})
        + "\n"
        + json.dumps(
            {"type": "attachment", "content": f"we-worker: Dein Starter ist Kiska. {secret}"}
        )
        + "\n"
    )
    (projects / "p" / "sid-c.jsonl").write_text(
        json.dumps({"type": "user", "content": secret}) + "\n"
    )
    workers = [("AC-1-a", "sid-a"), ("AC-2-b", "sid-b"), ("AC-3-c", "sid-c"), ("AC-4-d", None)]
    kw = {
        "state": state,
        "timing": timing,
        "projects": projects,
        "session_names": {"sid-master": "m-1"},
    }
    dry = wl.backfill_starters(workers, False, **kw)
    assert dry == [
        "AC-1-a: would use timing -> m-1",
        "AC-2-b: would use transcript -> Kiska",
        "AC-3-c: unrecoverable",
        "AC-4-d: unrecoverable",
    ]
    assert not (state / wl.LAUNCHED).exists()
    done = wl.backfill_starters(workers, True, **kw)
    rows, bad = wl.read_launched(state)
    assert bad == 0
    assert [(r["name"], r["starter"], r["backfill"]) for r in rows] == [
        ("AC-1-a", "m-1", "timing"),
        ("AC-2-b", "Kiska", "transcript"),
    ]
    assert rows[0]["starter_session"] == "sid-master" and rows[1]["starter_session"] is None
    text = "\n".join(dry + done) + capsys.readouterr().out + (state / wl.LAUNCHED).read_text()
    assert secret not in text and "token" not in text


def test_starters_json_snapshot(tmp_path):
    """AC7: `starters --json` carries `schema_version` and `generated_at`; its field list is pinned."""
    state = tmp_path / "state"
    wl.record_launch("AC-1-a", "AC-1", "m-1", "sid-m", state)
    wl.record_launch("AC-1-a", "AC-1", "m-2", None, state)
    (state / wl.LAUNCHED).open("a").write("not json\n")
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "starters", "--json"],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "WE_WORKER_STATE_DIR": str(state)},
    ).stdout
    doc = json.loads(out)
    assert sorted(doc) == ["generated_at", "path", "schema_version", "starters", "unreadable"]
    assert doc["schema_version"] == 1 and doc["unreadable"] == 1
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", doc["generated_at"])
    (only,) = doc["starters"]
    assert sorted(only) == ["key", "name", "starter", "starter_session", "ts"]
    assert only["starter"] == "m-2"
