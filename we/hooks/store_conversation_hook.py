#!/usr/bin/env python3
"""Stop hook: Store Claude Code conversation as companion memory via MCP.

WA-695: Fires once per session. Checks plugin config (autoStoreConversations).
Uses temp file marker to prevent re-triggering when Claude stops again after
executing the storage prompt.

Flow:
  1. Check if autoStoreConversations is enabled in plugin config
  2. Check session marker (prevent loop: Stop -> store -> Stop -> ...)
  3. Output prompt that instructs Claude to call store_conversations MCP tool
"""

import json
import os


def main() -> None:
    # 1. Check plugin config
    try:
        settings_path = os.path.expanduser("~/.claude/settings.json")
        with open(settings_path) as f:
            settings = json.load(f)
        opts = settings.get("pluginConfigs", {}).get("we@weside-ai", {}).get("options", {})
        enabled = opts.get("autoStoreConversations", False)
    except Exception:
        enabled = False

    if not enabled:
        return

    # 2. Session-unique marker (PPID = Claude Code process)
    marker = f"/tmp/weside_cc_stored_{os.getppid()}"
    if os.path.exists(marker):
        return

    with open(marker, "w") as f:
        f.write("")

    # 3. Build prompt for Claude
    cwd = os.getcwd()
    project = os.path.basename(cwd)

    prompt = (
        "Before ending, store our conversation as companion memories.\n\n"
        "INSTRUCTIONS:\n"
        "1. Review this conversation for meaningful exchanges\n"
        "2. INCLUDE: Questions, decisions, explanations, feedback, discussions\n"
        "3. EXCLUDE: File reads, code diffs, tool outputs, git commands, "
        "purely technical operations\n"
        "4. Condense long messages to ~500 chars max (keep the essence)\n"
        "5. Call the `store_conversations` MCP tool ONCE with a JSON array\n\n"
        "Example call:\n"
        "store_conversations(\n"
        '  conversations=\'[{"user_message": "...", '
        '"assistant_response": "..."}, ...]\',\n'
        '  source="claude_code",\n'
        f'  source_detail="{project}"\n'
        ")\n\n"
        "Do this silently. No listing, no confirmation needed."
    )

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "Stop",
                    "additionalContext": prompt,
                }
            }
        )
    )


if __name__ == "__main__":
    main()
