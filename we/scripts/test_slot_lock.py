"""slot_lock.py: the holder's note line, the waiters from /proc/locks, the holder read."""

from __future__ import annotations

import fcntl
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
import slot_lock

NOTE_RE = r"(?P<label>.+) \(pid (?P<pid>\d+), since \d\d:\d\d:\d\d(?:, until \d\d:\d\d)?\)\n"


def test_the_note_is_exactly_the_line_the_waiters_parse():
    at = time.mktime((2026, 11, 21, 3, 57, 32, 0, 0, -1))
    assert slot_lock.note("bench --reps 5", 42, at) == "bench --reps 5 (pid 42, since 03:57:32)\n"
    assert (
        slot_lock.note("bench --reps 5", 42, at, at + 30 * 60)
        == "bench --reps 5 (pid 42, since 03:57:32, until 04:27)\n"
    )


def test_hold_writes_its_own_note_over_a_dead_holder_and_frees_the_slot(tmp_path, monkeypatch):
    lock = tmp_path / "tests.lock"
    lock.write_text("old (pid 1, since 01:00:00)\n")
    monkeypatch.setenv("WESIDE_TESTS_LOCK", str(lock))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("WESIDE_TESTS_LOCK_HELD", raising=False)
    with slot_lock.hold("harness: run", expected_minutes=30):
        text = lock.read_text()
        assert re.fullmatch(NOTE_RE, text), text
        assert f"(pid {os.getpid()}, since " in text and ", until " in text
        assert os.environ["WESIDE_TESTS_LOCK_HELD"] == str(os.getpid())
    assert "WESIDE_TESTS_LOCK_HELD" not in os.environ
    assert slot_lock.holder(lock) is None  # released


@pytest.mark.skipif(not Path("/proc/locks").exists(), reason="the waiters come from /proc/locks")
def test_a_blocked_waiter_is_listed_with_its_pid(tmp_path):
    lock = tmp_path / "tests.lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o666)
    fcntl.flock(fd, fcntl.LOCK_EX)
    os.pwrite(fd, b"me (pid 7, since 10:00:00)\n", 0)
    code = f"import fcntl, os; fcntl.flock(os.open({str(lock)!r}, os.O_RDWR), fcntl.LOCK_EX)"
    waiter = subprocess.Popen([sys.executable, "-c", code])
    try:
        for _ in range(50):
            if slot_lock.waiters(lock):
                break
            time.sleep(0.1)
        assert slot_lock.waiters(lock) == [waiter.pid]
        assert slot_lock.waiting_roots({os.getpid(), 999999}, lock) == {os.getpid()}
        assert slot_lock.holder(lock) == "me (pid 7, since 10:00:00)"
    finally:
        waiter.kill()
        os.close(fd)
    assert slot_lock.waiters(lock) == []


def test_waiters_ignore_holders_and_other_inodes(tmp_path):
    lock = tmp_path / "tests.lock"
    lock.touch()
    st = os.stat(lock)
    inode = f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}"
    locks = tmp_path / "locks"
    locks.write_text(
        f"1: FLOCK  ADVISORY  WRITE 100 {inode} 0 EOF\n"
        f"1: -> FLOCK  ADVISORY  WRITE 101 {inode} 0 EOF\n"
        "2: -> FLOCK  ADVISORY  WRITE 102 00:01:5 0 EOF\n"
        f"3: -> POSIX  ADVISORY  WRITE 103 {inode} 0 EOF\n"
    )
    assert slot_lock.waiters(lock, locks) == [101]


def test_a_note_is_printed_without_control_characters_and_cut_to_its_limit(tmp_path):
    """T2 panel on #308: the lock file is 0o666 in /tmp; whatever a process writes there reaches a
    model's context through the waiting line and `holder`."""
    raw = b"evil\x1b[2J\x07 note\r" + b"x" * 500 + b"\nsecond line"
    text = slot_lock.shown(raw)
    assert text.startswith("evil[2J note") and len(text) == slot_lock.NOTE_MAX
    assert all(c.isprintable() for c in text)
    assert slot_lock.shown(b"\x00\x01\n") == "unknown"
    lock = tmp_path / "tests.lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o666)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.pwrite(fd, raw, 0)
        code = (
            "import slot_lock, sys; from pathlib import Path;"
            f" sys.stdout.write(slot_lock.holder(Path({str(lock)!r})))"
        )
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(slot_lock.__file__).parent,
        ).stdout
        assert out == text
    finally:
        os.close(fd)
