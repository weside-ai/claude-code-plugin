#!/usr/bin/env python3
"""The freeze flag: while it stands, the merge hook (`hooks/automerge_gate.py`) refuses every merge
and every auto-merge arm in the repos the flag names (`repos`; `*` names every repo), naming the
reason.

The flag sits beside the board file (`board.file` in the crew) and carries the board's stem
(`flag_path`: `board.json` → `freeze.json`, `acme-board.json` → `acme-board-freeze.json`), so it is
one per crew, not one per folder: `{"since", "by", "reason", "repos", "disarmed", "not_disarmed",
"issues"}`. `board.py freeze` and `board.py unfreeze` are its only writers; the hook only reads it
(`read_flag`).

The freeze also reaches GitHub, where a repo's one-way gate reads it: an open issue labelled `merge-freeze`
(`FREEZE_LABEL`, the judge's contract in `fixtures/brake-self-merge/judge.json`) means frozen.

  * `freeze` opens one such issue in every repo of `issue_repos` (the named repos; for `*` every
    repo of the crew, `board.py` resolves them) unless one is open there already, and records the
    issues it opened in `issues`. An issue that fails to open lands in `not_disarmed` and the
    local flag stands anyway.
  * `unfreeze` closes only the issues the flag recorded; an issue someone else opened (the owner's
    stop button on the phone) stays open, and a failed close is returned as `issues_open`.

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
    directory), else `board.json` in the crew's state directory (`crew.state_dir`: `WE_STATE_DIR`,
    the crew's `state_dir`, else the default folder). A crew with a board of its own is a separate team: a
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
FREEZE_LABEL = "merge-freeze"
DEFAULT_BOARD = str(Path(crew.DEFAULT_STATE_DIR) / crew.BOARD_NAME)
GhRunner = Callable[[list], Optional[str]]


class FreezeError(Exception):
    """The flag file exists but cannot be read as a flag."""


def flag_path(board_file: str | Path) -> Path:
    """The flag beside `board_file`, named after its stem like the board's logs: `board.json` keeps
    `freeze.json`, a second crew's `acme-board.json` gets `acme-board-freeze.json`, so a freeze in
    one crew does not brake another crew whose board shares the folder."""
    board = Path(board_file).expanduser()
    if board.stem == "board":
        return board.with_name(FLAG_NAME)
    return board.with_name(f"{board.stem}-{FLAG_NAME}")


def watched_board_files(start: str | Path | None, default: str = DEFAULT_BOARD) -> list[Path]:
    """The board file the merge hook reads a freeze beside, for a command run in `start`, as a
    one-item list: `crew.resolve_board` (the crew's `board.file`, relative to the crew file's
    directory, else `<state dir>/board.json` with the state directory from `WE_STATE_DIR` or the
    crew's `state_dir`), `default` where neither moves the folder. A missing or broken crew file
    resolves as no crew. `board.py` writes and the merge hook reads through this one function."""
    return [crew.resolve_board(start, default=default)]


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
    it). Fail closed: a flag without `scoped: true` (written before per-repo scope), no `repos`
    list, `*`, an entry that names no repo, or an unknown slug count as covered. Both sides are normalised (`norm_slug`): `-R github.com/o/r` is `o/r`."""
    repos = flag.get("repos")
    if flag.get("scoped") is not True:
        return True  # a flag from a writer before per-repo scope: `repos` was a disarm list only
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
    issue_repos: list[str] | None = None,
) -> dict:
    """Write the flag, open the freeze issue in `issue_repos` (default: `repos` without `*`),
    disarm the armed PRs of `disarm` (default: `repos` without `*`), record both; returns the
    flag."""
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
        "scoped": True,
        # A second freeze keeps what the first disarmed: `unfreeze` must list every PR.
        "disarmed": list(standing.get("disarmed") or []),
        "not_disarmed": list(standing.get("not_disarmed") or []),
        "issues": list(standing.get("issues") or []),
    }
    _write_atomic(path, flag)
    wanted = issue_repos if issue_repos is not None else [r for r in repos if r != "*"]
    if "*" in repos and not wanted:
        flag["not_disarmed"].append(
            {"repo": "*", "why": f"no repo here for a `{FREEZE_LABEL}` issue"}
        )
    for repo in wanted:
        _open_issue(repo, reason, by, flag, gh)
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


def issue_failures(flag: dict) -> list[dict]:
    """The `not_disarmed` entries for a freeze issue that did not open (GitHub not frozen there)."""
    return [e for e in flag.get("not_disarmed") or [] if FREEZE_LABEL in str(e.get("why"))]


def _open_freeze_issues(repo: str, gh: GhRunner) -> list[int] | None:
    raw = gh(
        [
            "issue",
            "list",
            "-R",
            repo,
            "--label",
            FREEZE_LABEL,
            "--state",
            "open",
            "--json",
            "number",
        ]
    )
    try:
        return sorted(int(i["number"]) for i in json.loads(raw or ""))
    except (ValueError, TypeError, KeyError):
        return None


def _open_issue(repo: str, reason: str, by: str, flag: dict, gh: GhRunner) -> None:
    """Open the freeze issue in `repo` unless one is open; record it in `issues` or the failure in
    `not_disarmed`."""
    if any(i.get("repo") == repo for i in flag["issues"]):
        return
    standing = _open_freeze_issues(repo, gh)
    if standing is None:
        flag["not_disarmed"].append(
            {"repo": repo, "why": f"listing the `{FREEZE_LABEL}` issues failed"}
        )
        return
    if standing:
        return  # someone else's freeze issue stands; it is theirs to close
    # gh refuses a label the repo lacks: create it first (`--force` keeps an existing one).
    gh(["label", "create", FREEZE_LABEL, "-R", repo, "--color", "b60205", "--force"])
    out = gh(
        [
            "issue",
            "create",
            "-R",
            repo,
            "--label",
            FREEZE_LABEL,
            "--title",
            f"Merge freeze: {reason}"[:200],
            "--body",
            f"Frozen by {by}: {reason}\n\nWhile this issue is open no one-way PR merges itself. "
            "`board.py unfreeze` closes it; closing it by hand lifts the GitHub side only.",
        ]
    )
    number = (out or "").strip().rstrip("/").rsplit("/", 1)[-1]
    if out is None or not number.isdigit():
        flag["not_disarmed"].append(
            {"repo": repo, "why": f"opening the `{FREEZE_LABEL}` issue failed"}
        )
        return
    flag["issues"].append({"repo": repo, "number": int(number)})


def unfreeze(path: Path, gh: GhRunner = _gh) -> dict | None:
    """Remove the flag and close the freeze issues it opened; returns what stood (None when nothing
    did), with `issues_open` listing each issue whose close failed. A torn flag is removed too."""
    try:
        flag = read_flag(path)
    except FreezeError:
        flag = {"reason": "(unreadable flag)", "disarmed": []}
    try:
        path.unlink()
    except FileNotFoundError:
        return None
    flag["issues_open"] = []
    for issue in flag.get("issues") or []:
        try:
            repo, number = str(issue["repo"]), int(issue["number"])
        except (KeyError, TypeError, ValueError):
            continue
        closed = gh(
            [
                "issue",
                "close",
                str(number),
                "-R",
                repo,
                "--comment",
                f"Unfrozen: {flag.get('reason')}",
            ]
        )
        if closed is None:
            flag["issues_open"].append({"repo": repo, "number": number})
    return flag
