"""render_process.py: the L0 template filled from a crew, the worker short form, the role totals
and the ``--serves`` predicate."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import crew as crewlib
import pytest
import render_process as rp

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "render_process.py"
GENERIC = HERE / "fixtures" / "crew-v2-generic.json"

INBOX = (
    "**The board is Hal's only inbox:** the push line, the bundle and an escalation each point at "
    "a board item."
)
ONE_WAY = (
    "Only Hal\n  merges it (user merge, enforced by the `one-way gate` check), from a board item "
    "with the PR link,\n  the class and the panel verdict; the merge hook only warns early."
)
DECIDED_3 = "3. Only Hal merges the computed one-way class (user merge); all other T2 auto-merge."


@pytest.fixture(autouse=True)
def _state_dir(tmp_path, monkeypatch):
    """Recorded extra-hook outputs go to a temp state dir, never the real home."""
    monkeypatch.setenv("WE_STATE_DIR", str(tmp_path / "we-state"))


def crew_repo(tmp_path: Path, data: dict | None = None) -> Path:
    repo = tmp_path / "repo"
    (repo / ".weside").mkdir(parents=True, exist_ok=True)
    (repo / ".git").mkdir(exist_ok=True)
    if data is None:
        shutil.copy(GENERIC, repo / ".weside" / "crew.json")
    else:
        (repo / ".weside" / "crew.json").write_text(json.dumps(data))
    return repo


def generic() -> dict:
    return crewlib._merge(json.loads(GENERIC.read_text()))


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )


def test_every_role_renders_within_the_budget_with_crew_values():
    crew = generic()
    for role in rp.all_roles():
        text = rp.role_text(crew, role)
        assert len(text) <= rp.BUDGET, role
        assert "{" not in text.replace("{name}", ""), role
    full = rp.render_l0(crew)
    assert "Ada: the WHAT" in full and "Otto adds Bo as second reviewer" in full
    assert "Specialists woken on demand: Bo (security), Lex (legal)." in full
    assert "`ASK · <KEY> <title> · <question without context> · Advice: …`" in full
    assert "`done-for-now` before parking" in full
    assert "pod 16 GiB minus gate lock (≤ 2), test slot (≤ 3) and devbox" in full
    assert "\n## Local (this crew)\n\n- A draft PR names why it waits in its first line.\n" in full


def test_the_template_renders_against_the_defaults_alone():
    text = rp.render_l0(crewlib._merge({"version": 2, "roles": {}, "members": {}}))
    assert "The product owner: the WHAT" in text
    assert "the human" in text and "QUESTION ·" in text and "Recommendation: …" in text
    assert "Specialists" not in text, "the specialists line drops without specialists"
    assert "## Local" not in text, "the local section drops without local_rules"
    assert "the risk classifier over the risk paths" in text
    assert len(text) <= rp.BUDGET


def test_a_token_without_value_or_fallback_raises():
    with pytest.raises(rp.RenderError, match="no such crew key"):
        rp.render("{no.such.key}", generic())
    with pytest.raises(rp.RenderError, match="no fallback"):
        rp.render("{files.goals}", generic())
    assert rp.render("{files.goals|the goal file}", generic()) == "the goal file"


def test_talking_carries_the_board_only_inbox_bullet():
    assert INBOX in rp.render_l0(generic())


def test_waits_names_the_human_as_the_only_merger_of_one_way():
    text = rp.render_l0(generic())
    assert ONE_WAY in text
    assert DECIDED_3 in text
    for old in ("one word arms auto-merge", "one push line at panel green", "reads the class"):
        assert old not in text, old


def test_the_phrase_tests_go_red_on_the_previous_text(tmp_path):
    """Red arm: the version-1 text (one word arms auto-merge, no inbox bullet) fails both."""
    process = tmp_path / "process"
    process.mkdir()
    old = (rp.PROCESS / "L0.md").read_text()
    old = old.replace(
        "- **The board is {human}'s only inbox:** the push line, the bundle and an "
        "escalation each point at a board item.\n",
        "",
    )
    old = old.replace(
        "Only {human}\n  merges it",
        "{human} gets one\n  push line at panel green; "
        "one word arms auto-merge. Only {human}\n  merges it",
    )
    (process / "L0.md").write_text(old)
    text = rp.render_l0(generic(), process=process)
    assert INBOX not in text
    assert "one word arms auto-merge" in text


def test_worker_form_is_short_and_carries_the_crew_values():
    text = rp.role_text(generic(), "worker")
    assert len(text) <= 1_500
    assert "a question for Hal goes to Otto as one line `ASK ·" in text
    assert "(full text: `render_process.py --role master`)" in text
    assert text.count("\n- ") == 5


def test_cli_role_and_all_roles(tmp_path):
    repo = crew_repo(tmp_path)
    for workplace in ("biz", "infra"):
        (tmp_path / workplace).mkdir()
    full = run("--role", "master", "--from", str(repo))
    card = rp.render_card(generic(), "master")
    assert (
        full.returncode == 0
        and full.stdout == f"{rp.render_l0(generic())}\n\n{card}\n\n{rp.POINTER}\n"
    )
    sizes = run("--all-roles", "--from", str(repo))
    assert sizes.returncode == 0
    rows = [line.split("\t") for line in sizes.stdout.splitlines()]
    assert [r[0] for r in rows] == list(rp.all_roles())
    assert all(r[3] == "ok" and int(r[2]) > 0 for r in rows)


def test_serves_needs_a_crew_that_loads(tmp_path):
    repo = crew_repo(tmp_path)
    assert run("--serves", "--from", str(repo)).returncode == 0
    (repo / ".weside" / "crew.json").write_text(json.dumps({"version": 1, "roles": {}}))
    assert run("--serves", "--from", str(repo)).returncode == 1
    bare = tmp_path / "bare"
    (bare / ".git").mkdir(parents=True)
    assert run("--serves", "--from", str(bare)).returncode == 1


def test_serves_is_false_when_the_render_is_over_budget(tmp_path):
    data = json.loads(GENERIC.read_text())
    data["local_rules"] = ["x" * 160] * 10
    repo = crew_repo(tmp_path, data)
    assert len(rp.render_l0(crewlib.load(repo / ".weside" / "crew.json"))) > rp.BUDGET
    assert run("--serves", "--from", str(repo)).returncode == 1


def _write(path: Path, text: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return len(text)


def test_total_counts_the_instruction_layer_of_a_role(tmp_path):
    """Workplace ``infra`` with an extra repo ``core`` (the crew's repo); an ancestor AGENTS.md."""
    ws = tmp_path / "ws"
    core = crew_repo(ws)  # ws/repo holds the crew
    infra = ws / "infra"
    data = json.loads(GENERIC.read_text())
    data["members"]["kit"]["workplace"] = "../infra"
    (core / ".weside" / "crew.json").write_text(json.dumps(data))
    counted = _write(tmp_path / "AGENTS.md", "ancestor " * 10)
    counted += _write(infra / "AGENTS.md", "infra agents " * 7)
    counted += _write(infra / ".claude" / "rules" / "a.md", "always a\n")
    counted += _write(
        infra / ".claude" / "rules" / "sub" / "b.md", "---\ndescription: x\n---\nb\n"
    )
    scoped = _write(infra / ".claude" / "rules" / "c.md", '---\npaths: ["src/**"]\n---\nscoped\n')
    loose = _write(infra / ".claude" / "rules" / "d.md", '---\npaths: "**"\n---\nany file\n')
    counted += _write(core / "CLAUDE.md", "core claude\n")
    _write(core / "AGENTS.md", "core agents, never counted for an extra repo\n")
    counted += _write(core / ".claude" / "rules" / "e.md", "core always\n")
    _write(core / ".claude" / "rules" / "f.md", '---\npaths: "x/**"\n---\nscoped core\n')
    home = tmp_path / "home"
    home.mkdir()
    crew = crewlib.load(core / ".weside" / "crew.json")
    [(label, slug, rows, total)] = rp.total_rows(
        core / ".weside" / "crew.json", crew, "machinery", home
    )
    assert (label, slug) == ("machinery Kit", "kit")
    parts = {(part, Path(path).name) for part, path, _ in rows}
    assert ("extra", "AGENTS.md") not in parts and ("rules", "c.md") not in parts
    assert ("rules-any-file", "d.md") in parts and ("extra", "CLAUDE.md") in parts
    l0 = len(rp.render_l0(crew))
    sizes = {p: n for p, _, n in rows}
    hook = sum(sizes[p] for p in ("plugin-hook", "card", "addendum", "extra-head", "extra-hooks"))
    assert hook == len(rp.session_text(core / ".weside" / "crew.json", crew, "machinery", "kit"))
    assert sizes["extra-head"] == len("core agents, never counted for an extra repo")
    assert total == counted + l0 + hook
    assert scoped and loose  # neither is in the sum
    out = run("--role", "machinery", "--total", "--from", str(core), "--home", str(home))
    assert out.returncode == 0
    assert out.stdout.splitlines()[0] == "# machinery Kit"
    assert (
        out.stdout.splitlines()[-1] == f"rules-any-file\t{infra / '.claude/rules/d.md'}\t{loose}"
    )
    assert f"sum\t\t{total}" in out.stdout


def test_total_for_specialists_prints_one_block_each(tmp_path):
    ws = tmp_path / "ws"
    repo = crew_repo(ws)
    (ws / "biz").mkdir()
    out = run("--role", "specialist", "--total", "--from", str(repo), "--home", str(tmp_path))
    assert out.returncode == 0
    assert [line for line in out.stdout.splitlines() if line.startswith("#")] == [
        "# specialist Bo",
        "# specialist Lex",
    ]


# --- role cards (L1) ----------------------------------------------------------------------

DEFAULTS_ONLY = {"version": 2, "roles": {}, "members": {}}


def _norm(line: str) -> str:
    return " ".join(line.strip().lstrip("-*0123456789. ").replace("*", "").split()).lower()


@pytest.mark.parametrize("data", [None, DEFAULTS_ONLY], ids=["fixture", "defaults"])
def test_every_card_has_the_five_headings_fits_and_repeats_no_l0_line(data):
    crew = generic() if data is None else crewlib._merge(data)
    for role in rp.all_roles():
        raw = (rp.ROLES / f"{role}.md").read_text(encoding="utf-8")
        assert len(raw) <= rp.CARD_RAW_BUDGET, role
        card = rp.render_card(crew, role)
        assert tuple(rp.card_headings(card)) == rp.CARD_HEADINGS, role
        assert not rp.TOKEN.search(card), role
        assert len(rp.compose(rp.Parts(role, card, None, [], []))[0]) <= rp.BUDGET
        l0 = rp.render_l0(crew, "worker" if role == "worker" else "full")
        l0_lines = {_norm(x) for x in l0.split("\n") if len(_norm(x).split()) >= 4}
        for line in card.split("\n"):
            assert _norm(line) not in l0_lines, (role, line)


def test_the_card_sizes_follow_the_plan():
    sizes = {r: len((rp.ROLES / f"{r}.md").read_text(encoding="utf-8")) for r in rp.all_roles()}
    assert sizes["specialist"] <= 1_800 and sizes["worker"] <= 1_500


def test_no_card_names_a_member_of_the_fixture_crew():
    """A card written from a filled example carries a real name; the plugin cannot know real
    names, so the neutral fixture's stand in."""
    data = json.loads(GENERIC.read_text())
    names = {m["name"] for m in data["members"].values()} | {data["human"]["name"]}
    for card in rp.ROLES.glob("*.md"):
        words = set(re.findall(r"\b[A-Z][a-z]+\b", card.read_text(encoding="utf-8")))
        assert not words & names, (card.name, words & names)


def test_the_master_card_carries_the_fence_transition_line():
    card = rp.render_card(generic(), "master")
    assert "While `epic.fence_confirmed` is false on the board" in card


def _member_ws(tmp_path: Path) -> tuple[Path, dict]:
    ws = tmp_path / "ws"
    repo = crew_repo(ws)
    for d in ("biz", "infra"):
        (ws / d).mkdir()
    return repo, crewlib.load(repo / ".weside" / "crew.json")


def test_total_rows_carry_card_addendum_extras_and_the_role_skill(tmp_path):
    repo, crew = _member_ws(tmp_path)
    infra = repo.parent / "infra"
    addendum = _write(infra / ".weside" / "roles" / "kit.md", "Kit's local notes.\n")
    # the session starts in infra; its crew pointer gives the skill prefix (``crew.skill_path``)
    _write(infra / ".weside" / "config.json", json.dumps({"crew": "../repo/.weside/crew.json"}))
    skill = _write(
        infra / ".claude" / "skills" / "acme-kit" / "SKILL.md", "---\nname: x\n---\nbody\n"
    )
    _write(repo / "AGENTS.md", "# Repo\n\nHead line.\n\n## Later\n\nnot counted\n")
    _write(
        repo / ".claude" / "settings.json",
        json.dumps(
            {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "printf hi"}]}]}}
        ),
    )
    rp.card_parts(repo / ".weside" / "crew.json", crew, "machinery", "kit")  # records "hi"
    [t] = rp.total_rows(repo / ".weside" / "crew.json", crew, "machinery", tmp_path / "home")
    rows = {part: (path, n) for part, path, n in t.rows}
    assert rows["card"] == ("roles/machinery.md", len(rp.render_card(crew, "machinery")))
    assert rows["addendum"][1] == addendum - 1  # the trailing newline is stripped
    assert rows["extra-head"] == (str(repo.resolve()), len("# Repo\n\nHead line."))
    assert rows["extra-hooks"] == ("printf hi", 2)
    assert rows["role-skill"] == (str(infra.resolve() / ".claude/skills/acme-kit/SKILL.md"), skill)
    out = run("--role", "machinery", "--total", "--from", str(repo), "--home", str(tmp_path))
    lines = out.stdout.splitlines()
    assert [ln.split("\t")[0] for ln in lines[1:8]] == [
        "L0",
        "plugin-hook",
        "card",
        "addendum",
        "extra-head",
        "extra-hooks",
        "role-skill",
    ]


def test_an_unpinned_master_has_no_role_skill_and_its_repo_addendum_counts(tmp_path):
    repo, crew = _member_ws(tmp_path)
    _write(repo / ".weside" / "roles" / "master.md", "Masters here use the shared lane.\n")
    [t] = rp.total_rows(repo / ".weside" / "crew.json", crew, "master", tmp_path / "home")
    rows = {part: n for part, _, n in t.rows}
    assert rows["role-skill"] == 0 and rows["addendum"] == len("Masters here use the shared lane.")


def test_compose_cuts_hook_output_first_then_head_lines():
    head = "\n".join(f"head {i}" for i in range(200))
    hook = "\n".join(f"line {i:05d}" for i in range(1_100))
    parts = rp.Parts(
        "master", "C" * 6_000, None, [(Path("/x"), head)], [(Path("/x"), "cmd", hook)]
    )
    text, sizes = rp.compose(parts)
    assert len(text) <= rp.BUDGET and sizes["extra-head"] == len(head)
    assert head in text and text.rstrip().endswith("… cut, full output: cmd in /x")
    small = rp.Parts(
        "master", "C" * 9_000, None, [(Path("/x"), head)], [(Path("/x"), "cmd", hook)]
    )
    text, _ = rp.compose(small)
    assert len(text) <= rp.BUDGET and "… cut, full text: /x/AGENTS.md" in text
    with pytest.raises(rp.RenderError, match=r"plus addendum /a\.md has"):
        rp.compose(rp.Parts("master", "C" * 9_000, (Path("/a.md"), "A" * 600), [], []))


def test_limit_key_prefers_the_member_key():
    assert (
        rp.limit_key("specialist", "bo", {"specialist": 1, "specialist:bo": 2}) == "specialist:bo"
    )
    assert rp.limit_key("specialist", "lex", {"specialist": 1}) == "specialist"
    assert rp.limit_key("master", "", {"master": 1}) == "master"


def _hook_settings(repo: Path, *commands: str) -> None:
    hooks = [{"type": "command", "command": c} for c in commands]
    _write(
        repo / ".claude" / "settings.json",
        json.dumps({"hooks": {"SessionStart": [{"hooks": hooks}]}}),
    )


def test_extra_hooks_share_one_total_time_cap(tmp_path, monkeypatch):
    """Three hooks of 0.7 s under a 1 s cap: the first runs, the one that would cross the cap
    and the one after it are skipped, each with one line."""
    repo, crew = _member_ws(tmp_path)
    _hook_settings(repo, "sleep 0.7; printf one", "sleep 0.7; printf two", "printf three")
    monkeypatch.setattr(rp, "EXTRA_HOOKS_CAP", 1, raising=False)
    parts = rp.card_parts(repo / ".weside" / "crew.json", crew, "machinery", "kit")
    outputs = [out for _, _, out in parts.hooks]
    assert outputs[0] == "one"
    assert outputs[1:] == [
        "extra hook skipped, total cap 1 s reached: sleep 0.7; printf two",
        "extra hook skipped, total cap 1 s reached: printf three",
    ]


def test_totals_never_run_extra_hooks_and_count_the_recorded_output(tmp_path):
    repo, crew = _member_ws(tmp_path)
    marker = tmp_path / "ran"
    _hook_settings(repo, f"touch {marker}; printf hello")
    path = repo / ".weside" / "crew.json"
    [t] = rp.total_rows(path, crew, "machinery", tmp_path / "home")
    assert not marker.exists(), "role totals ran an extra repo's hook"
    rows = [(part, where, n) for part, where, n in t.rows]
    assert ("extra-hooks", f"touch {marker}; printf hello", 0) in rows
    assert ("note", "extra-hooks not run (measure only)", 0) in rows
    rp.card_parts(path, crew, "machinery", "kit")  # what the SessionStart hook does
    assert marker.exists()
    marker.unlink()
    [t] = rp.total_rows(path, crew, "machinery", tmp_path / "home")
    assert not marker.exists()
    rows = [(part, where, n) for part, where, n in t.rows]
    assert ("extra-hooks", f"touch {marker}; printf hello", len("hello")) in rows
    assert all(part != "note" for part, _, _ in rows)
