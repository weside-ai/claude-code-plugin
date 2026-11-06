"""Pins scripts/check_compat_line.py: a PR touching what a second repo runs names its check."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).with_name("check_compat_line.py")
_spec = importlib.util.spec_from_file_location("check_compat_line", SCRIPT)
ccl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ccl)

LINE = "Compat repo checked: no, the change only renames a heading"


def test_a_skill_change_without_the_line_fails():
    why = ccl.check("## Summary\nx\n", ["we/skills/master/SKILL.md", "README.md"])
    assert why is not None and "we/skills/master/SKILL.md" in why
    assert "`Compat repo checked: yes|no, <why>`" in why


def test_each_trigger_path_counts():
    for path in ("we/process/L0.md", "we/roles/master.md", "we/scripts/crew.py"):
        assert ccl.check("", [path]) is not None, path


def test_the_line_with_a_reason_passes():
    assert ccl.check(f"## Summary\n\n{LINE}\n", ["we/skills/pr/SKILL.md"]) is None
    assert (
        ccl.check("compat repo checked: YES, ran /we:master there\n", ["we/process/L0.md"]) is None
    )


def test_the_line_without_a_reason_fails():
    why = ccl.check("Compat repo checked: yes\n", ["we/process/L0.md"])
    assert why == "`Compat repo checked:` needs its reason after yes/no"


def test_the_line_inside_fenced_code_does_not_count():
    body = f"```text\n{LINE}\n```\n"
    assert ccl.check(body, ["we/skills/pr/SKILL.md"]) is not None


def test_other_diffs_need_no_line():
    files = ["docs/README.md", "we/hooks/automerge_gate.py", "we/scripts/board.py"]
    assert ccl.check("", files) is None


def test_main_reads_the_event_and_the_diff(tmp_path):
    repo = tmp_path / "r"
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@x.invalid"]
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "root"], check=True)
    subprocess.run([*git, "checkout", "-q", "-b", "feat"], check=True)
    (repo / "we" / "skills" / "x").mkdir(parents=True)
    (repo / "we" / "skills" / "x" / "SKILL.md").write_text("x\n")
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "skill"], check=True)
    event = tmp_path / "event.json"
    for body, code in (("no line", 1), (LINE, 0)):
        event.write_text(json.dumps({"pull_request": {"body": body, "base": {"ref": "main"}}}))
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--event", str(event), "--base", "main"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == code, done.stdout + done.stderr
