#!/usr/bin/env python3
"""A plugin PR that changes what a second repo runs says whether it was checked there.

The plugin runs in more than one team's repo. A PR whose diff touches the process text (L0, role
cards), a skill or the crew schema reader must carry, outside fenced code, one line

    Compat repo checked: yes|no, <why>

The PR template asks for it; this check is the gate (workflow `compat-line.yml`, which also runs
when the PR body is edited). Other diffs pass.

Usage: check_compat_line.py [--event <event.json>] [--base <ref>]
Reads the PR body from the GitHub event (`GITHUB_EVENT_PATH` by default) and the changed files
from `git diff --name-only <base>...HEAD` (default: `origin/<base branch of the event>`).
Exit 0 with `ok: …`, exit 1 naming what is missing. Pinned by `scripts/test_check_compat_line.py`.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys

TRIGGERS = ("we/process/L0.md", "we/skills/*", "we/roles/*", "we/scripts/crew.py")
LINE = re.compile(r"^\s*Compat repo checked:\s*(yes|no)\b\s*,?\s*(\S.*)?$", re.IGNORECASE)
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def triggering(files: list[str]) -> list[str]:
    return [f for f in files if any(fnmatch.fnmatch(f, pat) for pat in TRIGGERS)]


def compat_line(body: str) -> re.Match | None:
    fenced = False
    for line in (body or "").splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            m = LINE.match(line)
            if m:
                return m
    return None


def check(body: str, files: list[str]) -> str | None:
    """Why the PR fails the check, or None."""
    touched = triggering(files)
    if not touched:
        return None
    m = compat_line(body)
    if m is None:
        return (
            f"this PR changes {', '.join(touched[:3])}{' …' if len(touched) > 3 else ''}; "
            "add the line `Compat repo checked: yes|no, <why>` to the PR body"
        )
    reason = (m.group(2) or "").strip()
    if not reason or reason.startswith("|") or "<why>" in reason:
        return "`Compat repo checked:` needs one of yes/no and its reason (the template's placeholder is not one)"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--event", default=os.environ.get("GITHUB_EVENT_PATH"))
    parser.add_argument("--base")
    args = parser.parse_args(argv)
    if not args.event:
        print("check_compat_line: no event file (GITHUB_EVENT_PATH)", file=sys.stderr)
        return 1
    with open(args.event, encoding="utf-8") as fh:
        pr = json.load(fh).get("pull_request") or {}
    base = args.base or f"origin/{(pr.get('base') or {}).get('ref') or 'main'}"
    diff = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if diff.returncode != 0:
        print(f"check_compat_line: git diff against {base} failed: {diff.stderr.strip()}")
        return 1
    why = check(pr.get("body") or "", diff.stdout.split())
    if why:
        print(f"compat line missing: {why}")
        return 1
    print("ok: compat line present or not needed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
