"""Every cold-start case (`tests/coldstart/<dir>/<id>.yaml`) has the scenario keys the harness
reads (epic format § 5.1): `id` (= the file name), `role`, `crew` (an existing fixture), `prompt`,
`expect`. The harness itself replaces this check when it lands."""

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

TOP = re.compile(r"^([a-z_]+):(.*)$", re.MULTILINE)


def test_the_two_process_cases_exist():
    names = {p.relative_to(REPO / "tests" / "coldstart").as_posix() for p in CASES}
    assert {"master/t2-oneway-human-merges.yaml", "companion/board-only-inbox.yaml"} <= names


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
