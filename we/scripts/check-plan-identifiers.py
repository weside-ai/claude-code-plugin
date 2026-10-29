#!/usr/bin/env python3
"""Every identifier a plan names as existing must exist on the base branch.

    check-plan-identifiers.py <plan.md> [--ref origin/<default>]

Reads the plan's inline code spans (fenced blocks skipped) that look like code: a path with a
`/` and an extension or a trailing `/`, or a name with `_`, `.`, `::` or camelCase. A span
followed by `(new)` (the plan builds it) or `(other repo)` is skipped. A path must exist in the tree of `--ref`
(default `origin/HEAD`, else `origin/main`), also as the tail of a longer path; a name must occur
in a file there (`git grep -F`). Misses print as `missing: <token> (line <n>)`, exit 1: strike
the claim or mark it `(new)`. Exit 2 on a git error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SPAN = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
NEW = re.compile(r"^\s*\((new|other repo)\)")
PLACEHOLDER = re.compile(r"[\s<>*?{}\[\]$|=@'\"\\…]|://|^-|^~|^/")
PATH = re.compile(r"^[\w.-]+(/[\w.-]+)*(/|\.[A-Za-z0-9]{1,5})$")
NAME = re.compile(r"^[A-Za-z_][\w]*(\.[A-Za-z_]\w*)*$")


def _git(args: list[str]) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or f"git {' '.join(args)} failed")
    return out.stdout


def _code_like(token: str) -> bool:
    return "_" in token or "." in token or bool(re.search(r"[a-z][A-Z]", token))


def claims(text: str) -> list[tuple[str, int]]:
    """(token, line) for every span the plan treats as existing code."""
    found, fenced = [], False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        for match in SPAN.finditer(line):
            if NEW.match(line[match.end() :]):
                continue
            token = re.sub(r"(::.*|:\d+(-\d+)?|\(\)|\[\w*\])$", "", match.group(1).strip()).rstrip(
                ".,;:"
            )
            if not token or PLACEHOLDER.search(token):
                continue
            if ("/" in token and PATH.match(token)) or (
                "/" not in token and NAME.match(token) and _code_like(token) and len(token) > 3
            ):
                found.append((token, number))
    return found


def _default_ref() -> str:
    try:
        return _git(["rev-parse", "--abbrev-ref", "origin/HEAD"]).strip()
    except RuntimeError:
        return "origin/main"


def missing(found: list[tuple[str, int]], ref: str) -> list[tuple[str, int]]:
    paths: set[str] = set()
    for f in _git(["ls-tree", "-r", "--name-only", ref]).splitlines():
        parts = f.split("/")
        for end in range(1, len(parts) + 1):
            for start in range(end):
                paths.add("/".join(parts[start:end]))
    names = sorted({t for t, _ in found if "/" not in t})
    seen: set[str] = set()
    if names:
        out = subprocess.run(
            ["git", "grep", "-h", "-o", "-F", *[a for n in names for a in ("-e", n)], ref, "--"],
            capture_output=True,
            text=True,
            check=False,
        )
        seen = set(out.stdout.split())
    result = []
    for token, line in found:
        if "/" in token:
            ok = token.rstrip("/").removeprefix("./") in paths
        else:
            ok = (
                token in seen
                or subprocess.run(
                    ["git", "grep", "-q", "-F", "-e", token, ref, "--"], check=False
                ).returncode
                == 0
            )
        if not ok:
            result.append((token, line))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan")
    parser.add_argument("--ref")
    args = parser.parse_args()
    found = claims(Path(args.plan).read_text(encoding="utf-8"))
    try:
        misses = missing(found, args.ref or _default_ref())
    except RuntimeError as exc:
        print(f"check-plan-identifiers: {exc}", file=sys.stderr)
        return 2
    for token, line in misses:
        print(f"missing: {token} (line {line})")
    print(f"{len(found)} claims checked, {len(misses)} missing")
    return 1 if misses else 0


if __name__ == "__main__":
    sys.exit(main())
