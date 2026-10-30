"""teammate_gate.py as Claude Code runs it: a subprocess with a project dir."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "teammate_gate.py"


def run(project: Path, tool_input: dict, config: dict | None = None) -> str | None:
    if config is not None:
        (project / ".weside").mkdir(exist_ok=True)
        (project / ".weside" / "config.json").write_text(json.dumps(config))
    payload = {"tool_name": "Agent", "tool_input": tool_input, "cwd": str(project)}
    res = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
        check=False,
        timeout=20,
    )
    assert res.returncode == 0, res.stderr
    if not res.stdout.strip():
        return None
    out = json.loads(res.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    return out["permissionDecisionReason"]


WORKER = {"subagent_type": "we:dev-medium", "name": "w1", "prompt": "x", "description": "d"}


def test_named_worker_without_isolation_is_denied(tmp_path):
    reason = run(tmp_path, WORKER)
    assert reason.startswith("Worker panes are off")
    assert "Drop `name`" in reason and 'isolation: "worktree"' in reason


def test_isolated_or_unnamed_worker_passes(tmp_path):
    assert run(tmp_path, {**WORKER, "isolation": "worktree"}) is None
    assert run(tmp_path, {k: v for k, v in WORKER.items() if k != "name"}) is None


def test_other_agent_types_pass(tmp_path):
    assert run(tmp_path, {**WORKER, "subagent_type": "we:council-architect"}) is None
    assert run(tmp_path, {**WORKER, "subagent_type": "general-purpose"}) is None


def test_switch_turns_panes_back_on(tmp_path):
    assert run(tmp_path, WORKER, {"agents": {"visible_teammates": True}}) is None
    assert run(tmp_path, WORKER, {"agents": {"visible_teammates": False}}) is not None


def test_broken_input_fails_open(tmp_path):
    res = subprocess.run(
        [sys.executable, str(HOOK)], input="{", capture_output=True, text=True, check=False
    )
    assert res.returncode == 0 and not res.stdout.strip()
