"""Every cold-start case (`tests/coldstart/<dir>/<id>.yaml`) has the scenario keys the harness
(`tests/coldstart/run.py`) reads (epic format § 5.1): `id` (= the file name), `role`, `crew` (an
existing fixture), `prompt`, `expect`; the suite holds at least 20 cases, at most a fifth of them
judged by a model, and the routing pair. These checks are regex-only: the 3.9 floor lane has no
PyYAML."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CASES = sorted((REPO / "tests" / "coldstart").glob("**/*.yaml"))
KEYS = ("id", "role", "crew", "prompt", "expect")
sys.path.insert(0, str(REPO / "we" / "scripts"))

import crew as crewlib  # noqa: E402
import render_process  # noqa: E402

sys.path.insert(0, str(REPO / "tests" / "coldstart"))
import grade  # noqa: E402

TOP = re.compile(r"^([a-z_]+):(.*)$", re.MULTILINE)


MIN_CASES = 20
MAX_JUDGE_SHARE = 0.2
ROUTING = {"worker/route-plan-story.yaml": "plan-story", "master/route-merged.yaml": "merged"}


def test_the_suite_holds_at_least_twenty_cases():
    assert len(CASES) >= MIN_CASES, len(CASES)


def test_at_most_a_fifth_of_the_cases_have_a_judge():
    judged = [
        p.name for p in CASES if re.search(r"^judge: (?!null\s*$)\S", p.read_text(), re.MULTILINE)
    ]
    assert len(judged) <= MAX_JUDGE_SHARE * len(CASES), judged


@pytest.mark.parametrize(("name", "verb"), sorted(ROUTING.items()))
def test_the_routing_pair_asks_an_intent_without_naming_the_skill(name, verb):
    text = (REPO / "tests" / "coldstart" / name).read_text(encoding="utf-8")
    assert re.search(r"^routing: true$", text, re.MULTILINE)
    assert re.search(rf"^  next_verb: \[{verb}\]$", text, re.MULTILINE)
    prompt = text.split("\nprompt:", 1)[1].split("\nexpect:", 1)[0]
    assert verb not in prompt, "the prompt names the skill it should route to"


def test_the_two_process_cases_exist():
    names = {p.relative_to(REPO / "tests" / "coldstart").as_posix() for p in CASES}
    assert {"master/t2-oneway-human-merges.yaml", "product/board-only-inbox.yaml"} <= names


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.stem)
def test_case_has_the_scenario_keys(case: Path):
    top = {k: v.strip() for k, v in TOP.findall(case.read_text(encoding="utf-8"))}
    assert set(KEYS) <= set(top), sorted(set(KEYS) - set(top))
    assert top["id"] == case.stem
    assert top["role"] in render_process.all_roles()
    assert (REPO / top["crew"]).is_file(), top["crew"]
    assert top["prompt"] and not top["expect"], "prompt is text, expect a block"


ROUTE = re.compile(r'^  route: "(.*)"$', re.MULTILINE)
ENV = re.compile(r"^env: \{(WESIDE_COMPANION|WE_ROLE): (\w+)\}$", re.MULTILINE)
CARD_CASES = sorted((REPO / "tests" / "coldstart").glob("*/card-cornerstone.yaml"))


def test_one_card_case_per_role():
    assert {p.parent.name for p in CARD_CASES} == set(render_process.all_roles())


@pytest.mark.parametrize("case", CARD_CASES, ids=lambda p: p.parent.name)
def test_card_case_names_its_role_an_environment_and_a_route_regex(case: Path):
    text = case.read_text(encoding="utf-8")
    top = {k: v.strip() for k, v in TOP.findall(text)}
    assert top["role"] == case.parent.name
    assert ENV.search(text), "env: one of WESIDE_COMPANION or WE_ROLE"
    [route] = ROUTE.findall(text)
    re.compile(route.encode().decode("unicode_escape"))


@pytest.mark.parametrize("case", CARD_CASES, ids=lambda p: p.parent.name)
def test_the_route_matches_the_cards_own_cornerstone_and_first_move(case: Path):
    """The expected answer is the card's own text: a route the card cannot satisfy is wrong."""
    role = case.parent.name
    crew = crewlib._merge(
        json.loads((REPO / "we/scripts/fixtures/crew-v2-generic.json").read_text())
    )
    card = render_process.render_card(crew, role)
    cornerstone = card.split("## Cornerstone", 1)[1].split("## You do", 1)[0]
    first = card.split("## At start", 1)[1].split("## You wait on", 1)[0]
    [route] = ROUTE.findall(case.read_text(encoding="utf-8"))
    assert re.search(route.encode().decode("unicode_escape"), cornerstone + first)


UNKNOWN_KEY_CASE = REPO / "tests" / "coldstart" / "master" / "crew-unknown-key.yaml"


def test_an_unknown_crew_key_keeps_the_full_l0_with_the_line_on_startup_and_compact(
    tmp_path, monkeypatch
):
    """The hook output the case's session sees: the full L0, one notice line, identical after
    ``/compact`` (``refire: compact``)."""
    sys.path.insert(0, str(REPO / "we" / "hooks"))
    import process_on_start  # noqa: PLC0415

    text = UNKNOWN_KEY_CASE.read_text(encoding="utf-8")
    top = {k: v.strip() for k, v in TOP.findall(text)}
    assert top["refire"] == "compact"
    [route] = ROUTE.findall(text)
    repo = tmp_path / "repo"
    (repo / ".weside").mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / ".weside" / "crew.json").write_text((REPO / top["crew"]).read_text())
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # the served log, never the real one
    env = {"WE_ROLE": "master"}
    outs = [
        process_on_start.output({"cwd": str(repo), "source": source, "session_id": "s"}, env)
        for source in ("startup", "compact")
    ]
    assert outs[0] == outs[1] and outs[0][1] is None
    first, rest = outs[0][0].split("\n\n", 1)
    assert re.search(route, first) and first.startswith("crew.json: unknown keys ignored: limitz")
    generic = json.loads((REPO / "we/scripts/fixtures/crew-v2-generic.json").read_text())
    assert rest == render_process.render_l0(crewlib._merge(generic))


RATES = REPO / "tests" / "coldstart" / "rates.json"
CASE_IDS = {f"{p.parent.name}/{p.stem}" for p in CASES}


def rates_problems(table: dict, ids: set[str]) -> list[str]:
    """What is wrong with a ``rates.json`` table for the suite ``ids``."""
    problems = []
    for key in ("model", "run_budget_usd", "release_cap", "cost_target_tokens", "scenarios"):
        if key not in table:
            problems.append(f"no {key}")
    cap = table.get("release_cap") or {}
    if not (isinstance(cap.get("runs"), int) and cap["runs"] > 0 and cap.get("wall_minutes")):
        problems.append("release_cap needs runs and wall_minutes")
    rows = table.get("scenarios") or {}
    problems += [f"row for unknown scenario {sid}" for sid in sorted(set(rows) - ids)]
    if not table.get("measured"):
        return problems + (["rows without a measurement"] if rows else [])
    for key in ("date", "model", "digest", "runs_per_scenario"):
        if key not in table["measured"]:
            problems.append(f"measured lacks {key}")
    if not isinstance(table.get("suite_tokens_one_run"), int):
        problems.append("no suite_tokens_one_run")
    problems += [f"no row for {sid}" for sid in sorted(ids - set(rows))]
    for sid, row in sorted(rows.items()):
        runs, hits = row.get("runs", 0), row.get("hits", 0)
        if runs < 10:
            problems.append(f"{sid}: {runs} runs < 10")
        if row.get("gated") != (hits * 10 >= 9 * runs):
            problems.append(f"{sid}: gated is not hits >= 9/10")
        if not row.get("gated") and not str(row.get("defect") or "").strip():
            problems.append(f"{sid}: below 9/10 without a defect line")
    return problems


def test_rates_json_has_the_shape_the_harness_reads():
    """Until the first measurement (a pod run) the table holds its caps and no rows; after it,
    every scenario has a row with 10 runs, gated by the entry rule, and a defect when below."""
    table = json.loads(RATES.read_text())
    assert rates_problems(table, CASE_IDS) == []
    assert table["model"] == "claude-opus-5-5 medium"


GOOD = {
    "model": "m",
    "run_budget_usd": 1.0,
    "release_cap": {"runs": 69, "wall_minutes": 30},
    "cost_target_tokens": 1,
    "measured": {"date": "d", "model": "m", "digest": "x", "runs_per_scenario": 10},
    "suite_tokens_one_run": 5,
    "scenarios": {
        "a/x": {"runs": 10, "hits": 9, "gated": True},
        "a/y": {"runs": 10, "hits": 8, "gated": False, "defect": "card line 3 is vague"},
    },
}


@pytest.mark.parametrize(
    ("patch", "problem"),
    [
        ({}, None),
        (
            {"a/y": {"runs": 10, "hits": 8, "gated": False}},
            "a/y: below 9/10 without a defect line",
        ),
        ({"a/y": {"runs": 10, "hits": 8, "gated": True}}, "a/y: gated is not hits >= 9/10"),
        ({"a/x": {"runs": 3, "hits": 3, "gated": True}}, "a/x: 3 runs < 10"),
        ({"a/x": None}, "no row for a/x"),
    ],
)
def test_the_rates_rules_refuse_each_defect(patch, problem):
    rows = {k: v for k, v in {**GOOD["scenarios"], **patch}.items() if v is not None}
    found = rates_problems({**GOOD, "scenarios": rows}, {"a/x", "a/y"})
    assert found == ([problem] if problem else [])


def test_board_only_inbox_takes_the_board_answer_its_route_names():
    """The measured answer (route hit every run) names the board as its verb: the expectation
    follows it, the prompt stays."""
    yaml = pytest.importorskip("yaml")
    scn = yaml.safe_load((REPO / "tests/coldstart/product/board-only-inbox.yaml").read_text())
    answer = {"next_verb": "board", "waits": [], "route": "the board", "reason": "one inbox"}
    assert grade.grade(scn["expect"], answer, []) == (True, "ok")
