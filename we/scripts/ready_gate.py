#!/usr/bin/env python3
"""The Ready gate: is a story plan (or an epic plan) ready for Selected?

Usage:
  ready_gate.py story <plan>        a story plan and, through its ``epic:``, the epic's fence,
                                    ``serves:`` and the goal file
  ready_gate.py epic <epic plan>    ``serves:``, the goal file, the presence of ``fence:`` and the
                                    finish line (``line:``, ``line_goal:``)

Exit 0 ready, 1 refused (one stdout line per failure, ``<plan>:<line>: <place>: <what is
missing>``; the line is the one to fix, left out where nothing in the plan marks the place, such
as a missing section), 2 usage or an unreadable plan. Warnings go to stderr, each prefixed
``warning:``, and never change the exit. There is no option: no caller can switch a check off.

The gate reads the plan file it is given and the crew of its checkout, not the plan from
``origin/main``: it runs on a refiner's branch before the plan lands. The epic plan comes from
``risk.rules_from`` when it is there (a checkout behind a fence extension saw a scope change
the ref no longer has), else from beside the plan. Only the
tier (check 10) needs the plan on ``risk.rules_from`` and defers there with one warning; the short
form's limits (check 9c) are read there too.

The grammar it parses is owned by ``references/story-plan.md`` (§ Oracle-class marker, § What the
Ready gate reads); this docstring only lists the story checks in their order:

1. frontmatter ``story:`` and ``epic:``;
2. the required sections, and no ``## Open Fork``;
3. every AC holds ``**Given**``, ``**When**``, ``**Then**`` and a marker;
4. every marker parses;
5. a ``walk`` part without ``why:`` needs a ``**Files:**`` path on ``oracles.walk_paths``;
6. ``receipt`` ACs: the crew's ``oracles.receipt_check`` runs on the plan, its lines pass through;
7. boundary ACs hand ``--boundary-acs`` and ``--mock-persona`` to that check;
8. the epic plan's ``fence:``, its ``serves:`` against the goal file, the goal file itself; each
   source missing turns its check off with one warning, and the check arms when it lands;
9. seams named: at least one path in some phase's ``**Files:**`` list;
9b. the ``## Verification`` block's ``**Oracle:**`` line, read by the PR hook's own parser
   (``hooks/verification_gate.py``): a line that hook would flag is one warning now, not a
   hint after ``gh pr create`` later (the AC classes ``receipt``/``ci``/``walk`` are no oracle
   there);
9c. the short form (``form: short``): the sections ``SHORT_SECTIONS`` replace the full set, the
   paths come from ``## Files`` (at most ``plans.short_max_files`` of ``.weside/config.json``,
   default 3), and a path on a rule of ``.weside/risk-paths``, a path marked ``(other repo)``,
   or no rules file at all refuses with "use the full form"; both files are read from
   ``risk.rules_from`` (default ``origin/main``), never from the tree that holds the plan;
10. the plan's tier (``plan_tier.py``): the repo's ``risk.command`` on the plan alone, in a
    scratch tree at ``risk.rules_from``. A success prints ``tier: <line 1>`` on stderr, a
    failure is one stdout line ``<plan>: tier: tier not computed: <reason>``; without a
    ``risk.command``, and for a plan not yet on ``risk.rules_from`` (a plan branch: ``board.py
    select`` computes the tier on main), one warning. The epic mode computes no tier.

The epic mode also reads the finish line (``references/epic-plan.md`` § Finish line): an epic
whose ``status:`` starts with ``approved`` without ``line:`` is refused, any other status without
it warns; a ``line:`` present must list keys without a repeat and come with a ``line_goal:``; more
keys than the crew's ``limits.epic_stories`` upper bound is one warning.

``story_failures(plan)`` runs checks 1-9c for ``board.py select``, which runs the tier itself.

Every repo value comes from the crew through ``crew.py`` (a ``CrewError`` is a refusal), except
the short form's two: ``plans.short_max_files`` and the rules file, both read on ``risk.rules_from``. Python
3.9, stdlib only.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import crew  # noqa: E402
import plan_tier  # noqa: E402
import risk_paths  # noqa: E402

_HOOKS = str(Path(__file__).resolve().parent.parent / "hooks")
if _HOOKS not in sys.path:
    sys.path.append(_HOOKS)
import verification_gate  # noqa: E402

EXTENSIONS = "Extensions"  # the epic plan's list of what lies beyond the line
EXTENSION_ITEM = re.compile(r"^- \[([ xX])\] (.*)$")
USAGE = "usage: ready_gate.py story <plan> | ready_gate.py epic <epic plan>"
REQUIRED_SECTIONS = (
    "Context",
    "Acceptance Criteria",
    "User Journey",
    "Testing Requirements",
    "Verification",
    "Technical Approach",
    "Implementation Phases",
    "Out of scope",
    "Constraints and Pins",
    "Design Decisions",
    "Security Review Required",
    "Documentation Impact",
)
# The short form for a defect at one place (story-plan.md § Short form); `## Updates Log` stays
# optional as in the full form.
SHORT = "short"
SHORT_SECTIONS = ("Is", "Should", "Acceptance Criteria", "Files", "Verification")
SHORT_MAX_FILES = 3
RISK_RULES = ".weside/risk-paths"
FULL_FORM = "use the full form (references/story-plan.md § Short form)"
CLASSES = ("receipt", "ci", "walk")
RECEIPT_TIMEOUT = 60
GOAL_OFF = (
    "warning: goal check off: crew.json names no files.goals; add the goal file and bind it to "
    "arm the check"
)

_AC_ITEM = re.compile(r"^(\d+)\.\s")
_PHASE = re.compile(r"^### Phase (\d+)\b")
_LABEL_BULLET = re.compile(r"^- \*\*([^*]+):\*\*\s*(.*)$")
_BULLET = re.compile(r"^\s*- ")
_CLASS = re.compile(r"^`?(receipt|ci|walk)`?(?=[:\s]|$)(.*)$", re.S)
_TOKEN = re.compile(r"^`?([A-Za-z][\w-]*)`?(?=[:\s]|$)")
_SPAN = re.compile(r"`([^`]+)`")
_LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")
_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,5}$")
_OTHER_REPO = re.compile(r"^\s*\(other repo\)")
_METRIC = re.compile(r"^\s*[-*]\s+metric:\s*(.+?)\s*$")
_LINK = re.compile(r"\]\(([^)\s]+)\)")


class Marker:
    """One parsed oracle-class marker: its parts as (class, detail) pairs."""

    def __init__(self, parts: list[tuple[str, str]]) -> None:
        self.parts = parts

    def classes(self) -> list[str]:
        return [cls for cls, _ in self.parts]

    def detail(self, cls: str) -> str | None:
        for name, detail in self.parts:
            if name == cls:
                return detail
        return None


# --- plan text -----------------------------------------------------------------------------


def frontmatter(text: str) -> dict[str, str]:
    """Bare ``key: value`` lines between the leading ``---`` fences; the value taken whole."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep and key.strip() and not key.startswith((" ", "\t")):
            out[key.strip()] = value.strip()
    return out


def inline_list(value: str | None) -> list[str]:
    """``[a, b]`` (or a bare value) as a list of stripped items."""
    if value is None:
        return []
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return [item.strip().strip("'\"") for item in value.split(",") if item.strip()]


def sections(text: str) -> dict[str, str]:
    """Level-2 sections by heading, each body up to the next level-2 heading."""
    out: dict[str, str] = {}
    name = None
    body: list[str] = []
    fenced = False
    for line in text.split("\n"):
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            if name is not None:
                out.setdefault(name, "\n".join(body))
            name, body = line[3:].strip(), []
        elif name is not None:
            body.append(line)
    if name is not None:
        out.setdefault(name, "\n".join(body))
    return out


def acceptance_criteria(text: str) -> list[tuple[int, str]]:
    """The numbered items of ``## Acceptance Criteria``; an item runs to the next item or header,
    its wrapped lines and nested bullets joined into one text."""
    items: list[tuple[int, list[str]]] = []
    in_section = False
    for line in text.split("\n"):
        if line.startswith("#"):
            if in_section:
                break
            in_section = line.strip() == "## Acceptance Criteria"
            continue
        if not in_section:
            continue
        start = _AC_ITEM.match(line)
        if start:
            items.append((int(start.group(1)), [line]))
        elif items:
            items[-1][1].append(line)
    return [(n, " ".join(part.strip() for part in lines).strip()) for n, lines in items]


# --- oracle-class marker -------------------------------------------------------------------


def _top_level(text: str) -> list[tuple[int, int]]:
    """Top-level ``[...]`` spans (start, end inclusive), skipping brackets in backtick spans."""
    spans: list[tuple[int, int]] = []
    depth, start, i = 0, -1, 0
    while i < len(text):
        ch = text[i]
        if ch == "`":
            run = len(text[i:]) - len(text[i:].lstrip("`"))
            close = text.find("`" * run, i + run)
            i = (close + run) if close >= 0 else i + run  # unclosed run: literal (CommonMark)
            continue
        if ch == "[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "]" and depth:
            depth -= 1
            if depth == 0:
                spans.append((start, i))
        i += 1
    return spans


def _split_top(body: str, sep: str) -> list[str]:
    """``body`` split on ``sep`` outside backtick spans and nested brackets."""
    parts, depth, i, last = [], 0, 0, 0
    while i < len(body):
        ch = body[i]
        if ch == "`":
            run = len(body[i:]) - len(body[i:].lstrip("`"))
            close = body.find("`" * run, i + run)
            i = (close + run) if close >= 0 else i + run  # unclosed run: literal (CommonMark)
            continue
        if ch == "[":
            depth += 1
        elif ch == "]" and depth:
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append(body[last:i])
            last = i + 1
        i += 1
    parts.append(body[last:])
    return parts


def marker_body(ac_text: str) -> str | None:
    """The body of the last balanced ``[...]`` that closes the AC's text, else None."""
    text = ac_text.rstrip()
    spans = _top_level(text)
    if not spans or spans[-1][1] != len(text) - 1:
        return None
    start, end = spans[-1]
    return text[start + 1 : end]


def parse_marker(body: str) -> tuple[Marker | None, str | None]:
    """The marker, or None and the reason it does not parse (story-plan.md § Oracle-class
    marker)."""
    parts: list[tuple[str, str]] = []
    for raw in _split_top(body, ";"):
        part = raw.strip()
        found = _CLASS.match(part)
        if found:
            detail = found.group(2).strip()
            if detail.startswith(":"):
                detail = detail[1:].strip()
            parts.append((found.group(1), detail))
        elif parts:
            cls, detail = parts[-1]
            parts[-1] = (cls, f"{detail}; {part}".strip("; "))
        else:
            token = _TOKEN.match(part)
            shown = token.group(1) if token else part or "(empty)"
            return None, f"unknown oracle class `{shown}` (receipt, ci or walk)"
    for cls, detail in parts:
        problem = _detail_problem(cls, detail)
        if problem:
            return None, problem
    return Marker(parts), None


def _detail_problem(cls: str, detail: str) -> str | None:
    if cls == "ci" and not detail:
        return "`ci` names no test (the test, and why staging cannot see it)"
    if cls == "walk":
        fields = [f.strip() for f in detail.split("·")]
        if any(f.startswith("why:") and not f[4:].strip() for f in fields):
            return "`walk` has an empty `why:`"
        named = [f for f in fields if f and not f.startswith("why:")]
        if len(named) < 2:
            return "`walk` needs a persona and a screen (`walk: <persona> · <screen>`)"
    if cls == "receipt" and re.search(r"\bnot-boundary:\s*$", detail):
        return "`not-boundary:` gives no reason"
    return None


def walk_why(marker: Marker) -> bool:
    detail = marker.detail("walk") or ""
    return any(f.strip().startswith("why:") for f in detail.split("·"))


def receipt_boundary(marker: Marker) -> str:
    """``boundary``, ``not-boundary`` or ``""`` as the receipt part says."""
    detail = marker.detail("receipt") or ""
    if re.search(r"\bnot-boundary:", detail):
        return "not-boundary"
    if re.search(r"(?<![\w-])boundary\b", detail):
        return "boundary"
    return ""


# --- phases, paths, globs ------------------------------------------------------------------


class Phase:
    """A phase of the full form; number 0 is the short form's ``## Files`` section."""

    def __init__(self, number: int) -> None:
        self.number = number
        self.repo: str | None = None
        self.paths: list[tuple[str, bool]] = []  # (path, marked "(other repo)")

    @property
    def label(self) -> str:
        return f"phase {self.number}" if self.number else "## Files"


def short_files(text: str) -> Phase:
    """The short form's one seam: the paths of ``## Files``, read like a ``**Files:**`` list."""
    files = Phase(0)
    files.paths = _paths(sections(text).get("Files", "").split("\n"))
    return files


def phases(text: str) -> list[Phase]:
    """Each ``### Phase <n>:`` with its ``**Repo:**`` and the paths under ``**Files:**``."""
    found: list[Phase] = []
    current: Phase | None = None
    files: list[str] | None = None
    for line in text.split("\n"):
        heading = _PHASE.match(line)
        if heading or line.startswith(("## ", "### ")):
            if current is not None and files is not None:
                current.paths = _paths(files)
            current = Phase(int(heading.group(1))) if heading else None
            files = None
            if current is not None:
                found.append(current)
            continue
        if current is None:
            continue
        label = _LABEL_BULLET.match(line)
        if label:
            if files is not None:
                current.paths = _paths(files)
                files = None
            if label.group(1) == "Repo":
                current.repo = label.group(2).strip().strip("`") or None
            elif label.group(1) == "Files":
                files = [label.group(2)]
        elif files is not None:
            files.append(line)
    if current is not None and files is not None:
        current.paths = _paths(files)
    return found


def _paths(lines: list[str]) -> list[tuple[str, bool]]:
    """Path-like backtick spans of a ``**Files:**`` list (story-plan.md § What the Ready gate
    reads): no whitespace, and a ``/``, a leading ``.``, or an extension on a bullet's first span.
    A span shaped like a media type stays here; ``Gate._drop_media_types`` needs the tree to judge it."""
    items: list[str] = []
    for line in lines:
        if _BULLET.match(line) or not items:
            items.append(line)
        else:
            items[-1] += "\n" + line
    out: list[tuple[str, bool]] = []
    for item in items:
        for index, span in enumerate(_SPAN.finditer(item)):
            value = span.group(1)
            if re.search(r"\s", value) or "://" in value:
                continue
            value = _LINE_SUFFIX.sub("", value.split("§")[0]).rstrip("/")
            first = index == 0
            if not value or not (
                "/" in value or value.startswith(".") or (first and _EXTENSION.search(value))
            ):
                continue
            out.append((value, bool(_OTHER_REPO.match(item[span.end() :]))))
    return out


# ``application/pdf`` names no file though it carries a ``/``; a span with an extension
# (``model/user.py``) is a path whatever its first segment
_MEDIA_TYPE = re.compile(
    r"(application|audio|font|image|message|model|multipart|text|video)/[A-Za-z0-9][\w.+-]*"
)


def glob_regex(glob: str) -> re.Pattern[str]:
    """``**`` any depth, ``*`` within one segment, ``?`` one character; a glob ending ``/**``
    also matches the directory itself."""
    out, i = "", 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out += r"(?:.*/)?"
            i += 3
        elif glob.startswith("**", i):
            out += r".*"
            i += 2
        elif glob[i] == "*":
            out += r"[^/]*"
            i += 1
        elif glob[i] == "?":
            out += r"[^/]"
            i += 1
        else:
            out += re.escape(glob[i])
            i += 1
    if out.endswith("/.*"):
        out = out[: -len("/.*")] + r"(?:/.*)?"
    return re.compile(rf"^{out}$")


def matches(path: str, globs: list[str]) -> bool:
    return any(glob_regex(g).match(path) for g in globs)


# --- the checks ----------------------------------------------------------------------------


class Gate:
    def __init__(self, plan: Path, crew_data: dict[str, Any], root: Path) -> None:
        self.plan = plan
        self.crew = crew_data
        self.root = root
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.text = ""

    def fail(self, place: str, message: str, line: int | None = None) -> None:
        """One failure line; ``line`` (1-based, in the plan) names the line to fix."""
        where = f"{self.plan}:{line}" if line else str(self.plan)
        self.failures.append(f"{where}: {place}: {message}")

    def story(self, text: str) -> None:
        self.text = text
        meta = frontmatter(text)
        if not meta.get("story"):
            self.fail("frontmatter", "no `story:`", 1)
        form = meta.get("form", "")
        if form not in ("", SHORT):
            self.fail(
                "frontmatter",
                f"`form: {form}`: `short` or no `form:` line",
                frontmatter_line(text, "form"),
            )
        short = form == SHORT
        present = sections(text)
        for name in SHORT_SECTIONS if short else REQUIRED_SECTIONS:
            if name not in present:
                self.fail(f"## {name}", "section missing")
        if "Open Fork" in present:
            self.fail(
                "## Open Fork",
                "an open fork stands; answer it and delete the section",
                heading_line(text, "Open Fork"),
            )
        found_phases = [short_files(text)] if short else phases(text)
        self._drop_media_types(found_phases)
        if short:
            self._short(found_phases[0], "Files" in present)
        markers = self._acs(text)
        self._walk(markers, found_phases)
        self._receipts(markers)
        epic = self._epic_plan(meta.get("epic"))
        if epic is not None:
            self._fence(epic, meta["epic"], found_phases)
            self._goals(epic)
        elif not short:  # the short form refuses an (other repo) path itself
            self._phase_repos(found_phases)
        if "Implementation Phases" in present and not any(ph.paths for ph in found_phases):
            self.fail(
                "Implementation Phases",
                "no seams named (no path in any Files list)",
                heading_line(text, "Implementation Phases"),
            )
        if "Verification" in present:
            self._oracle_line(text)

    def _short(self, files: Phase, present: bool) -> None:
        """Check 9c: the short form holds a defect at one place, off every risk path."""
        at = heading_line(self.text, "Files")
        paths = list(dict.fromkeys(p for p, _ in files.paths))
        if present and not paths:
            self.fail("## Files", "no path named", at)
        limit = self._short_max_files()
        if limit is not None and len(paths) > limit:
            self.fail(
                "## Files",
                f"{len(paths)} files, the short form holds at most {limit} "
                f"(plans.short_max_files); {FULL_FORM}",
                at,
            )
        for path, other in files.paths:
            if other:
                self.fail(
                    "## Files",
                    f"`{path}` is in another repo; {FULL_FORM}",
                    path_line(self.text, 0, path),
                )
        text = self._on_ref(RISK_RULES)
        if text is None:
            self.fail(
                "## Files",
                f"no {RISK_RULES} on {self._ref()} to check the files against; {FULL_FORM}",
                at,
            )
            return
        globs = risk_globs(text)
        for path in paths:
            hit = next((g for g, pattern in globs if pattern.match(path)), None)
            if hit is not None:
                self.fail(
                    "## Files",
                    f"`{path}` is on the risk path `{hit}` (.weside/risk-paths); {FULL_FORM}",
                    path_line(self.text, 0, path),
                )

    def _short_max_files(self) -> int | None:
        """``plans.short_max_files`` of ``.weside/config.json`` on ``risk.rules_from``, default 3; a
        value that is no positive integer is one failure and None."""
        try:
            config = json.loads(self._on_ref(".weside/config.json") or "{}")
        except ValueError:
            config = {}
        plans = config.get("plans") if isinstance(config, dict) else None
        value = (
            plans.get("short_max_files", SHORT_MAX_FILES)
            if isinstance(plans, dict)
            else SHORT_MAX_FILES
        )
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            self.fail("config", f"plans.short_max_files {value!r} is no positive integer")
            return None
        return value

    def _ref(self) -> str:
        return str((self.crew.get("risk") or {}).get("rules_from") or "origin/main")

    def _on_ref(self, rel: str) -> str | None:
        """``rel`` as committed on ``risk.rules_from``, None when absent or unreadable: the short
        form's limits come from the default branch, never from the tree whose plan they judge."""
        try:
            done = subprocess.run(
                ["git", "-C", str(self.root), "show", f"{self._ref()}:{rel}"],
                capture_output=True,
                text=True,
                timeout=RECEIPT_TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return done.stdout if done.returncode == 0 else None

    def _exists_on_ref(self, rel: str) -> bool | None:
        """Whether a file or directory ``rel`` is on ``risk.rules_from``; None when that tree is
        unreadable (no git, no ref)."""
        try:
            tree = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.root),
                    "rev-parse",
                    "--verify",
                    "-q",
                    f"{self._ref()}^{{tree}}",
                ],
                capture_output=True,
                text=True,
                timeout=RECEIPT_TIMEOUT,
                check=False,
            )
            if tree.returncode != 0:
                return None
            done = subprocess.run(
                ["git", "-C", str(self.root), "cat-file", "-e", f"{tree.stdout.strip()}:{rel}"],
                capture_output=True,
                timeout=RECEIPT_TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return done.returncode == 0

    def _drop_media_types(self, found: list[Phase]) -> None:
        """A span shaped like a media type (``image/png``) is no path when nothing of that name is
        on ``risk.rules_from``. In another repo, or with that tree unreadable, it stays a path: a
        false scope change costs one answer, a missed one lets a plan past its fence."""
        for phase in found:
            if phase.repo is not None:
                continue
            phase.paths = [
                (path, other)
                for path, other in phase.paths
                if other
                or not _MEDIA_TYPE.fullmatch(path)
                or _EXTENSION.search(path)
                or self._exists_on_ref(path) is not False
            ]

    def _oracle_line(self, text: str) -> None:
        """Check 9b: warn now what the PR hook flags at `gh pr create`."""
        problem = verification_gate._receipt_problem(text)
        if problem is not None:
            self.warnings.append(
                f"warning: {self.plan}: ## Verification: the PR hook will flag this plan's "
                f"block: {problem} The AC classes receipt, ci and walk belong in the AC markers; "
                f"the `**Oracle:**` line names how the build was observed "
                f"({verification_gate._MENU}); see references/story-plan.md § Two vocabularies "
                f"named oracle."
            )

    def tier(self, text: str) -> None:
        """Check 10: the plan-only tier; needs the ``story:`` key and a git checkout."""
        key = frontmatter(text).get("story")
        if not key:
            return
        if not self.crew.get("risk", {}).get("command"):
            self.warnings.append(plan_tier.NO_COMMAND)
            return
        top = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if top.returncode != 0:
            self.fail("tier", "tier not computed: not inside a git checkout")
            return
        root = Path(top.stdout.strip())
        try:
            rel = self.plan.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            self.fail("tier", f"tier not computed: the plan lies outside {root}")
            return
        result = plan_tier.plan_tier(self.crew, root, key, rel)
        self.warnings.extend(result.warnings)
        if result.failure is not None and result.failure.startswith(plan_tier.NOT_ON_REF):
            # A plan branch before its merge: `board.py select` computes the tier on main. As a
            # failure it made every refiner's run exit 1, and a real failure above it went unread.
            self.warnings.append(
                f"warning: {self.plan}: tier deferred: {result.failure}; `board.py select` "
                "computes it on main"
            )
        elif result.failure is not None:
            self.fail("tier", f"tier not computed: {result.failure}")
        else:
            self.warnings.append(f"tier: {result.line}")

    def epic(self, text: str) -> None:
        meta = frontmatter(text)
        if "fence" not in meta:
            self.warnings.append(_fence_off(self.plan, self.plan))
        self._line(meta)
        self._goals((self.plan, text))

    def _line(self, meta: dict[str, str]) -> None:
        """The finish line: ``line:`` (story keys) and ``line_goal:`` (one measurable goal)."""
        keys = line_keys(meta)
        if keys is None:
            if meta.get("status", "").startswith("approved"):
                self.fail(
                    "line",
                    "an approved epic has no `line:` (its story keys) and `line_goal:` (one "
                    "measurable goal); the human approves the epic with its line",
                )
            else:
                self.warnings.append(
                    f"warning: {self.plan}: no `line:` yet; the epic is approved with its line"
                )
            return
        if not keys:
            self.fail("line", "`line:` lists no story key")
        repeated = sorted({k for k in keys if keys.count(k) > 1})
        if repeated:
            self.fail("line", "`line:` names " + ", ".join(repeated) + " twice")
        if not meta.get("line_goal", "").strip():
            self.fail("line_goal", "`line:` without `line_goal:` (one measurable goal)")
        bound = (self.crew.get("limits") or {}).get("epic_stories") or [0, 8]
        upper = bound[-1] if isinstance(bound, list) else bound
        if len(keys) > int(upper):
            self.warnings.append(
                f"warning: {self.plan}: `line:` holds {len(keys)} stories, above the crew's "
                f"limit of {upper}; cut a linked epic"
            )

    def _acs(self, text: str) -> dict[int, tuple[Marker, str]]:
        markers: dict[int, tuple[Marker, str]] = {}
        acs = acceptance_criteria(text)
        if not acs and "Acceptance Criteria" in sections(text):
            self.fail(
                "## Acceptance Criteria",
                "no numbered AC",
                heading_line(text, "Acceptance Criteria"),
            )
        at = ac_lines(text)
        for n, ac in acs:
            missing = [w for w in ("Given", "When", "Then") if f"**{w}**" not in ac]
            if missing:
                self.fail(f"AC{n}", "no " + ", ".join(f"`**{w}**`" for w in missing), at.get(n))
            body = marker_body(ac)
            if body is None:
                self.fail(
                    f"AC{n}",
                    "no oracle-class marker `[receipt]`, `[ci: …]` or `[walk: …]`",
                    at.get(n),
                )
                continue
            marker, problem = parse_marker(body)
            if marker is None:
                self.fail(f"AC{n}", problem or "marker does not parse", at.get(n))
                continue
            markers[n] = (marker, ac)
        return markers

    def _walk(self, markers: dict[int, tuple[Marker, str]], found: list[Phase]) -> None:
        walk_paths = list(self.crew["oracles"].get("walk_paths") or [])
        own = [p for ph in found if ph.repo is None for p, _ in ph.paths]
        on_path = any(matches(p, walk_paths) for p in own)
        at = ac_lines(self.text)
        for n, (marker, _) in sorted(markers.items()):
            if "walk" in marker.classes() and not walk_why(marker) and not on_path:
                self.fail(
                    f"AC{n}",
                    "`walk` on a change whose **Files:** touch no walk path "
                    "(crew oracles.walk_paths); add `why: <sentence>` to the marker",
                    at.get(n),
                )

    def _receipts(self, markers: dict[int, tuple[Marker, str]]) -> None:
        receipt = {n: v for n, v in markers.items() if "receipt" in v[0].classes()}
        if not receipt:
            return
        terms = list(self.crew["acceptance"].get("boundary_terms") or [])
        boundary = []
        for n, (marker, ac) in sorted(receipt.items()):
            said = receipt_boundary(marker)
            if said == "boundary" or (said != "not-boundary" and _names_a_term(ac, terms)):
                boundary.append(n)
        persona = self.crew["acceptance"].get("mock_persona")
        at = ac_lines(self.text)
        if boundary and not persona:
            listed = ", ".join(f"AC{n}" for n in boundary)
            self.fail(
                listed,
                "server-boundary receipt AC but the crew names no acceptance.mock_persona",
                at.get(boundary[0]),
            )
        command = self.crew["oracles"].get("receipt_check")
        if not command:
            self.fail(
                ", ".join(f"AC{n}" for n in sorted(receipt)),
                "receipt AC but the crew names no oracles.receipt_check",
                at.get(min(receipt)),
            )
            return
        argv = [*shlex.split(command), str(self.plan.resolve())]
        if boundary and persona:
            argv += ["--boundary-acs", ",".join(str(n) for n in boundary)]
            argv += ["--mock-persona", str(persona)]
        self._run_receipt_check(argv)

    def _run_receipt_check(self, argv: list[str]) -> None:
        try:
            done = subprocess.run(
                argv,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=RECEIPT_TIMEOUT,
                check=False,
            )
        except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as exc:
            self.fail("receipt check", f"receipt check not runnable: {type(exc).__name__}: {exc}")
            return
        lines = [line for line in done.stdout.splitlines() if line.strip()]
        reasons = 0
        for line in lines:
            if line.startswith("warning:"):
                self.warnings.append(line)
            else:
                self.failures.append(line)
                reasons += 1
        if done.returncode != 0 and not reasons:
            self.fail(
                "receipt check",
                f"receipt check failed without a reason (exit {done.returncode})",
            )
        if done.returncode != 0 and self._behind():
            # the check reads the files the plan names from this tree: one behind the ref misses
            # a receipt that landed there, and the refusal alone does not say so
            self.fail(
                "receipt check",
                f"this checkout is behind {self._ref()}: a file the plan names may be there only;"
                f" run from a tree at {self._ref()}",
            )

    def _behind(self) -> bool:
        """``risk.rules_from`` holds a commit this checkout's HEAD lacks; False when unreadable."""
        try:
            done = subprocess.run(
                ["git", "-C", str(self.root), "merge-base", "--is-ancestor", self._ref(), "HEAD"],
                capture_output=True,
                timeout=RECEIPT_TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return done.returncode == 1

    def _epic_plan(self, key: str | None) -> tuple[Path, str] | None:
        if not key:
            self.warnings.append(
                f"warning: {self.plan}: fence and goal checks off: no `epic:` frontmatter; add it "
                "to the story plan to arm the checks"
            )
            return None
        hits = self._epic_plans_on_ref(key) or find_epic_plan(self.plan.parent, key)
        if not hits:
            self.warnings.append(
                f"warning: {self.plan}: fence and goal checks off: no *-epic.md next to the plan "
                f"names `{key}`; add the epic plan to arm the checks"
            )
            return None
        if len(hits) > 1:
            names = " and ".join(p.name for p, _ in hits)
            self.fail(
                "epic",
                f"`{key}` is named by more than one epic plan: {names}",
                frontmatter_line(self.text, "epic"),
            )
            return None
        return hits[0]

    def _epic_plans_on_ref(self, key: str) -> list[tuple[Path, str]]:
        """The epic plans naming ``key`` as committed on ``risk.rules_from``, at their tree paths;
        [] when the ref is unreadable or holds none (a new epic lands with its stories). A
        checkout behind a fence extension otherwise reports a scope change the ref no longer
        has; the story plan itself stays the tree's, since the refiner gates it before it lands."""
        try:
            rel = self.plan.parent.resolve().relative_to(self.root.resolve()).as_posix()
            done = subprocess.run(
                ["git", "-C", str(self.root), "ls-tree", "--name-only", f"{self._ref()}:{rel}"],
                capture_output=True,
                text=True,
                timeout=RECEIPT_TIMEOUT,
                check=False,
            )
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return []
        if done.returncode != 0:
            return []
        hits = []
        for name in sorted(n for n in done.stdout.splitlines() if n.endswith("-epic.md")):
            text = self._on_ref(f"{rel}/{name}")
            if text is not None:
                text = text.replace("\r\n", "\n")
                if names_epic(frontmatter(text), key):
                    hits.append((self.plan.parent / name, text))
        return hits

    def _phase_repos(self, found: list[Phase]) -> None:
        for phase in found:
            for path, other in phase.paths:
                if other and phase.repo is None:
                    self.fail(
                        phase.label,
                        f"`{path}` is marked (other repo): name the repo in a `**Repo:**` line",
                        path_line(self.text, phase.number, path),
                    )

    def _fence(self, epic: tuple[Path, str], key: str, found: list[Phase]) -> None:
        self._phase_repos(found)
        path, text = epic
        meta = frontmatter(text)
        if "fence" not in meta:
            self.warnings.append(_fence_off(self.plan, path))
            return
        own, other = [], {}
        for glob in inline_list(meta["fence"]):
            repo, sep, rest = glob.partition(":")
            if sep and "/" not in repo and "*" not in repo:
                other.setdefault(repo, []).append(rest)
            else:
                own.append(glob)
        product = crew.holder_name(self.crew, "product") or "product"
        human = str(self.crew.get("human", {}).get("name") or "the human")
        for phase in found:
            for file, marked in phase.paths:
                if marked and phase.repo is None:
                    continue
                globs = own if phase.repo is None else other.get(phase.repo, [])
                if matches(file, globs):
                    continue
                shown = file if phase.repo is None else f"{phase.repo}:{file}"
                self.fail(
                    "scope change",
                    f"{shown} ({phase.label}) outside the fence of {key} — approver: "
                    f"{product} (fence change); {human} if it changes the outcome (§Units)",
                    path_line(self.text, phase.number, file),
                )

    def _goals(self, epic: tuple[Path, str]) -> None:
        bound = self.crew["files"].get("goals")
        if not bound:
            self.warnings.append(GOAL_OFF)
            return
        goal_path = self.root / bound
        try:
            goal_text = goal_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        except OSError as exc:
            self.failures.append(f"crew: files.goals {bound!r} unreadable ({type(exc).__name__})")
            return
        key_re = re.compile(rf"\b(?:{self.crew['naming'].get('key') or '[A-Z]+-[0-9]+'})\b")
        metrics = []
        for number, line in enumerate(goal_text.split("\n"), 1):
            place = f"{goal_path}:{number}"
            plans = [
                t
                for t in _LINK.findall(line)
                if t.split("#")[0].endswith(("-epic.md", "-story.md"))
            ]
            metric = _METRIC.match(line)
            # On a metric line only the name part can name work; its definition may hold UTF-8.
            named = re.split(r"\s+—\s+", metric.group(1))[0] if metric else line
            key = key_re.search(" ".join([named, *_LINK.findall(line)]))
            if plans:
                self.failures.append(f"{place}: goal file links the plan {plans[0]}")
            elif key:
                self.failures.append(f"{place}: goal file names the ticket key {key.group(0)}")
            if metric:
                metrics.append(_norm(re.split(r"\s+—\s+", metric.group(1))[0]))
        epic_path, epic_text = epic
        serves = frontmatter(epic_text).get("serves")
        if not serves:
            self.warnings.append(
                f"warning: {epic_path}: serves check off: no serves: frontmatter; add it to the "
                "epic plan to arm the check"
            )
            return
        for part in (p.strip() for p in serves.split(";")):
            if part and not any(_starts_with_metric(_norm(part), m) for m in metrics):
                self.failures.append(
                    f"{epic_path}: serves: `{part}` names no metric of the goal file {bound}"
                )


def heading_line(text: str, name: str) -> int | None:
    """The 1-based line of the level-2 heading ``name`` outside a code fence."""
    fenced = False
    for number, line in enumerate(text.split("\n"), 1):
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("## ") and line[3:].strip() == name:
            return number
    return None


def frontmatter_line(text: str, key: str) -> int | None:
    """The 1-based line of the frontmatter key ``key``."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    for number, line in enumerate(lines[1:], 2):
        if line.strip() == "---":
            return None
        if line.partition(":")[0].strip() == key and not line.startswith((" ", "\t")):
            return number
    return None


def ac_lines(text: str) -> dict[int, int]:
    """AC number -> the 1-based line its item starts on (``acceptance_criteria``'s items)."""
    out: dict[int, int] = {}
    in_section = False
    for number, line in enumerate(text.split("\n"), 1):
        if line.startswith("#"):
            if in_section:
                break
            in_section = line.strip() == "## Acceptance Criteria"
            continue
        start = _AC_ITEM.match(line) if in_section else None
        if start:
            out.setdefault(int(start.group(1)), number)
    return out


def path_line(text: str, phase: int, path: str) -> int | None:
    """The 1-based line under ``### Phase <phase>`` (0: the short form's ``## Files``) whose
    backtick span names ``path``."""
    inside = False
    for number, line in enumerate(text.split("\n"), 1):
        heading = _PHASE.match(line)
        if heading or line.startswith(("## ", "### ")):
            if phase == 0:
                inside = line.strip() == "## Files"
            else:
                inside = bool(heading) and int(heading.group(1)) == phase
        elif inside and any(
            _LINE_SUFFIX.sub("", span.split("§")[0]).rstrip("/") == path
            for span in _SPAN.findall(line)
        ):
            return number
    return None


def risk_globs(rules: str) -> list[tuple[str, re.Pattern[str]]]:
    """Every ``path <glob>`` rule of a risk-paths file, whatever its section: each section is a
    risk class. Other keywords (a classifier's ``line``, ``hunk``, ``from`` rules) judge a diff, not
    a file name, and are skipped."""
    out = []
    for raw in rules.splitlines():
        keyword, _, rest = raw.strip().partition(" ")
        if keyword == "path" and rest.strip():
            glob = rest.strip()
            out += [(glob, risk_paths._glob_regex(one)) for one in risk_paths._expand(glob)]
    return out


def line_keys(meta: dict[str, str]) -> list[str] | None:
    """The finish line's story keys, None when the epic plan has no ``line:`` yet."""
    if "line" not in meta:
        return None
    return inline_list(meta["line"])


def extensions(text: str) -> list[tuple[bool, str]]:
    """(open, entry) of each ``- [ ]``/``- [x]`` item under ``## Extensions``: open is unchecked."""
    body = sections(text).get(EXTENSIONS, "")
    out = []
    for line in body.split("\n"):
        match = EXTENSION_ITEM.match(line)
        if match:
            out.append((match.group(1) == " ", match.group(2).strip()))
    return out


def names_epic(meta: dict[str, str], key: str) -> bool:
    """An epic plan's frontmatter names ``key``: its ``ticket:``, ``epic:`` or ``linked_epics:``."""
    return key in (meta.get("ticket"), meta.get("epic")) or key in inline_list(
        meta.get("linked_epics")
    )


def find_epic_plan(plans_dir: Path, key: str) -> list[tuple[Path, str]]:
    """Every ``*-epic.md`` in ``plans_dir`` whose ``ticket:`` or ``epic:`` is ``key`` or whose
    ``linked_epics:`` holds it, with its text; the one finder for the gate and ``board.py move``."""
    hits = []
    for candidate in sorted(plans_dir.glob("*-epic.md")):
        try:
            text = candidate.read_text(encoding="utf-8").replace("\r\n", "\n")
        except OSError:
            continue
        if names_epic(frontmatter(text), key):
            hits.append((candidate, text))
    return hits


def _fence_off(plan: Path, epic: Path) -> str:
    return (
        f"warning: {plan}: fence check off: {epic} has no fence: frontmatter; add it to the "
        "epic plan to arm the check"
    )


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def _starts_with_metric(part: str, metric: str) -> bool:
    if not metric or not part.startswith(metric):
        return False
    rest = part[len(metric) :]
    return rest == "" or rest[0] in " ("


def _names_a_term(text: str, terms: list[str]) -> bool:
    return any(
        re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", text, re.I) for term in terms if term
    )


# --- entry ---------------------------------------------------------------------------------


def _crew_for(plan: Path) -> tuple[dict[str, Any], Path]:
    path, data = crew.find_and_load(plan.resolve().parent)
    if path is None or data is None:
        base = dict(crew.DEFAULTS)
        base.update({"roles": {}, "members": {}})
        return base, plan.resolve().parent
    return data, path.parent.parent


def story_failures(plan: Path, text: str | None = None) -> tuple[list[str], list[str]]:
    """(failures, warnings) of checks 1-9 on a story plan, as the CLI prints them; the tier is the
    caller's. ``text`` is the plan's content when it does not come from ``plan`` (``board.py
    select`` passes the blob on main). ``OSError`` on the plan propagates; a ``CrewError`` is one
    failure."""
    if text is None:
        text = plan.read_text(encoding="utf-8")
    text = text.replace("\r\n", "\n")
    try:
        crew_data, root = _crew_for(plan)
    except crew.CrewError as exc:
        return [f"crew: {exc}"], []
    gate = Gate(plan, crew_data, root)
    gate.story(text)
    return gate.failures, gate.warnings


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("story", "epic"):
        print(USAGE, file=sys.stderr)
        return 0 if argv[:1] in (["-h"], ["--help"]) else 2
    mode, plan = argv[0], Path(argv[1])
    try:
        text = plan.read_text(encoding="utf-8").replace("\r\n", "\n")
    except OSError as exc:
        print(f"{plan}: unreadable ({type(exc).__name__})", file=sys.stderr)
        return 2
    try:
        crew_data, root = _crew_for(plan)
    except crew.CrewError as exc:
        print(f"crew: {exc}")
        return 1
    gate = Gate(plan, crew_data, root)
    getattr(gate, mode)(text)
    if mode == "story":
        gate.tier(text)
    for line in gate.warnings:
        print(line, file=sys.stderr)
    for line in gate.failures:
        print(line)
    return 1 if gate.failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
