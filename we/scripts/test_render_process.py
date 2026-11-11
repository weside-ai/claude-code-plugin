"""render_process.py: the L0 template filled from a crew, the worker short form, the role totals
and the ``--serves`` predicate."""

from __future__ import annotations

import json
import os
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
    "A one-way PR outside the\n  core merges itself, where a self-merge window runs, 2 h after "
    "a green T2 panel on its head, once\n  Hal got the push line; a `veto` label stops it; else and "
    "the core only Hal merges."
)
DECIDED_3 = "3. One-way merges via the 2 h window, the core by Hal."


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
    assert "Ada: the WHAT" in full and "Otto adds a worker with Bo's card to review" in full
    assert "Specialists woken on demand: Bo (security), Lex (legal)." in full
    assert "`ASK · <KEY> <title> · <question without context> · Advice: …`" in full
    assert "`done-for-now` before parking" in full
    assert "- **Capacity:** a master's limit is its context: watch compactions" in full
    assert "GiB" not in full, "the L0 names no host memory numbers"
    assert "\n## Local (this crew)\n\n- A draft PR names why it waits in its first line.\n" in full


def test_the_template_renders_against_the_defaults_alone():
    text = rp.render_l0(crewlib._merge({"version": 2, "roles": {}, "members": {}}))
    assert "The product owner: the WHAT" in text
    assert "the human" in text and "QUESTION ·" in text and "Recommendation: …" in text
    assert "Specialists" not in text, "the specialists line drops without specialists"
    assert "## Local" not in text, "the local section drops without local_rules"
    assert "`risk_paths.py` over `.weside/risk-paths`" in text
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


# the crew notice line a hook may print above the L0, its two newlines included
NOTICE_RESERVE = 160


def test_owners_decide_cut_and_fence_and_the_manual_rc_line_closes_the_l0():
    text = rp.render_l0(generic())
    assert (
        "- An owner decides cut and fence questions of their area unless a new outcome, money, law"
        " or the vision\n  is touched; a board line records it and Hal may overturn it.\n"
    ) in text
    assert text.rstrip().endswith("Until the RC train job ships, RCs are cut by hand.")
    assert "today's rules hold" not in text


def test_the_l0_keeps_room_for_the_notice_line():
    for data in (None, DEFAULTS_ONLY):
        crew = generic() if data is None else crewlib._merge(data)
        assert len(rp.render_l0(crew)) + NOTICE_RESERVE <= rp.BUDGET


def test_capacity_numbers_and_cadence_owners_left_the_l0():
    template = (rp.PROCESS / "L0.md").read_text(encoding="utf-8")
    assert "capacity_line" not in rp.SPECIAL and "{capacity" not in template
    cadences = template.split("## Cadences", 1)[1].split("\n## ", 1)[0]
    for gone in ("({machinery})", "({hr},", "({human} + {escalation})"):
        assert gone not in cadences, gone


def test_the_phrase_tests_go_red_on_the_previous_text(tmp_path):
    """Red arm: the version-1 text (one word arms auto-merge, no inbox bullet) fails both."""
    process = tmp_path / "process"
    process.mkdir()
    old = (rp.PROCESS / "L0.md").read_text()
    old = old.replace(
        "- **The board is {human.local}'s only inbox:** the push line, the bundle and an "
        "escalation each point at a board item.\n",
        "",
    )
    old = old.replace(
        "else and the core only {human} merges.",
        "else and the core only {human} merges. {human} gets one push line at panel green; one "
        "word arms auto-merge.",
    )
    (process / "L0.md").write_text(old)
    text = rp.render_l0(generic(), process=process)
    assert INBOX not in text
    assert "one word arms auto-merge" in text


WORKER_ENDS = (
    "- **Workers execute one chunk and end**; a PR chunk ends at its merge or a `user merge` {label};\n"
    "  the worker watches it until green and ends, its starter until the merge."
)
REARM = (
    "4. Also after a compaction: re-arm the watch per `/we:master` § Push, PR, CI step 4"
    " for every open PR you own.\n"
)


def test_whoever_opens_a_pr_watches_it_and_the_master_re_arms_after_a_compaction():
    crew = generic()
    assert WORKER_ENDS.format(label=crew["question_label"]) in rp.render_l0(crew)
    assert REARM in rp.render_card(generic(), "master")


def test_the_watch_phrases_go_red_on_the_previous_text(tmp_path):
    """Red arm: the text before the watch rule (worker ends after its chunk, no re-arm step)."""
    process, roles = tmp_path / "process", tmp_path / "roles"
    process.mkdir()
    roles.mkdir()
    l0 = (rp.PROCESS / "L0.md").read_text(encoding="utf-8")
    old_l0 = l0.replace(
        WORKER_ENDS.format(label="{question_label}") + " Masters",
        "- **Workers execute one chunk and end.** Masters",
    )
    assert old_l0 != l0
    (process / "L0.md").write_text(old_l0, encoding="utf-8")
    for card in rp.ROLES.glob("*.md"):
        (roles / card.name).write_text(card.read_text(encoding="utf-8"), encoding="utf-8")
    master = (roles / "master.md").read_text(encoding="utf-8")
    assert REARM in master
    (roles / "master.md").write_text(master.replace(REARM, ""), encoding="utf-8")
    crew = generic()
    assert WORKER_ENDS.format(label=crew["question_label"]) not in rp.render_l0(
        crew, process=process
    )
    assert REARM not in rp.render_card(crew, "master", roles=roles)


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
    assert full.returncode == 0 and full.stdout == f"{rp.render_l0(generic())}\n\n{card}\n"
    sizes = run("--all-roles", "--from", str(repo))
    assert sizes.returncode == 0
    rows = [line.split("\t") for line in sizes.stdout.splitlines()]
    assert [r[0] for r in rows] == [*rp.all_roles(), "fallback"]
    assert all(r[3] == "ok" and int(r[2]) > 0 for r in rows)
    crew = generic()
    master = next(r for r in rows if r[0] == "master")
    assert int(master[1]) == len(rp.render_l0(crew)) + rp.NOTICE_CHARS
    fallback = crewlib.fallback(repo / ".weside" / "crew.json", "")
    assert rows[-1][1:3] == [
        str(len(rp.render_l0(fallback, kind)) + rp.NOTICE_CHARS) for kind in ("full", "worker")
    ]


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
    assert "While your epic's plan lacks its user, metric or scope fence" in card


def test_the_master_card_carries_the_effort_rule_and_the_epic_update():
    card = rp.render_card(generic(), "master")
    for phrase in (
        "do it inline when it is a handful of tool calls",
        "use a read-only\n  subagent for a wide read or a review",
        "give a story to one worker (the default)",
        "two to\n  four workers only for independent chunks",
        "Multi-agent work costs ~15\u00d7 the tokens.",
        "After every merged story: `/we:epic` update (Updates Log, ticket mirror) before you pull"
        " the next one.",
    ):
        assert phrase in card, phrase


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


# --- crew notice (unknown keys, refused crew) -----------------------------------------------


UNKNOWN_KEY = HERE / "fixtures" / "crew-v2-unknown-key.json"


def _without_notice_token(kind: str) -> str:
    name = "L0-worker.md" if kind == "worker" else "L0.md"
    text = (rp.PROCESS / name).read_text(encoding="utf-8")
    assert text.startswith("{crew_notice}\n\n")
    return text[len("{crew_notice}\n\n") :]


@pytest.mark.parametrize("kind", ["full", "worker"])
def test_a_clean_crew_renders_as_without_the_notice_token(kind):
    crew = {**generic(), "unknown_keys": []}
    assert rp.render_l0(crew, kind) == rp.render(_without_notice_token(kind), crew)
    assert "crew.json" not in rp.render_l0(crew, kind).split("\n")[0]


@pytest.mark.parametrize("kind", ["full", "worker"])
def test_unknown_keys_render_one_notice_line_first(tmp_path, kind, capsys):
    repo = crew_repo(tmp_path, json.loads(UNKNOWN_KEY.read_text()))
    crew = crewlib.load(repo / ".weside" / "crew.json")
    text = rp.render_l0(crew, kind)
    first, rest = text.split("\n\n", 1)
    assert first == (
        "crew.json: unknown keys ignored: limitz, limits.masterz, roles.auditor, "
        "members.ada.titel, fallback.securty, lenses.product.keepr"
    )
    assert rest == rp.render(_without_notice_token(kind), crew)
    assert text.count("unknown keys ignored") == 1


def test_a_refused_crew_renders_the_reason_under_its_own_label(tmp_path):
    repo = crew_repo(tmp_path)
    path = repo / ".weside" / "crew.json"
    data = json.loads(GENERIC.read_text())
    data["labels"]["crew_unreadable"] = "crew.json nicht lesbar"
    path.write_text(json.dumps(data))
    crew = crewlib.fallback(path, f"{path}: limits.masters must be a number")
    first = rp.render_l0(crew).split("\n\n", 1)[0]
    assert first == f"crew.json nicht lesbar: {path}: limits.masters must be a number"
    assert crewlib.fallback(path, "x")["crew_error"] == "x" and crew["members"] == {}


def test_a_long_notice_is_cut_to_the_reserve_keeping_label_and_reason_end():
    reason = "/" + "deep/" * 60 + ".weside/crew.json: limits.masters must be a number"
    crew = {**generic(), "crew_error": reason}
    first = rp.render_l0(crew).split("\n\n", 1)[0]
    assert len(first) + 2 == rp.NOTICE_CHARS
    assert first.startswith("crew.json not readable: /deep/") and "…" in first
    assert first.endswith("crew.json: limits.masters must be a number")
    short = {**generic(), "crew_error": "y"}
    assert rp.render_l0(short).split("\n\n", 1)[0] == "crew.json not readable: y"


@pytest.mark.parametrize("kind", ["full", "worker"])
def test_the_fallback_l0_fits_the_budget_with_the_reserve(kind):
    fallback = crewlib.fallback(None, "x" * 400)
    assert len(rp.render_l0({**fallback, "crew_error": None}, kind)) + rp.NOTICE_CHARS <= rp.BUDGET
    assert len(rp.render_l0(fallback, kind)) <= rp.BUDGET
    assert rp.l0_chars(fallback, kind) <= rp.BUDGET


def test_serves_counts_the_reserve(tmp_path, monkeypatch):
    repo = crew_repo(tmp_path)
    assert run("--serves", "--from", str(repo)).returncode == 0
    crew = crewlib.load(repo / ".weside" / "crew.json")
    full = len(rp.render_l0(crew))
    monkeypatch.setattr(rp, "BUDGET", full + rp.NOTICE_CHARS - 1)
    assert rp.serves(repo) is False
    monkeypatch.setattr(rp, "BUDGET", full + rp.NOTICE_CHARS)
    assert rp.serves(repo) is True


SECURITY = HERE / "fixtures" / "crew-v2-security.json"
# one line: on call (woken, not running); a worker with its card signs a `trust-loosening` item
SECURITY_LINE = (
    "  - {security} owns its label, runs on call; a worker with its card signs card hits."
)
BOUND_SECURITY_LINE = (
    "  - Bo owns its label, runs on call; a worker with its card signs card hits."
)
TRUST_LINE = (
    "- On a card hit (`trust-loosening`, `money-path`, `brake-review`): the panel, then a fresh "
    "worker with {security}'s card signs on the head, then auto-merge."
)


def bound() -> dict:
    return crewlib._merge(json.loads(SECURITY.read_text()))


def _template_without(name: str, line: str) -> str:
    text = (rp.PROCESS / name).read_text(encoding="utf-8")
    assert text.count(line + "\n") == 1, line
    return text.replace(line + "\n", "")


@pytest.mark.parametrize("kind", ["full", "worker"])
def test_an_unbound_crew_renders_as_the_template_without_the_security_line(kind):
    """Without ``roles.security`` the line holding the bare token drops, so the render equals the
    template without it: byte-identical to the release before the role key."""
    crew = generic()
    name = "L0-worker.md" if kind == "worker" else "L0.md"
    text = (rp.PROCESS / name).read_text(encoding="utf-8")
    text = text.replace(SECURITY_LINE + "\n", "")
    expected = rp.render(text, crew)
    assert rp.render_l0(crew, kind) == expected
    assert "owns its label" not in rp.render_l0(crew, kind)
    assert "Bo (security)" in rp.render_l0(crew, "full")


def test_a_bound_security_owner_gets_its_line_and_leaves_the_specialists():
    full = rp.render_l0(bound())
    assert "\n" + BOUND_SECURITY_LINE + "\n" in full
    assert "Specialists woken on demand: Lex (legal)." in full
    assert "Bo (security)" not in full


def on_call_line(l0: str, name: str) -> str | None:
    """The L0 line naming ``name`` as an owner run on call (woken, not running all the time)."""
    return next((x for x in l0.split("\n") if name in x and "on call" in x), None)


def test_the_security_line_says_its_owner_is_woken_on_call():
    """The holder leaves the specialists line, so its own line carries "on call"."""
    assert on_call_line(rp.render_l0(bound()), "Bo") == BOUND_SECURITY_LINE
    assert on_call_line(rp.render_l0(generic()), "Bo") is None


def test_a_role_holder_is_never_listed_as_specialist_even_with_the_field():
    data = json.loads(SECURITY.read_text())
    data["members"]["bo"]["specialist"] = "security"
    crew = crewlib._merge(data)
    assert "Bo (security)" not in rp.render_l0(crew)
    assert [slug for slug, _ in rp.specialist_members(crew)] == ["lex"]
    assert [label for label, _, _ in rp._sessions(SECURITY, crew, "specialist")] == [
        "specialist Lex"
    ]


def test_an_optional_role_token_with_a_fallback_keeps_its_line():
    """Only the bare token drops its line; ``{security|…}`` renders its fallback."""
    text = rp.render("a {security|nobody}\nb {security}\nc", generic())
    assert text == "a nobody\nc"


def test_the_master_card_carries_the_trust_loosening_order_only_when_bound():
    assert TRUST_LINE in (rp.ROLES / "master.md").read_text(encoding="utf-8")
    with_owner = rp.render_card(bound(), "master")
    assert (
        "- On a card hit (`trust-loosening`, `money-path`, `brake-review`): the panel, then a fresh "
        "worker with Bo's card signs on the head, then auto-merge." in with_owner
    )
    assert "trust-loosening" not in rp.render_card(generic(), "master")


@pytest.mark.parametrize("crew", [generic, bound], ids=["unbound", "bound"])
def test_the_security_card_names_label_lens_review_and_signature(crew):
    card = " ".join(rp.render_card(crew(), "security").split())
    for phrase in (
        "You own every item labelled `security`, approve its plan and keep the security check",
        "Where the crew's `t2_panel` names a `security` lens, keep its question file current",
        "Never hold up a two-way diff that touches auth; the panel's verdict is enough there.",
        "keep its question file current and sample every 5th verdict post hoc.",
        "A card hit (`trust-loosening`, `money-path`, `brake-review`) is signed after the panel "
        "and before auto-merge by a fresh worker its master starts with this card",
        "the card version (`worker-dispatch.md` § Card worker). A case without precedent it "
        "escalates to you undecided",
    ):
        assert phrase in card, phrase


@pytest.mark.parametrize(
    "data",
    [None, json.loads(SECURITY.read_text()), DEFAULTS_ONLY],
    ids=["generic", "bound", "defaults"],
)
@pytest.mark.parametrize("kind", ["full", "worker"])
def test_every_crew_keeps_the_l0_within_the_budget_with_the_reserve(data, kind):
    crew = generic() if data is None else crewlib._merge(data)
    assert rp.l0_chars(crew, kind) <= rp.BUDGET
    assert rp.l0_chars(crewlib.fallback(None, "x"), kind) <= rp.BUDGET


def test_all_roles_prints_a_security_row(tmp_path):
    repo = crew_repo(tmp_path, json.loads(SECURITY.read_text()))
    for workplace in ("biz", "infra"):
        (tmp_path / workplace).mkdir()
    out = run("--all-roles", "--from", str(repo))
    assert out.returncode == 0, out.stderr
    rows = {line.split("\t")[0]: line.split("\t") for line in out.stdout.splitlines()}
    assert rows["security"][-1] == "ok"
    assert all(r[-1] == "ok" for r in rows.values())


ALL_BOUND = HERE / "fixtures" / "crew-v2-all-bound.json"
# red arm: ``L0_BUDGET_REF=<ref>`` renders ``we/process/L0.md`` as it stood on that git ref
L0_BUDGET_REF = os.environ.get("L0_BUDGET_REF", "")


def all_bound() -> dict:
    return crewlib._merge(json.loads(ALL_BOUND.read_text()))


@pytest.fixture(autouse=True)
def _all_bound_human(monkeypatch):
    """The all-bound crew names three humans; its sessions render for the one with most roles."""
    monkeypatch.setenv("WE_HUMAN", "hale")


def _l0_from_ref(tmp_path: Path) -> Path:
    """``rp.PROCESS``, or a copy of it holding ``L0.md`` from ``L0_BUDGET_REF``."""
    if not L0_BUDGET_REF:
        return rp.PROCESS
    shown = subprocess.run(
        ["git", "-C", str(HERE), "show", f"{L0_BUDGET_REF}:we/process/L0.md"],
        capture_output=True,
        text=True,
        check=True,
    )
    process = tmp_path / "process"
    shutil.copytree(rp.PROCESS, process)
    (process / "L0.md").write_text(shown.stdout, encoding="utf-8")
    return process


def l0_overrun(crew: dict, process: Path) -> str | None:
    """None when both L0 forms of ``crew``, measured as ``rp.l0_chars`` measures them (render
    without the notice plus the ``NOTICE_CHARS`` reserve), fit ``rp.BUDGET``; else the overrun."""
    clean = {**crew, "crew_error": None, "unknown_keys": []}
    for kind in ("full", "worker"):
        chars = len(rp.render_l0(clean, kind, process=process)) + rp.NOTICE_CHARS
        if chars > rp.BUDGET:
            return f"{kind} L0 with every role bound: {chars} > BUDGET {rp.BUDGET} chars"
    return None


def test_the_all_bound_fixture_binds_every_optional_line():
    """Each line that drops or shrinks when a crew leaves something unbound renders here: every
    role key (``OPTIONAL_ROLE_KEYS`` included), specialists, the T2 second reviewer, local rules
    and a value for every ``{key|fallback}`` token, so no fallback text stands in."""
    crew = all_bound()
    for role in crewlib.ROLE_KEYS:
        assert crewlib.holder_name(crew, role), role
    assert set(crewlib.OPTIONAL_ROLE_KEYS) <= set(crewlib.ROLE_KEYS)
    assert len(rp.specialist_members(crew)) >= 4
    assert rp._second_reviewer(crew) and rp._local_rules(crew)
    template = (rp.PROCESS / "L0.md").read_text(encoding="utf-8")
    for match in rp.TOKEN.finditer(template):
        key = match.group(1)
        if key == "single":  # the one-human arm: dropped in a crew with humans, like this one
            assert rp._resolve({**crew, "humans": {}}, key) == "", key
        elif key != "crew_notice":
            assert rp._resolve(crew, key), key


def test_the_l0_fits_the_budget_with_every_role_bound(tmp_path):
    """A bound optional role adds its lines (7.71.0 put the security owner's L0 over ``BUDGET``,
    and ``process_on_start`` then loads no L0 at all); the unbound fixtures cannot see that."""
    process = _l0_from_ref(tmp_path)
    for crew in (all_bound(), {**all_bound(), "humans": {}}):  # both arms of the human line
        overrun = l0_overrun(crew, process)
        assert overrun is None, overrun


def test_the_bound_budget_check_goes_red_with_its_number(tmp_path):
    """Red arm: the L0 grown by one character past the fixture's headroom fails with the count."""
    process = tmp_path / "process"
    shutil.copytree(rp.PROCESS, process)
    crew = all_bound()
    headroom = rp.BUDGET - rp.l0_chars(crew, "full")
    text = (process / "L0.md").read_text(encoding="utf-8")
    (process / "L0.md").write_text(text + "x" * (headroom + 1), encoding="utf-8")
    assert l0_overrun(crew, process) == (
        f"full L0 with every role bound: {rp.BUDGET + 1} > BUDGET {rp.BUDGET} chars"
    )


# The brake's core: a diff to the classifier, the gates, the review workflows, the crew's `risk`
# block or one that removes a rule is `brake-change` (`risk_paths.CORE`), never self-merged. The
# review workflows are named apart from the gates: a crew's `[brake-change]` lists them as paths of
# their own. Rules live only in the rules file, so the bundled classifier sees a removed rule as a
# change to that file, which the setup template puts under `[brake-change]`; a crew's own
# `risk.command` may narrow it to removed lines.
BRAKE_CORE = "brake core (classifier, gates, review workflows, removed rules, crew `risk`)."


@pytest.mark.parametrize(
    "data", [None, json.loads(ALL_BOUND.read_text())], ids=["generic", "bound"]
)
def test_l0_names_every_part_of_the_brake_core(data):
    crew = generic() if data is None else crewlib._merge(data)
    assert BRAKE_CORE in rp.render_l0(crew)


def test_the_setup_template_classifies_a_removed_rule_as_brake_core():
    """L0's "removed rules" holds for the bundled classifier: the rules file is a core path."""
    import risk_paths  # noqa: PLC0415

    rules = risk_paths.parse_rules((HERE.parent / "templates" / "risk-paths").read_text())
    assert risk_paths.CORE == ("brake-change",)
    assert any(p.fullmatch(".weside/risk-paths") for _, p in rules["brake-change"])


def test_the_setup_template_classifies_a_review_workflow_as_brake_core():
    """L0's "review workflows" holds for the bundled classifier: both usual review workflow names are
    core paths, the review helpers beside them (skip gate, runner image) are not."""
    import risk_paths  # noqa: PLC0415

    rules = risk_paths.parse_rules((HERE.parent / "templates" / "risk-paths").read_text())
    core = [p for _, p in rules["brake-change"]]
    for name in ("claude-code-review.yml", "codex-code-review.yml"):
        assert any(p.fullmatch(f".github/workflows/{name}") for p in core), name
    for name in ("codex-review-skip.yml", "build-codex-review-runner.yml", "ci.yml"):
        assert not any(p.fullmatch(f".github/workflows/{name}") for p in core), name


def test_the_subagent_fallback_lives_in_the_cards_not_in_l0():
    """L0 keeps the principle (a subagent never builds); the opt-in exception sits in the master
    and worker cards, each pointing at its reference."""
    crew = all_bound()
    l0 = rp.render_l0(crew)
    assert "A subagent reads and reviews, never builds." in l0
    assert "subagent_fallback" not in l0
    for role in ("master", "worker"):
        card = rp.render_card(crew, role)
        assert "launch.subagent_fallback" in card, role
        assert "`worker-dispatch.md` § Worker launch backend" in card, role


# --- several humans: names per human, the human line, the humans part after the card ----------


def test_several_humans_render_per_human(monkeypatch):
    crew = all_bound()
    monkeypatch.setenv("WE_HUMAN", "marisol")
    l0 = rp.render_l0(crew)
    assert "- **Marisol** decides product direction on this machine;" in l0
    assert "and whatever else they choose" not in l0
    # decider sentences name the deciding human, not the local one
    assert "| T3 company | Hale," in l0 and "| T3 company | Marisol" not in l0
    assert "Adalinde" in l0 and "Ada " not in l0.replace("Adalinde", "")
    part = rp.humans_part(crew, "product")
    assert part.startswith("**Several humans** (this crew; you work for Marisol)")
    assert (
        "- **Quentin** (`quentin`): owns Done; decides domain, acceptance; runs acceptance."
        in part
    )
    assert "Adalinde moves a story to Selected only with `board.py select <KEY>`" in part
    assert rp.humans_part(crew, "worker") is None
    card = rp.render_card(crew, "product")
    assert "a ticket labelled for Marisol asks Marisol" in card
    assert "never answer it yourself" in card and "answer each ticket" not in card


def test_a_human_who_decides_nothing_claims_no_decision(monkeypatch):
    crew = all_bound()
    crew["humans"]["marisol"]["decides"] = []
    monkeypatch.setenv("WE_HUMAN", "marisol")
    l0 = rp.render_l0(crew)
    assert "on this machine; other humans" not in l0
    assert "Marisol** decides vision" not in l0


def test_inbox_lines_name_the_local_human_decider_lines_the_deciding_one(monkeypatch):
    """Red arm: on Marisol's machine the board is Marisol's inbox and her coordinator carries
    her questions, while T3, prod and the core merges stay with the deciding human (Hale)."""
    crew = all_bound()
    monkeypatch.setenv("WE_HUMAN", "marisol")
    l0 = rp.render_l0(crew)
    assert "The board is Marisol's only inbox" in l0 and "Hale's only inbox" not in l0
    assert "carries what goes to Marisol," in l0
    assert "| T3 company | Hale," in l0
    assert "Prod ships an accepted RC's commit, only on Hale's word" in l0
    coord = rp.render_card(crew, "coordinator")
    assert "Questions for Marisol reach you" in coord and "Never answer for Marisol;" in coord
    assert "native build needs Hale's word" in coord
    sec = rp.render_card(crew, "security")
    assert "every human's personal data" in sec
    assert "a question for Marisol goes to" in rp.render_l0(crew, "worker")


def test_in_test_lines_only_for_a_crew_that_maps_in_test():
    """A crew without board.states.in_test (weside-core) renders no In Test line; one that maps it
    gets the move and the Done rule (red arm: the mapped crew's lines)."""
    plain = generic()
    for role in ("product", "acceptance", "master"):
        assert "in_test" not in rp.render_card(plain, role)
        assert "In Test" not in rp.render_card(plain, role)
    assert "Never mark a story Done; acceptance does that" in rp.render_card(plain, "product")
    mapped = crewlib._merge(
        {**json.loads(GENERIC.read_text()), "board": {"states": {"in_test": "In Test"}}}
    )
    assert "`board.py move <KEY> in_test` from In Review" in rp.render_card(mapped, "acceptance")
    product = rp.render_card(mapped, "product")
    assert "unless your human owns In Test" in product
    assert "Never mark a story Done; acceptance does that" not in product


def test_one_human_renders_as_before():
    crew = generic()
    l0 = rp.render_l0(crew)
    assert "and whatever else they choose, and talks to any companion directly." in l0
    assert "on this machine; other humans" not in l0
    assert rp.humans_part(crew, "coordinator") is None
    assert "Several humans" not in rp.render_card(crew, "coordinator")
    assert "Several humans" not in rp.render_card(crew, "product")
