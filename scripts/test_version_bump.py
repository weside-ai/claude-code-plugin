"""version_bump.py in a throwaway git repo: the bump level from Conventional Commits, the one
version line it rewrites, and the bump-PR test the review skip and the version check share."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "version_bump.py"
sys.path.insert(0, str(SCRIPT.parent))
import version_bump as vb  # noqa: E402

PLUGIN = "we/.claude-plugin/plugin.json"
BOT = ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com")
DEV = ("dev", "dev@example.invalid")


def git(root: Path, *args: str, who: tuple[str, str] = DEV) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": who[0],
        "GIT_AUTHOR_EMAIL": who[1],
        "GIT_COMMITTER_NAME": who[0],
        "GIT_COMMITTER_EMAIL": who[1],
    }
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


def write_plugin(root: Path, version: str, **extra: str) -> None:
    path = root / PLUGIN
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": "we", "version": version, **extra}, indent=2) + "\n")


def commit(root: Path, msg: str, files: dict[str, str] | None = None, who=DEV) -> str:
    for name, text in (files or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg, "--allow-empty", who=who)
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
    text = (repo / PLUGIN).read_text()
    assert '"version": "8.33.0"' in text
    assert git(repo, "diff", "--numstat").split() == ["1", "1", PLUGIN]


def test_prepare_with_nothing_since_the_last_bump_prints_nothing(repo: Path):
    out = run(repo, "prepare")
    assert out.returncode == 0 and out.stdout == ""
    assert git(repo, "status", "--porcelain") == ""


def _bump_branch(repo: Path, who=BOT, plugin_extra: dict | None = None, more: dict | None = None):
    git(repo, "checkout", "-q", "-b", "chore/version-bump")
    write_plugin(repo, "8.33.0", **(plugin_extra or {}))
    return commit(repo, "chore: bump we to 8.33.0", more, who=who)


def test_a_bot_commit_on_the_version_line_only_is_a_bump(repo: Path):
    head = _bump_branch(repo)
    assert vb_run(repo, "is-bump", head).returncode == 0
    out = vb_run(repo, "check", head)
    assert out.returncode == 0 and "Bump PR" in out.stdout


def test_a_foreign_commit_on_the_branch_is_no_bump(repo: Path):
    _bump_branch(repo)
    head = commit(repo, "chore: bump we to 8.33.0", who=DEV)
    out = vb_run(repo, "is-bump", head)
    assert out.returncode == 1 and "author is 'dev'" in out.stdout


def test_a_second_file_in_the_diff_is_no_bump(repo: Path):
    head = _bump_branch(repo, more={"we/hooks/x.py": "evil\n"})
    out = vb_run(repo, "is-bump", head)
    assert out.returncode == 1 and "we/hooks/x.py" in out.stdout


def test_a_second_line_in_plugin_json_is_no_bump(repo: Path):
    head = _bump_branch(repo, plugin_extra={"description": "changed"})
    out = vb_run(repo, "is-bump", head)
    assert out.returncode == 1 and "more than its version line" in out.stdout
    check = vb_run(repo, "check", head)
    assert check.returncode == 1 and "changes the version" in check.stdout


def test_a_pr_that_changes_the_version_is_refused(repo: Path):
    git(repo, "checkout", "-q", "-b", "feat/x")
    write_plugin(repo, "8.33.0")
    head = commit(repo, "feat: x", {"we/x.py": "1\n"})
    out = vb_run(repo, "check", head)
    assert out.returncode == 1
    assert "rises by itself after the merge" in out.stdout


def test_a_pr_that_leaves_the_version_alone_passes(repo: Path):
    git(repo, "checkout", "-q", "-b", "feat/x")
    write_plugin(repo, "8.32.0", description="a userConfig-free edit")
    head = commit(repo, "feat: x", {"we/x.py": "1\n"})
    out = vb_run(repo, "check", head)
    assert out.returncode == 0 and "Version untouched" in out.stdout


def vb_run(repo: Path, verb: str, head: str) -> subprocess.CompletedProcess:
    return run(repo, verb, "main", head)


def test_an_unknown_verb_is_refused(repo: Path):
    assert run(repo, "nope").returncode == 2
