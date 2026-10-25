#!/usr/bin/env python3
"""Install the companion launcher ``wclaude`` into ``~/.local/bin``.

Single owner of the procedure: report the install state, copy the shipped
``scripts/wclaude`` to a stable path, refresh it when the bytes differ, and
revert on request. Skills only call this script and relay its output.

Why a copy instead of a link into the plugin: ``${CLAUDE_PLUGIN_ROOT}`` changes
on every plugin update, so a link breaks at the next ``claude plugins update``.

A file at the target that lacks the ``MARKER`` line is someone else's: ``--apply``
refuses it without ``--force``, and ``--force`` backs it up first; ``--revert``
removes ours and restores that backup.

Modes::

    --status    report the install state and whether ~/.local/bin is on PATH
    --apply     install or refresh (refuses a foreign file without --force)
    --force     with --apply: replace a foreign file, backing it up
    --revert    remove ours, restore the backed-up file if there is one

Exit codes: 0 = done / nothing to do, 1 = blocked (reason on stdout), 2 = usage.
Python stdlib only.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

BIN_DIR = Path.home() / ".local" / "bin"
TARGET = BIN_DIR / "wclaude"
BACKUP = Path.home() / ".claude" / "we-wclaude-backup"
SOURCE = Path(__file__).resolve().parent / "wclaude"

# Present in the shipped script; a target without it is foreign.
MARKER = b"wclaude \xe2\x80\x94 start Claude Code as a weside Companion"

# The verdicts /we:setup § 5 Companion launcher branches on; scripts/validate-consistency.py
# checks that the skill names each one.
VERDICT_OFFER = "offer the launcher"
VERDICT_ACTIVE = "launcher installed"
VERDICT_KEEP = "foreign wclaude"


def on_path() -> bool:
    entries = os.environ.get("PATH", "").split(os.pathsep)
    target = BIN_DIR.resolve()
    for entry in entries:
        if not entry:
            continue
        try:
            if Path(os.path.expanduser(entry)).resolve() == target:
                return True
        except OSError:
            continue
    return False


def state() -> str:
    """`missing`, `foreign`, `stale` or `current` — byte comparison, no version stamps."""
    if not TARGET.exists():
        return "missing"
    try:
        data = TARGET.read_bytes()
    except OSError:
        return "foreign"
    if MARKER not in data:
        return "foreign"
    return "current" if data == SOURCE.read_bytes() else "stale"


def path_note() -> None:
    if not on_path():
        print(f"NOTE: {BIN_DIR} is not on PATH — add it in your shell profile:")
        print('      export PATH="$HOME/.local/bin:$PATH"')


def copy_script() -> None:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE, TARGET)
    TARGET.chmod(0o755)


def cmd_status() -> int:
    current = state()
    print(f"launcher:  {current} ({TARGET})")
    print(f"PATH:      {BIN_DIR} {'on PATH' if on_path() else 'NOT on PATH'}")
    if current == "missing":
        print(f"VERDICT: {VERDICT_OFFER}")
    elif current == "foreign":
        print(f"VERDICT: {VERDICT_KEEP}")
        print("NOTE: replacing it needs --apply --force; the old file is backed up")
    else:
        print(f"VERDICT: {VERDICT_ACTIVE}")
        if current == "stale":
            print("NOTE: the installed copy differs from the shipped one — --apply refreshes it")
    return 0


def cmd_apply(force: bool) -> int:
    current = state()
    if current == "foreign" and not force:
        print(f"BLOCKED: {TARGET} exists and is not this plugin's launcher.")
        print("Re-run with --force to replace it (the current file is backed up).")
        return 1
    if current == "foreign":
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(TARGET, BACKUP)
        print(f"Backed up the previous {TARGET.name} to {BACKUP}")
    if current == "current":
        print(f"{TARGET} is up to date.")
    else:
        copy_script()
        print(f"{'Refreshed' if current == 'stale' else 'Installed'}: {TARGET}")
    path_note()
    return 0


def cmd_revert() -> int:
    current = state()
    if current in ("missing", "foreign"):
        print(f"Nothing to revert — {TARGET} is not this plugin's launcher.")
        return 0
    TARGET.unlink()
    print(f"Removed {TARGET}")
    if BACKUP.exists():
        shutil.move(str(BACKUP), str(TARGET))
        print(f"Restored the previous {TARGET.name} from {BACKUP}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--status", action="store_true", help="report, change nothing")
    mode.add_argument("--apply", action="store_true", help="install or refresh the launcher")
    mode.add_argument("--revert", action="store_true", help="remove it, restore a backup")
    parser.add_argument(
        "--force", action="store_true", help="with --apply: replace a foreign file"
    )
    args = parser.parse_args()

    if not SOURCE.exists():
        print(f"BLOCKED: shipped launcher missing at {SOURCE}")
        return 1
    if args.status:
        return cmd_status()
    if args.apply:
        return cmd_apply(args.force)
    return cmd_revert()


if __name__ == "__main__":
    sys.exit(main())
