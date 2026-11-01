"""pin.sh: status, the no-op case, and the successor command outside tmux (nothing is started)."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "pin.sh"

pytestmark = pytest.mark.skipif(not shutil.which("bash"), reason="pin.sh is a bash script")


def run(tmp_path, *args, profile=False, **extra):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
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
        prof.mkdir(exist_ok=True)
        (prof / ".claude.json").write_text(
            json.dumps({"oauthAccount": {"emailAddress": "me@example.com"}})
        )
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
