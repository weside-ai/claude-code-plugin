#!/usr/bin/env python3
"""The ticketing adapter behind `board.py`'s moves: one protocol, one implementation per transport.

`TicketAdapter.move(key, status_name)` and `.comment(key, text)` return the list of `CarryOp`s the
calling session still has to carry out with its own ticketing tool; an empty list means nothing
is left to carry. `adapter_for(crew)` picks the transport by the crew file's `board.ticketing`:

- `none` → `NoneAdapter`: no ticketing system; the transitions row says `ticket: none`.
- `jira` → `SessionTransport`: the script holds no credential; it returns the ops, `board.py`
  prints them as the last stdout line `carry: <JSON list>`, and the session executes them with
  its ticketing tool (a transition first, a comment second) and re-reads the status. The
  transitions row says `ticket: carried`.

`FakeAdapter` is for tests only and is injected in code (`board.main(argv, adapter=…)`); no
command-line flag selects it. A REST transport that moves the ticket itself and re-reads its
status drops in later as one more arm of `TRANSPORTS`, once a ticketing account for agents exists.
"""

from __future__ import annotations

from typing import NamedTuple

# the JSON field that carries an op's value
VALUE_FIELD = {"transition": "status", "comment": "text"}


class CarryOp(NamedTuple):
    """One operation the session carries with its ticketing tool: `op` on `key` with `value`."""

    op: str
    key: str
    value: str

    def as_json(self) -> dict:
        return {"op": self.op, "key": self.key, VALUE_FIELD[self.op]: self.value}


class TicketAdapter:
    """Protocol: `name` goes into the transitions row as `ticket`; the methods name what to carry."""

    name = "abstract"

    def move(self, key: str, status_name: str) -> list[CarryOp]:
        raise NotImplementedError

    def comment(self, key: str, text: str) -> list[CarryOp]:
        raise NotImplementedError


class NoneAdapter(TicketAdapter):
    name = "none"

    def move(self, key: str, status_name: str) -> list[CarryOp]:  # noqa: ARG002
        return []

    def comment(self, key: str, text: str) -> list[CarryOp]:  # noqa: ARG002
        return []


class SessionTransport(TicketAdapter):
    name = "carried"

    def move(self, key: str, status_name: str) -> list[CarryOp]:
        return [CarryOp("transition", key, status_name)]

    def comment(self, key: str, text: str) -> list[CarryOp]:
        return [CarryOp("comment", key, text)]


class FakeAdapter(TicketAdapter):
    """Tests only: holds a status per key and records every call."""

    name = "fake"

    def __init__(self, statuses: dict[str, str] | None = None):
        self.statuses = dict(statuses or {})
        self.calls: list[tuple[str, str, str]] = []

    def move(self, key: str, status_name: str) -> list[CarryOp]:
        self.calls.append(("move", key, status_name))
        self.statuses[key] = status_name
        return []

    def comment(self, key: str, text: str) -> list[CarryOp]:
        self.calls.append(("comment", key, text))
        return []


TRANSPORTS = {"none": NoneAdapter, "jira": SessionTransport}


def adapter_for(crew: dict) -> TicketAdapter:
    ticketing = str((crew.get("board") or {}).get("ticketing") or "none")
    if ticketing not in TRANSPORTS:
        raise ValueError(
            f"board.ticketing {ticketing!r} has no transport (known: {', '.join(TRANSPORTS)})"
        )
    return TRANSPORTS[ticketing]()
