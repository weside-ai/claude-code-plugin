"""ready_gate.py: the eight-fixture table, the marker grammar, the receipt-check hand-over, the
fence (warn until present, arms without a flag) and the goal file."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import ready_gate

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "ready_gate.py"
FIXTURES = HERE / "fixtures" / "ready_gate"
MARKERS = HERE / "fixtures" / "oracle_markers.txt"
PLANS = "docs/plans"


def repo(tmp_path: Path, crew_file: str = "crew-plain.json", **changes: object) -> Path:
    """A repo with the fixture crew (``changes`` as dotted keys), plans, goal files and the fake
    receipt check."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / ".weside").mkdir()
    shutil.copytree(FIXTURES / "plans", root / PLANS)
    for name in ("goals.md", "goals-bad.md", "fake_receipt_check.py"):
        shutil.copy(FIXTURES / name, root / name)
    data = json.loads((FIXTURES / crew_file).read_text())
    data["oracles"]["receipt_check"] = f"{shlex.quote(sys.executable)} fake_receipt_check.py"
    for dotted, value in changes.items():
        node = data
        *parents, leaf = dotted.split("__")
        for part in parents:
            node = node.setdefault(part, {})
        if value is None:
            node.pop(leaf, None)
        else:
            node[leaf] = value
    (root / ".weside" / "crew.json").write_text(json.dumps(data))
    return root


def gate(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def plan(root: Path, name: str) -> str:
    return f"{PLANS}/{name}.md"


def argv_log(root: Path) -> list[list[str]]:
    log = root / "argv.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


# --- AC1: the eight-fixture table ---------------------------------------------------------

TABLE = [
    ("green", []),
    ("walk-why", []),
    ("no-verification", ["## Verification: section missing"]),
    ("no-then", ["AC2: no `**Then**`"]),
    ("no-marker", ["AC2: no oracle-class marker"]),
    ("receipt-missing", ["AC1 is a receipt AC, receipts/PROJ-12.yaml does not exist"]),
    ("walk-no-why", ["AC3: `walk` on a change whose **Files:** touch no walk path"]),
    (
        "five-failures",
        [
            "## Verification: section missing",
            "AC2: no `**Then**`",
            "AC4: no oracle-class marker",
            "AC3: `walk` on a change whose **Files:** touch no walk path",
            "AC1 is a receipt AC, receipts/PROJ-12.yaml does not exist",
        ],
    ),
]


@pytest.mark.parametrize(("name", "expected"), TABLE, ids=[row[0] for row in TABLE])
def test_the_eight_fixture_plans(tmp_path, name, expected):
    root = repo(tmp_path)
    out = gate(root, "story", plan(root, name))
    lines = out.stdout.splitlines()
    assert out.returncode == (1 if expected else 0), out.stdout + out.stderr
    assert len(lines) == len(expected), lines
    for want in expected:
        hits = [line for line in lines if want in line]
        assert len(hits) == 1, (want, lines)
        assert name in hits[0], "each line names the plan"
    assert "fence check off" not in out.stderr  # PROJ-1 carries a fence


def test_an_open_fork_fails(tmp_path):
    root = repo(tmp_path)
    path = root / plan(root, "green")
    text = path.read_text().replace("## Acceptance", "## Open Fork\n\nA or B?\n\n## Acceptance")
    path.write_text(text)
    out = gate(root, "story", str(path))
    assert out.returncode == 1
    assert out.stdout.splitlines() == [
        f"{path}: ## Open Fork: an open fork stands; answer it and delete the section"
    ]


def test_a_standalone_story_warns_and_still_checks_repos(tmp_path):
    root = repo(tmp_path, "crew-goals.json")
    path = root / plan(root, "green")
    path.write_text(path.read_text().replace("epic: PROJ-1\n", ""))
    out = gate(root, "story", str(path))
    assert out.returncode == 0 and out.stdout == ""
    assert out.stderr.splitlines() == [
        f"warning: {path}: fence and goal checks off: no `epic:` frontmatter; add it to the story "
        "plan to arm the checks"
    ]
    add_file(root, "green", "  - `lib/x.py` (other repo)", phase="### Phase 1")
    out = gate(root, "story", str(path))
    assert out.returncode == 1
    assert out.stdout.splitlines() == [
        f"{path}: phase 1: `lib/x.py` is marked (other repo): name the repo in a `**Repo:**` line"
    ]


def test_an_unknown_class_fails(tmp_path):
    root = repo(tmp_path)
    path = root / plan(root, "green")
    path.write_text(path.read_text().replace("and a header [receipt]", "and a header [manual]"))
    out = gate(root, "story", str(path))
    assert out.returncode == 1
    assert out.stdout.splitlines() == [
        f"{path}: AC1: unknown oracle class `manual` (receipt, ci or walk)"
    ]


def test_crlf_plans_parse(tmp_path):
    root = repo(tmp_path)
    path = root / plan(root, "green")
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    out = gate(root, "story", str(path))
    assert out.returncode == 0, out.stdout


def test_receipt_check_unset_fails_closed(tmp_path):
    root = repo(tmp_path, oracles__receipt_check=None)
    out = gate(root, "story", plan(root, "green"))
    assert out.returncode == 1
    assert out.stdout.splitlines() == [
        f"{plan(root, 'green')}: AC1: receipt AC but the crew names no oracles.receipt_check"
    ]


def test_a_receipt_check_warning_goes_to_stderr_and_keeps_exit_0(tmp_path):
    root = repo(tmp_path)
    (root / PLANS / "green.out").write_text("warning: receipts/PROJ-12.yaml: env: dev without …\n")
    out = gate(root, "story", plan(root, "green"))
    assert out.returncode == 0 and out.stdout == ""
    assert "warning: receipts/PROJ-12.yaml: env: dev without …" in out.stderr.splitlines()


def test_a_receipt_check_failing_without_a_line_is_one_failure(tmp_path):
    root = repo(tmp_path)
    (root / "fake_receipt_check.py").write_text("import sys\nsys.exit(1)\n")
    out = gate(root, "story", plan(root, "green"))
    assert out.returncode == 1
    assert out.stdout.splitlines() == [
        f"{plan(root, 'green')}: receipt check: receipt check failed without a reason (exit 1)"
    ]


def test_a_receipt_check_not_on_disk_is_not_runnable(tmp_path):
    root = repo(tmp_path, oracles__receipt_check="no-such-checker-anywhere --flag")
    out = gate(root, "story", plan(root, "green"))
    assert out.returncode == 1
    (line,) = out.stdout.splitlines()
    assert "receipt check: receipt check not runnable: FileNotFoundError" in line


def test_the_receipt_check_gets_the_plan_and_runs_in_the_crew_root(tmp_path):
    root = repo(tmp_path)
    gate(root, "story", plan(root, "green"))
    (argv,) = argv_log(root)
    assert argv == [str((root / plan(root, "green")).resolve())]


def test_no_receipt_ac_runs_no_receipt_check(tmp_path):
    root = repo(tmp_path)
    path = root / plan(root, "green")
    path.write_text(
        path.read_text().replace("and a header [receipt]", "and a header [ci: test_x.py]")
    )
    assert gate(root, "story", str(path)).returncode == 0
    assert argv_log(root) == []


def test_help_lists_only_the_two_modes_and_the_plan():
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, check=False
    )
    assert out.returncode == 0
    assert (
        out.stderr.strip() == "usage: ready_gate.py story <plan> | ready_gate.py epic <epic plan>"
    )
    bad = subprocess.run(
        [sys.executable, str(SCRIPT), "story", "x.md", "--no-fence"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode == 2


def test_an_unreadable_plan_is_a_usage_error(tmp_path):
    root = repo(tmp_path)
    out = gate(root, "story", "docs/plans/missing.md")
    assert out.returncode == 2 and "docs/plans/missing.md: unreadable" in out.stderr


def test_a_crew_error_is_a_refusal(tmp_path):
    root = repo(tmp_path, limits__masters="five")
    out = gate(root, "story", plan(root, "green"))
    assert out.returncode == 1 and out.stdout.startswith("crew: ")


# --- the marker grammar (shared fixture) --------------------------------------------------


def marker_rows() -> list[tuple[str, str]]:
    rows = []
    for line in MARKERS.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            expected, marker = line.split("\t", 1)
            rows.append((expected, marker))
    return rows


@pytest.mark.parametrize(("expected", "marker"), marker_rows())
def test_the_shared_marker_grammar(expected, marker):
    body = ready_gate.marker_body(f"**Given** a **When** b **Then** c {marker}")
    assert body is not None, marker
    parsed, problem = ready_gate.parse_marker(body)
    if expected == "!":
        assert parsed is None and problem, marker
    else:
        assert parsed is not None, (marker, problem)
        assert ",".join(parsed.classes()) == expected


def test_a_marker_quoted_mid_sentence_is_prose():
    assert ready_gate.marker_body("**Then** it says [receipt] in the text") is None
    assert ready_gate.marker_body("**Then** see `[receipt]`") is None


def test_files_extraction_reads_a_real_files_shape():
    text = (FIXTURES / "plans" / "green.md").read_text()
    found = ready_gate.phases(text)
    assert [(p.number, p.repo) for p in found] == [(1, None), (2, "lib-repo")]
    assert found[0].paths == [
        ("src/report/export.py", False),
        ("src/report/base.py", False),
        ("tests/test_export.py", False),
        ("docs/guides/export.md", False),
    ]
    assert found[1].paths == [("lib/csv/parse.py", True)]


@pytest.mark.parametrize(
    ("glob", "path", "hit"),
    [
        ("src/**", "src/a/b/c.py", True),
        ("src/**", "src", True),
        ("src/*.py", "src/a/b.py", False),
        ("src/*.py", "src/b.py", True),
        ("**/x.md", "x.md", True),
        ("a?c.md", "abc.md", True),
        ("app.config.js", "app.config.js", True),
    ],
)
def test_the_glob_matcher(glob, path, hit):
    assert ready_gate.matches(path, [glob]) is hit


# --- AC4 plugin half: boundary hand-over --------------------------------------------------


def boundary_plan(root: Path, marker: str, text: str = "a room member reads the rows") -> str:
    path = root / plan(root, "green")
    path.write_text(
        path.read_text().replace(
            "**Then** the response carries three data lines and a header [receipt]",
            f"**Then** {text} {marker}",
        )
    )
    return str(path)


def test_a_term_match_hands_boundary_acs_and_the_mock_persona(tmp_path):
    root = repo(tmp_path)
    assert gate(root, "story", boundary_plan(root, "[receipt]")).returncode == 0
    (argv,) = argv_log(root)
    assert argv[1:] == ["--boundary-acs", "1", "--mock-persona", "mock-1"]


def test_a_boundary_marker_hands_over_without_a_term(tmp_path):
    root = repo(tmp_path)
    gate(root, "story", boundary_plan(root, "[receipt: boundary]", text="three lines"))
    assert argv_log(root)[0][1:] == ["--boundary-acs", "1", "--mock-persona", "mock-1"]


def test_not_boundary_exempts_a_term_match(tmp_path):
    root = repo(tmp_path)
    gate(root, "story", boundary_plan(root, "[receipt: not-boundary: reads its own rows]"))
    assert argv_log(root)[0][1:] == []


def test_a_boundary_ac_without_a_mock_persona_fails(tmp_path):
    root = repo(tmp_path, acceptance__mock_persona=None)
    path = boundary_plan(root, "[receipt]")
    out = gate(root, "story", path)
    assert out.returncode == 1
    assert out.stdout.splitlines() == [
        f"{path}: AC1: server-boundary receipt AC but the crew names no acceptance.mock_persona"
    ]
    assert argv_log(root)[0][1:] == []


def test_a_receipt_check_boundary_line_passes_through(tmp_path):
    root = repo(tmp_path)
    path = boundary_plan(root, "[receipt]")
    line = "AC1: server-boundary check AC1 runs on standard-1, not the mock-bound owner mock-1"
    (root / PLANS / "green.out").write_text(line + "\n")
    out = gate(root, "story", path)
    assert out.returncode == 1 and out.stdout.splitlines() == [line]


# --- AC2: the fence -----------------------------------------------------------------------

SCOPE = (
    "{plan}: scope change: {path} (phase {n}) outside the fence of PROJ-1 — approver: {who} "
    "(fence change); Hal if it changes the outcome (§Units)"
)


def add_file(root: Path, name: str, line: str, phase: str = "### Phase 2") -> str:
    path = root / plan(root, name)
    text = path.read_text()
    anchor = "  - `docs/guides/export.md`" if phase == "### Phase 1" else "  - `lib/csv/parse.py`"
    path.write_text(text.replace(anchor, f"{line}\n{anchor}", 1))
    return str(path)


def test_a_path_outside_the_fence_is_a_scope_change(tmp_path):
    root = repo(tmp_path)
    path = add_file(root, "green", "  - `infra/main.tf`", phase="### Phase 1")
    out = gate(root, "story", path)
    assert out.returncode == 1
    assert out.stdout.splitlines() == [
        SCOPE.format(plan=path, path="infra/main.tf", n=1, who="Ada")
    ]


def test_another_repos_path_is_judged_against_its_repo_globs(tmp_path):
    root = repo(tmp_path)
    path = add_file(root, "green", "  - `src/other.py`")
    out = gate(root, "story", path)
    assert out.stdout.splitlines() == [
        SCOPE.format(plan=path, path="lib-repo:src/other.py", n=2, who="Ada")
    ]


def test_an_unbound_product_role_names_the_role_key(tmp_path):
    root = repo(tmp_path, roles={})
    path = add_file(root, "green", "  - `infra/main.tf`", phase="### Phase 1")
    out = gate(root, "story", path)
    assert out.stdout.splitlines() == [
        SCOPE.format(plan=path, path="infra/main.tf", n=1, who="product")
    ]


def test_other_repo_without_a_repo_line_fails(tmp_path):
    root = repo(tmp_path)
    path = add_file(root, "green", "  - `lib/x.py` (other repo)", phase="### Phase 1")
    out = gate(root, "story", path)
    assert out.returncode == 1
    assert out.stdout.splitlines() == [
        f"{path}: phase 1: `lib/x.py` is marked (other repo): name the repo in a `**Repo:**` line"
    ]


def use_epic(root: Path, name: str, epic: str) -> str:
    path = root / plan(root, name)
    path.write_text(path.read_text().replace("epic: PROJ-1\n", f"epic: {epic}\n"))
    return str(path)


def test_an_epic_without_fence_warns_and_refuses_nothing(tmp_path):
    root = repo(tmp_path)
    path = add_file(root, "green", "  - `infra/main.tf`", phase="### Phase 1")
    path = use_epic(root, "green", "PROJ-3")  # linked_epics of PROJ-2-epic.md
    out = gate(root, "story", path)
    epic = Path(path).parent / "PROJ-2-epic.md"
    assert out.returncode == 0 and out.stdout == ""
    assert (
        f"warning: {path}: fence check off: {epic} has no fence: frontmatter; add it to the epic "
        "plan to arm the check"
    ) in out.stderr.splitlines()


def test_adding_fence_arms_the_check_without_a_flag(tmp_path):
    root = repo(tmp_path)
    path = add_file(root, "green", "  - `infra/main.tf`", phase="### Phase 1")
    path = use_epic(root, "green", "PROJ-2")
    assert gate(root, "story", path).returncode == 0
    epic = root / PLANS / "PROJ-2-epic.md"
    epic.write_text(
        epic.read_text().replace("status:", "fence: [src/**, tests/**, docs/**]\nstatus:")
    )
    out = gate(root, "story", path)
    assert out.returncode == 1
    assert "fence check off" not in out.stderr
    lines = out.stdout.splitlines()
    assert any(
        "scope change: infra/main.tf (phase 1) outside the fence of PROJ-2" in x for x in lines
    )


def test_an_epic_without_a_plan_warns_and_two_plans_fail(tmp_path):
    root = repo(tmp_path, "crew-goals.json")
    path = use_epic(root, "green", "PROJ-9")
    out = gate(root, "story", path)
    assert out.returncode == 0 and out.stdout == ""
    assert out.stderr.splitlines() == [
        f"warning: {path}: fence and goal checks off: no *-epic.md next to the plan names "
        "`PROJ-9`; add the epic plan to arm the checks"
    ]
    path = add_file(root, "green", "  - `lib/x.py` (other repo)", phase="### Phase 1")
    out = gate(root, "story", path)
    assert out.returncode == 1 and "is marked (other repo)" in out.stdout
    shutil.copy(root / PLANS / "PROJ-1-epic.md", root / PLANS / "PROJ-1b-epic.md")
    out = gate(root, "story", plan(root, "walk-why"))
    assert "is named by more than one epic plan: PROJ-1-epic.md and PROJ-1b-epic.md" in out.stdout


# --- AC3: goal file and serves: -----------------------------------------------------------

GOAL_OFF = (
    "warning: goal check off: crew.json names no files.goals; add the goal file and bind it to "
    "arm the check"
)


def test_goal_check_off_without_files_goals(tmp_path):
    root = repo(tmp_path)
    out = gate(root, "epic", plan(root, "PROJ-1-epic"))
    assert out.returncode == 0 and out.stdout == ""
    assert out.stderr.splitlines() == [GOAL_OFF]


def test_every_serves_part_matches_a_metric(tmp_path):
    root = repo(tmp_path, "crew-goals.json")
    out = gate(root, "epic", plan(root, "PROJ-1-epic"))
    assert out.returncode == 0, out.stdout
    assert out.stderr == ""
    assert gate(root, "story", plan(root, "green")).returncode == 0


def test_an_unknown_serves_part_fails_with_no_flag(tmp_path):
    root = repo(tmp_path, "crew-goals.json")
    out = gate(root, "epic", plan(root, "PROJ-2-epic"))
    epic = root / PLANS / "PROJ-2-epic.md"
    assert out.returncode == 1
    assert out.stdout.splitlines() == [
        f"{epic.relative_to(root)}: serves: `churn of the settings page` names no metric of the goal "
        "file goals.md"
    ]
    assert "fence check off" in out.stderr


def test_a_goal_file_naming_work_fails_by_line(tmp_path):
    root = repo(tmp_path, "crew-goals.json", files__goals="goals-bad.md")
    out = gate(root, "epic", plan(root, "PROJ-1-epic"))
    bad = root / "goals-bad.md"
    assert out.returncode == 1
    assert out.stdout.splitlines() == [
        f"{bad}:5: goal file names the ticket key PROJ-12",
        f"{bad}:6: goal file links the plan plans/PROJ-1-epic.md",
    ]


def test_files_goals_set_and_absent_is_the_crew_message(tmp_path):
    root = repo(tmp_path, "crew-goals.json")
    (root / "goals.md").unlink()
    out = gate(root, "story", plan(root, "green"))
    assert out.returncode == 1
    assert (
        out.stdout.startswith("crew: ") and "files.goals 'goals.md' does not exist" in out.stdout
    )


def test_a_hyphenated_standard_in_a_metric_definition_is_no_ticket_key(tmp_path):
    root = repo(tmp_path, "crew-goals.json")
    goals = root / "goals.md"
    goals.write_text(
        goals.read_text().replace(
            "- metric: time to first report",
            "- metric: time to first report — UTF-8 export, SHA-256 checked, ISO-8601 dates, "
            "HTTP-2",
        )
    )
    out = gate(root, "epic", plan(root, "PROJ-1-epic"))
    assert out.returncode == 0, out.stdout
    assert out.stdout == ""


def test_a_ticket_key_in_a_metric_name_or_link_target_fails(tmp_path):
    root = repo(tmp_path, "crew-goals.json")
    goals = root / "goals.md"
    goals.write_text(
        goals.read_text()
        + "- metric: PROJ-7 adoption — share of owners\n"
        + "- metric: churn — see [the ticket](https://jira.example/browse/PROJ-8)\n"
    )
    out = gate(root, "epic", plan(root, "PROJ-1-epic"))
    assert out.returncode == 1
    assert out.stdout.splitlines() == [
        f"{goals}:7: goal file names the ticket key PROJ-7",
        f"{goals}:8: goal file names the ticket key PROJ-8",
    ]
