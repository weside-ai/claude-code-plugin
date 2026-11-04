"""role_on_start.py: the role card with its addendum, extra repo heads and hooks within the
budget, byte-identical card part on every source, and nothing without a crew or a role."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "role_on_start.py"
SCRIPTS = HOOK.parent.parent / "scripts"
GENERIC = SCRIPTS / "fixtures" / "crew-v2-generic.json"
sys.path.insert(0, str(SCRIPTS))

import render_process  # noqa: E402

SOURCES = ("startup", "resume", "clear", "compact")
LOUD = "for i in $(seq 1 120); do printf '%099d\\n' $i; done"
ADDENDUM = "Local notes for this member: the release lane is Tuesday."


def workspace(tmp_path: Path, data: dict | None = None) -> tuple[Path, Path]:
    """(crew repo, infra): the crew repo is the machinery member's extra repo, with an AGENTS.md
    and a SessionStart command that prints 12,000 chars; infra is its workplace."""
    ws = tmp_path / "ws"
    repo, infra = ws / "repo", ws / "infra"
    for root in (repo, infra, ws / "biz"):
        (root / ".weside").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
    if data is None:
        shutil.copy(GENERIC, repo / ".weside" / "crew.json")
    else:
        (repo / ".weside" / "crew.json").write_text(json.dumps(data))
    (infra / ".weside" / "config.json").write_text(
        json.dumps({"crew": "../repo/.weside/crew.json"})
    )
    (infra / ".weside" / "roles").mkdir()
    (infra / ".weside" / "roles" / "kit.md").write_text(ADDENDUM + "\n")
    (repo / "AGENTS.md").write_text("# Repo\n\nHead line one.\n\n## Later\n\nnot in the head\n")
    hooks = {"SessionStart": [{"hooks": [{"type": "command", "command": LOUD}]}]}
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text(json.dumps({"hooks": hooks}))
    return repo, infra


def run(tmp_path: Path, cwd: Path, env_extra: dict, **hook_input) -> subprocess.CompletedProcess:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("WE_ROLE", "WESIDE_COMPANION", "CLAUDE_CODE_SESSION_ID")
    }
    env.update({"HOME": str(tmp_path / "home"), **env_extra})
    data = {"session_id": "sid-1", "source": "startup", "cwd": str(cwd), **hook_input}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(data),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def context(done: subprocess.CompletedProcess) -> str | None:
    assert done.returncode == 0, done.stderr
    if not done.stdout:
        return None
    return json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]


def test_a_pinned_member_gets_card_addendum_head_and_the_cut_hook_on_every_source(tmp_path):
    repo, infra = workspace(tmp_path)
    texts = {}
    for source in SOURCES:
        text = context(run(tmp_path, infra, {"WESIDE_COMPANION": "Kit"}, source=source))
        assert text is not None and len(text) <= render_process.BUDGET, source
        assert text.startswith("# Role card: machinery")
        assert ADDENDUM in text
        assert "# Repo\n\nHead line one." in text and "not in the head" not in text
        assert text.rstrip().endswith(f"… cut, full output: {LOUD} in {repo.resolve()}")
        texts[source] = text
    card_parts = {s: t.split("\n\nExtra repo ", 1)[0] for s, t in texts.items()}
    assert len(set(card_parts.values())) == 1, "card and addendum differ between sources"


def test_each_session_kind_gets_its_card(tmp_path):
    _, infra = workspace(tmp_path)
    repo = infra.parent / "repo"
    cases = [
        ({"WE_ROLE": "master"}, "# Role card: master"),
        ({"WE_ROLE": "worker"}, "# Role card: worker"),
        ({"WESIDE_COMPANION": "Bo"}, "# Role card: specialist"),
        ({"WESIDE_COMPANION": "Otto"}, "# Role card: coordinator"),
    ]
    for env, head in cases:
        text = context(run(tmp_path, repo, env))
        assert text is not None and text.startswith(head), env


def test_nothing_without_or_with_a_refused_crew_only_the_pointer_without_a_role(tmp_path):
    bare = tmp_path / "bare"
    subprocess.run(["git", "init", "-q", str(bare)], check=True)
    assert context(run(tmp_path, bare, {"WE_ROLE": "master"})) is None
    repo, _ = workspace(tmp_path)
    pointer = context(run(tmp_path, repo, {}))
    assert pointer is not None and pointer.startswith("Read "), "no role: only the pointer"
    assert "# Role card" not in pointer


V1_LINE = (
    "crew.json not readable: crew.json is version 1: in a worktree, merge the default branch; "
    "otherwise run /we:setup"
)


def test_a_refused_crew_gets_the_default_card_with_the_reason_never_nothing(tmp_path):
    repo, infra = workspace(tmp_path)
    (repo / ".weside" / "roles").mkdir()
    (repo / ".weside" / "roles" / "master.md").write_text("Repo addendum for masters.\n")
    (repo / ".weside" / "crew.json").write_text(json.dumps({"version": 1, "roles": {}}))
    for source in SOURCES:
        master = context(run(tmp_path, repo, {"WE_ROLE": "master"}, source=source))
        assert master.startswith("# Role card: master"), source
        assert "Repo addendum for masters." in master
        assert V1_LINE in master.split("\n") and master.endswith(render_process.POINTER)
        assert master.index(V1_LINE) < master.index(render_process.POINTER)
        worker = context(run(tmp_path, repo, {"WE_ROLE": "worker"}, source=source))
        assert worker.startswith("# Role card: worker") and V1_LINE in worker.split("\n")
        pin = context(run(tmp_path, repo, {"WESIDE_COMPANION": "Kit"}, source=source))
        assert pin == f"{V1_LINE}\n\n{render_process.POINTER}", source
    data = json.loads(GENERIC.read_text())
    data["labels"]["crew_unreadable"] = "crew.json nicht lesbar"
    data["limits"] = {"masters": "five"}
    (repo / ".weside" / "crew.json").write_text(json.dumps(data))
    text = context(run(tmp_path, infra, {"WE_ROLE": "master"}))
    path = repo / ".weside" / "crew.json"
    line = f"crew.json nicht lesbar: {path.resolve()}: limits.masters must be a number"
    assert line in text.split("\n"), text[-400:]


def test_card_plus_addendum_over_the_budget_prints_nothing_and_names_the_addendum(tmp_path):
    _, infra = workspace(tmp_path)
    addendum = infra / ".weside" / "roles" / "kit.md"
    addendum.write_text("x" * 9_000)
    done = run(tmp_path, infra, {"WESIDE_COMPANION": "Kit"})
    assert done.returncode == 1 and done.stdout == ""
    assert len(done.stderr.strip().splitlines()) == 1
    assert str(addendum.resolve()) in done.stderr


def test_a_missing_extra_repo_is_skipped_by_name_and_the_card_still_loads(tmp_path):
    """One of the member's extra repos is not cloned here: the card, the addendum and the present
    extra repo still load on every source, plus one line naming the missing repo."""
    data = json.loads(GENERIC.read_text())
    data["members"]["kit"]["extra_repos"] = [".", "../absent"]
    _, infra = workspace(tmp_path, data)
    for source in SOURCES:
        text = context(run(tmp_path, infra, {"WESIDE_COMPANION": "Kit"}, source=source))
        assert text is not None, source
        assert text.startswith("# Role card: machinery") and ADDENDUM in text, source
        assert "extra repo ../absent not found, skipped" in text, source
        assert "Head line one." in text and len(text) <= render_process.BUDGET, source


def test_every_crew_session_is_pointed_at_the_working_mode_reference(tmp_path):
    repo, infra = workspace(tmp_path)
    reference = (HOOK.parent.parent / "references" / "working-mode.md").resolve()
    assert reference.is_file()
    line = f"Read {reference} before routing, starting a session or moving a ticket."
    for cwd, env in (
        (infra, {"WESIDE_COMPANION": "Kit"}),
        (repo, {"WE_ROLE": "master"}),
        (repo, {"WE_ROLE": "worker"}),
        (repo, {}),
    ):
        text = context(run(tmp_path, cwd, env))
        assert text is not None and line in text.split("\n"), env
        assert len(text) <= render_process.BUDGET, env
