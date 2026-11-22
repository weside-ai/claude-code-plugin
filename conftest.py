"""Every test run keeps off the live state directory (tests wrote ~9 % of the live
`brakes.jsonl`) and off the host's memory and load readings (`WE_WORKER_HOST_ROOT`).

A write a test sends to a live state directory is refused by `worker_rights.brake_log`
(`WE_STATE_FORBIDDEN`), its line lands in `WE_STATE_LEAKS`, and the run fails naming it. A test
that writes the brake log gives itself a `WE_STATE_DIR` (the fixture `own_state_dir`). No global
`WE_STATE_DIR`: it would win over the board tests' own isolation (`DEFAULT_BOARD`,
a crew's `state_dir`).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_LIVE = [os.path.expanduser("~/.claude/we-state")]
if os.environ.get("WE_STATE_DIR", "").strip():
    _LIVE.append(os.environ["WE_STATE_DIR"].strip())
_LEAKS = Path(tempfile.mkdtemp(prefix="we-state-leaks-")) / "leaks.jsonl"
# set at import, before any test: subprocesses inherit it even from an environment copied early
os.environ["WE_STATE_FORBIDDEN"] = os.pathsep.join(_LIVE)
os.environ["WE_STATE_LEAKS"] = str(_LEAKS)
# the launcher's resource rule reads the host's cgroup, meminfo and loadavg: on a busy host every
# start in a test would wait in the queue; an empty stand-in for `/` reads `n/a` (counts as room)
os.environ["WE_WORKER_HOST_ROOT"] = tempfile.mkdtemp(prefix="we-host-root-")


@pytest.fixture
def own_state_dir(tmp_path, monkeypatch):
    """A `WE_STATE_DIR` of the test's own; returns it."""
    path = tmp_path / ".we-state"
    monkeypatch.setenv("WE_STATE_DIR", str(path))
    return path


def pytest_sessionfinish(session, exitstatus):
    if _LEAKS.is_file() and _LEAKS.read_text().strip():
        lines = _LEAKS.read_text().splitlines()
        print(
            f"\nconftest: {len(lines)} write(s) to the live state directory refused;"
            f" a test reached {os.environ['WE_STATE_FORBIDDEN']}:\n  " + "\n  ".join(lines[:5])
        )
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
