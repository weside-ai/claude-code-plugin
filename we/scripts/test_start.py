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
    assert start.plan(root, False, env, no_agents) == f"Lea\t1\t{root}\tnew"
    assert start.plan(root, True, env, no_agents) == f"Lea\t1\t{root}\t"


def test_plan_unpinned_member_and_no_transcript(tmp_path):
    crew = {**CREW, "members": {"lead": {"name": "Lea"}, "po": {"name": "Ada"}}}
    root = repo(tmp_path, crew)
    assert (
        start.plan(root, False, {"CLAUDE_CONFIG_DIR": str(tmp_path / "none")}, no_agents)
        == f"Lea\t0\t{root}\t"
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
    assert len(lines) == 3
    if "CLAUDE_CONFIG_DIR" not in env:
        assert lines[2].startswith("FAIL") and "/we:pin on" in lines[2]


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
