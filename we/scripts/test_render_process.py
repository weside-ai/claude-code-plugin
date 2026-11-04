"""render_process.py: the L0 template filled from a crew, the worker short form, the role totals
and the ``--serves`` predicate."""

from __future__ import annotations

import json
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
    full = run("--role", "master", "--from", str(repo))
    assert full.returncode == 0 and full.stdout == rp.render_l0(generic())
    sizes = run("--all-roles", "--from", str(repo))
    assert sizes.returncode == 0
    roles = [line.split("\t")[0] for line in sizes.stdout.splitlines()]
    assert roles == list(rp.all_roles())
    assert all(line.endswith("\tok") for line in sizes.stdout.splitlines())


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
    [(label, rows, total)] = rp.total_rows(core / ".weside" / "crew.json", crew, "machinery", home)
    assert label == "machinery Kit"
    parts = {(part, Path(path).name) for part, path, _ in rows}
    assert ("extra", "AGENTS.md") not in parts and ("rules", "c.md") not in parts
    assert ("rules-any-file", "d.md") in parts and ("extra", "CLAUDE.md") in parts
    l0 = len(rp.render_l0(crew))
    hook = {p: n for p, _, n in rows}["plugin-hook"]
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
