#!/usr/bin/env python3
"""Write one optimization inbox entry without losing a parallel writer's entry.

Usage: retro_write.py <dir> <body-file> [--date YYYY-MM-DD]

<body-file> is a whole entry in the inbox format (references/optimization-store.md § Inbox entry);
its frontmatter `key:` names the entry. In <dir> (the inbox or its staging):

  created <path>                          exit 0  no file carries the key: the whole entry is written to
                                                  a temp file and hard-linked to <dir>/<date>-<key>.md,
                                                  so the name never exists empty and one writer wins
  appended <n> evidence line(s) to <path> exit 0  a file `*-<key>.md` exists, or appeared between the
                                                  look and the create: the body's `## Evidence` lines
                                                  it lacks go under its `## Evidence`, under a lock
  <reason>                                exit 2  no key, no evidence line, unreadable file

A shell `cat > <file>` after an `ls` is a check-then-write race: a dozen sessions of one broadcast
retro wrote the same keys within a minute and the last writer replaced the others' entries.
"""

from __future__ import annotations

import argparse
import datetime
import fcntl
import os
import re
import sys
import tempfile
from pathlib import Path

KEY = re.compile(r"^key:\s*([a-z0-9][a-z0-9:-]*)\s*(?:#.*)?$", re.MULTILINE)
EVIDENCE = "## Evidence"


class WriteError(Exception):
    pass


def key_of(body: str) -> str:
    if not body.startswith("---"):
        raise WriteError("the body has no frontmatter (--- … ---)")
    head = body.split("\n---", 1)[0]
    found = KEY.search(head)
    if not found:
        raise WriteError("the body's frontmatter has no `key:`")
    return found.group(1)


def evidence_lines(text: str) -> list[str]:
    """The `- …` lines under `## Evidence`, up to the next level-2 heading."""
    out, inside = [], False
    for line in text.split("\n"):
        if line.startswith("## "):
            inside = line.strip() == EVIDENCE
            continue
        if inside and line.startswith("- "):
            out.append(line.rstrip())
    return out


def merged(text: str, lines: list[str]) -> str:
    """`text` with `lines` after the last line of its `## Evidence` section (made at the end when
    it has none)."""
    rows = text.rstrip("\n").split("\n")
    start = next((i for i, r in enumerate(rows) if r.strip() == EVIDENCE), None)
    if start is None:
        return "\n".join([*rows, "", EVIDENCE, "", *lines]) + "\n"
    end = next((i for i in range(start + 1, len(rows)) if rows[i].startswith("## ")), len(rows))
    last = end
    while last > start + 1 and not rows[last - 1].strip():
        last -= 1
    return "\n".join([*rows[:last], *lines, *rows[last:]]) + "\n"


def append(path: Path, lines: list[str]) -> int:
    with open(path, "r+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        text = fh.read()
        have = set(evidence_lines(text))
        new = [line for line in lines if line not in have]
        if new:
            fh.seek(0)
            fh.write(merged(text, new))
            fh.truncate()
    return len(new)


def _link_new(path: Path, text: str) -> bool:
    """Create ``path`` holding ``text`` in one step: write a temp file beside it, then
    ``os.link`` it to the name (fails when the name exists). False when another writer won."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, 0o644)
        try:
            os.link(tmp, path)
        except FileExistsError:
            return False
        return True
    finally:
        os.unlink(tmp)


def write(folder: Path, body: str, date: str) -> str:
    key = key_of(body)
    lines = evidence_lines(body)
    if not lines:
        raise WriteError("the body has no `- …` line under `## Evidence`")
    folder.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        existing = sorted(folder.glob(f"????-??-??-{key}.md"))
        if existing:
            n = append(existing[0], lines)
            return f"appended {n} evidence line(s) to {existing[0]}"
        path = folder / f"{date}-{key}.md"
        if _link_new(path, body if body.endswith("\n") else body + "\n"):
            return f"created {path}"
        # another writer created it between the look and the link: append to theirs
    raise WriteError(f"{folder}: {key} neither created nor found")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="retro_write.py", description=__doc__.split("\n")[0])
    p.add_argument("dir")
    p.add_argument("body_file")
    p.add_argument(
        "--date", default=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    )
    args = p.parse_args(argv)
    try:
        body = Path(args.body_file).read_text(encoding="utf-8")
        print(write(Path(args.dir).expanduser(), body, args.date))
    except (OSError, WriteError) as exc:
        print(f"retro_write.py: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
