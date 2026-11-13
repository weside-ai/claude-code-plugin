#!/usr/bin/env python3
"""Stop hook: a PR this session opened that went DIRTY sends the session back to merge the base.

The owner of a PR has no standing signal for "the default branch moved under you": the watcher
prints the merge state once, and a worker or peer session idles while its PR conflicts (retro
22.10.2026: the user found the conflicts, twice). This hook closes that at the turn boundary.

  * Own PRs: the URLs that `gh pr create` printed in this session's transcript, plus the `pr` of
    the statusline focus file `~/.claude/we-focus/<session>.json`. The transcript is read
    incrementally (offset in the state file).
  * Blocks once per PR head per session: the state file remembers each `<url>@<head>` it named.
    A new push (new head) that conflicts again is named again. No block while
    `stop_hook_active` is set.
  * No block for a PR with auto-merge off whose body carries `user merge:`: it waits for the human.
  * Re-arm: a PR this hook saw armed (`autoMergeRequest`) in an earlier sweep that is now open,
    ready, CLEAN (mergeable, required checks green) and without auto-merge blocks once, until the
    sweep sees it armed again. A crew's board showed such PRs green and unarmed after a conflict
    merge, a retargeted stacked PR and fix pushes, until someone happened to look. A PR never seen
    armed is left alone: a master arms late on purpose (`/we:master` § Close the run). Not in a worker (`WE_ROLE=worker`): it may not
    arm (`automerge_gate.py`); its starter's own sweep names the PR.
  * At most one `gh` sweep per THROTTLE_S per session, at most MAX_PRS PRs (the newest), at most
    SWEEP_BUDGET_S seconds of `gh` per sweep.
  * Fail-open on every error: a `gh` or parse failure lets the stop through.

State: `$WE_STATE_DIR/conflict-gate/<session>.json` (default `~/.claude/we-state`); a session's
file ages out after 45 days (`scripts/state_prune.py`).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import state_prune

THROTTLE_S = 120
MAX_PRS = 10
SWEEP_BUDGET_S = 20  # total gh time per sweep; the rest waits for the next sweep
_PR_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")


def _state_path(session: str) -> Path:
    root = Path(os.environ.get("WE_STATE_DIR") or Path.home() / ".claude" / "we-state")
    safe = re.sub(r"[^\w.-]", "_", session)
    return root / "conflict-gate" / f"{safe}.json"


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            _text(c.get("text") or c.get("content")) for c in content if isinstance(c, dict)
        )
    return ""


def _scan_entry(entry: dict, pending: set, prs: list) -> None:
    content = (entry.get("message") or {}).get("content")
    if not isinstance(content, list):
        return
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "tool_use":
            cmd = str((part.get("input") or {}).get("command", ""))
            if re.search(r"\bgh\s+pr\s+create\b", cmd):
                pending.add(part.get("id"))
        elif part.get("type") == "tool_result" and part.get("tool_use_id") in pending:
            pending.discard(part.get("tool_use_id"))
            for url in _PR_URL.findall(_text(part.get("content"))):
                if url not in prs:
                    prs.append(url)


def _scan_transcript(path: str, state: dict) -> None:
    """Add the PR URLs printed by `gh pr create` since the last offset to state['prs']."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    offset = state.get("offset", 0)
    if offset > size:
        offset = 0
    pending = set(state.get("pending", []))
    prs = state.setdefault("prs", [])
    with open(path, "rb") as fh:
        fh.seek(offset)
        for raw in fh:
            if not raw.endswith(b"\n"):
                break  # a line still being written: read it next time
            offset += len(raw)
            try:
                entry = json.loads(raw)
            except ValueError:
                continue
            _scan_entry(entry, pending, prs)
    state["offset"] = offset
    state["pending"] = sorted(p for p in pending if p)


def _focus_pr(session: str) -> tuple[str, str] | None:
    path = Path.home() / ".claude" / "we-focus" / f"{session}.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if isinstance(data.get("pr"), int) and data.get("dir"):
        return str(data["pr"]), str(data["dir"])
    return None


def _view(selector: str, cwd: str | None) -> dict | None:
    try:
        out = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                selector,
                "--json",
                "url,number,state,isDraft,mergeStateStatus,mergeable,headRefOid,autoMergeRequest,body,"
                "baseRefName",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
            cwd=cwd or None,
        )
        return json.loads(out.stdout) if out.returncode == 0 else None
    except Exception:
        return None


def _dirty(pr: dict) -> bool:
    if pr.get("state") != "OPEN":
        return False
    if pr.get("mergeStateStatus") != "DIRTY" and pr.get("mergeable") != "CONFLICTING":
        return False
    return not _waits_for_human(pr)


def _waits_for_human(pr: dict) -> bool:
    return not pr.get("autoMergeRequest") and "user merge:" in (pr.get("body") or "")


def _unarmed(pr: dict, watched: set) -> bool:
    """Green, ready, unarmed, and seen armed before: it lost its arm."""
    return (
        pr.get("url") in watched
        and pr.get("state") == "OPEN"
        and not pr.get("isDraft")
        and pr.get("mergeStateStatus") == "CLEAN"
        and not pr.get("autoMergeRequest")
        and not _waits_for_human(pr)
        and os.environ.get("WE_ROLE") != "worker"
    )


def _sweep(targets: list[tuple[str, str | None]], state: dict) -> str | None:
    """One `gh` pass over the session's PRs: the block reason, or None. Updates `state`."""
    named = set(state.get("named", []))
    watched = set(state.get("watched", []))
    lines, rearm, seen = [], [], set()
    started = time.monotonic()
    for selector, cwd in targets:
        if time.monotonic() - started > SWEEP_BUDGET_S:
            break
        pr = _view(selector, cwd)
        if not pr or pr.get("url") in seen:
            continue
        seen.add(pr.get("url"))
        key = f"{pr.get('url')}@{pr.get('headRefOid')}"
        head = str(pr.get("headRefOid"))[:9]
        if f"rearm:{key}" not in named and _unarmed(pr, watched):
            named.add(f"rearm:{key}")  # its own key: a later conflict on this head is still named
            watched.discard(pr.get("url"))
            rearm.append(
                f"PR #{pr.get('number')} ({pr.get('url')}) is green and ready on head {head} "
                "without auto-merge"
            )
            continue
        if pr.get("autoMergeRequest"):
            watched.add(pr.get("url"))
        dirty = _dirty(pr)
        if key in named or not dirty:
            continue
        named.add(key)
        lines.append(
            f"PR #{pr.get('number')} ({pr.get('url')}) is {pr.get('mergeStateStatus')}/"
            f"{pr.get('mergeable')} on head {head}"
        )
    state["named"] = sorted(named)
    state["watched"] = sorted(u for u in watched if u)
    parts = []
    if lines:
        parts.append(
            "; ".join(lines)
            + ". Merge the default branch in that PR's worktree (`git merge origin/<base>`), run the "
            "after-merge check, push once; or name why not."
        )
    if rearm:
        parts.append(
            "; ".join(rearm)
            + ". It lost its arm (a conflict, a ready event GitHub ran no workflow for, or a fix "
            "round's `--disable-auto`): arm it again per `/we:master` § Close the run, or name why "
            "not yet."
        )
    return " ".join(parts) + " This hook names each head once." if parts else None


def decide(payload: dict, now: float | None = None) -> str | None:
    """The block reason, or None. Updates the session's state file."""
    if payload.get("stop_hook_active") or payload.get("agent_id"):
        return None
    session = payload.get("session_id")
    if not session:
        return None
    path = _state_path(session)
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        state = {}
    now = time.time() if now is None else now
    if payload.get("transcript_path"):
        _scan_transcript(payload["transcript_path"], state)
    targets: list[tuple[str, str | None]] = [(u, None) for u in state.get("prs", [])[-MAX_PRS:]]
    focus = _focus_pr(session)
    if focus:
        targets.append(focus)
    reason = None
    if targets and now - state.get("checked", 0) >= THROTTLE_S:
        state["checked"] = now
        reason = _sweep(targets, state)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state))
        state_prune.prune(path.parent, "*.json")  # a session's state ages out (45 days)
    except OSError:
        pass
    return reason


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        reason = decide(payload)
    except Exception:
        return
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
