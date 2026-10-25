"""wclaude against a stub `claude` on PATH that records its environment and argv."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "wclaude"

pytestmark = pytest.mark.skipif(not shutil.which("bash"), reason="wclaude is a bash script")

COUNCIL = {
    "members": {
        "po": {"name": "Ada", "role": "product_owner", "title": "Product Owner"},
        "arch": {"name": "Bo", "role": "architect"},
        "generic": {"role": "scrum_master"},
    }
}


def run(tmp_path, args=(), stdin="", council=COUNCIL):
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    record = tmp_path / "record.json"
    stub = stub_dir / "claude"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "json.dump({'companion': os.environ.get('WESIDE_COMPANION'), 'argv': sys.argv[1:]},"
        f" open({str(record)!r}, 'w'))\n"
    )
    stub.chmod(0o755)
    project = tmp_path / "project"
    cwd = project / "sub" / "dir"
    cwd.mkdir(parents=True, exist_ok=True)
    if council is not None:
        (project / ".weside").mkdir(exist_ok=True)
        (project / ".weside" / "council.json").write_text(json.dumps(council))
    env = {
        **os.environ,
        "PATH": f"{stub_dir}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "WESIDE_COMPANION": "Stale",
    }
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


def test_menu_lists_title_else_role_and_skips_nameless(tmp_path):
    proc, result = run(tmp_path, stdin="1\n")
    assert proc.returncode == 0, proc.stderr
    assert "Ada" in proc.stderr
    assert "Product Owner" in proc.stderr
    assert "architect" in proc.stderr
    assert "scrum_master" not in proc.stderr
    assert " 3) other name..." in proc.stderr
    assert "~/project/.weside/council.json" in proc.stderr
    assert result == {"companion": "Ada", "argv": []}


def test_menu_pick_second(tmp_path):
    _, result = run(tmp_path, stdin="2\n")
    assert result["companion"] == "Bo"


def test_other_name_prompt(tmp_path):
    _, result = run(tmp_path, stdin="3\n  Cleo \n")
    assert result["companion"] == "Cleo"


def test_typed_name(tmp_path):
    _, result = run(tmp_path, args=["--resume"], stdin="Dana\n")
    assert result == {"companion": "Dana", "argv": ["--resume"]}


def test_dash_c_skips_menu(tmp_path):
    proc, result = run(tmp_path, args=["-c", "Eve", "-p", "hi"])
    assert proc.returncode == 0, proc.stderr
    assert "other name" not in proc.stderr
    assert result == {"companion": "Eve", "argv": ["-p", "hi"]}


def test_dash_c_without_name_is_usage_error(tmp_path):
    proc, result = run(tmp_path, args=["-c"])
    assert proc.returncode == 2
    assert result is None


def test_zero_clears_the_pin(tmp_path):
    proc, result = run(tmp_path, args=["--continue"], stdin="0\n")
    assert proc.returncode == 0, proc.stderr
    assert result == {"companion": "", "argv": ["--continue"]}
    assert "(no companion)" in proc.stderr


def test_arguments_with_spaces_pass_unchanged(tmp_path):
    args = ["-p", "two words", "", "a'quote", "--model", "x y"]
    _, result = run(tmp_path, args=args, stdin="1\n")
    assert result["argv"] == args


@pytest.mark.parametrize("choice", ["4\n", "99\n", "\n"])
def test_out_of_range_or_empty_choice_refused(tmp_path, choice):
    proc, result = run(tmp_path, stdin=choice)
    assert proc.returncode == 1
    assert result is None


def test_closed_stdin_refused(tmp_path):
    proc, result = run(tmp_path, stdin="")
    assert proc.returncode == 1
    assert result is None


def test_without_council_offers_name_and_zero(tmp_path):
    proc, result = run(tmp_path, council=None, stdin="1\nFay\n")
    assert "no .weside/council.json found" in proc.stderr
    assert result["companion"] == "Fay"


def test_broken_council_still_offers_menu(tmp_path):
    (tmp_path / "project" / ".weside").mkdir(parents=True)
    (tmp_path / "project" / ".weside" / "council.json").write_text("{not json")
    proc, result = run(tmp_path, council=None, stdin="Gus\n")
    assert "cannot read" in proc.stderr
    assert result["companion"] == "Gus"


def write_profile(tmp_path, filename):
    profiles = tmp_path / ".claude" / "we" / "profiles"
    path = profiles / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"permissions": {"deny": ["Bash(gh pr merge*)"]}}))
    return path


def test_profile_passed_as_settings_before_user_args(tmp_path):
    path = write_profile(tmp_path, "ada.json")
    proc, result = run(tmp_path, args=["--resume"], stdin="1\n")
    assert proc.returncode == 0, proc.stderr
    assert result == {"companion": "Ada", "argv": ["--settings", str(path), "--resume"]}
    assert "--settings " + str(path) in proc.stderr


def test_profile_for_dash_c_and_typed_name(tmp_path):
    path = write_profile(tmp_path, "eve.json")
    _, result = run(tmp_path, args=["-c", "EVE", "-p", "hi"])
    assert result["argv"] == ["--settings", str(path), "-p", "hi"]
    _, result = run(tmp_path, stdin="Eve\n")
    assert result["argv"] == ["--settings", str(path)]


def test_no_profile_file_leaves_argv_unchanged(tmp_path):
    write_profile(tmp_path, "bo.json")
    proc, result = run(tmp_path, args=["--resume"], stdin="1\n")
    assert result == {"companion": "Ada", "argv": ["--resume"]}
    assert "--settings" not in proc.stderr


def test_choice_zero_never_takes_a_profile(tmp_path):
    write_profile(tmp_path, ".json")
    write_profile(tmp_path, "0.json")
    _, result = run(tmp_path, stdin="0\n")
    assert result == {"companion": "", "argv": []}


@pytest.mark.parametrize("name", ["../escape", "sub/ada", ".hidden", ".."])
def test_traversal_name_starts_without_profile(tmp_path, name):
    write_profile(tmp_path, "ada.json")
    write_profile(tmp_path, ".hidden.json")
    write_profile(tmp_path, "sub/ada.json")
    write_profile(tmp_path, "../escape.json")
    write_profile(tmp_path, "..json")
    proc, result = run(tmp_path, args=["-c", name])
    assert proc.returncode == 0, proc.stderr
    assert result == {"companion": name, "argv": []}
    assert "--settings" not in proc.stderr
