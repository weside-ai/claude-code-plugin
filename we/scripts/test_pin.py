"""pin.sh: status, the no-op case, and the successor command outside tmux (nothing is started)."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "pin.sh"

pytestmark = pytest.mark.skipif(not shutil.which("bash"), reason="pin.sh is a bash script")


def run(tmp_path, *args, profile=False, profile_json=True, own_projects=False, **extra):
    home = tmp_path / "home"
    (home / ".claude" / "projects").mkdir(parents=True, exist_ok=True)
    (home / ".claude.json").write_text(
        json.dumps({"oauthAccount": {"emailAddress": "global@example.com"}})
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("TMUX", "CLAUDE_CONFIG_DIR", "WCLAUDE_PIN")
    }
    env.update(HOME=str(home), CLAUDE_CODE_SESSION_ID="sid-1", WESIDE_COMPANION="Ada", **extra)
    if profile:
        prof = tmp_path / "3-me_example.com"
        prof.mkdir()
        if profile_json:
            (prof / ".claude.json").write_text(
                json.dumps({"oauthAccount": {"emailAddress": "me@example.com"}})
            )
        if own_projects:
            (prof / "projects").mkdir()
        else:
            (prof / "projects").symlink_to(home / ".claude" / "projects")
        env["CLAUDE_CONFIG_DIR"] = str(prof)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=20,
        check=False,
    )


def test_status_unpinned_names_the_global_login(tmp_path):
    assert run(tmp_path).stdout.strip() == "unpinned · bills global@example.com"


def test_status_pinned_names_the_profile_account(tmp_path):
    out = run(tmp_path, "status", profile=True).stdout.strip()
    assert out == "pinned · bills me@example.com · profile 3-me_example.com"


def test_same_side_is_a_no_op(tmp_path):
    assert run(tmp_path, "off").stdout.startswith("already unpinned")


def test_off_outside_tmux_prints_the_resume_command(tmp_path):
    proc = run(tmp_path, "off", profile=True)
    assert proc.returncode == 0, proc.stderr
    assert (
        "env -u CLAUDE_CONFIG_DIR WESIDE_COMPANION=Ada WE_ROLE=master claude --name Ada --resume sid-1"
        in proc.stdout
    )


def test_on_needs_the_pin_command(tmp_path):
    proc = run(tmp_path, "on")
    assert proc.returncode == 1
    assert "WCLAUDE_PIN" in proc.stderr


def test_on_outside_tmux_uses_the_pin_command(tmp_path):
    proc = run(tmp_path, "on", WCLAUDE_PIN="/opt/pinned")
    assert "WE_ROLE=master /opt/pinned --name Ada --resume sid-1" in proc.stdout


def test_pinned_status_never_falls_back_to_the_global_login(tmp_path):
    out = run(tmp_path, profile=True, profile_json=False).stdout.strip()
    assert out == "pinned · bills unknown · profile 3-me_example.com"


def test_off_refuses_a_profile_with_its_own_transcripts(tmp_path):
    proc = run(tmp_path, "off", profile=True, own_projects=True)
    assert proc.returncode == 1
    assert "--resume will not find" in proc.stderr


FLAG = "--allow-dangerously-skip-permissions"


def _bypass_crew(tmp_path, on=True):
    (tmp_path / ".git").mkdir(exist_ok=True)
    (tmp_path / ".weside").mkdir(exist_ok=True)
    crew = {
        "version": 2,
        "roles": {"product": "po"},
        "members": {"po": {"name": "Ada"}},
        "launch": {"allow_bypass": on},
    }
    (tmp_path / ".weside" / "crew.json").write_text(json.dumps(crew))


@pytest.mark.parametrize("mode,extra", [("off", {}), ("on", {"WCLAUDE_PIN": "/opt/pinned"})])
def test_allow_bypass_reaches_the_successor_on_and_off(tmp_path, mode, extra):
    _bypass_crew(tmp_path)
    proc = run(tmp_path, mode, profile=mode == "off", **extra)
    assert proc.returncode == 0, proc.stderr
    assert f"--name Ada {FLAG} --resume sid-1" in proc.stdout


def test_without_allow_bypass_the_successor_has_no_flag(tmp_path):
    _bypass_crew(tmp_path, on=False)
    proc = run(tmp_path, "off", profile=True)
    assert FLAG not in proc.stdout


@pytest.mark.parametrize(
    "args,ok",
    [
        ("claude --bg", True),
        ("/opt/local/bin/claude -c", True),
        ("node /usr/lib/node_modules/@anthropic-ai/claude-code/cli.js --resume x", True),
        ("bun /opt/claude", True),
        ("node server.js", False),
        ("bash -c claude", False),
    ],
)
def test_the_claude_process_is_found_also_under_node(args, ok):
    proc = subprocess.run(["bash", str(SCRIPT), "--is-claude", args], check=False)
    assert (proc.returncode == 0) is ok
