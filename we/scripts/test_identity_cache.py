#!/usr/bin/env python3
"""Standalone unittest for the identity cache.

Covers what can silently break a materialize: the tool-result shape must be
unwrapped, the cache must be keyed per companion (a switch must not serve the
previous companion's file), freshness must flip at the day boundary, and the
file must not be world-readable — it carries the compass and snapshot.

Run with: python3 we/scripts/test_identity_cache.py
No pytest required.
"""

import contextlib
import io
import json
import os
import stat
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import identity_cache as ic
import wake_poller as wp
from test_wake_poller import TOKEN, FakeInbox, FakeMcp, fake_weside, wait_for

WAKE_ENV = (
    "CLAUDE_CODE_MESSAGING_SOCKET",
    "CLAUDE_CODE_MESSAGING_TOKEN",
    "WE_NEWS_DIR",
    "WESIDE_MCP_URL",
    "WE_WAKE_INTERVAL_S",
    "PATH",
)


class IdentityCacheTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "cache"
        os.environ["WE_IDENTITY_CACHE_DIR"] = str(self.dir)
        self.src = Path(self._tmp.name) / "tool-result.txt"

    def tearDown(self):
        os.environ.pop("WE_IDENTITY_CACHE_DIR", None)
        self._tmp.cleanup()

    def write_payload(self, text):
        self.src.write_text(json.dumps({"result": text}), encoding="utf-8")

    def test_store_unwraps_tool_result_and_path_reports_fresh(self):
        self.write_payload("You are Nox.\n\n## Your Compass\n…")
        self.assertEqual(ic.main(["store", "--companion", "Nox", "--from", str(self.src)]), 0)
        target = self.dir / "nox.md"
        body = target.read_text(encoding="utf-8")
        self.assertTrue(body.startswith("<!-- weside identity cache · companion: Nox · fetched: "))
        self.assertIn("You are Nox.", body)
        self.assertNotIn('{"result"', body)
        self.assertEqual(ic.main(["path", "--companion", "Nox"]), 0)

    def test_store_accepts_plain_text(self):
        self.src.write_text("You are Mila.", encoding="utf-8")
        self.assertEqual(ic.main(["store", "--companion", "Mila", "--from", str(self.src)]), 0)
        self.assertIn("You are Mila.", (self.dir / "mila.md").read_text(encoding="utf-8"))

    def test_cache_is_keyed_per_companion(self):
        self.write_payload("You are Nox.")
        ic.main(["store", "--companion", "Nox", "--from", str(self.src)])
        # A different companion has no cache of its own yet.
        self.assertEqual(ic.main(["path", "--companion", "Mila"]), 2)

    def test_yesterdays_cache_is_stale(self):
        self.write_payload("You are Nox.")
        ic.main(["store", "--companion", "Nox", "--from", str(self.src)])
        target = self.dir / "nox.md"
        lines = target.read_text(encoding="utf-8").split("\n")
        yesterday = (datetime.now().astimezone() - timedelta(days=1)).replace(microsecond=0)
        lines[0] = (
            f"<!-- weside identity cache · companion: Nox · fetched: {yesterday.isoformat()} -->"
        )
        target.write_text("\n".join(lines), encoding="utf-8")
        self.assertEqual(ic.main(["path", "--companion", "Nox"]), 1)

    def test_headerless_file_counts_as_missing(self):
        self.dir.mkdir(parents=True)
        (self.dir / "nox.md").write_text("You are Nox.", encoding="utf-8")
        self.assertEqual(ic.main(["path", "--companion", "Nox"]), 2)

    def test_cache_file_is_owner_only(self):
        self.write_payload("You are Nox.")
        ic.main(["store", "--companion", "Nox", "--from", str(self.src)])
        mode = stat.S_IMODE((self.dir / "nox.md").stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_empty_payload_is_refused(self):
        self.write_payload("   \n")
        self.assertEqual(ic.main(["store", "--companion", "Nox", "--from", str(self.src)]), 1)
        self.assertFalse((self.dir / "nox.md").exists())

    def test_missing_source_is_refused(self):
        rc = ic.main(["store", "--companion", "Nox", "--from", str(self.src.with_name("nope"))])
        self.assertEqual(rc, 1)


class SessionBindingTest(unittest.TestCase):
    """The binding file is the one record the Stop hook and the statusline read."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "sessions"
        self._saved = {
            k: os.environ.get(k) for k in ("WE_SESSION_DIR", "WESIDE_COMPANION", *WAKE_ENV)
        }
        os.environ["WE_SESSION_DIR"] = str(self.dir)
        os.environ["WE_NEWS_DIR"] = str(Path(self._tmp.name) / "news")
        os.environ.pop("WESIDE_COMPANION", None)
        # never reach the real session's inbox socket from a test
        os.environ.pop("CLAUDE_CODE_MESSAGING_SOCKET", None)
        os.environ.pop("CLAUDE_CODE_MESSAGING_TOKEN", None)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def test_bind_writes_one_owner_only_file_per_session(self):
        self.assertEqual(ic.main(["bind", "--session", "s-1", "--companion", "Vyra"]), 0)
        self.assertEqual(ic.main(["bind", "--session", "s-2", "--companion", "Nox"]), 0)
        target = self.dir / "s-1.json"
        self.assertEqual(json.loads(target.read_text())["companion"], "Vyra")
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(ic.read_binding("s-1"), "Vyra")
        self.assertEqual(ic.read_binding("s-2"), "Nox")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["s-1.json", "s-2.json"])

    def test_binding_reports_bound_and_unbound(self):
        ic.main(["bind", "--session", "s-1", "--companion", "Vyra"])
        self.assertEqual(ic.main(["binding", "--session", "s-1"]), 0)
        self.assertEqual(ic.main(["binding", "--session", "s-9"]), 2)
        self.assertIsNone(ic.read_binding("s-9"))

    def test_session_id_cannot_escape_the_directory(self):
        outside = Path(self._tmp.name) / "escaped.json"
        for bad in ("../escaped", "a/b", "", ".", "..", "x" * 129, "s 1"):
            self.assertEqual(ic.main(["bind", "--session", bad, "--companion", "Vyra"]), 1, bad)
            self.assertIsNone(ic.read_binding(bad))
        self.assertFalse(outside.exists())
        self.assertFalse(self.dir.exists() and any(self.dir.iterdir()))

    def test_bind_prunes_bindings_older_than_30_days(self):
        ic.main(["bind", "--session", "old", "--companion", "Vyra"])
        ic.main(["bind", "--session", "recent", "--companion", "Vyra"])
        old = time.time() - 31 * 24 * 3600
        os.utime(self.dir / "old.json", (old, old))
        recent = time.time() - 29 * 24 * 3600
        os.utime(self.dir / "recent.json", (recent, recent))
        ic.main(["bind", "--session", "new", "--companion", "Nox"])
        self.assertFalse((self.dir / "old.json").exists())
        self.assertTrue((self.dir / "recent.json").exists())
        self.assertTrue((self.dir / "new.json").exists())

    def test_a_pinned_session_refuses_another_name(self):
        os.environ["WESIDE_COMPANION"] = "Vyra"
        self.assertEqual(ic.main(["bind", "--session", "s-1", "--companion", "Nox"]), 1)
        self.assertIsNone(ic.read_binding("s-1"))
        self.assertEqual(ic.main(["bind", "--session", "s-1", "--companion", "vyra"]), 0)

    def test_corrupt_binding_reads_as_unbound(self):
        self.dir.mkdir(parents=True)
        (self.dir / "s-1.json").write_text("{not json")
        self.assertIsNone(ic.read_binding("s-1"))


class WakeBindTest(unittest.TestCase):
    """``bind`` starts the wake poller for a pinned session; ``status`` shows its heartbeat."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir="/tmp", prefix="wb")
        self.root = Path(self._tmp.name)
        self.bin = self.root / "bin"
        fake_weside(self.bin)
        self.mcp = FakeMcp()
        self.inbox = FakeInbox(self.root / f"{os.getpid()}.sock")
        keys = ("WE_SESSION_DIR", "WESIDE_COMPANION", *WAKE_ENV)
        self._saved = {k: os.environ.get(k) for k in keys}
        os.environ.update(
            {
                "WE_SESSION_DIR": str(self.root / "sessions"),
                "WE_NEWS_DIR": str(self.root / "news"),
                "WESIDE_MCP_URL": self.mcp.url,
                "WE_WAKE_INTERVAL_S": "1",
                "CLAUDE_CODE_MESSAGING_SOCKET": self.inbox.path,
                "CLAUDE_CODE_MESSAGING_TOKEN": TOKEN,
                "WESIDE_COMPANION": "Nox",
                "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}",
            }
        )
        self.pids = []

    def tearDown(self):
        for pid in self.pids:
            with contextlib.suppress(OSError):
                os.kill(pid, 9)
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.inbox.close()
        self.mcp.close()
        self._tmp.cleanup()

    def bind(self, session="s-1", name="Nox"):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ic.main(["bind", "--session", session, "--companion", name])
        self.assertEqual(code, 0, out.getvalue())
        lines = out.getvalue().splitlines()
        wake = [line for line in lines if line.startswith("wake ")]
        for line in wake:
            if line.startswith("wake on: poller "):
                self.pids.append(int(line.split()[3]))
        return wake

    # AC 8
    def test_a_pinned_bind_starts_one_poller_and_a_rebind_none(self):
        first = self.bind()
        self.assertEqual(len(first), 1)
        self.assertRegex(first[0], r"^wake on: poller \d+ asks weside every 1 s for Nox$")
        self.assertTrue(wait_for(lambda: wp.lock_held(self.inbox.path)))
        self.assertEqual(self.bind(), ["wake on: a poller already runs for this session"])
        # /clear starts a new session id in the same process: same socket, no second poller
        self.assertEqual(self.bind("s-2"), ["wake on: a poller already runs for this session"])
        self.inbox.close()
        self.assertTrue(wait_for(lambda: not wp.lock_held(self.inbox.path), timeout=4))

    # AC 9
    def test_an_unpinned_bind_starts_none(self):
        os.environ.pop("WESIDE_COMPANION")
        self.assertEqual(self.bind(), [])
        self.assertFalse(wp.lock_held(self.inbox.path))

    # AC 15
    def test_a_pinned_bind_names_why_the_wake_is_off(self):
        os.environ.pop("CLAUDE_CODE_MESSAGING_SOCKET")
        (line,) = self.bind()
        self.assertTrue(line.startswith("wake off: CLAUDE_CODE_MESSAGING_SOCKET is unset"), line)
        os.environ["CLAUDE_CODE_MESSAGING_SOCKET"] = self.inbox.path
        fake_weside(self.bin, exit_code=1)
        origin = wp.api_origin(wp.mcp_url(os.environ))
        self.assertEqual(
            self.bind(),
            [
                f"wake off: the weside CLI is not logged in for {origin}"
                f" (weside auth login --api-url {origin})"
            ],
        )
        os.environ["PATH"] = "/nonexistent"
        self.assertEqual(self.bind(), ["wake off: the weside CLI is not installed"])
        wp.news_dir().mkdir(parents=True, exist_ok=True)  # an earlier session's cursor lives here
        self.assertFalse(wp.lock_held(self.inbox.path))
        self.assertFalse(
            wp.poller_lock_path(self.inbox.path).exists(),
            "a probe leaves no lock file: the prompt hook reads it as 'a poller ran here'",
        )

    def test_a_spawn_that_fails_keeps_the_bind_and_names_the_class(self):
        real_popen = wp.subprocess.Popen

        def popen(args, **kwargs):
            if str(args[1]).endswith("wake_poller.py"):
                raise PermissionError("denied")
            return real_popen(args, **kwargs)

        with mock.patch.object(wp.subprocess, "Popen", side_effect=popen):
            self.assertEqual(self.bind(), ["wake off: PermissionError"])
        self.assertEqual(ic.read_binding("s-1"), "Nox")

    # AC 17
    def test_status_prints_the_heartbeat_of_the_bound_companion(self):
        os.environ.pop("WESIDE_COMPANION")
        self.bind()
        with wp.locked_state("Nox") as state:
            state["cursor"] = 42
            state["last_ok"] = "2026-10-26T12:00:00+00:00"
            state["last_error"] = {
                "class": "auth",
                "detail": "token",
                "at": "2026-10-26T11:59:00+00:00",
            }
            wp.bump(state, "polls", 1793448000.0, by=3)
            wp.bump(state, "wakes", 1793448000.0)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(ic.main(["status", "--session", "s-1"]), 0)
        text = out.getvalue()
        self.assertTrue(text.startswith("Nox\n"), text)
        for expected in (
            "poller: not running for this session",
            "cursor: 42",
            "last_ok: 2026-10-26T12:00:00+00:00",
            "last_error: auth (token command failed) at 2026-10-26T11:59:00+00:00",
            "polls 3 errors 0 wakes 1 hook_delivered 0",
        ):
            self.assertIn(expected, text)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ic.main(["status", "--session", "s-9"]), 2)


if __name__ == "__main__":
    unittest.main()
