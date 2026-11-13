"""main_red_gate.py as Claude Code runs it: a subprocess in a git repo with a stub `gh` on PATH."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "main_red_gate.py"

# A crew's default branch after two PRs merged past each other: the newest CI run is red.
RED = [
    {
        "workflowName": "CI",
        "status": "completed",
        "conclusion": "failure",
        "headSha": "abcdef0123456789",
        "createdAt": "2026-11-12T10:00:00Z",
    },
    {
        "workflowName": "CI",
        "status": "completed",
        "conclusion": "success",
        "headSha": "1111111111111111",
        "createdAt": "2026-11-12T09:00:00Z",
    },
    {
        "workflowName": "Secret Scan",
        "status": "completed",
        "conclusion": "success",
        "headSha": "abcdef0123456789",
        "createdAt": "2026-11-12T10:00:00Z",
    },
]
GREEN = [dict(RED[0], conclusion="success"), *RED[1:]]
OVERRIDE = "## Summary\nx\n\n**Ready on red main:** this PR fixes the typecheck on main\n"


def run(
    tmp: Path,
    command: str,
    runs=None,
    body: str = "## Summary\nx\n",
    config=None,
    gh_fails: bool = False,
) -> str | None:
    if not (tmp / ".git").exists():
        subprocess.run(["git", "init", "-q", str(tmp)], check=True)
    if config is not None:
        (tmp / ".weside").mkdir(exist_ok=True)
        (tmp / ".weside" / "config.json").write_text(json.dumps(config))
    bin_dir = tmp / "bin"
    bin_dir.mkdir(exist_ok=True)
    (tmp / "runs.json").write_text(json.dumps(RED if runs is None else runs))
    (tmp / "body.json").write_text(json.dumps({"body": body}))
    stub = bin_dir / "gh"
    stub.write_text(
        "#!/bin/sh\n"
        + ("exit 1\n" if gh_fails else "")
        + 'case "$*" in\n'
        + '  *"repo view"*) echo main ;;\n'
        + f"  *\"run list\"*) cat '{tmp / 'runs.json'}' ;;\n"
        + f"  *\"pr view\"*) cat '{tmp / 'body.json'}' ;;\n"
        + "  *) exit 1 ;;\nesac\n"
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(tmp)}
    res = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        check=False,
        timeout=30,
    )
    assert res.returncode == 0, res.stderr
    if not res.stdout.strip():
        return None
    out = json.loads(res.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    return out["permissionDecisionReason"]


ON = {"ci": {"hold_ready_on_red_main": True}}


def test_ready_while_main_is_red_is_denied(tmp_path):
    reason = run(tmp_path, "gh pr ready 12", config=ON)
    assert reason.startswith("`gh pr ready` holds: `main` is red on CI (abcdef01)")
    assert "merge `origin/main` once, push once" in reason
    assert "**Ready on red main:** <reason>" in reason and "gh pr edit 12" in reason


def test_off_by_default(tmp_path):
    assert run(tmp_path, "gh pr ready 12") is None
    assert (
        run(tmp_path, "gh pr ready 12", config={"ci": {"hold_ready_on_red_main": False}}) is None
    )
    assert run(tmp_path, "gh pr ready 12", config={"ci": {}}) is None


def test_green_main_passes(tmp_path):
    assert run(tmp_path, "gh pr ready 12", runs=GREEN, config=ON) is None


def test_a_run_in_progress_or_cancelled_defers_to_the_one_before(tmp_path):
    newer = {
        "workflowName": "CI",
        "headSha": "2222222222222222",
        "createdAt": "2026-11-12T11:00:00Z",
    }
    pending = [dict(newer, status="in_progress", conclusion=""), *RED]
    assert run(tmp_path, "gh pr ready 12", runs=pending, config=ON) is not None
    cancelled = [dict(newer, status="completed", conclusion="cancelled"), *RED]
    assert run(tmp_path, "gh pr ready 12", runs=cancelled, config=ON) is not None
    fixed = [dict(newer, status="completed", conclusion="success"), *RED]
    assert run(tmp_path, "gh pr ready 12", runs=fixed, config=ON) is None


def test_a_workflow_list_limits_what_counts(tmp_path):
    assert (
        run(tmp_path, "gh pr ready 12", config={"ci": {"hold_ready_on_red_main": ["Secret Scan"]}})
        is None
    )
    assert (
        run(tmp_path, "gh pr ready 12", config={"ci": {"hold_ready_on_red_main": ["CI"]}})
        is not None
    )


def test_override_line_passes(tmp_path):
    assert run(tmp_path, "gh pr ready 12", body=OVERRIDE, config=ON) is None


def test_override_with_placeholder_or_in_a_fence_is_denied(tmp_path):
    placeholder = "**Ready on red main:** <reason>\n"
    assert run(tmp_path, "gh pr ready 12", body=placeholder, config=ON) is not None
    fenced = "```\n**Ready on red main:** fixes main\n```\n"
    assert run(tmp_path, "gh pr ready 12", body=fenced, config=ON) is not None


def test_undo_push_and_prose_are_not_held(tmp_path):
    assert run(tmp_path, "gh pr ready 12 --undo", config=ON) is None
    assert run(tmp_path, "git push origin HEAD", config=ON) is None
    assert run(tmp_path, "echo 'gh pr ready 12'", config=ON) is None


def test_command_position_forms_are_held(tmp_path):
    assert run(tmp_path, "git push && gh pr ready", config=ON) is not None
    assert run(tmp_path, "gh -R o/r pr ready 12", config=ON) is not None


def test_gh_errors_fail_open(tmp_path):
    assert run(tmp_path, "gh pr ready 12", config=ON, gh_fails=True) is None
