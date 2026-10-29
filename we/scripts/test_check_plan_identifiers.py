"""check-plan-identifiers.py against a real git repo with an `origin/main` ref."""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("check-plan-identifiers.py")


@pytest.fixture()
def repo(tmp_path):
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "apps" / "api" / "app").mkdir(parents=True)
    (tmp_path / "apps" / "api" / "app" / "consumer.py").write_text(
        "class ThreadLock:\n    pass\n\ndef run_turn():\n    KIND_SPECS = {}\n"
    )
    git("add", "-A")
    git("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "-m", "base")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    return tmp_path


def check(repo, plan):
    (repo / "plan.md").write_text(plan)
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "plan.md", "--ref", "origin/main"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return res.returncode, res.stdout.splitlines()


def test_existing_names_and_paths_pass(repo):
    plan = (
        "Touch `app/consumer.py:12` and `apps/api/app/`; `ThreadLock` guards `run_turn()`,\n"
        "`KIND_SPECS[kind]` is a lookup, plain words like `queue` are no claim.\n"
    )
    code, out = check(repo, plan)
    assert (code, out[-1]) == (0, "5 claims checked, 0 missing")


def test_a_claimed_name_without_hit_is_named_with_its_line(repo):
    plan = "## Context\n\n`ThreadLock` exists.\n`WAKE_PROFILES` has a row per wake.\n`app/gone.py` too.\n"
    code, out = check(repo, plan)
    assert code == 1
    assert out == [
        "missing: WAKE_PROFILES (line 4)",
        "missing: app/gone.py (line 5)",
        "3 claims checked, 2 missing",
    ]


def test_new_other_repo_placeholders_and_fences_are_skipped(repo):
    plan = (
        "`NEW_THING` (new) and `other/x.md` (other repo) and `docs/plans/<KEY>-story.md`\n"
        "```python\nMISSING_IN_FENCE = 1\n```\n"
    )
    code, out = check(repo, plan)
    assert (code, out) == (0, ["0 claims checked, 0 missing"])
