"""Test support for the node scripts (``statusline.js``): the real node binary and the reaping of
every process a test leaves behind.

A test runs a node script under a throwaway ``HOME``. Called by name, ``node`` may be a version
manager's shim that looks up its toolchain under ``HOME`` and, not finding it there, calls
``node`` again: a fork chain without end (measured: thousands of processes within seconds).
``real_node`` resolves the binary once under the real environment, so a test never runs the shim.

The scripts start detached children (their own session), which no process group of the test
holds; ``reap`` finds them by their environment instead (``HOME`` under the test's directory),
waits for them to end, then stops and kills the rest.
"""

from __future__ import annotations

import contextlib
import functools
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

SETTLE_S = 5.0  # a detached refresh ends within this after its test (it only writes a cache)


@functools.lru_cache(maxsize=1)
def real_node() -> str | None:
    """The node binary itself (``process.execPath``), resolved under the real environment."""
    if not shutil.which("node"):
        return None
    try:
        out = subprocess.run(
            ["node", "-p", "process.execPath"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out if out and Path(out).is_file() else None


def _home_of(pid: int) -> str | None:
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return None
    for item in raw.split(b"\0"):
        if item.startswith(b"HOME="):
            return item[5:].decode(errors="replace")
    return None


def processes_under(home: Path) -> list[int]:
    """Live processes (not this one) whose ``HOME`` is ``home`` or below it; empty without
    ``/proc``."""
    proc = Path("/proc")
    if not proc.is_dir():
        return []
    root = str(home)
    found = []
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        value = _home_of(int(entry.name))
        if value is not None and (value == root or value.startswith(root + os.sep)):
            found.append(int(entry.name))
    return found


def _signal_all(pids: list[int], sig: int) -> None:
    for pid in pids:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, sig)


def reap(home: Path, settle: float = SETTLE_S) -> int:
    """How many processes under ``home`` outlived ``settle`` seconds; those are stopped (so a
    fork chain cannot outrun the kill) and killed until none is left."""
    deadline = time.monotonic() + settle
    left = processes_under(home)
    while left and time.monotonic() < deadline:
        time.sleep(0.1)
        left = processes_under(home)
    seen = set(left)
    for _ in range(1_000):
        if not left:
            break
        _signal_all(left, signal.SIGSTOP)
        _signal_all(left, signal.SIGKILL)
        time.sleep(0.05)
        left = processes_under(home)
        seen.update(left)
    return len(seen)
