"""tests/coldstart/receipt_gate.py against fixture bodies (scripts/fixtures/coldstart/bodies/) on
throwaway repos: one master and one worker scenario, a PR branch off ``main``. ``@DIGEST@`` in a
body is replaced by the digest the test names."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BODIES = REPO / "scripts" / "fixtures" / "coldstart" / "bodies"
sys.path.insert(0, str(REPO / "tests" / "coldstart"))

import affected  # noqa: E402
import receipt_gate  # noqa: E402

GIT_ID = ("-c", "user.name=t", "-c", "user.email=t@example.invalid")


def _scenario(role: str) -> str:
    return f"id: x\nrole: {role}\ncrew: fx/crew.json\nprompt: p\nexpect:\n  route: x\n"


class Repo:
    def __init__(self, root: Path):
        self.root = root

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *GIT_ID, *args], cwd=self.root, check=True, capture_output=True, text=True
        ).stdout

    def commit(self, rel: str, text: str) -> None:
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(text)
        self.git("add", rel)
        self.git("commit", "-qm", rel)

    def check(self, body: str, base: str = "main"):
        return receipt_gate.check(body, base, self.root)

    def digest(self, *ids: str) -> str:
        return affected.digest(set(ids), self.root)


@pytest.fixture
def repo(tmp_path):
    """``main`` with the suite; HEAD on branch ``pr``."""
    r = Repo(tmp_path / "r")
    r.root.mkdir()
    r.git("init", "-q", "-b", "main")
    for rel, text in {
        "we/process/L0.md": "l0\n",
        "we/roles/master.md": "m\n",
        "we/roles/worker.md": "w\n",
        "we/skills/x/SKILL.md": "---\nname: x\ndescription: d\n---\n",
        "fx/crew.json": "{}\n",
        "tests/coldstart/master/a.yaml": _scenario("master"),
        "tests/coldstart/worker/b.yaml": _scenario("worker"),
        "README.md": "r\n",
    }.items():
        r.commit(rel, text)
    r.git("checkout", "-qb", "pr")
    return r


def body(name: str, digest: str = "") -> str:
    return (BODIES / f"{name}.md").read_text().replace("@DIGEST@", digest)


def test_a_master_card_pr_without_a_receipt_fails_with_no_receipt(repo):
    """Red arm: today no check fails this PR."""
    repo.commit("we/roles/master.md", "m2\n")
    assert repo.check(body("missing")) == (False, ["no receipt: 1 affected scenarios (master/a)"])


def test_the_cli_exits_1_on_no_receipt_and_0_on_green(repo, tmp_path, capsys):
    repo.commit("we/roles/master.md", "m2\n")
    missing, green = tmp_path / "missing.md", tmp_path / "green.md"
    missing.write_text(body("missing"))
    green.write_text(body("green", repo.digest("master/a")))
    args = ["--base", "main", "--root", str(repo.root), "--body-file"]
    assert receipt_gate.main([*args, str(missing)]) == 1
    assert capsys.readouterr().out.startswith("no receipt")
    assert receipt_gate.main([*args, str(green)]) == 0


def test_the_body_comes_from_the_env_variable(repo, monkeypatch, capsys):
    repo.commit("we/roles/master.md", "m2\n")
    monkeypatch.setenv("PR_BODY", body("green", repo.digest("master/a")))
    assert receipt_gate.main(["--base", "main", "--root", str(repo.root)]) == 0
    assert capsys.readouterr().out.startswith("receipt green: 1 affected scenarios")


def test_a_green_receipt_for_the_head_passes(repo):
    repo.commit("we/roles/master.md", "m2\n")
    passed, lines = repo.check(body("green", repo.digest("master/a")))
    assert passed and lines == [
        f"receipt green: 1 affected scenarios, digest {repo.digest('master/a')}"
    ]


def test_a_red_receipt_fails_naming_its_reasons(repo):
    repo.commit("we/roles/master.md", "m2\n")
    assert repo.check(body("red", repo.digest("master/a"))) == (
        False,
        ["receipt red: gated miss master/a 2/3"],
    )


def test_a_cap_overrun_fails_as_red(repo):
    repo.commit("we/roles/master.md", "m2\n")
    assert repo.check(body("cap-overrun", repo.digest("master/a"))) == (
        False,
        ["receipt red: cap runs 6 > 3; not run master/a"],
    )


def test_a_receipt_for_another_scope_fails_naming_the_left_out_scenario(repo):
    repo.commit("we/roles/master.md", "m2\n")
    assert repo.check(body("wrong-scope", repo.digest("worker/b"))) == (
        False,
        ["affected scenario left out: master/a"],
    )


def test_an_unreadable_block_fails(repo):
    repo.commit("we/roles/master.md", "m2\n")
    assert repo.check(body("unreadable")) == (
        False,
        ["receipt unreadable: no JSON block after the marker"],
    )


def test_a_pr_touching_no_suite_input_passes_without_a_block(repo):
    repo.commit("README.md", "r2\n")
    repo.commit("we/skills/x/SKILL.md", "---\nname: x\ndescription: d\n---\nbody\n")
    assert repo.check(body("no-input")) == (True, ["no suite input changed"])


def test_a_gated_scenario_needs_three_hits_even_in_a_green_block(repo):
    repo.commit("we/roles/master.md", "m2\n")
    forged = body("green", repo.digest("master/a")).replace('"hits": 3', '"hits": 2')
    assert repo.check(forged) == (False, ["gated miss master/a 2/3"])


def test_a_scenario_below_its_rate_may_miss(repo):
    repo.commit("tests/coldstart/rates.json", '{"scenarios": {"master/a": {"gated": false}}}\n')
    repo.commit("we/roles/master.md", "m2\n")
    loose = body("green", repo.digest("master/a")).replace('"hits": 3', '"hits": 1')
    assert repo.check(loose)[0] is True


def test_cost_over_target_passes_with_one_line_in_the_summary(repo, tmp_path, monkeypatch):
    repo.commit("tests/coldstart/rates.json", '{"cost_target_tokens": 1000}\n')
    repo.commit("we/roles/master.md", "m2\n")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("PR_BODY", body("green", repo.digest("master/a")))
    assert receipt_gate.main(["--base", "main", "--root", str(repo.root)]) == 0
    assert "- cost over target: 21000 > 1000\n" in summary.read_text()


# --- AC 10: the digest, recomputed on the head -----------------------------------------------


def test_a_receipt_from_the_head_before_a_card_edit_fails_on_the_digest(repo):
    """Red arm first: without the digest comparison this stale receipt passes."""
    repo.commit("we/roles/master.md", "m2\n")
    stale = repo.digest("master/a")
    repo.commit("we/roles/master.md", "m3\n")
    head = repo.digest("master/a")
    assert repo.check(body("green", stale)) == (False, [f"receipt digest {stale} != head {head}"])


def test_a_receipt_whose_digest_belongs_to_another_branch_fails(repo):
    repo.commit("we/roles/master.md", "m2\n")
    repo.git("checkout", "-qb", "other", "main")
    repo.commit("we/roles/master.md", "other\n")
    foreign = repo.digest("master/a")
    repo.git("checkout", "-q", "pr")
    assert repo.check(body("green", foreign))[1] == [
        f"receipt digest {foreign} != head {repo.digest('master/a')}"
    ]


def test_a_merge_of_main_that_touches_no_input_keeps_the_receipt_green(repo):
    repo.commit("we/roles/master.md", "m2\n")
    receipt = body("green", repo.digest("master/a"))
    repo.git("checkout", "-q", "main")
    repo.commit("README.md", "main moved\n")
    repo.git("checkout", "-q", "pr")
    repo.git("merge", "-q", "--no-edit", "main")
    assert repo.check(receipt)[0] is True


def test_git_failing_on_the_base_exits_2(repo, capsys):
    assert receipt_gate.main(["--base", "no-such-ref", "--root", str(repo.root)]) == 2
    assert "coldstart-receipt: git" in capsys.readouterr().err
