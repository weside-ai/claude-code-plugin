#!/usr/bin/env python3
"""The plugin version rises by itself after every merge to main; no PR sets it.

`.github/workflows/version-bump.yml` runs `prepare` on every push to main: it finds the last commit
that changed the version line of `we/.claude-plugin/plugin.json`, reads the Conventional Commit
subjects since (a `!` after the type or a `BREAKING CHANGE` footer → major, `feat` → minor, anything
else → patch), writes the next version into that one line and prints it. The workflow commits it as
`github-actions[bot]` onto the rolling branch `chore/version-bump` and arms auto-merge on its PR.

A bump PR is recognised by what it is, never by its branch name (`is_bump`): its diff against
main is exactly the version line of plugin.json, and its head commit's author is
`github-actions[bot]`. An author name can be forged, so the diff is the guard: a forged commit can
only move the version. `check` (the required `Version Bump Check`) refuses every other PR that
changes the version; the Claude review skips a bump PR by the same test. Both workflows load this
file from the default branch, so a PR cannot rewrite the test that judges it.

Usage:
    version_bump.py prepare                 write the next version, print it (nothing to bump: prints nothing)
    version_bump.py is-bump BASE HEAD       exit 0 for a bump PR, 1 otherwise, with the reason
    version_bump.py check BASE HEAD         exit 0 unless HEAD changes the version and is no bump PR
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PLUGIN_JSON = "we/.claude-plugin/plugin.json"
BOT = "github-actions[bot]"
_VERSION_LINE = re.compile(r'^\s*"version":\s*"(\d+)\.(\d+)\.(\d+)",?\s*$')
_BREAKING = re.compile(r"^[a-z]+(\([^)]*\))?!:|^BREAKING[ -]CHANGE:", re.MULTILINE)
_FEAT = re.compile(r"^feat(\([^)]*\))?:", re.MULTILINE)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def level(messages: list[str]) -> str | None:
    """The bump the commit messages ask for: major, minor, patch, or None without a commit."""
    if not messages:
        return None
    text = "\n".join(messages)
    if _BREAKING.search(text):
        return "major"
    if _FEAT.search(text):
        return "minor"
    return "patch"


def bumped(version: tuple[int, int, int], step: str) -> tuple[int, int, int]:
    major, minor, patch = version
    if step == "major":
        return (major + 1, 0, 0)
    if step == "minor":
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def _version_of(text: str) -> tuple[int, int, int]:
    return tuple(int(p) for p in json.loads(text)["version"].split("."))  # type: ignore[return-value]


def prepare(root: Path) -> str | None:
    """Write the next version into plugin.json's version line; None when nothing landed since."""
    last = git("log", "-1", "--format=%H", "-G", r'"version":', "--", PLUGIN_JSON).strip()
    rng = f"{last}..HEAD" if last else "HEAD"
    messages = [
        m for m in git("log", "--no-merges", "--format=%B%x00", rng).split("\0") if m.strip()
    ]
    step = level(messages)
    if step is None:
        return None
    path = root / PLUGIN_JSON
    text = path.read_text()
    new = ".".join(str(p) for p in bumped(_version_of(text), step))
    lines = text.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if _VERSION_LINE.match(line)]
    if len(hits) != 1:
        raise SystemExit(f"{PLUGIN_JSON}: expected one version line, found {len(hits)}")
    i = hits[0]
    lines[i] = re.sub(r'"\d+\.\d+\.\d+"', f'"{new}"', lines[i], count=1)
    path.write_text("".join(lines))
    return new


def _diff_lines(base: str, head: str) -> list[str]:
    out = git("diff", "--unified=0", "--no-renames", f"{base}...{head}")
    return [
        line
        for line in out.splitlines()
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]


def _files(base: str, head: str) -> list[str]:
    return git("diff", "--name-only", "--no-renames", f"{base}...{head}").split()


def is_bump(base: str, head: str) -> str | None:
    """None for a bump PR, else why it is none."""
    files = _files(base, head)
    if files != [PLUGIN_JSON]:
        return f"the diff touches {', '.join(files) or 'nothing'}, not only {PLUGIN_JSON}"
    changed = _diff_lines(base, head)
    if len(changed) != 2 or not all(_VERSION_LINE.match(line[1:]) for line in changed):
        return f"the diff of {PLUGIN_JSON} is more than its version line"
    author = git("log", "-1", "--format=%an", head).strip()
    if author != BOT:
        return f"the head commit's author is {author!r}, not {BOT}"
    return None


def _version_at(rev: str) -> str | None:
    try:
        return json.loads(git("show", f"{rev}:{PLUGIN_JSON}")).get("version")
    except (subprocess.CalledProcessError, ValueError):
        return None


def _version_changed(base: str, head: str) -> bool:
    """Whether the version value moves; a comma or another key next to it is no change."""
    if PLUGIN_JSON not in _files(base, head):
        return False
    fork = git("merge-base", base, head).strip()
    return _version_at(fork) != _version_at(head)


def main(argv: list[str]) -> int:
    if argv[:1] == ["prepare"] and len(argv) == 1:
        new = prepare(Path(git("rev-parse", "--show-toplevel").strip()))
        if new:
            print(new)
        return 0
    if len(argv) == 3 and argv[0] in ("is-bump", "check"):
        base, head = argv[1], argv[2]
        why = is_bump(base, head)
        if argv[0] == "is-bump":
            print("bump PR" if why is None else f"no bump PR: {why}")
            return 0 if why is None else 1
        if why is None:
            print("Bump PR: the version line moves and nothing else.")
            return 0
        if _version_changed(base, head):
            print(f"ERROR: this PR changes the version in {PLUGIN_JSON}.")
            print(
                "The version rises by itself after the merge (version-bump.yml); leave the line alone."
            )
            print(f"({why})")
            return 1
        print("Version untouched: the bump follows the merge.")
        return 0
    print(__doc__.split("Usage:")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
