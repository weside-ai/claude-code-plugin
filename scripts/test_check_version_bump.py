"""check-version-bump.sh in a throwaway git repo: the PR's version must be above main's, compared
numerically per part (8.10.0 is above 8.9.0, 8.0.9 is not above 8.1.0)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "check-version-bump.sh"


def _repo(tmp_path: Path, main: str, pr: str) -> Path:
    plugin = tmp_path / "we" / ".claude-plugin"
    plugin.mkdir(parents=True)

    def commit(version: str) -> None:
        (plugin / "plugin.json").write_text(json.dumps({"version": version}))
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@example.invalid",
                "commit",
                "--allow-empty",
                "-qm",
                version,
            ],
            cwd=tmp_path,
            check=True,
        )

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    commit(main)
    subprocess.run(["git", "branch", "base"], cwd=tmp_path, check=True)
    commit(pr)
    return tmp_path


def _run(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "VERSION_MAIN_REF": "base"}
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("main", "pr"), [("8.1.0", "8.1.1"), ("8.9.0", "8.10.0"), ("8.1.3", "9.0.0")]
)
def test_a_version_above_main_passes(tmp_path, main, pr):
    res = _run(_repo(tmp_path, main, pr))
    assert res.returncode == 0, res.stdout
    assert f"Version bumped: {main} -> {pr}" in res.stdout


@pytest.mark.parametrize(
    ("main", "pr"), [("8.1.0", "8.1.0"), ("8.1.0", "8.0.9"), ("8.10.0", "8.9.9")]
)
def test_an_equal_or_lower_version_fails(tmp_path, main, pr):
    res = _run(_repo(tmp_path, main, pr))
    assert res.returncode == 1
    assert "not above main" in res.stdout
    assert "the master sets the version" in res.stdout


def test_an_unknown_flag_is_refused(tmp_path):
    assert _run(_repo(tmp_path, "1.0.0", "1.0.1"), "--nope").returncode == 2
