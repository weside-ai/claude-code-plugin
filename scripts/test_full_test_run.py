"""full_test_run.py: a full local run waits for the test slot, names its holder, and reports its
peak; CI and a nested run take no slot."""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "full_test_run.py"

pytestmark = pytest.mark.skipif(not Path("/proc").is_dir(), reason="the slot reads /proc")


def run(lock: Path, *command: str, **env_extra: str) -> subprocess.Popen:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("GITHUB_ACTIONS", "WESIDE_TESTS_LOCK_HELD")
    }
    env.update({"WESIDE_TESTS_LOCK": str(lock), **env_extra})
    return subprocess.Popen(
        [sys.executable, str(SCRIPT), "--", *command],
        env=env,
        stderr=subprocess.PIPE,
        text=True,
    )


def held(lock: Path, note: str) -> int:
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o666)
    fcntl.flock(fd, fcntl.LOCK_EX)
    os.pwrite(fd, note.encode(), 0)
    return fd


def test_a_run_waits_for_the_slot_and_names_its_holder(tmp_path):
    lock = tmp_path / "tests.lock"
    fd = held(lock, "other-repo: pytest (pid 1, since 10:00:00)")
    proc = run(lock, sys.executable, "-c", "pass")
    time.sleep(1.0)
    assert proc.poll() is None, "the run did not wait for the held slot"
    os.close(fd)  # release
    _, err = proc.communicate(timeout=30)
    assert proc.returncode == 0, err
    lines = err.splitlines()
    assert lines[0] == "waiting for test slot (held by other-repo: pytest (pid 1, since 10:00:00))"
    assert lines[1].startswith("got test slot after ")
    assert lines[-1].startswith("peak: ") and lines[-1].endswith(" MiB RSS")


def test_the_peak_counts_the_command_s_process_tree(tmp_path):
    child = "import subprocess, sys; subprocess.run(['sleep', '1.5']); sys.exit(3)"
    proc = run(tmp_path / "tests.lock", sys.executable, "-c", child)
    _, err = proc.communicate(timeout=30)
    assert proc.returncode == 3, "the command's exit code passes through"
    peak = err.splitlines()[-1]
    count = int(peak.split()[1])
    assert count >= 2, peak


@pytest.mark.parametrize("env", [{"GITHUB_ACTIONS": "true"}, {"WESIDE_TESTS_LOCK_HELD": "self"}])
def test_ci_and_a_nested_run_take_no_slot(tmp_path, env):
    lock = tmp_path / "tests.lock"
    fd = held(lock, "holder")
    if env.get("WESIDE_TESTS_LOCK_HELD") == "self":
        env = {"WESIDE_TESTS_LOCK_HELD": str(os.getpid())}
    try:
        proc = run(lock, sys.executable, "-c", "pass", **env)
        _, err = proc.communicate(timeout=10)
    finally:
        os.close(fd)
    assert proc.returncode == 0 and "waiting" not in err, err
