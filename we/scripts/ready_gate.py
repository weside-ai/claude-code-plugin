#!/usr/bin/env python3
"""The Ready gate: is a story plan (or an epic plan) ready for Selected?

Usage:
  ready_gate.py story <plan>        a story plan and, through its ``epic:``, the epic's fence,
                                    ``serves:`` and the goal file
  ready_gate.py epic <epic plan>    ``serves:``, the goal file and the presence of ``fence:``

Exit 0 ready, 1 refused (one stdout line per failure, ``<plan>: <place>: <what is missing>``),
2 usage or an unreadable plan. Warnings go to stderr, each prefixed ``warning:``, and never
change the exit. There is no option: no caller can switch a check off.

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
   (``hooks/verification_gate.py``): a line that hook would refuse is one warning now, not a
   refusal at ``gh pr create`` later (the AC classes ``receipt``/``ci``/``walk`` are no oracle
   there);
10. the plan's tier (``plan_tier.py``): the repo's ``risk.command`` on the plan alone, in a
    scratch tree at ``risk.rules_from``. A success prints ``tier: <line 1>`` on stderr, a
    failure is one stdout line ``<plan>: tier: tier not computed: <reason>``; without a
    ``risk.command`` one warning. The epic mode computes no tier.

``story_failures(plan)`` runs checks 1-9 for ``board.py select``, which runs the tier itself.

Every repo value comes from the crew through ``crew.py``; a ``CrewError`` is a refusal. Python
3.9, stdlib only.
"""

from __future__ import annotations

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

_HOOKS = str(Path(__file__).resolve().parent.parent / "hooks")
if _HOOKS not in sys.path:
    sys.path.append(_HOOKS)
import verification_gate  # noqa: E402

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
    def __init__(self, number: int) -> None:
        self.number = number
        self.repo: str | None = None
        self.paths: list[tuple[str, bool]] = []  # (path, marked "(other repo)")


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
    reads): no whitespace, and a ``/``, a leading ``.``, or an extension on a bullet's first span."""
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

    def fail(self, place: str, message: str) -> None:
        self.failures.append(f"{self.plan}: {place}: {message}")

    def story(self, text: str) -> None:
        meta = frontmatter(text)
        if not meta.get("story"):
            self.fail("frontmatter", "no `story:`")
        present = sections(text)
        for name in REQUIRED_SECTIONS:
            if name not in present:
                self.fail(f"## {name}", "section missing")
        if "Open Fork" in present:
            self.fail("## Open Fork", "an open fork stands; answer it and delete the section")
        found_phases = phases(text)
        markers = self._acs(text)
        self._walk(markers, found_phases)
        self._receipts(markers)
        epic = self._epic_plan(meta.get("epic"))
        if epic is not None:
            self._fence(epic, meta["epic"], found_phases)
            self._goals(epic)
        else:
            self._phase_repos(found_phases)
        if "Implementation Phases" in present and not any(ph.paths for ph in found_phases):
            self.fail("Implementation Phases", "no seams named (no path in any Files list)")
        if "Verification" in present:
            self._oracle_line(text)

    def _oracle_line(self, text: str) -> None:
        """Check 9b: warn now what the PR hook refuses at `gh pr create`."""
        problem = verification_gate._receipt_problem(text)
        if problem is not None:
            self.warnings.append(
                f"warning: {self.plan}: ## Verification: the PR hook will refuse this plan's "
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
        if result.failure is not None:
            self.fail("tier", f"tier not computed: {result.failure}")
        else:
            self.warnings.append(f"tier: {result.line}")

    def epic(self, text: str) -> None:
        if "fence" not in frontmatter(text):
            self.warnings.append(_fence_off(self.plan, self.plan))
        self._goals((self.plan, text))

    def _acs(self, text: str) -> dict[int, tuple[Marker, str]]:
        markers: dict[int, tuple[Marker, str]] = {}
        acs = acceptance_criteria(text)
        if not acs and "Acceptance Criteria" in sections(text):
            self.fail("## Acceptance Criteria", "no numbered AC")
        for n, ac in acs:
            missing = [w for w in ("Given", "When", "Then") if f"**{w}**" not in ac]
            if missing:
                self.fail(f"AC{n}", "no " + ", ".join(f"`**{w}**`" for w in missing))
            body = marker_body(ac)
            if body is None:
                self.fail(f"AC{n}", "no oracle-class marker `[receipt]`, `[ci: …]` or `[walk: …]`")
                continue
            marker, problem = parse_marker(body)
            if marker is None:
                self.fail(f"AC{n}", problem or "marker does not parse")
                continue
            markers[n] = (marker, ac)
        return markers

    def _walk(self, markers: dict[int, tuple[Marker, str]], found: list[Phase]) -> None:
        walk_paths = list(self.crew["oracles"].get("walk_paths") or [])
        own = [p for ph in found if ph.repo is None for p, _ in ph.paths]
        on_path = any(matches(p, walk_paths) for p in own)
        for n, (marker, _) in sorted(markers.items()):
            if "walk" in marker.classes() and not walk_why(marker) and not on_path:
                self.fail(
                    f"AC{n}",
                    "`walk` on a change whose **Files:** touch no walk path "
                    "(crew oracles.walk_paths); add `why: <sentence>` to the marker",
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
        if boundary and not persona:
            listed = ", ".join(f"AC{n}" for n in boundary)
            self.fail(
                listed,
                "server-boundary receipt AC but the crew names no acceptance.mock_persona",
            )
        command = self.crew["oracles"].get("receipt_check")
        if not command:
            self.fail(
                ", ".join(f"AC{n}" for n in sorted(receipt)),
                "receipt AC but the crew names no oracles.receipt_check",
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

    def _epic_plan(self, key: str | None) -> tuple[Path, str] | None:
        if not key:
            self.warnings.append(
                f"warning: {self.plan}: fence and goal checks off: no `epic:` frontmatter; add it "
                "to the story plan to arm the checks"
            )
            return None
        hits = find_epic_plan(self.plan.parent, key)
        if not hits:
            self.warnings.append(
                f"warning: {self.plan}: fence and goal checks off: no *-epic.md next to the plan "
                f"names `{key}`; add the epic plan to arm the checks"
            )
            return None
        if len(hits) > 1:
            names = " and ".join(p.name for p, _ in hits)
            self.fail("epic", f"`{key}` is named by more than one epic plan: {names}")
            return None
        return hits[0]

    def _phase_repos(self, found: list[Phase]) -> None:
        for phase in found:
            for path, other in phase.paths:
                if other and phase.repo is None:
                    self.fail(
                        f"phase {phase.number}",
                        f"`{path}` is marked (other repo): name the repo in a `**Repo:**` line",
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
                self.failures.append(
                    f"{self.plan}: scope change: {shown} (phase {phase.number}) outside the "
                    f"fence of {key} — approver: {product} (fence change); {human} if it "
                    "changes the outcome (§Units)"
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


def find_epic_plan(plans_dir: Path, key: str) -> list[tuple[Path, str]]:
    """Every ``*-epic.md`` in ``plans_dir`` whose ``ticket:`` or ``epic:`` is ``key`` or whose
    ``linked_epics:`` holds it, with its text; the one finder for the gate and ``board.py move``."""
    hits = []
    for candidate in sorted(plans_dir.glob("*-epic.md")):
        try:
            text = candidate.read_text(encoding="utf-8").replace("\r\n", "\n")
        except OSError:
            continue
        meta = frontmatter(text)
        if key in (meta.get("ticket"), meta.get("epic")) or key in inline_list(
            meta.get("linked_epics")
        ):
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


def story_failures(plan: Path) -> tuple[list[str], list[str]]:
    """(failures, warnings) of checks 1-9 on a story plan, as the CLI prints them; the tier is the
    caller's. ``OSError`` on the plan propagates; a ``CrewError`` is one failure."""
    text = plan.read_text(encoding="utf-8").replace("\r\n", "\n")
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
