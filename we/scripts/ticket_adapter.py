#!/usr/bin/env python3
"""The ticketing adapter behind `board.py`'s moves: one protocol, one implementation per transport.

`TicketAdapter.move(key, status_name)` returns the list of `CarryOp`s the calling session still
has to carry out with its own ticketing tool; an empty list means nothing is left to carry.
`adapter_for(crew)` picks the transport by the crew file's `board.ticketing`:

- `none` → `NoneAdapter`: no ticketing system; the transitions row says `ticket: none`.

`FakeAdapter` is for tests only and is injected in code (`board.main(argv, adapter=…)`); no
command-line flag selects it. Further transports drop in behind the same protocol as one more
arm of `adapter_for`: the session transport (`jira`, a `carry:` line the session executes) and,
once a ticketing account for agents exists, a REST transport that moves the ticket itself and
re-reads its status.
"""

from __future__ import annotations

from typing import NamedTuple


class CarryOp(NamedTuple):
    """One operation the session carries with its ticketing tool: `op` on `key` with `value`."""

    op: str
    key: str
    value: str

    def as_json(self) -> dict:
        return {"op": self.op, "key": self.key, "value": self.value}


class TicketAdapter:
    """Protocol: `name` goes into the transitions row as `ticket`; `move` names what to carry."""

    name = "abstract"

    def move(self, key: str, status_name: str) -> list[CarryOp]:
        raise NotImplementedError


class NoneAdapter(TicketAdapter):
    name = "none"

    def move(self, key: str, status_name: str) -> list[CarryOp]:  # noqa: ARG002
        return []


class FakeAdapter(TicketAdapter):
    """Tests only: holds a status per key and records every call."""

    name = "fake"

    def __init__(self, statuses: dict[str, str] | None = None):
        self.statuses = dict(statuses or {})
        self.calls: list[tuple[str, str]] = []

    def move(self, key: str, status_name: str) -> list[CarryOp]:
        self.calls.append((key, status_name))
        self.statuses[key] = status_name
        return []


TRANSPORTS = {"none": NoneAdapter}


def adapter_for(crew: dict) -> TicketAdapter:
    ticketing = str((crew.get("board") or {}).get("ticketing") or "none")
    if ticketing not in TRANSPORTS:
        raise ValueError(
            f"board.ticketing {ticketing!r} has no transport (known: {', '.join(TRANSPORTS)})"
        )
    return TRANSPORTS[ticketing]()
