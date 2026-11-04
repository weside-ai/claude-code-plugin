#!/usr/bin/env python3
"""A master's epic state from git: its plan, status, Updates Log and open PRs.

Read by ``hooks/compact_on_start.py`` (the epic block after a compaction) and
``hooks/epic_age_precompact.py`` (is the Updates Log stale?).

- ``resolve(board_line, roots)``: the epic number is the board line's ``epic`` field (a key or a
  number), else the trailing number of its ``name`` (the crew's ``naming.master``,
  ``<word>-<number>``); the plan is the one ``docs/plans/*-epic.md`` under ``roots`` whose
  frontmatter ``ticket:`` ends in ``-<number>`` or whose ``linked_epics`` lists such a key. No
  match or two → ``EpicError`` with ``NOT_FOUND``.
- ``updates_log(text)``: the entries ``- YYYY-MM-DD — …`` under ``## Updates Log``, oldest first
  (logs run both ways).
- ``story_keys(root, key)``: the keys of ``docs/plans/*-story.md`` whose frontmatter has
  ``epic: <key>``, newest plan first.
- ``open_prs(...)``: one ``gh search prs`` over the epic and story keys (query cut at
  ``QUERY_CAP``), ``GH_TIMEOUT`` seconds; any failure → None ("unknown"). ``runner`` is injected.
- ``is_stale(newest, tz)``: the newest entry is dated before yesterday in ``tz``; a plan without
  an Updates Log is stale (the first epic update adds it).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

NOT_FOUND = "epic plan not found: set `epic` on your board line"
QUERY_CAP = 256
GH_TIMEOUT = 5
ENTRY = re.compile(r"^- \**(\d{4}-\d{2}-\d{2})\**\s*(.*)$")
DASHES = "\u2014\u2013 "
NUMBER = re.compile(r"(\d+)$")

Runner = Callable[..., subprocess.CompletedProcess]


class EpicError(Exception):
    """No single epic plan for this master."""


def frontmatter(text: str) -> dict[str, Any]:
    """The flat ``key: value`` lines of a plan's frontmatter; ``[a, b]`` becomes a list."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, Any] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if not sep or line[:1].isspace():
            continue
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            out[key.strip()] = [
                v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()
            ]
        else:
            out[key.strip()] = value.strip("'\"")
    return out


def epic_number(board_line: dict[str, Any]) -> str | None:
    for field in ("epic", "name"):
        match = NUMBER.search(str(board_line.get(field) or "").strip())
        if match:
            return match.group(1)
    return None


def _matches(meta: dict[str, Any], number: str) -> bool:
    keys = [meta.get("ticket") or ""]
    linked = meta.get("linked_epics")
    keys += linked if isinstance(linked, list) else []
    return any(str(k).endswith(f"-{number}") for k in keys if k)


def resolve(board_line: dict[str, Any], roots: list[Path]) -> Path:
    number = epic_number(board_line)
    if number is None:
        raise EpicError(NOT_FOUND)
    found: set[Path] = set()
    for root in roots:
        for plan in sorted((root / "docs" / "plans").glob("*-epic.md")):
            try:
                meta = frontmatter(plan.read_text(encoding="utf-8"))
            except OSError:
                continue
            if _matches(meta, number):
                found.add(plan.resolve())
    if len({p.name for p in found}) != 1:
        raise EpicError(NOT_FOUND)
    return sorted(found)[0]


def updates_log(text: str) -> list[tuple[str, str]]:
    """(date, text) of each Updates Log entry, oldest first; a wrapped line joins its entry."""
    entries: list[list[str]] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line.strip() == "## Updates Log"
            continue
        if not inside:
            continue
        match = ENTRY.match(line)
        if match:
            entries.append([match.group(1), match.group(2).lstrip(DASHES).strip()])
        elif entries and line.startswith("  ") and line.strip():
            entries[-1][1] += " " + line.strip()
    return sorted(((d, t) for d, t in entries), key=lambda e: e[0])


def story_keys(root: Path, key: str) -> list[str]:
    plans = []
    for plan in (root / "docs" / "plans").glob("*-story.md"):
        try:
            meta = frontmatter(plan.read_text(encoding="utf-8"))
        except OSError:
            continue
        if meta.get("epic") == key:
            story = meta.get("story") or meta.get("ticket") or plan.name[: -len("-story.md")]
            plans.append((plan.stat().st_mtime, str(story)))
    return [k for _, k in sorted(plans, reverse=True)]


def search_query(keys: list[str]) -> str:
    query = ""
    for key in keys:
        part = f'"{key}"' if not query else f' OR "{key}"'
        if len(query) + len(part) > QUERY_CAP:
            break
        query += part
    return query


def _run(cmd: list[str], cwd: Path, runner: Runner, timeout: int) -> subprocess.CompletedProcess:
    return runner(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False)


def origin_owner(cwd: Path, runner: Runner = subprocess.run) -> str | None:
    try:
        url = _run(["git", "remote", "get-url", "origin"], cwd, runner, GH_TIMEOUT).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"[:/]([^/:]+)/[^/]+?(?:\.git)?$", url)
    return match.group(1) if match else None


def open_prs(
    cwd: Path, keys: list[str], runner: Runner = subprocess.run
) -> list[dict[str, Any]] | None:
    owner = origin_owner(cwd, runner)
    if not owner or not keys:
        return None
    cmd = ["gh", "search", "prs", "--state", "open", "--owner", owner]
    cmd += ["--json", "number,title,url,repository", search_query(keys)]
    try:
        result = _run(cmd, cwd, runner, GH_TIMEOUT)
        data = json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return data if isinstance(data, list) else None


def today(tz: str, now: dt.datetime | None = None) -> dt.date:
    try:
        zone: dt.tzinfo = ZoneInfo(tz)
    except (KeyError, ValueError):  # an unknown zone or no tz database: UTC
        zone = dt.timezone.utc
    return (now or dt.datetime.now(dt.timezone.utc)).astimezone(zone).date()


def is_stale(newest: str | None, tz: str, now: dt.datetime | None = None) -> bool:
    if not newest:
        return True
    return dt.date.fromisoformat(newest) < today(tz, now) - dt.timedelta(days=1)
