#!/usr/bin/env python3
"""SessionStart hook: remind the user of open instruction-loop work.

Shows one `systemMessage` line (user-visible, no model context) when the repo has a
`.weside/optimization/` store with open inbox entries and the last `/we:optimize` is
older than `optimization.reminder_days` (default 14) or never ran. Silent on resume,
clear and compact, without a store, and when `.weside/config.json` sets
`optimization.reminder: false`. Store format: references/optimization-store.md.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_DAYS = 14


def repo_root(cwd: str) -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return Path(result.stdout.strip()) if result.returncode == 0 else None


def staging_dir(root: Path) -> Path | None:
    """`~/.claude/we-inbox/<owner>-<name>/`, named after the origin URL."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$", result.stdout.strip())
    if result.returncode != 0 or not match:
        return None
    return Path.home() / ".claude" / "we-inbox" / f"{match.group(1)}-{match.group(2)}"


def last_optimize(charter: Path) -> dt.date | None:
    try:
        text = charter.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"^last_optimize:\s*(\d{4}-\d{2}-\d{2})\s*$", text, re.MULTILINE)
    return dt.date.fromisoformat(match.group(1)) if match else None


def message(root: Path, today: dt.date, staged: Path | None = None) -> str | None:
    store = root / ".weside" / "optimization"
    if not store.is_dir():
        return None
    try:
        config = json.loads((root / ".weside" / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        config = {}
    section = config.get("optimization") or {}
    if section.get("reminder") is False:
        return None
    entries = [*(store / "inbox").glob("*.md"), *(staged.glob("*.md") if staged else [])]
    keys = {re.sub(r"^\d{4}-\d{2}-\d{2}-", "", p.stem) for p in entries}
    if not keys:
        return None
    last = last_optimize(store / "CHARTER.md")
    days = (today - last).days if last else None
    if days is not None and days < int(section.get("reminder_days", DEFAULT_DAYS)):
        return None
    age = f"{days} days ago" if days is not None else "never"
    return (
        f"we: {len(keys)} open instruction finding(s), last /we:optimize {age}. "
        "Run /we:optimize, or set optimization.reminder to false in .weside/config.json."
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("source", "startup") != "startup":
        return 0
    root = repo_root(payload.get("cwd") or ".")
    today = dt.datetime.now(dt.UTC).astimezone().date()
    text = message(root, today, staging_dir(root)) if root else None
    if text:
        print(json.dumps({"systemMessage": text}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
