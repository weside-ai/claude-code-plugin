"""Pins the council shells: one tool set for every member, one list of shipped roles.

A council member reads the tree and speaks to its peers; it never writes, runs or spawns. So every
`agents/council-*.md`, the generic `council-member` included, carries exactly the tool set below,
and the effort is set so a member never inherits the session's. The shipped-role list in
`references/apo-hierarchy.md` must name exactly the role shells, or a lead reading it seats a role
on the wrong shell.

Run with: python3 -m pytest -q we/scripts/test_council_shells.py
"""

from __future__ import annotations

import re
from pathlib import Path

WE = Path(__file__).resolve().parent.parent
AGENTS = WE / "agents"
APO = WE / "references" / "apo-hierarchy.md"

EXPECTED = {
    "tools": "[Read, Glob, Grep, SendMessage]",
    "model": "sonnet",
    "effort": "medium",
}


def _frontmatter(path: Path) -> dict[str, str]:
    found = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", path.read_text(encoding="utf-8"), re.DOTALL)
    assert found, f"{path.name}: no YAML frontmatter"
    return dict(re.findall(r"^([a-z_]+):[ \t]*(.*?)[ \t]*$", found.group(1), re.MULTILINE))


def _shells() -> list[Path]:
    return sorted(AGENTS.glob("council-*.md"))


def shell_violations(shells: list[Path]) -> list[str]:
    problems = []
    for path in shells:
        fm = _frontmatter(path)
        for key, want in EXPECTED.items():
            if fm.get(key) != want:
                problems.append(f"{path.name}: {key} is {fm.get(key)!r}, must be {want!r}")
    return problems


def shipped_roles_line(text: str) -> set[str]:
    found = re.search(r"Shipped role shells:(.*?)\(agent", text, re.DOTALL)
    assert found, "apo-hierarchy.md: no 'Shipped role shells:' line"
    return set(re.findall(r"`([a-z_]+)`", found.group(1)))


def roster_mismatch(shells: list[Path], listed: set[str]) -> list[str]:
    on_disk = {p.stem.removeprefix("council-").replace("-", "_") for p in shells} - {"member"}
    problems = []
    if on_disk - listed:
        problems.append(f"apo-hierarchy.md does not list the shells {sorted(on_disk - listed)}")
    if listed - on_disk:
        problems.append(f"apo-hierarchy.md lists roles without a shell {sorted(listed - on_disk)}")
    return problems


def test_generic_member_shell_ships():
    assert (AGENTS / "council-member.md").is_file()


def test_every_council_shell_has_the_member_tool_set():
    shells = _shells()
    assert len(shells) >= 10
    assert shell_violations(shells) == []


def test_apo_hierarchy_lists_exactly_the_role_shells():
    listed = shipped_roles_line(APO.read_text(encoding="utf-8"))
    assert roster_mismatch(_shells(), listed) == []
