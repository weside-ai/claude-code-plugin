"""version_bump.py in a throwaway git repo: the bump level from Conventional Commits, the one
version line it rewrites, and the Version Bump Check that lets only the App's one-step bump PR move
the version."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "version_bump.py"
sys.path.insert(0, str(SCRIPT.parent))
import version_bump as vb  # noqa: E402

PLUGIN = "we/.claude-plugin/plugin.json"
APP = "weside-agent[bot]"


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def write_plugin(root: Path, version: str, **extra: str) -> None:
    path = root / PLUGIN
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": "we", "version": version, **extra}, indent=2) + "\n")


def commit(root: Path, msg: str, files: dict[str, str] | None = None) -> str:
    for name, text in (files or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg, "--allow-empty")
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    write_plugin(tmp_path, "8.32.0")
    commit(tmp_path, "chore: bump we to 8.32.0")
    return tmp_path


def run(root: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv], cwd=root, capture_output=True, text=True, check=False
    )


def check(root: Path, head: str, author: str = APP) -> subprocess.CompletedProcess:
    return run(root, "check", "main", head, "--author", author)


@pytest.mark.parametrize(
    ("messages", "want"),
    [
        ([], None),
        (["fix(x): y", "docs: z"], "patch"),
        (["fix: y", "feat(board): z"], "minor"),
        (["feat!: drop a verb"], "major"),
        (["fix: y\n\nBREAKING CHANGE: the flag is gone"], "major"),
        (["chore: a feat: in the middle"], "patch"),
    ],
)
def test_the_level_follows_the_commit_types(messages, want):
    assert vb.level(messages) == want


def test_prepare_bumps_from_the_commits_since_the_last_bump(repo: Path):
    commit(repo, "fix(hooks): x", {"a.py": "1\n"})
    commit(repo, "feat(board): y", {"b.py": "1\n"})
    out = run(repo, "prepare")
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "8.33.0"
    assert git(repo, "diff", "--numstat").split() == ["1", "1", PLUGIN]


def test_the_merge_of_the_bump_pr_bumps_nothing(repo: Path):
    """No loop: after the bump commit only its merge lands, and merges are skipped."""
    commit(repo, "feat: x", {"a.py": "1\n"})
    git(repo, "checkout", "-q", "-b", "chore/version-bump")
    write_plugin(repo, "8.33.0")
    commit(repo, "chore: bump we to 8.33.0")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "Merge pull request #9", "chore/version-bump")
    out = run(repo, "prepare")
    assert out.returncode == 0 and out.stdout == ""
    assert git(repo, "status", "--porcelain") == ""


def _branch(repo: Path, version: str, more: dict | None = None, **extra: str) -> str:
    git(repo, "checkout", "-q", "-b", "chore/version-bump")
    write_plugin(repo, version, **extra)
    return commit(repo, f"chore: bump we to {version}", more)


@pytest.mark.parametrize("version", ["8.32.1", "8.33.0", "9.0.0"])
def test_the_apps_one_step_bump_pr_passes(repo: Path, version: str):
    out = check(repo, _branch(repo, version))
    assert out.returncode == 0, out.stdout
    assert f"Bump PR: 8.32.0 -> {version}" in out.stdout


def test_a_bump_by_another_author_is_refused(repo: Path):
    out = check(repo, _branch(repo, "8.33.0"), author="someone")
    assert out.returncode == 1 and "author is 'someone'" in out.stdout


def test_a_second_file_in_the_diff_is_refused(repo: Path):
    out = check(repo, _branch(repo, "8.33.0", more={"we/hooks/x.py": "evil\n"}))
    assert out.returncode == 1 and "we/hooks/x.py" in out.stdout


def test_a_second_line_in_plugin_json_is_refused(repo: Path):
    out = check(repo, _branch(repo, "8.33.0", description="changed"))
    assert out.returncode == 1 and "more than its version line" in out.stdout


@pytest.mark.parametrize("version", ["8.34.0", "8.31.0", "8.33.1", "10.0.0"])
def test_a_jump_or_a_downgrade_is_refused(repo: Path, version: str):
    out = check(repo, _branch(repo, version))
    assert out.returncode == 1 and "not one step above 8.32.0" in out.stdout


def test_a_feature_pr_that_moves_the_version_is_refused(repo: Path):
    git(repo, "checkout", "-q", "-b", "feat/x")
    write_plugin(repo, "8.33.0")
    out = check(repo, commit(repo, "feat: x", {"we/x.py": "1\n"}), author="dev")
    assert out.returncode == 1 and "rises by itself after the merge" in out.stdout


def test_a_pr_that_leaves_the_version_alone_passes(repo: Path):
    git(repo, "checkout", "-q", "-b", "feat/x")
    write_plugin(repo, "8.32.0", description="another key")
    out = check(repo, commit(repo, "feat: x", {"we/x.py": "1\n"}), author="dev")
    assert out.returncode == 0 and "Version untouched" in out.stdout


def test_check_needs_the_author(repo: Path):
    assert run(repo, "check", "main", "HEAD").returncode == 2
