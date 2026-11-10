#!/usr/bin/env python3
"""The ticketing adapter behind `board.py`'s moves: one protocol, one implementation per transport.

Writes: `TicketAdapter.move(key, status_name)`, `.comment(key, text)` and `.label(key, label)`
return the list of `CarryOp`s the calling session still has to carry out with its own ticketing
tool; an empty list means nothing is left to carry. Reads: `.search(state, jql)` (the tickets a
JQL query finds, each `{key, changed?}`) and `.ticket(key)` (`{labels, comments}`, each comment
`{author, body, created}`) return the data, or None when the session has to read it: then
`read_ops` names the reads (`search`, `read`) and the session hands their results back with
`board.py <verb> --input FILE` (`FileReads`). `adapter_for(crew)` picks the transport by the crew
file's `board.ticketing`:

- `none` → `NoneAdapter`: no ticketing system; the transitions row says `ticket: none`; a search
  finds nothing, a ticket has no labels and no comments.
- `jira` → `SessionTransport`: the script holds no credential; it returns the ops, `board.py`
  prints them as the last stdout line `carry: <JSON list>`, and the session executes them with
  its ticketing tool (a transition first, a comment second, a label third) and re-reads the
  status. The transitions row says `ticket: carried`.

`FakeAdapter` is for tests only and is injected in code (`board.main(argv, adapter=…)`); no
command-line flag selects it. A REST transport that moves the ticket itself and re-reads its
status drops in later as one more arm of `TRANSPORTS`, once a ticketing account for agents exists.
"""

from __future__ import annotations

from typing import NamedTuple

# the JSON field that carries an op's value
VALUE_FIELD = {
    "transition": "status",
    "comment": "text",
    "label": "add",
    "search": "jql",
    "read": "fields",
}


class CarryOp(NamedTuple):
    """One operation the session carries with its ticketing tool: `op` on `key` with `value`."""

    op: str
    key: str
    value: str

    def as_json(self) -> dict:
        if self.op == "search":  # `key` holds the board state the hits belong to
            return {"op": "search", "state": self.key, "jql": self.value}
        return {"op": self.op, "key": self.key, VALUE_FIELD[self.op]: self.value}


class TicketAdapter:
    """Protocol: `name` goes into the transitions row as `ticket`; the methods name what to carry."""

    name = "abstract"

    def move(self, key: str, status_name: str) -> list[CarryOp]:
        raise NotImplementedError

    def comment(self, key: str, text: str) -> list[CarryOp]:
        raise NotImplementedError

    def label(self, key: str, label: str) -> list[CarryOp]:
        raise NotImplementedError

    def search(self, state: str, jql: str) -> list[dict] | None:
        raise NotImplementedError

    def ticket(self, key: str) -> dict | None:
        raise NotImplementedError


def read_ops(searches: list[tuple[str, str]], keys: list[str]) -> list[CarryOp]:
    """The reads a session carries: one `search` per (state, jql), one `read` per ticket key."""
    return [CarryOp("search", state, jql) for state, jql in searches] + [
        CarryOp("read", key, "labels,comments") for key in keys
    ]


class NoneAdapter(TicketAdapter):
    name = "none"

    def move(self, key: str, status_name: str) -> list[CarryOp]:  # noqa: ARG002
        return []

    def comment(self, key: str, text: str) -> list[CarryOp]:  # noqa: ARG002
        return []

    def label(self, key: str, label: str) -> list[CarryOp]:  # noqa: ARG002
        return []

    def search(self, state: str, jql: str) -> list[dict] | None:  # noqa: ARG002
        return []

    def ticket(self, key: str) -> dict | None:  # noqa: ARG002
        return {"labels": [], "comments": []}


class SessionTransport(TicketAdapter):
    name = "carried"

    def move(self, key: str, status_name: str) -> list[CarryOp]:
        return [CarryOp("transition", key, status_name)]

    def comment(self, key: str, text: str) -> list[CarryOp]:
        return [CarryOp("comment", key, text)]

    def label(self, key: str, label: str) -> list[CarryOp]:
        return [CarryOp("label", key, label)]

    def search(self, state: str, jql: str) -> list[dict] | None:  # noqa: ARG002
        return None

    def ticket(self, key: str) -> dict | None:  # noqa: ARG002
        return None


class FileReads(TicketAdapter):
    """The reads a session carried, from `--input FILE` (`{"hits": {state: [key or {key,
    changed}]}, "tickets": {key: {labels, comments}}}`), over `inner`'s writes. A state the file
    leaves out reads as no hits; a ticket it leaves out is read again."""

    def __init__(self, inner: TicketAdapter, data: dict):
        self.inner = inner
        self.name = inner.name
        self.hits = data.get("hits") or {}
        self.tickets = data.get("tickets") or {}

    def move(self, key: str, status_name: str) -> list[CarryOp]:
        return self.inner.move(key, status_name)

    def comment(self, key: str, text: str) -> list[CarryOp]:
        return self.inner.comment(key, text)

    def label(self, key: str, label: str) -> list[CarryOp]:
        return self.inner.label(key, label)

    def search(self, state: str, jql: str) -> list[dict] | None:  # noqa: ARG002
        return [h if isinstance(h, dict) else {"key": h} for h in self.hits.get(state) or []]

    def ticket(self, key: str) -> dict | None:
        """None for a key the file leaves out (the read is carried again); `labels` None when
        the read gave none, so no label counts as removed."""
        found = self.tickets.get(key)
        if not isinstance(found, dict):
            return None
        labels = found.get("labels")
        return {
            "labels": labels if isinstance(labels, list) else None,
            "comments": found.get("comments") or [],
        }


class FakeAdapter(TicketAdapter):
    """Tests only: holds a status per key and records every call."""

    name = "fake"

    def __init__(
        self,
        statuses: dict[str, str] | None = None,
        searches: dict[str, list] | None = None,
        tickets: dict[str, dict] | None = None,
    ):
        self.statuses = dict(statuses or {})
        self.searches = dict(searches or {})  # jql -> hits
        self.tickets = {k: dict(v) for k, v in (tickets or {}).items()}
        self.calls: list[tuple[str, str, str]] = []

    def move(self, key: str, status_name: str) -> list[CarryOp]:
        self.calls.append(("move", key, status_name))
        self.statuses[key] = status_name
        return []

    def comment(self, key: str, text: str) -> list[CarryOp]:
        self.calls.append(("comment", key, text))
        return []

    def label(self, key: str, label: str) -> list[CarryOp]:
        self.calls.append(("label", key, label))
        return []

    def search(self, state: str, jql: str) -> list[dict] | None:
        self.calls.append(("search", state, jql))
        return [h if isinstance(h, dict) else {"key": h} for h in self.searches.get(jql, [])]

    def ticket(self, key: str) -> dict | None:
        found = self.tickets.get(key) or {}
        return {"labels": found.get("labels") or [], "comments": found.get("comments") or []}


TRANSPORTS = {"none": NoneAdapter, "jira": SessionTransport}


def adapter_for(crew: dict) -> TicketAdapter:
    ticketing = str((crew.get("board") or {}).get("ticketing") or "none")
    if ticketing not in TRANSPORTS:
        raise ValueError(
            f"board.ticketing {ticketing!r} has no transport (known: {', '.join(TRANSPORTS)})"
        )
    return TRANSPORTS[ticketing]()
