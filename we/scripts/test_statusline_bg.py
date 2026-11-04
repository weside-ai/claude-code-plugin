"""statusline.js --refresh-bg against a stub `claude agents --json` (shape recorded from Claude Code)."""

import json
import os
import re
import subprocess
import time
from pathlib import Path

import pytest
from node_test_procs import real_node, reap

SCRIPT = Path(__file__).parent / "statusline.js"

NODE = real_node()

pytestmark = pytest.mark.skipif(NODE is None, reason="statusline.js needs node")


@pytest.fixture(autouse=True)
def _no_process_outlives_its_test(tmp_path):
    """Every process a test started (detached refreshes too) ends with it: 0 left, else red."""
    yield
    left = reap(tmp_path)
    assert left == 0, f"{left} processes with HOME under {tmp_path} outlived the test"


# Recorded 2026-10-30 from `claude agents --json`; re-record when a release renames these fields.
AGENTS = [
    {"kind": "interactive", "sessionId": "i1", "status": "busy"},
    {"kind": "background", "sessionId": "b1", "state": "working", "status": "busy"},
    {"kind": "background", "sessionId": "b2", "state": "idle", "status": "idle"},
]


def refresh(tmp_path):
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / "claude"
    stub.write_text(f"#!/bin/sh\necho '{json.dumps(AGENTS)}'\n")
    stub.chmod(0o755)
    (tmp_path / ".claude").mkdir()
    lock = tmp_path / ".claude" / ".we-statusline-bg-cache.json.lock"
    lock.touch()
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "PATH": f"{stub_dir}{os.pathsep}{os.environ['PATH']}",
    }
    subprocess.run([NODE, str(SCRIPT), "--refresh-bg"], env=env, timeout=20, check=True)
    return json.loads((tmp_path / ".claude" / ".we-statusline-bg-cache.json").read_text()), lock


def test_refresh_keeps_background_sessions_with_their_working_flag(tmp_path):
    cache, _ = refresh(tmp_path)
    assert cache["sessions"] == [
        {"sessionId": "b1", "working": True},
        {"sessionId": "b2", "working": False},
    ]
    assert time.time() * 1000 - cache["ts"] < 20_000


def test_refresh_releases_the_lock(tmp_path):
    _, lock = refresh(tmp_path)
    assert not lock.exists()


SPAWN = re.compile(r"\b(spawn|spawnSync|execFileSync|execFile|fork)\(\s*([^,\s)]+)")


def test_the_script_restarts_itself_through_its_own_binary_never_by_name():
    """A self-start by the name ``node`` goes through PATH and may hit a version manager's shim,
    which under another HOME calls ``node`` again without end; ``process.execPath`` cannot."""
    text = SCRIPT.read_text(encoding="utf-8")
    calls = SPAWN.findall(text)
    assert calls, "no spawn found: the pattern no longer matches the script"
    by_name = [(fn, first) for fn, first in calls if first.strip("'\"`") in ("node", "nodejs")]
    assert by_name == [], f"started by name: {by_name}"
    selves = [first for fn, first in calls if fn == "spawn"]
    assert selves and all(first == "process.execPath" for first in selves), selves
