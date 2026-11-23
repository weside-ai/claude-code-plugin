"""push_notify.py: one POST, one status line, never the URL (a local fake server, never a real
webhook)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import push_notify as pn  # noqa: E402
import test_event_routes as ter  # noqa: E402  (the fake webhook)


@pytest.mark.parametrize(
    "url, status",
    [
        ("", "no url"),
        ("http://example.invalid/hook", "bad url"),
        ("ftp://127.0.0.1/hook", "bad url"),
        ("https://", "bad url"),
    ],
)
def test_refused_urls(url, status):
    assert pn.send(url, "x") == status


def test_unreachable_names_no_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert pn.send(f"http://127.0.0.1:{port}/secret-path", "x") == "unreachable"


@pytest.mark.parametrize(
    "code, status", [(200, "sent"), (204, "sent"), (302, "HTTP 302"), (404, "HTTP 404")]
)
def test_status_lines(code, status):
    with ter.fake_webhook(code) as url:
        assert pn.send(url, "hello", body_key="content") == status
    assert ter.Hook.bodies == [{"content": "hello"}]


def test_cli_reads_the_url_from_the_named_variable_only(tmp_path):
    with ter.fake_webhook(500) as url:
        out = subprocess.run(
            [sys.executable, str(HERE / "push_notify.py"), "--env", "CREW_HOOK"],
            input="line",
            capture_output=True,
            text=True,
            env={**os.environ, "CREW_HOOK": url},
            check=False,
            timeout=30,
        )
    assert (out.returncode, out.stdout, out.stderr) == (1, "HTTP 500\n", "")
