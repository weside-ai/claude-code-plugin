"""process_on_start.py: the L0 on every source, the worker short form, the budget gate, the
served log, and nothing without a crew."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "process_on_start.py"
SCRIPTS = HOOK.parent.parent / "scripts"
GENERIC = SCRIPTS / "fixtures" / "crew-v2-generic.json"
sys.path.insert(0, str(SCRIPTS))

import crew as crewlib  # noqa: E402
import render_process  # noqa: E402

SOURCES = ("startup", "resume", "clear", "compact")
KINDS = {
    "named companion": {"WESIDE_COMPANION": "Ada"},
    "unpinned master": {"WE_ROLE": "master"},
    "no WE_ROLE": {},
}


def repo(tmp_path: Path, data: dict | None = None) -> Path:
    root = tmp_path / "repo"
    (root / ".weside").mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    if data is None:
        shutil.copy(GENERIC, root / ".weside" / "crew.json")
    else:
        (root / ".weside" / "crew.json").write_text(json.dumps(data))
    return root


def run(tmp_path: Path, cwd: Path, env_extra: dict, **hook_input) -> subprocess.CompletedProcess:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("WE_ROLE", "WESIDE_COMPANION", "CLAUDE_CODE_SESSION_ID")
    }
    env.update({"HOME": str(tmp_path / "home"), **env_extra})
    data = {"session_id": "sid-1", "source": "startup", "cwd": str(cwd), **hook_input}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(data),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def context(done: subprocess.CompletedProcess) -> str | None:
    assert done.returncode == 0, done.stderr
    if not done.stdout:
        return None
    return json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]


def test_every_source_gets_the_same_l0_per_session_kind(tmp_path):
    root = repo(tmp_path)
    full = render_process.render_l0(crewlib.load(root / ".weside" / "crew.json"))
    for kind, env in KINDS.items():
        texts = {context(run(tmp_path, root, env, source=s)) for s in SOURCES}
        assert texts == {full}, kind
        assert len(full) <= 9_500


def test_over_budget_prints_nothing_names_the_file_and_exits_1(tmp_path):
    data = json.loads(GENERIC.read_text())
    data["local_rules"] = ["r" * 160] * 10
    root = repo(tmp_path, data)
    done = run(tmp_path, root, {"WE_ROLE": "master"}, source="compact")
    assert done.returncode == 1
    assert done.stdout == ""
    [line] = done.stderr.splitlines()
    assert "> 9500; not loaded, read " in line and line.split("read ")[1].startswith(
        str(render_process.PROCESS / "L0.md")
    )


def test_red_arm_without_the_budget_check_the_over_budget_l0_is_printed(tmp_path):
    """Control: the same crew through the hook with the 9,500 check removed goes through."""
    data = json.loads(GENERIC.read_text())
    data["local_rules"] = ["r" * 160] * 10
    root = repo(tmp_path, data)
    copy = tmp_path / "hooks" / "process_on_start.py"
    copy.parent.mkdir()
    text = HOOK.read_text().replace(
        "if len(text) > render_process.BUDGET:", "if False:  # red arm: check removed"
    )
    assert text != HOOK.read_text()
    copy.write_text(
        text.replace('str(Path(__file__).resolve().parent.parent / "scripts")', repr(str(SCRIPTS)))
    )
    done = subprocess.run(
        [sys.executable, str(copy)],
        input=json.dumps({"cwd": str(root), "source": "startup"}),
        env={**os.environ, "HOME": str(tmp_path / "home"), "WE_ROLE": "master"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert len(json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]) > 9_500


def test_workers_get_the_short_form_and_a_consultation_the_l0(tmp_path):
    root = repo(tmp_path)
    crew = crewlib.load(root / ".weside" / "crew.json")
    short = render_process.render_l0(crew, "worker")
    assert len(short) <= 1_500
    assert context(run(tmp_path, root, {"WE_ROLE": "worker"})) == short
    assert context(run(tmp_path, root, {}, agent_type="we:dev-medium")) == short
    git_dir = root / ".git"
    (git_dir / "we-worker.json").write_text(json.dumps({"name": "PROJ-7-build"}))
    assert context(run(tmp_path, root, {"WE_ROLE": "master", "WESIDE_COMPANION": "Ada"})) == short
    (git_dir / "we-worker.json").unlink()
    consult = context(run(tmp_path, root, {"WE_ROLE": "worker", "WESIDE_COMPANION": "Ada"}))
    assert consult == render_process.render_l0(crew)


def test_no_crew_prints_nothing_and_a_refused_crew_one_line(tmp_path):
    bare = tmp_path / "bare"
    subprocess.run(["git", "init", "-q", str(bare)], check=True)
    assert context(run(tmp_path, bare, {"WE_ROLE": "master"})) is None
    root = repo(tmp_path, {"version": 1, "roles": {}})
    assert context(run(tmp_path, root, {"WE_ROLE": "master"})) == (
        "crew: crew.json is version 1: in a worktree, merge the default branch; otherwise run "
        "/we:setup"
    )


def test_each_print_appends_a_plugin_line_to_the_served_log(tmp_path):
    root = repo(tmp_path)
    for source in ("startup", "compact"):
        context(run(tmp_path, root, {"WE_ROLE": "master"}, source=source))
    log = tmp_path / "home" / ".claude" / "we-state" / "l0-served.jsonl"
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    assert [(entry["source"], entry["by"], entry["session_id"]) for entry in lines] == [
        ("startup", "plugin", "sid-1"),
        ("compact", "plugin", "sid-1"),
    ]
    assert all(isinstance(entry["pid"], int) and entry["ts"] for entry in lines)


def test_the_served_log_keeps_the_last_lines(tmp_path):
    root = repo(tmp_path)
    log = tmp_path / "home" / ".claude" / "we-state" / "l0-served.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text("".join(f'{{"n": {i}}}\n' for i in range(1_000)))
    context(run(tmp_path, root, {}))
    lines = log.read_text().splitlines()
    assert len(lines) == 1_000 and lines[0] == '{"n": 1}' and '"by": "plugin"' in lines[-1]
