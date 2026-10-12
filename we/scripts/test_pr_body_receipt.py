"""pr-body-receipt.py: the spliced body passes the verification gate it was built for.

Run: `python3 -m pytest -q we/scripts/test_pr_body_receipt.py`
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("pr-body-receipt.py")
GATE = Path(__file__).resolve().parent.parent / "hooks" / "verification_gate.py"

_spec = importlib.util.spec_from_file_location("verification_gate", GATE)
gate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(gate)

PLAN = """# Story

## Acceptance Criteria

1. it works

## Verification

- **Oracle:** cli — the repo's CLI against the dev server
- **Seed:**

  ```bash
  app widgets create --json
  # measurements: one id per call
  ```

- **Asserted:** 201 and a widget id
- **Not proven:** device geometry

## Technical Approach

Code.
"""

BODY = "## Summary\n\nWidgets.\n\nKEY-1\n"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".weside").mkdir()
    (tmp_path / ".weside" / "config.json").write_text(
        json.dumps({"verification": {"required": True}})
    )
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    (tmp_path / "docs" / "plans" / "KEY-1-story.md").write_text(PLAN)
    return tmp_path


def run(repo: Path, body: str, key: str = "KEY-1") -> subprocess.CompletedProcess:
    (repo / "in.md").write_text(body)
    return subprocess.run(
        [sys.executable, str(SCRIPT), key, "in.md", "out.md"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def gate_verdict(repo: Path) -> str | None:
    return gate._refusal(
        {
            "tool_name": "Bash",
            "cwd": str(repo),
            "tool_input": {"command": "gh pr create --body-file out.md"},
        }
    )


def test_spliced_body_passes_the_gate(repo: Path) -> None:
    result = run(repo, BODY)
    assert result.returncode == 0, result.stderr
    out = (repo / "out.md").read_text()
    assert out.startswith(BODY.rstrip("\n"))
    assert "# measurements: one id per call" in out and "Technical Approach" not in out
    assert gate_verdict(repo) is None


def test_a_retyped_receipt_is_replaced_not_duplicated(repo: Path) -> None:
    body = BODY + "\n## Verification\n\nRan it, works.\n\n## Notes\n\nn\n"
    result = run(repo, body)
    assert result.returncode == 0, result.stderr
    out = (repo / "out.md").read_text()
    assert out.count("## Verification") == 1
    assert "Ran it, works." not in out and "## Notes" in out
    assert gate_verdict(repo) is None


def test_a_plan_without_the_block_stops(repo: Path) -> None:
    (repo / "docs" / "plans" / "KEY-2-story.md").write_text("# Story\n\n## Technical Approach\n")
    result = run(repo, BODY, key="KEY-2")
    assert result.returncode == 1
    assert "verification did not happen" in result.stderr
    assert not (repo / "out.md").exists()


def test_a_plan_block_the_gate_refuses_is_named(repo: Path) -> None:
    plan = PLAN.replace("**Oracle:** cli — ", "**Oracle:** the dev server — ")
    (repo / "docs" / "plans" / "KEY-1-story.md").write_text(plan)
    result = run(repo, BODY)
    assert result.returncode == 1
    assert "fails the gate" in result.stderr and "has to start with one of" in result.stderr
