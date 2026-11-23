#!/usr/bin/env python3
"""Posts one message to a chat incoming webhook: the poller's push to the human's phone.

The text comes on stdin; the webhook URL from the environment variable ``--env`` names, which the
project's wrapper command sets (``events.push.wrapper``, e.g. a secret tool's ``run`` verb): the
URL is never in argv, a file or a log. The body is one JSON object ``{<body_key>: <text>}``
(``--body-key``, default ``text``: the incoming-webhook body most chat tools accept).

Prints exactly one status line and nothing else, never the URL nor an error text that could carry
it: ``sent`` · ``HTTP <code>`` · ``timeout`` · ``unreachable`` · ``no url`` · ``bad url`` ·
``error <ExceptionClass>``. Exit 0 only for ``sent``. A URL must be ``https``; plain ``http`` only
to the loopback address (the tests' local server).

Usage:
  <wrapper> -- push_notify.py --env NAME [--body-key KEY] < text
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT_S = 15
LOOPBACK = ("127.0.0.1", "localhost", "::1")


def url_ok(url: str) -> bool:
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if not parts.hostname:
        return False
    return parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in LOOPBACK)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):  # a webhook answers, it never redirects
        return None


def send(url: str, text: str, body_key: str = "text", timeout: float = TIMEOUT_S) -> str:  # noqa: PLR0911
    """The status of one POST; never raises, never names the URL."""
    if not url:
        return "no url"
    if not url_ok(url):
        return "bad url"
    body = json.dumps({body_key: text}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as resp:
            code = resp.status
    except urllib.error.HTTPError as exc:
        return f"HTTP {int(exc.code)}"
    except (socket.timeout, TimeoutError):
        return "timeout"
    except urllib.error.URLError as exc:
        return (
            "timeout" if isinstance(exc.reason, (socket.timeout, TimeoutError)) else "unreachable"
        )
    except Exception as exc:
        return f"error {type(exc).__name__}"
    return "sent" if 200 <= code < 300 else f"HTTP {int(code)}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--env", required=True)
    ap.add_argument("--body-key", default="text")
    a = ap.parse_args(argv)
    text = sys.stdin.read().strip()
    status = send(os.environ.get(a.env, "").strip(), text, a.body_key)
    print(status)
    return 0 if status == "sent" else 1


if __name__ == "__main__":
    sys.exit(main())
