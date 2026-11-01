#!/usr/bin/env python3
"""The one reader of a repo's crew (``.weside/crew.json``): who holds which role.

Usage:
  crew.py path [--from DIR]                 the crew file in force, exit 1 without one
  crew.py show [--from DIR]                 the crew as JSON, roles resolved to member slugs
  crew.py members [--from DIR]              one line per named member: "<name>\\t<title, else role>"
  crew.py skill-path NAME [--cwd DIR]       "<path>\\t<loadable|workplace>\\t<skill|stub>", exit 1 if none
  crew.py stubs [--from DIR] [--write]      members without a role skill; --write creates the stubs

Lookup (``find``): from DIR (default the cwd) upwards, the first ``.weside/crew.json``; a
``.weside/config.json`` whose ``crew`` names another crew file (relative to that repo's root)
counts as that file. The crew is the repo's projection of the account's handbook; the handbook
stays the truth about people. Contract: ``references/working-mode.md`` § Crew.

Schema: ``roles`` maps ``product_owner``, ``orchestrator``, ``hr``, ``tester`` to member slugs;
``members.<slug>`` carries ``name``, ``role`` (the council lens role), optional ``title`` and
``lens``, ``components`` (backlogs the member orders), ``workplace`` (the repo holding the
member's role skill, relative to the repo that holds the crew file) and ``on_call``.
``skill_prefix`` (default ``weside``) names role skills ``<prefix>-<name lowercased>``;
``question_label`` (default ``QUESTION``) opens a question line to the human.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

WORKING_ROLES = ("product_owner", "orchestrator", "hr", "tester")
STUB_MARKER = "<!-- we:stub"
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "companion-skill" / "SKILL.md"
_SAFE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


class CrewError(Exception):
    """A crew file that exists but cannot be used."""


def find(start: str | Path | None = None) -> Path | None:
    """The crew file in force for ``start``, or None."""
    d = Path(start or Path.cwd()).resolve()
    for root in (d, *d.parents):
        own = root / ".weside" / "crew.json"
        if own.is_file():
            return own
        config = root / ".weside" / "config.json"
        if config.is_file():
            try:
                pointer = json.loads(config.read_text(encoding="utf-8")).get("crew")
            except (OSError, ValueError, AttributeError):
                pointer = None
            if isinstance(pointer, str) and pointer.strip():
                target = (root / pointer.strip()).resolve()
                return target if target.is_file() else None
    return None


def load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CrewError(f"{path}: unreadable ({type(exc).__name__})") from exc
    if not isinstance(data, dict) or not isinstance(data.get("members"), dict):
        raise CrewError(f"{path}: needs an object with a members object")
    if not isinstance(data.get("roles", {}), dict):
        raise CrewError(f"{path}: roles is not an object")
    return data


def find_and_load(start: str | Path | None = None) -> tuple[Path | None, dict[str, Any] | None]:
    path = find(start)
    if path is None:
        return None, None
    return path, load(path)


def members(crew: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {k: v for k, v in crew.get("members", {}).items() if isinstance(v, dict)}


def member(crew: dict[str, Any], who: str) -> tuple[str, dict[str, Any]] | None:
    """The member whose slug or name is ``who`` (case-insensitive)."""
    key = who.strip().lower()
    for slug, entry in members(crew).items():
        if slug.lower() == key or str(entry.get("name", "")).strip().lower() == key:
            return slug, entry
    return None


def holder(crew: dict[str, Any], role: str) -> dict[str, Any] | None:
    """The member holding a working-mode role (``roles.<role>`` → slug)."""
    slug = crew.get("roles", {}).get(role)
    entry = members(crew).get(slug) if isinstance(slug, str) else None
    return entry


def holder_name(crew: dict[str, Any], role: str) -> str | None:
    entry = holder(crew, role)
    name = str(entry.get("name", "")).strip() if entry else ""
    return name or None


def skill_name(name: str, crew: dict[str, Any] | None = None) -> str | None:
    prefix = str((crew or {}).get("skill_prefix") or "weside").strip().lower()
    skill = f"{prefix}-{name.strip().lower()}"
    return skill if _SAFE.fullmatch(skill) else None


def workplace(crew_path: Path, entry: dict[str, Any]) -> Path | None:
    value = entry.get("workplace")
    if not isinstance(value, str) or not value.strip():
        return None
    return (crew_path.parent.parent / value.strip()).resolve()


def is_stub(path: Path) -> bool:
    try:
        return STUB_MARKER in path.read_text(encoding="utf-8")
    except OSError:
        return False


def skill_path(name: str, cwd: str | Path, home: Path | None = None) -> tuple[Path, bool] | None:
    """(SKILL.md, loadable) for ``name``'s role skill, or None.

    Loadable: under ``<cwd>/.claude/skills/`` or ``~/.claude/skills/``, where the Skill tool finds
    it. Otherwise the member's ``workplace`` repo (crew in force for ``cwd``): a session reads it.
    """
    try:
        crew_path, crew = find_and_load(cwd)
    except CrewError:
        crew_path, crew = None, None
    skill = skill_name(name, crew)
    if skill is None:
        return None
    for root in (Path(cwd) / ".claude" / "skills", (home or Path.home()) / ".claude" / "skills"):
        if (root / skill / "SKILL.md").is_file():
            return root / skill / "SKILL.md", True
    found = member(crew, name) if crew else None
    place = workplace(crew_path, found[1]) if crew_path and found else None
    if place and (place / ".claude" / "skills" / skill / "SKILL.md").is_file():
        return place / ".claude" / "skills" / skill / "SKILL.md", False
    return None


def render_stub(crew: dict[str, Any], slug: str) -> str:
    entry = members(crew)[slug]
    name = str(entry.get("name") or slug).strip()
    components = ", ".join(str(c) for c in entry.get("components") or []) or "none"
    values = {
        "skill": skill_name(name, crew) or slug,
        "name": name,
        "role": str(entry.get("title") or entry.get("role") or "member").strip(),
        "components": components,
        "hr": holder_name(crew, "hr") or "HR",
    }
    text = TEMPLATE.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", " ".join(value.split()))
    return text


def stubs(crew_path: Path, crew: dict[str, Any], write: bool = False) -> list[str]:
    """One line per member without a role skill in its workplace: the path (written with --write)."""
    lines = []
    for slug, entry in members(crew).items():
        name = str(entry.get("name") or "").strip()
        skill = skill_name(name, crew) if name else None
        place = workplace(crew_path, entry)
        if not skill or place is None:
            continue
        target = place / ".claude" / "skills" / skill / "SKILL.md"
        if target.exists():
            continue
        if write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render_stub(crew, slug), encoding="utf-8")
        lines.append(str(target))
    return lines


def show(crew_path: Path, crew: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(crew_path),
        "roles": {role: crew.get("roles", {}).get(role) for role in WORKING_ROLES},
        "question_label": crew.get("question_label") or "QUESTION",
        "members": {
            slug: {
                "name": entry.get("name"),
                "role": entry.get("role"),
                "components": entry.get("components") or [],
                "workplace": entry.get("workplace"),
                "on_call": bool(entry.get("on_call")),
            }
            for slug, entry in members(crew).items()
        },
    }


def _opt(argv: list[str], flag: str) -> str | None:
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def _skill_path_cli(argv: list[str]) -> int:
    found = skill_path(argv[1], _opt(argv, "--cwd") or Path.cwd()) if len(argv) > 1 else None
    if found is None:
        return 1
    path, loadable = found
    kind = "stub" if is_stub(path) else "skill"
    print(f"{path}\t{'loadable' if loadable else 'workplace'}\t{kind}")
    return 0


def _print_members(crew: dict[str, Any]) -> None:
    for entry in members(crew).values():
        name = str(entry.get("name") or "").strip()
        if name:
            label = entry.get("title") or entry.get("role") or ""
            print(name + "\t" + " ".join(str(label).split()))


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("path", "show", "members", "skill-path", "stubs"):
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    cmd = argv[0]
    if cmd == "skill-path":
        return _skill_path_cli(argv)
    if cmd == "path":
        found = find(_opt(argv, "--from"))
        if found is not None:
            print(found)
        return 0 if found is not None else 1
    try:
        crew_path, crew = find_and_load(_opt(argv, "--from"))
    except CrewError as exc:
        print(f"crew: {exc}", file=sys.stderr)
        return 1
    if crew_path is None or crew is None:
        return 1
    if cmd == "show":
        print(json.dumps(show(crew_path, crew), ensure_ascii=False, indent=2))
    elif cmd == "members":
        _print_members(crew)
    else:
        for line in stubs(crew_path, crew, write="--write" in argv):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
