"""events_on_start.py: poller and tail only in a crew with `events:`; the poller's environment has
no `CLAUDE_*`; the socket and token go to the tail's environment only."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent
SCRIPTS = HOOKS.parent / "scripts"
sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "command_center"))
import event_poller  # noqa: E402
import event_tail  # noqa: E402
import events_on_start  # noqa: E402
import test_event_routes as ter  # noqa: E402  (its crew and project builder)

TOKEN = "tok-" + "q" * 24


class Spawned:
    """Records the detached starts of poller and tail; every other process runs for real."""

    def __init__(self, real):
        self.real = real
        self.calls: list[dict] = []

    def __call__(self, argv, *args, **kw):
        if not any(str(a).endswith(("event_poller.py", "event_tail.py")) for a in argv):
            return self.real(argv, *args, **kw)
        self.calls.append({"argv": list(argv), "env": dict(kw.get("env") or {})})
        return type("Proc", (), {"pid": 4242})()


@pytest.fixture
def spawned(monkeypatch):
    spy = Spawned(subprocess.Popen)
    monkeypatch.setattr(subprocess, "Popen", spy)
    return spy


def environ(tmp: Path, **extra) -> dict:
    return {
        "HOME": str(tmp),
        "PATH": "/usr/bin:/bin",
        "WE_STATE_DIR": str(tmp / "state"),
        "CLAUDE_CODE_MESSAGING_SOCKET": str(tmp / "s.sock"),
        "CLAUDE_CODE_MESSAGING_TOKEN": TOKEN,
        "CLAUDE_CONFIG_DIR": str(tmp / "cfg"),
        **extra,
    }


def test_nothing_without_an_events_block(tmp_path, spawned):
    root = tmp_path / "repo"
    (root / ".weside").mkdir(parents=True)
    (root / ".weside" / "config.json").write_text(json.dumps({"stack": []}))
    assert (
        events_on_start.start({"cwd": str(root)}, environ(tmp_path, WESIDE_COMPANION="Kiska"))
        == []
    )
    assert spawned.calls == []


def test_poller_without_claude_env_and_tail_with_the_socket(tmp_path, spawned):
    root = ter.project(tmp_path)
    said = events_on_start.start(
        {"cwd": str(root), "session_id": "sess-1"}, environ(tmp_path, WESIDE_COMPANION="Kiska")
    )
    assert said == ["events: poller 4242 started", "events: tail 4242 for kiska"]
    poller, tail = spawned.calls
    assert poller["argv"][1:3] == [str(event_poller.Path(event_poller.__file__).resolve()), "run"]
    assert not [k for k in poller["env"] if k.startswith("CLAUDE")]
    assert TOKEN not in " ".join(poller["argv"]) + json.dumps(poller["env"])
    assert tail["argv"][1] == str(Path(event_tail.__file__).resolve())
    assert TOKEN not in " ".join(tail["argv"])
    assert tail["env"]["CLAUDE_CODE_MESSAGING_TOKEN"] == TOKEN
    assert tail["env"]["CLAUDE_CODE_SESSION_ID"] == "sess-1"


def test_a_worker_or_a_session_without_a_member_gets_no_tail(tmp_path, spawned):
    root = ter.project(tmp_path)
    worker = events_on_start.start({"cwd": str(root)}, environ(tmp_path, WE_ROLE="worker"))
    assert worker == [] and spawned.calls == []  # a worker hosts no poller, gets no tail
    plain = events_on_start.start({"cwd": str(root)}, environ(tmp_path))
    assert plain[-1] == "events: no tail (this session is no crew member and no master)"


def test_a_failure_is_one_line_and_exit_0(tmp_path, monkeypatch, capsys):
    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(events_on_start, "start", boom)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    assert events_on_start.main() == 0
    out, err = capsys.readouterr()
    assert (out, err.strip()) == ("", "events_on_start: skipped (RuntimeError: boom)")


def test_a_master_without_a_companion_gets_a_tail_a_worker_none(tmp_path, spawned):
    root = ter.project(tmp_path)
    said = events_on_start.start(
        {"cwd": str(root), "session_id": "sid-m"}, environ(tmp_path, WE_ROLE="master")
    )
    assert said == ["events: poller 4242 started", "events: tail 4242 for master"]
    assert spawned.calls[-1]["env"]["CLAUDE_CODE_SESSION_ID"] == "sid-m"
    spawned.calls.clear()
    assert events_on_start.start({"cwd": str(root)}, environ(tmp_path, WE_ROLE="worker")) == []
    assert spawned.calls == []
