#!/usr/bin/env python3
"""Appends one answer (a news ack, or Refresh's `rebuild` request) of the /board pane to the answers file, as one JSON line.

Usage: answer.py <file> <id> <accept|deny|followup|update|withdraw|read|rebuild> <ts> [<session>]

Opens the file for appending only (O_APPEND) and writes the line in one write: two panes clicking
at once each add a whole line, and nothing already in the file is rewritten. Never touches
board.json. A pane's line carries no `via`; `append` takes one only from `board.py answer` (the
one writer of a chat answer, `chat`) and `board.py signals` (a reply read from a ticket,
`ticket`), and the command line here refuses it.
"""

import json
import os
import sys

ANSWERS = ("accept", "deny", "followup", "update", "withdraw", "read", "rebuild")


def append(path, qid, answer, ts, session, via=None, quote=None, ask=None, recommendation=None):
    if answer not in ANSWERS:
        raise ValueError(f"answer must be one of {', '.join(ANSWERS)}")
    record = {"id": qid, "answer": answer, "ts": ts, "session": session or None}
    if via:
        record["via"] = via
    if quote:
        record["quote"] = quote
    if ask:
        record["ask"] = ask
    if recommendation:
        record["recommendation"] = recommendation
    line = json.dumps(record, ensure_ascii=False) + "\n"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
    return record


def main(argv):
    if any(arg.startswith("--") for arg in argv[1:]):
        print(
            "answer.py: a pane's line has no options; a chat answer goes through board.py answer",
            file=sys.stderr,
        )
        return 2
    if len(argv) not in (5, 6):
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    append(argv[1], argv[2], argv[3], argv[4], argv[5] if len(argv) == 6 else None)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
