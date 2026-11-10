"""role_on_start.py: the role card with its addendum, extra repo heads and hooks within the
budget, byte-identical card part on every source, and nothing without a crew or a role."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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
        if k
        not in (
            "WE_ROLE",
            "WESIDE_COMPANION",
            "CLAUDE_CODE_SESSION_ID",
            "CLAUDE_CONFIG_DIR",
            "CLAUDE_PLUGIN_ROOT",
            "WE_STATE_DIR",
        )
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


def test_the_pinned_security_holder_gets_the_security_card(tmp_path):
    data = json.loads((SCRIPTS / "fixtures" / "crew-v2-security.json").read_text())
    _, infra = workspace(tmp_path, data)
    repo = infra.parent / "repo"
    for source in ("startup", "compact"):
        text = context(run(tmp_path, repo, {"WESIDE_COMPANION": "Bo"}, source=source))
        assert text is not None and text.startswith("# Role card: security"), source
        assert "trust-loosening" in text and "# Role card: specialist" not in text


def test_nothing_without_a_crew_or_without_a_role(tmp_path):
    bare = tmp_path / "bare"
    subprocess.run(["git", "init", "-q", str(bare)], check=True)
    assert context(run(tmp_path, bare, {"WE_ROLE": "master"})) is None
    repo, _ = workspace(tmp_path)
    assert context(run(tmp_path, repo, {})) is None, "no role: nothing"


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
        assert master is not None, f"{source}: a refused crew printed nothing"
        assert master.startswith("# Role card: master"), source
        assert "Repo addendum for masters." in master
        assert V1_LINE in master.split("\n")
        worker = context(run(tmp_path, repo, {"WE_ROLE": "worker"}, source=source))
        assert worker.startswith("# Role card: worker") and V1_LINE in worker.split("\n")
        pin = context(run(tmp_path, repo, {"WESIDE_COMPANION": "Kit"}, source=source))
        assert pin == V1_LINE, source
        unnamed = context(run(tmp_path, repo, {}, source=source))
        assert unnamed == V1_LINE, source
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


def test_no_session_is_pointed_at_a_deleted_working_mode_reference(tmp_path):
    """The working-mode reference is gone (its rules are the L0 and the cards): a session with a
    role gets its card without a pointer line, a session without a role gets nothing."""
    repo, infra = workspace(tmp_path)
    for cwd, env in (
        (infra, {"WESIDE_COMPANION": "Kit"}),
        (repo, {"WE_ROLE": "master"}),
        (repo, {"WE_ROLE": "worker"}),
    ):
        text = context(run(tmp_path, cwd, env))
        assert text is not None and text.startswith("# Role card:"), env
        assert "working-mode" not in text and "before routing" not in text, env
        assert len(text) <= render_process.BUDGET, env
    assert context(run(tmp_path, repo, {})) is None


# --- two crews, AC3: a state directory two crews resolve -----------------------------------------


def _second_crew(tmp_path: Path, name: str, **top) -> Path:
    repo = tmp_path / name
    (repo / ".weside").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", f"git@github.com:acme/{name}.git"],
        check=True,
    )
    data = json.loads(GENERIC.read_text())
    data.update(top)
    (repo / ".weside" / "crew.json").write_text(json.dumps(data))
    return repo


def test_the_second_crew_on_a_held_state_dir_gets_one_collision_note(tmp_path):
    first = _second_crew(tmp_path, "crew-one")
    second = _second_crew(tmp_path, "crew-two")
    master = {"WE_ROLE": "master"}
    assert "state dir" not in (context(run(tmp_path, first, master)) or "")
    stamp = tmp_path / "home" / ".claude" / "we-state" / "crew.id"
    assert stamp.read_text().strip() == "acme/crew-one"
    text = context(run(tmp_path, second, master)) or ""
    assert text.count("is held by crew acme/crew-one") == 1
    assert "this crew acme/crew-two" in text and "`state_dir`" in text
    # the first crew again, and the second crew once it has its own folder: silent
    assert "state dir" not in (context(run(tmp_path, first, master)) or "")
    data = json.loads((second / ".weside" / "crew.json").read_text())
    data["state_dir"] = "~/.claude/we-state/two"
    (second / ".weside" / "crew.json").write_text(json.dumps(data))
    assert "state dir" not in (context(run(tmp_path, second, master)) or "")


def test_a_crew_with_a_board_file_of_its_own_shares_the_folder_silently(tmp_path):
    """Review 09.11. (colenet): its board family is named after its own file, nothing collides."""
    first = _second_crew(tmp_path, "crew-one")
    second = _second_crew(
        tmp_path, "crew-two", board={"file": "~/.claude/we-state/two-board.json"}
    )
    master = {"WE_ROLE": "master"}
    run(tmp_path, first, master)
    assert "state dir" not in (context(run(tmp_path, second, master)) or "")


def test_another_worktree_or_a_pointer_of_the_same_crew_prints_nothing(tmp_path):
    first = _second_crew(tmp_path, "crew-one")
    master = {"WE_ROLE": "master"}
    context(run(tmp_path, first, master))
    tree = tmp_path / "crew-one-wt"
    subprocess.run(
        ["git", "-C", str(first), "commit", "-q", "--allow-empty", "-m", "x"],
        check=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )
    subprocess.run(["git", "-C", str(first), "worktree", "add", "-q", str(tree)], check=True)
    (tree / ".weside").mkdir(exist_ok=True)
    shutil.copy(first / ".weside" / "crew.json", tree / ".weside" / "crew.json")
    pointer = tmp_path / "side"
    (pointer / ".weside").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(pointer)], check=True)
    (pointer / ".weside" / "config.json").write_text(
        json.dumps({"crew": "../crew-one/.weside/crew.json"})
    )
    for where in (tree, pointer):
        assert "state dir" not in (context(run(tmp_path, where, master)) or "")


# --- two crews, AC6: a plugin older than the user install, pinned by a project-scope install -----

INSTALLED = (
    Path(__file__).resolve().parent.parent / "scripts" / "fixtures" / "installed-plugins.json"
)


def _plugin_root(tmp_path: Path, version: str) -> Path:
    root = tmp_path / f"plugin-{version}"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": version}))
    return root


def _config(tmp_path: Path, project: Path | None, scope: str = "project") -> Path:
    data = json.loads(INSTALLED.read_text())
    for row in data["plugins"]["we@acme-market"]:
        if row["scope"] == "project":
            row["projectPath"] = str(project or tmp_path / "elsewhere")
            row["scope"] = scope
    config = tmp_path / "config"
    (config / "plugins").mkdir(parents=True)
    (config / "plugins" / "installed_plugins.json").write_text(json.dumps(data))
    return config


@pytest.mark.parametrize(
    "running, project, said",
    [
        ("8.6.1", True, True),  # older, a project entry holds the cwd: one note
        ("9.1.0", True, False),  # equal to the newest user install
        ("8.6.1", False, False),  # no project entry for this directory
    ],
)
def test_an_old_plugin_pinned_by_a_project_install_names_both_versions(
    tmp_path, running, project, said
):
    repo, _ = workspace(tmp_path)
    env = {
        "WE_ROLE": "master",
        "CLAUDE_PLUGIN_ROOT": str(_plugin_root(tmp_path, running)),
        "CLAUDE_CONFIG_DIR": str(_config(tmp_path, repo.parent if project else None)),
    }
    text = context(run(tmp_path, repo, env)) or ""
    if said:
        assert text.count(f"plugin we {running} runs here, the user install is 9.1.0") == 1
        assert f"project-scope install for {repo.parent}" in text
        assert "claude plugin update we@weside-ai --scope project" in text
    else:
        assert "plugin we " not in text


def test_an_unreadable_installed_plugins_file_prints_nothing(tmp_path):
    repo, _ = workspace(tmp_path)
    config = tmp_path / "config"
    (config / "plugins").mkdir(parents=True)
    (config / "plugins" / "installed_plugins.json").write_text("{not json")
    env = {
        "WE_ROLE": "master",
        "CLAUDE_PLUGIN_ROOT": str(_plugin_root(tmp_path, "8.6.1")),
        "CLAUDE_CONFIG_DIR": str(config),
    }
    assert "plugin we " not in (context(run(tmp_path, repo, env)) or "")


def test_a_local_scope_install_counts_like_a_project_one(tmp_path):
    repo, _ = workspace(tmp_path)
    env = {
        "WE_ROLE": "master",
        "CLAUDE_PLUGIN_ROOT": str(_plugin_root(tmp_path, "8.6.1")),
        "CLAUDE_CONFIG_DIR": str(_config(tmp_path, repo.parent, scope="local")),
    }
    assert "plugin we 8.6.1 runs here" in (context(run(tmp_path, repo, env)) or "")
