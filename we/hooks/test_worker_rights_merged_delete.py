"""A worker deletes a merged remote branch: `worker_rights.merged_delete_refusal` through `never`,
against a local bare origin and a fake `gh pr list`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import worker_rights as wr  # noqa: E402

# `gh pr list --head <b> …`: the open PRs of <b> from $FAKE_GH_OPEN ({branch: [numbers]}), exit 1
# when $FAKE_GH_FAIL is set
FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
if os.environ.get("FAKE_GH_FAIL"):
    print("gh: network down", file=sys.stderr); sys.exit(1)
if args[:2] == ["pr", "list"]:
    head = args[args.index("--head") + 1]
    table = json.loads(os.environ.get("FAKE_GH_OPEN") or "{}")
    print(json.dumps([{"number": n} for n in table.get(head, [])])); sys.exit(0)
sys.exit(0)
"""
PUSH = "git push origin"


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A checkout on a feature branch with origin a bare repo: `feat/done` is in main, `feat/open`
    has a commit main lacks, `feat/stale` was merged as fetched but got a commit on origin since."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "gh").write_text(FAKE_GH)
    (bindir / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    monkeypatch.delenv("FAKE_GH_FAIL", raising=False)
    monkeypatch.delenv("FAKE_GH_OPEN", raising=False)
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    work = tmp_path / "work"
    _git(tmp_path, "init", "-q", "-b", "main", str(work))
    _git(work, "commit", "-q", "--allow-empty", "-m", "base")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "branch", "feat/done")
    _git(work, "branch", "feat/stale")
    _git(work, "checkout", "-q", "-b", "feat/open")
    _git(work, "commit", "-q", "--allow-empty", "-m", "unmerged")
    _git(work, "checkout", "-q", "main")
    _git(work, "push", "-q", "origin", "main", "feat/done", "feat/open", "feat/stale")
    _git(work, "fetch", "-q", "origin")
    _git(work, "remote", "set-head", "origin", "main")
    # a commit lands on origin's feat/stale after this checkout fetched it
    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", "-b", "feat/stale", str(origin), str(other))
    _git(other, "commit", "-q", "--allow-empty", "-m", "late")
    _git(other, "push", "-q", "origin", "feat/stale")
    _git(work, "checkout", "-q", "-b", "feat/mine")
    return work


def never(repo, command):
    return wr.never(command, str(repo), {})


@pytest.mark.parametrize(
    "command",
    [
        f"{PUSH} --delete feat/done",
        f"{PUSH} -d feat/done",
        f"{PUSH} :feat/done",
        f"{PUSH} :refs/heads/feat/done",
        "git push --delete origin feat/done",
    ],
)
def test_a_merged_branch_passes(repo, command):
    assert never(repo, command) is None


def test_a_merged_branch_passes_from_a_main_checkout(repo):
    """The deletion sends no ref, so the main-checkout brake does not hold it."""
    _git(repo, "checkout", "-q", "main")
    assert never(repo, f"{PUSH} --delete feat/done") is None
    # a plain push from there still is one
    assert never(repo, "git push").startswith("main (a git push from main")


@pytest.mark.parametrize(
    ("command", "env", "reason"),
    [
        (f"{PUSH} --delete feat/open", {}, "feat/open ("),  # not merged
        (f"{PUSH} --delete feat/stale", {}, "feat/stale ("),  # merged as fetched, not on origin
        (f"{PUSH} --delete main", {}, "main is a protected branch"),
        (f"{PUSH} :master", {}, "master is a protected branch"),
        (f"{PUSH} --delete feat/done", {"FAKE_GH_OPEN": '{"feat/done": [12]}'}, "open PR #12"),
        (f"{PUSH} --delete feat/done", {"FAKE_GH_FAIL": "1"}, "could not be read"),
        (f"{PUSH} --delete feat/done feat/open", {}, "feat/open ("),  # one of two unmerged
        (f"{PUSH} --delete feat/gone", {}, "origin/feat/gone is unknown"),
        (f"{PUSH} --delete --force feat/done", {}, "without --force"),
        (f"{PUSH} feat/mine :feat/done", {}, "feat/mine is no deletion"),
        ("git push upstream --delete feat/done", {}, "remote origin"),
        (f"cd . && {PUSH} --delete feat/done", {}, "of its own"),
    ],
)
def test_a_deletion_that_does_not_hold_is_refused(repo, monkeypatch, command, env, reason):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    found = never(repo, command)
    assert found and found.startswith("delete (git push "), found
    assert reason in found, found


def test_the_settings_carry_no_deletion_deny_rule():
    """A merged branch passes, so the permission layer must not deny what the gate allows."""
    rules = wr.never_rules({"main"})
    assert not [r for r in rules if "push" in r and ("--del" in r or " -d " in r or " :" in r)]
