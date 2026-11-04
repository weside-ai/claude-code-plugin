#!/usr/bin/env python3
"""The one renderer of the crew process (L0): the templates under ``process/`` filled from a crew.

Usage:
  render_process.py --role R [--from DIR]      what ``process_on_start.py`` prints for a session of
                                               role R (``worker`` → the short form, every other
                                               role → the L0)
  render_process.py --all-roles [--from DIR]   one size line per role (``ROLE_KEYS``, ``master``,
                                               ``worker``, ``specialist``)
  render_process.py --role R --total [--from DIR] [--home DIR]
                                               what a session of role R always loads: one row per
                                               counted part (part, path, chars), then the sum
  render_process.py --serves --from DIR        exit 0 iff ``process_on_start.py`` prints the L0 for
                                               a session there (a crew loads and both forms render
                                               within ``BUDGET``), else 1

Templates: ``process/L0.md`` (every session but a worker) and ``process/L0-worker.md``. A token is
``{key}`` or ``{key|fallback}``. ``key`` is a role key of ``crew.ROLE_KEYS`` (the holder's name,
else the fallback, else the role's title), ``human`` (``human.name``), ``specialists`` (``Name
(field)`` of every member with ``specialist``; the line holding it is dropped when there is none),
``local_rules`` (one bullet each; the section holding it is dropped when there is none),
``t2_second_reviewer`` (that member's name), ``capacity_line`` (the host's memory split), or a
dotted key of the merged crew (``crew.load`` merges ``DEFAULTS``, so every key has a value). A list
renders ``a-b`` (en dash) for two numbers, else joined by ``, ``. A null or empty value takes the fallback; a
token with neither raises ``RenderError``, so a template change cannot ship a hole.

``--total`` parts (``total_rows``), the definition of an instruction layer this gate bounds:
``L0`` (this renderer's text for the role), ``plugin-hook`` (the other always-on model context
this plugin prints at SessionStart: ``working_mode_on_start.core``), ``instructions`` (each
``AGENTS.md``, ``CLAUDE.md``, ``CLAUDE.local.md`` from the workplace up through every ancestor,
plus ``<home>/.claude/CLAUDE.md``), ``rules`` (each ``.claude/rules/**/*.md`` of the workplace and
of ``<home>/.claude/rules`` that ``rule_loading.parse_rule`` calls always-on), ``extra`` (per
extra repo: its ``CLAUDE.md`` and always-on rules, never its ``AGENTS.md``), ``card`` and
``addendum`` (0 until role cards exist). ``rules-any-file`` (rules with ``paths: "**"``, loaded on
the first file read) is printed and not summed. Not counted: auto memory, the skill listing, MCP
instructions, a companion's identity.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import crew as crewlib  # noqa: E402
import rule_loading  # noqa: E402
import working_mode_on_start  # noqa: E402 - the plugin's other always-on SessionStart text

PROCESS = _HERE.parent / "process"
BUDGET = 9_500
EXTRA_KINDS = ("master", "worker", "specialist")
ROLE_TITLES = {
    "product": "the product owner",
    "architecture": "the architect",
    "acceptance": "the tester",
    "machinery": "the machinery owner",
    "coordinator": "the coordinator",
    "escalation": "the escalation owner",
    "hr": "the HR owner",
}
INSTRUCTION_NAMES = ("AGENTS.md", "CLAUDE.md", "CLAUDE.local.md")
EN_DASH = "\u2013"
TOKEN = re.compile(r"\{([a-z_][a-z0-9_.]*)(?:\|([^{}\n]*))?\}")


class RenderError(Exception):
    """A template token that resolves against neither the crew nor its fallback."""


def all_roles() -> tuple[str, ...]:
    return (*crewlib.ROLE_KEYS, *EXTRA_KINDS)


def _dotted(crew: dict[str, Any], key: str) -> Any:
    value: Any = crew
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise RenderError(f"token {{{key}}}: no such crew key")
        value = value[part]
    return value


def _show(value: Any) -> str | None:
    if value is None or value in ([], ""):
        return None
    if isinstance(value, list):
        if len(value) == 2 and all(crewlib._is_int(v) for v in value):
            return f"{value[0]}{EN_DASH}{value[1]}"
        return ", ".join(str(v) for v in value)
    return str(value)


def _specialists(crew: dict[str, Any]) -> str | None:
    found = [
        f"{entry['name']} ({entry['specialist']})"
        for entry in crewlib.members(crew).values()
        if entry.get("specialist")
    ]
    return ", ".join(found) or None


def _capacity_line(crew: dict[str, Any]) -> str | None:
    cap = crew.get("capacity") or {}
    if cap.get("pod_gib") is None:
        return None
    parts = [f"pod {cap['pod_gib']} GiB minus gate lock (≤ {cap.get('gate_lock_gib') or '?'})"]
    parts.append(f"test slot (≤ {cap.get('test_slot_gib') or '?'}) and devbox")
    return ", ".join(parts)


def _local_rules(crew: dict[str, Any]) -> str | None:
    rules = [" ".join(str(r).split()) for r in crew.get("local_rules") or []]
    return "\n".join(f"- {r}" for r in rules if r) or None


def _second_reviewer(crew: dict[str, Any]) -> str | None:
    slug = (crew.get("sla") or {}).get("t2_second_reviewer")
    entry = crewlib.members(crew).get(slug) if slug else None
    return str(entry["name"]) if entry else None


SPECIAL = {
    "human": lambda crew: _show((crew.get("human") or {}).get("name")),
    "specialists": _specialists,
    "local_rules": _local_rules,
    "t2_second_reviewer": _second_reviewer,
    "capacity_line": lambda crew: (
        _capacity_line(crew) or "the host's memory minus the gate lock, the test slot and devboxes"
    ),
}


def _resolve(crew: dict[str, Any], key: str) -> str | None:
    if key in crewlib.ROLE_KEYS:
        return crewlib.holder_name(crew, key)
    if key in SPECIAL:
        return SPECIAL[key](crew)
    return _show(_dotted(crew, key))


def render(template: str, crew: dict[str, Any]) -> str:
    """``template`` with every token filled from ``crew``; see the module docstring."""
    drop_lines = {"specialists": _resolve(crew, "specialists") is None}
    drop_section = _resolve(crew, "local_rules") is None
    if drop_section:
        template = re.sub(r"\n## [^\n]*\n\n\{local_rules\}\n", "\n", template)
    lines = [
        line
        for line in template.split("\n")
        if not any(f"{{{k}}}" in line and dropped for k, dropped in drop_lines.items())
    ]

    def fill(match: re.Match) -> str:
        key, fallback = match.group(1), match.group(2)
        value = _resolve(crew, key)
        if value is not None:
            return value
        if fallback is not None:
            return fallback
        if key in ROLE_TITLES:
            return ROLE_TITLES[key]
        raise RenderError(f"token {{{key}}} has no value in the crew and no fallback")

    return TOKEN.sub(fill, "\n".join(lines))


def render_l0(crew: dict[str, Any], kind: str = "full", process: Path = PROCESS) -> str:
    """The L0 (``kind`` ``full``) or the worker short form (``worker``) for ``crew``."""
    name = "L0-worker.md" if kind == "worker" else "L0.md"
    return render((process / name).read_text(encoding="utf-8"), crew)


def role_text(crew: dict[str, Any], role: str, process: Path = PROCESS) -> str:
    """What ``process_on_start.py`` prints for a session of ``role``."""
    return render_l0(crew, "worker" if role == "worker" else "full", process)


def serves(start: str | Path) -> bool:
    try:
        _, crew = crewlib.find_and_load(start)
        if crew is None:
            return False
        return all(len(render_l0(crew, kind)) <= BUDGET for kind in ("full", "worker"))
    except (crewlib.CrewError, RenderError, OSError):
        return False


# --- role totals ---------------------------------------------------------------------------


def _chars(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="replace"))


def _rules(root: Path) -> tuple[list[Path], list[Path]]:
    """(always-on, ``paths: "**"``) rule files under ``root/.claude/rules``."""
    always, any_file = [], []
    rules_dir = root / ".claude" / "rules"
    if not rules_dir.is_dir():
        return always, any_file
    for path in sorted(rules_dir.rglob("*.md")):
        rule = rule_loading.load_rule(path)
        if rule.is_always_on:
            always.append(path)
        elif set(rule.patterns) == {"**"}:
            any_file.append(path)
    return always, any_file


def _sessions(crew_path: Path, crew: dict[str, Any], role: str) -> list[tuple[str, str, str]]:
    """(label, session kind, pin) per session of ``role``; a specialist role gives one each."""
    if role == "master":
        return [("master", "unnamed", "")]
    if role == "worker":
        return [("worker", "worker", "")]
    if role == "specialist":
        return [
            (f"specialist {e['name']}", "named", str(e["name"]))
            for e in crewlib.members(crew).values()
            if e.get("specialist")
        ]
    if role not in crewlib.ROLE_KEYS:
        raise crewlib.CrewError(f"{crew_path}: unknown role {role}")
    name = crewlib.holder_name(crew, role)
    return [(f"{role} {name}", "named", name)] if name else []


def total_rows(
    crew_path: Path, crew: dict[str, Any], role: str, home: Path | None = None
) -> list[tuple[str, list[tuple[str, str, int]], int]]:
    """Per session of ``role``: (label, rows of (part, path, chars), sum). CrewError for an
    unknown role or a workplace that does not exist."""
    home = home or Path.home()
    out = []
    for label, kind, pin in _sessions(crew_path, crew, role):
        if kind == "named":
            places = crewlib.workplace_paths(crew_path, crew, pin)
        else:
            places = [crew_path.parent.parent.resolve()]
        work, extras = places[0], places[1:]
        rows: list[tuple[str, str, int]] = [
            (
                "L0",
                f"process/{'L0-worker' if kind == 'worker' else 'L0'}.md",
                len(render_l0(crew, "worker" if kind == "worker" else "full")),
            ),
            (
                "plugin-hook",
                "hooks/working_mode_on_start.py",
                len(working_mode_on_start.core(crew, kind, pin)),
            ),
            ("card", "-", 0),
            ("addendum", "-", 0),
        ]
        seen: set[Path] = set()
        for directory in (work, *work.parents):
            for name in INSTRUCTION_NAMES:
                path = (directory / name).resolve()
                if path.is_file() and path not in seen:
                    seen.add(path)
                    rows.append(("instructions", str(path), _chars(path)))
        user = (home / ".claude" / "CLAUDE.md").resolve()
        if user.is_file() and user not in seen:
            rows.append(("instructions", str(user), _chars(user)))
        any_file: list[Path] = []
        for root in (work, home):  # the workplace's rules, then the user's (~/.claude/rules)
            always, loose = _rules(root)
            rows += [("rules", str(p), _chars(p)) for p in always]
            any_file += loose
        for repo in extras:
            claude_md = repo / "CLAUDE.md"
            if claude_md.is_file():
                rows.append(("extra", str(claude_md), _chars(claude_md)))
            always, _ = _rules(repo)
            rows += [("extra", str(p), _chars(p)) for p in always]
        total = sum(n for _, _, n in rows)
        rows += [("rules-any-file", str(p), _chars(p)) for p in any_file]
        out.append((label, rows, total))
    return out


# --- CLI ---------------------------------------------------------------------------------


def _load(start: str | None) -> tuple[Path, dict[str, Any]] | None:
    try:
        crew_path, crew = crewlib.find_and_load(start)
    except crewlib.CrewError as exc:
        print(f"crew: {exc}", file=sys.stderr)
        return None
    if crew_path is None or crew is None:
        print("crew: no crew file here", file=sys.stderr)
        return None
    return crew_path, crew


def _print_totals(crew_path: Path, crew: dict[str, Any], role: str, home: str | None) -> None:
    for label, rows, total in total_rows(crew_path, crew, role, Path(home) if home else None):
        print(f"# {label}")
        summed = [r for r in rows if r[0] != "rules-any-file"]
        for part, path, n in summed:
            print(f"{part}\t{path}\t{n}")
        print(f"sum\t\t{total}")
        for part, path, n in rows[len(summed) :]:  # informational, not summed
            print(f"{part}\t{path}\t{n}")


def _print_sizes(crew: dict[str, Any]) -> None:
    for role in all_roles():
        n = len(role_text(crew, role))
        print(f"{role}\t{n}\t{'ok' if n <= BUDGET else f'> {BUDGET}'}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--role")
    parser.add_argument("--all-roles", action="store_true")
    parser.add_argument("--total", action="store_true")
    parser.add_argument("--serves", action="store_true")
    parser.add_argument("--from", dest="start")
    parser.add_argument("--home")
    args = parser.parse_args(argv)
    if args.serves:
        return 0 if serves(args.start or Path.cwd()) else 1
    loaded = _load(args.start)
    if loaded is None:
        return 1
    crew_path, crew = loaded
    if not args.all_roles and args.role not in all_roles():
        print(f"render_process: --role takes one of {', '.join(all_roles())}", file=sys.stderr)
        return 2
    try:
        if args.all_roles:
            _print_sizes(crew)
        elif args.total:
            _print_totals(crew_path, crew, args.role, args.home)
        else:
            sys.stdout.write(role_text(crew, args.role))
    except (crewlib.CrewError, RenderError) as exc:
        print(f"render_process: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
