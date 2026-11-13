"""The comfort hooks fail open: an exception inside their logic prints one `skipped (` line on
stderr and lets the command, the stop or the session start through (no deny, no block, exit 0)."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(HOOKS.parent / "scripts"))

# (module, the function whose failure must not stop anything, the stdin payload)
CASES = [
    ("verification_gate", "_refusal", {"tool_name": "Bash", "tool_input": {"command": "ls"}}),
    ("main_red_gate", "refusal", {"tool_name": "Bash", "tool_input": {"command": "gh pr ready"}}),
    ("worker_report_gate", "decide", {"session_id": "s"}),
    ("compact_on_start", "render", {"source": "compact"}),
    ("optimization_reminder", "repo_root", {"source": "startup", "cwd": "."}),
]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"fail_open_{name}", HOOKS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(("name", "func", "payload"), CASES, ids=[c[0] for c in CASES])
def test_an_exception_inside_the_hook_lets_everything_through(
    name, func, payload, monkeypatch, capsys
):
    module = _load(name)

    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(module, func, boom)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    code = module.main()
    out, err = capsys.readouterr()
    assert code in (None, 0)
    assert out == ""
    assert f"{name}: skipped (RuntimeError: boom)" in err


def test_every_command_hook_has_a_timeout():
    """A hook without `timeout` runs under Claude Code's default; hooks.json names one for each."""
    doc = json.loads((HOOKS / "hooks.json").read_text())
    missing = [
        h.get("command")
        for groups in doc["hooks"].values()
        for group in groups
        for h in group.get("hooks", [])
        if h.get("type") == "command" and not isinstance(h.get("timeout"), int)
    ]
    assert missing == []
