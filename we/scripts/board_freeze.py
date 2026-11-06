#!/usr/bin/env python3
"""The freeze flag: while it stands, the merge hook (`hooks/automerge_gate.py`) refuses every merge
and every auto-merge arm in the repos the flag names (`repos`; `*` names every repo), naming the
reason.

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
  * `repos` scopes the flag: a merge in a repo the flag does not name passes it. `*`
    names every repo of the crews reading this board; `board.py freeze` without `--repo` writes
    it (a freeze from the wrong checkout must not silently miss the repo it is for) and disarms
    the current repo's armed PRs. A flag without a `repos` list counts for every repo.
  * The hook reads a flag only beside the board file `watched_board_files` names: the crew's
    `board.file` when the crew names one (a relative one resolved against the crew file's
    directory), else the default board. A crew with a board of its own is a separate team: a
    freeze on the default board does not reach it, `*` included. `freeze` and `unfreeze` refuse any other `--board`, so no flag stands where no
    hook sees it.

A brake against slips, not a boundary: any session can delete the file. The
boundary is the repository's ruleset and the owner's own merge. Pinned by `test_board.py`
(`TestFreeze`) and `hooks/test_automerge_gate.py` (freeze cases).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crew

FLAG_NAME = "freeze.json"
DEFAULT_BOARD = "~/.claude/we-state/board.json"
GhRunner = Callable[[list], Optional[str]]


class FreezeError(Exception):
    """The flag file exists but cannot be read as a flag."""


def flag_path(board_file: str | Path) -> Path:
    return Path(board_file).expanduser().with_name(FLAG_NAME)


def watched_board_files(start: str | Path | None, default: str = DEFAULT_BOARD) -> list[Path]:
    """The board file the merge hook reads a freeze beside, for a command run in `start`, as a
    one-item list: the crew's `board.file` (relative to the crew file's directory) when the crew
    names one, else the default board. A missing or broken crew file names the default board."""
    default_file = Path(default).expanduser()
    try:
        crew_file, crew_data = crew.find_and_load(start)
    except crew.CrewError:
        return [default_file]
    board = (crew_data or {}).get("board")
    name = board.get("file") if isinstance(board, dict) else None
    if crew_file is not None and isinstance(name, str) and name.strip():
        return [crew_file.parent / Path(name.strip()).expanduser()]
    return [default_file]


def norm_slug(value: object) -> str | None:
    """`owner/repo` from a slug, `HOST/OWNER/REPO` or a GitHub URL (lower case, no `.git`), else
    None: a bare name or anything else names no repo."""
    text = str(value or "").strip().lower()
    text = text.split("://", 1)[-1].split("#", 1)[0].split("?", 1)[0].rstrip("/")
    text = text.removesuffix(".git")
    parts = [p for p in text.replace(":", "/").split("/") if p]
    if "pull" in parts:
        parts = parts[: parts.index("pull")]
    if len(parts) < 2:
        return None
    return f"{parts[-2]}/{parts[-1]}"


def covers(flag: dict, slug: str | None) -> bool:
    """Whether a standing `flag` freezes a merge in repo `slug` (None when the hook cannot name
    it). Fail closed: no `repos` list, `*`, an entry that names no repo, or an unknown slug count
    as covered. Both sides are normalised (`norm_slug`): `-R github.com/o/r` is `o/r`."""
    repos = flag.get("repos")
    if not isinstance(repos, list) or not repos or "*" in repos:
        return True
    named = [norm_slug(r) for r in repos]
    target = norm_slug(slug)
    if target is None or None in named:
        return True
    return target in named


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
    path: Path,
    reason: str,
    repos: list[str],
    by: str,
    gh: GhRunner = _gh,
    now: str | None = None,
    disarm: list[str] | None = None,
) -> dict:
    """Write the flag, disarm the armed PRs of `disarm` (default: `repos` without `*`), record
    them; returns the flag."""
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
    targets = disarm if disarm is not None else [r for r in repos if r != "*"]
    if "*" in repos and not targets:
        flag["not_disarmed"].append(
            {"repo": "*", "why": "no repo here to disarm; armed PRs elsewhere still auto-merge"}
        )
    for repo in targets:
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
