#!/usr/bin/env python3
"""Who is the master of a PR or a red run: the ``epic_master`` target of the event poller.

Reads local files only (no API): the crew's board (``crew.resolve_board``), its ticket snapshot
beside it (``ticket_snapshot.path_for``) and the project clone's story plans.

Key
    The crew's ``naming.key`` regex (default ``[A-Z]+-\\d+``) on the PR's head branch, else on its
    title. The title only matches: it never enters a line or a field.
Key → epic
    ``stories[KEY].epic`` of the ticket snapshot, else ``epic:`` in ``docs/plans/<KEY>-story.md``
    of the project clone, else the key itself when the snapshot lists it as an epic.
Epic → board lines
    A line whose ``keys`` hold the story key wins; else every line whose ``epic`` is the epic or
    whose ``keys`` hold it. A line in state ``done`` drops, and so does a companion's line
    (``companion`` set): a companion owns and reviews, the build master without a companion builds
    and acts on the line. Two lines on one epic both receive.
    A parked line drops before the key wins (but for ``main_red``): an active master of the same
    epic then receives.
Board line → receiver
    The fresh tail presence whose ``session_id`` equals the line's. A parked line receives
    ``main_red`` (damage to its own epic) and nothing else: every other kind goes to the
    coordinator's delta with the epic, as does a line without a running tail.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import crew as crew_mod  # noqa: E402
import ticket_snapshot  # noqa: E402

TARGET = "epic_master"
DEFAULT_KEY = r"[A-Z]+-\d+"
PARKED_KINDS = ("main_red",)  # the one kind a parked master still receives
_EPIC_LINE = re.compile(r"^epic:\s*['\"]?([A-Za-z0-9_-]+)['\"]?\s*$", re.MULTILINE)


def key_rx(crew: dict | None) -> re.Pattern:
    naming = (crew or {}).get("naming")
    text = naming.get("key") if isinstance(naming, dict) else None
    try:
        return re.compile(text if isinstance(text, str) and text else DEFAULT_KEY)
    except re.error:
        return re.compile(DEFAULT_KEY)


def key_of(rx: re.Pattern, branch: Any, title: Any = None) -> str | None:
    """The first key in the branch, else in the title; None without one."""
    for text in (branch, title):
        found = rx.search(str(text or ""))
        if found:
            return found.group(0)
    return None


@dataclass
class Owners:
    """The receivers of one event: ``to`` session keys (presence names), ``epic`` or why none."""

    to: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)  # the receiving board lines' names
    epic: str | None = None
    reason: str = ""


class Resolver:
    """One round's view of board, snapshot and plans (read once per round)."""

    def __init__(self, root: Path, crew: dict | None = None):
        self.root = Path(root)
        self.crew = crew or {}
        self.rx = key_rx(self.crew)
        try:
            board_path = crew_mod.resolve_board(self.root)
        except Exception:  # an unreadable crew resolves as no board
            board_path = None
        self.lines = _board_lines(board_path)
        self.stories, self.epics = _snapshot(board_path)

    def epic_of(self, key: str) -> str | None:
        rec = self.stories.get(key)
        if isinstance(rec, dict) and isinstance(rec.get("epic"), str):
            return rec["epic"]
        plan = self.root / "docs" / "plans" / f"{key}-story.md"
        try:
            head = plan.read_text(encoding="utf-8")[:4000]
        except OSError:
            head = ""
        found = _EPIC_LINE.search(head.split("\n---", 1)[0]) if head.startswith("---") else None
        if found:
            return found.group(1)
        return key if key in self.epics else None

    def board_lines(self, key: str | None, epic: str, kind: str = "") -> list[dict]:
        live = [
            x
            for x in self.lines
            if x.get("state") != "done"
            and not x.get("companion")
            and x.get("session_id")
            and (kind in PARKED_KINDS or x.get("state") != "parked")
        ]
        if key:
            hit = [x for x in live if key in (x.get("keys") or [])]
            if hit:
                return hit
        return [x for x in live if x.get("epic") == epic or epic in (x.get("keys") or [])]

    def owners(self, kind: str, fields: dict, presences: list[dict]) -> Owners:
        """The receivers of an event addressed to ``epic_master``."""
        key = fields.get("story") if isinstance(fields.get("story"), str) else None
        epics = [e for e in fields.get("epics") or [] if isinstance(e, str)]
        if not epics:
            epic = self.epic_of(key) if key else None
            if epic is None:
                return Owners(reason="epic unknown")
            epics = [epic]
        out = Owners(epic=", ".join(epics))
        by_sid = {p.get("session_id"): p for p in presences if p.get("session_id")}
        for epic in epics:
            for line in self.board_lines(key if len(epics) == 1 else None, epic, kind):
                p = by_sid.get(line.get("session_id"))
                if p and p["name"] not in out.to:
                    out.to.append(p["name"])
                    out.names.append(str(line.get("name") or ""))
        if not out.to:
            out.reason = "no running master"
        return out


def _board_lines(path: Path | None) -> list[dict]:
    try:
        board = json.loads(path.read_text(encoding="utf-8")) if path else {}
    except (OSError, ValueError):
        return []
    lines = board.get("sessions") if isinstance(board, dict) else None
    return [x for x in lines or [] if isinstance(x, dict)]


def _snapshot(board: Path | None) -> tuple[dict, dict]:
    try:
        doc = (
            json.loads(ticket_snapshot.path_for(board).read_text(encoding="utf-8"))
            if board
            else {}
        )
    except (OSError, ValueError):
        return {}, {}
    if not isinstance(doc, dict):
        return {}, {}
    stories = doc.get("stories") if isinstance(doc.get("stories"), dict) else {}
    epics = doc.get("epics") if isinstance(doc.get("epics"), dict) else {}
    return stories, epics
