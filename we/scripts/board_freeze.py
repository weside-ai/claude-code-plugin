#!/usr/bin/env python3
"""The freeze flag: while it stands, the merge hook (`hooks/automerge_gate.py`) refuses every merge
and every auto-merge arm, in every repo, naming the reason.

The flag is `freeze.json` in the board's state directory (beside `board.json`, `board.file` in the
crew): `{"since", "by", "reason", "repos", "disarmed", "not_disarmed"}`. `board.py freeze` and
`board.py unfreeze` are its only writers; the hook only reads it (`read_flag`).

  * `freeze` writes the flag first, then disarms every open PR with auto-merge armed in the named
    repos (`gh pr merge <N> -R <repo> --disable-auto`) and records them in `disarmed`. The flag is
    the order, the disarm is courtesy: a PR whose disarm or whose list fails is recorded in
    `not_disarmed` and the flag stands anyway.
  * `unfreeze` removes the flag and returns it, so the caller can print the disarmed PRs for
    re-arming through the hook. It re-arms nothing itself: a re-arm from a script passes no hook,
    so a one-way PR armed before the freeze would come back unchecked.
  * A flag file that exists but does not parse is a standing freeze (`FreezeError`; the hook
    refuses): a torn write must not lift it.

A brake against slips, not a boundary: any session can delete the file. The
boundary is the repository's ruleset and the owner's own merge. Pinned by `test_board.py`
(`TestFreeze`) and `hooks/test_automerge_gate.py` (freeze cases).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

FLAG_NAME = "freeze.json"
GhRunner = Callable[[list], Optional[str]]


class FreezeError(Exception):
    """The flag file exists but cannot be read as a flag."""


def flag_path(board_file: str | Path) -> Path:
    return Path(board_file).expanduser().with_name(FLAG_NAME)


def read_flag(path: Path) -> dict | None:
    """The standing flag, None when there is none; FreezeError when the file is unreadable."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise FreezeError(f"{path}: {exc.strerror}") from exc
    try:
        flag = json.loads(text)
    except ValueError as exc:
        raise FreezeError(f"{path} does not parse") from exc
    if not isinstance(flag, dict) or not isinstance(flag.get("reason"), str):
        raise FreezeError(f"{path} carries no reason")
    return flag


def _write_atomic(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".freeze.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _gh(args: list) -> str | None:
    try:
        out = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 else None


def _armed(repo: str, gh: GhRunner) -> list[int] | None:
    raw = gh(
        [
            "pr",
            "list",
            "-R",
            repo,
            "--state",
            "open",
            "--json",
            "number,autoMergeRequest",
            "--limit",
            "500",
        ]
    )
    try:
        prs = json.loads(raw or "")
        return sorted(p["number"] for p in prs if p.get("autoMergeRequest"))
    except (ValueError, TypeError, KeyError):
        return None


def freeze(
    path: Path, reason: str, repos: list[str], by: str, gh: GhRunner = _gh, now: str | None = None
) -> dict:
    """Write the flag, disarm the armed PRs of `repos`, record them; returns the flag."""
    if not reason.strip():
        raise FreezeError("a freeze needs a reason")
    stamp = now or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    try:
        standing = read_flag(path) or {}
    except FreezeError:
        standing = {}
    flag = {
        "since": standing.get("since") or stamp,
        "by": by,
        "reason": reason,
        "repos": sorted(set(standing.get("repos") or []) | set(repos)),
        # A second freeze keeps what the first disarmed: `unfreeze` must list every PR.
        "disarmed": list(standing.get("disarmed") or []),
        "not_disarmed": list(standing.get("not_disarmed") or []),
    }
    _write_atomic(path, flag)
    for repo in repos:
        armed = _armed(repo, gh)
        if armed is None:
            flag["not_disarmed"].append({"repo": repo, "why": "listing the open PRs failed"})
            continue
        for number in armed:
            ok = gh(["pr", "merge", str(number), "-R", repo, "--disable-auto"]) is not None
            entry = {"repo": repo, "number": number}
            if entry in flag["disarmed"]:
                continue
            if ok:
                flag["disarmed"].append(entry)
            else:
                flag["not_disarmed"].append({**entry, "why": "--disable-auto failed"})
    _write_atomic(path, flag)
    return flag


def unfreeze(path: Path) -> dict | None:
    """Remove the flag; returns what stood (None when nothing did). A torn flag is removed too."""
    try:
        flag = read_flag(path)
    except FreezeError:
        flag = {"reason": "(unreadable flag)", "disarmed": []}
    try:
        path.unlink()
    except FileNotFoundError:
        return None
    return flag
