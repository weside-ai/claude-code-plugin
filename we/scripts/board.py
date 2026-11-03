#!/usr/bin/env python3
"""The board's verbs for a session (docs/board.md); this release has one, `answer`.

Usage:
  board.py [--board FILE] answer <id> <accept|deny|discuss|info|update> --session NAME --via chat
           [--quote "<the owner's words>"]

answer   writes back an answer the owner gave in a session's chat: one line in
         board-answers.jsonl beside the board file, which the deliverer in the orchestrator's
         session then carries like a press of the /board pane. It refuses an id that is in neither
         `owner_queue` nor `news` of the board file, an id an Accept or Deny already closed, and a
         kind outside the five; a refused write writes nothing. It opens board.json read-only and
         prints the written line.

FILE defaults to ~/.claude/we-state/board.json (the pane's option `boardFile` names another).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BOARD = "~/.claude/we-state/board.json"
KINDS = ("accept", "deny", "discuss", "info", "update")
CLOSING = ("accept", "deny")


def _answer_writer():
    """answer.py's `append`, by path: the one writer of the answers file's line format."""
    path = Path(__file__).resolve().parent.parent / "hooks" / "board" / "answer.py"
    spec = importlib.util.spec_from_file_location("we_board_answer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.append


class StateDir:
    """The board file and the JSONL files beside it: every path and every read or write of them."""

    def __init__(self, board_file):
        self.board_path = Path(board_file).expanduser()
        self.answers_path = self.board_path.with_name("board-answers.jsonl")

    def board(self):
        """The board file as a dict, read only; a missing file is an empty board."""
        try:
            with open(self.board_path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return {}
        if not isinstance(data, dict):
            raise ValueError(f"{self.board_path} is no JSON object")
        return data

    def ids(self):
        board = self.board()
        out = set()
        for field in ("owner_queue", "news"):
            for item in board.get(field) or []:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    out.add(item["id"])
        return out

    def answers(self):
        """Every line of the answers file that parses as a JSON object; torn or foreign lines are skipped."""
        try:
            text = self.answers_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        out = []
        for line in text.splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict):
                out.append(item)
        return out

    def is_closed(self, qid):
        return any(a.get("id") == qid and a.get("answer") in CLOSING for a in self.answers())

    def append_answer(self, qid, kind, session, via=None, quote=None, ts=None):
        stamp = ts or datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )
        return _answer_writer()(
            str(self.answers_path), qid, kind, stamp, session, via=via, quote=quote
        )


def cmd_answer(state, args):
    if args.id not in state.ids():
        print(
            f"board.py answer: {args.id} is in neither owner_queue nor news of {state.board_path}",
            file=sys.stderr,
        )
        return 1
    if state.is_closed(args.id):
        print(
            f"board.py answer: {args.id} is closed by an Accept or Deny; a new question takes a new id",
            file=sys.stderr,
        )
        return 1
    line = state.append_answer(args.id, args.kind, args.session, via=args.via, quote=args.quote)
    print(json.dumps(line, ensure_ascii=False))
    return 0


def parser():
    p = argparse.ArgumentParser(prog="board.py", description="The board's verbs for a session.")
    p.add_argument(
        "--board", default=DEFAULT_BOARD, help=f"the board file (default {DEFAULT_BOARD})"
    )
    verbs = p.add_subparsers(dest="verb", required=True)
    a = verbs.add_parser("answer", help="write back an answer the owner gave in a chat")
    a.add_argument("id")
    a.add_argument("kind", choices=KINDS)
    a.add_argument("--session", required=True, help="the session whose chat the answer came in")
    a.add_argument("--via", required=True, choices=("chat",))
    a.add_argument("--quote", help="the owner's own words")
    a.set_defaults(run=cmd_answer)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    return args.run(StateDir(args.board), args)


if __name__ == "__main__":
    sys.exit(main())
