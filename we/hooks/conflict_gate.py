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
  * At most one `gh` sweep per THROTTLE_S per session, at most MAX_PRS PRs (the newest).
  * Fail-open on every error: a `gh` or parse failure lets the stop through.

State: `$WE_STATE_DIR/conflict-gate/<session>.json` (default `~/.claude/we-state`).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

THROTTLE_S = 120
MAX_PRS = 10
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
                "url,number,state,mergeStateStatus,mergeable,headRefOid,autoMergeRequest,body,baseRefName",
            ],
            capture_output=True,
            text=True,
            timeout=15,
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
    waits_for_human = not pr.get("autoMergeRequest") and "user merge:" in (pr.get("body") or "")
    return not waits_for_human


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
        named = set(state.get("named", []))
        lines, seen = [], set()
        for selector, cwd in targets:
            pr = _view(selector, cwd)
            if not pr or pr.get("url") in seen:
                continue
            seen.add(pr.get("url"))
            key = f"{pr.get('url')}@{pr.get('headRefOid')}"
            if key in named or not _dirty(pr):
                continue
            named.add(key)
            lines.append(
                f"PR #{pr.get('number')} ({pr.get('url')}) is {pr.get('mergeStateStatus')}/"
                f"{pr.get('mergeable')} on head {str(pr.get('headRefOid'))[:9]}"
            )
        state["named"] = sorted(named)
        if lines:
            reason = (
                "; ".join(lines)
                + ". Merge the default branch in that PR's worktree (`git merge origin/<base>`), run the "
                "after-merge check, push once; or name why not. This hook names each head once."
            )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state))
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
