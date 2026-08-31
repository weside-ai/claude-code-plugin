#!/usr/bin/env python3
"""Install the plugin's statusline into the user's Claude Code settings.

Single owner of the whole procedure: detect what is configured now, copy the
shipped script to a stable path, merge the ``statusLine`` key into
``~/.claude/settings.json``, back up what was there, and revert on request.
Skills only call this script and relay its output.

Why a copy instead of pointing at the plugin: ``${CLAUDE_PLUGIN_ROOT}`` changes
on every plugin update, so a plugin path baked into settings.json breaks at the
next ``claude plugins update``. The copy lives at ``~/.claude/we-statusline.js``
and is refreshed whenever this script runs and the bytes differ.

Modes::

    --status    report node availability, install state, current statusLine
    --apply     install (refuses a foreign statusLine without --force)
    --force     with --apply: replace a foreign statusLine, backing it up
    --revert    restore the backed-up statusLine (or remove ours)

Exit codes: 0 = done / nothing to do, 1 = blocked (reason on stdout), 2 = usage.
Python stdlib only.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

SETTINGS = Path.home() / ".claude" / "settings.json"
TARGET = Path.home() / ".claude" / "we-statusline.js"
BACKUP = Path.home() / ".claude" / "we-statusline-backup.json"
SOURCE = Path(__file__).resolve().parent / "statusline.js"

# Written into settings.json verbatim — `~` expands, and an absolute path would
# bake this machine's username into a file users mirror between machines.
COMMAND = "node ~/.claude/we-statusline.js"

# The three verdicts /we:setup Step 4b branches on. Keep them short and keep both
# sides in sync — scripts/validate-consistency.py asserts the skill names each one.
VERDICT_OFFER = "offer to install"
VERDICT_ACTIVE = "already active"
VERDICT_KEEP = "keep theirs"


def load_settings() -> dict:
    if not SETTINGS.exists():
        return {}
    try:
        return json.loads(SETTINGS.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"BLOCKED: cannot read {SETTINGS}: {exc}")
        sys.exit(1)


def write_settings(data: dict) -> None:
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(data, indent=2) + "\n")


def current_command(settings: dict) -> str | None:
    line = settings.get("statusLine")
    if isinstance(line, dict):
        return line.get("command")
    return None


def is_ours(command: str | None) -> bool:
    return bool(command) and "we-statusline.js" in command


def has_node() -> bool:
    return shutil.which("node") is not None


def installed_state() -> str:
    """`missing`, `stale`, or `current` — byte comparison, no version stamps."""
    if not TARGET.exists():
        return "missing"
    try:
        return "current" if TARGET.read_bytes() == SOURCE.read_bytes() else "stale"
    except OSError:
        return "stale"


def copy_script() -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE, TARGET)
    TARGET.chmod(0o755)


def cmd_status(settings: dict) -> int:
    command = current_command(settings)
    print(f"node:      {'available' if has_node() else 'MISSING'}")
    print(f"script:    {installed_state()} ({TARGET})")
    if command is None:
        print("statusLine: none configured")
        print(f"VERDICT: {VERDICT_OFFER}")
    elif is_ours(command):
        print(f"statusLine: ours — {command}")
        stale = installed_state() == "stale"
        print(f"VERDICT: {VERDICT_ACTIVE}")
        if stale:
            print("NOTE: the installed copy differs from the shipped one — --apply refreshes it")
    else:
        print(f"statusLine: foreign — {command}")
        print(f"VERDICT: {VERDICT_KEEP}")
        print("NOTE: replacing it needs --apply --force; the old value is backed up")
    return 0


def cmd_apply(settings: dict, force: bool) -> int:
    if not has_node():
        print("BLOCKED: `node` not found on PATH — the statusline is a Node script.")
        print("Install Node.js and re-run /we:setup. Nothing was changed.")
        return 1

    command = current_command(settings)
    if command is not None and not is_ours(command) and not force:
        print(f"BLOCKED: a different statusLine is configured: {command}")
        print("Re-run with --force to replace it (the current value is backed up).")
        return 1

    copy_script()

    if command is not None and not is_ours(command):
        BACKUP.write_text(json.dumps(settings["statusLine"], indent=2) + "\n")
        print(f"Backed up the previous statusLine to {BACKUP}")

    if command == COMMAND:
        print(f"statusLine already points at {TARGET.name}; script refreshed.")
        return 0

    settings["statusLine"] = {"type": "command", "command": COMMAND}
    write_settings(settings)
    print(f"Installed: {TARGET}")
    print(f"settings.json statusLine → {COMMAND}")
    print("Takes effect in new sessions — restart Claude Code to see it.")
    return 0


def cmd_revert(settings: dict) -> int:
    command = current_command(settings)
    if not is_ours(command):
        print("Nothing to revert — the statusLine is not ours.")
        return 0

    if BACKUP.exists():
        try:
            settings["statusLine"] = json.loads(BACKUP.read_text())
            restored = current_command(settings)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"BLOCKED: backup at {BACKUP} unreadable: {exc}")
            return 1
        write_settings(settings)
        BACKUP.unlink()
        print(f"Restored the previous statusLine: {restored}")
    else:
        settings.pop("statusLine", None)
        write_settings(settings)
        print("Removed the statusLine — Claude Code falls back to its default footer.")

    if TARGET.exists():
        TARGET.unlink()
        print(f"Removed {TARGET}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--status", action="store_true", help="report, change nothing")
    mode.add_argument("--apply", action="store_true", help="install the statusline")
    mode.add_argument("--revert", action="store_true", help="restore what was there before")
    parser.add_argument(
        "--force", action="store_true", help="with --apply: replace a foreign statusLine"
    )
    args = parser.parse_args()

    if not SOURCE.exists():
        print(f"BLOCKED: shipped script missing at {SOURCE}")
        return 1

    settings = load_settings()
    if args.status:
        return cmd_status(settings)
    if args.apply:
        return cmd_apply(settings, args.force)
    return cmd_revert(settings)


if __name__ == "__main__":
    sys.exit(main())
