#!/usr/bin/env python3
"""The plugin version rises by itself after every merge to main; no PR sets it.

`.github/workflows/version-bump.yml` runs `prepare` on every push to main: it finds the last commit
that changed the version of `we/.claude-plugin/plugin.json`, reads the Conventional Commits since
(merges skipped; a `!` after the type or a `BREAKING CHANGE` footer → major, `feat` → minor,
anything else → patch), writes the next version into that one line and prints it; with nothing
since, it prints nothing. The merge of the bump PR itself therefore bumps nothing: no loop. The
workflow pushes the line onto the rolling branch `chore/version-bump` and opens its PR with the
token of the `weside-agent` GitHub App, so the PR runs every workflow and gets the normal review.

`check` is the required `Version Bump Check`: a PR that leaves the version alone passes; a PR that
moves it passes only as the bump PR (`bump_refusal`), all three at once:
- its author is the App's bot (the PR author from the event, which no commit can set),
- its diff against main is the version line of plugin.json and nothing else,
- the new version is one step above main's (patch + 1, minor + 1 or major + 1, the lower parts 0).
The workflow loads this file from the default branch, so a PR cannot rewrite the test that judges it.

Usage:
    version_bump.py prepare                          write the next version, print it
    version_bump.py check BASE HEAD --author LOGIN [--bot LOGIN]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

PLUGIN_JSON = "we/.claude-plugin/plugin.json"
BOT = "weside-agent[bot]"
_VERSION_LINE = re.compile(r'^\s*"version":\s*"(\d+)\.(\d+)\.(\d+)",?\s*$')
_BREAKING = re.compile(r"^[a-z]+(\([^)]*\))?!:|^BREAKING[ -]CHANGE:", re.MULTILINE)
_FEAT = re.compile(r"^feat(\([^)]*\))?:", re.MULTILINE)
Version = tuple[int, int, int]


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


def bumped(version: Version, step: str) -> Version:
    major, minor, patch = version
    if step == "major":
        return (major + 1, 0, 0)
    if step == "minor":
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def parse(text: str | None) -> Version | None:
    try:
        parts = tuple(int(p) for p in str(text).split("."))
    except ValueError:
        return None
    return parts if len(parts) == 3 else None  # type: ignore[return-value]


def prepare(root: Path) -> str | None:
    """Write the next version into plugin.json's version line; None when nothing landed since."""
    last = git("log", "-1", "--format=%H", "-G", r'"version":', "--", PLUGIN_JSON).strip()
    rng = f"{last}..HEAD" if last else "HEAD"
    raw = git("log", "--no-merges", "--format=%B%x00", rng).split("\0")
    step = level([m for m in raw if m.strip()])
    if step is None:
        return None
    path = root / PLUGIN_JSON
    text = path.read_text()
    current = parse(json.loads(text)["version"])
    if current is None:
        raise SystemExit(f"{PLUGIN_JSON}: the version is no x.y.z")
    new = ".".join(str(p) for p in bumped(current, step))
    lines = text.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if _VERSION_LINE.match(line)]
    if len(hits) != 1:
        raise SystemExit(f"{PLUGIN_JSON}: expected one version line, found {len(hits)}")
    lines[hits[0]] = re.sub(r'"\d+\.\d+\.\d+"', f'"{new}"', lines[hits[0]], count=1)
    path.write_text("".join(lines))
    return new


def _version_at(rev: str) -> str | None:
    try:
        return json.loads(git("show", f"{rev}:{PLUGIN_JSON}")).get("version")
    except (subprocess.CalledProcessError, ValueError, AttributeError):
        return None


def bump_refusal(base: str, head: str, author: str, bot: str = BOT) -> str | None:
    """None when base...head is the bump PR, else why it is none."""
    if author != bot:
        return f"the PR's author is {author!r}, not {bot}"
    files = git("diff", "--name-only", "--no-renames", f"{base}...{head}").split()
    if files != [PLUGIN_JSON]:
        return f"the diff touches {', '.join(files) or 'nothing'}, not only {PLUGIN_JSON}"
    out = git("diff", "--unified=0", f"{base}...{head}", "--", PLUGIN_JSON)
    changed = [
        line[1:]
        for line in out.splitlines()
        if line[:1] in "+-" and line[:3] not in ("+++", "---")
    ]
    if len(changed) != 2 or not all(_VERSION_LINE.match(line) for line in changed):
        return f"the diff of {PLUGIN_JSON} is more than its version line"
    old = parse(_version_at(git("merge-base", base, head).strip()))
    new = parse(_version_at(head))
    steps = {bumped(old, s) for s in ("major", "minor", "patch")} if old else set()
    if new not in steps:
        return f"{_version_at(head)} is not one step above {_version_at(base)}"
    return None


def check(base: str, head: str, author: str, bot: str = BOT) -> tuple[int, str]:
    fork = git("merge-base", base, head).strip()
    if _version_at(fork) == _version_at(head):
        return 0, "Version untouched: the bump follows the merge."
    why = bump_refusal(base, head, author, bot)
    if why is None:
        return 0, f"Bump PR: {_version_at(fork)} -> {_version_at(head)}, the version line alone."
    return 1, (
        f"ERROR: this PR changes the version in {PLUGIN_JSON}.\n"
        "The version rises by itself after the merge (version-bump.yml); leave the line alone.\n"
        f"(no bump PR: {why})"
    )


def main(argv: list[str]) -> int:
    if argv == ["prepare"]:
        new = prepare(Path(git("rev-parse", "--show-toplevel").strip()))
        if new:
            print(new)
        return 0
    parser = argparse.ArgumentParser(prog="version_bump.py")
    sub = parser.add_subparsers(dest="verb", required=True)
    c = sub.add_parser("check")
    c.add_argument("base")
    c.add_argument("head")
    c.add_argument("--author", required=True)
    c.add_argument("--bot", default=BOT)
    args = parser.parse_args(argv)
    code, text = check(args.base, args.head, args.author, args.bot)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
