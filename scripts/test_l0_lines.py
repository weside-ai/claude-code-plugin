"""Pins every skill and reference line that once contradicted the crew process L0
(we/process/L0.md): one case per finding row of the cut, `(row, file, forbidden, required)`.

A row fails when its file still holds the forbidden phrase or lacks the required one. Text is
compared with its whitespace collapsed, so a re-wrapped line keeps its case. Rows whose file was
deleted are pinned by check 10 of validate-consistency.py; the ones whose content survives
elsewhere get a case on the successor here (rows marked "successor").

Red arm: `L0_LINES_REF=<ref> python3 -m pytest -q scripts/test_l0_lines.py` reads every file
from that git ref instead (the renamed master skill from its old path), so on the ref before the
cut every case fails with its row id in the message.

Run with: python3 -m pytest -q scripts/test_l0_lines.py
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
REF = os.environ.get("L0_LINES_REF", "")
# a file's path on a ref older than the rename
OLD_PATHS = {
    "we/skills/master/SKILL.md": "we/skills/orchestrate/SKILL.md",
    "we/skills/plan-story/SKILL.md": "we/skills/refine/SKILL.md",
}

MASTER = "we/skills/master/SKILL.md"
EPIC = "we/skills/epic/SKILL.md"
PR = "we/skills/pr/SKILL.md"
MERGED = "we/skills/merged/SKILL.md"
DEVELOP = "we/skills/develop/SKILL.md"
CI_REVIEW = "we/skills/ci-review/SKILL.md"
STANDUP = "we/skills/standup/SKILL.md"
COUNCIL = "we/skills/council/SKILL.md"
SETUP = "we/skills/setup/SKILL.md"
OPTIMIZE = "we/skills/optimize/SKILL.md"
DISPATCH = "we/references/worker-dispatch.md"
CONTEXT = "we/references/context-engineering.md"
STORY_PLAN = "we/references/story-plan.md"
PLAN_COMMIT = "we/references/plan-commit.md"
TICKETING = "we/references/ticketing.md"
TEMPLATE = "we/skills/epic/references/template.md"
PLAN_STORY = "we/skills/plan-story/SKILL.md"


def _git(*args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False
    )
    return done.stdout if done.returncode == 0 else ""


def read(rel: str) -> str:
    """The file's text, whitespace collapsed; from ``L0_LINES_REF`` when set."""
    if REF:
        text = _git("show", f"{REF}:{rel}") or _git("show", f"{REF}:{OLD_PATHS.get(rel, rel)}")
    else:
        path = REPO / rel
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    assert text, f"{rel} not found{' on ' + REF if REF else ''}"
    return " ".join(text.split())


def description(rel: str) -> str:
    text = read(rel)
    found = re.search(r"description: >? ?(.*?) --- ", text)
    assert found, f"{rel}: no description"
    return found.group(1)


def instruction_files() -> list[str]:
    """Every skill and reference under we/ (the skill-local references included)."""
    if REF:
        names = _git("ls-tree", "-r", "--name-only", REF, "we/skills", "we/references").split()
    else:
        names = [
            p.relative_to(REPO).as_posix()
            for p in (REPO / "we").glob("**/*.md")
            if p.parts[len(REPO.parts) + 1] in ("skills", "references")
        ]
    return sorted(n for n in names if n.endswith(".md"))


# (row, file, forbidden regex or None, required regex or None); "desc:" reads the description
CASES = [
    ("F01", "desc:" + MASTER, r"runs CI once on one PR", r"one PR per story"),
    ("F02", MASTER, r"serially onto one PR", r"each its own PR"),
    ("F03", "desc:" + EPIC, r"Initiative altitude", r"one outcome serving a goal-file metric"),
    ("F04", EPIC, r"serves a Saga", r"carries `serves: <metric>` of the goal file"),
    ("F05", EPIC, r"/we:saga promote", r"linked epics"),
    ("F06", "desc:" + PR, r"ticket to In Review", r"PR linked to the ticket"),
    ("F07", PR, r"move it to In Review", r"link the PR to it and move no status"),
    ("F08", "desc:" + MERGED, r"Done or In Review", r"In Review once its PR is linked"),
    ("F09", MERGED, r"after_merge|\"done\"", r"The target is In Review, never Done"),
    ("F14", MASTER, r"dispatch one implementer", r"never through a build subagent"),
    ("F15", MASTER, r"--solo", None),
    ("F16", MASTER, r"waiting for approval|approval batch", r"approval is per epic"),
    ("F17", MASTER, r"Decision.Queue", r"becomes one decision story"),
    (
        "F18",
        MASTER,
        r"No ticket during a run, and no question whether to create one",
        r"A product question mid-run becomes one decision story",
    ),
    (
        "F19",
        MASTER,
        r"Move every landed story to In Review",
        r"In Review is \"PR merged and linked\"",
    ),
    ("F20", MASTER, r"plan-approved status", r"`ticketing.md`, which names the mover"),
    ("F21", MASTER, r"move the ticket to In Progress", r"Selected → In Progress per"),
    (
        "F22",
        MASTER,
        r"--user-merge|a question to the human is open",
        r"\*\*Who merges what\*\* \(the one table",
    ),
    ("F23", MASTER, r"AskUserQuestion", r"one question line to the coordinator"),
    ("F24", EPIC, r"<saga>-saga\.md|saga: null", r"`serves: null`"),
    (
        "F25",
        EPIC,
        r"each plan from `/we:story`",
        r"refiner worker the epic's master starts \(`/we:plan-story`\), never from the epic owner",
    ),
    ("F26", EPIC, r"serially onto one PR", r"each Story as its own PR"),
    ("F30", DEVELOP, r"(?i)invoked by a human outside a worktree", r"names a story key"),
    ("F31", DEVELOP, r"(?i)invoked by a human", None),
    ("F32", CI_REVIEW, r"Run as a subagent, you report", r"never as a subagent"),
    ("F33", STANDUP, r"active sagas", r"`serves:` metric"),
    ("F34", STANDUP, r"<Saga> \u203a", r"\(serves <metric>\)"),
    ("F35", COUNCIL, r"--meeting=", None),
    ("F36", SETUP, r"`\"subagent\"` or a command template", r"A repo with a crew gets one"),
    ("F37", SETUP, r"after_merge", r"never to Done"),
    ("F38", SETUP, r"\*\*Vision\*\*|/we:vision|PRD", r"\*\*Goals\*\*"),
    ("F39", SETUP, r"\"meetings\"|\"saga\"", None),
    ("F40", OPTIMIZE, r"evidence and the user's approval", r"the HR role, which decides weekly"),
    ("F41", OPTIMIZE, r"AskUserQuestion", r"one question line"),
    (
        "F50",
        DISPATCH,
        r"the default is `Agent\(",
        r"A repo with a crew starts every `we:dev-\*` worker through the template `worker_launch.py backend` prints",
    ),
    (
        "F51",
        DISPATCH,
        r"`\"subagent\"` \(the default, also when unset\)",
        r"only in a repo without a crew",
    ),
    ("F54", CONTEXT, r"the crew's orchestrator writes them", r"the HR role owns them"),
    ("F55", STORY_PLAN, r"`draft` until the user approved", r"Approval is per epic"),
    ("F56", "desc:" + PLAN_COMMIT, r"\bsaga\b|\bPRD\b", None),
    ("F57", PLAN_COMMIT, r"/we:(vision|saga|story)\b", None),
    (
        "F58",
        TICKETING,
        r"Only `/we:merged` moves a ticket",
        r"a move goes through `board.py select` or `board.py move`",
    ),
    # successor cases for deleted rows whose content survives elsewhere
    ("F27/F42/F43 successor", STORY_PLAN, r"until the user approved", r"never per story"),
    ("F28/F44 successor", MASTER, r"plans to the epic owner", r"the owner judges, never starts"),
    (
        "F45 successor",
        TICKETING,
        r"by push",
        r"the master moves Selected → In Progress when it pulls",
    ),
    ("F47 successor", DISPATCH, None, r"a subagent reads and reviews, never builds"),
    (
        "F48/F49 successor",
        MERGED,
        r"Done is legitimate here",
        r"Done comes only from a receipt report",
    ),
    ("F24 successor", TEMPLATE, r"^.*saga:|Saga", r"serves: <metric of the goal file>"),
    # review rows of the cut (R*): a contract field or file the cut left without a writer or reader
    (
        "R1 approved has a writer",
        MASTER,
        r"Pass → commit it\.",
        r"Pass → set `status: approved` in the plan's frontmatter, then commit it",
    ),
    (
        "R1 who sets approved",
        STORY_PLAN,
        None,
        r"the master sets it in the commit that puts the plan on the default branch",
    ),
    ("R1 the refiner writes draft", PLAN_STORY, r"status: approved", r"`status: draft`"),
    ("R2 goals bound in the crew", SETUP, r"Skip → no goal check", r"bind `files\.goals`"),
    ("R2 no crew, no goal check", SETUP, None, r"the goal check needs a crew"),
    # watch rows: the PR watcher rule has one owner, L0 §Sessions
    (
        "W1 pr watch follows the L0",
        PR,
        r"Whoever opens a PR watches it until the merge",
        r"The watch follows L0 §Sessions",
    ),
    (
        "W2 master arms after the worker's green",
        MASTER,
        r"the worker owns the watch and you arm none",
        r"watches until green \(L0 §Sessions\), then you arm it `--until-merged`",
    ),
]


def _check(row: str, target: str, forbidden: str | None, required: str | None) -> list[str]:
    rel = target.removeprefix("desc:")
    text = description(rel) if target.startswith("desc:") else read(rel)
    problems = []
    if forbidden and re.search(forbidden, text):
        hit = re.search(forbidden, text).group(0)
        problems.append(f"{row} {rel}: still says {hit!r} (contradicts the L0)")
    if required and not re.search(required, text):
        problems.append(f"{row} {rel}: lacks the L0 line /{required}/")
    return problems


@pytest.mark.parametrize(
    ("row", "target", "forbidden", "required"), CASES, ids=[c[0] for c in CASES]
)
def test_l0_line(row, target, forbidden, required):
    problems = _check(row, target, forbidden, required)
    assert not problems, "\n".join(problems)


LEVELS = re.compile(r"\b[Ss]agas?\b|\b[Aa]ltitudes?\b|\bPRD\b|/we:(?:saga|vision|meet)\b")


def test_no_skill_or_reference_names_a_saga_vision_or_altitude():
    """Rows F10, F12, F13, F52, F53 (deleted files) on their successors: no skill or reference,
    description or body, names a level above the epic other than the goal file (L0 §Units)."""
    hits = [
        f"F10/F12/F13/F52/F53 {rel}: names {m.group(0)!r} as a level of work"
        for rel in instruction_files()
        for m in [LEVELS.search(read(rel))]
        if m
    ]
    assert not hits, "\n".join(hits)


def test_no_instruction_file_names_the_after_merge_key():
    """Rows F09, F37, F48, F49: Done is never the merge's target, so the key that chose it is gone."""
    hits = [rel for rel in instruction_files() if "after_merge" in read(rel)]
    assert not hits, f"F09/F37/F48/F49 ticketing.after_merge still named in: {hits}"


def test_every_finding_row_is_covered():
    """58 rows: the cases here plus the rows resolved by deleting their file (check 10)."""
    deleted_only = {"F11", "F46"}
    by_successor = {"F10", "F12", "F13", "F29", "F52", "F53"}
    covered = {r for c in CASES for r in re.findall(r"F\d\d", c[0])} | deleted_only | by_successor
    assert covered == {f"F{n:02d}" for n in range(1, 59)}
