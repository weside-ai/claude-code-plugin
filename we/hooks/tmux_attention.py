#!/usr/bin/env python3
"""Hook: the session's tmux window shows, by event alone, whether it waits for the human.

A session in one of many tmux windows that asks a question or waits for a permission is easy to
miss; the window title in the tmux status bar shows it, as Codex does. Three states, set
mechanically per event:

  * White, the human must act: `PreToolUse` of `AskUserQuestion`, and `Notification` of the
    types in `WAITING`. Style: option `tmuxAttentionStyle`, default `bg=white,fg=black`.
  * Grey, done and resting: `Stop`, and `Notification` of `idle_prompt`. Style: option
    `tmuxIdleStyle`, default `bg=colour240,fg=white`. `idle_prompt` never overwrites white: it
    reads the window's current style (`tmux show-options -w -v`) and leaves an open question
    white.
  * Normal: `UserPromptSubmit`, `PostToolUse`, `SessionStart`, `SessionEnd`. An approved
    permission fires no hook of its own, only the tool's `PostToolUse` (hooks reference), so
    `PostToolUse` matches every tool, synchronously so an earlier tool's normal cannot land after
    a later white; a denial ends at the next prompt or `Stop`. Normal unsets the window option,
    so the window falls back to the session's style.
  * All set `window-status-style` and `window-status-current-style` of the window holding
    `$TMUX_PANE`.
  * Nothing without `$TMUX_PANE`, in a background session (`$CLAUDE_JOB_DIR`), in a subagent
    (`agent_id`), or with the option `tmuxAttention` off. Options come from
    `CLAUDE_PLUGIN_OPTION_<KEY>`, else from `pluginConfigs` in `~/.claude/settings.json`.
  * Fail-open and silent: every error exits 0 without output.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

STYLE = "bg=white,fg=black"
IDLE_STYLE = "bg=colour240,fg=white"
OPTIONS = ("window-status-style", "window-status-current-style")
WAITING = ("permission_prompt", "elicitation_dialog", "elicitation_url_dialog")
IDLE = "idle_prompt"
OFF = ("UserPromptSubmit", "PostToolUse", "SessionStart", "SessionEnd")

ATTENTION, RESTING, NORMAL = "attention", "resting", "normal"


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


def wants(payload: dict) -> str | None:
    """The state the event asks for; None leaves the window alone."""
    event = payload.get("hook_event_name")
    if event == "PreToolUse":
        return ATTENTION if payload.get("tool_name") == "AskUserQuestion" else None
    if event == "Notification":
        kind = payload.get("notification_type")
        if kind in WAITING:
            return ATTENTION
        return RESTING if kind == IDLE else None
    if event == "Stop":
        return RESTING
    return NORMAL if event in OFF else None


def current_style(pane: str) -> str:
    """The window's own `window-status-style`, empty when unset or unreadable."""
    try:
        res = subprocess.run(
            ["tmux", "show-options", "-w", "-v", "-t", pane, OPTIONS[0]],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        return res.stdout.strip() if res.returncode == 0 else ""
    except Exception:
        return ""


def commands(
    payload: dict, environ: dict, settings: dict, current=current_style
) -> list[list[str]]:
    pane = environ.get("TMUX_PANE")
    if not pane or environ.get("CLAUDE_JOB_DIR") or payload.get("agent_id"):
        return []
    if option(environ, settings, "tmuxAttention") is False:
        return []
    state = wants(payload)
    if state is None:
        return []
    if state == NORMAL:
        return [["tmux", "set-window-option", "-u", "-t", pane, opt] for opt in OPTIONS]
    attention = option(environ, settings, "tmuxAttentionStyle") or STYLE
    if state == ATTENTION:
        style = attention
    else:
        if payload.get("hook_event_name") == "Notification" and current(pane) == attention:
            return []
        style = option(environ, settings, "tmuxIdleStyle") or IDLE_STYLE
    return [["tmux", "set-window-option", "-t", pane, opt, style] for opt in OPTIONS]


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
