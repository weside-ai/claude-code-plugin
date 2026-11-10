"""start.py: the coordinator's start plan and the in-session check, from the crew alone."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import start

CREW = {
    "version": 2,
    "roles": {"coordinator": "lead", "product": "po"},
    "members": {"lead": {"name": "Lea", "pin": True}, "po": {"name": "Ada"}},
    "launch": {"restore": "python3 /opt/restore.py"},
}


def repo(tmp_path, crew=CREW):
    root = tmp_path / "repo"
    (root / ".weside").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / ".weside" / "crew.json").write_text(json.dumps(crew))
    return root


def no_agents():
    return []


def transcript(projects, root, sid, lines, mtime):
    folder = projects / start.project_slug(root)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sid}.jsonl"
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    os.utime(path, (mtime, mtime))


def test_plan_names_coordinator_pin_workplace_and_last_session(tmp_path):
    root = repo(tmp_path)
    cfg = tmp_path / "cfg"
    transcript(
        cfg / "projects", root, "old", [{"type": "custom-title", "customTitle": "Lea"}], 100
    )
    transcript(cfg / "projects", root, "new", [{"type": "agent-name", "agentName": "Lea"}], 200)
    transcript(
        cfg / "projects", root, "other", [{"type": "custom-title", "customTitle": "Ada"}], 300
    )
    env = {"CLAUDE_CONFIG_DIR": str(cfg)}
    row = f"Lea\t1\t{root}\tthe-human\tcoordinator\t"
    assert start.plan(root, False, env, no_agents) == row + "new"
    assert start.plan(root, True, env, no_agents) == row


def test_plan_unpinned_member_and_no_transcript(tmp_path):
    crew = {**CREW, "members": {"lead": {"name": "Lea"}, "po": {"name": "Ada"}}}
    root = repo(tmp_path, crew)
    assert (
        start.plan(root, False, {"CLAUDE_CONFIG_DIR": str(tmp_path / "none")}, no_agents)
        == f"Lea\t0\t{root}\tthe-human\tcoordinator\t"
    )


def test_plan_refuses_a_running_coordinator(tmp_path):
    root = repo(tmp_path)
    with pytest.raises(start.StartError, match="runs already"):
        start.plan(root, False, {}, lambda: [{"name": "Lea (2)", "pid": 7}])
    # a registry row without pid is a dead session: no refusal
    assert start.plan(root, True, {}, lambda: [{"name": "Lea"}]).startswith("Lea\t")


def test_plan_refuses_when_the_session_list_is_unreadable(tmp_path):
    def broken():
        raise start.worker_launch.LaunchError("claude agents --json timed out after 30 s")

    with pytest.raises(start.StartError, match="cannot tell whether Lea runs"):
        start.plan(repo(tmp_path), True, {}, broken)


def test_plan_without_coordinator_fails(tmp_path):
    root = repo(
        tmp_path, {"version": 2, "roles": {"product": "po"}, "members": {"po": {"name": "Ada"}}}
    )
    with pytest.raises(start.StartError, match="coordinator"):
        start.plan(root, False, {}, no_agents)


@pytest.mark.parametrize(
    "env, ok",
    [
        ({"WESIDE_COMPANION": "Lea", "WE_ROLE": "master", "CLAUDE_CONFIG_DIR": "/p"}, True),
        ({"WESIDE_COMPANION": "Lea", "WE_ROLE": "master"}, False),
        ({"WESIDE_COMPANION": "Ada", "WE_ROLE": "master", "CLAUDE_CONFIG_DIR": "/p"}, False),
        ({"WESIDE_COMPANION": "Lea", "WE_ROLE": "worker", "CLAUDE_CONFIG_DIR": "/p"}, False),
    ],
)
def test_check_against_the_crew(tmp_path, env, ok):
    lines, result = start.check(repo(tmp_path), env)
    assert result is ok
    assert len(lines) == 4
    assert lines[0] == "ok    human the-human (the human), runs product, coordinator, masters"
    if "CLAUDE_CONFIG_DIR" not in env:
        assert lines[3].startswith("FAIL") and "/we:pin on" in lines[3]


def test_restore_prints_the_crew_command_or_fails(tmp_path, capsys):
    root = repo(tmp_path)
    assert start.main(["restore", "--from", str(root)]) == 0
    assert capsys.readouterr().out.strip() == "python3 /opt/restore.py"
    bare = repo(tmp_path / "b", {k: v for k, v in CREW.items() if k != "launch"})
    assert start.main(["restore", "--from", str(bare)]) == 1


def test_pin_is_a_known_member_key(tmp_path):
    out = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parent / "crew.py"),
            "validate",
            "--strict",
            "--from",
            str(repo(tmp_path)),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 0, out.stderr


HUMANS = {
    "version": 2,
    "roles": {"coordinator": "lead", "product": "po", "acceptance": "qa"},
    "members": {
        "lead": {"name": "Lea", "pin": True},
        "po": {"name": "Ada"},
        "qa": {"name": "Tess"},
    },
    "humans": {
        "alice": {
            "name": "Alice",
            "email": "alice@example.com",
            "owns_states": ["selected", "in_progress"],
            "runs": ["coordinator", "acceptance", "masters"],
        },
        "bob": {
            "name": "Bob",
            "email": "Bob@Example.com",
            "owns_states": ["backlog"],
            "runs": ["product"],
            "companions": {"product": "Paula"},
        },
    },
}


def test_plan_starts_the_role_the_human_runs_under_the_human_s_name(tmp_path):
    root = repo(tmp_path, HUMANS)
    bob = {"WE_HUMAN": "bob", "CLAUDE_CONFIG_DIR": str(tmp_path / "none")}
    assert start.plan(root, True, bob, no_agents) == f"Paula\t0\t{root}\tbob\tproduct\t"
    with pytest.raises(start.StartError, match="bob does not run coordinator"):
        start.plan(root, True, bob, no_agents, role="coordinator")
    alice = {"WE_HUMAN": "alice"}
    assert start.plan(root, True, alice, no_agents).startswith("Lea\t1\t")
    assert start.plan(root, True, alice, no_agents, role="acceptance").startswith("Tess\t0\t")
    assert start.others(root, None, alice) == [
        "alice also runs acceptance (Tess): wclaude --start --role acceptance"
    ]
    # a running Paula refuses a second one, by the display name
    with pytest.raises(start.StartError, match="Paula runs already"):
        start.plan(root, True, bob, lambda: [{"name": "Paula", "pid": 3}])


def test_plan_resolves_the_human_from_git_email(tmp_path, monkeypatch):
    root = repo(tmp_path, HUMANS)
    monkeypatch.setattr(start.crewlib, "git_email", lambda _cwd=None: "bob@example.com")
    assert start.plan(root, True, {}, no_agents).split("\t")[3:5] == ["bob", "product"]
    monkeypatch.setattr(start.crewlib, "git_email", lambda _cwd=None: "eve@example.com")
    with pytest.raises(start.StartError, match="none is you"):
        start.plan(root, True, {}, no_agents)
    with pytest.raises(start.StartError, match="WE_HUMAN=eve is no human"):
        start.plan(root, True, {"WE_HUMAN": "eve"}, no_agents)


def test_check_prints_the_human_line_and_the_human_s_companion(tmp_path):
    root = repo(tmp_path, HUMANS)
    env = {
        "WE_HUMAN": "bob",
        "WE_ROLE_ID": "product",
        "WESIDE_COMPANION": "Paula",
        "WE_ROLE": "master",
    }
    lines, ok = start.check(root, env)
    assert ok, lines
    assert lines[0] == "ok    human bob (Bob), runs product"
    lines, ok = start.check(root, {**env, "WE_ROLE_ID": "coordinator"})
    assert not ok and lines[0].startswith("FAIL  human: bob does not run coordinator")
