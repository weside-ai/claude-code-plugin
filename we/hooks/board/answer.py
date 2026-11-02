#!/usr/bin/env python3
"""Appends one answer (or news ack) of the /board pane to the answers file, as one JSON line.

Usage: answer.py <file> <id> <accept|deny|discuss|info|read> <ts> [<session>]

Opens the file for appending only (O_APPEND): two panes clicking at once each add
a whole line, and nothing already in the file is rewritten. Never touches board.json.
"""

import json
import os
import sys

ANSWERS = ("accept", "deny", "discuss", "info", "read")


def append(path, qid, answer, ts, session):
    if answer not in ANSWERS:
        raise ValueError(f"answer must be one of {', '.join(ANSWERS)}")
    line = json.dumps(
        {"id": qid, "answer": answer, "ts": ts, "session": session or None}, ensure_ascii=False
    )
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main(argv):
    if len(argv) not in (5, 6):
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    append(argv[1], argv[2], argv[3], argv[4], argv[5] if len(argv) == 6 else None)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
