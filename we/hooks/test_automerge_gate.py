"""Matrix for the auto-merge gate: `gh pr merge --auto` waits for a Codex verdict on the head.

The race it closes: auto-merge armed seconds after `gh pr create`, Codex posting BLOCKING after
the arm, the PR merged with the finding unread. `gh` is replaced by a fake; no network.

Run: `python3 -m pytest -q we/hooks/test_automerge_gate.py`
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).with_name("automerge_gate.py")
_spec = importlib.util.spec_from_file_location("automerge_gate", HOOK)
gate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(gate)

SHA = "abc123def4567890"
WORKFLOW = "name: Review\njobs:\n  publish:\n    name: Codex Review\n    runs-on: x\n"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "codex.yml").write_text(WORKFLOW)
    return tmp_path


class FakeGh:
    def __init__(self, runs: list[dict] | None, comments: list[str] = (), fail: bool = False):
        self.runs, self.comments, self.fail, self.calls = runs, list(comments), fail, []

    def __call__(self, args: list[str], _cwd: str | None) -> str | None:
        self.calls.append(args)
        if self.fail:
            return None
        if args[:2] == ["pr", "view"] and "comments" in args:
            return json.dumps({"comments": [{"body": b} for b in self.comments]})
        if args[:2] == ["pr", "view"]:
            url = "https://github.com/o/r/pull/7"
            return json.dumps({"headRefOid": SHA, "number": 7, "url": url})
        if args[0] == "api":
            assert f"commits/{SHA}/check-runs" in args[1]
            return json.dumps({"check_runs": self.runs})
        raise AssertionError(args)


def refuse(repo: Path, command: str, fake: FakeGh, monkeypatch, **extra) -> str | None:
    monkeypatch.setattr(gate, "_gh", fake)
    payload = {"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": command}}
    payload.update(extra)
    return gate._refusal(payload)


def run(status: str = "completed", conclusion: str | None = "success", id_: int = 1) -> dict:
    return {"id": id_, "status": status, "conclusion": conclusion}


ARM = "gh pr merge 7 --auto --merge"


def test_arm_before_codex_reported_is_refused(repo: Path, monkeypatch) -> None:
    reason = refuse(repo, ARM, FakeGh(runs=[]), monkeypatch)
    assert reason is not None
    assert "no `Codex Review` check on head abc123def of PR #7 yet" in reason


@pytest.mark.parametrize("status", ["queued", "in_progress"])
def test_arm_while_codex_runs_is_refused(repo: Path, monkeypatch, status: str) -> None:
    reason = refuse(repo, ARM, FakeGh([run(status, None)]), monkeypatch)
    assert reason is not None and f"still {status}" in reason


def test_cancelled_run_has_no_verdict(repo: Path, monkeypatch) -> None:
    reason = refuse(repo, ARM, FakeGh([run(conclusion="cancelled")]), monkeypatch)
    assert reason is not None and "without a verdict" in reason


def test_verdict_error_is_refused(repo: Path, monkeypatch) -> None:
    fake = FakeGh([run(conclusion="failure")], ["<!-- codex-review -->\n<!-- VERDICT:ERROR -->"])
    reason = refuse(repo, ARM, fake, monkeypatch)
    assert reason is not None and "VERDICT:ERROR" in reason


def test_another_reviewers_verdict_is_not_codexs(repo: Path, monkeypatch) -> None:
    fake = FakeGh(
        [run(conclusion="failure")],
        [
            "<!-- codex-review -->\n<!-- VERDICT:ERROR -->",
            "<!-- claude-code-review -->\nCodex aside.\n<!-- VERDICT:PASS -->",
        ],
    )
    reason = refuse(repo, ARM, fake, monkeypatch)
    assert reason is not None and "VERDICT:ERROR" in reason


def test_blocking_is_a_verdict_and_passes(repo: Path, monkeypatch) -> None:
    fake = FakeGh(
        [run(conclusion="failure")], ["<!-- codex-review -->\n<!-- VERDICT:BLOCKING -->"]
    )
    assert refuse(repo, ARM, fake, monkeypatch) is None


def test_latest_rerun_decides(repo: Path, monkeypatch) -> None:
    fake = FakeGh([run(conclusion="cancelled", id_=1), run(conclusion="success", id_=2)])
    assert refuse(repo, ARM, fake, monkeypatch) is None


@pytest.mark.parametrize(
    "command",
    [
        "gh pr merge --auto --squash",
        "gh pr merge --squash --auto 7",
        "cd . && gh pr merge https://github.com/o/r/pull/7 --merge --auto",
    ],
)
def test_auto_in_any_position_is_seen(repo: Path, monkeypatch, command: str) -> None:
    assert refuse(repo, command, FakeGh(runs=[]), monkeypatch) is not None


def test_success_passes(repo: Path, monkeypatch) -> None:
    assert refuse(repo, ARM, FakeGh([run()]), monkeypatch) is None


def test_repo_without_codex_workflow_passes_offline(repo: Path, monkeypatch) -> None:
    (repo / ".github" / "workflows" / "codex.yml").unlink()
    fake = FakeGh(runs=[])
    assert refuse(repo, ARM, fake, monkeypatch) is None
    assert fake.calls == []


def test_configured_check_name_is_used(repo: Path, monkeypatch) -> None:
    (repo / ".weside").mkdir()
    (repo / ".weside" / "config.json").write_text(
        json.dumps({"review": {"codex_check": "AI Rev"}})
    )
    (repo / ".github" / "workflows" / "codex.yml").write_text("jobs:\n  a:\n    name: AI Rev\n")
    reason = refuse(repo, ARM, FakeGh(runs=[]), monkeypatch)
    assert reason is not None and "no `AI Rev` check" in reason


def test_gh_failure_fails_open(repo: Path, monkeypatch) -> None:
    assert refuse(repo, ARM, FakeGh(runs=[], fail=True), monkeypatch) is None


@pytest.mark.parametrize(
    "command",
    [
        "gh pr merge 7 --merge",
        "gh pr merge 7 --disable-auto",
        "echo 'gh pr merge 7 --auto'",
        "cat <<'EOF' > notes.md\ngh pr merge 7 --auto --merge\nEOF",
    ],
)
def test_not_an_arm_passes(repo: Path, monkeypatch, command: str) -> None:
    assert refuse(repo, command, FakeGh(runs=[]), monkeypatch) is None


@pytest.mark.parametrize("command", [ARM, "gh pr merge 7 --squash"])
def test_a_subagent_never_merges(repo: Path, monkeypatch, command: str) -> None:
    fake = FakeGh([run()])
    reason = refuse(repo, command, fake, monkeypatch, agent_id="a1", agent_type="we:dev-medium")
    assert reason is not None and "A subagent never merges" in reason
    assert fake.calls == []


def test_a_subagent_may_disarm(repo: Path, monkeypatch) -> None:
    command = "gh pr merge 7 --disable-auto"
    assert refuse(repo, command, FakeGh([run()]), monkeypatch, agent_id="a1") is None


def test_hook_prints_a_deny(repo: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(gate, "_gh", FakeGh(runs=[]))
    payload = {"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": ARM}}
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(payload)))
    gate.main()
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
