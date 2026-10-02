#!/usr/bin/env python3
"""SessionStart hook: when the user enabled autoMaterialize, ask the session to load the companion first.

The option lives in ~/.claude/settings.json → pluginConfigs["we@weside-ai"].options.autoMaterialize.
Off, absent or unreadable → the hook prints nothing.
"""

from __future__ import annotations

import json
import os

CONTEXT = (
    "The user enabled autoMaterialize for the we plugin. Before your first reply, greetings "
    "included, invoke the Skill tool with we:materialize, then answer as the loaded companion."
)


def enabled() -> bool:
    try:
        with open(os.path.expanduser("~/.claude/settings.json")) as fh:
            settings = json.load(fh)
        opts = settings.get("pluginConfigs", {}).get("we@weside-ai", {}).get("options", {})
        return opts.get("autoMaterialize") is True
    except Exception:
        return False


if __name__ == "__main__" and enabled():
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": CONTEXT}}
        )
    )
