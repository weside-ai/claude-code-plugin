#!/usr/bin/env python3
"""A full local test run takes the host's test slot, then reports its peak.

Several sessions on one host share its memory, and a full ``pytest we scripts`` forks node and
shell children per test. A full local run therefore waits for the test slot, one ``flock`` over
``$WESIDE_TESTS_LOCK`` (default ``/tmp/weside-tests.lock``, the slot a host's other heavy test runs
take too): a run that has to wait says who holds the slot, then waits as long as it takes. The
kernel drops the lock when its holder dies. A run nested in one that holds the slot
(``WESIDE_TESTS_LOCK_HELD`` = the holder's pid, alive) does not wait for itself; CI
(``GITHUB_ACTIONS=true``) takes no slot.

While the command runs, its process tree is sampled every ``SAMPLE_S`` seconds; at the end one
stderr line names the peak process count and summed RSS (``peak: N processes, M MiB RSS``).

Usage:
  python3 scripts/full_test_run.py                  the full run: python3 -m pytest -q we scripts
  python3 scripts/full_test_run.py -- <command>...  any other command under the slot
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOCK_ENV = "WESIDE_TESTS_LOCK"
DEFAULT_LOCK = "/tmp/weside-tests.lock"
HELD_ENV = f"{LOCK_ENV}_HELD"
FULL_RUN = [sys.executable, "-m", "pytest", "-q", "we", "scripts"]
SAMPLE_S = 0.5


def lock_path() -> Path:
    return Path(os.environ.get(LOCK_ENV) or DEFAULT_LOCK)


def _held_by_caller() -> bool:
    holder = os.environ.get(HELD_ENV, "")
    if holder.isdigit() and int(holder) > 0:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(int(holder), 0)
            return True
    return False


@contextlib.contextmanager
def slot(label: str):
    """Hold the test slot for the body; while another run holds it, say whose and wait."""
    if os.environ.get("GITHUB_ACTIONS") == "true" or _held_by_caller():
        yield
        return
    fd = os.open(lock_path(), os.O_RDWR | os.O_CREAT, 0o666)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            note = os.pread(fd, 400, 0).decode(errors="replace").strip() or "unknown"
            print(f"waiting for test slot (held by {note})", file=sys.stderr, flush=True)
            start = time.monotonic()
            fcntl.flock(fd, fcntl.LOCK_EX)
            print(f"got test slot after {time.monotonic() - start:.0f}s", file=sys.stderr)
        note = f"{label} (pid {os.getpid()}, since {time.strftime('%H:%M:%S')})\n"
        os.ftruncate(fd, 0)
        os.pwrite(fd, note.encode(), 0)
        yield
    finally:
        os.close(fd)


def _children() -> dict[int, list[int]]:
    tree: dict[int, list[int]] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        with contextlib.suppress(OSError, ValueError, IndexError):
            stat = (entry / "stat").read_text()
            ppid = int(stat.rsplit(")", 1)[1].split()[1])
            tree.setdefault(ppid, []).append(int(entry.name))
    return tree


def _rss_kib(pid: int) -> int:
    with contextlib.suppress(OSError, ValueError):
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    return 0


def tree_of(root: int) -> list[int]:
    """``root`` and every descendant (by parent pid) alive now; empty without ``/proc``."""
    if not Path("/proc").is_dir():
        return []
    tree, out, todo = _children(), [], [root]
    while todo:
        pid = todo.pop()
        out.append(pid)
        todo += tree.get(pid, [])
    return out


class Peak:
    """The largest process count and summed RSS of a process tree, sampled in a thread."""

    def __init__(self, root: int) -> None:
        self.root, self.processes, self.rss_kib = root, 0, 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            pids = tree_of(self.root)
            self.processes = max(self.processes, len(pids))
            self.rss_kib = max(self.rss_kib, sum(_rss_kib(p) for p in pids))
            self._stop.wait(SAMPLE_S)

    def __enter__(self) -> Peak:
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        self._thread.join()


def main(argv: list[str]) -> int:
    command = argv[argv.index("--") + 1 :] if "--" in argv else FULL_RUN
    if not command:
        print(__doc__.strip().splitlines()[-2], file=sys.stderr)
        return 2
    with slot(f"{REPO.name}: {' '.join(command)[:80]}"):
        env = {**os.environ, HELD_ENV: str(os.getpid())}
        child = subprocess.Popen(command, cwd=REPO, env=env)
        with Peak(child.pid) as peak:
            code = child.wait()
    print(
        f"peak: {peak.processes} processes, {peak.rss_kib // 1024} MiB RSS",
        file=sys.stderr,
        flush=True,
    )
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
