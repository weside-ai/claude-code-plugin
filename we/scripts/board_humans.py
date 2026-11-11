#!/usr/bin/env python3
"""Several humans, one crew: what `board.py signals`, `claim` and `ask --to` read from a ticket.

Pure functions over the ticket data the adapter returns (`ticket_adapter.py`: `search` hits
`{key, changed?}`, a ticket's `{labels, comments}`, each comment `{author, body, created}`); the
verbs in `board.py` own every write. Grammar (docs/board.md § Several humans):

- a signal query: `[<board.jql_scope> AND ]status changed to "<status>" after -<jql_window>`;
- a claim comment: `claim <role>@<human> <session>` as the comment's first line, its release
  `release <role>@<human> <session>`; a ticket comment holds a claim only from the account of the
  human it names, or from one of `board.shared_accounts` (`held_claims`); a claim lives
  `board.claim_hours` from its comment's `created`, until the same role, human and session releases
  it (two sessions of one human are two claimants);
- a question to a human on another machine: the comment `<question_label> <labels.to> <Name> ·
  <ask> · <labels.recommendation>: <recommendation>` and the label `question_label(crew, human)`;
- an account: a human's `email` or Jira `account_id` (`humans.<slug>`), never a display name,
  which anyone can give themselves;
- a reply: a comment created after the question by the asked human alone (its `author` is one of
  that human's accounts), or signed `<role>@<human>` as its first word from that human's account or
  one of `board.shared_accounts`; another human with the same role never answers for them, and the
  question comment itself is never a reply;
  its first word, read in any case, when it is an answer kind
  (`accept`, `deny`, `discuss`, `info`, `update`), is the answer, else `discuss`. The label taken
  off without a reply is the answer `update` (ask whether the question still stands).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

KINDS = ("accept", "deny", "discuss", "info", "update")
CLAIM = re.compile(r"(claim|release) ([a-z0-9_-]+)@([a-z0-9_-]+)(?: (\S+))?")
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
    """The claim or release on the first line of each comment, oldest first: `{verb, role, human,
    session, at}` (`at` the comment's `created`, None when unreadable); a quoted claim further
    down a comment never counts (the caller passes only `held_claims`)."""
    out = []
    for c in comments or []:
        body = str((c or {}).get("body") or "").strip()
        m = CLAIM.match(body.split("\n", 1)[0].strip())
        if m:
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


def live_claims(
    comments: list[dict], now: datetime, hours: float
) -> dict[tuple[str, str, str], dict]:
    """(role, human, session) -> its newest claim still alive at `now`: younger than `hours`, not
    released by the same claimant."""
    newest: dict[tuple[str, str, str], dict] = {}
    for c in claims(comments):
        newest[(c["role"], c["human"], c["session"])] = c
    limit = timedelta(hours=hours)
    return {
        who: c
        for who, c in newest.items()
        if c["verb"] == "claim" and c["at"] is not None and now - c["at"] < limit
    }


def _accounts(entry: dict) -> set[str]:
    """The human's accounts: `email` and `account_id`, lowered; a display name is none."""
    return {str(entry.get(k) or "").strip().lower() for k in ("email", "account_id")} - {""}


def _author(comment: dict) -> str:
    return str((comment or {}).get("author") or "").strip().lower()


def crew_accounts(every: dict) -> set[str]:
    return set().union(set(), *(_accounts(e) for e in (every or {}).values()))


def shared_accounts(crew: dict) -> set[str]:
    """`board.shared_accounts`, lowered: the accounts several humans write from."""
    found = (crew.get("board") or {}).get("shared_accounts") or []
    return {str(a).strip().lower() for a in found if str(a).strip()}


def speaks_for(author: str, human: str, every: dict, shared: set[str]) -> bool:
    """A comment from `author` may speak for `human`: one of that human's own accounts, or one of
    the explicitly shared accounts. Another human's account never speaks for them."""
    author = str(author or "").strip().lower()
    return bool(author) and (author in _accounts(every.get(human) or {}) or author in shared)


def held_claims(comments: list[dict], every: dict, shared: set[str]) -> list[dict]:
    """The comments whose first-line claim or release names a human its author speaks for
    (`speaks_for`); a claim from a crew account for another human holds nothing."""
    out = []
    for c in comments or []:
        found = claims([c])
        if (
            found
            and found[0]["human"] in every
            and speaks_for(_author(c), found[0]["human"], every, shared)
        ):
            out.append(c)
    return out


def _by_human(comment: dict, human: str, every: dict, shared: set[str] = frozenset()) -> bool:
    """The comment is `human`'s: its author is one of that human's accounts, or it is signed
    `<role>@<human>` from one of the shared accounts; a signature from another human's account
    never counts."""
    author = _author(comment)
    if not author:
        return False
    if author in _accounts(every.get(human) or {}):
        return True
    m = SIGNED.match(str(comment.get("body") or "").strip())
    return bool(m and m.group(2) == human and author in shared)


def _is_question(comment: dict, crew: dict) -> bool:
    """The question comment `question_comment` wrote: never an answer to itself."""
    word = str(crew.get("question_label") or "QUESTION").strip()
    body = str((comment or {}).get("body") or "").strip()
    return bool(word) and body.lower().startswith(word.lower() + " ")


def replies(
    ticket: dict, asked: datetime, human: str, every: dict, crew: dict | None = None
) -> list[dict]:
    """The comments `human` wrote on the ticket after `asked`, oldest first: `{kind, quote, at,
    by}`; `every` is the crew's humans (``crew.humans``), `crew` the crew file (its
    `board.shared_accounts` and `question_label`)."""
    crew = crew or {}
    shared = shared_accounts(crew)
    out = []
    for c in (ticket or {}).get("comments") or []:
        at = parse_ts((c or {}).get("created"))
        if at is None or at <= asked or _is_question(c or {}, crew):
            continue
        if not _by_human(c or {}, human, every, shared):
            continue
        by = human
        body = " ".join(str(c.get("body") or "").split())
        body = SIGNED.sub("", body, count=1).lstrip(" :·-")
        first = body.split(" ", 1)[0].strip(".:,;·").lower() if body else ""
        kind = first if first in KINDS else "discuss"
        out.append({"kind": kind, "quote": body[:QUOTE_CHARS], "at": c.get("created"), "by": by})
    return sorted(out, key=lambda r: parse_ts(r["at"]))


def inbox_jql(crew: dict, human: str) -> str:
    """The open questions to `human`: the tickets carrying their question label."""
    query = f'labels = "{question_label(crew, human)}"'
    scope = str((crew.get("board") or {}).get("jql_scope") or "").strip()
    return f"{scope} AND {query}" if scope else query


def reply_comment(who: str, kind: str, text: str) -> str:
    """The reply `board.py reply` writes: `<role>@<human> <kind> · <text>`."""
    return f"{who} {kind} · {' '.join(text.split())}" if text.strip() else f"{who} {kind}"
