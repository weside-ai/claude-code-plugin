#!/usr/bin/env python3
"""The scheduled ticket snapshot: the ticket system's REST search → `ticket_snapshot.write`.

Jira Cloud only, scheduling is external: a timer (cron, a systemd timer, the crew's loop) runs it.

Usage:
  ticket_fetch.py [--jql JQL] [--epics-jql JQL] [--board FILE] [--timeout S]

Reads `JIRA_BASE_URL` (https only), `JIRA_EMAIL` and `JIRA_SNAPSHOT_TOKEN` from the environment; the
token reaches the process only through the environment (a secret runner such as `wsec run --only`),
never as an argument or in a URL. The stories' JQL is `--jql`, else the crew's `flow.tickets_jql`
(`crew.py`); without one nothing is fetched. The open epics' JQL is `--epics-jql`, else
`flow.epics_jql`; without one no epics are fetched. Each query pages through Jira Cloud's `POST
/rest/api/3/search/jql` (`fields`: `FIELDS`, `nextPageToken` until the answer carries none or
`isLast`); the issues map to their records (`ticket_snapshot.records`: an `Epic` issuetype to the
epics) and go to `ticket_snapshot.write` for the board (`--board`, else the crew's), the
snapshot's one writer.

Exit codes, one per failure class; nothing is written on any of them:
  2  config: a variable, the JQL or the board is missing, or the base URL is not https
  3  auth: Jira answers 401 or 403
  4  network: no answer (DNS, connect, timeout, TLS)
  5  server: Jira answers 5xx
  6  refused: another HTTP status, an answer that is no search result, or more than MAX_PAGES pages

A failure is one stderr line: the class, the HTTP status and at most LINE_CHARS of the answer's
first error message, with the token, the auth header and the e-mail address taken out and the
rest passed through `redaction.redact`. Request headers and the answer's body are never echoed.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import ticket_snapshot as ts  # noqa: E402
from redaction import redact  # noqa: E402

EXIT_CONFIG, EXIT_AUTH, EXIT_NETWORK, EXIT_SERVER, EXIT_REFUSED = 2, 3, 4, 5, 6
CLASS = {
    EXIT_CONFIG: "config",
    EXIT_AUTH: "auth",
    EXIT_NETWORK: "network",
    EXIT_SERVER: "server",
    EXIT_REFUSED: "refused",
}
ENV = ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_SNAPSHOT_TOKEN")
SEARCH = "/rest/api/3/search/jql"
FIELDS = [
    "status",
    "summary",
    "parent",
    "components",
    "labels",
    "priority",
    "updated",
    "issuetype",
]
PAGE_SIZE = 100
MAX_PAGES = 100  # 10 000 stories; a token that never ends is refused, not followed forever
LINE_CHARS = 160
BODY_BYTES = 4096


class FetchError(Exception):
    def __init__(self, code: int, line: str):
        super().__init__(line)
        self.code = code
        self.line = line


def auth_header(email: str, token: str) -> str:
    return "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()


def _scrub(text: str, secrets: tuple) -> str:
    for value in secrets:
        if value:
            text = text.replace(value, "[REDACTED]")
    text = " ".join(redact(text).split())
    return text[:LINE_CHARS]


def _first_message(raw: bytes) -> str:
    """The answer's first error message (`errorMessages`, else `errors`), else its first line."""
    text = raw.decode("utf-8", "replace")
    try:
        doc = json.loads(text)
    except ValueError:
        return text.strip().splitlines()[0] if text.strip() else ""
    if isinstance(doc, dict):
        msgs = doc.get("errorMessages") or list((doc.get("errors") or {}).values())
        if msgs:
            return str(msgs[0])
    return ""


def _post(url: str, body: dict, auth: str, opener, timeout: float, secrets: tuple) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": auth,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with opener(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        try:
            msg = _first_message(exc.read(BODY_BYTES) or b"")
        except Exception:  # an unreadable error body is only a missing detail
            msg = ""
        code = exc.code
        cls = EXIT_AUTH if code in (401, 403) else EXIT_SERVER if code >= 500 else EXIT_REFUSED
        line = f"HTTP {code}" + (f": {_scrub(msg, secrets)}" if msg else "")
        raise FetchError(cls, line) from None
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", None) or exc
        raise FetchError(
            EXIT_NETWORK, _scrub(f"{type(exc).__name__}: {reason}", secrets)
        ) from None
    try:
        doc = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise FetchError(EXIT_REFUSED, "the answer is no JSON") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("issues"), list):
        raise FetchError(EXIT_REFUSED, "the answer carries no issues list")
    return doc


def fetch(
    base: str,
    email: str,
    token: str,
    jql: str,
    opener=urllib.request.urlopen,
    timeout: float = 30,
) -> list:
    """Every issue of `jql` with its `FIELDS`, page by page."""
    auth = auth_header(email, token)
    secrets = (token, auth, auth.split(" ", 1)[1], email)
    url = base.rstrip("/") + SEARCH
    issues: list = []
    page_token = None
    for _ in range(MAX_PAGES):
        body = {"jql": jql, "fields": FIELDS, "maxResults": PAGE_SIZE}
        if page_token:
            body["nextPageToken"] = page_token
        doc = _post(url, body, auth, opener, timeout, secrets)
        issues += doc["issues"]
        page_token = doc.get("nextPageToken")
        if not page_token or doc.get("isLast"):
            return issues
    raise FetchError(EXIT_REFUSED, f"more than {MAX_PAGES} pages")


def config(env, jql_arg: str | None, crew: dict | None, epics_arg: str | None = None) -> tuple:
    """`(base, email, token, jql, epics jql or None)` or `FetchError(EXIT_CONFIG)` naming what is
    missing."""
    missing = [name for name in ENV if not (env.get(name) or "").strip()]
    if missing:
        raise FetchError(EXIT_CONFIG, "not set: " + ", ".join(missing))
    base = env["JIRA_BASE_URL"].strip()
    if not base.startswith("https://"):
        raise FetchError(EXIT_CONFIG, "JIRA_BASE_URL must start with https://")
    flow = (crew or {}).get("flow") or {}
    jql = jql_arg or flow.get("tickets_jql")
    if not jql:
        raise FetchError(EXIT_CONFIG, "no JQL: set flow.tickets_jql in the crew or pass --jql")
    epics = epics_arg or flow.get("epics_jql") or None
    return base, env["JIRA_EMAIL"].strip(), env["JIRA_SNAPSHOT_TOKEN"].strip(), jql, epics


def run(args, env, opener=urllib.request.urlopen) -> tuple:
    """`(snapshot file, story count, epic count)`."""
    board, crew = ts.locate(args.board)
    base, email, token, jql, epics_jql = config(env, args.jql, crew, args.epics_jql)
    if board is None:
        raise FetchError(EXIT_CONFIG, "no board (no crew, no --board)")
    issues = fetch(base, email, token, jql, opener, args.timeout)
    if epics_jql:
        issues += fetch(base, email, token, epics_jql, opener, args.timeout)
    try:
        stories, epics = ts.records({"issues": issues})
    except ValueError as exc:
        raise FetchError(EXIT_REFUSED, f"answer refused ({exc})") from None
    target = ts.write(board, stories, datetime.now(timezone.utc), epics)
    return target, len(stories), len(epics)


def main(argv=None, env=None, opener=urllib.request.urlopen) -> int:
    p = argparse.ArgumentParser(prog="ticket_fetch.py", description=__doc__.split("\n")[0])
    p.add_argument("--jql")
    p.add_argument("--epics-jql")
    p.add_argument("--board")
    p.add_argument("--timeout", type=float, default=30)
    args = p.parse_args(argv)
    try:
        target, count, epics = run(args, os.environ if env is None else env, opener)
    except FetchError as exc:
        print(f"ticket_fetch: {CLASS[exc.code]}: {exc.line}; nothing written", file=sys.stderr)
        return exc.code
    print(f"{target} ({count} stories, {epics} epics)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
