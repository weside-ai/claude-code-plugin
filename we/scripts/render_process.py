#!/usr/bin/env python3
"""The one renderer of the crew process (L0): the templates under ``process/`` filled from a crew.

Usage:
  render_process.py --role R [--from DIR]      what a session of role R sees at start: the text
                                               ``process_on_start.py`` prints (``worker`` → the
                                               short form, every other role → the L0), then the
                                               text ``role_on_start.py`` prints (role card,
                                               addendum, extra repos) for the role's holder (a
                                               specialist: the card alone)
  render_process.py --all-roles [--from DIR]   one line per role (``ROLE_KEYS``, ``master``,
                                               ``worker``, ``specialist``): role, L0 chars, card
                                               plus addendum chars, ok or the budget exceeded
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
``t2_second_reviewer`` (that member's name), or a
dotted key of the merged crew (``crew.load`` merges ``DEFAULTS``, so every key has a value). A list
renders ``a-b`` (en dash) for two numbers, else joined by ``, ``. A null or empty value takes the fallback; a
token with neither raises ``RenderError``, so a template change cannot ship a hole.

Role cards (L1): ``roles/<role>.md`` per role of ``all_roles``, the five ``CARD_HEADINGS`` and
nothing else, raw ≤ ``CARD_RAW_BUDGET``; rendered with the same tokens (``render_card``).
``card_parts`` collects what ``role_on_start.py`` prints for one session and ``compose`` joins it,
cut to ``BUDGET`` (order and cut rule: ``compose``); ``--total`` counts the same text, so the gate
and the hook cannot drift.

``--total`` parts (``total_rows``), the definition of an instruction layer this gate bounds:
``L0`` (this renderer's text for the role), ``plugin-hook`` (the framing ``role_on_start.py``
prints around its parts: headers, separators, cut lines; with the part rows below it sums to that
hook's whole output), ``card``, ``addendum`` (the repo addendum ``.weside/roles/<slug>.md``),
``extra-head`` (each extra repo's ``AGENTS.md`` head), ``extra-hooks`` (each extra repo's
SessionStart command output as the hook last recorded it, as printed after the cut; never run here,
a command without a record counts 0 and adds the row ``note`` ``NOT_RUN``), ``role-skill``
(a pinned member's role skill, ``crew.skill_path``: ``materialize_on_start.py`` makes that
session invoke or read it at start), ``instructions`` (each
``AGENTS.md``, ``CLAUDE.md``, ``CLAUDE.local.md`` from the workplace up through every ancestor,
plus ``<home>/.claude/CLAUDE.md``), ``rules`` (each ``.claude/rules/**/*.md`` of the workplace and
of ``<home>/.claude/rules`` that ``rule_loading.parse_rule`` calls always-on), ``extra`` (per
extra repo: its ``CLAUDE.md`` and always-on rules, never its ``AGENTS.md``). ``rules-any-file`` (rules with ``paths: "**"``, loaded on
the first file read) is printed and not summed. Not counted: auto memory, the skill listing, MCP
instructions, a companion's identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, NamedTuple

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import crew as crewlib  # noqa: E402
import rule_loading  # noqa: E402

PROCESS = _HERE.parent / "process"
ROLES = _HERE.parent / "roles"
REFERENCE = _HERE.parent / "references" / "working-mode.md"
POINTER = f"Read {REFERENCE} before routing, starting a session or moving a ticket."
BUDGET = 9_500
CARD_RAW_BUDGET = 5_500
ADDENDUM_BUDGET = 3_500
CARD_HEADINGS = (
    "## Cornerstone",
    "## You do",
    "## You never",
    "## At start",
    "## You wait on / others wait on you",
)
HOOK_TIMEOUT = 10
EXTRA_HOOKS_CAP = 15  # seconds, all extra repos' SessionStart hooks of one session together
NOT_RUN = "extra-hooks not run (measure only)"
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


# --- role cards (L1) -----------------------------------------------------------------------


class Parts(NamedTuple):
    """What ``role_on_start.py`` prints for one session, before ``compose`` cuts it."""

    role: str
    card: str
    addendum: tuple[Path, str] | None
    heads: list[tuple[Path, str]]  # (extra repo, AGENTS.md head lines)
    hooks: list[tuple[Path, str, str]]  # (extra repo, command, output or failure line)
    notes: tuple[str, ...] = ()  # one line each, after card and addendum, never cut


def card_headings(text: str) -> list[str]:
    return [line.rstrip() for line in text.split("\n") if line.startswith("## ")]


def render_card(crew: dict[str, Any], role: str, roles: Path = ROLES) -> str:
    """The role card for ``role`` (``all_roles``) filled from ``crew``."""
    return render((roles / f"{role}.md").read_text(encoding="utf-8"), crew).strip("\n")


def addendum_path(crew_path: Path, crew: dict[str, Any], role: str, slug: str) -> Path:
    """A pinned member's ``<workplace>/.weside/roles/<slug>.md``; an unpinned session's
    ``<crew repo>/.weside/roles/<role>.md``."""
    if slug:
        return crewlib.workplace_path(crew_path, crew, slug) / ".weside" / "roles" / f"{slug}.md"
    return crew_path.parent.parent.resolve() / ".weside" / "roles" / f"{role}.md"


def agents_head(repo: Path) -> str | None:
    """``repo/AGENTS.md`` up to its first level-2 heading, or None."""
    path = repo / "AGENTS.md"
    if not path.is_file():
        return None
    head = []
    for line in path.read_text(encoding="utf-8", errors="replace").split("\n"):
        if line.startswith("## "):
            break
        head.append(line)
    return "\n".join(head).strip("\n") or None


def _matches(matcher: Any, source: str) -> bool:
    if not isinstance(matcher, str) or matcher in ("", "*"):
        return True
    try:
        return re.fullmatch(matcher, source) is not None
    except re.error:
        return matcher == source


def session_start_commands(repo: Path, source: str) -> list[str]:
    """The ``type: command`` SessionStart hooks of ``repo/.claude/settings.json`` whose matcher
    takes ``source``, in order; an unreadable file gives none."""
    path = repo / ".claude" / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = ((data.get("hooks") or {}) if isinstance(data, dict) else {}).get("SessionStart")
    commands = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or not _matches(entry.get("matcher"), source):
            continue
        for hook in entry.get("hooks") or []:
            if isinstance(hook, dict) and hook.get("type") == "command" and hook.get("command"):
                commands.append(str(hook["command"]))
    return commands


def _record_path(repo: Path, command: str) -> Path:
    """Where the last printed output of ``command`` in ``repo`` is kept:
    ``$WE_STATE_DIR/extra-hooks/<hash>.txt`` (default ``~/.claude/we-state``)."""
    state = os.environ.get("WE_STATE_DIR") or str(Path.home() / ".claude" / "we-state")
    key = hashlib.sha256(f"{repo}\0{command}".encode()).hexdigest()[:24]
    return Path(state).expanduser() / "extra-hooks" / f"{key}.txt"


def recorded_output(repo: Path, command: str) -> str | None:
    """The output ``command`` printed in ``repo`` at its last run by the hook, or None."""
    try:
        return _record_path(repo, command).read_text(encoding="utf-8")
    except OSError:
        return None


def _record(repo: Path, command: str, output: str) -> None:
    path = _record_path(repo, command)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")
    except OSError:
        pass  # a measurement aid: the hook output does not depend on it


def run_extra_hook(
    repo: Path,
    command: str,
    hook_input: dict[str, Any],
    timeout: float = HOOK_TIMEOUT,
    timeout_line: str | None = None,
) -> str:
    """The command's context as Claude Code would take it in ``repo`` (``additionalContext`` of
    a JSON answer, else stdout), or the line ``extra hook failed: <command>`` (``timeout_line``,
    when given, on a timeout). What it returns is recorded for ``recorded_output``."""
    output = _run_extra_hook(repo, command, hook_input, timeout, timeout_line)
    _record(repo, command, output)
    return output


def _run_extra_hook(
    repo: Path,
    command: str,
    hook_input: dict[str, Any],
    timeout: float,
    timeout_line: str | None,
) -> str:
    payload = {**hook_input, "cwd": str(repo)}
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo)}
    try:
        done = subprocess.run(
            command,
            shell=True,
            cwd=repo,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return timeout_line or f"extra hook failed: {command}"
    except OSError:
        return f"extra hook failed: {command}"
    if done.returncode != 0:
        return f"extra hook failed: {command}"
    out = done.stdout.strip("\n")
    try:
        data = json.loads(out)
    except ValueError:
        return out
    context = (
        (data.get("hookSpecificOutput") or {}).get("additionalContext")
        if isinstance(data, dict)
        else None
    )
    return str(context).strip("\n") if context else out


def card_parts(
    crew_path: Path,
    crew: dict[str, Any],
    role: str,
    slug: str = "",
    hook_input: dict[str, Any] | None = None,
    run_hooks: bool = True,
) -> Parts:
    """The parts for a session of ``role`` (``slug``: the pinned member, empty for an unpinned
    master or worker). Extra repos are the member's ``crew.extra_repos`` that exist here; a
    missing one is the note ``extra repo <value> not found, skipped``, so the card never depends
    on an extra repo. The notes end with ``POINTER``. Hooks run only with ``run_hooks``, all of
    them within ``EXTRA_HOOKS_CAP`` seconds together (a hook past it: ``extra hook skipped, total
    cap N s reached: <command>``); without, ``hooks`` holds the ``recorded_output`` of each
    command that has one. OSError and CrewError (unknown
    member, missing workplace) propagate."""
    card = render_card(crew, role)
    path = addendum_path(crew_path, crew, role, slug)
    addendum = (path, path.read_text(encoding="utf-8").strip("\n")) if path.is_file() else None
    extras, missing = crewlib.extra_repos(crew_path, crew, slug) if slug else ([], [])
    notes = [f"extra repo {value} not found, skipped" for value in missing]
    heads = [(repo, head) for repo in extras if (head := agents_head(repo))]
    hooks: list[tuple[Path, str, str]] = []
    hook_input = hook_input or {}
    source = str(hook_input.get("source") or "startup")
    commands = [
        (repo, command) for repo in extras for command in session_start_commands(repo, source)
    ]
    if run_hooks:
        deadline = time.monotonic() + EXTRA_HOOKS_CAP
        for repo, command in commands:
            capped = f"extra hook skipped, total cap {EXTRA_HOOKS_CAP} s reached: {command}"
            left = deadline - time.monotonic()
            if left <= 0:
                hooks.append((repo, command, capped))
                continue
            timeout = min(HOOK_TIMEOUT, left)
            line = capped if timeout < HOOK_TIMEOUT else None
            hooks.append((repo, command, run_extra_hook(repo, command, hook_input, timeout, line)))
    else:
        for repo, command in commands:
            recorded = recorded_output(repo, command)
            if recorded is not None:
                hooks.append((repo, command, recorded))
    notes.append(POINTER)
    return Parts(role, card, addendum, heads, hooks, tuple(notes))


def _fit(body: str, room: int, marker: str) -> str | None:
    """``body`` within ``room`` chars: whole, else its first whole lines plus ``marker``; None
    when not even the marker fits."""
    if len(body) <= room:
        return body
    keep = room - len(marker) - 1
    if keep < 0:
        return None if len(marker) > room else marker
    cut = body.rfind("\n", 0, keep + 1)
    return marker if cut <= 0 else f"{body[:cut]}\n{marker}"


def compose(parts: Parts, budget: int = BUDGET) -> tuple[str, dict[str, int]]:
    """(text, chars per part as printed). Order: card, addendum, each extra repo's ``AGENTS.md``
    head, each extra hook's output. Card plus addendum over ``budget`` raises ``RenderError``
    naming the addendum. The rest takes what is left: heads first, so hook output is cut first
    (``… cut, full output: <command> in <repo>``), then heads (``… cut, full text:
    <repo>/AGENTS.md``); a part whose cut line does not fit is left out."""
    blocks = [parts.card]
    sizes = {"card": len(parts.card), "addendum": 0, "extra-head": 0, "extra-hooks": 0}
    if parts.addendum:
        path, text = parts.addendum
        blocks.append(f"Repo addendum ({path}):\n{text}")
        sizes["addendum"] = len(text)
    if parts.notes:
        blocks.append("\n".join(parts.notes))
    base = "\n\n".join(blocks)
    if len(base) > budget:
        where = parts.addendum[0] if parts.addendum else ROLES / f"{parts.role}.md"
        raise RenderError(
            f"role card {parts.role} plus addendum {where} has {len(base)} chars > {budget}"
        )
    used = len(base)
    sections = [
        (
            "extra-head",
            f"Extra repo {repo}, AGENTS.md head:\n",
            head,
            f"… cut, full text: {repo}/AGENTS.md",
        )
        for repo, head in parts.heads
    ]
    sections += [
        (
            "extra-hooks",
            f"Extra repo {repo}, SessionStart `{command}`:\n",
            output,
            f"… cut, full output: {command} in {repo}",
        )
        for repo, command, output in parts.hooks
    ]
    for kind, header, body, marker in sections:
        room = budget - used - 2 - len(header)
        shown = _fit(body, room, marker) if room > 0 else None
        if shown is None:
            continue
        blocks.append(header + shown)
        sizes[kind] += len(shown)
        used += 2 + len(header) + len(shown)
    return "\n\n".join(blocks), sizes


def session_text(
    crew_path: Path,
    crew: dict[str, Any],
    role: str,
    slug: str = "",
    hook_input: dict[str, Any] | None = None,
    run_hooks: bool = True,
) -> str:
    """What ``role_on_start.py`` prints for that session."""
    return compose(card_parts(crew_path, crew, role, slug, hook_input, run_hooks))[0]


def holder_slug(crew: dict[str, Any], role: str) -> str:
    """The slug holding ``role`` (a role key), else empty."""
    slug = crew.get("roles", {}).get(role) if role in crewlib.ROLE_KEYS else None
    return slug if isinstance(slug, str) and slug in crewlib.members(crew) else ""


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
    """(label, session kind, member slug) per session of ``role``; a specialist role gives one
    each."""
    if role == "master":
        return [("master", "unnamed", "")]
    if role == "worker":
        return [("worker", "worker", "")]
    if role == "specialist":
        return [
            (f"specialist {e['name']}", "named", slug)
            for slug, e in crewlib.members(crew).items()
            if e.get("specialist")
        ]
    if role not in crewlib.ROLE_KEYS:
        raise crewlib.CrewError(f"{crew_path}: unknown role {role}")
    name = crewlib.holder_name(crew, role)
    return [(f"{role} {name}", "named", holder_slug(crew, role))] if name else []


def _places(
    crew_path: Path, crew: dict[str, Any], slug: str, label: str, absent: list[str] | None
) -> list[Path]:
    """A member's workplace then extra repos, the crew repo for an unpinned session; empty (and
    ``label`` noted in ``absent``) when one is missing and ``absent`` is a list."""
    if not slug:
        return [crew_path.parent.parent.resolve()]
    try:
        return crewlib.workplace_paths(crew_path, crew, slug)
    except crewlib.CrewError:
        if absent is None:
            raise
        absent.append(label)
        return []


class Total(NamedTuple):
    """One session's always-loaded total: ``slug`` empty for an unpinned master or worker."""

    label: str
    slug: str
    rows: list[tuple[str, str, int]]
    total: int


def limit_key(role: str, slug: str, limits: dict[str, Any]) -> str:
    """The ``role_total_chars`` key bounding a session: ``<role>:<slug>`` when present, else the
    role key."""
    member_key = f"{role}:{slug}" if slug else ""
    return member_key if member_key and member_key in limits else role


def total_rows(
    crew_path: Path,
    crew: dict[str, Any],
    role: str,
    home: Path | None = None,
    absent: list[str] | None = None,
) -> list[Total]:
    """Per session of ``role``: its ``Total`` (rows of (part, path, chars), sum). CrewError for an
    unknown role or a workplace that does not exist, unless ``absent`` is a list: then such a
    session is left out and its label appended there (a CI checkout without the sibling repos);
    RenderError for a card plus addendum over ``BUDGET``."""
    home = home or Path.home()
    out = []
    for label, kind, slug in _sessions(crew_path, crew, role):
        places = _places(crew_path, crew, slug, label, absent)
        if not places:
            continue
        work, extras = places[0], places[1:]
        hook_input = {"source": "startup", "cwd": str(work)}
        parts = card_parts(crew_path, crew, role, slug, hook_input, run_hooks=False)
        text, sizes = compose(parts)
        pairs = [(repo, c) for repo in extras for c in session_start_commands(repo, "startup")]
        commands = [c for _, c in pairs]
        unrecorded = any(recorded_output(repo, c) is None for repo, c in pairs)
        rows: list[tuple[str, str, int]] = [
            (
                "L0",
                f"process/{'L0-worker' if kind == 'worker' else 'L0'}.md",
                len(render_l0(crew, "worker" if kind == "worker" else "full")),
            ),
            ("plugin-hook", "hooks/role_on_start.py", len(text) - sum(sizes.values())),
            ("card", f"roles/{role}.md", sizes["card"]),
            (
                "addendum",
                str(parts.addendum[0]) if parts.addendum else "-",
                sizes["addendum"],
            ),
            ("extra-head", ", ".join(str(r) for r, _ in parts.heads) or "-", sizes["extra-head"]),
            ("extra-hooks", ", ".join(commands) or "-", sizes["extra-hooks"]),
        ]
        if unrecorded:
            rows.append(("note", NOT_RUN, 0))
        skill = None
        if kind == "named":
            name = str(crewlib.members(crew)[slug].get("name") or slug)
            skill = crewlib.skill_path(name, work, home)
        rows.append(
            ("role-skill", str(skill[0]) if skill else "-", _chars(skill[0]) if skill else 0)
        )
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
        out.append(Total(label, slug, rows, total))
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
    for label, _, rows, total in total_rows(crew_path, crew, role, Path(home) if home else None):
        print(f"# {label}")
        summed = [r for r in rows if r[0] != "rules-any-file"]
        for part, path, n in summed:
            print(f"{part}\t{path}\t{n}")
        print(f"sum\t\t{total}")
        for part, path, n in rows[len(summed) :]:  # informational, not summed
            print(f"{part}\t{path}\t{n}")


def _print_sizes(crew_path: Path, crew: dict[str, Any]) -> None:
    for role in all_roles():
        n = len(role_text(crew, role))
        card = len(session_text(crew_path, crew, role, holder_slug(crew, role), run_hooks=False))
        ok = "ok" if max(n, card) <= BUDGET else f"> {BUDGET}"
        print(f"{role}\t{n}\t{card}\t{ok}")


def _print_role(crew_path: Path, crew: dict[str, Any], role: str) -> None:
    slug = holder_slug(crew, role)
    hook_input = {"source": "startup", "cwd": str(crew_path.parent.parent.resolve())}
    sys.stdout.write(role_text(crew, role))
    sys.stdout.write("\n\n" + session_text(crew_path, crew, role, slug, hook_input) + "\n")


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
            _print_sizes(crew_path, crew)
        elif args.total:
            _print_totals(crew_path, crew, args.role, args.home)
        else:
            _print_role(crew_path, crew, args.role)
    except (crewlib.CrewError, RenderError, OSError) as exc:
        print(f"render_process: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
