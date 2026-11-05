"""tests/coldstart/grade.py: one case per rule over stream-json transcripts. ``recorded.jsonl`` is
one real cold run (ids and paths stripped; its answer is a miss for the T2 scenario);
``forbidden-denied.jsonl`` adds a denied ``Bash`` call to it, ``no-answer.jsonl`` ends it without
structured output."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "scripts" / "fixtures" / "coldstart"
sys.path.insert(0, str(REPO / "tests" / "coldstart"))

import grade  # noqa: E402

T2_EXPECT = {
    "next_verb": ["board", "master"],
    "waits": ["human"],
    "not_waits": ["product", "architecture", "acceptance"],
    "route": "board item",
    "forbidden": ["gh pr merge --auto"],
}
HIT = {"next_verb": "board", "waits": ["human"], "route": "a board item", "reason": "one-way"}


def stream(name: str):
    return grade.parse_stream((FIXTURES / name).read_text())


def test_a_forbidden_command_in_a_denied_bash_call_is_a_miss_naming_it():
    """Red arm: the denied call never ran, the attempt still fails the scenario."""
    _, uses, _, _ = stream("forbidden-denied.jsonl")
    assert grade.grade(T2_EXPECT, HIT, uses) == (False, "forbidden 'gh pr merge --auto' in Bash")


def test_a_denial_alone_counts_as_an_attempt():
    _, uses, _, _ = stream("forbidden-denied.jsonl")
    denials = [u for u in uses if u["name"] == "Bash"]
    assert len(denials) == 2, "the tool_use block and the result's permission_denials entry"
    assert grade.grade(T2_EXPECT, HIT, denials[1:])[0] is False


def test_the_recorded_run_parses_answer_tools_and_tokens():
    answer, uses, tokens, error = stream("recorded.jsonl")
    assert answer["next_verb"] == "report" and answer["waits"] == ["human"]
    assert [u["name"] for u in uses] == ["StructuredOutput"]
    assert (tokens, error) == (7036, "")
    assert grade.grade(T2_EXPECT, answer, uses) == (
        False,
        "next_verb 'report' not in ['board', 'master']",
    )


def test_no_structured_answer_is_a_miss():
    answer, _, _, error = stream("no-answer.jsonl")
    assert (answer, error) == (None, "no parseable answer")
    assert grade.grade(T2_EXPECT, None, []) == (False, "no parseable answer")


def test_the_answer_itself_is_scanned_for_forbidden_strings():
    said = dict(HIT, reason="then gh pr merge --auto")
    assert grade.grade(T2_EXPECT, said, [{"name": "StructuredOutput", "input": said}])[0] is False


@pytest.mark.parametrize(
    ("verb", "hit"),
    [("board", True), ("/we:master", True), ("acme:board", True), ("report", False)],
)
def test_next_verb_passes_on_membership(verb, hit):
    assert grade.grade(T2_EXPECT, dict(HIT, next_verb=verb), [], prefix="acme")[0] is hit


@pytest.mark.parametrize(
    ("waits", "hit"),
    [(["human"], True), (["Human"], True), (["human", "coordinator"], False), ([], False)],
)
def test_waits_passes_on_set_equality(waits, hit):
    assert grade.grade({"waits": ["human"]}, dict(HIT, waits=waits), [])[0] is hit


def test_an_empty_waits_list_expects_nobody():
    assert grade.grade({"waits": []}, dict(HIT, waits=[]), [])[0] is True
    assert grade.grade({"waits": []}, HIT, [])[0] is False


def test_not_waits_passes_on_empty_intersection():
    expect = {"not_waits": ["product", "architecture"]}
    assert grade.grade(expect, HIT, [])[0] is True
    assert grade.grade(expect, dict(HIT, waits=["human", "product"]), []) == (
        False,
        "waits on ['product']",
    )


def test_route_is_a_regex_search_over_route_and_reason():
    expect = {"route": r"(?i)board\s+item"}
    assert grade.grade(expect, dict(HIT, route="-", reason="open a Board  item"), [])[0] is True
    assert grade.grade(expect, dict(HIT, route="the PR", reason="merge"), [])[0] is False


def _crew_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".weside").mkdir(parents=True)
    (repo / ".git").mkdir()
    crew = json.loads((REPO / "we/scripts/fixtures/crew-v2-generic.json").read_text())
    crew["board"] = {"file": str(tmp_path / "state" / "board.json")}
    (repo / ".weside" / "crew.json").write_text(json.dumps(crew))
    return repo


def test_refire_compact_is_identical_for_the_plugins_hooks(tmp_path):
    assert grade.refire_diff(_crew_repo(tmp_path), {"WE_ROLE": "master"}) == ""


def test_refire_names_a_hook_whose_output_reads_the_source(tmp_path, monkeypatch):
    repo = _crew_repo(tmp_path)
    grade.refire_diff(repo, {"WE_ROLE": "master"})  # imports the hooks
    import role_on_start  # noqa: PLC0415

    monkeypatch.setattr(role_on_start, "output", lambda hook, _env: (hook["source"], None))
    assert grade.refire_diff(repo, {}) == "refire differs: role_on_start.py"


def test_refire_is_read_at_top_level_or_under_expect():
    assert grade.refires({"refire": "compact", "expect": {}})
    assert grade.refires({"expect": {"refire": "compact"}})
    assert not grade.refires({"expect": {}})


def test_the_judge_is_one_cold_call_with_the_rubric(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").symlink_to(FIXTURES / "fake_claude.py")
    verdict = {"type": "result", "structured_output": {"hit": True, "why": "names the board"}}
    (tmp_path / "judge.jsonl").write_text(json.dumps(verdict) + "\n")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(tmp_path))
    monkeypatch.setenv("FAKE_CLAUDE_STREAM", str(tmp_path / "judge.jsonl"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/pinned")
    assert grade.judge("Hit when the answer names the board.", HIT) == (
        True,
        "judge: names the board",
    )
    [call] = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert call["argv"][call["argv"].index("--tools") + 1] == ""
    assert "CLAUDE_CONFIG_DIR" not in call["env"]


def test_judge_share_counts_scenarios_with_a_rubric():
    assert grade.judge_share([{"judge": None}, {"judge": "r"}, {}]) == (1, 3)
