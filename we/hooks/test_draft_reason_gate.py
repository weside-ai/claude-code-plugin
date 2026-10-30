"""draft_reason_gate.py as Claude Code runs it: a subprocess with a stub `gh` on PATH."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "draft_reason_gate.py"
REASONED = "**Draft:** waits for the schema PR — ready when it merged\n\n## Summary\nx\n"
PLAIN = "## Summary\nx\n"


def run(tmp: Path, command: str, view_body: str | None = None) -> str | None:
    bin_dir = tmp / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "gh"
    if view_body is None:
        stub.write_text("#!/bin/sh\nexit 1\n")
    else:
        (tmp / "view.json").write_text(json.dumps({"body": view_body}))
        stub.write_text(f"#!/bin/sh\ncat '{tmp / 'view.json'}'\n")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(tmp)}
    res = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        check=False,
        timeout=20,
    )
    assert res.returncode == 0, res.stderr
    if not res.stdout.strip():
        return None
    out = json.loads(res.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    return out["permissionDecisionReason"]


def test_draft_create_without_reason_is_denied(tmp_path):
    (tmp_path / "b.md").write_text(PLAIN)
    reason = run(tmp_path, "gh pr create --draft --title t --body-file b.md")
    assert reason.startswith("`gh pr create --draft` needs a reason")
    assert (
        "the `--body-file` with that line first" in reason
        and "A fix round does not draft" in reason
    )


def test_draft_create_with_reason_passes(tmp_path):
    (tmp_path / "b.md").write_text(REASONED)
    assert run(tmp_path, "gh pr create --draft --title t --body-file b.md") is None
    assert run(tmp_path, f"gh pr create -d -t t -b '{REASONED}'") is None


def test_heredoc_body_written_in_the_same_command(tmp_path):
    cmd = "cat > b.md <<'EOF'\n{}EOF\ngh pr create --draft --body-file b.md"
    assert run(tmp_path, cmd.format(REASONED)) is None
    assert run(tmp_path, cmd.format(PLAIN)) is not None


def test_placeholder_or_missing_body_is_denied(tmp_path):
    body = "**Draft:** <reason> — ready when <condition>\n"
    assert run(tmp_path, f"gh pr create --draft -b '{body}'") is not None
    assert run(tmp_path, "gh pr create --draft --fill") is not None


def test_ready_create_and_unreadable_body_pass(tmp_path):
    (tmp_path / "b.md").write_text(PLAIN)
    assert run(tmp_path, "gh pr create --title t --body-file b.md") is None
    assert run(tmp_path, 'gh pr create --draft --body "$(cat b.md)"') is None
    assert run(tmp_path, "gh pr create --draft --body-file missing.md") is None


def test_ready_undo_reads_the_pr_body(tmp_path):
    reason = run(tmp_path, "gh pr ready 7 --undo", view_body=PLAIN)
    assert reason.startswith("`gh pr ready --undo` needs a reason")
    assert "gh pr edit 7 --body-file" in reason
    assert run(tmp_path, "gh pr ready 7 --undo", view_body=REASONED) is None
    assert run(tmp_path, "gh pr merge 7 --disable-auto && gh pr ready 7 --undo", PLAIN) is not None


def test_ready_undo_fails_open_and_plain_ready_passes(tmp_path):
    assert run(tmp_path, "gh pr ready 7 --undo", view_body=None) is None
    assert run(tmp_path, "gh pr ready 7", view_body=PLAIN) is None
    assert run(tmp_path, "echo 'gh pr ready 7 --undo'", view_body=PLAIN) is None
