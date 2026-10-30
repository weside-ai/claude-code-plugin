"""statusline.js --refresh-bg against a stub `claude agents --json` (shape recorded from Claude Code)."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "statusline.js"

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="statusline.js needs node")

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
    subprocess.run(["node", str(SCRIPT), "--refresh-bg"], env=env, timeout=20, check=True)
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
