#!/usr/bin/env python3
"""Hook: the session's tmux window turns white while it waits for the human, and back when they answer.

A session in one of many tmux windows that asks a question or waits for a permission is easy to
miss; the window title in the tmux status bar shows it, as Codex does.

  * On: `PreToolUse` of `AskUserQuestion`, and `Notification` of the types in `WAITING`.
  * Off: `UserPromptSubmit`, `PostToolUse`, `Stop`, `SessionStart`, `SessionEnd`. An approved
    permission fires no hook of its own, only the tool's `PostToolUse` (hooks reference), so
    `PostToolUse` matches every tool; a denial ends at the next prompt or `Stop`. Off unsets the
    window option, so the window falls back to the session's style.
  * Both set `window-status-style` and `window-status-current-style` of the window holding
    `$TMUX_PANE`.
  * Nothing without `$TMUX_PANE`, in a background session (`$CLAUDE_JOB_DIR`), in a subagent
    (`agent_id`), or with the option `tmuxAttention` off. The style is the option
    `tmuxAttentionStyle`, default `bg=white,fg=black`. Options come from
    `CLAUDE_PLUGIN_OPTION_<KEY>`, else from `pluginConfigs` in `~/.claude/settings.json`.
  * Fail-open and silent: every error exits 0 without output.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

STYLE = "bg=white,fg=black"
OPTIONS = ("window-status-style", "window-status-current-style")
WAITING = ("permission_prompt", "idle_prompt", "elicitation_dialog", "elicitation_url_dialog")
OFF = ("UserPromptSubmit", "PostToolUse", "Stop", "SessionStart", "SessionEnd")


def option(environ: dict, settings: dict, key: str) -> object:
    env = environ.get("CLAUDE_PLUGIN_OPTION_" + key.upper())
    if env is None:
        return settings.get(key)
    if env.strip().lower() in ("false", "0", "no", "off"):
        return False
    return env


def plugin_options() -> dict:
    try:
        with open(os.path.expanduser("~/.claude/settings.json")) as fh:
            settings = json.load(fh)
        opts = settings.get("pluginConfigs", {}).get("we@weside-ai", {}).get("options", {})
        return opts if isinstance(opts, dict) else {}
    except Exception:
        return {}


def wants(payload: dict) -> bool | None:
    """True turns the highlight on, False off, None leaves the window alone."""
    event = payload.get("hook_event_name")
    if event == "PreToolUse":
        return True if payload.get("tool_name") == "AskUserQuestion" else None
    if event == "Notification":
        return True if payload.get("notification_type") in WAITING else None
    return False if event in OFF else None


def commands(payload: dict, environ: dict, settings: dict) -> list[list[str]]:
    pane = environ.get("TMUX_PANE")
    if not pane or environ.get("CLAUDE_JOB_DIR") or payload.get("agent_id"):
        return []
    if option(environ, settings, "tmuxAttention") is False:
        return []
    on = wants(payload)
    if on is None:
        return []
    style = option(environ, settings, "tmuxAttentionStyle") or STYLE
    if on:
        return [["tmux", "set-window-option", "-t", pane, opt, style] for opt in OPTIONS]
    return [["tmux", "set-window-option", "-u", "-t", pane, opt] for opt in OPTIONS]


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        for cmd in commands(payload, dict(os.environ), plugin_options()):
            subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
            )
    except Exception:
        return


if __name__ == "__main__":
    main()
