"""risk_paths.py: the plugin repo classifies its own brake changes, rules from origin/main only.

Each case builds a throwaway repo whose `refs/remotes/origin/main` carries this checkout's
`.weside/risk-paths`; `HEAD` carries the fixture change. No network.

Run: `python3 -m pytest -q we/scripts/test_risk_paths.py`
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("risk_paths.py")
RULES = Path(__file__).resolve().parents[2] / ".weside" / "risk-paths"

# AC 7: every path of the plugin's [brake-change] section.
BRAKE = [
    ".weside/risk-paths",
    ".github/CODEOWNERS",
    "we/hooks/automerge_gate.py",
    "we/hooks/hooks.json",
    "we/hooks/verification_gate.py",
    "we/scripts/ready_gate.py",
    "we/scripts/lens_verdict.py",
    "we/scripts/board_freeze.py",
    "we/scripts/risk_paths.py",
    "we/scripts/worker_launch.py",
]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def commit(repo: Path, msg: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD").strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.invalid")
    git(tmp_path, "config", "user.name", "t")
    write(tmp_path, ".weside/risk-paths", RULES.read_text())
    write(tmp_path, "README.md", "x\n")
    for rel in BRAKE[1:]:
        write(tmp_path, rel, "# original\n")
    base = commit(tmp_path, "base")
    git(tmp_path, "update-ref", "refs/remotes/origin/main", base)
    git(tmp_path, "checkout", "-q", "-b", "feat")
    return tmp_path


def classify(repo: Path, base: str = "origin/main") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), base], cwd=repo, capture_output=True, text=True, check=False
    )


def test_codeowners_names_every_brake_path() -> None:
    """The owner reviews every brake path, CODEOWNERS included."""
    owners = (RULES.parent.parent / ".github" / "CODEOWNERS").read_text().splitlines()
    owned = {line.split()[0].lstrip("/") for line in owners if line and not line.startswith("#")}
    assert owned == set(BRAKE)


@pytest.mark.parametrize("rel", BRAKE)
def test_each_brake_path_is_one_way_brake_change(repo: Path, rel: str) -> None:
    write(repo, rel, "# changed\n")
    commit(repo, "touch")
    out = classify(repo)
    assert out.returncode == 0, out.stderr
    lines = out.stdout.splitlines()
    assert lines[0] == "T2 one-way brake-change"
    assert lines[1] == "review: high"
    assert f"{rel}\tbrake-change: path {rel}" in lines


def test_a_docs_change_is_t0(repo: Path) -> None:
    write(repo, "README.md", "y\n")
    commit(repo, "docs")
    out = classify(repo)
    assert out.returncode == 0, out.stderr
    assert out.stdout.splitlines() == ["T0", "review: standard"]


def test_emptied_rules_and_a_hook_change_still_classify_by_mains_rules(repo: Path) -> None:
    write(repo, ".weside/risk-paths", "")
    write(repo, "we/hooks/automerge_gate.py", "# allow everything\n")
    commit(repo, "empty the rules")
    out = classify(repo)
    assert out.returncode == 0, out.stderr
    assert out.stdout.splitlines()[0] == "T2 one-way brake-change"
    assert "we/hooks/automerge_gate.py\tbrake-change: path we/hooks/automerge_gate.py" in (
        out.stdout
    )


def test_a_rename_away_from_a_brake_path_counts(repo: Path) -> None:
    git(repo, "mv", "we/hooks/automerge_gate.py", "we/hooks/gate_old.py")
    commit(repo, "rename")
    assert classify(repo).stdout.splitlines()[0] == "T2 one-way brake-change"


def _mains_rules(repo: Path, text: str) -> None:
    git(repo, "checkout", "-q", "main")
    write(repo, ".weside/risk-paths", text)
    main = commit(repo, "rules")
    git(repo, "update-ref", "refs/remotes/origin/main", main)
    git(repo, "checkout", "-q", "-b", "feat2")


def test_glob_grammar_and_order(repo: Path) -> None:
    _mains_rules(
        repo,
        "[t2]\npath docs/**\n[money]\npath **/pay.py\n[brake-change]\npath ci/{a,b}.yml\n",
    )
    write(repo, "docs/x/y.md", "x\n")
    commit(repo, "t2 only")
    assert classify(repo).stdout.splitlines()[:2] == ["T2", "review: standard"]
    write(repo, "pay.py", "x\n")
    commit(repo, "root pay.py: **/ matches zero dirs")
    assert classify(repo).stdout.splitlines()[0] == "T2 one-way money"
    write(repo, "ci/b.yml", "x\n")
    commit(repo, "brake wins by order")
    lines = classify(repo).stdout.splitlines()
    assert lines[0] == "T2 one-way brake-change"
    assert "pay.py\tmoney: path **/pay.py" in lines


def test_star_stays_in_one_directory(repo: Path) -> None:
    _mains_rules(repo, "[money]\npath src/*.py\n")
    write(repo, "src/deep/x.py", "x\n")
    commit(repo, "deep")
    assert classify(repo).stdout.splitlines()[0] == "T0"


@pytest.mark.parametrize(
    ("rules", "message"),
    [
        ("[money]\nline any **/*.py DROP\n", "a `line` rule needs the repo's own risk.command"),
        ("[money]\nfrom paid-seam-modules\n", "a `from` rule needs the repo's own risk.command"),
        ("[money]\n[t2]\npath x\n", "section [money] has no rule"),
        ("[nope]\npath x\n", "unknown section [nope]"),
        ("path x\n", "rule before the first section"),
        ("[money]\nglob x\n", "not a rule: glob x"),
        ("# nothing\n", "holds no section"),
    ],
)
def test_rules_outside_the_grammar_exit_2(repo: Path, rules: str, message: str) -> None:
    _mains_rules(repo, rules)
    out = classify(repo)
    assert out.returncode == 2
    assert out.stdout == ""
    assert message in out.stderr


def test_without_origin_main_exit_2(repo: Path) -> None:
    git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    out = classify(repo, "main")
    assert out.returncode == 2 and "origin/main" in out.stderr


def test_without_a_rules_file_on_main_exit_2(repo: Path) -> None:
    _mains_rules(repo, "")
    git(repo, "checkout", "-q", "main")
    git(repo, "rm", "-q", ".weside/risk-paths")
    main = commit(repo, "drop rules")
    git(repo, "update-ref", "refs/remotes/origin/main", main)
    out = classify(repo)
    assert out.returncode == 2 and ".weside/risk-paths" in out.stderr


def test_a_base_ahead_of_main_exit_2(repo: Path) -> None:
    write(repo, "README.md", "z\n")
    commit(repo, "ahead")
    out = classify(repo, "HEAD")
    assert out.returncode == 2
    assert "is not an ancestor of origin/main" in out.stderr


@pytest.mark.parametrize("argv", [[], ["a", "b"], ["--rules-from=HEAD"]])
def test_bad_arguments_exit_2(repo: Path, argv: list[str]) -> None:
    out = subprocess.run(
        [sys.executable, str(SCRIPT), *argv], cwd=repo, capture_output=True, text=True, check=False
    )
    assert out.returncode == 2 and "usage" in out.stderr
