"""Every cold-start case (`tests/coldstart/<dir>/<id>.yaml`) has the scenario keys the harness
reads (epic format § 5.1): `id` (= the file name), `role`, `crew` (an existing fixture), `prompt`,
`expect`. The harness itself replaces this check when it lands."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CASES = sorted((REPO / "tests" / "coldstart").glob("**/*.yaml"))
KEYS = ("id", "role", "crew", "prompt", "expect")
sys.path.insert(0, str(REPO / "we" / "scripts"))

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
