#!/usr/bin/env python3
"""PreToolUse hook (Agent): a dev worker runs as a background subagent, not as a teammate pane.

An `Agent` call with a `name` and no `isolation` spawns a visible teammate (a tmux pane); with
`isolation: "worktree"` or without a `name` the worker runs in the background. The owner decided
on 30.10.2026 that worker panes are off by default.

  * Denied: `subagent_type` starting with `we:dev-`, a non-empty `name`, no `isolation`.
  * Allowed: every other agent type (council lenses included), and every dispatch when the
    project's `.weside/config.json` (`CLAUDE_PROJECT_DIR`, else the payload's `cwd`) sets
    `agents.visible_teammates: true`.
  * Fail-open on every error.
"""

from __future__ import annotations

import json
import os
import sys

REASON = (
    "Worker panes are off: a `we:dev-*` dispatch with `name` and no `isolation` opens a teammate "
    "pane. Drop `name` (steer the worker by the returned agent id; give it the worktree path in "
    'its brief) or set `isolation: "worktree"`. `.weside/config.json` → '
    "`agents.visible_teammates: true` turns panes back on."
)


def _visible(root: str | None) -> bool:
    if not root:
        return False
    try:
        with open(os.path.join(root, ".weside", "config.json")) as fh:
            agents = json.load(fh).get("agents") or {}
    except Exception:
        return False
    return isinstance(agents, dict) and agents.get("visible_teammates") is True


def refusal(payload: dict) -> str | None:
    if payload.get("tool_name") != "Agent":
        return None
    args = payload.get("tool_input") or {}
    if not str(args.get("subagent_type") or "").startswith("we:dev-"):
        return None
    if not args.get("name") or args.get("isolation"):
        return None
    if _visible(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd")):
        return None
    return REASON


def main() -> None:
    try:
        reason = refusal(json.load(sys.stdin))
    except Exception:
        return
    if reason is None:
        return
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


if __name__ == "__main__":
    main()
