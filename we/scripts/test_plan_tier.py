"""plan_tier.py: the plan-only tier in a scratch no-checkout tree at `risk.rules_from`, never in the
caller's checkout; the fake risk command keeps the classifier contract (plan from HEAD, diff
base...HEAD)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import plan_tier  # noqa: E402

RISK = HERE / "fixtures" / "plan_tier" / "risk"
ONE_WAY_PLAN = "# PROJ-12\n\n- **Files:**\n  - `money/pay.py`\n"
DOCS_PLAN = "# PROJ-13\n\n- **Files:**\n  - `docs/guide.md`\n"
CREW = {
    "risk": {
        "command": "scripts/risk",
        "rules_from": "origin/main",
        "one_way": ["money", "brake-change"],
    }
}


def git(root: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def tier_repo(tmp_path: Path, plans: dict | None = None, extra: dict | None = None) -> Path:
    """A git repo whose `refs/remotes/origin/main` holds the fake risk command at `scripts/risk`
    and the plans (`{KEY: text}`), with no `origin` remote; `HEAD` is a branch `feature` that
    touches `money/` (an unrelated one-way diff). `extra` adds files on origin/main."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.org")
    git(root, "config", "user.name", "t")
    (root / "scripts").mkdir()
    shutil.copy(RISK, root / "scripts" / "risk")
    plans_dir = root / "docs" / "plans"
    plans_dir.mkdir(parents=True)
    for key, text in (plans or {"PROJ-12": ONE_WAY_PLAN, "PROJ-13": DOCS_PLAN}).items():
        (plans_dir / f"{key}-story.md").write_text(text, encoding="utf-8")
    for rel, text in (extra or {}).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(root, "checkout", "-q", "-b", "feature")
    (root / "money").mkdir()
    (root / "money" / "pay.py").write_text("x = 1\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "one-way diff on the branch")
    return root


@pytest.fixture(autouse=True)
def risk_log(tmp_path, monkeypatch):
    log = tmp_path / "risk-calls.jsonl"
    monkeypatch.setenv("FAKE_RISK_LOG", str(log))
    for var in ("FAKE_RISK_EXIT", "FAKE_RISK_LINE"):
        monkeypatch.delenv(var, raising=False)
    return log


def calls(log: Path) -> list[dict]:
    return [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []


def tier(root: Path, key: str, crew: dict = CREW, **kw) -> plan_tier.TierResult:
    return plan_tier.plan_tier(crew, root, key, f"docs/plans/{key}-story.md", **kw)


class TestPlanTier:
    def test_a_one_way_plan_with_no_diff_is_t2(self, tmp_path):
        root = tier_repo(tmp_path)
        assert tier(root, "PROJ-12") == ("T2 one-way money", None, [])

    def test_a_docs_plan_stays_t0_on_a_one_way_branch(self, tmp_path, risk_log):
        """The red arm of AC4: run in the caller's checkout, this case reads `T2 one-way money`."""
        root = tier_repo(tmp_path)
        assert tier(root, "PROJ-13") == ("T0", None, [])
        [call] = calls(risk_log)
        assert call["argv"] == ["origin/main", "PROJ-13"]
        assert Path(call["cwd"]).resolve() != root.resolve()

    def test_the_command_runs_as_the_blob_of_rules_from(self, tmp_path, risk_log):
        root = tier_repo(tmp_path)
        (root / "scripts" / "risk").write_text("#!/bin/sh\necho T0\n")  # the checkout's copy
        assert tier(root, "PROJ-12").line == "T2 one-way money"
        [call] = calls(risk_log)
        assert call["self_hash"] == git(root, "rev-parse", "origin/main:scripts/risk")

    @pytest.mark.parametrize(
        "env, reason",
        [
            ({"FAKE_RISK_EXIT": "2"}, "risk.command exit 2: risk: refused"),
            ({"FAKE_RISK_LINE": "critical-review"}, "line 1 'critical-review' is no tier"),
            (
                {"FAKE_RISK_LINE": "T2 one-way lunch"},
                "one-way class 'lunch' is not in risk.one_way",
            ),
        ],
    )
    def test_a_failed_or_foreign_answer_is_a_failure(self, tmp_path, monkeypatch, env, reason):
        root = tier_repo(tmp_path)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        result = tier(root, "PROJ-12")
        assert result.line is None and result.failure.startswith(reason), result.failure

    def test_t1_and_t3_pass_for_a_generic_classifier(self, tmp_path, monkeypatch):
        root = tier_repo(tmp_path)
        monkeypatch.setenv("FAKE_RISK_LINE", "T3")
        assert tier(root, "PROJ-12").line == "T3"

    def test_no_command_is_a_warning_and_tier_none(self, tmp_path, risk_log):
        root = tier_repo(tmp_path)
        assert tier(root, "PROJ-12", crew={"risk": {"command": None}}) == (
            "none",
            None,
            ["warning: tier check off: crew.json names no risk.command"],
        )
        assert calls(risk_log) == []

    def test_a_plan_missing_on_rules_from_never_runs_the_command(self, tmp_path, risk_log):
        root = tier_repo(tmp_path)
        (root / "docs" / "plans" / "PROJ-14-story.md").write_text(ONE_WAY_PLAN)  # checkout only
        result = tier(root, "PROJ-14")
        assert result.failure == "plan not on origin/main: docs/plans/PROJ-14-story.md"
        assert calls(risk_log) == []

    def test_a_missing_ref_or_command_is_named(self, tmp_path):
        root = tier_repo(tmp_path)
        crew = {"risk": {**CREW["risk"], "rules_from": "origin/nope"}}
        assert tier(root, "PROJ-12", crew=crew).failure == (
            "risk.rules_from origin/nope is no commit here"
        )
        crew = {"risk": {**CREW["risk"], "command": "scripts/absent"}}
        assert tier(root, "PROJ-12", crew=crew).failure == (
            "risk.command scripts/absent not on origin/main"
        )

    def test_the_scratch_tree_is_gone_after_every_run(self, tmp_path, monkeypatch):
        root = tier_repo(tmp_path)
        before = git(root, "worktree", "list", "--porcelain")
        tier(root, "PROJ-12")
        monkeypatch.setenv("FAKE_RISK_EXIT", "2")
        tier(root, "PROJ-12")
        assert git(root, "worktree", "list", "--porcelain") == before

    def test_fetch_without_origin_warns_once_and_goes_on(self, tmp_path):
        root = tier_repo(tmp_path)
        result = tier(root, "PROJ-12", fetch=True)
        assert result.line == "T2 one-way money"
        [warning] = result.warnings
        assert warning.startswith("warning: git fetch origin failed (") and warning.endswith(
            "the tier reads the local origin/main"
        )


def test_the_fake_risk_command_is_executable():
    assert os.access(RISK, os.X_OK)
