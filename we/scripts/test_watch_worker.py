"""watch-worker.sh against a real git worktree, with second-scale timings."""

import json
import os
import subprocess
import threading
import time
from pathlib import Path

SCRIPT = Path(__file__).parent / "watch-worker.sh"


def _git(wt, *args):
    subprocess.run(["git", "-C", str(wt), *args], check=True, capture_output=True)


def _repo(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    _git(wt, "init", "-q")
    _git(
        wt,
        "-c",
        "user.email=a@b",
        "-c",
        "user.name=a",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "base",
    )
    return wt


def _run(wt, interval="0.2", stall="60", max_s="60", during=None):
    env = {
        **os.environ,
        "WATCH_WORKER_INTERVAL": interval,
        "WATCH_WORKER_STALL": stall,
        "WATCH_WORKER_MAX": max_s,
    }
    if during:
        threading.Timer(0.5, during).start()
    res = subprocess.run(
        ["bash", str(SCRIPT), str(wt), "dev-X"],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )
    return res.returncode, res.stdout.splitlines()


def test_a_commit_ends_the_watch_with_its_line(tmp_path):
    wt = _repo(tmp_path)
    code, out = _run(
        wt,
        during=lambda: _git(
            wt,
            "-c",
            "user.email=a@b",
            "-c",
            "user.name=a",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "phase 1 done",
        ),
    )
    assert code == 0
    assert len(out) == 1 and out[0].endswith(" phase 1 done")


def test_an_unchanged_tree_is_a_stall(tmp_path):
    code, out = _run(_repo(tmp_path), stall="1")
    assert (code, out) == (1, ["STALL 0 min: dev-X"])


def test_a_changing_tree_without_commit_hits_the_lifetime_cap(tmp_path):
    wt = _repo(tmp_path)
    (wt / "f.txt").write_text("start")
    _git(wt, "add", "f.txt")
    stop = time.time() + 3

    def edit():
        n = 0
        while time.time() < stop:
            (wt / "f.txt").write_text(str(n))
            n += 1
            time.sleep(0.1)

    threading.Thread(target=edit, daemon=True).start()
    code, out = _run(wt, stall="1", max_s="2")
    assert (code, out) == (3, ["alive: dev-X · no commit in 0 min, tree changing"])


def test_a_removed_worktree_ends_the_watch(tmp_path):
    wt = _repo(tmp_path)
    code, out = _run(wt, during=lambda: subprocess.run(["rm", "-rf", str(wt)], check=True))
    assert (code, out) == (2, [f"gone: dev-X ({wt} is no git worktree)"])


def _stub_claude(tmp_path, rows):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "claude"
    stub.write_text(f"#!/bin/sh\necho '{json.dumps(rows)}'\n")
    stub.chmod(0o755)
    return {"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}


def test_an_ended_process_worker_exits_4(tmp_path, monkeypatch):
    wt = _repo(tmp_path)
    (wt / ".git" / "we-worker.json").write_text(json.dumps({"name": "dev-X", "lead": "L"}))
    for key, value in _stub_claude(tmp_path, []).items():
        monkeypatch.setenv(key, value)
    assert _run(wt) == (4, ["exited: dev-X"])


def test_a_running_process_worker_keeps_watching(tmp_path, monkeypatch):
    wt = _repo(tmp_path)
    (wt / ".git" / "we-worker.json").write_text(json.dumps({"name": "dev-X", "lead": "L"}))
    for key, value in _stub_claude(tmp_path, [{"id": "b1", "name": "dev-X"}]).items():
        monkeypatch.setenv(key, value)
    assert _run(wt, stall="1") == (1, ["STALL 0 min: dev-X"])
