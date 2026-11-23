"""event_poller.py: one poller per project (AC 6), its environment, state and heartbeat."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import event_poller as ep  # noqa: E402
import test_event_routes as ter  # noqa: E402  (its crew and project builder)

SCRIPT = HERE / "event_poller.py"


def env_for(tmp: Path) -> dict:
    return {
        "HOME": str(tmp),
        "PATH": os.environ["PATH"],
        "WE_STATE_DIR": str(tmp / "state"),
        "CLAUDE_CODE_MESSAGING_TOKEN": "secret-token",
        "CLAUDE_CODE_MESSAGING_SOCKET": str(tmp / "sock"),
        "CLAUDE_CONFIG_DIR": str(tmp / "cfg"),
    }


def wait_for(predicate, timeout: float = 10.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_one_poller_per_project(tmp_path):
    """Two starts at once leave one poller; a second `run` exits on the held lock."""
    root = ter.project(tmp_path)
    env = env_for(tmp_path)
    folder = ep.events_dir(root, env)
    starts = [
        subprocess.Popen(
            [sys.executable, str(SCRIPT), "ensure", "--from", str(root)],
            env=env,
            stdout=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    said = [p.communicate(timeout=30)[0].strip() for p in starts]
    started = [s for s in said if s.startswith("events: poller ") and s.endswith(" started")]
    assert started, said
    pids = [int(s.split()[2]) for s in started]
    try:
        assert wait_for(lambda: ep.lock_held(folder))
        assert wait_for((folder / "heartbeat.json").exists)
        # a start that lost the race exits on the lock; the winner keeps running
        assert wait_for(lambda: sum(1 for p in pids if _alive(p)) == 1)
        assert ep.ensure(root, env) == "events: poller runs"
        second = subprocess.run(
            [sys.executable, str(SCRIPT), "run", "--root", str(root), "--rounds", "1"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert (second.returncode, second.stderr.strip()) == (
            0,
            "events: another poller holds the lock",
        )
        once = subprocess.run(
            [sys.executable, str(SCRIPT), "once", "--from", str(root)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert once.returncode == 1
        winner = next(p for p in pids if _alive(p))
        environ = Path(f"/proc/{winner}/environ")
        if environ.exists():
            names = {kv.split("=", 1)[0] for kv in environ.read_bytes().decode().split("\0") if kv}
            assert not any(n.startswith("CLAUDE") for n in names)
            assert names <= set(ep.KEEP_ENV)
    finally:
        for pid in pids:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(pid, signal.SIGTERM)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # a zombie child of a finished start counts as gone
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return True


def test_clean_env_keeps_home_path_lang_and_the_state_dir_only(tmp_path):
    env = env_for(tmp_path)
    env["GH_TOKEN"] = "x"
    assert ep.clean_env(env) == {
        "HOME": str(tmp_path),
        "PATH": os.environ["PATH"],
        "WE_STATE_DIR": str(tmp_path / "state"),
        "LANG": "C.UTF-8",
    }


def test_ensure_is_off_without_an_events_block(tmp_path):
    root = tmp_path / "repo"
    (root / ".weside").mkdir(parents=True)
    (root / ".weside" / "config.json").write_text(json.dumps({"stack": []}))
    assert ep.ensure(root, env_for(tmp_path)) == "events: off (no events: block)"


def test_once_writes_state_and_heartbeat(tmp_path):
    root = ter.project(tmp_path)
    env = env_for(tmp_path)
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "once", "--from", str(root)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    beat = json.loads(out.stdout)
    assert beat["routes"]["release_pr_blocked"] == ["tester"] and beat["interval_s"] == 300
    folder = ep.events_dir(root, env)
    assert json.loads((folder / "state.json").read_text())["seq"] == 0
    status = subprocess.run(
        [sys.executable, str(SCRIPT), "status", "--from", str(root)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert "route release_pr_blocked -> tester" in status.stdout
    path = subprocess.run(
        [sys.executable, str(SCRIPT), "path", "--delta", "--from", str(root)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert path.stdout.strip() == str(folder / "delta.jsonl")


def test_sessions_source_runs_on_its_own_interval(tmp_path):
    """The loop ticks at the sessions interval (60 s); GitHub and the local checks keep theirs
    (300 s): over five minutes six samples of the sessions, two main rounds."""
    root = ter.project(tmp_path, {})
    config = root / ".weside" / "config.json"
    config.write_text(
        json.dumps(
            {
                "events": {
                    "sources": {"sessions": {"interval_s": 60}},
                    "local_checks": ["true"],
                    "routes": {},
                }
            }
        )
    )
    now = [ter.NOW]
    samples: list[float] = []
    calls = ter.Calls()

    def sessions():
        samples.append(now[0])
        return []

    p = ep.Poller(
        root, tmp_path / "events", clock=lambda: now[0], run=calls, env={}, sessions=sessions
    )
    beats = []
    for _ in range(6):
        beats.append(p.round())
        now[0] += 60
    assert len(samples) == 6
    assert len([a for a in calls.argv if a[:2] == ["sh", "-c"]]) == 2
    assert {b["interval_s"] for b in beats} == {60}
    assert beats[0]["poll_interval_s"] == 300 and beats[0]["sessions_interval_s"] == 60
