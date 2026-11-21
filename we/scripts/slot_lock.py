#!/usr/bin/env python3
"""The host's test slot: one `flock` over `$WESIDE_TESTS_LOCK` (default `/tmp/weside-tests.lock`).

Every heavy run on the host takes the same slot: the plugin's full test run
(`scripts/full_test_run.py`), a cold-start harness, and the gates of other repos on the host. This
module is the plugin's one holder (`hold`) and its one reader of who waits (`waiters`).

The note: a holder that takes the slot rewrites the lock file to exactly one line,
`<label> (pid N, since HH:MM:SS[, until HH:MM])` (`note`). `until` is the announced end, only when
the holder knows its duration. Waiters on the host parse exactly this line, so its shape does not
change. A holder that takes the `flock` itself leaves the previous holder's note (a dead pid) for
every waiter to read; that is why every holder goes through `hold`.

Who waits comes from the kernel, not from a note: `/proc/locks` lists every process blocked in
`flock` on the slot's inode as a `->` line with its pid (`waiters`). A waiter that polls with
`LOCK_NB` in a loop is not blocked in the kernel and is not listed; `hold` blocks.

Usage:
  slot_lock.py holder              the note of the current holder, exit 1 when the slot is free
  slot_lock.py waiters             one pid per process blocked on the slot
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import sys
import time
from collections.abc import Iterator
from pathlib import Path

LOCK_ENV = "WESIDE_TESTS_LOCK"
DEFAULT_LOCK = "/tmp/weside-tests.lock"
HELD_ENV = f"{LOCK_ENV}_HELD"
PROC_LOCKS = Path("/proc/locks")


def lock_path() -> Path:
    return Path(os.environ.get(LOCK_ENV) or DEFAULT_LOCK)


def note(label: str, pid: int, since: float, until: float | None = None) -> str:
    """The holder's line: `<label> (pid N, since HH:MM:SS[, until HH:MM])` plus a newline."""
    text = f"{label} (pid {pid}, since {time.strftime('%H:%M:%S', time.localtime(since))}"
    if until is not None:
        text += f", until {time.strftime('%H:%M', time.localtime(until))}"
    return text + ")\n"


def held_by_caller() -> bool:
    """A parent holds the slot (`WESIDE_TESTS_LOCK_HELD` = its pid, alive): no wait for itself."""
    holder = os.environ.get(HELD_ENV, "")
    if holder.isdigit() and int(holder) > 0:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(int(holder), 0)
            return True
    return False


@contextlib.contextmanager
def hold(label: str, expected_minutes: float | None = None) -> Iterator[None]:
    """Hold the slot for the body. While another process holds it, print whose note on stderr and
    block until it is free; then write this holder's `note` (with `until` when
    `expected_minutes` is given) and export `WESIDE_TESTS_LOCK_HELD` to children. CI
    (`GITHUB_ACTIONS=true`) and a child of a holder take no slot. The kernel drops the lock when
    the holder dies."""
    if os.environ.get("GITHUB_ACTIONS") == "true" or held_by_caller():
        yield
        return
    fd = os.open(lock_path(), os.O_RDWR | os.O_CREAT, 0o666)
    before = os.environ.get(HELD_ENV)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            held = os.pread(fd, 400, 0).decode(errors="replace").strip() or "unknown"
            print(f"waiting for test slot (held by {held})", file=sys.stderr, flush=True)
            start = time.monotonic()
            fcntl.flock(fd, fcntl.LOCK_EX)
            print(f"got test slot after {time.monotonic() - start:.0f}s", file=sys.stderr)
        now = time.time()
        until = now + expected_minutes * 60 if expected_minutes else None
        os.ftruncate(fd, 0)
        os.pwrite(fd, note(label, os.getpid(), now, until).encode(), 0)
        os.environ[HELD_ENV] = str(os.getpid())
        yield
    finally:
        if before is None:
            os.environ.pop(HELD_ENV, None)
        else:
            os.environ[HELD_ENV] = before
        os.close(fd)


def holder(path: Path | None = None) -> str | None:
    """The note in the lock file while a process holds the slot, else None."""
    try:
        fd = os.open(path or lock_path(), os.O_RDONLY)
    except OSError:
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        lines = os.pread(fd, 400, 0).decode(errors="replace").strip().splitlines()
        return lines[0] if lines else "unknown"
    finally:
        os.close(fd)
    return None


def waiters(path: Path | None = None, locks: Path = PROC_LOCKS) -> list[int]:
    """The pids `/proc/locks` lists as blocked (`->`) on the slot's inode; empty without the file
    or `/proc/locks`."""
    try:
        st = os.stat(path or lock_path())
        rows = locks.read_text().splitlines()
    except OSError:
        return []
    inode = f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}"
    out = []
    for row in rows:
        fields = row.split()
        if len(fields) < 7 or fields[1] != "->" or fields[2] != "FLOCK":
            continue
        if fields[6] == inode and fields[5].isdigit():
            out.append(int(fields[5]))
    return out


def ancestors(pid: int) -> set[int]:
    """`pid`'s parents up to init, read from `/proc/<pid>/stat`."""
    seen: set[int] = set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
            pid = int(stat.rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return seen


def waiting_roots(roots: set[int], path: Path | None = None) -> set[int]:
    """The pids of `roots` with a process below them (or themselves) blocked on the slot."""
    hit: set[int] = set()
    for pid in waiters(path):
        hit |= ancestors(pid) & roots
    return hit


def main(argv: list[str]) -> int:
    if argv == ["holder"]:
        held = holder()
        if held:
            print(held)
        return 0 if held else 1
    if argv == ["waiters"]:
        for pid in waiters():
            print(pid)
        return 0
    print("usage: slot_lock.py holder | waiters", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
