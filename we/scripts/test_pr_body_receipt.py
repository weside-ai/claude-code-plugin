"""pr-body-receipt.py: the spliced body passes the verification gate it was built for.

Run: `python3 -m pytest -q we/scripts/test_pr_body_receipt.py`
"""

from __future__ import annotations

import importlib.util
import json
import shlex
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
    assert "write it into the PR body yourself" in result.stderr
    assert "say so and stop" not in result.stderr
    assert not (repo / "out.md").exists()


def test_a_plan_block_the_gate_refuses_is_named(repo: Path) -> None:
    plan = PLAN.replace("**Oracle:** cli — ", "**Oracle:** the dev server — ")
    (repo / "docs" / "plans" / "KEY-1-story.md").write_text(plan)
    result = run(repo, BODY)
    assert result.returncode == 1
    assert "fails the gate" in result.stderr and "has to start with one of" in result.stderr


def test_swapped_arguments_leave_the_plan_untouched(repo: Path) -> None:
    plan_rel = "docs/plans/KEY-1-story.md"
    subprocess.run(["git", "add", plan_rel], cwd=repo, check=True)
    (repo / "in.md").write_text(BODY)
    for args in (["in.md", "KEY-1", plan_rel], ["KEY-1", "in.md", plan_rel]):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2, (args, result.stderr)
        assert (repo / plan_rel).read_text() == PLAN
    assert (
        "no plan"
        in subprocess.run(
            [sys.executable, str(SCRIPT), "in.md", "KEY-1", "out.md"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        ).stderr
    )


def test_a_tracked_body_out_is_refused(repo: Path) -> None:
    (repo / "README.md").write_text("readme\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    (repo / "in.md").write_text(BODY)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "KEY-1", "in.md", "README.md"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2 and "tracked by git" in result.stderr
    assert (repo / "README.md").read_text() == "readme\n"


# The pre-merge receipt line (`verification.pre_merge_receipt`): a fake command prints the
# stdout contract and exits with the code the test names.

FAKE = """import sys
from pathlib import Path
here = Path(__file__).parent
(here / "called").write_text(" ".join(sys.argv[1:]))
sys.stdout.write((here / "fake-out").read_text())
sys.stderr.write((here / "fake-err").read_text())
sys.exit(int((here / "fake-exit").read_text()))
"""


def arm_receipt(repo: Path, stdout: str, code: int, stderr: str = "") -> None:
    (repo / "fake.py").write_text(FAKE)
    (repo / "fake-out").write_text(stdout)
    (repo / "fake-err").write_text(stderr)
    (repo / "fake-exit").write_text(str(code))
    command = f"{shlex.quote(sys.executable)} fake.py {{KEY}}"
    (repo / ".weside" / "config.json").write_text(
        json.dumps({"verification": {"required": True, "pre_merge_receipt": command}})
    )


def receipt_lines(repo: Path, body: str = BODY) -> list:
    result = run(repo, body)
    assert result.returncode == 0, result.stderr
    out = (repo / "out.md").read_text()
    assert gate_verdict(repo) is None
    return [ln for ln in out.splitlines() if ln.startswith("receipt ")]


def test_no_config_key_leaves_the_body_as_today(repo: Path) -> None:
    (repo / "fake.py").write_text(FAKE)
    assert receipt_lines(repo) == []
    assert not (repo / "called").exists()


def test_green_names_the_report_and_the_key_reaches_the_command(repo: Path) -> None:
    arm_receipt(repo, "report: /c/r/dev-abc\n", 0)
    assert receipt_lines(repo) == ["receipt green: `/c/r/dev-abc`"]
    assert (repo / "called").read_text() == "KEY-1"
    out = (repo / "out.md").read_text()
    # Directly under the spliced block.
    assert "- **Not proven:** device geometry\n\nreceipt green:" in out


def test_skip_writes_no_line(repo: Path) -> None:
    arm_receipt(repo, "skip: no receipt\n", 0)
    assert receipt_lines(repo) == []


def test_not_run_lines_join_the_green_line(repo: Path) -> None:
    arm_receipt(
        repo,
        "report: /c/r/x\nnot-run: no DEV slot dev-usd-1\nnot-run: no DEV slot dev-eur-1\n",
        0,
    )
    assert receipt_lines(repo) == [
        "receipt green: `/c/r/x`",
        "receipt not run on DEV: no DEV slot dev-usd-1; no DEV slot dev-eur-1",
    ]


def test_not_run_alone_is_its_own_line(repo: Path) -> None:
    arm_receipt(repo, "not-run: no DEV slot dev-usd-1\n", 0)
    assert receipt_lines(repo) == ["receipt not run on DEV: no DEV slot dev-usd-1"]


def test_red_wins_over_not_run(repo: Path) -> None:
    arm_receipt(repo, "report: /c/r/x\nnot-run: no DEV slot dev-usd-1\n", 1)
    assert receipt_lines(repo) == ["receipt red: `/c/r/x`"]


@pytest.mark.parametrize(
    "code,stderr,why",
    [
        (2, "refused: --env dev runs the branch's own story only\n", "exit 2: refused: --env dev"),
        (3, "mock not running (start it first)\n", "exit 3: mock not running"),
    ],
)
def test_a_run_that_did_not_complete_is_red(repo: Path, code: int, stderr: str, why: str) -> None:
    arm_receipt(repo, "", code, stderr)
    (line,) = receipt_lines(repo)
    assert line.startswith(f"receipt red (not run: {why}")


def test_a_command_not_on_path_is_red(repo: Path) -> None:
    (repo / ".weside" / "config.json").write_text(
        json.dumps({"verification": {"pre_merge_receipt": "no-such-receipt-cmd-xyz {KEY}"}})
    )
    assert receipt_lines(repo) == ["receipt red (not run: no-such-receipt-cmd-xyz not found)"]


def test_a_timeout_is_red(repo: Path, monkeypatch) -> None:
    spec = importlib.util.spec_from_file_location("pr_body_receipt", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "RECEIPT_TIMEOUT_S", 0.5)
    command = f"{sys.executable} -c 'import time; time.sleep(5)'"
    assert mod.run_receipt(command, "KEY-1", repo) == [
        "receipt red (not run: timeout after 0.5 s)"
    ]


@pytest.mark.parametrize(
    "path,span",
    [("/c/my report/x", "`/c/my report/x`"), ("/c/a`b/x", "``/c/a`b/x``")],
)
def test_a_path_with_a_space_or_a_backtick_sits_in_a_code_span(
    repo: Path, path: str, span: str
) -> None:
    arm_receipt(repo, f"report: {path}\n", 1)
    assert receipt_lines(repo) == [f"receipt red: {span}"]


def test_a_second_run_replaces_the_old_line(repo: Path) -> None:
    arm_receipt(repo, "report: /c/r/old\n", 1)
    first = run(repo, BODY)
    assert first.returncode == 0, first.stderr
    body = (repo / "out.md").read_text() + "\n## Notes\n\nn\n"
    arm_receipt(repo, "report: /c/r/new\n", 0)
    assert receipt_lines(repo, body) == ["receipt green: `/c/r/new`"]
    assert "## Notes" in (repo / "out.md").read_text()
