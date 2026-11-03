#!/usr/bin/env python3
"""Appends rows to the /board delivery ledger (board-deliveries.jsonl), one JSON line each.

Usage: deliveries.py append <file> <row-json> [<row-json> ...]

A row is either the deliverer's start, {"epoch": "<ts>"}, or one recipient's outcome of one
answer line: {"id", "answer_ts", "to", "role", "click_ts", "ts", "delivered"[, "reason"]}, with
role coordinator, asker or route. Every row is checked before any is written; then all go out in
one write on a file opened O_APPEND, so two writers each add whole lines and nothing already in
the file is rewritten. Never touches board.json or the answers file.
"""

import json
import os
import sys

ROLES = ("coordinator", "asker", "route")
TEXT_FIELDS = ("id", "answer_ts", "to", "click_ts", "ts")


def check(row):
    if not isinstance(row, dict):
        raise ValueError("a row is a JSON object")
    if set(row) == {"epoch"}:
        if not isinstance(row["epoch"], str) or not row["epoch"]:
            raise ValueError("epoch is a timestamp")
        return row
    allowed = set(TEXT_FIELDS) | {"role", "delivered", "reason"}
    extra = set(row) - allowed
    if extra:
        raise ValueError(f"unknown field(s): {', '.join(sorted(extra))}")
    for field in TEXT_FIELDS:
        if not isinstance(row.get(field), str):
            raise ValueError(f"{field} must be a string")
    if row.get("role") not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    if not isinstance(row.get("delivered"), bool):
        raise ValueError("delivered must be true or false")
    if "reason" in row and not isinstance(row["reason"], str):
        raise ValueError("reason must be a string")
    return row


def append(path, rows):
    data = "".join(json.dumps(check(r), ensure_ascii=False) + "\n" for r in rows)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, data.encode("utf-8"))
    finally:
        os.close(fd)


def main(argv):
    if len(argv) < 4 or argv[1] != "append":
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    try:
        append(argv[2], [json.loads(r) for r in argv[3:]])
    except ValueError as err:
        print(f"deliveries.py: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
