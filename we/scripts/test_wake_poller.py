#!/usr/bin/env python3
"""Wake poller: one content-free wake per news, hold-off, heartbeat, back-off, exits.

Two layers. ``PollerTest`` drives ``Poller`` on a fake clock with injected news and
delivery (no sleeps, no network). ``PollerProcessTest`` runs the real script against a fake
MCP HTTP server on localhost, a fake ``weside`` on PATH and a fake Unix-socket inbox, and
checks that the inbox token never reaches argv, a file or the log.

Run with: python3 -m pytest -q we/scripts/test_wake_poller.py
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import wake_poller as wp

POLLER = Path(wp.__file__).resolve()
TOKEN = "inbox-token-SECRET-4711"
BEARER = "bearer-SECRET-0815"
T0 = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc).timestamp()

WAKE_384_2 = (
    'weside: new for Nox in room:384 (2). Read it yourself with read_timeline(room="room:384"). '
    "This note carries no content; your WESIDE side may already have answered there."
)


# --- fakes shared with the hook suites -----------------------------------------------------


class FakeInbox:
    """A Unix-socket inbox that records every line it receives."""

    def __init__(self, path: Path):
        self.path = str(path)
        self.lines: list[dict] = []
        self.connections = 0
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.path)
        self.sock.listen(8)
        self.sock.settimeout(0.2)
        self._stop = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
            except (socket.timeout, OSError):
                continue
            self.connections += 1
            data = b""
            with conn:
                conn.settimeout(2)
                with contextlib.suppress(OSError):
                    while True:
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        data += chunk
            for line in data.decode("utf-8").splitlines():
                if line.strip():
                    self.lines.append(json.loads(line))

    def close(self):
        self._stop = True
        self._thread.join(timeout=2)
        self.sock.close()
        with contextlib.suppress(OSError):
            os.unlink(self.path)


class FakeMcp:
    """A localhost MCP endpoint answering ``news_since`` from a script of answers."""

    def __init__(self):
        self.requests: list[dict] = []
        self.answers: list = []
        self.sse = False
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append({"headers": dict(self.headers), "body": body})
                answer = outer.answers.pop(0) if outer.answers else {"cursor": 0, "rooms": []}
                if isinstance(answer, int):
                    self.send_response(answer)
                    self.end_headers()
                    return
                rpc = {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "result": {"content": [{"type": "text", "text": json.dumps(answer)}]},
                }
                if outer.sse:
                    raw = f"event: message\ndata: {json.dumps(rpc)}\n\n".encode()
                    ctype = "text/event-stream"
                else:
                    raw = json.dumps(rpc).encode()
                    ctype = "application/json"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/mcp/"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def fake_weside(bin_dir: Path, exit_code: int = 0) -> None:
    """A ``weside`` whose ``auth token`` prints BEARER (or fails with ``exit_code``).

    Every call appends its argv, one line, to ``<bin_dir>/weside.argv``.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "weside"
    argv_log = bin_dir / "weside.argv"
    script.write_text(
        "#!/bin/sh\n"
        f'echo "$*" >> "{argv_log}"\n'
        f'if [ "$1 $2" = "auth token" ]; then\n'
        f"  [ {exit_code} -eq 0 ] && echo {BEARER}\n"
        f"  exit {exit_code}\n"
        "fi\nexit 3\n"
    )
    script.chmod(0o755)


def wait_for(predicate, timeout=8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


# --- in-process poller on a fake clock -----------------------------------------------------


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class PollerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "news"
        self._env = mock.patch.dict(os.environ, {"WE_NEWS_DIR": str(self.dir)})
        self._env.start()
        self.clock = Clock()
        self.answers: list = []
        self.afters: list = []
        self.call_times: list = []
        self.sent: list[str] = []
        self.send_error = None
        self.bearer_error = None
        self.bearer_origins: list[str] = []
        self.alive = True

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def news(self, _url, _bearer, _companion, after):
        self.afters.append(after)
        self.call_times.append(self.clock.t)
        answer = self.answers.pop(0) if self.answers else {"cursor": 0, "rooms": []}
        if isinstance(answer, Exception):
            raise answer
        return answer

    def bearer(self, api_url):
        self.bearer_origins.append(api_url)
        if self.bearer_error:
            raise self.bearer_error
        return BEARER

    def send(self, _path, token, text):
        self.assertEqual(token, TOKEN)
        if self.send_error:
            raise self.send_error
        self.sent.append(text)

    def poller(self):
        p = wp.Poller(
            "Nox",
            str(self.dir / "1234.sock"),
            TOKEN,
            clock=self.clock,
            sleep=self.clock.sleep,
            get_bearer=self.bearer,
            news=self.news,
            send=self.send,
            alive=lambda _p: self.alive,
        )
        p.start()
        return p

    def state(self):
        return json.loads(wp.state_path("Nox").read_text())

    def seed_cursor(self, cursor):
        with wp.locked_state("Nox") as s:
            s["cursor"] = cursor

    @staticmethod
    def rooms(*pairs, cursor):
        return {
            "cursor": cursor,
            "rooms": [{"room": r, "count": c, "saturated": False} for r, c in pairs],
        }

    # AC 10
    def test_two_lines_give_one_wake_with_the_exact_text(self):
        self.seed_cursor(100)
        p = self.poller()
        p.first = False
        self.answers = [self.rooms(("room:384", 2), cursor=102)]
        self.assertEqual(p.poll_once(), "ok")
        self.assertEqual(self.sent, [WAKE_384_2])
        self.assertEqual(self.afters, [100])
        self.assertEqual(self.state()["cursor"], 102)

    def test_first_poll_without_cursor_takes_the_head_and_wakes_nobody(self):
        p = self.poller()
        self.answers = [{"cursor": 57, "rooms": []}]
        p.poll_once()
        self.assertEqual(self.afters, [None])
        self.assertEqual(self.sent, [])
        self.assertEqual(self.state()["cursor"], 57)

    # AC 14
    def test_an_hour_without_news_contacts_no_socket_and_calls_at_most_60_times(self):
        p = self.poller()
        self.answers = [{"cursor": 5, "rooms": []}] * 200
        ticks = []

        def sleep(s):
            ticks.append(s)
            self.clock.sleep(s)
            if self.clock.t - T0 >= 3600:
                self.alive = False

        p.sleep = sleep
        self.assertEqual(p.run(), "gone")
        self.assertEqual(self.sent, [])
        self.assertLessEqual(len(self.afters), 60)
        self.assertEqual(self.state()["days"]["2026-10-26"]["polls"], len(self.afters))

    # AC 11
    def test_holdoff_suppresses_a_second_wake_and_the_next_counts_every_line(self):
        self.seed_cursor(100)
        p = self.poller()
        p.first = False
        self.answers = [self.rooms(("room:384", 2), cursor=102)]
        p.poll_once()
        self.clock.t = T0 + 180
        self.answers = [self.rooms(("room:384", 1), cursor=103)]
        p.poll_once()
        self.clock.t = T0 + 300
        self.answers = [self.rooms(("room:384", 3), cursor=105)]
        p.poll_once()
        self.assertEqual(len(self.sent), 1, "no second wake inside the hold-off")
        self.assertEqual(self.afters, [100, 102, 102], "the cursor waits for the held room")
        self.clock.t = T0 + 600
        self.answers = [self.rooms(("room:384", 4), cursor=106)]
        p.poll_once()
        self.assertEqual(len(self.sent), 2)
        self.assertIn("room:384 (4)", self.sent[1])
        self.assertEqual(self.state()["cursor"], 106)

    def test_another_room_wakes_at_the_next_poll_while_one_is_held(self):
        self.seed_cursor(100)
        p = self.poller()
        p.first = False
        self.answers = [self.rooms(("room:384", 2), cursor=102)]
        p.poll_once()
        self.clock.t = T0 + 60
        self.answers = [self.rooms(("room:384", 1), ("room:9", 1), cursor=104)]
        p.poll_once()
        self.assertEqual(len(self.sent), 2)
        self.assertIn("in room:9 (1).", self.sent[1])
        self.assertNotIn("room:384", self.sent[1])
        # room:384's wake is refused at T + 10 min: a pending note, the cursor stays put
        self.clock.t = T0 + 600
        self.send_error = wp.PollError("socket")
        self.answers = [self.rooms(("room:384", 1), ("room:9", 1), cursor=104)]
        p.poll_once()
        self.send_error = None
        # room:9's hold-off has ended, but its line was delivered against this cursor
        self.clock.t = T0 + 700
        self.answers = [self.rooms(("room:384", 1), ("room:9", 1), cursor=104)]
        p.poll_once()
        self.assertEqual(len(self.sent), 2, "a delivered line never wakes again")
        self.assertEqual(self.afters[-1], 102)
        # room:384's hold-off ends: it wakes alone, and the cursor moves past both
        self.clock.t = T0 + 1200
        self.answers = [self.rooms(("room:384", 1), ("room:9", 1), cursor=104)]
        p.poll_once()
        self.assertEqual(len(self.sent), 3)
        self.assertIn("in room:384 (1).", self.sent[2])
        self.assertNotIn("room:9", self.sent[2])
        self.assertEqual(self.state()["cursor"], 104)
        self.assertEqual(self.state()["delivered"], {})

    # AC 20
    def test_holdoff_survives_a_poller_restart(self):
        self.seed_cursor(100)
        p = self.poller()
        p.first = False
        self.answers = [self.rooms(("room:384", 1), cursor=101)]
        p.poll_once()
        self.clock.t = T0 + 120
        q = self.poller()
        self.clock.t = T0 + 180
        self.answers = [self.rooms(("room:384", 1), cursor=102)]
        q.poll_once()
        self.clock.t = T0 + 540
        self.answers = [self.rooms(("room:384", 1), cursor=102)]
        q.poll_once()
        self.assertEqual(len(self.sent), 1, "no wake before T + 10 min")
        self.clock.t = T0 + 600
        self.answers = [self.rooms(("room:384", 1), cursor=102)]
        q.poll_once()
        self.assertEqual(len(self.sent), 2)

    # AC 13
    def test_the_first_poll_after_a_persisted_cursor_says_since_your_last_session(self):
        self.seed_cursor(200)
        p = self.poller()
        self.answers = [self.rooms(("room:384", 1), ("room:9", 1), cursor=202)]
        p.poll_once()
        self.assertEqual(self.afters, [200])
        self.assertTrue(
            self.sent[0].startswith(
                "weside: new for Nox since your last session in room:384 (1), room:9 (1). "
                'Read it yourself with read_timeline(room="room:384"), '
                'read_timeline(room="room:9").'
            ),
            self.sent[0],
        )
        self.clock.t = T0 + 60
        self.answers = [self.rooms(("room:5", 1), cursor=203)]
        p.poll_once()
        self.assertNotIn("since your last session", self.sent[1])

    # AC 12 (the poller half)
    def test_a_refused_line_writes_one_pending_note_and_keeps_the_cursor(self):
        self.seed_cursor(100)
        p = self.poller()
        p.first = False
        self.send_error = wp.PollError("socket")
        self.answers = [self.rooms(("room:384", 2), cursor=102)]
        self.assertEqual(p.poll_once(), "error:socket")
        note = json.loads(wp.pending_path(p.socket_path).read_text())
        self.assertEqual(note["companion"], "Nox")
        self.assertEqual(note["rooms"], [{"room": "room:384", "count": 2, "saturated": False}])
        st = self.state()
        self.assertEqual(st["cursor"], 100)
        self.assertEqual(st["last_error"]["class"], "socket")
        self.assertEqual(stat.S_IMODE(os.stat(wp.pending_path(p.socket_path)).st_mode), 0o600)
        wp.pending_path(p.socket_path).unlink()
        self.clock.t = T0 + 60
        self.answers = [self.rooms(("room:384", 2), cursor=102)]
        p.poll_once()
        self.assertFalse(wp.pending_path(p.socket_path).exists(), "no repeat inside hold-off")

    def test_a_vanished_session_exits_and_keeps_the_cursor(self):
        self.seed_cursor(100)
        p = self.poller()
        self.send_error = wp.SessionGoneError()
        self.answers = [self.rooms(("room:384", 2), cursor=102)]
        self.assertEqual(p.poll_once(), "gone")
        self.assertEqual(self.state()["cursor"], 100)
        self.assertFalse(wp.pending_path(p.socket_path).exists())

    # AC 8 (exit half)
    def test_run_exits_within_two_intervals_after_the_session_ended_even_in_backoff(self):
        p = self.poller()
        self.bearer_error = wp.PollError("network")
        ended_at = []

        def sleep(s):
            self.clock.sleep(s)
            if self.clock.t - T0 >= 3000 and not ended_at:
                self.alive = False
                ended_at.append(self.clock.t)

        p.sleep = sleep
        self.assertEqual(p.run(), "gone")
        self.assertLessEqual(self.clock.t - ended_at[0], 2 * wp.INTERVAL_S)

    # AC 17
    def test_heartbeat_fields_and_day_counters(self):
        self.seed_cursor(100)
        p = self.poller()
        p.first = False
        self.answers = [self.rooms(("room:384", 1), cursor=101)]
        p.poll_once()
        self.clock.t = T0 + 60
        self.answers = [wp.PollError("network")]
        p.poll_once()
        st = self.state()
        self.assertEqual(st["last_ok"], wp.iso(T0))
        self.assertEqual(st["last_error"], {"class": "network", "at": wp.iso(T0 + 60)})
        self.assertEqual(
            st["days"]["2026-10-26"], {"polls": 2, "errors": 1, "wakes": 1, "hook_delivered": 0}
        )
        self.assertEqual(
            set(st), {"cursor", "delivered", "holdoff", "started", "last_ok", "last_error", "days"}
        )
        self.assertEqual(stat.S_IMODE(os.stat(wp.state_path("Nox")).st_mode), 0o600)

    def test_only_seven_days_of_counters_are_kept(self):
        p = self.poller()
        for d in range(9):
            self.clock.t = T0 + d * 86400
            p.poll_once()
        days = sorted(self.state()["days"])
        self.assertEqual(len(days), 7)
        self.assertEqual(days[-1], "2026-11-03")

    # AC 19
    def test_backoff_doubles_to_fifteen_minutes_and_resets_after_a_success(self):
        p = self.poller()
        self.answers = (
            [wp.PollError("network")] * 6 + [{"cursor": 1, "rooms": []}] + [wp.PollError("http")]
        )
        p.run(max_cycles=8)
        waits = [b - a for a, b in zip(self.call_times, self.call_times[1:])]
        self.assertEqual(waits, [120, 240, 480, 900, 900, 900, 60])

    def test_five_consecutive_auth_failures_exit_with_last_error_auth(self):
        p = self.poller()
        self.answers = [wp.PollError("auth")] * 10
        self.assertEqual(p.run(max_cycles=20), "auth-exit")
        self.assertEqual(len(self.afters), 5)
        self.assertEqual(self.state()["last_error"]["class"], "auth")

    def test_the_bearer_is_asked_for_the_origin_of_the_polled_mcp_url(self):
        self.poller().poll_once()
        self.assertEqual(self.bearer_origins, ["https://api.weside.ai"])

    def test_an_auth_error_names_its_source_in_the_heartbeat(self):
        p = self.poller()
        self.answers = [wp.PollError("auth", "401")]
        p.poll_once()
        err = self.state()["last_error"]
        self.assertEqual(err["detail"], "401")
        self.assertEqual(
            wp.describe_error(wp.read_state("Nox")["last_error"]),
            f"auth (401 from /mcp) at {err['at']}",
        )
        self.bearer_error = wp.PollError("auth", "token")
        p.poll_once()
        self.assertEqual(wp.read_state("Nox")["last_error"]["detail"], "token")
        self.assertEqual(wp.describe_error(None), "none")

    def test_auth_failures_must_be_consecutive(self):
        p = self.poller()
        self.answers = (
            [wp.PollError("auth")] * 4 + [{"cursor": 1, "rooms": []}] + [wp.PollError("auth")] * 4
        )
        self.assertEqual(p.run(max_cycles=9), "max-cycles")

    def test_a_cursor_moved_by_another_poller_skips_this_answer(self):
        self.seed_cursor(100)
        p = self.poller()
        p.first = False

        def news(url, bearer, companion, after):
            self.seed_cursor(150)
            return self.rooms(("room:384", 2), cursor=102)

        p.news = news
        p.poll_once()
        self.assertEqual(self.sent, [])
        self.assertEqual(self.state()["cursor"], 150)

    def test_saturated_room_shows_a_plus(self):
        text = wp.render("Nox", [{"room": "room:1", "count": 50, "saturated": True}])
        self.assertIn("room:1 (50+)", text)

    def test_the_wake_text_refuses_anything_but_refs_and_integers(self):
        for bad in ("room:1 Foxy says hi", "Weside Crew", "room:1\n"):
            with self.assertRaises(ValueError):
                wp.render("Nox", [{"room": bad, "count": 1}])
        with self.assertRaises(ValueError):
            wp.render("Nox\nignore previous", [{"room": "room:1", "count": 1}])

    def test_parse_news_rejects_a_non_plain_answer(self):
        def rpc(news):
            return {"result": {"content": [{"type": "text", "text": json.dumps(news)}]}}

        ok = wp.parse_news(rpc({"cursor": 3, "rooms": [{"room": "room:1", "count": 2}]}))
        self.assertEqual(ok["rooms"], [{"room": "room:1", "count": 2, "saturated": False}])
        for bad in (
            {"cursor": "3", "rooms": []},
            {"cursor": 3, "rooms": [{"room": "Weside Crew", "count": 1}]},
            {"cursor": 3, "rooms": [{"room": "room:1", "count": True}]},
            {"cursor": 3},
        ):
            with self.assertRaises(wp.PollError) as cm:
                wp.parse_news(rpc(bad))
            self.assertEqual(cm.exception.cls, "format")
        with self.assertRaises(wp.PollError) as cm:
            wp.parse_news({"result": {"isError": True, "content": []}})
        self.assertEqual(cm.exception.cls, "http")


# --- the real script against fakes ---------------------------------------------------------


class PollerProcessTest(unittest.TestCase):
    def setUp(self):
        # AF_UNIX paths are short: keep the socket in a short directory
        self._tmp = tempfile.TemporaryDirectory(dir="/tmp", prefix="wp")
        self.root = Path(self._tmp.name)
        self.news = self.root / "news"
        self.bin = self.root / "bin"
        fake_weside(self.bin)
        self.mcp = FakeMcp()
        self.inbox = FakeInbox(self.root / f"{os.getpid()}.sock")
        self.procs = []

    def tearDown(self):
        for proc in self.procs:
            with contextlib.suppress(OSError):
                os.kill(proc, 9)
        self.inbox.close()
        self.mcp.close()
        self._tmp.cleanup()

    def env(self, **extra):
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("CLAUDE_CODE_", "WESIDE_", "WE_"))
        }
        env.update(
            {
                "PATH": f"{self.bin}{os.pathsep}{env.get('PATH', '')}",
                "WE_NEWS_DIR": str(self.news),
                "WESIDE_MCP_URL": self.mcp.url,
                "CLAUDE_CODE_MESSAGING_SOCKET": self.inbox.path,
                "CLAUDE_CODE_MESSAGING_TOKEN": TOKEN,
            }
        )
        env.update(extra)
        return env

    def run_once(self, **extra):
        return subprocess.run(
            [sys.executable, str(POLLER), "--companion", "Nox", "--once"],
            env=self.env(**extra),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def files_text(self) -> str:
        return "".join(p.read_text(errors="replace") for p in self.news.rglob("*") if p.is_file())

    def test_one_cycle_end_to_end_and_the_token_stays_in_memory(self):
        self.mcp.answers = [{"cursor": 10, "rooms": []}]
        done = self.run_once()
        self.assertEqual(done.returncode, 0, done.stderr)
        first = self.mcp.requests[0]
        self.assertEqual(first["headers"]["Authorization"], f"Bearer {BEARER}")
        self.assertEqual(first["headers"]["X-Weside-Companion"], "Nox")
        self.assertEqual(first["body"]["params"], {"name": "news_since", "arguments": {}})
        self.assertEqual(self.inbox.connections, 0, "no news, no socket contact")

        self.mcp.sse = True
        self.mcp.answers = [
            {"cursor": 12, "rooms": [{"room": "room:384", "count": 2, "saturated": False}]}
        ]
        done = self.run_once()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.mcp.requests[1]["body"]["params"]["arguments"], {"after": 10})
        self.assertTrue(wait_for(lambda: len(self.inbox.lines) == 2))
        auth, user = self.inbox.lines
        self.assertEqual(auth, {"type": "auth", "token": TOKEN})
        self.assertEqual(user["type"], "user")
        self.assertEqual(user["message"]["role"], "user")
        self.assertEqual(
            user["message"]["content"],
            WAKE_384_2.replace("for Nox in", "for Nox since your last session in"),
        )
        state = json.loads((self.news / "nox.json").read_text())
        self.assertEqual(state["cursor"], 12)
        text = self.files_text()
        self.assertNotIn(TOKEN, text)
        self.assertNotIn(BEARER, text)
        self.assertIn("wake delivered", text)

    def argv_lines(self) -> list[str]:
        return (self.bin / "weside.argv").read_text().splitlines()

    def test_the_token_is_asked_for_the_polled_origin_not_the_cli_default(self):
        origin = self.mcp.url.rsplit("/mcp/", 1)[0]
        self.assertTrue(origin.startswith("http://127.0.0.1:"), origin)
        done = self.run_once()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.argv_lines(), [f"auth token --api-url {origin}"])

    def test_http_401_records_auth_and_a_failing_cli_too(self):
        self.mcp.answers = [401]
        self.run_once()
        state = json.loads((self.news / "nox.json").read_text())
        self.assertEqual(state["last_error"]["class"], "auth")
        self.assertEqual(state["last_error"]["detail"], "401")
        fake_weside(self.bin, exit_code=1)
        self.run_once()
        self.assertEqual(len(self.mcp.requests), 1, "no MCP call without a bearer")
        state = json.loads((self.news / "nox.json").read_text())
        self.assertEqual(state["last_error"]["detail"], "token")
        self.assertIn("error auth 401", self.files_text())
        self.assertIn("error auth token", self.files_text())

    # AC 8
    def test_spawn_runs_one_poller_per_socket_and_it_exits_when_the_session_ends(self):
        env = self.env(WE_WAKE_INTERVAL_S="1")
        with mock.patch.dict(os.environ, {"WE_NEWS_DIR": str(self.news)}):
            line = wp.spawn("Nox", env)
            self.assertRegex(line, r"^wake on: poller \d+ asks weside every 1 s for Nox$")
            pid = int(line.split()[3])
            self.procs.append(pid)
            self.assertTrue(wait_for(lambda: wp.lock_held(self.inbox.path)))
            self.assertEqual(
                wp.spawn("Nox", env), "wake on: a poller already runs for this session"
            )
        cmdline = Path(f"/proc/{pid}/cmdline")
        if cmdline.exists():
            self.assertNotIn(TOKEN, cmdline.read_bytes().decode(errors="replace"))
        self.assertTrue(wait_for(lambda: len(self.mcp.requests) >= 1))
        self.inbox.close()
        self.assertTrue(
            wait_for(lambda: not wp.lock_held(self.inbox.path), timeout=2 * 1 + 2),
            "the poller outlived its session",
        )
        self.assertNotIn(TOKEN, self.files_text())

    # AC 15
    def test_missing_prerequisites_name_their_reason(self):
        with mock.patch.dict(os.environ, {"WE_NEWS_DIR": str(self.news)}):
            cases = [
                (
                    self.env(CLAUDE_CODE_MESSAGING_SOCKET=""),
                    "CLAUDE_CODE_MESSAGING_SOCKET is unset",
                ),
                (self.env(CLAUDE_CODE_MESSAGING_TOKEN=""), "CLAUDE_CODE_MESSAGING_TOKEN is unset"),
                (self.env(PATH="/nonexistent"), "the weside CLI is not installed"),
            ]
            for env, reason in cases:
                self.assertTrue(wp.spawn("Nox", env).startswith(f"wake off: {reason}"), reason)
            fake_weside(self.bin, exit_code=1)
            self.assertEqual(
                wp.spawn("Nox", self.env()),
                "wake off: the weside CLI is not logged in (weside auth login)",
            )
        origin = self.mcp.url.rsplit("/mcp/", 1)[0]
        self.assertEqual(self.argv_lines(), [f"auth token --api-url {origin}"])
        self.assertFalse(wp.lock_held(self.inbox.path))


if __name__ == "__main__":
    unittest.main()
