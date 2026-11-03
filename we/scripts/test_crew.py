"""crew.py: lookup with the config pointer, the v2 schema (validation, defaults, transition keys),
member and role lookup, skill paths, stubs, workplace and lenses."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import crew
import pytest

SCRIPT = Path(__file__).resolve().parent / "crew.py"
TRANSITION = Path(__file__).resolve().parent / "fixtures" / "crew-v2-transition.json"
VERSION_1 = (
    "crew.json is version 1: in a worktree, merge the default branch; otherwise run /we:setup"
)

CREW = {
    "version": 2,
    "skill_prefix": "acme",
    "question_label": "ASK",
    "roles": {"product": "ada", "coordinator": "otto", "hr": "hana", "acceptance": "tess"},
    "members": {
        "ada": {"name": "Ada", "components": ["App"], "workplace": "."},
        "otto": {"name": "Otto", "workplace": "."},
        "hana": {"name": "Hana", "workplace": "../biz"},
        "tess": {"name": "Tess", "workplace": ".", "on_call": False},
        "lex": {"name": "Lex", "specialist": "legal", "workplace": "../biz", "on_call": True},
    },
}


def workspace(tmp_path: Path, crew_data: dict | None = None) -> tuple[Path, Path]:
    core, biz = tmp_path / "core", tmp_path / "biz"
    (core / ".weside").mkdir(parents=True)
    (biz / ".weside").mkdir(parents=True)
    (core / ".weside" / "crew.json").write_text(
        json.dumps(CREW if crew_data is None else crew_data)
    )
    (biz / ".weside" / "config.json").write_text(json.dumps({"crew": "../core/.weside/crew.json"}))
    return core, biz


def test_find_walks_up_and_follows_the_pointer(tmp_path):
    core, biz = workspace(tmp_path)
    (biz / "deep" / "dir").mkdir(parents=True)
    assert crew.find(core / ".weside") == core / ".weside" / "crew.json"
    assert crew.find(biz / "deep" / "dir") == (core / ".weside" / "crew.json").resolve()


def test_no_crew_and_a_dangling_pointer_find_nothing(tmp_path):
    assert crew.find(tmp_path) is None
    (tmp_path / ".weside").mkdir()
    (tmp_path / ".weside" / "config.json").write_text(json.dumps({"crew": "../gone.json"}))
    assert crew.find(tmp_path) is None


def test_member_and_holder(tmp_path):
    assert crew.member(CREW, "lex")[1]["name"] == "Lex"
    assert crew.member(CREW, "ADA")[0] == "ada"
    assert crew.member(CREW, "nobody") is None
    assert crew.holder_name(CREW, "coordinator") == "Otto"
    assert crew.holder_name({"members": {}}, "hr") is None


def test_skill_path_loadable_before_workplace(tmp_path):
    core, biz = workspace(tmp_path)
    home = tmp_path / "home"
    skill = biz / ".claude" / "skills" / "acme-hana" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: acme-hana\n---\n")
    path, loadable = crew.skill_path("Hana", core, home=home)
    assert (path, loadable) == (skill.resolve(), False)
    path, loadable = crew.skill_path("Hana", biz, home=home)
    assert loadable is True and path == biz / ".claude" / "skills" / "acme-hana" / "SKILL.md"
    assert crew.skill_path("Lex", core, home=home) is None


def test_skill_path_without_crew_uses_the_default_prefix(tmp_path):
    skill = tmp_path / ".claude" / "skills" / "weside-otto" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("x")
    assert crew.skill_path("Otto", tmp_path, home=tmp_path / "h") == (skill, True)
    assert crew.skill_path("../x", tmp_path, home=tmp_path / "h") is None


def test_stubs_write_once_and_never_overwrite(tmp_path):
    core, biz = workspace(tmp_path)
    path = core / ".weside" / "crew.json"
    pending = crew.stubs(path, CREW)
    assert len(pending) == 5 and not any(Path(p).exists() for p in pending)
    written = crew.stubs(path, CREW, write=True)
    assert written == pending
    lex = biz / ".claude" / "skills" / "acme-lex" / "SKILL.md"
    text = lex.read_text()
    assert crew.is_stub(lex)
    assert (
        "name: acme-lex" in text
        and "# Lex · legal" in text
        and "tell Otto in one line (for HR)" in text
    )
    assert "{{" not in text
    lex.write_text("filled")
    assert crew.stubs(path, CREW, write=True) == []
    assert lex.read_text() == "filled"


def test_cli_show_members_and_skill_path(tmp_path):
    core, biz = workspace(tmp_path)

    def cli(*args, cwd=core):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )

    shown = json.loads(cli("show", cwd=biz).stdout)
    assert shown["roles"]["coordinator"] == "otto" and shown["question_label"] == "ASK"
    assert shown["members"]["lex"]["on_call"] is True
    assert shown["skill_prefix"] == "acme" and shown["weside_account"] is False
    lines = cli("members").stdout.splitlines()
    assert lines[0] == "Ada\tproduct" and lines[-1] == "Lex\tlegal"
    assert cli("path", cwd=tmp_path).returncode == 1
    cli("stubs", "--write")
    out = cli("skill-path", "Lex", "--cwd", str(core)).stdout.strip().split("\t")
    assert out[1:] == ["workplace", "stub"]


def test_broken_crew_is_an_error(tmp_path):
    (tmp_path / ".weside").mkdir()
    (tmp_path / ".weside" / "crew.json").write_text('{"version": 2, "roles": {}, "members": []}')
    try:
        crew.find_and_load(tmp_path)
    except crew.CrewError as exc:
        assert "members" in str(exc)
    else:
        raise AssertionError("expected CrewError")


def test_find_stops_at_the_repo_root(tmp_path):
    (tmp_path / ".weside").mkdir()
    (tmp_path / ".weside" / "crew.json").write_text(json.dumps(CREW))
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "src").mkdir()
    assert crew.find(repo / "src") is None
    assert crew.find(tmp_path / "other") == tmp_path / ".weside" / "crew.json"


def test_session_kind():
    assert crew.session_kind({"WE_ROLE": "worker"}) == ("worker", "")
    assert crew.session_kind({"WESIDE_COMPANION": "Eva", "WE_ROLE": "worker"}) == (
        "consult",
        "Eva",
    )
    assert crew.session_kind({"WESIDE_COMPANION": "Eva"}) == ("named", "Eva")
    assert crew.session_kind({"WESIDE_COMPANION": "Eva", "WE_ROLE": "master"}) == ("named", "Eva")
    assert crew.session_kind({"WE_ROLE": "master"}) == ("unnamed", "")
    assert crew.session_kind({}) == ("unnamed", "")
    assert crew.session_kind({"WESIDE_COMPANION": "Eva"}, agent_type="x") == ("worker", "")


def test_holds_role_and_cli(tmp_path):
    core, _biz = workspace(tmp_path)
    assert crew.holds_role(CREW, "coordinator", {"WESIDE_COMPANION": "Otto", "WE_ROLE": "master"})
    assert crew.holds_role(CREW, "coordinator", {"WESIDE_COMPANION": "otto"})
    assert not crew.holds_role(
        CREW, "coordinator", {"WESIDE_COMPANION": "Otto", "WE_ROLE": "worker"}
    )
    assert not crew.holds_role(CREW, "coordinator", {"WESIDE_COMPANION": "Ada"})
    assert not crew.holds_role(CREW, "coordinator", {"WE_ROLE": "master"})

    def cli(env):
        base = {k: v for k, v in os.environ.items() if k not in ("WESIDE_COMPANION", "WE_ROLE")}
        return subprocess.run(
            [sys.executable, str(SCRIPT), "is-role", "coordinator"],
            cwd=core,
            env={**base, **env},
            capture_output=True,
            check=False,
        ).returncode

    assert cli({"WESIDE_COMPANION": "Otto"}) == 0
    assert cli({"WESIDE_COMPANION": "Ada"}) == 1
    assert cli({}) == 1


def test_a_process_worker_is_a_worker_whatever_its_environment(tmp_path):
    repo = tmp_path / "wt"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    git_dir = repo / ".git"
    env = {"WESIDE_COMPANION": "Eva", "WE_ROLE": "master"}
    payload = {"cwd": str(repo), "session_id": "s-w"}
    assert crew.session_kind(env, hook_input=payload) == ("named", "Eva")
    (git_dir / "we-worker.json").write_text(json.dumps({"name": "w1"}))
    assert crew.session_kind(env, hook_input=payload) == ("worker", "")
    (git_dir / "we-worker.json").write_text(json.dumps({"name": "w1", "session_id": "s-w"}))
    assert crew.session_kind(env, hook_input=payload) == ("worker", "")
    (git_dir / "we-worker.json").write_text(json.dumps({"name": "w1", "session_id": "other"}))
    assert crew.session_kind(env, hook_input=payload) == ("named", "Eva")


def test_lookup_keeps_non_ascii_names_stubs_stay_strict():
    assert crew.skill_name("Zoë") == "weside-zoë"
    assert crew.skill_name("Zoë", strict=True) is None
    for bad in ("../x", "a/b", "a\\b", "two words", ""):
        assert crew.skill_name(bad) is None


def test_stub_frontmatter_survives_quotes_and_backslashes(tmp_path):
    odd = {
        "skill_prefix": "acme",
        "roles": {"coordinator": "otto"},
        "members": {
            "otto": {"name": "Otto"},
            "q": {"name": "Quinn", "title": 'Head of "Growth" \\ Sales', "workplace": "."},
        },
    }
    text = crew.render_stub(odd, "q")
    head = text.split("\n---", 1)[0]
    assert '(Head of \\"Growth\\" \\\\ Sales)' in head
    assert '# Quinn · Head of "Growth" \\ Sales' in text


def test_is_role_excludes_a_process_worker_by_session_and_reads_the_role_anywhere(tmp_path):
    core, _biz = workspace(tmp_path)
    subprocess.run(["git", "init", "-q", str(core)], check=True)
    base = {
        k: v
        for k, v in os.environ.items()
        if k not in ("WESIDE_COMPANION", "WE_ROLE", "CLAUDE_CODE_SESSION_ID")
    }
    env = {**base, "WESIDE_COMPANION": "Otto", "WE_ROLE": "master"}

    def cli(*args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "is-role", *args],
            cwd=core,
            env=env,
            capture_output=True,
            check=False,
        ).returncode

    assert cli("coordinator", "--session", "s1") == 0
    assert cli("--session", "s1", "coordinator") == 0
    (core / ".git" / "we-worker.json").write_text(json.dumps({"name": "w", "session_id": "s-w"}))
    assert cli("coordinator", "--session", "s-w") == 1  # the worker the marker names
    assert cli("coordinator") == 1  # no session id: the marker alone decides
    assert cli("coordinator", "--session", "s-lead") == 0  # the Lead working in the worker's tree


# --- v2 schema -------------------------------------------------------------------------------


def run(core: Path, *args: str, env: dict | None = None, isolated: bool = False):
    base = {k: v for k, v in os.environ.items() if k not in ("WESIDE_COMPANION", "WE_ROLE")}
    flags = ["-I"] if isolated else []
    return subprocess.run(
        [sys.executable, *flags, str(SCRIPT), *args, "--from", str(core)],
        capture_output=True,
        text=True,
        env={**base, **(env or {})},
        check=False,
    )


def with_(**changes) -> dict:
    data = json.loads(json.dumps(CREW))
    for dotted, value in changes.items():
        *parents, leaf = dotted.split("__")
        node = data
        for part in parents:
            node = node.setdefault(part, {})
        node[leaf] = value
    return data


@pytest.mark.parametrize(
    ("changes", "dotted"),
    [
        ({"limitz": 3}, "limitz"),
        ({"limits__masterz": 3}, "limits.masterz"),
        ({"members__ada__colour": "red"}, "members.ada.colour"),
        ({"lenses__product__questionz": "q.md"}, "lenses.product.questionz"),
    ],
)
def test_an_unknown_key_is_refused_by_name(tmp_path, changes, dotted):
    core, _ = workspace(tmp_path, with_(**changes))
    out = run(core, "show")
    assert out.returncode == 1
    assert f"unknown key {dotted}" in out.stderr


@pytest.mark.parametrize("version", [1, None])
@pytest.mark.parametrize(
    "verb", [["show"], ["members"], ["stubs"], ["is-role", "hr"], ["workplace", "ada"], ["lenses"]]
)
def test_a_version_1_file_is_refused_by_every_reading_verb(tmp_path, version, verb):
    data = with_(version=version)
    if version is None:
        del data["version"]
    core, _ = workspace(tmp_path, data)
    out = run(core, *verb)
    assert out.returncode == 1
    assert out.stderr.strip() == f"crew: {VERSION_1}"


@pytest.mark.parametrize(
    ("changes", "dotted"),
    [({"roles__boss": "ada"}, "roles.boss"), ({"roles__product": "nobody"}, "roles.product")],
)
def test_a_role_key_without_a_card_or_a_holder_without_a_member_is_refused(
    tmp_path, changes, dotted
):
    core, _ = workspace(tmp_path, with_(**changes))
    out = run(core, "show")
    assert out.returncode == 1 and dotted in out.stderr


@pytest.mark.parametrize(
    ("changes", "dotted"),
    [
        ({"files__dod": "docs/dod.md"}, "files.dod"),
        ({"lenses__architecture__registry": "docs/registry.md"}, "lenses.architecture.registry"),
        ({"lenses__product__questions": "docs/q.md"}, "lenses.product.questions"),
    ],
)
@pytest.mark.parametrize("verb", [["show"], ["lenses"], ["workplace", "ada"]])
def test_a_missing_path_is_refused_and_an_existing_one_passes(tmp_path, changes, dotted, verb):
    core, _ = workspace(tmp_path, with_(**changes))
    value = next(iter(changes.values()))
    out = run(core, *verb)
    assert out.returncode == 1 and dotted in out.stderr and value in out.stderr
    (core / value).parent.mkdir(parents=True, exist_ok=True)
    (core / value).write_text("x")
    assert run(core, *verb).returncode == 0


def test_show_carries_every_default_and_merges_one_level(tmp_path):
    minimal = {"version": 2, "roles": CREW["roles"], "members": CREW["members"]}
    core, _ = workspace(tmp_path, minimal)
    shown = json.loads(run(core, "show").stdout)
    for key, default in crew.DEFAULTS.items():
        assert shown[key] == default, key
    core.joinpath(".weside", "crew.json").write_text(json.dumps(with_(limits__masters=3)))
    limits = json.loads(run(core, "show").stdout)["limits"]
    assert limits == {**crew.DEFAULTS["limits"], "masters": 3}


def test_a_lens_merges_over_its_default_lens(tmp_path):
    core, _ = workspace(tmp_path, with_(lenses__product__keeper="ada"))
    product = json.loads(run(core, "show").stdout)["lenses"]["product"]
    assert product == {**crew.DEFAULTS["lenses"]["product"], "keeper": "ada"}


@pytest.mark.parametrize(
    "rules",
    [
        [f"rule {i}" for i in range(11)],
        ["x" * 161],
        ["two\nlines"],
    ],
)
def test_local_rules_are_capped(tmp_path, rules):
    core, _ = workspace(tmp_path, with_(local_rules=rules))
    out = run(core, "show")
    assert out.returncode == 1 and "local_rules" in out.stderr
    assert "10" in out.stderr or "160" in out.stderr


def test_ten_rules_of_160_characters_pass(tmp_path):
    core, _ = workspace(tmp_path, with_(local_rules=["x" * 160] * 10))
    assert run(core, "show").returncode == 0


def test_a_value_of_the_wrong_type_is_refused(tmp_path):
    core, _ = workspace(tmp_path, with_(limits__masters="five"))
    out = run(core, "show")
    assert out.returncode == 1 and "limits.masters must be a number" in out.stderr


def test_workplace_prints_the_start_repo_then_the_extra_repos(tmp_path):
    data = with_(members__ada__workplace="../infra", members__ada__extra_repos=["."])
    core, _ = workspace(tmp_path, data)
    (tmp_path / "infra").mkdir()
    out = run(core, "workplace", "ada")
    assert out.returncode == 0, out.stderr
    assert out.stdout.splitlines() == [str((tmp_path / "infra").resolve()), str(core.resolve())]
    unknown = run(core, "workplace", "nobody")
    assert unknown.returncode == 1 and "nobody" in unknown.stderr
    shutil.rmtree(tmp_path / "infra")
    gone = run(core, "workplace", "ada")
    assert gone.returncode == 1 and "members.ada.workplace" in gone.stderr


def test_lenses_prints_a_set_in_order_with_absolute_paths(tmp_path):
    data = with_(
        lenses__architecture__registry="docs/registry.md", lenses__architecture__keeper="otto"
    )
    core, _ = workspace(tmp_path, data)
    (core / "docs").mkdir()
    (core / "docs" / "registry.md").write_text("x")
    out = run(core, "lenses", "--set", "ready")
    assert out.returncode == 0, out.stderr
    shown = json.loads(out.stdout)
    assert [lens["lens"] for lens in shown] == ["product", "architecture", "acceptance"]
    arch = shown[1]
    assert arch == {
        "lens": "architecture",
        "agent": "we:lens-architecture",
        "questions": None,
        "registry": str((core / "docs" / "registry.md").resolve()),
        "keeper": "otto",
        "keeper_name": "Otto",
        "sample": 5,
    }
    t2 = json.loads(run(core, "lenses", "--set", "t2").stdout)
    assert [lens["lens"] for lens in t2] == ["architecture", "security", "premise"]
    assert len(json.loads(run(core, "lenses").stdout)) == 5


def test_is_role_reads_v2_keys_and_refuses_a_v1_key(tmp_path):
    core, _ = workspace(tmp_path)
    otto = {"WESIDE_COMPANION": "Otto", "WE_ROLE": "master"}
    assert run(core, "is-role", "coordinator", "--session", "s", env=otto).returncode == 0
    old = run(core, "is-role", "orchestrator", "--session", "s", env=otto)
    assert old.returncode == 1 and old.stderr.strip() == "crew: unknown role orchestrator"


def test_the_reader_runs_isolated(tmp_path):
    core, _ = workspace(tmp_path)
    otto = {"WESIDE_COMPANION": "Otto", "WE_ROLE": "master"}
    out = run(core, "is-role", "coordinator", "--session", "s", env=otto, isolated=True)
    assert out.returncode == 0, out.stderr


def transition_workspace(tmp_path: Path, data: dict) -> Path:
    core, _ = workspace(tmp_path, data)
    for name in ("primitives.md", "runbook.md", "dod.md", "verify.md"):
        (core / "docs").mkdir(exist_ok=True)
        (core / "docs" / name).write_text("x")
    return core


def test_v7_transition_keys_are_stripped_and_named(tmp_path):
    data = json.loads(TRANSITION.read_text())
    core = transition_workspace(tmp_path, data)
    out = run(core, "show")
    assert out.returncode == 0, out.stderr
    shown = json.loads(out.stdout)
    assert not set(crew.V7_TRANSITION) & set(shown["roles"])
    assert all("role" not in m and "lens" not in m for m in shown["members"].values())
    assert out.stderr.strip() == (
        "crew: v7 transition keys present (roles.product_owner, roles.orchestrator, "
        "roles.tester, members.*.role, members.*.lens): remove them at the switchover cleanup, "
        "switchover day + 7"
    )
    assert shown["roles"]["coordinator"] == "otto"
    assert run(core, "workplace", "kit").returncode == 1  # ../infra absent
    (tmp_path / "infra").mkdir()
    assert run(core, "workplace", "kit").stdout.splitlines()[1] == str(core.resolve())
    assert run(core, "lenses").returncode == 0


def test_v7_transition_keys_must_agree(tmp_path):
    data = json.loads(TRANSITION.read_text())
    data["roles"]["orchestrator"] = "ada"
    core = transition_workspace(tmp_path, data)
    out = run(core, "show")
    assert out.returncode == 1
    assert "roles.orchestrator" in out.stderr and "roles.coordinator" in out.stderr


def test_labels_default_merge_and_refuse_an_unknown_key(tmp_path):
    core, _ = workspace(tmp_path)
    assert json.loads(run(core, "show").stdout)["labels"] == {
        "recommendation": "Recommendation",
        "ready": "ready",
    }
    core.joinpath(".weside", "crew.json").write_text(json.dumps(with_(labels__ready="bereit")))
    assert json.loads(run(core, "show").stdout)["labels"] == {
        "recommendation": "Recommendation",
        "ready": "bereit",
    }
    core.joinpath(".weside", "crew.json").write_text(json.dumps(with_(labels__readyz="x")))
    out = run(core, "show")
    assert out.returncode == 1 and "unknown key labels.readyz" in out.stderr


@pytest.mark.parametrize("text", ["", "x" * 41, "two\nlines"])
def test_a_label_is_one_short_line(tmp_path, text):
    core, _ = workspace(tmp_path, with_(labels__recommendation=text))
    out = run(core, "show")
    assert out.returncode == 1 and "labels.recommendation" in out.stderr
