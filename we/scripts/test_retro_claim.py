"""retro_claim.sh in a real git repo with a fake HOME."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "retro_claim.sh"


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "wt"
    r.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:org/app.git"], cwd=r, check=True
    )
    return r


def claim(repo, n, home):
    res = subprocess.run(
        ["bash", str(SCRIPT), n],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "HOME": str(home)},
    )
    return res.returncode, res.stdout.strip()


def test_first_claim_lands_in_the_staging_dir_never_the_repo(repo, tmp_path):
    code, out = claim(repo, "4627", tmp_path)
    path = tmp_path / ".claude" / "we-inbox" / "org-app" / "claims" / "pr-4627"
    assert (code, out) == (0, f"claimed {path}")
    assert path.exists()
    assert not (repo / ".weside").exists()
    assert claim(repo, "#4627", tmp_path) == (1, f"covered: {path}")


def test_https_origin_and_an_evidence_line_cover_it(repo, tmp_path):
    subprocess.run(
        ["git", "remote", "set-url", "origin", "https://github.com/org/app"], cwd=repo, check=True
    )
    inbox = repo / ".weside" / "optimization" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "x.md").write_text("- 2026-10-07 retro PR #4627 | session …\n")
    assert claim(repo, "4627", tmp_path) == (1, f"covered: {inbox / 'x.md'}")
    assert claim(repo, "462", tmp_path)[0] == 0  # PR #4627 does not cover #462


def test_bad_argument(repo, tmp_path):
    assert claim(repo, "abc", tmp_path)[0] == 2
