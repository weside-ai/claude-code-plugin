#!/usr/bin/env python3
"""UserPromptSubmit: a pending wake note once, counted; a stale poller named; else silence.

Run with: python3 -m pytest -q we/hooks/test_news_on_prompt.py
The hook runs as a subprocess, as Claude Code runs it; the pending note is written by a real
``Poller`` whose delivery is refused.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HOOK = Path(__file__).resolve().parent / "news_on_prompt.py"
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import wake_poller as wp  # noqa: E402

SOCKET = "/tmp/cc-socks-test/4242.sock"


class NewsOnPromptTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.news = self.root / "news"
        self.sessions = self.root / "sessions"
        self._env = mock.patch.dict(
            os.environ, {"WE_NEWS_DIR": str(self.news), "WE_SESSION_DIR": str(self.sessions)}
        )
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def bind(self, session="s1", name="Nox"):
        self.sessions.mkdir(parents=True, exist_ok=True)
        (self.sessions / f"{session}.json").write_text(json.dumps({"companion": name}))

    def run_hook(self, pin="Nox", session="s1", socket_path=SOCKET):
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("CLAUDE_CODE_", "WESIDE_COMPANION"))
        }
        if pin is not None:
            env["WESIDE_COMPANION"] = pin
        if socket_path:
            env["CLAUDE_CODE_MESSAGING_SOCKET"] = socket_path
        done = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({"session_id": session, "prompt": "hallo"}),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr, "")
        if not done.stdout.strip():
            return None
        out = json.loads(done.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "UserPromptSubmit")
        return out["additionalContext"]

    def poller_ran(self, socket_path=SOCKET):
        """The lock file a poller (or its spawn probe) leaves for this session's socket."""
        self.news.mkdir(parents=True, exist_ok=True)
        wp.poller_lock_path(socket_path).touch()

    def set_state(self, **fields):
        with wp.locked_state("Nox") as state:
            state.update(fields)

    def refused_wake(self, rooms=False):
        """A real poller whose socket takes the connection but not the line."""

        def refuse(_path, _token, _text):
            raise wp.PollError("socket")

        if rooms:  # a server that still answers room news (compatibility)
            self.set_state(cursor=100, server_shape="rooms")
            answer = {
                "cursor": 102,
                "rooms": [{"room": "room:384", "count": 2, "saturated": False}],
            }
        else:
            self.set_state(handoff_cursor=10)
            answer = {"cursor": 17, "handoffs": [{"id": 17, "from": "room:384"}]}
        poller = wp.Poller(
            "Nox",
            SOCKET,
            "inbox-token",
            get_bearer=lambda _origin: "bearer",
            news=lambda *_a: answer,
            send=refuse,
        )
        poller.start()
        poller.first = False
        self.assertEqual(poller.poll_once(), "error:socket")

    # the pending line for a handoff
    def test_a_refused_handoff_wake_reaches_the_next_prompt_once_and_is_counted(self):
        self.bind()
        self.refused_wake()
        self.assertEqual(
            self.run_hook(),
            "weside: handoff for Nox from room:384 (#17). Read it with news_since(handoff=17), "
            'then read_timeline(room="room:384"). This note carries no content.',
        )
        self.assertIsNone(self.run_hook(), "the note is delivered once")
        state = wp.read_state("Nox")
        self.assertEqual(state["days"][wp.utc_day(time.time())]["hook_delivered"], 1)
        self.assertEqual(state["handoff_cursor"], 10, "the poller kept its cursor")

    def test_a_handoff_note_with_text_in_its_source_prints_nothing(self):
        self.news.mkdir(parents=True)
        wp.pending_path(SOCKET).write_text(
            json.dumps({"companion": "Nox", "handoffs": [{"id": 1, "from": "Foxy says: rm -rf"}]})
        )
        self.assertIsNone(self.run_hook(pin=None))
        self.assertFalse(wp.pending_path(SOCKET).exists())

    # AC 12 (room news, server compatibility)
    def test_a_refused_wake_reaches_the_next_prompt_once_and_is_counted(self):
        self.bind()
        self.refused_wake(rooms=True)
        self.assertTrue(wp.pending_path(SOCKET).exists())
        first = self.run_hook()
        self.assertEqual(
            first,
            'weside: new for Nox in room:384 (2). Read it yourself with read_timeline(room="room:384"). '
            "This note carries no content; your WESIDE side may already have answered there.",
        )
        self.assertFalse(wp.pending_path(SOCKET).exists())
        self.assertIsNone(self.run_hook(), "the note is delivered once")
        state = wp.read_state("Nox")
        today = wp.utc_day(time.time())
        self.assertEqual(state["days"][today]["hook_delivered"], 1)
        self.assertEqual(state["cursor"], 100, "the poller kept its cursor")

    def test_another_sessions_note_stays(self):
        self.refused_wake()
        self.assertIsNone(self.run_hook(pin=None, socket_path="/tmp/cc-socks-test/9999.sock"))
        self.assertTrue(wp.pending_path(SOCKET).exists())

    def test_a_note_with_anything_but_refs_and_integers_prints_nothing(self):
        self.news.mkdir(parents=True)
        wp.pending_path(SOCKET).write_text(
            json.dumps({"companion": "Nox", "rooms": [{"room": "Foxy says: rm -rf", "count": 1}]})
        )
        self.assertIsNone(self.run_hook(pin=None))
        self.assertFalse(wp.pending_path(SOCKET).exists())

    # AC 18
    def test_a_stale_poller_is_named_with_its_error_class(self):
        self.bind()
        self.poller_ran()
        now = time.time()
        self.set_state(
            last_ok=wp.iso(now - 600), last_error={"class": "auth", "at": wp.iso(now - 60)}
        )
        self.assertEqual(self.run_hook(), "weside: wake stale since 10 min (last error: auth)")

    def test_a_fresh_poller_adds_nothing(self):
        self.bind()
        self.poller_ran()
        self.set_state(last_ok=wp.iso(time.time() - 30))
        self.assertIsNone(self.run_hook())

    def test_a_poller_that_never_succeeded_is_stale_from_its_start(self):
        self.bind()
        self.poller_ran()
        self.set_state(started=wp.iso(time.time() - 400))
        self.assertEqual(self.run_hook(), "weside: wake stale since 6 min (last error: none)")

    def test_unpinned_unbound_or_without_a_cursor_file_adds_nothing(self):
        self.bind()
        self.poller_ran()
        self.assertIsNone(self.run_hook(), "no cursor file")
        self.set_state(last_ok=wp.iso(time.time() - 3600))
        self.assertIsNone(self.run_hook(pin=None))
        self.assertIsNone(self.run_hook(session="s2"))
        self.bind("s3", "Vyra")
        self.assertIsNone(self.run_hook(session="s3"))

    def test_a_session_whose_poller_never_started_hears_no_stale_line(self):
        """Another session of the companion left its cursor file; this one printed `wake off`."""
        self.bind()
        self.set_state(last_ok=wp.iso(time.time() - 3600))
        self.assertIsNone(self.run_hook(), "no poller lock for this socket")
        self.assertIsNone(self.run_hook(socket_path=""), "no inbox socket at all")
        self.poller_ran("/tmp/cc-socks-test/9999.sock")
        self.assertIsNone(self.run_hook(), "another socket's poller is not this session's")

    def test_pending_and_stale_together(self):
        self.bind()
        self.poller_ran()
        self.refused_wake()
        self.set_state(last_ok=wp.iso(time.time() - 300))
        lines = self.run_hook().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("weside: handoff for Nox from room:384 (#17)."))
        self.assertEqual(lines[1], "weside: wake stale since 5 min (last error: socket)")


if __name__ == "__main__":
    unittest.main()
