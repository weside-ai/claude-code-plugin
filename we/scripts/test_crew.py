"""crew.py: lookup with the config pointer, member and role lookup, skill paths, stubs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import crew

SCRIPT = Path(__file__).resolve().parent / "crew.py"

CREW = {
    "version": 1,
    "skill_prefix": "acme",
    "question_label": "FRAGE",
    "roles": {"product_owner": "ada", "orchestrator": "otto", "hr": "hana", "tester": "tess"},
    "members": {
        "ada": {"name": "Ada", "role": "product_owner", "components": ["App"], "workplace": "."},
        "otto": {"name": "Otto", "role": "orchestrator", "workplace": "."},
        "hana": {"name": "Hana", "role": "hr", "workplace": "../biz"},
        "tess": {"name": "Tess", "role": "tester", "workplace": ".", "on_call": False},
        "lex": {"name": "Lex", "role": "legal", "workplace": "../biz", "on_call": True},
    },
}


def workspace(tmp_path: Path) -> tuple[Path, Path]:
    core, biz = tmp_path / "core", tmp_path / "biz"
    (core / ".weside").mkdir(parents=True)
    (biz / ".weside").mkdir(parents=True)
    (core / ".weside" / "crew.json").write_text(json.dumps(CREW))
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
    assert crew.holder_name(CREW, "orchestrator") == "Otto"
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
    skill = tmp_path / ".claude" / "skills" / "weside-vyra" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("x")
    assert crew.skill_path("Vyra", tmp_path, home=tmp_path / "h") == (skill, True)
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
    assert "name: acme-lex" in text and "# Lex · legal" in text and "tell Hana" in text
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
    assert shown["roles"]["orchestrator"] == "otto" and shown["question_label"] == "FRAGE"
    assert shown["members"]["lex"]["on_call"] is True
    assert cli("members").stdout.splitlines()[0] == "Ada\tproduct_owner"
    assert cli("path", cwd=tmp_path).returncode == 1
    cli("stubs", "--write")
    out = cli("skill-path", "Lex", "--cwd", str(core)).stdout.strip().split("\t")
    assert out[1:] == ["workplace", "stub"]


def test_broken_crew_is_an_error(tmp_path):
    (tmp_path / ".weside").mkdir()
    (tmp_path / ".weside" / "crew.json").write_text('{"members": []}')
    try:
        crew.find_and_load(tmp_path)
    except crew.CrewError as exc:
        assert "members" in str(exc)
    else:
        raise AssertionError("expected CrewError")
