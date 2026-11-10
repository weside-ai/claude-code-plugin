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
    (core / ".weside" / "risk-paths").write_text("[t2]\npath docs/**\n")
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


UNKNOWN_KEY = Path(__file__).resolve().parent / "fixtures" / "crew-v2-unknown-key.json"
UNKNOWN_IN_FILE_ORDER = [
    "limitz",
    "limits.masterz",
    "roles.auditor",
    "members.ada.titel",
    "fallback.securty",
    "lenses.product.keepr",
]


def warning(core: Path, dotted: str) -> str:
    path = core / ".weside" / "crew.json"
    return f"crew: {path}: unknown key {dotted} ignored (crew.py validate --strict refuses it)"


@pytest.mark.parametrize(
    ("changes", "dotted"),
    [
        ({"limitz": {}}, "limitz"),
        ({"limits__masterz": 3}, "limits.masterz"),
        ({"members__ada__titel": "x"}, "members.ada.titel"),
        ({"roles__auditor": "ada"}, "roles.auditor"),
        ({"fallback__securty": "human_bundle"}, "fallback.securty"),
        ({"lenses__product__keepr": "ada"}, "lenses.product.keepr"),
        ({"board__states__parked": "Parked"}, "board.states.parked"),
    ],
)
def test_an_unknown_key_warns_by_name_and_validate_strict_refuses_it(tmp_path, changes, dotted):
    core, _ = workspace(tmp_path, with_(**changes))
    out = run(core, "show")
    assert out.returncode == 0, out.stderr
    assert out.stderr.strip() == warning(core, dotted)
    shown = json.loads(out.stdout)
    assert shown["unknown_keys"] == [dotted]
    node = shown
    for part in dotted.split(".")[:-1]:
        node = node[part]
    assert dotted.split(".")[-1] not in node
    loose = run(core, "validate")
    assert loose.returncode == 0 and loose.stdout.strip() == f"ok {core / '.weside' / 'crew.json'}"
    assert loose.stderr.strip() == warning(core, dotted)
    strict = run(core, "validate", "--strict")
    assert strict.returncode == 1 and strict.stdout == ""
    assert strict.stderr.strip() == f"crew: {core / '.weside' / 'crew.json'}: unknown key {dotted}"


def test_every_unknown_key_warns_in_file_order_and_the_known_ones_still_hold(tmp_path):
    core, _ = workspace(tmp_path, json.loads(UNKNOWN_KEY.read_text()))
    out = run(core, "show")
    assert out.returncode == 0, out.stderr
    assert out.stderr.splitlines() == [warning(core, d) for d in UNKNOWN_IN_FILE_ORDER]
    shown = json.loads(out.stdout)
    assert shown["unknown_keys"] == UNKNOWN_IN_FILE_ORDER
    assert shown["limits"] == crew.DEFAULTS["limits"] and "limitz" not in shown
    assert "auditor" not in shown["roles"] and shown["fallback"] == {}
    assert shown["members"]["ada"] == {
        "name": "Ada",
        "title": "Product Owner",
        "components": ["App"],
        "workplace": ".",
    }
    assert shown["lenses"]["product"] == crew.DEFAULTS["lenses"]["product"]
    strict = run(core, "validate", "--strict")
    assert strict.returncode == 1
    assert strict.stderr.strip().endswith("unknown key " + ", ".join(UNKNOWN_IN_FILE_ORDER))


def test_a_clean_crew_validates_strict_and_carries_no_unknown_keys(tmp_path):
    core, _ = workspace(tmp_path)
    out = run(core, "validate", "--strict")
    assert (out.returncode, out.stdout.strip(), out.stderr) == (
        0,
        f"ok {core / '.weside' / 'crew.json'}",
        "",
    )
    assert json.loads(run(core, "show").stdout)["unknown_keys"] == []


def test_validate_warns_when_the_crew_has_no_risk_rules(tmp_path):
    """The merge hook refuses a crew repo without rules; validate says so first."""
    core, _ = workspace(tmp_path)
    rules = core / ".weside" / "risk-paths"
    rules.unlink(missing_ok=True)
    out = run(core, "validate")
    assert out.returncode == 0
    assert out.stderr.startswith("warning: no risk rules: the crew sets no `risk.command`")
    rules.write_text("# no brake, on purpose\n")
    assert run(core, "validate").stderr == ""


def test_a_known_key_beside_an_unknown_one_is_still_checked(tmp_path):
    core, _ = workspace(tmp_path, with_(limits__masterz=3, limits__masters="five"))
    out = run(core, "show")
    assert out.returncode == 1
    assert out.stderr.strip() == (
        f"crew: {core / '.weside' / 'crew.json'}: limits.masters must be a number"
    )


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (with_(version=1), "crew.json is version 1: "),
        (with_(version=3), "{path}: version 3 is not 2"),
        (with_(version=True), "{path}: version True is not 2"),
        (with_(limits__masters="five"), "{path}: limits.masters must be a number"),
        (
            with_(acceptance__done_sample="5"),
            "{path}: acceptance.done_sample must be a number or null",
        ),
        (with_(members__ada__on_call="yes"), "{path}: members.ada.on_call must be true or false"),
        (with_(roles__product="nobody"), "{path}: roles.product 'nobody' is no member"),
        (with_(lenses__product__keeper="nobody"), "{path}: lenses.product.keeper 'nobody' is no"),
        (with_(files__dod="docs/gone.md"), "{path}: files.dod 'docs/gone.md' does not exist"),
        ("{not json", "{path}: unreadable (JSONDecodeError)"),
    ],
)
def test_a_hard_error_keeps_its_message(tmp_path, raw, message):
    core, _ = workspace(tmp_path)
    path = core / ".weside" / "crew.json"
    path.write_text(raw if isinstance(raw, str) else json.dumps(raw))
    with pytest.raises(crew.CrewError) as exc:
        crew.load(path)
    assert str(exc.value).startswith(message.format(path=path))
    out = run(core, "validate")
    assert out.returncode == 1 and out.stderr.startswith("crew: " + message.format(path=path))


def test_fallback_is_the_defaults_with_the_reason_and_the_file_s_own_labels(tmp_path):
    core, _ = workspace(
        tmp_path, with_(labels__crew_unreadable="nicht lesbar", limits__masters="x")
    )
    path = core / ".weside" / "crew.json"
    found = crew.fallback(path, "why")
    assert found["crew_error"] == "why" and found["unknown_keys"] == []
    assert found["roles"] == {} and found["members"] == {}
    assert found["labels"]["crew_unreadable"] == "nicht lesbar"
    assert found["labels"]["crew_unknown_keys"] == "crew.json: unknown keys ignored"
    assert found["limits"] == crew.DEFAULTS["limits"]
    for bad in ("{not json", json.dumps(with_(labels__crew_unreadable="x" * 41))):
        path.write_text(bad)
        assert crew.fallback(path, "why")["labels"]["crew_unreadable"] == "crew.json not readable"
    assert crew.fallback(None, "why")["labels"] == crew.DEFAULTS["labels"]


def test_a_retired_capacity_key_loads_with_one_stderr_line(tmp_path):
    core, _ = workspace(tmp_path, with_(capacity={"pod_gib": 16, "gate_lock_gib": 2}))
    out = run(core, "show")
    assert out.returncode == 0, out.stderr
    crew_file = core / ".weside" / "crew.json"
    assert out.stderr.count("crew: capacity is no longer read") == 1
    assert f"crew: capacity is no longer read; remove it from {crew_file}" in out.stderr
    assert "capacity" not in crew.load(crew_file)
    assert crew.load(crew_file)["unknown_keys"] == [], "a retired key is not an unknown one"
    strict = run(core, "validate", "--strict")
    assert strict.returncode == 0, "a retired key never fails validate --strict"


def test_only_retired_keys_are_skipped_silently_for_strict_another_unknown_key_is_refused(
    tmp_path,
):
    core, _ = workspace(tmp_path, with_(capacity={"pod_gib": 16}, capacityz=1))
    out = run(core, "show")
    assert out.returncode == 0, out.stderr
    assert warning(core, "capacityz") in out.stderr.splitlines()
    assert json.loads(out.stdout)["unknown_keys"] == ["capacityz"]
    strict = run(core, "validate", "--strict")
    assert strict.returncode == 1
    assert strict.stderr.strip().endswith("unknown key capacityz")


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
    [({"roles__product": "nobody"}, "roles.product"), ({"roles__hr": 3}, "roles.hr")],
)
def test_a_holder_without_a_member_is_refused(tmp_path, changes, dotted):
    core, _ = workspace(tmp_path, with_(**changes))
    out = run(core, "show")
    assert out.returncode == 1 and dotted in out.stderr


@pytest.mark.parametrize(
    ("changes", "dotted"),
    [
        ({"files__dod": "docs/dod.md"}, "files.dod"),
        ({"lenses__architecture__registry": "docs/registry.md"}, "lenses.architecture.registry"),
        ({"lenses__product__questions": "docs/q.md"}, "lenses.product.questions"),
        ({"lenses__product__t2_questions": "docs/q-t2.md"}, "lenses.product.t2_questions"),
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


def test_warning_ok_after_rounds_defaults_off_and_takes_a_number_of_at_least_one(tmp_path):
    minimal = {"version": 2, "roles": CREW["roles"], "members": CREW["members"]}
    core, _ = workspace(tmp_path, minimal)
    assert json.loads(run(core, "show").stdout)["ready_panel"] == {"warning_ok_after_rounds": None}
    core.joinpath(".weside", "crew.json").write_text(
        json.dumps(with_(ready_panel__warning_ok_after_rounds=2))
    )
    assert json.loads(run(core, "show").stdout)["ready_panel"]["warning_ok_after_rounds"] == 2
    for bad in (0, -1, "2", True, 1.5):
        core.joinpath(".weside", "crew.json").write_text(
            json.dumps(with_(ready_panel__warning_ok_after_rounds=bad))
        )
        out = run(core, "show")
        assert out.returncode == 1, bad
        assert "ready_panel.warning_ok_after_rounds must be" in out.stderr, (bad, out.stderr)


def test_the_ready_gate_keys_default_and_are_typed(tmp_path):
    minimal = {"version": 2, "roles": CREW["roles"], "members": CREW["members"]}
    core, _ = workspace(tmp_path, minimal)
    shown = json.loads(run(core, "show").stdout)
    assert shown["oracles"]["receipt_check"] is None
    assert shown["acceptance"]["boundary_terms"] == []
    bound = with_(oracles__receipt_check="python3 check.py", acceptance__boundary_terms=["tenant"])
    core.joinpath(".weside", "crew.json").write_text(json.dumps(bound))
    shown = json.loads(run(core, "show").stdout)
    assert shown["oracles"]["receipt_check"] == "python3 check.py"
    assert shown["acceptance"]["boundary_terms"] == ["tenant"]
    for changes, message in [
        (
            {"oracles__receipt_check": ["python3"]},
            "oracles.receipt_check must be a string or null",
        ),
        ({"acceptance__boundary_terms": "tenant"}, "acceptance.boundary_terms must be a list"),
    ]:
        core.joinpath(".weside", "crew.json").write_text(json.dumps(with_(**changes)))
        out = run(core, "show")
        assert out.returncode == 1 and message in out.stderr, (changes, out.stderr)


def test_the_flow_block_defaults_merges_and_is_typed(tmp_path):
    minimal = {"version": 2, "roles": CREW["roles"], "members": CREW["members"]}
    core, _ = workspace(tmp_path, minimal)
    shown = json.loads(run(core, "show").stdout)
    assert shown["flow"] == {
        "log_dir": None,
        "stale_min": 15,
        "starter_wait_min": 30,
        "urgent_commands": [],
    }
    bound = with_(flow__log_dir="~/flow", flow__urgent_commands=["gh secret", r"eas build"])
    core.joinpath(".weside", "crew.json").write_text(json.dumps(bound))
    shown = json.loads(run(core, "show").stdout)
    assert shown["flow"]["log_dir"] == "~/flow" and shown["flow"]["stale_min"] == 15
    assert shown["flow"]["urgent_commands"] == ["gh secret", "eas build"]
    for changes, message in [
        ({"flow__stale_min": "15"}, "flow.stale_min must be a number"),
        ({"flow__urgent_commands": "gh secret"}, "flow.urgent_commands must be a list"),
        (
            {"flow__urgent_commands": ["ok", "(open"]},
            "flow.urgent_commands[1] '(open' is no regex",
        ),
    ]:
        core.joinpath(".weside", "crew.json").write_text(json.dumps(with_(**changes)))
        out = run(core, "show")
        assert out.returncode == 1 and message in out.stderr, (changes, out.stderr)


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


def test_extra_repos_splits_present_from_missing_and_workplace_path_ignores_them(tmp_path):
    data = with_(members__ada__workplace="../infra", members__ada__extra_repos=[".", "../gone"])
    core, _ = workspace(tmp_path, data)
    (tmp_path / "infra").mkdir()
    path = core / ".weside" / "crew.json"
    loaded = crew.load(path)
    assert crew.extra_repos(path, loaded, "ada") == ([core.resolve()], ["../gone"])
    assert crew.workplace_path(path, loaded, "ada") == (tmp_path / "infra").resolve()
    with pytest.raises(crew.CrewError, match=r"members\.ada\.extra_repos '\.\./gone'"):
        crew.workplace_paths(path, loaded, "ada")


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
        "t2_questions": None,
        "registry": str((core / "docs" / "registry.md").resolve()),
        "keeper": "otto",
        "keeper_name": "Otto",
        "sample": 5,
    }
    t2 = json.loads(run(core, "lenses", "--set", "t2").stdout)
    assert [lens["lens"] for lens in t2] == ["product", "architecture", "acceptance"]
    assert len(json.loads(run(core, "lenses").stdout)) == 3


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


@pytest.mark.parametrize(
    "old,new",
    [("product_owner", "product"), ("orchestrator", "coordinator"), ("tester", "acceptance")],
)
def test_a_transition_key_without_its_v2_key_is_refused(tmp_path, old, new):
    data = json.loads(TRANSITION.read_text())
    del data["roles"][new]
    core = transition_workspace(tmp_path, data)
    out = run(core, "show")
    assert out.returncode == 1
    assert f"roles.{old} needs roles.{new} beside it" in out.stderr


def test_labels_default_merge_and_warn_on_an_unknown_key(tmp_path):
    core, _ = workspace(tmp_path)
    defaults = {
        "recommendation": "Recommendation",
        "ready": "ready",
        "crew_unreadable": "crew.json not readable",
        "crew_unknown_keys": "crew.json: unknown keys ignored",
        "prompt_resolved": "prompt resolved at",
        "to": "to",
    }
    assert json.loads(run(core, "show").stdout)["labels"] == defaults
    core.joinpath(".weside", "crew.json").write_text(json.dumps(with_(labels__ready="bereit")))
    assert json.loads(run(core, "show").stdout)["labels"] == {**defaults, "ready": "bereit"}
    core.joinpath(".weside", "crew.json").write_text(json.dumps(with_(labels__readyz="x")))
    out = run(core, "show")
    assert out.returncode == 0 and out.stderr.strip() == warning(core, "labels.readyz")
    assert json.loads(out.stdout)["labels"] == defaults


@pytest.mark.parametrize("text", ["", "x" * 41, "two\nlines"])
def test_a_label_is_one_short_line(tmp_path, text):
    core, _ = workspace(tmp_path, with_(labels__recommendation=text))
    out = run(core, "show")
    assert out.returncode == 1 and "labels.recommendation" in out.stderr


@pytest.mark.parametrize(
    ("env", "hook", "want"),
    [
        ({"WE_ROLE": "worker"}, None, "worker"),
        ({}, {"agent_type": "x"}, "worker"),
        ({"WE_ROLE": "master"}, None, "master"),
        ({"WE_ROLE": "master", "WESIDE_COMPANION": "Otto"}, None, "coordinator"),
        ({"WESIDE_COMPANION": "ada"}, None, "product"),
        ({"WE_ROLE": "worker", "WESIDE_COMPANION": "Hana"}, None, "hr"),
        ({"WESIDE_COMPANION": "Lex"}, None, "specialist"),
        ({}, None, None),
        ({"WESIDE_COMPANION": "Nobody"}, None, None),
    ],
)
def test_role_of_session(env, hook, want):
    merged = crew._merge(CREW)
    assert crew.role_of_session(merged, env, hook) == want


def test_session_kind_verb_prints_the_role_or_none_with_a_hint(tmp_path):
    core, _ = workspace(tmp_path)
    base = {k: v for k, v in os.environ.items() if k not in ("WE_ROLE", "WESIDE_COMPANION")}
    base.pop("CLAUDE_CODE_SESSION_ID", None)

    def verb(**env):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "session-kind", "--from", str(core)],
            capture_output=True,
            text=True,
            env={**base, **env},
            cwd=tmp_path,
            check=False,
        )

    assert verb(WESIDE_COMPANION="Otto").stdout == "coordinator\n"
    assert verb(WE_ROLE="master").stdout == "master\n"
    none = verb()
    assert none.returncode == 0
    assert none.stdout == "none\nno role: ask the coordinator or run `/we:setup`\n"


def test_at_reads_only_the_root_itself(tmp_path):
    core, biz = workspace(tmp_path)
    assert crew.at(core) == core / ".weside" / "crew.json"
    assert crew.at(biz) == (core / ".weside" / "crew.json").resolve()
    assert crew.at(core / ".weside") is None


ROLE_CARDS = Path(__file__).resolve().parent.parent / "roles"


def card_stems(cards: Path = ROLE_CARDS) -> set[str]:
    return {p.stem for p in cards.glob("*.md")}


def test_one_role_card_per_role_key_and_session_kind():
    assert card_stems() == set(crew.ROLE_KEYS) | {"master", "worker", "specialist"}


def test_an_extra_card_or_a_missing_key_breaks_the_match(tmp_path):
    """Red arm of the card set: an eleventh card file, and a card set missing one key."""
    shutil.copytree(ROLE_CARDS, tmp_path / "roles")
    (tmp_path / "roles" / "auditor.md").write_text("# Role card: auditor\n")
    expected = set(crew.ROLE_KEYS) | {"master", "worker", "specialist"}
    assert card_stems(tmp_path / "roles") != expected
    (tmp_path / "roles" / "auditor.md").unlink()
    (tmp_path / "roles" / "hr.md").unlink()
    assert card_stems(tmp_path / "roles") != expected


@pytest.mark.parametrize("former", ["security", "premise"])
def test_an_undefined_former_default_lens_is_missing_with_a_warning(tmp_path, former):
    data = with_(t2_panel=["product", former, "acceptance"], ready_lenses=[former, "product"])
    core, _ = workspace(tmp_path, data)
    out = run(core, "lenses", "--set", "t2")
    assert out.returncode == 0, out.stderr
    assert [lens["lens"] for lens in json.loads(out.stdout)] == ["product", "acceptance"]
    assert (
        f"t2_panel: {former!r} is a former default lens no longer defined; "
        "left out (define it under lenses or drop the entry)"
    ) in out.stderr
    ready = run(core, "lenses", "--set", "ready")
    assert [lens["lens"] for lens in json.loads(ready.stdout)] == ["product"]
    assert f"ready_lenses: {former!r} is a former default lens" in ready.stderr
    assert run(core, "show").returncode == 0


def test_a_defined_former_default_lens_is_kept_and_an_unknown_lens_stays_an_error(tmp_path):
    core, _ = workspace(tmp_path, with_(lenses__security={}, t2_panel=["security"]))
    out = run(core, "lenses", "--set", "t2")
    assert out.returncode == 0 and out.stderr == ""
    assert [lens["lens"] for lens in json.loads(out.stdout)] == ["security"]
    core, _ = workspace(tmp_path / "u", with_(t2_panel=["product", "bogus"]))
    out = run(core, "show")
    assert out.returncode == 1
    assert "t2_panel: 'bogus' is no lens" in out.stderr


def test_security_is_an_optional_role_key():
    assert crew.ROLE_KEYS[-1] == "security" and len(crew.ROLE_KEYS) == 8
    assert crew.OPTIONAL_ROLE_KEYS == ("security",)
    assert set(crew.OPTIONAL_ROLE_KEYS) <= set(crew.ROLE_KEYS)


def test_a_crew_without_the_security_role_loads_silently(tmp_path):
    core, _ = workspace(tmp_path)
    out = run(core, "validate", "--strict")
    assert out.returncode == 0 and out.stderr == "", out.stderr
    assert crew.load(core / ".weside" / "crew.json")["unknown_keys"] == []


def test_a_bound_security_role_and_fallback_are_known_keys(tmp_path):
    data = with_(roles__security="lex", fallback__security="hr")
    core, _ = workspace(tmp_path, data)
    out = run(core, "validate", "--strict")
    assert out.returncode == 0 and out.stderr == "", out.stderr
    assert crew.holder_name(crew.load(core / ".weside" / "crew.json"), "security") == "Lex"


def test_the_pinned_security_holder_is_security_even_with_a_specialist_field():
    merged = crew._merge(with_(roles__security="lex"))
    assert merged["members"]["lex"]["specialist"] == "legal"
    assert crew.role_of_session(merged, {"WESIDE_COMPANION": "Lex"}) == "security"


def test_is_role_accepts_security_for_its_holder(tmp_path):
    core, _ = workspace(tmp_path, with_(roles__security="lex"))
    lex = {"WESIDE_COMPANION": "Lex", "WE_ROLE": "master"}
    assert run(core, "is-role", "security", "--session", "s", env=lex).returncode == 0
    otto = {"WESIDE_COMPANION": "Otto", "WE_ROLE": "master"}
    assert run(core, "is-role", "security", "--session", "s", env=otto).returncode == 1


def test_launch_subagent_fallback_is_a_known_bool_default_off(tmp_path):
    """A crew may let its master fall back to build subagents where its launcher is missing; the
    default keeps L0's "build only in workers"."""
    assert crew.DEFAULTS["launch"]["subagent_fallback"] is False
    core, _ = workspace(
        tmp_path, {**CREW, "launch": {"worker": "w {name} {brief}", "subagent_fallback": True}}
    )
    assert run(core, "validate", "--strict").returncode == 0
    core2, _ = workspace(tmp_path / "b", {**CREW, "launch": {"subagent_fallback": "yes"}})
    out = run(core2, "validate")
    assert out.returncode == 1 and "launch.subagent_fallback" in out.stderr


# --- two crews, AC1: the crew's state directory -------------------------------------------------


@pytest.mark.parametrize(
    "env, state_dir, expected",
    [
        ({"WE_STATE_DIR": "/forced"}, "own", "/forced"),  # the env wins over the key
        ({}, "own", "{core}/.weside/own"),  # relative to the crew file's directory
        ({}, "~/crew-b", "{home}/crew-b"),  # a ~ path
        ({}, None, "{home}/.claude/we-state"),  # no key: today's folder
    ],
)
def test_state_dir_precedence(tmp_path, monkeypatch, env, state_dir, expected):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    data = {**CREW, **({"state_dir": state_dir} if state_dir is not None else {})}
    core, _ = workspace(tmp_path, data)
    path, loaded = crew.find_and_load(core)
    want = expected.format(core=core, home=tmp_path / "home")
    assert crew.state_dir(path, loaded, env) == Path(want)
    assert crew.board_file(path, loaded, env) == Path(want) / "board.json"


def test_board_file_wins_over_state_dir(tmp_path):
    core, _ = workspace(tmp_path, {**CREW, "state_dir": "own", "board": {"file": "b/x.json"}})
    path, loaded = crew.find_and_load(core)
    assert crew.board_file(path, loaded, {}) == core / ".weside" / "b" / "x.json"


def test_without_a_crew_file_the_paths_are_todays(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    today = tmp_path / "home" / ".claude" / "we-state"
    assert crew.state_dir(None, None, {}) == today
    assert crew.resolve_board(tmp_path, env={}) == today / "board.json"
    # a caller's DEFAULT_BOARD (tests point it at a temp file) stands in while nothing moves it
    assert crew.resolve_board(tmp_path, env={}, default="/t/b.json") == Path("/t/b.json")
    assert crew.resolve_board(tmp_path, env={"WE_STATE_DIR": "/s"}, default="/t/b.json") == Path(
        "/s/board.json"
    )


def test_a_state_dir_that_is_no_string_is_refused(tmp_path):
    core, _ = workspace(tmp_path, {**CREW, "state_dir": 3})
    with pytest.raises(crew.CrewError, match="state_dir must be a string or null"):
        crew.find_and_load(core)


def test_cli_state_dir_prints_the_resolved_folder(tmp_path):
    core, _ = workspace(tmp_path, {**CREW, "state_dir": "own"})
    env = {k: v for k, v in os.environ.items() if k != "WE_STATE_DIR"}
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "state-dir", "--from", str(core)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert out.returncode == 0
    assert out.stdout.strip() == str((core / ".weside" / "own").resolve())


def test_crew_id_is_the_origin_slug_shared_by_a_pointer(tmp_path):
    core, biz = workspace(tmp_path)
    subprocess.run(["git", "init", "-q", str(core)], check=True)
    subprocess.run(
        ["git", "-C", str(core), "remote", "add", "origin", "git@github.com:Acme/Core.git"],
        check=True,
    )
    assert crew.crew_id(core / ".weside" / "crew.json") == "acme/core"
    assert crew.crew_id(crew.find(biz)) == "acme/core"


def test_stamp_is_named_after_the_board_stem_and_written_once(tmp_path):
    assert crew.stamp_path(tmp_path / "board.json") == tmp_path / "crew.id"
    assert crew.stamp_path(tmp_path / "acme-board.json") == tmp_path / "acme-board-crew.id"
    assert crew.write_stamp(tmp_path / "board.json", "a/one") is True
    assert crew.write_stamp(tmp_path / "board.json", "b/two") is False
    assert crew.read_stamp(tmp_path / "board.json") == "a/one"


def test_a_relative_state_dir_names_one_folder_for_every_worktree(tmp_path):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    core, _ = workspace(tmp_path, {**CREW, "state_dir": "../../.we-state"})
    subprocess.run(["git", "init", "-q", str(core)], check=True)
    subprocess.run(["git", "-C", str(core), "add", "."], check=True)
    subprocess.run(["git", "-C", str(core), "commit", "-q", "-m", "c"], check=True, env=env)
    tree = tmp_path / "core-wt"
    subprocess.run(["git", "-C", str(core), "worktree", "add", "-q", str(tree)], check=True)
    main_path, main_crew = crew.find_and_load(core)
    wt_path, wt_crew = crew.find_and_load(tree)
    assert wt_path == tree / ".weside" / "crew.json"
    want = (core / ".weside" / "../../.we-state").resolve()
    assert crew.state_dir(main_path, main_crew, {}).resolve() == want
    assert crew.state_dir(wt_path, wt_crew, {}).resolve() == want


def test_launch_allow_bypass_is_a_bool_default_off_and_the_launch_verb_prints_it(tmp_path):
    assert crew.DEFAULTS["launch"]["allow_bypass"] is False
    core, _ = workspace(
        tmp_path, {**CREW, "launch": {"allow_bypass": True, "worker_timer": "~/t.py"}}
    )
    assert run(core, "validate", "--strict").returncode == 0
    assert run(core, "launch", "allow_bypass").stdout == "true\n"
    assert run(core, "launch", "worker_timer").stdout == "~/t.py\n"
    assert run(core, "launch", "worker").stdout == "\n"
    assert run(core, "launch", "nope").returncode == 2
    bad, _ = workspace(tmp_path / "b", {**CREW, "launch": {"allow_bypass": "yes"}})
    out = run(bad, "validate")
    assert out.returncode == 1 and "launch.allow_bypass" in out.stderr


def test_the_launch_verb_without_a_crew_prints_the_default(tmp_path):
    (tmp_path / ".git").mkdir()
    out = run(tmp_path, "launch", "allow_bypass")
    assert out.returncode == 0 and out.stdout == "false\n"


def test_launch_worker_mode_is_auto_or_bypass(tmp_path):
    assert crew.DEFAULTS["launch"]["worker_mode"] == "auto"
    core, _ = workspace(tmp_path, {**CREW, "launch": {"worker_mode": "bypass"}})
    assert run(core, "launch", "worker_mode").stdout == "bypass\n"
    bad, _ = workspace(tmp_path / "b", {**CREW, "launch": {"worker_mode": "yolo"}})
    out = run(bad, "validate")
    assert out.returncode == 1 and "launch.worker_mode must be one of auto, bypass" in out.stderr


def test_a_member_with_a_role_addendum_gets_the_pointer_skill(tmp_path):
    core, biz = workspace(tmp_path)
    path = core / ".weside" / "crew.json"
    (core / ".weside" / "roles").mkdir(parents=True, exist_ok=True)
    (core / ".weside" / "roles" / "lex.md").write_text("# Lex\n")
    crew.stubs(path, CREW, write=True)
    lex = biz / ".claude" / "skills" / "acme-lex" / "SKILL.md"
    text = lex.read_text()
    assert not crew.is_stub(lex)
    assert "name: acme-lex" in text and "`.weside/roles/lex.md`" in text
    assert "{{" not in text


@pytest.mark.parametrize(
    ("extra", "dotted"),
    [
        ({"release": {"prod_on": "human"}}, "release.prod_on"),
        ({"release": {"rc_job": "rc.yml"}}, "release.rc_job"),
        ({"oracles": {"receipt_schema": "x.json"}}, "oracles.receipt_schema"),
        ({"coldstart": {"suite": "tests/coldstart"}}, "coldstart"),
    ],
)
def test_a_retired_nested_key_loads_with_one_stderr_line(tmp_path, extra, dotted):
    """2b: keys no release reads any more leave the schema and load with one line, never an
    unknown-key refusal under --strict."""
    core, _ = workspace(tmp_path, with_(**extra))
    out = run(core, "validate", "--strict")
    assert out.returncode == 0, out.stderr
    assert out.stderr.count(f"crew: {dotted} is no longer read") == 1
    loaded = crew.load(core / ".weside" / "crew.json")
    assert loaded["unknown_keys"] == []
    parent, _, leaf = dotted.rpartition(".")
    assert leaf not in (loaded.get(parent) if parent else loaded)


# --- humans: several humans, one crew -------------------------------------------------------

HUMANS = {
    "alice": {
        "name": "Alice",
        "email": "alice@example.com",
        "decides": ["money", "prod"],
        "owns_states": ["selected", "in_progress", "in_review"],
        "runs": ["coordinator", "hr", "acceptance", "masters"],
    },
    "bob": {
        "name": "Bob",
        "email": "Bob@Example.com",
        "decides": ["product"],
        "owns_states": ["backlog"],
        "runs": ["product", "lex"],
        "companions": {"product": "Paula", "lex": "Lexi"},
    },
}


def test_without_humans_the_one_human_runs_everything():
    one = crew.humans({**CREW, "human": {"name": "Fay Doe", "decides": ["prod"]}})
    assert list(one) == ["fay-doe"]
    entry = one["fay-doe"]
    assert entry["runs"] == ["product", "acceptance", "coordinator", "hr", "masters"]
    assert entry["owns_states"] == list(crew.STATES) and entry["decides"] == ["prod"]
    assert crew.current_human(CREW, {}, email="") == ("the-human", crew.humans(CREW)["the-human"])
    assert not crew.several_humans(CREW)


def test_humans_load_and_resolve_the_session_s_human(tmp_path):
    core, _ = workspace(tmp_path, with_(humans=HUMANS))
    loaded = crew.load(core / ".weside" / "crew.json", strict=True)
    assert crew.several_humans(loaded)
    assert crew.current_human(loaded, {"WE_HUMAN": "bob"})[0] == "bob"
    assert crew.current_human(loaded, {}, email="BOB@example.com")[0] == "bob"
    assert crew.current_human(loaded, {}, email="eve@example.com") is None
    with pytest.raises(crew.CrewError, match="WE_HUMAN=eve is no human"):
        crew.current_human(loaded, {"WE_HUMAN": "eve"})
    assert crew.state_owners(loaded, "backlog") == ["bob"]
    assert crew.state_owners(loaded, "done") == []
    assert crew.runs(loaded, "bob") == ["product", "lex"]


def test_several_humans_share_a_state_and_in_test_is_a_state(tmp_path):
    shared = {
        **HUMANS,
        "alice": {**HUMANS["alice"], "owns_states": ["backlog", "in_review"]},
        "bob": {**HUMANS["bob"], "owns_states": ["backlog", "in_test"]},
    }
    core, _ = workspace(tmp_path, with_(humans=shared))
    loaded = crew.load(core / ".weside" / "crew.json", strict=True)
    assert crew.state_owners(loaded, "backlog") == ["alice", "bob"]
    assert crew.state_owners(loaded, "in_test") == ["bob"]
    assert loaded["board"]["states"]["in_test"] == "In Test"
    assert (
        crew.STATES.index("in_review") < crew.STATES.index("in_test") < crew.STATES.index("done")
    )
    assert crew.RUNNING_STATES[0] == "in_progress"


def test_the_deciding_human_is_the_first_with_decides(tmp_path):
    first = {
        "bob": {**HUMANS["bob"], "decides": []},
        "alice": HUMANS["alice"],
    }
    core, _ = workspace(tmp_path, with_(humans=first))
    loaded = crew.load(core / ".weside" / "crew.json", strict=True)
    assert crew.deciding_human(loaded)[0] == "alice"


def test_the_deliverer_is_the_coordinator_or_the_first_role_this_human_runs(tmp_path):
    core, _ = workspace(tmp_path, with_(humans=HUMANS))
    loaded = crew.load(core / ".weside" / "crew.json")
    assert crew.deliverer(loaded, {"WE_HUMAN": "alice"}) == "Otto"
    # bob's machine runs no coordinator: his product session delivers, by his name for it
    assert crew.deliverer(loaded, {"WE_HUMAN": "bob"}) == "Paula"
    assert crew.deliverer(CREW, {}) == crew.holder_name(CREW, "coordinator")
    out = run(core, "deliverer", env={"WE_HUMAN": "bob"})
    assert out.returncode == 0 and out.stdout.strip() == "Paula"


@pytest.mark.parametrize("value, ok", [("acceptance", True), (None, True), ("tester", False)])
def test_done_without_test_is_a_role_key_or_null(tmp_path, value, ok):
    core, _ = workspace(tmp_path, with_(board__done_without_test=value))
    if ok:
        assert crew.load(core / ".weside" / "crew.json")["board"]["done_without_test"] == value
    else:
        with pytest.raises(crew.CrewError, match="done_without_test must be a role key"):
            crew.load(core / ".weside" / "crew.json")


def test_display_name_per_human_and_member_lookup_by_it(tmp_path):
    core, _ = workspace(tmp_path, with_(humans=HUMANS))
    loaded = crew.load(core / ".weside" / "crew.json")
    assert crew.display_name(loaded, "product", "bob") == "Paula"
    assert crew.display_name(loaded, "product", "alice") == "Ada"
    assert crew.display_name(loaded, "lex", "bob") == "Lexi"
    assert crew.display_name(loaded, "lex", None) == "Lex"
    assert crew.display_name(loaded, "security", "bob") is None
    assert crew.member(loaded, "paula")[0] == "ada"
    env = {"WESIDE_COMPANION": "Paula", "WE_ROLE": "master"}
    assert crew.role_of_session(loaded, env) == "product"
    assert crew.holds_role(loaded, "product", env)


def test_we_role_id_picks_among_the_roles_one_member_holds():
    two = with_(roles__escalation="otto")
    env = {"WESIDE_COMPANION": "Otto", "WE_ROLE": "master"}
    assert crew.role_of_session(two, env) == "coordinator"
    assert crew.role_of_session(two, {**env, "WE_ROLE_ID": "escalation"}) == "escalation"
    assert crew.role_of_session(two, {**env, "WE_ROLE_ID": "product"}) == "coordinator"


@pytest.mark.parametrize(
    "change, message",
    [
        ({"alice": {"email": "a@x"}}, "humans.alice.name is missing"),
        ({"Alice": {"name": "Alice"}}, "a slug is lower case"),
        ({"alice": {"name": "A", "runs": "coordinator"}}, "humans.alice.runs must be a list"),
        ({"alice": {"name": "A", "runs": ["pilot"]}}, "'pilot' is no role key, member slug"),
        ({"alice": {"name": "A", "owns_states": ["review"]}}, "'review' is no state"),
        (
            {"alice": {"name": "A", "email": "x@y"}, "bob": {"name": "B", "email": "X@Y"}},
            "humans.bob.email is also humans.alice.email",
        ),
        ({"alice": {"name": "A", "companions": {"product": 3}}}, "must be an object of strings"),
        (
            {"alice": {"name": "A", "companions": {"pilot": "P"}}},
            "'pilot' is no role key nor member",
        ),
        ({"alice": {"name": "A", "companions": {"security": "S"}}}, "the role has no member"),
        (
            {"alice": {"name": "A", "companions": {"product": "Otto"}}},
            "'Otto' is already the name of members.otto.name",
        ),
        (
            {
                "alice": {"name": "A", "companions": {"product": "Max"}},
                "bob": {"name": "B", "companions": {"hr": "Max"}},
            },
            "a name denotes one member",
        ),
        ({}, "humans must be an object with at least one human"),
    ],
)
def test_humans_validation_names_the_key(tmp_path, change, message):
    core, _ = workspace(tmp_path, with_(humans=change))
    with pytest.raises(crew.CrewError, match=message):
        crew.load(core / ".weside" / "crew.json")


def test_an_unknown_human_field_warns_and_strict_refuses(tmp_path):
    core, _ = workspace(tmp_path, with_(humans={"alice": {"name": "A", "phone": "1"}}))
    path = core / ".weside" / "crew.json"
    assert crew.load(path)["unknown_keys"] == ["humans.alice.phone"]
    with pytest.raises(crew.CrewError, match=r"unknown key humans\.alice\.phone"):
        crew.load(path, strict=True)


@pytest.mark.parametrize(
    "signals, message",
    [
        ("x", "board.signals must be a list"),
        ([{"state": "selected", "role": "coordinator"}], r"jql_window must be a number"),
        ([{"state": "picked", "role": "coordinator", "jql_window": "5m"}], "state must be one of"),
        ([{"state": "selected", "role": "boss", "jql_window": "5m"}], "role must be a role key"),
        ([{"state": "selected", "role": "hr", "jql_window": "5m", "x": 1}], "has no field x"),
    ],
)
def test_board_signals_validation(tmp_path, signals, message):
    core, _ = workspace(tmp_path, with_(board__signals=signals))
    with pytest.raises(crew.CrewError, match=message):
        crew.load(core / ".weside" / "crew.json")


def test_human_and_name_verbs(tmp_path):
    core, _ = workspace(tmp_path, with_(humans=HUMANS))
    env = {**os.environ, "WE_HUMAN": "bob"}
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "human", "--from", str(core)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert out.stdout == "bob\tBob\tproduct,lex\n"
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "name", "product", "--from", str(core)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert out.stdout == "Paula\n"
    env["WE_HUMAN"] = ""
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "human", "--from", str(core)],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        check=False,
    )
    assert out.returncode == 1 and "set WE_HUMAN=<slug>" in out.stderr


def test_skill_path_finds_the_member_s_skill_under_a_human_s_name(tmp_path):
    core, _ = workspace(tmp_path, with_(humans=HUMANS))
    skill = core / ".claude" / "skills" / "acme-ada" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: acme-ada\n---\n")
    path, loadable = crew.skill_path("Paula", core, home=tmp_path / "home")
    assert path == skill and loadable


def test_a_crew_security_lens_dispatches_the_shipped_security_agent():
    """Three panels of a consumer crew dispatched the security lens as we:lens-architecture."""
    merged = crew._merge({**CREW, "lenses": {"security": {}}, "t2_panel": ["security"]})
    assert merged["lenses"]["security"]["agent"] == "we:lens-security"
    agent = Path(crew.__file__).resolve().parent.parent / "agents" / "lens-security.md"
    assert "name: lens-security" in agent.read_text(encoding="utf-8")
