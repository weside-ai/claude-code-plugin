#!/usr/bin/env python3
"""Several humans, one crew: what `board.py signals`, `claim` and `ask --to` read from a ticket.

Pure functions over the ticket data the adapter returns (`ticket_adapter.py`: `search` hits
`{key, changed?}`, a ticket's `{labels, comments}`, each comment `{author, body, created}`); the
verbs in `board.py` own every write. Grammar (docs/board.md § Several humans):

- a signal query: `[<board.jql_scope> AND ]status changed to "<status>" after -<jql_window>`;
- a claim comment: `claim <role>@<human> <session>`, its release `release <role>@<human> <session>`;
  a claim lives `board.claim_hours` from its comment's `created`, until its claimant releases it;
- a question to a human on another machine: the comment `<question_label> <labels.to> <Name> ·
  <ask> · <labels.recommendation>: <recommendation>` and the label `question_label(crew, human)`;
- a reply: a comment created after the question by that human (its `author` is the human's email
  or name) or signed `<role>@<human>` as its first word; its first word, when it is an answer kind
  (`accept`, `deny`, `discuss`, `info`, `update`), is the answer, else `discuss`. The label taken
  off without a reply is the answer `update` (ask whether the question still stands).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

KINDS = ("accept", "deny", "discuss", "info", "update")
CLAIM = re.compile(r"^(claim|release) ([a-z0-9_-]+)@([a-z0-9_-]+)(?: (\S+))?", re.MULTILINE)
SIGNED = re.compile(r"^([a-z0-9_-]+)@([a-z0-9_-]+)\b")
QUOTE_CHARS = 500


def parse_ts(text: Any) -> datetime | None:
    """A ticket timestamp (ISO, `Z` or `+0100` offsets, any fraction) as aware UTC; else None."""
    if not isinstance(text, str) or not text.strip():
        return None
    raw = text.strip().replace("Z", "+00:00")
    raw = re.sub(r"(T\d\d:\d\d:\d\d)\.\d+", r"\1", raw)
    raw = re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", raw)
    try:
        ts = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return ts.astimezone(timezone.utc) if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def signal_jql(crew: dict, state: str, window: str) -> str:
    board = crew.get("board") or {}
    status = (board.get("states") or {}).get(state) or state
    query = f'status changed to "{status}" after -{window}'
    scope = str(board.get("jql_scope") or "").strip()
    return f"{scope} AND {query}" if scope else query


def question_label(crew: dict, human: str) -> str:
    """`<question_label lowercased>-<human>`, every run of blanks one `-` (a ticket label has none)."""
    word = re.sub(r"\s+", "-", str(crew.get("question_label") or "QUESTION").strip().lower())
    return f"{word}-{human}"


def question_comment(crew: dict, name: str, ask: str, recommendation: str) -> str:
    labels = crew.get("labels") or {}
    return (
        f"{crew.get('question_label') or 'QUESTION'} {labels.get('to') or 'to'} {name} · {ask} · "
        f"{labels.get('recommendation') or 'Recommendation'}: {recommendation}"
    )


def claims(comments: list[dict]) -> list[dict]:
    """Every claim and release line of the comments, oldest first: `{verb, role, human, session,
    at}` (`at` the comment's `created`, None when unreadable)."""
    out = []
    for c in comments or []:
        body = str((c or {}).get("body") or "")
        for m in CLAIM.finditer(body):
            out.append(
                {
                    "verb": m.group(1),
                    "role": m.group(2),
                    "human": m.group(3),
                    "session": m.group(4) or "",
                    "at": parse_ts((c or {}).get("created")),
                }
            )
    return sorted(out, key=lambda x: x["at"] or datetime.min.replace(tzinfo=timezone.utc))


def live_claims(comments: list[dict], now: datetime, hours: float) -> dict[tuple[str, str], dict]:
    """(role, human) -> its newest claim still alive at `now`: younger than `hours`, not released."""
    newest: dict[tuple[str, str], dict] = {}
    for c in claims(comments):
        newest[(c["role"], c["human"])] = c
    limit = timedelta(hours=hours)
    return {
        who: c
        for who, c in newest.items()
        if c["verb"] == "claim" and c["at"] is not None and now - c["at"] < limit
    }


def _by_human(comment: dict, human: str, entry: dict) -> bool:
    author = str(comment.get("author") or "").strip().lower()
    known = {human, str(entry.get("name") or "").strip().lower()}
    if entry.get("email"):
        known.add(str(entry["email"]).strip().lower())
    if author and author in known:
        return True
    m = SIGNED.match(str(comment.get("body") or "").strip())
    return bool(m and m.group(2) == human)


def replies(ticket: dict, asked: datetime, human: str, entry: dict) -> list[dict]:
    """The comments `human` wrote on the ticket after `asked`, oldest first: `{kind, quote, at}`."""
    out = []
    for c in (ticket or {}).get("comments") or []:
        at = parse_ts((c or {}).get("created"))
        if at is None or at <= asked or not _by_human(c, human, entry):
            continue
        body = " ".join(str(c.get("body") or "").split())
        body = SIGNED.sub("", body, count=1).lstrip(" :·-")
        first = body.split(" ", 1)[0].strip(".:,;·").lower() if body else ""
        kind = first if first in KINDS else "discuss"
        out.append({"kind": kind, "quote": body[:QUOTE_CHARS], "at": c.get("created")})
    return sorted(out, key=lambda r: parse_ts(r["at"]))
