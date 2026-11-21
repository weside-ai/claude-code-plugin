#!/usr/bin/env python3
"""A full local test run takes the host's test slot, then reports its peak.

Several sessions on one host share its memory, and a full ``pytest we scripts`` forks node and
shell children per test. A full local run therefore waits for the host's test slot through the
plugin's one holder, ``we/scripts/slot_lock.py`` ``hold`` (its docstring owns the lock path, the
holder's note and who takes no slot): a run that has to wait says who holds the slot, then waits as
long as it takes.

While the command runs, its process tree is sampled every ``SAMPLE_S`` seconds; at the end one
stderr line names the peak process count and summed RSS (``peak: N processes, M MiB RSS``).

Usage:
  python3 scripts/full_test_run.py                  the full run: python3 -m pytest -q we scripts
  python3 scripts/full_test_run.py -- <command>...  any other command under the slot
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "we" / "scripts"))
import slot_lock  # noqa: E402

FULL_RUN = [sys.executable, "-m", "pytest", "-q", "we", "scripts"]
SAMPLE_S = 0.5


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
    with slot_lock.hold(f"{REPO.name}: {' '.join(command)[:80]}"):
        env = {**os.environ, slot_lock.HELD_ENV: str(os.getpid())}
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
