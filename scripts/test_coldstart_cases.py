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


def test_a_foreign_crew_case_runs_without_the_weside_mcp():
    """A crew of another team: no weside account, no weside MCP, a board and a launcher of its
    own, a minimal `.weside/config.json`. The plugin must work there from a cold start."""
    case = REPO / "tests" / "coldstart" / "master" / "foreign-crew-no-mcp.yaml"
    text = case.read_text(encoding="utf-8")
    top = {k: v.strip() for k, v in TOP.findall(text)}
    assert top["mcp"] == "none"
    assert ".weside/config.json:" in text
    data = json.loads((REPO / top["crew"]).read_text(encoding="utf-8"))
    assert data.get("weside_account") is not True
    assert data["board"]["file"] and data["launch"]["worker"]
    assert "weside" not in json.dumps(data).lower()


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
    top = {k: v.strip() for k, v in TOP.findall(case.read_text(encoding="utf-8"))}
    crew = crewlib._merge(json.loads((REPO / top["crew"]).read_text()))
    card = render_process.render_card(crew, role)
    cornerstone = card.split("## Cornerstone", 1)[1].split("## You do", 1)[0]
    first = card.split("## At start", 1)[1].split("## You wait on", 1)[0]
    [route] = ROUTE.findall(case.read_text(encoding="utf-8"))
    assert re.search(route.encode().decode("unicode_escape"), cornerstone + first)


UNKNOWN_KEY_CASE = REPO / "tests" / "coldstart" / "master" / "crew-unknown-key.yaml"


def test_an_unknown_crew_key_keeps_the_full_l0_with_the_line_on_startup_and_compact(
    tmp_path, monkeypatch
):
    """The hook output the case's session sees: the full L0, one notice line, identical after
    ``/compact`` (``refire: compact``)."""
    sys.path.insert(0, str(REPO / "we" / "hooks"))
    import process_on_start  # noqa: PLC0415

    text = UNKNOWN_KEY_CASE.read_text(encoding="utf-8")
    top = {k: v.strip() for k, v in TOP.findall(text)}
    assert top["refire"] == "compact"
    [route] = ROUTE.findall(text)
    repo = tmp_path / "repo"
    (repo / ".weside").mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / ".weside" / "crew.json").write_text((REPO / top["crew"]).read_text())
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # the served log, never the real one
    env = {"WE_ROLE": "master"}
    outs = [
        process_on_start.output({"cwd": str(repo), "source": source, "session_id": "s"}, env)
        for source in ("startup", "compact")
    ]
    assert outs[0] == outs[1] and outs[0][1] is None
    first, rest = outs[0][0].split("\n\n", 1)
    assert re.search(route, first) and first.startswith("crew.json: unknown keys ignored: limitz")
    generic = json.loads((REPO / "we/scripts/fixtures/crew-v2-generic.json").read_text())
    assert rest == render_process.render_l0(crewlib._merge(generic))


LIST = re.compile(r"^  (waits|not_waits|forbidden): \[(.*)\]$", re.MULTILINE)
SECURITY_FIXTURE = "we/scripts/fixtures/crew-v2-security.json"


def _lists(case: Path) -> dict[str, list[str]]:
    found = LIST.findall(case.read_text(encoding="utf-8"))
    return {k: [x.strip().strip('"') for x in v.split(",") if x.strip()] for k, v in found}


def top_prompt(case: Path) -> str:
    """The case's prompt (a folded block), whitespace collapsed."""
    text = case.read_text(encoding="utf-8")
    block = text.split("prompt: >\n", 1)[1].split("\nexpect:", 1)[0]
    return " ".join(block.split())


@pytest.mark.parametrize(
    ("name", "waits", "not_waits"),
    [
        ("security-twoway-panel-enough", [], ["security", "human"]),
        (
            "security-card-hit-card-worker-signs",
            [],
            ["human", "product", "acceptance", "security"],
        ),
    ],
)
def test_the_security_master_cases_name_who_waits_in_order(name, waits, not_waits):
    """A two-way auth diff with a green panel waits on nobody (the panel is enough); a
    ``trust-loosening`` hit (a card hit, T2 two-way) starts a fresh worker with the security card,
    whose verdict is a PR comment, and auto-merges without waiting on it."""
    case = REPO / "tests" / "coldstart" / "master" / f"{name}.yaml"
    top = {k: v.strip() for k, v in TOP.findall(case.read_text(encoding="utf-8"))}
    assert top["role"] == "master" and top["crew"] == SECURITY_FIXTURE
    lists = _lists(case)
    assert lists["waits"] == waits and lists["not_waits"] == not_waits
    assert ("gh pr merge --auto" in lists.get("forbidden", [])) == bool(waits)
    assert "8.0.0" not in top_prompt(case)


def test_the_unbound_t2_oneway_case_keeps_waiting_on_the_human_alone():
    case = REPO / "tests" / "coldstart" / "master" / "t2-oneway-human-merges.yaml"
    assert "crew-v2-generic.json" in case.read_text(encoding="utf-8")
    assert _lists(case)["waits"] == ["human"]


def test_the_t2_oneway_case_routes_a_question_and_arms_after_the_yes():
    """The one-way case's master posts the merge question on the board itself and arms with `arm_pr.sh`
    once the yes is back; no approve on GitHub and no go number is the yes. The case's route must be
    one the rendered L0 gives, and nothing the case forbids may stand in it. Red arm: the L0 that
    made the master arm with `arm_pr.sh --go Q<nr>`."""
    case = REPO / "tests" / "coldstart" / "master" / "t2-oneway-human-merges.yaml"
    forbidden = _lists(case)["forbidden"]
    assert {"gh pr review --approve", "please approve", "arm_pr.sh --go"} <= set(forbidden)
    [route] = ROUTE.findall(case.read_text(encoding="utf-8"))
    l0, _card = _rendered(GENERIC_FIXTURE)
    one_way = l0.split("- **One-way is a computed class:**", 1)[1].split("\n- ", 1)[0]
    flat = " ".join(one_way.split())
    assert re.search(route.encode().decode("unicode_escape"), flat), flat
    assert "`arm_pr.sh`" in flat
    assert [f for f in forbidden if f in flat] == [], flat
    assert "approve" not in flat


GENERIC_FIXTURE = "we/scripts/fixtures/crew-v2-generic.json"
ORDER_LINE = (
    "- On a card hit (`trust-loosening`, `brake-review`): a fresh worker with Bo's card reviews the "
    "head, its verdict a PR comment; auto-merge does not wait on it; on a one-way PR it goes to Hal "
    "with the T2 panel."
)
# L0's one security line: the holder runs on call; a worker with its card reviews each card hit
SECURITY_LINE = (
    "  - Bo owns its label, runs on call; a worker with its card reviews each card hit."
)


def _rendered(fixture: str) -> tuple[str, str]:
    """What a master reads at start: L0 and its card, rendered with the case's crew."""
    crew = crewlib._merge(json.loads((REPO / fixture).read_text(encoding="utf-8")))
    return render_process.render_l0(crew), render_process.render_card(crew, "master")


def test_the_security_cases_crew_renders_the_routing_they_expect():
    """The security master cases route on lines the rendered process must carry: the master card's
    order (panel, review, auto-merge), and L0's security line (on call, reviews each card hit).
    Comparing the YAML with a table only checks it against itself; this renders what the master
    reads with the crew the cases name."""
    l0, card = _rendered(SECURITY_FIXTURE)
    lines = l0.split("\n")
    assert ORDER_LINE in card.split("\n"), "master card lacks the card-hit order line"
    assert "Bo's review" not in card, "master card still waits on the security review"
    assert SECURITY_LINE in lines, "L0 lacks the security line (on call, reviews each card hit)"


def test_the_generic_crew_renders_no_security_routing():
    l0, card = _rendered(GENERIC_FIXTURE)
    assert "trust-loosening` diff:" not in card
    assert "also waits for" not in card
    assert "owns its label" not in l0
    assert "signs `trust-loosening`" not in l0


@pytest.mark.parametrize(
    ("name", "fixture"),
    [
        ("card-blocking-after-merge", SECURITY_FIXTURE),
        ("main-red-keeps-merging", GENERIC_FIXTURE),
    ],
)
def test_the_merge_cases_route_on_a_line_the_rendered_l0_carries(name, fixture):
    """A card verdict after the merge becomes a fix story; main red does not hold the arm.
    Both routes must be satisfiable by the L0 the master reads with the case's crew."""
    case = REPO / "tests" / "coldstart" / "master" / f"{name}.yaml"
    top = {k: v.strip() for k, v in TOP.findall(case.read_text(encoding="utf-8"))}
    assert top["crew"] == fixture
    [route] = ROUTE.findall(case.read_text(encoding="utf-8"))
    l0, _ = _rendered(fixture)
    assert re.search(route, " ".join(l0.split()))


# L0 § Flow first (Q954): a cold session of these roles reads the section (the worker its short
# form: the starter posts its question), and no line routes a question for the human through the
# coordinator. Red arm: origin/main before the section (`ask via Otto`, `goes to Otto as one line`).
FLOW_FIRST_ROLES = ("coordinator", "master", "worker")


@pytest.mark.parametrize("role", FLOW_FIRST_ROLES)
def test_a_cold_start_reads_flow_first_and_no_question_through_the_coordinator(role):
    crew = crewlib._merge(json.loads((REPO / GENERIC_FIXTURE).read_text(encoding="utf-8")))
    coordinator = crewlib.display_name(crew, "coordinator")
    text = render_process.role_text(crew, role) + render_process.render_card(crew, role)
    flat = " ".join(text.split())
    if role == "worker":
        assert "goes to your starter as one line" in flat and "which it posts on the board" in flat
    else:
        assert "## Flow first" in text and "In doubt, flow wins." in flat
    for phrase in (
        f"via {coordinator}",
        "through the coordinator",
        f"goes to {coordinator} as one line",
    ):
        assert phrase not in flat, (role, phrase)
