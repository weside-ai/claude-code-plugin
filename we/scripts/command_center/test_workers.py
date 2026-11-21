"""`worker_supervisor.py status --json` over fixture rows on stdin, and the red rows it feeds."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import ci_state  # noqa: E402
from test_open_ends import UNTIL  # noqa: E402

SUPERVISOR = HERE.parent / "worker_supervisor.py"
DEAD_PID = "4194303"  # above every pid_max default: no process holds it
FIELDS = ["name", "id", "pid", "state", "alive", "last", "end", "time_limit", "window", "resume"]
FIELDS += ["waits"]


def transcript(home: Path, sid: str, entry: dict) -> None:
    folder = home / ".claude" / "projects" / "-tmp-tree"
    folder.mkdir(parents=True, exist_ok=True)
    line = {"type": "assistant", "timestamp": "2026-04-01T11:40:00Z", **entry}
    (folder / f"{sid}.jsonl").write_text(json.dumps(line) + "\n")


def run(home: Path, rows: list, *extra: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "HOME": str(home), "WE_WORKER_STATE_DIR": str(home / "workers")}
    return subprocess.run(
        [sys.executable, str(SUPERVISOR), "status", *extra],
        input=json.dumps(rows),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )


def row(name, sid, pid):
    return {"name": name, "sessionId": sid, "pid": pid, "kind": "background", "state": "idle"}


def test_dead_and_limited_workers(tmp_path):
    rows = [
        row("w-exit", "s1", DEAD_PID),
        row("w-limit", "s2", DEAD_PID),
        row("w-auth", "s3", DEAD_PID),
        row("w-live", "s4", str(os.getpid())),
    ]
    transcript(tmp_path, "s1", {"message": {"content": [{"type": "text", "text": "done"}]}})
    transcript(tmp_path, "s2", {"isApiErrorMessage": True, "error": "rate_limit"})
    transcript(tmp_path, "s3", {"isApiErrorMessage": True, "error": "authentication_failed"})
    text_before = run(tmp_path, rows).stdout
    doc = json.loads(run(tmp_path, rows, "--json").stdout)
    assert doc["schema_version"] == 1
    assert [list(w) for w in doc["workers"]] == [FIELDS] * 4  # the snapshot of its fields
    red = ci_state.worker_rows(doc["workers"], UNTIL)
    assert [(r["item"], r["classes"]) for r in red] == [
        ("w-exit", ["exited"]),
        ("w-limit", ["usage-limit"]),
        ("w-auth", ["auth"]),
    ]
    assert "we-worker w-limit --bg --resume s2" in red[1]["title"]
    assert red[0]["title"] == "exited"
    # the text of `we-worker status` stays what it printed, line for line
    assert run(tmp_path, rows).stdout == text_before
    lines = text_before.splitlines()
    assert lines[0] == f"s1 w-exit pid={DEAD_PID} exited(idle) last=11:40"
    assert lines[2] == "  resume after the reset: we-worker w-limit --bg --resume s2"
    assert lines[-1] == f"s4 w-live pid={os.getpid()} idle last=-"
