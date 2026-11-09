#!/usr/bin/env python3
"""Install the companion launcher ``wclaude`` and the worker launcher ``we-worker`` into ``~/.local/bin``.

Single owner of the procedure: report the install state, copy the shipped
``scripts/wclaude`` and ``scripts/we-worker`` to a stable path, refresh each when the bytes
differ, and revert on request. Skills only call this script and relay its output. The verdict
follows ``wclaude``; ``we-worker`` gets its own state line and follows the same rules.

Why a copy instead of a link into the plugin: ``${CLAUDE_PLUGIN_ROOT}`` changes
on every plugin update, so a link breaks at the next ``claude plugins update``.

A file at a target that lacks its ``MARKER`` line is someone else's: ``--apply``
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
WORKER_SOURCE = Path(__file__).resolve().parent / "we-worker"
WORKER_MARKER = b"we-worker \xe2\x80\x94 start and steer a process worker"

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


def tools() -> list[tuple[Path, Path, bytes, Path]]:
    """(target, source, marker, backup) per launcher; read at call time so tests can move BIN_DIR."""
    return [
        (TARGET, SOURCE, MARKER, BACKUP),
        (BIN_DIR / "we-worker", WORKER_SOURCE, WORKER_MARKER, BACKUP.parent / "we-worker-backup"),
    ]


def state(tool: tuple[Path, Path, bytes, Path] | None = None) -> str:
    """`missing`, `foreign`, `stale` or `current` — byte comparison, no version stamps."""
    target, source, marker, _backup = tool or tools()[0]
    if not target.exists():
        return "missing"
    try:
        data = target.read_bytes()
    except OSError:
        return "foreign"
    if marker not in data:
        return "foreign"
    return "current" if data == source.read_bytes() else "stale"


def shadow_note(target: Path) -> None:
    """Name another file of the same name that comes first on PATH."""
    found = shutil.which(target.name)
    if found and Path(found).resolve() != target.resolve():
        print(f"NOTE: {found} comes before {target} on PATH")


def path_note() -> None:
    if not on_path():
        print(f"NOTE: {BIN_DIR} is not on PATH — add it in your shell profile:")
        print('      export PATH="$HOME/.local/bin:$PATH"')


def copy_script(target: Path | None = None, source: Path | None = None) -> None:
    target, source = target or TARGET, source or SOURCE
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o755)


def cmd_status() -> int:
    current = state()
    print(f"launcher:  {current} ({TARGET})")
    worker = tools()[1]
    print(f"worker:    {state(worker)} ({worker[0]})")
    shadow_note(worker[0])
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


def _apply_one(tool: tuple[Path, Path, bytes, Path], force: bool) -> int:
    target, source, _marker, backup = tool
    current = state(tool)
    if current == "foreign" and not force:
        print(f"BLOCKED: {target} exists and is not this plugin's {target.name}.")
        print("Re-run with --force to replace it (the current file is backed up).")
        return 1
    if current == "foreign":
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
        print(f"Backed up the previous {target.name} to {backup}")
    if current == "current":
        print(f"{target} is up to date.")
    else:
        copy_script(target, source)
        print(f"{'Refreshed' if current == 'stale' else 'Installed'}: {target}")
    return 0


def cmd_apply(force: bool) -> int:
    rc = max([_apply_one(tool, force) for tool in tools()])
    shadow_note(tools()[1][0])
    path_note()
    return rc


def _revert_one(tool: tuple[Path, Path, bytes, Path]) -> None:
    target, _source, _marker, backup = tool
    if state(tool) in ("missing", "foreign"):
        print(f"Nothing to revert — {target} is not this plugin's {target.name}.")
        return
    target.unlink()
    print(f"Removed {target}")
    if backup.exists():
        shutil.move(str(backup), str(target))
        print(f"Restored the previous {target.name} from {backup}")


def cmd_revert() -> int:
    for tool in tools():
        _revert_one(tool)
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

    for source in (SOURCE, WORKER_SOURCE):
        if not source.exists():
            print(f"BLOCKED: shipped launcher missing at {source}")
            return 1
    if args.status:
        return cmd_status()
    if args.apply:
        return cmd_apply(args.force)
    return cmd_revert()


if __name__ == "__main__":
    sys.exit(main())
