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


def test_a_name_marked_new_that_main_already_carries_is_named(repo):
    """A consumer plan built `ThreadLock (new)` a second time after main had merged it."""
    plan = "`ThreadLock` (new) guards the turn; `FreshThing` (not on main) comes with it.\n"
    code, out = check(repo, plan)
    assert code == 1
    assert out[0] == "exists: ThreadLock (line 1): marked new, already on origin/main"
    assert not any("FreshThing" in line for line in out)


def test_a_committed_plan_never_proves_its_own_new_names(repo):
    """Red arm of `exists:`: the plan on main names `FreshThing (new)`; that is no code."""
    plans = repo / "docs" / "plans"
    plans.mkdir(parents=True)
    (plans / "PROJ-1-story.md").write_text("`FreshThing` (new) lands here.\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.email=a@b",
            "-c",
            "user.name=a",
            "commit",
            "-qm",
            "plan",
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", "HEAD"], check=True
    )
    code, out = check(repo, "`FreshThing` (new) lands here.\n")
    assert code == 0 and not any(line.startswith("exists:") for line in out), out


def _commit(repo, message):
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.email=a@b",
            "-c",
            "user.name=a",
            "commit",
            "-qm",
            message,
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", "HEAD"], check=True
    )


def test_exists_matches_whole_words_only(repo):
    """Red arm: `send_email (new)` is not on main because `send_email_batch` is."""
    (repo / "mail.py").write_text("def send_email_batch():\n    pass\n")
    _commit(repo, "batch")
    code, out = check(repo, "`send_email` (new) sends one.\n")
    assert code == 0 and not any(line.startswith("exists:") for line in out), out


def test_the_plan_of_a_merged_story_does_not_fire(repo, tmp_path):
    """Red arm: PROJ-7 merged and built `fresh_thing`; its own plan still says (new)."""
    (repo / "fresh.py").write_text("def fresh_thing():\n    pass\n")
    _commit(repo, "feat(PROJ-7): fresh thing (#12)")
    plan = tmp_path / "PROJ-7-story.md"
    plan.write_text("`fresh_thing` (new) lands here.\n")
    out = subprocess.run(
        [sys.executable, str(SCRIPT), str(plan), "--ref", "origin/main"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 0 and "exists:" not in out.stdout, out.stdout
    other = tmp_path / "PROJ-8-story.md"
    other.write_text("`fresh_thing` (new) lands here.\n")
    out = subprocess.run(
        [sys.executable, str(SCRIPT), str(other), "--ref", "origin/main"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 1 and "exists: fresh_thing" in out.stdout
