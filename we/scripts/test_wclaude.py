"""wclaude against a stub `claude` on PATH that records its environment and argv."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "wclaude"

pytestmark = pytest.mark.skipif(not shutil.which("bash"), reason="wclaude is a bash script")

CREW = {
    "version": 2,
    "roles": {"product": "po", "architecture": "arch"},
    "members": {
        "po": {"name": "Ada", "title": "Product Owner"},
        "arch": {"name": "Bo"},
    },
}


def run(tmp_path, args=(), stdin="", crew=CREW, launch=None):
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    record = tmp_path / "record.json"
    stub = stub_dir / "claude"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "json.dump({'companion': os.environ.get('WESIDE_COMPANION'), 'argv': sys.argv[1:]},"
        f" open({str(record)!r}, 'w'))\n"
        f"open({str(tmp_path / 'role')!r}, 'w').write(os.environ.get('WE_ROLE', ''))\n"
    )
    stub.chmod(0o755)
    project = tmp_path / "project"
    cwd = project / "sub" / "dir"
    cwd.mkdir(parents=True, exist_ok=True)
    if crew is not None:
        (project / ".weside").mkdir(exist_ok=True)
        (project / ".weside" / "crew.json").write_text(json.dumps(crew))
    env = {
        **os.environ,
        "PATH": f"{stub_dir}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "WESIDE_COMPANION": "Stale",
    }
    env.pop("WCLAUDE_PIN", None)
    env["WE_ROLE"] = "worker"
    if launch is not None:
        env["WCLAUDE_PIN"] = launch
    proc = subprocess.run(
        ["bash", str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=20,
        check=False,
    )
    result = json.loads(record.read_text()) if record.exists() else None
    return proc, result


def test_menu_lists_title_else_held_role(tmp_path):
    proc, result = run(tmp_path, stdin="1\n")
    assert proc.returncode == 0, proc.stderr
    assert "Ada" in proc.stderr
    assert "Product Owner" in proc.stderr
    assert "architecture" in proc.stderr
    assert " 3) other name..." in proc.stderr
    assert "~/project/.weside/crew.json" in proc.stderr
    assert result == {"companion": "Ada", "argv": ["--name", "Ada"]}


def test_menu_pick_second(tmp_path):
    _, result = run(tmp_path, stdin="2\n")
    assert result["companion"] == "Bo"


def test_other_name_prompt(tmp_path):
    _, result = run(tmp_path, stdin="3\n  Cleo \n")
    assert result["companion"] == "Cleo"


def test_typed_name(tmp_path):
    _, result = run(tmp_path, args=["--resume"], stdin="Dana\n")
    assert result == {"companion": "Dana", "argv": ["--name", "Dana", "--resume"]}


def test_as_skips_menu(tmp_path):
    proc, result = run(tmp_path, args=["--as", "Eve", "-p", "hi"])
    assert proc.returncode == 0, proc.stderr
    assert "other name" not in proc.stderr
    assert result == {"companion": "Eve", "argv": ["--name", "Eve", "-p", "hi"]}


def test_as_without_name_is_usage_error(tmp_path):
    proc, result = run(tmp_path, args=["--as"])
    assert proc.returncode == 2
    assert result is None


def test_dash_c_passes_through_after_the_menu(tmp_path):
    proc, result = run(tmp_path, args=["-c"], stdin="1\n")
    assert proc.returncode == 0, proc.stderr
    assert "other name" in proc.stderr
    assert result == {"companion": "Ada", "argv": ["--name", "Ada", "-c"]}


def test_dash_c_with_a_member_name_warns_and_goes_on(tmp_path):
    proc, result = run(tmp_path, args=["-c", "bo"], stdin="1\n")
    assert proc.returncode == 0, proc.stderr
    assert "did you mean --as bo?" in proc.stderr
    assert result == {"companion": "Ada", "argv": ["--name", "Ada", "-c", "bo"]}


def test_dash_c_with_a_prompt_does_not_warn(tmp_path):
    proc, _ = run(tmp_path, args=["-c", "fix the tests"], stdin="1\n")
    assert "did you mean" not in proc.stderr


def test_zero_clears_the_pin(tmp_path):
    proc, result = run(tmp_path, args=["--continue"], stdin="0\n")
    assert proc.returncode == 0, proc.stderr
    assert result == {"companion": "", "argv": ["--continue"]}
    assert "(no companion)" in proc.stderr


def test_arguments_with_spaces_pass_unchanged(tmp_path):
    args = ["-p", "two words", "", "a'quote", "--model", "x y"]
    _, result = run(tmp_path, args=args, stdin="1\n")
    assert result["argv"] == ["--name", "Ada", *args]


@pytest.mark.parametrize("choice", ["4\n", "99\n", "\n"])
def test_out_of_range_or_empty_choice_refused(tmp_path, choice):
    proc, result = run(tmp_path, stdin=choice)
    assert proc.returncode == 1
    assert result is None


def test_closed_stdin_refused(tmp_path):
    proc, result = run(tmp_path, stdin="")
    assert proc.returncode == 1
    assert result is None


def test_without_crew_offers_name_and_zero(tmp_path):
    proc, result = run(tmp_path, crew=None, stdin="1\nFay\n")
    assert "no .weside/crew.json found" in proc.stderr
    assert result["companion"] == "Fay"


def test_broken_crew_still_offers_menu(tmp_path):
    (tmp_path / "project" / ".weside").mkdir(parents=True)
    (tmp_path / "project" / ".weside" / "crew.json").write_text("{not json")
    proc, result = run(tmp_path, crew=None, stdin="Gus\n")
    assert "unreadable" in proc.stderr
    assert result["companion"] == "Gus"


@pytest.mark.parametrize("given", [["-n", "mine"], ["--name", "mine"], ["--name=mine"]])
def test_own_name_is_kept(tmp_path, given):
    _, result = run(tmp_path, args=["--as", "Eve", *given])
    assert result == {"companion": "Eve", "argv": given}


def test_no_companion_gets_no_name(tmp_path):
    _, result = run(tmp_path, stdin="0\n")
    assert result == {"companion": "", "argv": []}


def _write_wrapper(tmp_path):
    # A wrapper that tags argv, so the test sees which command wclaude started.
    wrapper = tmp_path / "bin" / "pinned"
    wrapper.parent.mkdir(exist_ok=True)
    wrapper.write_text('#!/usr/bin/env bash\nexec claude --via-wrapper "$@"\n')
    wrapper.chmod(0o755)


@pytest.mark.parametrize(
    "args,stdin,companion,argv",
    [
        (["--pin", "-c"], "1\n", "Ada", ["--via-wrapper", "--name", "Ada", "-c"]),
        (["--pin", "-c"], "0\n", "", ["--via-wrapper", "-c"]),
        (["--as", "Eve", "--pin"], "", "Eve", ["--via-wrapper", "--name", "Eve"]),
        (["--pin", "--as", "Eve"], "", "Eve", ["--via-wrapper", "--name", "Eve"]),
    ],
)
def test_pin_starts_the_pin_command(tmp_path, args, stdin, companion, argv):
    _write_wrapper(tmp_path)
    proc, result = run(tmp_path, args=args, stdin=stdin, launch="pinned")
    assert proc.returncode == 0, proc.stderr
    assert result == {"companion": companion, "argv": argv}
    assert "pinned" in proc.stderr


def test_without_pin_the_pin_command_is_not_used(tmp_path):
    _write_wrapper(tmp_path)
    _, result = run(tmp_path, stdin="0\n", launch="pinned")
    assert result == {"companion": "", "argv": []}


@pytest.mark.parametrize("launch", [None, ""])
def test_pin_without_command_is_refused(tmp_path, launch):
    proc, result = run(tmp_path, args=["--pin", "--as", "Eve"], launch=launch)
    assert proc.returncode == 2
    assert "WCLAUDE_PIN" in proc.stderr
    assert result is None


@pytest.mark.parametrize("args", [["--as", "Eve"], ["--pin", "--as", "Eve"]])
def test_every_start_is_a_master(tmp_path, args):
    _write_wrapper(tmp_path)
    run(tmp_path, args=args, launch="pinned")
    assert (tmp_path / "role").read_text() == "master"


# --- two crews, AC7: the installed copy resolves the install Claude Code uses here ------------


def _install(cache, version, marker):
    scripts = cache / version / "scripts"
    scripts.mkdir(parents=True)
    crew_py = scripts / "crew.py"
    crew_py.write_text(
        "import sys\n"
        "if sys.argv[1:2] == ['path']:\n"
        f"    print({marker!r})\n"
        "elif sys.argv[1:2] == ['members']:\n"
        f"    print({marker!r} + '\\tfrom ' + {version!r})\n"
    )
    return cache / version


def _installed_copy(tmp_path, installed):
    """wclaude copied alone (as install_launcher.py does), HOME with the cache and the file."""
    home = tmp_path / "home"
    cache = home / ".claude" / "plugins" / "cache" / "weside-ai" / "we"
    old = _install(cache, "8.6.1", "Old")
    new = _install(cache, "9.1.0", "New")
    project = tmp_path / "project"
    (project / "sub").mkdir(parents=True)
    data = {
        "version": 2,
        "plugins": {
            "we@weside-ai": [
                {"scope": "user", "installPath": str(new), "version": "9.1.0"},
                {
                    "scope": "project",
                    "projectPath": str(project),
                    "installPath": str(old),
                    "version": "8.6.1",
                },
            ]
        },
    }
    if installed is not None:
        (home / ".claude" / "plugins" / "installed_plugins.json").write_text(
            installed if isinstance(installed, str) else json.dumps(data)
        )
    bin_dir = tmp_path / "local-bin"
    bin_dir.mkdir()
    shutil.copy(SCRIPT, bin_dir / "wclaude")
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "claude").write_text("#!/bin/sh\nexit 0\n")
    (stub / "claude").chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CONFIG_DIR", "WCLAUDE_PIN")}
    env.update(HOME=str(home), PATH=f"{stub}{os.pathsep}{env['PATH']}")
    return bin_dir / "wclaude", project, env


def _menu(script, cwd, env):
    return subprocess.run(
        ["bash", str(script)],
        input="0\n",
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=20,
        check=False,
    ).stderr


def test_the_installed_copy_takes_the_project_scope_install_of_its_directory(tmp_path):
    script, project, env = _installed_copy(tmp_path, installed=True)
    # the project's own install (8.6.1), also from a subdirectory; elsewhere the user install
    assert "from 8.6.1" in _menu(script, project / "sub", env)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert "from 9.1.0" in _menu(script, elsewhere, env)


def test_an_unreadable_installed_plugins_file_ends_with_one_line_naming_it(tmp_path):
    script, project, env = _installed_copy(tmp_path, installed="{broken")
    err = _menu(script, project, env)
    assert err.count("installed_plugins.json not readable") == 1
    assert "from 9.1.0" not in err and "from 8.6.1" not in err
