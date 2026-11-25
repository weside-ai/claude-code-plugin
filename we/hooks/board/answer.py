#!/usr/bin/env python3
"""Appends one answer (a news ack, or Refresh's `rebuild` request) of the /board pane to the answers file, as one JSON line.

Usage: answer.py <file> <id> <accept|deny|followup|update|withdraw|read|rebuild> <ts> [<session>]

Opens the file for appending only (O_APPEND) and writes the line in one write: two panes clicking
at once each add a whole line, and nothing already in the file is rewritten. Never writes
board.json. A pane's line carries no `via`; `append` takes one only from `board.py answer` (the
one writer of a chat answer, `chat`) and `board.py signals` (a reply read from a ticket,
`ticket`), and the command line here refuses it.

An Accept on a one-way `merge-go` question that carries a skipped Codex finding (`ask
--codex-finding`) also posts one PR comment through `gh` (`post_go`, both answer paths call it):
first line exactly `<!-- board-go Q<n> head=<the question's 40-hex head> -->`, then the human's
answer quoted, the finding and the asking session's reason. A CI job counts that marker on the
PR's current head as the skip. Each post leaves one `go-comment` line in <stem>-questions.jsonl;
a question with a posted comment is not posted again. A failed post exits 3 after the answer
line is written, its reason on stderr.

A press on a question close-merged's `pr_merged`/`pr_closed` closed (a hand merge the card did not
show yet) writes nothing and exits 4 with the note `Qn is already settled: PR merged` on stderr,
which the pane shows. A press after an earlier Accept, Deny or Withdraw is written as before:
board.py reads it as a duplicate, and a repeated Accept retries a go comment that failed to post.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

GH_TIMEOUT_S = 30
HEAD = re.compile(r"[0-9a-f]{40}")

PANE = ("accept", "deny", "followup", "update", "withdraw", "read", "rebuild")
# board.py close-merged's answers on a merge-go question whose PR merged or closed; never a press.
PR_DONE = {"pr_merged": "PR merged", "pr_closed": "PR closed"}
ANSWERS = (*PANE, *PR_DONE)
# The presses that answer a question; Read and Refresh do not.
QUESTION_PRESSES = ("accept", "deny", "followup", "update", "withdraw")


def append(
    path, qid, answer, ts, session, via=None, quote=None, ask=None, recommendation=None, pr=None
):
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
    if pr:
        record["pr"] = pr
    line = json.dumps(record, ensure_ascii=False) + "\n"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
    return record


def _stem_path(answers_path, suffix):
    """The file beside the answers file: <stem>-answers.jsonl → <stem><suffix>."""
    folder, name = os.path.split(answers_path)
    stem = name[: -len("-answers.jsonl")] if name.endswith("-answers.jsonl") else None
    return os.path.join(folder, stem + suffix) if stem else None


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _log_lines(path):
    try:
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
    except (OSError, ValueError):
        return []
    return [r for r in rows if isinstance(r, dict)]


def closed_note(answers_path, qid, answer):
    """The pane's note for a press on a question close-merged closed (a hand merge the card did not
    show yet), else None. An earlier Accept, Deny or Withdraw gets None: that press is written."""
    if answer not in QUESTION_PRESSES:
        return None
    closer = next(
        (r for r in _log_lines(answers_path) if r.get("id") == qid and r.get("answer") in PR_DONE),
        None,
    )
    if closer is None:
        return None
    return f"{qid} is already settled: {PR_DONE[closer['answer']]}"


def go_body(item, record):
    """The comment that carries the human's yes on a one-way PR as the skip of its Codex finding."""
    qid = item["id"]
    said = (record.get("quote") or "").strip() or "Go (Accept on the board)"
    where = (
        f"in the chat of {record.get('session')}"
        if record.get("via") == "chat"
        else f"on the board pane in {record.get('session') or 'a session'}"
    )
    quoted = "\n".join(f"> {line}" for line in said.splitlines())
    return (
        f"<!-- board-go {qid} head={item['head']} -->\n"
        f"{quoted}\n"
        f"— the human's answer to {qid}, {record.get('ts')}, {where}\n\n"
        f"Codex finding skipped on this yes: {item['codex_finding']}\n"
        f"Reason of the asking session: {item['codex_reason']}\n"
    )


def post_go(answers_path, record, run=subprocess.run, now=None):
    """None when the answer carries no go to post; else (True, comment url or note) or
    (False, the reason the post failed). One `go-comment` line in <stem>-questions.jsonl."""
    if record.get("answer") != "accept":
        return None
    board_path = _stem_path(answers_path, ".json")
    log_path = _stem_path(answers_path, "-questions.jsonl")
    board = _read_json(board_path) if board_path else None
    # The queue item, else its `posted` line: a question pruned after its answer keeps its fields there.
    item = next(
        (
            q
            for q in ((board or {}).get("owner_queue") or [])
            if isinstance(q, dict) and q.get("id") == record.get("id")
        ),
        None,
    ) or next(
        (
            r
            for r in _log_lines(log_path)
            if r.get("id") == record.get("id") and r.get("outcome") == "posted"
        ),
        None,
    )
    if not item or item.get("cause") != "merge-go" or not item.get("codex_finding"):
        return None
    if any(
        r.get("id") == item["id"] and r.get("outcome") == "go-comment" and r.get("ok")
        for r in _log_lines(log_path)
    ):
        return None
    pr, head = str(item.get("pr_url") or ""), str(item.get("head") or "")
    if not pr or not HEAD.fullmatch(head):
        ok, text = False, f"{item['id']} has no PR or no 40-hex head sha to bind the go to"
    else:
        try:
            done = run(
                ["gh", "pr", "comment", pr, "--body-file", "-"],
                input=go_body(item, record),
                capture_output=True,
                text=True,
                timeout=GH_TIMEOUT_S,
                check=False,
            )
            out = (done.stdout or "").strip()
            why = (done.stderr or "").strip().splitlines()
            ok = done.returncode == 0
            text = out or "posted" if ok else (why[-1] if why else f"gh exit {done.returncode}")
        except FileNotFoundError:
            ok, text = False, "gh not found"
        except subprocess.TimeoutExpired:
            ok, text = False, f"gh ran past {GH_TIMEOUT_S} s"
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = {
        "id": item["id"],
        "ts": stamp,
        "outcome": "go-comment",
        "ok": ok,
        "pr": pr,
        "head": head,
    }
    line["url" if ok else "error"] = text
    if log_path:
        fd = os.open(log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    return ok, text


def go_failure(record, result):
    """The stderr line of a failed go comment, or None."""
    if result is None or result[0]:
        return None
    return (
        f"{record['id']}: the answer is saved, but the go comment on the PR failed: {result[1]}; "
        "the CI job does not see this yes until it is posted; `board.py answer "
        f"{record['id']} accept --session <name> --via chat` posts it again"
    )


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
    if argv[3] not in PANE:
        print(f"answer.py: answer must be one of {', '.join(PANE)}", file=sys.stderr)
        return 2
    note = closed_note(argv[1], argv[2], argv[3])
    if note:
        print(note, file=sys.stderr)
        return 4
    record = append(argv[1], argv[2], argv[3], argv[4], argv[5] if len(argv) == 6 else None)
    failed = go_failure(record, post_go(argv[1], record))
    if failed:
        print(f"answer.py: {failed}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
