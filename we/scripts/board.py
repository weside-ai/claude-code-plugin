#!/usr/bin/env python3
"""The board's verbs for a session (docs/board.md § The file, § Answers, § Questions and decisions, § Escalations).

Usage:
  board.py [--board FILE] answer <id> <accept|deny|followup|update|withdraw> --session NAME --via chat
           [--quote "<the owner's words>" | --text-file <path or ->]
  board.py [--board FILE] path [--crew-only]
  board.py [--board FILE] set [--for NAME | --session NAME] <field>=<value> …   fields: waiting_on, state, now, topic, keys, epic
  board.py [--board FILE] ask [--session NAME] --key KEY --key-title T (--ask Q | --text-file <path or ->)
           --recommendation R
           --cause <merge-go|plan|prod|cut-fence|access-click|window-go|info> [--urgent]
           [--pr REF [--one-way CLASS]] [--to HUMAN]
  board.py [--board FILE] close-merged
  board.py [--board FILE] prune
  board.py [--board FILE] log correction <session> <kind>
  board.py [--board FILE] blocked <name> --kind <permission|chat> [--waiting-on ROLE]
           [--starter NAME] [--key KEY] [--command TEXT]
  board.py [--board FILE] blocked <name> --clear
  board.py [--board FILE] decision <area> <cut|fence|process> --key KEY --text T
  board.py [--board FILE] bundle
  board.py [--board FILE] news add --title T [--body B] [--kind <info|gate|todo>]
  board.py [--board FILE] news worker --id ID --title T [--body B]
  board.py [--board FILE] escalation open --key KEY --parties ROLE,ROLE --question Q --a T --a-cost C
           --b T --b-cost C --reversible <yes|no> [--touches <vision|money|law|priority>]
  board.py [--board FILE] escalation <route|count>
  board.py [--board FILE] escalation list [--waiting-on ROLE] [--stage STAGE]
  board.py [--board FILE] escalation advise E<n> --recommendation T
  board.py [--board FILE] escalation settle E<n> --outcome T [--via human]
  board.py [--board FILE] select <KEY> [--plan PATH] [--refiner]
  board.py [--board FILE] signals [--input FILE]
  board.py [--board FILE] claim <KEY> [--release] [--input FILE]
  board.py [--board FILE] inbox [--input FILE]
  board.py [--board FILE] reply <KEY> <accept|deny|followup|update> [--text T]
  board.py [--board FILE] show <Q>
  board.py [--board FILE] withdraw <Q> [--for <Q2>] [--reason T]
  board.py [--board FILE] supersede <Q> --by <Q2> [--reason T]
  board.py [--board FILE] move <KEY> <on_hold|backlog|in_progress|in_review|in_test|done>
           [--reopen TEXT] [--epic EPIC] [--pr REF]… [--comment-file FILE] [--input FILE]
  board.py [--board FILE] check --jira FILE
  board.py [--board FILE] book staging --until <YYYY-MM-DDTHH:MMZ>
  board.py [--board FILE] unbook [<rc tag>]
  board.py [--board FILE] staging

show     prints one question as JSON: the open `owner_queue` item (else its `posted` line), its
         lines from board-answers.jsonl and a `status` (`answered: <kind>` after an Accept, Deny
         or Withdraw, `withdrawn`/`superseded`, `open`, else `closed`/`replaced`/`pruned` or
         `off the board`: `question_status`, the one definition of open). The answer a pane
         click wrote lives only in the answers file, never in board.json: read it here before
         repeating another session's question to the owner. Read-only; exit 1 for an unknown id.
answer   writes back an answer the owner gave in a session's chat: one line in
         board-answers.jsonl beside the board file, which the deliverer in the orchestrator's
         session then carries like a press of the /board pane. It refuses an id that is in neither
         `owner_queue` nor `news` of the board file and a kind outside the five; a refused write
         writes nothing. A second answer on an id an Accept or Deny already closed is a duplicate:
         it writes no answer line (nothing is carried again), records one `duplicate-answer` line
         in board-questions.jsonl, says so and exits 0. It opens board.json read-only.
set      writes the caller's own session line (found by `name` through `claude agents --json`
         and CLAUDE_CODE_SESSION_ID; appended with `name` and `session_id` when absent). `--for`
         writes another line and is the coordinator's. `waiting_on=<role>` stamps `since` and
         `sla_due` (the crew's `sla`, counted in daytime hours); the same role keeps them, another
         resets them, `waiting_on=` ends a wait and clears all three. `state` and `now` never touch
         `since`. `topic=<text>` and `keys=<KEY>[,<KEY>…]` (each a match of the crew's
         `naming.key`) write the line's own topic and keys, `epic=<KEY or number>` the epic a
         master's compaction hook reads (`epic_state.py`); an empty value clears them.
         `--session <name>` is checked against the caller's own name and refused when it differs.
         A refused value (and a field passed as a flag, `--now x`, or an answer kind like `no`)
         prints the valid values and `corrected call: board.py …` with the value it likely
         meant: a member's name in `waiting_on` names the role it holds. It stamps
         the line's `updated_at` (UTC minute); the board's `updated` moves with every write of the
         coordinator (`write_board`), `updated_by` never.
ask      posts a question for the owner after a cold reader (`cold_reader.py`) understood it
         without context (`--key` is the crew's `naming.key` or, before the ticket exists, a
         lower-case plan slug like `onboarding-v2`; `proj-12`, a key in lower case, is refused); otherwise the reader's reason goes back as a `note` on the asking
         session's line and in the refusal; the owner's news gets nothing. Every run past the field check leaves one line
         in board-questions.jsonl, text included. On success it prints exactly one JSON object on
         stdout, `{"id": "Q<n>", "outcome": "posted"}` (with `carry` for an `ask --to` on jira),
         everything else on stderr. The same question again from the same session within
         REPEAT_WINDOW (text, key, cause, recommendation and `--to`; no `--replace`) while the
         first is open posts nothing and prints the first id with `"outcome": "repeat"` (a
         `repeat` line in board-questions.jsonl): a retry never doubles a question. Without
         `--session` the asker is this session's own name (as `set` finds it); `--text-file`
         reads the ask from a file or `-` stdin, so a `code span` never meets the shell, and a
         refusal of text that looks shell-mangled names both. The cold reader sees only the
         asker's text, never a line the tool appends. The item keeps `asker_id` and the launcher
         marker's `starter` (only when `--session` is the caller itself) and `answer_to: asker`, unless
         `board.answer_to` (crew, else the repo's `.weside/config.json`) is `coordinator` (docs/board.md § Delivery). `--urgent` stamps
         `urgent: true` on the item and the log line; `bundle` lists urgent questions first.
         A `merge-go` question needs `--pr` (a URL, `<owner>/<repo>#<n>` or a number) on an OPEN
         PR (`gh pr view`), else it is refused before the reader; the item keeps `pr_url`.
         `--one-way <class>` (only with merge-go) stamps `one_way`: the pane then names Accept
         Go (it writes `accept`) beside the PR link; the asking session arms on it with
         `arm_pr.sh <PR>`.
         `--kind task` stamps `kind: task` (the pane labels
         Accept as Taken when the task carries a recommendation). `--source <command or link>` stamps where the ask's fact comes from (the
         pane shows it). `--owner <member>` or `--component <name>` (the member whose `components`
         hold it) stamps `owner`: the deliverer carries the answer to that member's session too.
         A merge-go appends the PR's required checks (`gh pr checks --required`) to the ask as
         one line and keeps it as `checks`: the count per green, red, cancelled, pending,
         skipped and the names of every one not green.
         An open question on the same key with the same cause, PR and `--to` refuses the ask
         before the reader, naming its id (a `duplicate` line in board-questions.jsonl); one with
         another cause draws a warning, and so does a duplicate under `--distinct` (the asker
         says it is another question). `--replace <QID>` takes that question off the queue (a
         `replaced` line in board-questions.jsonl) and posts this one.
         `--to <human>` (a crew with `humans`, another human than this session's) asks a human on
         another machine on the ticket `--key`: the item keeps `to`, `to_name` and `label` (the
         pane shows it waiting on that human, with Withdraw only), and the carry
         is the comment `board_humans.question_comment` and the label
         `board_humans.question_label`; `signals` reads the reply back.
close-merged removes every `merge-go` question in `owner_queue` whose PR (its `pr_url`, in
         any repo) is MERGED or CLOSED, whatever its answer, the owner's hand merge included (one
         `closed` line each in board-questions.jsonl) and prints `closed <id>: PR <state> <url>`
         per question, `closed: none` without one; `bundle` runs it first.
prune    drops what is handled from board.json (docs/board.md § Pruning) and prints the ids:
         a question or item an Accept or Deny closed once nothing is owed to its asker any more
         (the deliverer finds the asker only on the board): every answer line on it is older than
         the ledger's epoch, written in the asker's own session, or the asker's row in
         board-deliveries.jsonl is `delivered: true` (the coordinator's row when the coordinator
         asked it itself; refused, or not taken within PRUNE_AFTER_H:
         the starter's or the route row is), a Go on a one-way merge-go and an accepted
         `window-go` included; an unanswered `withdrawn` or `superseded` one; a news item the
         owner marked read; a `returned` item at once; a bundle (`B-…`) PRUNE_AFTER_H after its `ts`. Escalation
         items (`E<n>`, `E<n>a`) stay for `escalation settle`. Each drop appends one `pruned` line
         to board-questions.jsonl. Every write of board.json runs the same pass, so leftovers go
         on the first write after an update; it also moves a `decision` or `sample` item and an
         older item without an id from `news` into `log` (`tidy_news`, the newest LOG_KEEP kept).
         A wait that ends or changes on a line (`set`, `blocked`) appends one row
         `{key, session, waiting_on, since, ended, duration_s}` to board-waits.jsonl.
log      `log correction <session> <kind>` (the coordinator): one `correction` line in the flow log
         (`flow_log.py`, `flow.log_dir`); `kind` is one lower-case token.
blocked  marks another session's line as blocked (docs/board.md § Blocked workers) after re-reading
         `claude agents --json`: `permission` only while that session is blocked on a permission
         prompt (`waiting_on: human`), `chat` only while it is idle (`--waiting-on` a role key or
         human). It writes `blocked`, `waiting_on`, `since`, `sla_due` of that one line and nothing
         else; the same wait again writes nothing. `--clear` removes them once (refused while the
         permission prompt still stands) and marks the session's open questions the wait raised
         (`access-click` for a permission wait, `info` for a chat wait) posted during the wait
         `obsolete` (`labels.prompt_resolved` and the time), never deleted.
decision records an owner's cut, fence or process decision of their area (`roles.<area>`; `--key`
         a ticket key or, for a decision without a ticket, a plan slug as in `ask`): one `log`
         entry `D<n>` of kind `decision`, then one line in board-decisions.jsonl.
bundle   the coordinator's evening bundle: one news item `B-<date>` of kind `todo` listing the
         decisions since the last bundle by area and the open questions oldest first, then a
         marker line in board-decisions.jsonl. Nothing to show prints `bundle: nothing`. It runs
         `escalation route` first and lists the open bundle-stage escalations after the open
         questions.
news     `news add` (the coordinator): one item `N<n>` for the owner at the top of `news`, kind
         `info` (default), `gate` or `todo`, a one-line `--title` and an optional `--body`;
         prints the item. The pane's News frame is for the owner: milestones, gates, todos.
escalation the decision story between two owners (docs/board.md § Escalations): events in
         board-escalations.jsonl (`open`, `route`, `advise`, `settle`), a record is the fold of
         its events. `open` (a session holding one of the two `--parties` roles) writes `E<n>` at
         stage `self`, waiting on both parties until `sla_due` (the crew's `sla`, daytime hours).
         `route` (the coordinator) moves a record past its `sla_due`: `self` → `escalation` while
         the `roles.escalation` holder's board line is there and not `parked`, else to
         `crew.fallback.escalation` (`human_bundle` → stage `bundle`); `escalation` → `bundle`; a
         `--touches` record goes from `self` straight to `bundle` with `advice_from: escalation`.
         Entering `escalation` adds one `news` item `E<n>` of kind `escalation` with `for` the role
         waited on; entering `bundle` replaces it by one of kind `todo` (a `--touches` record adds
         `E<n>a` of kind `escalation` for the holder until `advise`). `list` prints the open
         records waiting on `--waiting-on` (default: the caller's roles), one line each, optionally
         at one `--stage`. `advise` (the escalation holder) puts the recommendation into a
         `--touches` record and drops `E<n>a`; `settle` closes a record and drops its news items:
         a party at `self`, the role waited on at `escalation`, the coordinator `--via human` at
         `bundle` (a `--touches` record only once advised). `count` prints the records per role
         pair in this ISO week and warns past two. With `board.ticketing: jira`, `open` and
         `settle` print a `carry:` `comment` op on the story's ticket as the last line.
select   moves a story to Selected when its `ENTRY_RULES["selected"]` hold, in order: the plan
         on `risk.rules_from` (main, after one fetch), the Ready gate (`ready_gate.story_failures`)
         and the plan-only tier (`plan_tier.py`) on that blob, and a green `ready-<KEY>` lens
         verdict (`lens_verdict.check`) bound to that blob, never to the checkout's plan; in a
         crew with `humans` the caller holds `roles.product` first. The first failing group
         refuses with `board.py select <KEY>: refused (<group>)` and its lines; no rule asks a
         human. `--refiner` (a refiner selecting its own story, after `plan on main`) refuses,
         naming the product role, unless the story's epic plan on that ref is approved, holds
         the key on its `line:` and says no `select: owner`, and the crew does not set
         `select.refiner: false`. A passing select comments `selected by <role>@<human>, plan <blob>, panel <id>`
         on the ticket after the transition.
signals  (several humans, docs/board.md § Several humans) for each `board.signals` entry whose
         role this session's human runs: the ticket search `board_humans.signal_jql`; each hit
         is one `todo` news item `S<n>` for that role, once per key, state and change time
         (board-signals.jsonl). Each open question this board sent to another human
         (`ask --to`) reads its ticket: a reply is an answer line (`via: ticket`) the deliverer
         carries to the asker, once per reply; the label taken off without a reply is `update`.
         With `board.ticketing: jira` the script reads nothing itself: it prints the reads as
         `carry:` (`search`, `read`) and the session hands their results back with `--input`.
claim    writes the claim comment `claim <role>@<human> <session>` on the ticket (and a line in
         board-claims.jsonl), refused while another role or human holds a live claim
         (`board.claim_hours`, from the ticket's comments and the local claims); `--release` ends
         this session's claim. With `jira` the first run carries the read like `signals`.
inbox    (several humans) the tickets labelled `board_humans.question_label` for this session's
         human: the search `board_humans.inbox_jql`, carried like `signals` with `jira`.
reply    (several humans) this human's answer on a ticket: the comment
         `board_humans.reply_comment`, then this human's question label off (`unlabel`); only
         the asked human answers, a human with the same role never does.
withdraw takes the caller's own open question off `owner_queue` (`supersede --by Q2`: replaced
         by a newer one), a `withdrawn` or `superseded` line in board-questions.jsonl; a question
         asked with `--to` also gets a comment and loses its label. Only its asker (session name)
         or the coordinator. `withdraw --for Q2` records that it gave way to Q2; a refused
         `supersede` of Q2 names every session that withdrew for it (`--for`, or Q2 in the
         reason), so the caller tells them their alternative is on no board. A question already
         off the queue (answered and pruned, closed, withdrawn) is no refusal: it prints
         `<id>: nothing to withdraw, it is off the queue (<status>, <last outcome> <ts>)` and exits
         0; an id the board and its logs never had exits 1.
move     moves a story to another state when that state's entry rule holds (docs/board.md
         § Moves; with `humans` first the owner of the state it leaves, read from the ticket's
         status, § Several humans): `on_hold` --reopen, `backlog` --epic of an approved epic plan, `in_progress`
         after a `selected` row (from `in_review`/`in_test` with --reopen: a revert or a failed
         test), `in_review` with every --pr merged and linked (`gh pr view`),
         `in_test` after `in_review`, `done` after an `in_review` or `in_test` row with --comment-file holding a `Not proven:` line (or, in
         process from accept.py, a green verdict entry re-checked here: `move_done`), or from
         any state but done with --already-fixed <owner>/<repo>#<n> (a merged PR fixed it
         before it was built; row `via: already-fixed`, `pr`); a `done`
         move carries the transition and then the acceptance comment, and every
         `acceptance.done_sample`-th `via: receipt` row adds a `sample` `log` entry. A
         refusal prints `board.py move <KEY> <state>: refused: <reason>` per failure.
         Both write one row to board-transitions.jsonl after every rule passed, call the
         ticketing adapter once (`ticket_adapter.py`, by `board.ticketing`) and, with
         `board.ticketing: jira`, print `carry: <JSON list>` as the last line for the session
         to execute with its ticketing tool. A refusal writes, calls and carries nothing.
check    compares a ticketing snapshot (`--jira FILE`: a JSON object key → status name, read by
         the session; the script reads no ticketing system) with the transitions log and the
         board: one `drift:` line per mismatch, one `error:` line per unknown status, exit 1;
         else `no drift (<n> keys)`. Exit 2 for an unusable snapshot.
book     books staging for the caller's session until a UTC minute (docs/board.md § Staging): one
         issue in the crew's repo (`board_staging.py` owns the issue grammar), refused with
         `board.py book: refused: <rc> in acceptance since <UTC>` while an acceptance is open and
         naming the holder while another booking runs. Then it syncs like `staging`.
unbook   closes the caller's own booking early; `unbook <rc>` closes the acceptance of that RC.
staging  reads the booking and acceptance issues into board.json's `staging` block and prints one
         line each (`staging: free` without either); an acceptance past the crew's
         `release.staging_sla_hours` adds one `todo` news item `ST<issue>` for the coordinator, once.

path     prints the board file a verb writes (absolute); `--crew-only` prints the crew's
         `board.file` and exits 1 when the crew names none (the /board pane's lookup).

Every write of board.json goes through `StateDir.write_board` (an exclusive lock on
board.json.lock, a re-read, then a temp file and `os.replace`). The JSONL files beside the board
only grow (O_APPEND). FILE defaults to the crew's `board.file` (relative to the crew file), else
~/.claude/we-state/board.json. The JSONL files are named after the board file's stem:
`board.json` keeps `board-questions.jsonl` and the rest, `acme-board.json` writes
`acme-board-questions.jsonl`, so two crews count their ids apart.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import difflib
import fcntl
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import board_humans  # noqa: E402
import board_staging  # noqa: E402
import cold_reader  # noqa: E402
import crew as crew_mod  # noqa: E402
import flow_log  # noqa: E402  (the one writer of the flow log)
import lens_verdict  # noqa: E402
import plan_tier  # noqa: E402
import ready_gate  # noqa: E402
import ticket_adapter  # noqa: E402
import worker_launch as wl  # noqa: E402  (the one reader of `claude agents --json`)

DEFAULT_BOARD = str(Path(crew_mod.DEFAULT_STATE_DIR) / crew_mod.BOARD_NAME)
KINDS = ("accept", "deny", "followup", "update", "withdraw")
CLOSING = ("accept", "deny", "withdraw")  # withdraw: the asker's human takes back an `ask --to`
# The one owner of the session state values; docs/board.md's `sessions[].state` row mirrors it.
SESSION_STATES = ("build", "ci", "active", "wait-owner", "idle", "parked", "done")
SET_FIELDS = ("waiting_on", "state", "now", "topic", "keys", "epic")
CAUSES = ("merge-go", "plan", "prod", "cut-fence", "access-click", "window-go", "info")
DECISION_KINDS = ("cut", "fence", "process")
ASK_FIELDS = ("session", "key", "key_title", "ask", "recommendation", "cause")
RETURN_PREFIX = "returned to "
TOUCHES = ("vision", "money", "law", "priority")
OPEN_FIELDS = ("key", "parties", "question", "a", "a_cost", "b", "b_cost", "reversible")
STAGES = ("self", "escalation", "bundle")
NEWS_KIND_BY_STAGE = {"escalation": "escalation", "bundle": "todo"}
# A question about an epic before its ticket exists names the plan slug (`ask --key`).
PLAN_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
PAIR_WARN_AFTER = 2  # escalations per role pair and ISO week before the crew's rights look wrong
LOCK_WAIT_S = 10.0
MINUTE_FMT = "%Y-%m-%dT%H:%MZ"
ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"
BLOCKED_KINDS = ("permission", "chat")
EXCERPT_CHARS = 200  # a blocked command or question excerpt on the board line
TOKEN = re.compile(r"[a-z][a-z0-9_-]*")  # a correction's kind: one lower-case token
UNCHANGED = object()  # a `write_board` mutation returning this leaves board.json untouched
# Pruning (docs/board.md § Pruning): a closed question waits until its asker is carried, since the
# deliverer finds the asker only on the board; returned items and bundles go PRUNE_AFTER_H after
# their ts.
DELIVERED_KINDS = KINDS  # the answer kinds the deliverer carries; `read` is not one
PRUNE_AFTER_H = 24
# board-questions.jsonl outcomes that take a question off the board for good
GONE = ("withdrawn", "superseded")
# ... and those that take it off as a side effect (merged PR, `ask --replace`, pruning)
OFF_BOARD = ("closed", "replaced", "pruned")
# Every outcome that closes a posted question (`question_status`, flow_intervals.py). `returned`,
# `duplicate` and `repeat` close none: they log a refused ask and carry no new id.
QUESTION_CLOSED = GONE + OFF_BOARD
# A `returned` item is the asker's, who has it as its line's note: it leaves `news` on the next write.
RETURNED_KIND = "returned"
# The board's `log` (docs/board.md § News): what is kept for the record, not for the owner to read.
LOG_KINDS = ("decision", "sample")
LOG_KEEP = 50  # newest entries `log` keeps; board-decisions.jsonl and the transitions log keep all
NEWS_KINDS = ("info", "gate", "todo")  # what `news add` writes
BUNDLE_ID = re.compile(r"B-\d{4}-\d{2}-\d{2}(?:-\d+)?")
ESCALATION_ID = re.compile(r"E\d+a?")  # owned by `escalation route|settle`, never pruned


class BoardError(Exception):
    """A refusal: the message goes to stderr, `code` is the exit code."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def _answer_writer():
    """answer.py's `append`, by path: the one writer of the answers file's line format."""
    path = Path(__file__).resolve().parent.parent / "hooks" / "board" / "answer.py"
    spec = importlib.util.spec_from_file_location("we_board_answer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.append


def _now():
    return datetime.now(timezone.utc)


def _iso(ts):
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_jsonl(path):
    """Every line that parses as a JSON object; torn or foreign lines are skipped."""
    try:
        text = path.read_text(encoding="utf-8")
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


def _append_jsonl(path, record):
    """One whole line in one write on a file opened O_APPEND: nothing in the file is rewritten."""
    line = json.dumps(record, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
    return record


class StateDir:
    """The board file and the JSONL files beside it: every path and every read or write of them."""

    def __init__(self, board_file, now=None, stamps_updated=False):
        self.board_path = Path(board_file).expanduser()
        self.now = now  # the pruning clock; None reads the wall clock
        # True for the coordinator's writes (board.py main): only they move the board's `updated`.
        self.stamps_updated = stamps_updated
        self.last_pruned = []  # the `pruned` lines of the last write_board
        self.answers_path = self.log_path("answers")
        self.questions_path = self.log_path("questions")
        self.decisions_path = self.log_path("decisions")
        self.escalations_path = self.log_path("escalations")
        self.transitions_path = self.log_path("transitions")
        self.waits_path = self.log_path("waits")
        self.deliveries_path = self.log_path("deliveries")
        self.signals_path = self.log_path("signals")
        self.claims_path = self.log_path("claims")
        self.lock_path = self.board_path.with_name(self.board_path.name + ".lock")

    def log_path(self, kind):
        """`<stem>-<kind>.jsonl` beside the board file: `board.json` keeps `board-<kind>.jsonl`, a
        second crew's `acme-board.json` gets `acme-board-<kind>.jsonl` and its own ids."""
        return self.board_path.with_name(f"{self.board_path.stem}-{kind}.jsonl")

    def board(self):
        """The board file as a dict, read only; a missing file is an empty board."""
        try:
            with open(self.board_path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return {}
        if not isinstance(data, dict):
            raise BoardError(f"{self.board_path} is no JSON object")
        return data

    def write_board(self, mutate, after=None):
        """Run `mutate(board)` on a fresh read under the board lock, then replace the file with the
        mutated board (temp file + `os.replace`) unless `mutate` returned `UNCHANGED` and the pruning
        pass (`prune`) dropped nothing. `after(result)` runs once the file is replaced, still under
        the lock: the place for a JSONL line that must not exist without its board change. Returns
        what `mutate` returned. A write of the coordinator (`stamps_updated`) stamps the board's
        `updated` (the header's age, and the lapse of an Update mark once the orchestrator rewrote
        the board: `board.ts` `shownAnswer`); another session's write leaves it; `updated_by`
        stays as it was.
        The plugin's only writer of board.json."""
        with self.locked():
            return self._write_board_locked(mutate, after)

    @contextlib.contextmanager
    def locked(self):
        """The board lock (`<board>.lock`, flock, `LOCK_WAIT_S`): board.json and every JSONL line
        whose content depends on what the log already holds are written under it."""
        self.board_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.lock_path), os.O_WRONLY | os.O_CREAT, 0o644)
        try:
            deadline = time.monotonic() + LOCK_WAIT_S
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise BoardError(
                            f"lock {self.lock_path} not taken within {LOCK_WAIT_S:g} s"
                        ) from None
                    time.sleep(0.05)
            yield
        finally:
            os.close(fd)

    def _write_board_locked(self, mutate, after):
        board = self.board()
        result = mutate(board)
        pruned = self.last_pruned = prune(board, self, self.now or _now())
        tidied = tidy_news(board)
        if result is UNCHANGED and not pruned and not tidied:
            return result
        if self.stamps_updated:
            board["updated"] = (self.now or _now()).astimezone().isoformat(timespec="seconds")
        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=str(self.board_path.parent), prefix=self.board_path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp:
                json.dump(board, tmp, ensure_ascii=False, indent=2)
                tmp.write("\n")
            os.replace(tmp_name, str(self.board_path))
        except BaseException:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise
        for line in pruned:
            self.append_question(line)
        if after is not None and result is not UNCHANGED:
            after(result)
        return result

    def ids(self):
        board = self.board()
        out = set()
        for field in ("owner_queue", "news"):
            for item in board.get(field) or []:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    out.add(item["id"])
        return out

    def answers(self):
        return _read_jsonl(self.answers_path)

    def closing_answer(self, qid):
        """The Accept or Deny line that closed `qid`, or None."""
        return next(
            (a for a in self.answers() if a.get("id") == qid and a.get("answer") in CLOSING), None
        )

    def append_answer(self, qid, kind, session, via=None, quote=None, ts=None):
        """One answer line; it quotes the question's `ask` and `recommendation` from the open item,
        so the line reads without the board."""
        stamp = ts or _now().isoformat(timespec="milliseconds").replace("+00:00", "Z")
        item = next(
            (
                q
                for q in self.board().get("owner_queue") or []
                if isinstance(q, dict) and q.get("id") == qid
            ),
            {},
        )
        return _answer_writer()(
            str(self.answers_path),
            qid,
            kind,
            stamp,
            session,
            via=via,
            quote=quote,
            ask=item.get("ask") or None,
            recommendation=item.get("recommendation") or None,
        )

    def questions(self):
        return _read_jsonl(self.questions_path)

    def append_question(self, line):
        return _append_jsonl(self.questions_path, line)

    def decisions(self):
        return _read_jsonl(self.decisions_path)

    def append_decision(self, line):
        return _append_jsonl(self.decisions_path, line)

    def escalations(self):
        return _read_jsonl(self.escalations_path)

    def append_escalation(self, line):
        return _append_jsonl(self.escalations_path, line)

    def transitions(self):
        return _read_jsonl(self.transitions_path)

    def append_transition(self, row):
        return _append_jsonl(self.transitions_path, row)

    def record_transition(self, key, build):
        """Under the board lock: `build(last row of key or None)` makes the row, which is appended.
        Two moves of one key at once cannot both read the same `from`. Returns the row."""
        with self.locked():
            row = build(self.last_rows().get(key))
            self.append_transition(row)
        return row

    def append_wait(self, row):
        return _append_jsonl(self.waits_path, row)

    def deliveries(self):
        return _read_jsonl(self.deliveries_path)

    def last_rows(self):
        """`{key: last transitions row}` in log order."""
        out = {}
        for row in self.transitions():
            if isinstance(row.get("key"), str):
                out[row["key"]] = row
        return out

    def next_id(self, prefix, board):
        """`<prefix><n+1>` over every id the board, the answers file and the two logs carry."""
        pattern = re.compile(re.escape(prefix) + r"(\d+)")
        seen = [
            item.get("id")
            for field in ("owner_queue", "news", "log")
            for item in board.get(field) or []
            if isinstance(item, dict)
        ]
        logs = self.answers() + self.questions() + self.decisions() + self.escalations()
        seen += [line.get("id") for line in logs]
        numbers = [
            int(m.group(1))
            for m in (pattern.fullmatch(i) for i in seen if isinstance(i, str))
            if m
        ]
        return f"{prefix}{max(numbers, default=0) + 1}"


def _parse_ts(text):
    """An ISO date or timestamp as an aware UTC datetime (naive counts as UTC); None if unreadable."""
    if not isinstance(text, str) or not text.strip():
        return None
    raw = text.strip().replace("Z", "+00:00")
    # Python 3.9's fromisoformat takes 3 or 6 fraction digits only: drop the fraction.
    raw = re.sub(r"(T\d\d:\d\d:\d\d)\.\d+", r"\1", raw)
    try:
        ts = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _ledger(state):
    """The deliverer's first start (`epoch`, None without one), every (id, answer_ts, role)
    with a `delivered: true` row in board-deliveries.jsonl, and every (id, answer_ts, to) of a
    delivered `coordinator` row (the coordinator as asker gets no asker row: deliver.ts
    `recipientsOf`)."""
    epoch, delivered, to_coordinator = None, set(), set()
    for row in state.deliveries():
        if set(row) == {"epoch"}:
            ts = _parse_ts(row["epoch"])
            epoch = ts if epoch is None or (ts and ts < epoch) else epoch
        elif row.get("delivered") is True:  # a later refusal never follows a delivery
            delivered.add((row.get("id"), row.get("answer_ts"), row.get("role")))
            if row.get("role") == "coordinator":
                to_coordinator.add((row.get("id"), row.get("answer_ts"), row.get("to")))
    return epoch, delivered, to_coordinator


def prune(board, state, now):
    """Drop what is handled from `owner_queue` and `news` of `board` (in place); returns one
    `pruned` log line per drop. The rules are in the module docstring under `prune`."""
    after = timedelta(hours=PRUNE_AFTER_H)
    closing, last, carried = {}, {}, {}
    for a in state.answers():
        qid = a.get("id")
        if not isinstance(qid, str) or qid in closing:
            continue  # a line after the close is never delivered (docs/board.md § Answers)
        if a.get("answer") in DELIVERED_KINDS:
            carried.setdefault(qid, []).append(a)
        if a.get("answer") in CLOSING:
            closing[qid] = a
        last[qid] = a.get("answer")
    epoch, delivered, to_coordinator = _ledger(state)
    gone = {q.get("id") for q in state.questions() if q.get("outcome") in GONE}

    def asker_carried(item, line):
        """Nothing owed to the asker for this answer line any more (deliver.ts `pendingLines`)."""
        asker = item.get("session")
        at = _parse_ts(line.get("ts"))
        if not asker or line.get("session") == asker or epoch is None or (at and at <= epoch):
            return True
        key = (line.get("id"), line.get("ts"))
        if (*key, asker) in to_coordinator:
            return True  # the coordinator asked it itself: its prompt was the asker's copy
        return any((*key, role) in delivered for role in ("asker", "starter", "route"))

    def answered(item, qid, close):
        """A closed question goes once its asker is owed nothing: delivered to the asker, or
        routed to the coordinator (deliver.ts routes an answer the asker has not taken within
        PRUNE_AFTER_H). A Go on a one-way merge-go and an accepted window-go go the same way:
        the asker holds the go in its prompt and in `show`, the owner's queue keeps only what
        still waits for the owner."""
        if all(asker_carried(item, line) for line in carried.get(qid, [])):
            return {"reason": "answered", "answer": close["answer"]}
        return None

    def verdict(field, item):
        qid = item.get("id")
        if not isinstance(qid, str) or ESCALATION_ID.fullmatch(qid):
            return None
        close = closing.get(qid)
        if qid in gone and close is None:
            return {"reason": "withdrawn"}
        if close:
            return answered(item, qid, close)
        return news_verdict(item, qid) if field == "news" else None

    def news_verdict(item, qid):
        if last.get(qid) == "read":
            return {"reason": "read"}
        if item.get("kind") == RETURNED_KIND:
            return {"reason": "returned"}
        posted = _parse_ts(item.get("ts"))
        if BUNDLE_ID.fullmatch(qid) and posted and now - posted >= after:
            return {"reason": "expired"}
        return None

    lines = []
    for field in ("owner_queue", "news"):
        items = board.get(field)
        if not isinstance(items, list):
            continue
        kept = []
        for item in items:
            why = verdict(field, item) if isinstance(item, dict) else None
            if why is None:
                kept.append(item)
            else:
                lines.append(
                    {"id": item["id"], "ts": _iso(now), "outcome": "pruned", "field": field, **why}
                )
        if len(kept) != len(items):
            board[field] = kept
    return lines


def _log_entry(item):
    """One `log` entry from a news item: kept as it is with an id, else (an older line with `text`
    and `key`, or a bare string) its title made from them; None when nothing readable is left."""
    if isinstance(item, str):
        return {"title": item.strip()} if item.strip() else None
    if not isinstance(item, dict):
        return None
    if isinstance(item.get("id"), str) and item["id"]:
        return item
    text = str(item.get("text") or "").strip()
    key = str(item.get("key") or "").strip()
    title = str(item.get("title") or "").strip() or (
        f"{key}: {text}" if text and key and key != "—" else text
    )
    if not title:
        return None
    entry = {"title": title}
    entry.update({k: item[k] for k in ("body", "ts", "kind") if item.get(k)})
    return entry


def append_log(board, entries):
    """Append `entries` to the board's `log` (in place), keeping the newest LOG_KEEP."""
    log = board.get("log") if isinstance(board.get("log"), list) else []
    board["log"] = (log + list(entries))[-LOG_KEEP:]


def tidy_news(board):
    """Move what is no news for the owner from `news` into `log` (in place): a `decision` or
    `sample` item, and an older item without an id. Returns whether the board changed."""
    news = board.get("news")
    if not isinstance(news, list):
        return False
    kept, moved = [], []
    for item in news:
        has_id = isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]
        if has_id and item.get("kind") not in LOG_KINDS:
            kept.append(item)
            continue
        entry = _log_entry(item)
        if entry is not None:
            moved.append(entry)
    if len(kept) == len(news):
        return False
    board["news"] = kept
    if moved:
        append_log(board, moved)
    return True


def load_crew(start=None):
    """The merged crew in force for `start`; without a crew file a copy of crew.DEFAULTS with
    empty `roles` and `members` (`crew._merge` needs `roles`)."""
    try:
        _, found = crew_mod.find_and_load(start)
    except crew_mod.CrewError as exc:
        raise BoardError(f"crew: {exc}") from None
    if found is not None:
        return found
    defaults = copy.deepcopy(crew_mod.DEFAULTS)
    defaults["roles"] = {}
    defaults["members"] = {}
    return defaults


def own_session_name(env=None, verb="set"):
    """(name, session id) of the calling session as `claude agents --json` lists it."""
    env = os.environ if env is None else env
    session_id = env.get("CLAUDE_CODE_SESSION_ID") or None
    try:
        rows = wl.sessions()
    except wl.LaunchError as exc:
        raise BoardError(f"board.py {verb}: {exc}") from None
    try:
        return wl.lead_address(rows, session_id), session_id
    except wl.LaunchError:
        raise BoardError(
            f"board.py {verb}: this session has no name; run /rename first"
            + (" or pass --session <name>" if verb == "ask" else "")
        ) from None


def _daytime_window(daytime):
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", str(daytime))
    if not m or not 0 <= int(m.group(1)) < int(m.group(2)) <= 24:
        raise BoardError(f'sla.daytime "{daytime}" is no "HH-HH" window')
    return int(m.group(1)), int(m.group(2))


def daytime_due(since, hours, daytime, tz):
    """`since` (aware) plus `hours`, counting only the minutes inside the daily `daytime` window of
    zone `tz`, every day of the week alike; returned in UTC. The one owner of this arithmetic."""
    try:
        zone = ZoneInfo(tz)
    except (ValueError, KeyError, OSError):
        raise BoardError(f'sla.tz "{tz}" is no time zone') from None
    start_h, end_h = _daytime_window(daytime)
    left = timedelta(hours=float(hours))
    cur = since.astimezone(timezone.utc)
    day = cur.astimezone(zone).date()
    while True:
        midnight = datetime(day.year, day.month, day.day, tzinfo=zone)
        # wall-clock hours of that day, converted to UTC before any subtraction
        opens = (midnight + timedelta(hours=start_h)).astimezone(timezone.utc)
        closes = (midnight + timedelta(hours=end_h)).astimezone(timezone.utc)
        cur = max(cur, opens)
        if cur < closes:
            if left <= closes - cur:
                return cur + left
            left -= closes - cur
        day += timedelta(days=1)


# The state words sessions typed in place of a SESSION_STATES value, mapped to the one meant.
STATE_WORDS = {
    "working": "build",
    "work": "build",
    "building": "build",
    "coding": "build",
    "waiting": "wait-owner",
    "wait": "wait-owner",
    "blocked": "wait-owner",
    "refine": "active",
    "refining": "active",
    "planning": "active",
    "busy": "active",
    "review": "ci",
    "stopped": "parked",
    "paused": "parked",
    "finished": "done",
}


def _closest(value, choices):
    found = difflib.get_close_matches(value.strip().lower(), choices, n=1, cutoff=0.6)
    return found[0] if found else None


def _state_fix(value):
    return STATE_WORDS.get(value.strip().lower()) or _closest(value, SESSION_STATES)


def _waiting_fix(value, crew):
    """The role key a `waiting_on` value means: a member's name → the role it holds, the human's
    name → `human`, a near miss → that key; None when nothing fits."""
    text = value.strip()
    head = re.split(r"[\s(,;]", text, maxsplit=1)[0]
    roles = set(crew_mod.ROLE_KEYS) | {"human"}
    if text.lower() in roles:
        return text.lower()
    for word in (text, head):
        found = crew_mod.member(crew, word) if word else None
        if found:
            held = [r for r, slug in (crew.get("roles") or {}).items() if slug == found[0]]
            if held:
                return held[0]
        names = [str((crew.get("human") or {}).get("name") or "")]
        names += [h.get("name", "") for h in crew_mod.humans(crew).values()]
        if word and word.lower() in {n.lower() for n in names if n}:
            return "human"
    return _closest(head, sorted(roles))


def _parse_assignments(items, crew):
    """(fields, failures, fixed): `fixed` is the call's assignments with each refused value
    replaced by the one it likely meant, or None when a failure has no such value."""
    fields, failures, fixed = {}, [], []
    roles = set(crew_mod.ROLE_KEYS) | {"human"}
    for item in items:
        if "=" not in item:
            failures.append(f"board.py set: {item!r} is no <field>=<value>")
            fixed = None
            continue
        key, value = item.split("=", 1)
        fix = None
        if key not in SET_FIELDS:
            near = _closest(key.replace("-", "_"), SET_FIELDS)
            failures.append(
                f"board.py set: field {key!r} is not settable (only {', '.join(SET_FIELDS)})"
            )
            fix = f"{near}={value}" if near else None
        elif key == "waiting_on" and value and value not in roles:
            failures.append(
                f"board.py set: waiting_on {value!r} is no role key "
                f"({', '.join(crew_mod.ROLE_KEYS)} or human)"
            )
            meant = _waiting_fix(value, crew)
            fix = f"waiting_on={meant}" if meant else None
        elif key == "state" and value not in SESSION_STATES:
            failures.append(
                f"board.py set: state {value!r} is not one of {', '.join(SESSION_STATES)}"
            )
            meant = _state_fix(value)
            fix = f"state={meant}" if meant else None
        elif (
            key == "epic"
            and value
            and not (re.fullmatch(r"\d+", value) or not _key_failure(crew, value, "set"))
        ):
            failures.append(
                f"board.py set: epic {value!r} is neither a ticket key of the crew's naming.key "
                "nor an epic number"
            )
        elif key in ("now", "topic") and "\n" in value:
            failures.append(f"board.py set: {key} is one line")
            fix = f"{key}={' '.join(value.split())}"
        elif key == "keys":
            keys = [k for k in re.split(r"[,\s]+", value) if k]
            key_rx = (crew.get("naming") or {}).get("key") or crew_mod.DEFAULTS["naming"]["key"]
            bad = [k for k in keys if not re.fullmatch(key_rx, k)]
            if bad:
                failures.append(
                    f"board.py set: keys {', '.join(bad)} do not match the crew's naming.key {key_rx}"
                )
            else:
                fields[key] = keys
                fix = item
        else:
            fields[key] = value
            fix = item
        if fixed is not None:
            fixed = [*fixed, fix] if fix is not None else None
    return fields, failures, fixed


def _corrected(verb_argv):
    """The line naming the corrected call."""
    return "corrected call: board.py " + shlex.join(verb_argv)


def _minute(ts):
    return ts.astimezone(timezone.utc).replace(second=0, microsecond=0)


def _wait(crew, now, waiting_on):
    """`{waiting_on, since, sla_due}` from `now`: the one owner of the SLA wait, its defaults
    `crew.DEFAULTS["sla"]`."""
    sla = {**crew_mod.DEFAULTS["sla"], **(crew.get("sla") or {})}
    since = _minute(now)
    due = daytime_due(since, sla["hours"], sla["daytime"], sla["tz"])
    return {
        "waiting_on": waiting_on,
        "since": since.strftime(MINUTE_FMT),
        "sla_due": due.strftime(MINUTE_FMT),
    }


def _apply_wait(line, role, crew, now):
    """Set (or with an empty `role` end) the line's wait; returns the waits-log row of the wait
    that ended or changed (`_wait_row`), else None."""
    old = line.get("waiting_on")
    ended = _wait_row(line, crew, now) if old and old != role else None
    if not role:
        if old:
            for key in ("waiting_on", "since", "sla_due"):
                line.pop(key, None)
        return ended
    if old == role:
        return None
    line.update(_wait(crew, now, role))
    return ended


def _line_key(line, crew):
    """The story key of a board line: its first `keys` entry, its `blocked.key`, else the first
    `naming.key` match in its name, else None."""
    keys = line.get("keys")
    if isinstance(keys, list) and keys and isinstance(keys[0], str):
        return keys[0]
    blocked = line.get("blocked")
    if isinstance(blocked, dict) and isinstance(blocked.get("key"), str):
        return blocked["key"]
    key_rx = (crew.get("naming") or {}).get("key") or crew_mod.DEFAULTS["naming"]["key"]
    found = re.search(key_rx, str(line.get("name") or ""))
    return found.group(0) if found else None


def _wait_row(line, crew, now):
    """One `board-waits.jsonl` row for the line's current wait, ended at `now`."""
    try:
        since = datetime.strptime(str(line.get("since")), MINUTE_FMT).replace(tzinfo=timezone.utc)
        duration = int((now - since).total_seconds())
    except ValueError:
        duration = None
    return {
        "key": _line_key(line, crew),
        "session": line.get("name"),
        "waiting_on": line.get("waiting_on"),
        "since": line.get("since"),
        "ended": _iso(now),
        "duration_s": duration,
    }


def cmd_set(state, args, crew, now):
    fields, failures, fixed = _parse_assignments(args.assignments, crew)
    if failures and fixed:
        who = ["--for", args.for_] if args.for_ is not None else []
        failures.append(_corrected(["set", *who, *fixed]))
    if args.for_ is not None and not crew_mod.holds_role(crew, "coordinator", os.environ):
        failures.append(
            f"board.py set: --for {args.for_}: only the coordinator writes another session's line"
        )
    if failures:
        raise BoardError("\n".join(failures))
    if args.for_ is not None:
        name, session_id = args.for_, None
    else:
        name, session_id = own_session_name()
        if args.session is not None and args.session != name:
            raise BoardError(
                f"board.py set: --session {args.session}: set writes this session's own line, "
                f"named {name} (claude agents); another session's line is the coordinator's "
                "`--for <name>`"
            )
    ended = []

    def mutate(board):
        line = _session_line(board, name, session_id)
        if "waiting_on" in fields:
            ended.append(_apply_wait(line, fields["waiting_on"], crew, now))
            # the session set its own wait: a `blocked` mark of the old wait is over
            if ended[-1] is not None:
                line.pop("blocked", None)
        for key in ("state", "now", "topic", "keys", "epic"):
            if key in fields:
                if fields[key] in ("", []):
                    line.pop(key, None)  # `topic=` / `keys=` clears it
                else:
                    line[key] = fields[key]
        line["updated_at"] = now.strftime(MINUTE_FMT)
        return dict(line)

    print(
        json.dumps(
            state.write_board(mutate, after=lambda _r: _log_waits(state, ended)),
            ensure_ascii=False,
        )
    )
    return 0


def _session_line(board, name, session_id):
    """The board line named `name`, appended with `name` and `session_id` when absent."""
    sessions = board.setdefault("sessions", [])
    line = next((s for s in sessions if isinstance(s, dict) and s.get("name") == name), None)
    if line is None:
        line = {"name": name}
        if session_id:
            line["session_id"] = session_id
        sessions.append(line)
    return line


def _log_waits(state, rows):
    for row in rows:
        if row is not None:
            state.append_wait(row)


def cmd_log(state, args, crew, now):
    verb = f"board.py log {args.what}"
    failures = []
    if not crew_mod.holds_role(crew, "coordinator", os.environ):
        failures.append(f"{verb}: only the coordinator records a correction")
    if not TOKEN.fullmatch(args.kind):
        failures.append(f"{verb}: kind {args.kind!r} is no lower-case token")
    if not args.session.strip() or args.session != args.session.strip():
        failures.append(f"{verb}: session {args.session!r} is no session name")
    log_dir, tz, _flow = flow_log.settings(crew)
    if not log_dir:
        failures.append(f"{verb}: flow.log_dir is unset in the crew")
    if failures:
        raise BoardError("\n".join(failures))
    record = {
        "type": "correction",
        "ts": _iso(now),
        "session": args.session,
        "kind": args.kind,
        "by": (crew.get("roles") or {}).get("coordinator"),
    }
    try:
        flow_log.append(log_dir, record, tz)
    except (flow_log.FlowLogError, OSError) as exc:
        raise BoardError(f"{verb}: {exc}") from None
    print(json.dumps(record, ensure_ascii=False))
    return 0


def _agent_rows():
    try:
        return wl.sessions()
    except wl.LaunchError as exc:
        raise BoardError(f"board.py blocked: {exc}") from None


def _row_named(rows, name):
    return next((r for r in rows if isinstance(r, dict) and r.get("name") == name), None)


def _on_permission_prompt(row):
    return (
        row is not None
        and row.get("state") == "blocked"
        and "permission" in str(row.get("waitingFor") or "").lower()
    )


def _blocked_failures(args, row):
    name, kind = args.name, args.kind
    failures = []
    roles = set(crew_mod.ROLE_KEYS) | {"human"}
    if kind == "permission" and args.waiting_on not in (None, "human"):
        failures.append("board.py blocked: a permission prompt waits on human")
    if kind == "chat" and not args.waiting_on:
        failures.append("board.py blocked: --kind chat needs --waiting-on <role key or human>")
    elif args.waiting_on and args.waiting_on not in roles:
        failures.append(
            f"board.py blocked: waiting_on {args.waiting_on!r} is no role key "
            f"({', '.join(crew_mod.ROLE_KEYS)} or human)"
        )
    if row is None:
        failures.append(f"board.py blocked: {name} is not running (claude agents --json)")
    elif kind == "permission" and not _on_permission_prompt(row):
        failures.append(
            f"board.py blocked: {name} is not blocked on a permission prompt right now "
            f"(state {row.get('state')!r}, waitingFor {row.get('waitingFor')!r})"
        )
    elif kind == "chat" and row.get("status") != "idle":
        failures.append(
            f"board.py blocked: {name} is not idle right now (status {row.get('status')!r})"
        )
    return failures


def cmd_blocked(state, args, crew, now):
    if args.clear:
        return _clear_blocked(state, args, crew, now)
    if args.kind is None:
        raise BoardError("board.py blocked: give --kind permission|chat, or --clear")
    rows = _agent_rows()
    row = _row_named(rows, args.name)
    failures = _blocked_failures(args, row)
    if args.key is not None:
        failures += _key_failure(crew, args.key, "blocked")
    if failures:
        raise BoardError("\n".join(failures))
    starter = _row_named(rows, args.starter) if args.starter else None
    waiting_on = args.waiting_on or "human"
    fresh = {
        "kind": args.kind,
        "starter": args.starter,
        "starter_session_id": (starter or {}).get("sessionId"),
        "key": args.key,
        "since": _iso(now),
        "waiting_for": row.get("waitingFor") if args.kind == "permission" else None,
        "command": (args.command or "")[:EXCERPT_CHARS] or None,
    }
    fresh = {k: v for k, v in fresh.items() if v is not None}
    ended = []

    def mutate(board):
        line = _session_line(board, args.name, row.get("sessionId"))
        old = line.get("blocked") if isinstance(line.get("blocked"), dict) else None
        blocked = dict(fresh)
        if old and old.get("kind") == args.kind and old.get("since"):
            blocked["since"] = old["since"]  # the same wait goes on
        if old == blocked and line.get("waiting_on") == waiting_on:
            return UNCHANGED
        ended.append(_apply_wait(line, waiting_on, crew, now))  # the ended wait keeps its key
        line["blocked"] = blocked
        line["updated_at"] = now.strftime(MINUTE_FMT)  # a rewritten line is not stale
        return dict(line)

    result = state.write_board(mutate, after=lambda _r: _log_waits(state, ended))
    if result is UNCHANGED:
        print(f"board.py blocked: {args.name} unchanged")
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


def _resolved_label(crew, now):
    label = (crew.get("labels") or {}).get("prompt_resolved") or crew_mod.DEFAULTS["labels"][
        "prompt_resolved"
    ]
    _log_dir, tz, _flow = flow_log.settings(crew)
    return f"{label} {now.astimezone(ZoneInfo(tz)).strftime('%H:%M')}"


# The cause of the question a wait raises (the sampler's detector asks it): a cleared wait makes its
# open questions obsolete. Q874, Q883, Q891, Q892: a chat wait cleared (the worker answered by its
# starter, or stopped) left its `info` question open for hours, and the owner answered a dead one.
WAIT_CAUSES = {"permission": "access-click", "chat": "info"}


def _clear_blocked(state, args, crew, now):
    closed = {a.get("id") for a in state.answers() if a.get("answer") in CLOSING}
    ended, out = [], {}
    # `claude agents --json` runs before the board lock, never under it: only a permission
    # wait asks it, a chat wait clears without it
    seen = _row_named(state.board().get("sessions") or [], args.name) or {}
    seen_blocked = seen.get("blocked") if isinstance(seen.get("blocked"), dict) else {}
    prompt_stands = None
    if seen_blocked.get("kind") == "permission":
        prompt_stands = _on_permission_prompt(_row_named(_agent_rows(), args.name))

    def mutate(board):
        line = _row_named(board.get("sessions") or [], args.name)
        blocked = line.get("blocked") if line else None
        if not isinstance(blocked, dict):
            return UNCHANGED
        if blocked.get("kind") == "permission" and prompt_stands is not False:
            if prompt_stands is None:  # it became a permission wait after the read above
                raise BoardError(
                    f"board.py blocked: {args.name} changed meanwhile; run --clear again"
                )
            raise BoardError(
                f"board.py blocked: {args.name} is still blocked on a permission prompt; "
                "--clear waits until it is answered"
            )
        key = _line_key(line, crew)
        ended.append(_apply_wait(line, "", crew, now))  # before the del: the row keeps its key
        del line["blocked"]
        line["updated_at"] = now.strftime(MINUTE_FMT)  # a rewritten line is not stale
        obsolete = []
        cause = WAIT_CAUSES.get(blocked.get("kind"))
        if cause:
            reason = _resolved_label(crew, now)
            for item in board.get("owner_queue") or []:
                if (
                    isinstance(item, dict)
                    and item.get("session") == args.name
                    and item.get("cause") == cause
                    and not item.get("obsolete")
                    and item.get("id") not in closed
                    and str(item.get("ts") or "") >= str(blocked.get("since") or "")
                ):
                    item["obsolete"] = reason
                    obsolete.append(item.get("id"))
        since = blocked.get("since")
        try:
            start = datetime.strptime(str(since), ISO_FMT).replace(tzinfo=timezone.utc)
            duration = int((now - start).total_seconds())
        except ValueError:
            duration = None
        out.update(
            cleared=args.name,
            kind=blocked.get("kind"),
            key=key,
            since=since,
            duration_s=duration,
            obsolete=obsolete,
        )
        return out

    result = state.write_board(mutate, after=lambda _r: _log_waits(state, ended))
    if result is UNCHANGED:
        print(f"board.py blocked: {args.name} carries no wait to clear")
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_answer(state, args, crew, now):
    _text_file(args, "quote", "answer")
    if args.id not in state.ids():
        raise BoardError(
            f"board.py answer: {args.id} is in neither owner_queue nor news of {state.board_path}"
        )
    closed = state.closing_answer(args.id)
    if closed is not None:
        state.append_question(
            {
                "id": args.id,
                "ts": _iso(now),
                "outcome": "duplicate-answer",
                "answer": args.kind,
                "session": args.session,
                "closed_by": closed.get("answer"),
            }
        )
        print(
            f"board.py answer: {args.id} is closed by {closed.get('answer')}; recorded as a "
            "duplicate, nothing runs again (a new question takes a new id)"
        )
        return 0
    line = state.append_answer(args.id, args.kind, args.session, via=args.via, quote=args.quote)
    print(json.dumps(line, ensure_ascii=False))
    return 0


def cmd_path(state, args, _crew, _now):
    """Print the board file a verb writes; --crew-only: the crew's own board (its `board.file` or a
    `state_dir` of its own), exit 1 when it resolves to the default board."""
    if args.crew_only:
        default = Path(DEFAULT_BOARD).expanduser()
        named = crew_mod.resolve_board(Path.cwd(), default=str(default))
        if named == default:
            return 1
        print(named.resolve())
        return 0
    print(state.board_path.resolve())
    return 0


def question_status(state, qid, board=None, logs=None):
    """(status, queue item or None, log lines, answer lines) of one question: the one definition
    of "open" that `show`, `withdraw`, `close-merged` and `bundle` read; the pane's `isClosed`
    (hooks/board/board.ts) mirrors it. `status` is `answered: <kind>` after an Accept, Deny or
    Withdraw, `withdrawn`/`superseded`, `open` while in `owner_queue`, else the last log outcome
    that took it off (`closed`, `replaced`, `pruned`) or `off the board`; None for an id the board
    and its logs never had. `logs` is (questions, answers) read once by a caller that asks for
    many ids."""
    board = state.board() if board is None else board
    questions, every_answer = logs if logs is not None else (state.questions(), state.answers())
    item = next(
        (q for q in board.get("owner_queue") or [] if isinstance(q, dict) and q.get("id") == qid),
        None,
    )
    lines = [q for q in questions if isinstance(q, dict) and q.get("id") == qid]
    answers = [a for a in every_answer if isinstance(a, dict) and a.get("id") == qid]
    if item is None and not lines and not answers:
        return None, None, [], []
    closing = [a for a in answers if a.get("answer") in CLOSING]
    gone = [q for q in lines if q.get("outcome") in GONE]
    off = [q for q in lines if q.get("outcome") in OFF_BOARD]
    if closing:
        status = f"answered: {closing[0]['answer']}"
    elif gone:
        status = gone[-1]["outcome"]
    elif item is not None:
        status = "open"
    elif off:
        status = off[-1]["outcome"]
    else:
        status = "off the board"
    return status, item, lines, answers


def cmd_show(state, args, _crew, _now):
    """One question as every session sees it: the open item (or its posted line), its answers
    from the answers file and its status (`question_status`); exit 1 for an id the board never had."""
    qid = args.id
    status, item, lines, answers = question_status(state, qid)
    if status is None:
        raise BoardError(f"board.py show: {qid} is in neither owner_queue nor the logs")
    posted = next((q for q in lines if q.get("outcome") == "posted"), None)
    question = dict(item or posted or {"id": qid})
    question.pop("reader", None)
    question.pop("outcome", None)
    print(
        json.dumps(
            {**question, "status": status, "answers": answers}, ensure_ascii=False, indent=1
        )
    )
    return 0


def default_board(start=None):
    """The board file a verb without --board writes: the crew's `board.file` for `start` (default
    the cwd), else DEFAULT_BOARD (`crew.resolve_board`)."""
    return crew_mod.resolve_board(start or Path.cwd(), default=DEFAULT_BOARD)


def _key_failure(crew, key, verb):
    key_rx = (crew.get("naming") or {}).get("key") or crew_mod.DEFAULTS["naming"]["key"]
    if not re.fullmatch(key_rx, key):
        return [f"board.py {verb}: --key {key!r} does not match naming.key {key_rx}"]
    return []


def _is_plan_slug(crew, key):
    """A plan slug in place of a ticket key; one that upper-cased is a key (`proj-12`) is a typo."""
    if not re.fullmatch(PLAN_SLUG, key):
        return False
    return bool(_key_failure(crew, key.upper(), "ask"))


def _ask_extras(args, crew):
    """The optional fields of a question: `kind: task`, `source`, `owner`, and `to` and `label`
    for a human on another machine (`_remote_target`)."""
    extras = {}
    remote = _remote_target(args, crew)
    if remote is not None:
        extras["to"] = remote[0]
        extras["to_name"] = remote[1]["name"]
        extras["label"] = board_humans.question_label(crew, remote[0])
    if args.ask_kind == "task":
        extras["kind"] = "task"
    if args.source and args.source.strip():
        extras["source"] = args.source.strip()
    owner = _key_owner(crew, args.owner, args.component)
    if owner:
        extras["owner"] = owner
    return extras


def _take_off(board, qid, key=None):
    """Remove the open question `qid` (on `key`) from the queue for `ask --replace`; [] without
    one. A question on another key is refused: a mistyped id never drops an unrelated question."""
    if not qid:
        return []
    queue = board.get("owner_queue") or []
    old = [q for q in queue if isinstance(q, dict) and q.get("id") == qid]
    if not old:
        raise BoardError(f"board.py ask: --replace {qid}: no open question with that id")
    if key and old[0].get("key") != key:
        raise BoardError(
            f"board.py ask: --replace {qid}: that question is on {old[0].get('key')!r}, not {key!r}"
        )
    board["owner_queue"] = [q for q in queue if q not in old]
    return [qid]


def _same_key(state, fields, replacing, distinct=False):
    """The open questions on the question's key (not the one `--replace` names): one with the
    same cause, PR and `--to` human is a duplicate and refuses the ask with one
    `duplicate` line in board-questions.jsonl, unless `distinct` (`--distinct`: the asker says it
    is another question); every other one draws one stderr warning each."""
    key, cause = fields["key"], fields["cause"]
    for q in state.board().get("owner_queue") or []:
        if not isinstance(q, dict) or q.get("key") != key or q.get("id") == replacing:
            continue
        qid, text = q.get("id"), str(q.get("ask") or "")[:80]
        same = ("cause", "pr_url", "to")
        if not distinct and all(q.get(f) == fields.get(f) for f in same):
            state.append_question({**fields, "outcome": "duplicate", "of": qid})
            raise BoardError(
                f"board.py ask: refused: {qid} on {key} (cause {cause}) is still open ({text!r}); "
                f"wait for its answer, ask anew with `--replace {qid}`, or add `--distinct` "
                "when this is another question on the same key and cause"
            )
        print(
            f"board.py ask: warning: {qid} on {key} is still open ({text!r}); this posts a "
            f"second question — `--replace {qid}` replaces it",
            file=sys.stderr,
        )


CHECK_BUCKETS = (
    ("pass", "green"),
    ("fail", "red"),
    ("cancel", "cancelled"),
    ("pending", "pending"),
    ("skipping", "skipped"),
)


def _required_checks(pr_url):
    """One line with the state of the PR's required checks (`gh pr checks --required`): the
    count per bucket, the names of every one not green or skipped. gh exits non-zero on a red
    or pending check, so its JSON is read whatever the exit; a failure says why."""
    argv = ["gh", "pr", "checks", *_gh_argv(pr_url), "--required", "--json", "name,bucket"]
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=GH_TIMEOUT, check=False
        )
    except FileNotFoundError:
        return "required checks: unknown (gh not found)"
    except subprocess.TimeoutExpired:
        return f"required checks: unknown (gh ran past {GH_TIMEOUT} s)"
    try:
        checks = json.loads(done.stdout)
    except ValueError:
        checks = None
    if not isinstance(checks, list):
        if "no required checks" in done.stderr:
            return "required checks: none reported by gh"
        why = (done.stderr.strip().splitlines() or [f"exit {done.returncode}"])[-1]
        return f"required checks: unknown ({why})"
    if not checks:
        return "required checks: none reported by gh"
    parts = []
    for bucket, word in CHECK_BUCKETS:
        names = [
            str(c.get("name")) for c in checks if isinstance(c, dict) and c.get("bucket") == bucket
        ]
        if names:
            shown = "" if bucket in ("pass", "skipping") else f" ({', '.join(names)})"
            parts.append(f"{len(names)} {word}{shown}")
    return "required checks: " + ", ".join(parts)


def _key_owner(crew, owner, component):
    """The member name that owns the question's subject: `--owner` (a member name or slug), else
    the member whose `components` holds `--component`; None when neither is given. An unknown
    name or component is a refusal (`BoardError`)."""
    if owner:
        found = crew_mod.member(crew, owner.strip())
        if found is None:
            raise BoardError(f"board.py ask: --owner {owner!r} is no crew member")
        return str(found[1].get("name") or found[0])
    if component:
        want = component.strip().lower()
        for slug, entry in crew_mod.members(crew).items():
            if want in [str(c).lower() for c in entry.get("components") or []]:
                return str(entry.get("name") or slug)
        raise BoardError(f"board.py ask: --component {component!r} belongs to no crew member")
    return None


NO_STORY_KEY = (
    "board.py ask: a question without a story (a docs PR, an infra apply) names a lower-case "
    "slug as --key, e.g. --key docs-merge or --key infra-apply, with --pr for the PR it is about"
)


def _ask_failures(args, crew):
    failures = []
    for field in ASK_FIELDS:
        value = getattr(args, field)
        if value is None or not value.strip():
            failures.append(f"board.py ask: missing --{field.replace('_', '-')}")
            if field == "key":
                failures.append(NO_STORY_KEY)
    key = (args.key or "").strip()
    if key and not _is_plan_slug(crew, key):
        failures += _key_failure(crew, key, "ask")
        if failures and failures[-1].startswith("board.py ask: --key"):
            failures.append(NO_STORY_KEY)
    if args.cause and args.cause.strip() and args.cause.strip() not in CAUSES:
        near = _closest(args.cause, CAUSES)
        failures.append(
            f"board.py ask: --cause {args.cause!r} is not one of {', '.join(CAUSES)}"
            + (f"; corrected: --cause {near}" if near else "")
        )
    return failures


def _pr_arg_refusal(ref, cause, one_way):
    """The refusal of a question's `--pr`/`--one-way` before any `gh` call, or None."""
    if one_way and cause != "merge-go":
        return "board.py ask: --one-way belongs to a merge-go question"
    if not ref:
        return (
            "board.py ask: a merge-go question needs --pr <ref>" if cause == "merge-go" else None
        )
    if not (_PR_URL.match(ref) or _PR_QUALIFIED.match(ref) or ref.isdigit()):
        return f"board.py ask: PR {ref} is no URL, <owner>/<repo>#<n> or number"
    return None


def _pr_failure(args):
    """(the open PR's URL, None) or (None, the refusal) for a question's `--pr`; (None, None)
    when the question names no PR and needs none."""
    ref = (args.pr or "").strip()
    refusal = _pr_arg_refusal(ref, (args.cause or "").strip(), args.one_way)
    if refusal or not ref:
        return None, refusal
    pr, failure = _view_pr(ref, None)
    if failure:
        return None, f"board.py ask: {failure}"
    if pr.get("state") != "OPEN":
        state = pr.get("state") or "not open"
        return None, f"board.py ask: PR {ref} is {state}; a question on a PR needs an open one"
    return str(pr.get("url") or ref), None


def _reader_verdict(answer):
    """The reason to return the question, or None when the reader passed it."""
    reasons = []
    if not str(answer.get("decides") or "").strip():
        reasons.append("reader cannot tell what is decided")
    if not str(answer.get("on_yes") or "").strip():
        reasons.append("reader cannot tell what happens on yes")
    form = answer.get("form") or []
    if not isinstance(form, list):
        form = [form]
    reasons += [str(f).strip() for f in form if str(f).strip()]
    return "; ".join(reasons) or None


def _is_return_note(note):
    return isinstance(note, str) and note.startswith(RETURN_PREFIX)


def _remote_target(args, crew):
    """(slug, entry) of the human `--to` names on another machine, None for a local ask; a
    refusal (`BoardError`) for an unknown human, this session's own or a key that is no ticket."""
    to = (getattr(args, "to", None) or "").strip().lower()
    if not to:
        return None
    every = crew_mod.humans(crew)
    if not crew_mod.several_humans(crew) or to not in every:
        raise BoardError(f"board.py ask: --to {to!r} is no human of the crew ({', '.join(every)})")
    me = crew_mod.current_human(crew)
    if me is not None and me[0] == to:
        return None  # the local human: the question goes to this board as ever
    if _key_failure(crew, (args.key or "").strip(), "ask"):
        raise BoardError("board.py ask: --to asks on a ticket: --key must be a ticket key")
    return to, every[to]


def _on_hold_refusal(state, args, crew):
    """A merge-go in a crew with humans reads the ticket's status first: a story another machine
    put On Hold gets no merge question. `CARRY` while the session has to read it."""
    if args.cause != "merge-go" or not _status_bus(crew):
        return None
    if _key_failure(crew, (args.key or "").strip(), "ask"):
        return None  # a plan slug has no ticket yet
    ticket = _reads(args, crew).ticket(args.key.strip())
    if ticket is None:
        return CARRY
    found = state_of_status(crew, ticket.get("status"))
    if found is None:
        return (
            f"board.py ask: refused: {args.key} has the status {ticket.get('status')!r}, which no "
            "board.states entry maps; a merge-go needs the story's state (map the status in "
            "crew.json board.states, or move the ticket)"
        )
    if found == "on_hold":
        return (
            f"board.py ask: refused: {args.key} is {ticket.get('status')} on the ticket; a story "
            "on hold gets no merge-go (ask its owner why first)"
        )
    return None


def _ask_gate(state, args, crew):
    """The field check, the on-hold read of a merge-go and the PR check, before any write:
    the PR url, or `CARRY` while the session has to read the ticket; a refusal raises."""
    failures = _ask_failures(args, crew)
    if failures:
        raise BoardError("\n".join(failures))
    held = _on_hold_refusal(state, args, crew)
    if held is CARRY:
        return CARRY
    if held:
        raise BoardError(held)
    pr_url, refusal = _pr_failure(args)
    if refusal:
        raise BoardError(refusal)
    return pr_url


REPEAT_WINDOW = timedelta(hours=1)
ANSWER_TO = ("coordinator", "asker")
# A span the shell emptied: `x` inside double quotes ran as a command and left nothing behind.
_MANGLED = re.compile(r"[^\s.!?:] {2,}\S|\S [.,;:!?)](?:\s|$)|\(\s*\)")
MANGLED_HINT = (
    "the text looks shell-mangled (an empty span where a `code span` likely stood: the shell ran "
    "it inside double quotes); pass the text with --text-file <path>, or --text-file - with a "
    "quoted heredoc (<<'EOF') on stdin"
)


def _mangled(*texts):
    """MANGLED_HINT on its own line when one of the texts shows an emptied span, else ''."""
    return f"\n{MANGLED_HINT}" if any(_MANGLED.search(t or "") for t in texts) else ""


def _text_file(args, field, verb):
    """`--text-file <path>` (or `-` for stdin) fills `field`; giving both is refused."""
    path = getattr(args, "text_file", None)
    if not path:
        return
    if (getattr(args, field) or "").strip():
        raise BoardError(
            f"board.py {verb}: give the text once: --{field} or --text-file, not both", code=2
        )
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise BoardError(
            f"board.py {verb}: --text-file {path}: unreadable ({exc})", code=2
        ) from None
    setattr(args, field, text.strip())


def _asked_text(line):
    """The asker's own text of a posted question: its `ask` without the appended checks line."""
    asked, checks = str(line.get("ask") or ""), line.get("checks")
    if checks and asked.endswith(f"\n{checks}"):
        return asked[: -len(checks) - 1]
    return asked


def _repeat_of(state, fields, now):
    """The id of an open question this session posted with the same text, key, cause,
    recommendation and `--to` within REPEAT_WINDOW, else None: a retry after an unread success
    returns the first question instead of a second one; a re-ask after a withdraw or an answer
    posts anew."""
    board = state.board()
    logs = (state.questions(), state.answers())
    for line in reversed(logs[0]):
        if not isinstance(line, dict) or line.get("outcome") != "posted":
            continue
        ts = _parse_ts(line.get("ts"))
        if line.get("session") != fields["session"] or ts is None or now - ts > REPEAT_WINDOW:
            continue
        same = all(
            str(line.get(f) or "").strip() == str(fields.get(f) or "").strip()
            for f in ("key", "cause", "recommendation", "to")
        )
        if not same or _asked_text(line).strip() != fields["ask"].strip():
            continue
        if question_status(state, line.get("id"), board, logs)[0] == "open":
            return line.get("id")
    return None


_project_config = crew_mod.project_config


def _asker_stamp(session, env=None, cwd=None, crew=None):
    """Who receives the answer (docs/board.md § Delivery): `asker_id` (the asking session's id),
    `starter` (the launcher marker's, so a gone worker's answer reaches its starter), both only
    when `session` is the caller itself (a coordinator asking for another session stamps
    neither), and `answer_to: asker` unless `board.answer_to` is `coordinator`. The crew's value
    beats the asking repo's `.weside/config.json`, so a companion asks the same way from any repo;
    an unknown value warns and keeps the default, `asker`."""
    env = os.environ if env is None else env
    stamp = {}
    try:
        own = own_session_name(env, verb="ask")[0]
    except BoardError:
        own = None
    if own is not None and _same_session(own, session):
        if env.get("CLAUDE_CODE_SESSION_ID"):
            stamp["asker_id"] = env["CLAUDE_CODE_SESSION_ID"]
        marker = wl.read_marker(cwd or Path.cwd()) or {}
        if isinstance(marker.get("starter"), str) and marker["starter"].strip():
            stamp["starter"] = marker["starter"].strip()
    crew_value = ((crew or {}).get("board") or {}).get("answer_to")
    where = "crew.json" if crew_value else ".weside/config.json"
    value = crew_value or (_project_config(cwd).get("board") or {}).get("answer_to") or "asker"
    if value not in ANSWER_TO:
        print(
            f"board.py ask: warning: board.answer_to {value!r} in {where} is not one "
            f"of {', '.join(ANSWER_TO)}; the answer goes to the asker",
            file=sys.stderr,
        )
        value = "asker"
    if value == "asker":
        stamp["answer_to"] = "asker"
    return stamp


def _print_ask(qid, outcome, ops=()):
    """The one JSON object `ask` prints on stdout; what the session still carries rides in it."""
    out = {"id": qid, "outcome": outcome}
    if ops:
        out["carry"] = [op.as_json() for op in ops]
    print(json.dumps(out, ensure_ascii=False))
    if ops:
        print(_carry_note(len(ops)), file=sys.stderr)


def _cold_read(state, base, asked, fields, crew):
    """(the reader's raw verdict, the reason to return the question or None). The reader judges
    the asker's text alone: the checks line is the tool's, in English, and made the verdict on a
    question in another language unstable."""
    labels = crew.get("labels") or {}
    question = {
        "ask": asked,
        "recommendation": fields["recommendation"],
        "key_title": fields["key_title"],
        "question_label": crew.get("question_label") or "QUESTION",
        "recommendation_label": labels.get("recommendation") or "Recommendation",
    }
    try:
        answer = cold_reader.read(question)
    except cold_reader.ReaderError as exc:
        # A reader that cannot run never holds a question back: it is posted unread, and the
        # log line says so (`reader: {"error": …}`).
        print(f"board.py ask: reader-error: {exc}; posted unread", file=sys.stderr)
        return {"error": str(exc)}, None
    return {k: answer.get(k) for k in ("decides", "on_yes", "form")}, _reader_verdict(answer)


def _repeated(state, args, now):
    """Fill `--text-file` and the default `--session`, then answer a retry: True when this
    session posted the same text within REPEAT_WINDOW and the first id was printed."""
    _text_file(args, "ask", "ask")
    if not (args.session or "").strip():
        args.session = own_session_name(verb="ask")[0]
    if args.replace or not (args.session or "").strip() or not (args.ask or "").strip():
        return False
    session = args.session.strip()
    fields = {f: (getattr(args, f) or "") for f in ("key", "cause", "recommendation", "ask")}
    fields["to"] = (getattr(args, "to", None) or "").strip().lower()
    first = _repeat_of(state, {**fields, "session": session}, now)
    if not first:
        return False
    state.append_question({"id": first, "ts": _iso(now), "outcome": "repeat", "session": session})
    print(
        f"board.py ask: {first} holds this text from this session already; nothing new was posted",
        file=sys.stderr,
    )
    _print_ask(first, "repeat")
    return True


def cmd_ask(state, args, crew, now):
    if _repeated(state, args, now):
        return 0
    try:
        pr_url = _ask_gate(state, args, crew)
    except BoardError as exc:
        raise BoardError(f"{exc}{_mangled(args.ask, args.recommendation)}", exc.code) from None
    if pr_url is CARRY:
        return _carry_reads("ask", [], [args.key.strip()])

    fields = {f: getattr(args, f).strip() for f in ASK_FIELDS}
    if args.urgent:
        fields["urgent"] = True
    if pr_url:
        fields["pr_url"] = pr_url
    if args.one_way and args.one_way.strip():
        fields["one_way"] = args.one_way.strip()
    fields.update(_ask_extras(args, crew))
    _same_key(state, {"ts": _iso(now), **fields}, args.replace, args.distinct)
    asked = fields["ask"]
    if fields["cause"] == "merge-go":
        fields["checks"] = _required_checks(pr_url)
        fields["ask"] = f"{fields['ask']}\n{fields['checks']}"
    fields.update(_asker_stamp(fields["session"], crew=crew))
    base = {"ts": _iso(now), **fields}
    reader, reason = _cold_read(state, base, asked, fields, crew)
    session = fields["session"]

    def asker_lines(board):
        for line in board.get("sessions") or []:
            if isinstance(line, dict) and line.get("name") == session:
                yield line

    if reason is not None:
        text = f"{RETURN_PREFIX}{session}: {reason}"

        def returned(board):
            # Only an empty note or an earlier return is replaced; another note stays. The asker
            # has the return in its exit and its line, the log in board-questions.jsonl: the
            # owner's news gets nothing.
            for line in asker_lines(board):
                if not str(line.get("note") or "").strip() or _is_return_note(line["note"]):
                    line["note"] = text

        state.write_board(
            returned,
            after=lambda _r: state.append_question(
                {**base, "outcome": "returned", "reason": reason, "reader": reader}
            ),
        )
        raise BoardError(f"board.py ask: {text}{_mangled(asked, fields['recommendation'])}")

    replaced = []

    def posted(board):
        for line in asker_lines(board):
            if _is_return_note(line.get("note")):
                del line["note"]
        replaced.extend(_take_off(board, args.replace, args.key))
        qid = state.next_id("Q", board)
        item = {"id": qid, **fields, "since": crew_mod.today(now=now), "ts": base["ts"]}
        board.setdefault("owner_queue", []).append(item)
        return qid

    def log_posted(qid):
        for old in replaced:
            state.append_question({"id": old, "ts": base["ts"], "outcome": "replaced", "by": qid})
        state.append_question({"id": qid, **base, "outcome": "posted", "reader": reader})

    qid = state.write_board(posted, after=log_posted)
    _print_ask(qid, "posted", _remote_ops(args, crew, fields))
    return 0


def _remote_ops(args, crew, fields):
    """The comment and the label that carry an `ask --to` question to its ticket; [] local."""
    if not fields.get("to"):
        return []
    adapter = _adapter(args, crew)
    name = crew_mod.humans(crew)[fields["to"]]["name"]
    text = board_humans.question_comment(crew, name, fields["ask"], fields["recommendation"])
    return adapter.comment(fields["key"], text) + adapter.label(fields["key"], fields["label"])


# --- several humans: signals, claims (docs/board.md § Several humans) -----------------------


def _reads(args, crew):
    """The adapter, over the reads the session handed back with `--input FILE`."""
    adapter = _adapter(args, crew)
    path = getattr(args, "input", None)
    if not path:
        return adapter
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BoardError(
            f"board.py {args.verb}: --input {path}: unreadable ({exc})", code=2
        ) from None
    if not isinstance(data, dict):
        raise BoardError(f"board.py {args.verb}: --input {path}: needs an object", code=2)
    return ticket_adapter.FileReads(adapter, data)


def _me(crew, verb):
    try:
        found = crew_mod.current_human(crew)
    except crew_mod.CrewError as exc:
        raise BoardError(f"board.py {verb}: {exc}") from None
    if found is None:
        raise BoardError(
            f"board.py {verb}: several humans and none is this session's: set WE_HUMAN=<slug> "
            "or git config user.email to one of humans.*.email"
        )
    return found


def _carry_reads(verb, searches, keys):
    _print_carry(ticket_adapter.read_ops(searches, keys))
    print(
        f"board.py {verb}: carry the reads with your ticketing tool, then run it again with "
        '--input FILE ({"hits": {state: [key or {key, changed}]}, "tickets": {key: {status, '
        "labels, comments}}})",
        file=sys.stderr,
    )
    return 0


def _scope_guard(crew, wanted):
    """A signal search needs `board.jql_scope`: without it the query reads every project."""
    if wanted and not str((crew.get("board") or {}).get("jql_scope") or "").strip():
        raise BoardError(
            "board.py signals: refused: board.jql_scope is unset, so a signal query would read "
            'every project of the ticketing system; set it in crew.json (e.g. "project = ABC")'
        )


def cmd_signals(state, args, crew, now):
    slug, entry = _me(crew, "signals")
    mine = set(entry["runs"])
    adapter = _reads(args, crew)
    wanted = [sig for sig in (crew.get("board") or {}).get("signals") or [] if sig["role"] in mine]
    _scope_guard(crew, wanted)
    board = state.board()
    remote = [  # only open questions: an Accept or Deny ends the read-back
        q for q in open_questions(state, board)[0] if q.get("to") and q.get("to") != slug
    ]
    hits, searches, tickets, keys = [], [], {}, []
    for sig in wanted:
        jql = board_humans.signal_jql(crew, sig["state"], sig["jql_window"])
        found = adapter.search(sig["state"], jql)
        if found is None:
            searches.append((sig["state"], jql))
        else:
            hits += [(sig, h) for h in found if isinstance(h, dict) and h.get("key")]
    for q in remote:
        if q["key"] not in tickets:
            found = adapter.ticket(q["key"])
            if found is None:
                keys.append(q["key"])
            tickets[q["key"]] = found
    if searches or keys:
        return _carry_reads("signals", searches, sorted(set(keys)))
    rows = _read_jsonl(state.signals_path)
    seen = {row.get("id") for row in rows}
    every = crew_mod.humans(crew)
    lines = []

    def is_new(sig, hit):
        """Once per key, state and change time; a hit without one counts again only after a
        whole `jql_window` past the last signal of its key and state (a later selection)."""
        stem = f"{hit['key']}:{sig['state']}:"
        if hit.get("changed"):
            return stem + str(hit["changed"]), stem + str(hit["changed"]) not in seen
        window = _window(sig["jql_window"])
        recent = [
            _parse_ts(r.get("ts"))
            for r in rows
            if str(r.get("id") or "").startswith(stem) and r.get("kind") == "signal"
        ]
        fresh = any(ts and now - ts < window for ts in recent)
        return f"{stem}@{_iso(now)}", not fresh and f"{stem}@{_iso(now)}" not in seen

    def mutate(board):
        added = []
        for sig, hit in hits:
            sid, new = is_new(sig, hit)
            if not new:
                continue
            seen.add(sid)
            rows.append({"id": sid, "kind": "signal", "ts": _iso(now)})
            status = (crew.get("board") or {}).get("states", {}).get(sig["state"], sig["state"])
            item = {
                "id": state.next_id("S", board),
                "kind": "todo",
                "title": f"{hit['key']} → {status} (signal for {sig['role']})",
                "ts": _iso(now),
                "for": sig["role"],
                "key": hit["key"],
            }
            board.setdefault("news", []).append(item)
            added.append({"id": sid, "kind": "signal", "news": item["id"], "ts": _iso(now)})
            lines.append(f"signal {item['id']}: {item['title']}")
        return added or UNCHANGED

    def log(added):
        for row in added:
            _append_jsonl(state.signals_path, row)

    state.write_board(mutate, after=log)
    for q in remote:
        lines += _read_back(state, q, tickets.get(q["key"]) or {}, every, seen, now, crew)
    for line in lines:
        print(line)
    if not lines:
        print("signals: nothing new")
    return 0


def _window(text):
    """A `jql_window` (`35m`, `4h`, `2d`) as a timedelta."""
    unit = {"m": "minutes", "h": "hours", "d": "days"}[text[-1]]
    return timedelta(**{unit: int(text[:-1])})


def _read_back(state, q, ticket, every, seen, now, crew):
    """The answer lines for one question sent to another human, each once (board-signals.jsonl)."""
    human = q["to"]
    asked = _parse_ts(q.get("ts")) or now
    out = []
    found = board_humans.replies(ticket, asked, human, every, crew)
    for reply in found:
        rid = f"{q['id']}:reply:{reply['at']}"
        if rid in seen:
            continue
        seen.add(rid)
        _answer_from_ticket(state, q, reply["kind"], reply["quote"], reply["by"], now)
        _append_jsonl(state.signals_path, {"id": rid, "kind": "answer", "ts": _iso(now)})
        out.append(f"answer {q['id']}: {reply['kind']} from {reply['by']} on {q['key']}")
    rid = f"{q['id']}:label-off"
    label = q.get("label")
    labels = ticket.get("labels")  # None: the read gave no labels, so none counts as removed
    if (
        not found
        and label
        and isinstance(labels, list)
        and label not in labels
        and rid not in seen
    ):
        seen.add(rid)
        quote = f"label {label} removed on {q['key']} without a reply"
        _answer_from_ticket(state, q, "update", quote, human, now)
        _append_jsonl(state.signals_path, {"id": rid, "kind": "answer", "ts": _iso(now)})
        out.append(f"answer {q['id']}: update ({quote})")
    return out


def _answer_from_ticket(state, q, kind, quote, human, now):
    stamp = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    state.append_answer(
        q["id"], kind, f"ticket {q['key']} ({human})", via="ticket", quote=quote, ts=stamp
    )


def cmd_withdraw(state, args, crew, now):
    """`withdraw <Q>` and `supersede <Q> --by <Q2>`: the asker (or the coordinator) takes its own
    open question off the board; a question asked on a ticket loses its label there too."""
    verb = "supersede" if getattr(args, "by", None) else "withdraw"
    qid = args.id
    board = state.board()
    queue = [q for q in board.get("owner_queue") or [] if isinstance(q, dict)]
    status, found, lines, _answers = question_status(state, qid, board)
    if status is None:
        raise BoardError(
            f"board.py {verb}: {qid} was never on {state.board_path} (neither owner_queue nor "
            "its logs); check the id, or --board for another crew's board"
        )
    if found is None:
        # Already off the queue (answered and pruned, closed, withdrawn): what the caller wanted
        # holds, so it says the state it found and exits 0.
        last = lines[-1] if lines else {}
        when = f", {last.get('outcome')} {last.get('ts')}" if last.get("ts") else ""
        print(f"{qid}: nothing to {verb}, it is off the queue ({status}{when})")
        return 0
    caller = _caller()
    if not _same_session(found.get("session"), caller) and not crew_mod.holds_role(
        crew, "coordinator", os.environ
    ):
        raise BoardError(
            f"board.py {verb}: {qid} was asked by {found.get('session')}, not by {caller}; "
            "only its asker or the coordinator takes it back"
            + _tell_on_refusal(state, verb, qid, found.get("session"))
        )
    if verb == "supersede":
        newer = next((q for q in queue if q.get("id") == args.by), None)
        if newer is None or args.by == qid:
            raise BoardError(
                f"board.py supersede: --by {args.by} is no other open question"
                + _tell_on_refusal(state, verb, qid, found.get("session"))
            )
    adapter = _adapter(args, crew) if found.get("to") else None

    def mutate(board):
        items = board.get("owner_queue") or []
        if not any(isinstance(q, dict) and q.get("id") == qid for q in items):
            return UNCHANGED
        board["owner_queue"] = [
            q for q in items if not (isinstance(q, dict) and q.get("id") == qid)
        ]
        return [qid]

    def log(_gone):
        outcome = "superseded" if verb == "supersede" else "withdrawn"
        line = {"id": qid, "ts": _iso(now), "outcome": outcome, "session": caller}
        if verb == "supersede":
            line["by"] = args.by
        if getattr(args, "for_", None):
            line["for"] = args.for_.strip()
        if args.reason:
            line["reason"] = args.reason.strip()
        state.append_question(line)

    state.write_board(mutate, after=log)
    done = f"superseded by {args.by}" if verb == "supersede" else "withdrawn"
    print(f"{qid}: {done}")
    if adapter is not None:
        text = f"{qid} {done}" + (f": {args.reason.strip()}" if args.reason else "")
        _print_carry(
            adapter.comment(found["key"], text) + adapter.unlabel(found["key"], found["label"])
        )
    return 0


def _absorbing(state, qid):
    """The sessions that withdrew a question of their own in favour of `qid` (`withdraw --for
    <qid>`, or `qid` named in the withdraw's reason), oldest first, each once."""
    rx = re.compile(r"(?<![A-Za-z0-9])" + re.escape(qid) + r"(?![0-9])")
    names = []
    for line in state.questions():
        if not isinstance(line, dict) or line.get("outcome") != "withdrawn":
            continue
        named = line.get("for") == qid or rx.search(str(line.get("reason") or ""))
        who = str(line.get("session") or "").strip()
        if named and who and who not in names:
            names.append(who)
    return names


def _tell_on_refusal(state, verb, qid, asker):
    """A refused supersede leaves every session that withdrew its own question for `qid`
    without its alternative: the refusal names whom the caller tells, so none decides blind."""
    if verb != "supersede":
        return ""
    names = [n for n in _absorbing(state, qid) if not _same_session(n, _caller())]
    if not names:
        return ""
    return (
        f"\nnothing was superseded: tell {', '.join(names)} at once (they withdrew their own "
        f"question for {qid}, so their option is on no board), and {asker or 'its asker'} "
        f"if the replacement should still go up"
    )


def _same_session(asker, caller):
    """The question's asker is the caller: names compared case-insensitively; an empty name or
    `unknown` (a session without a name, `_caller`) never matches."""
    a, c = (str(x or "").strip().lower() for x in (asker, caller))
    return bool(a) and a != "unknown" and a == c


def cmd_inbox(state, args, crew, now):
    """The tickets carrying this session's human's question label: the open questions to them."""
    slug, _entry = _me(crew, "inbox")
    adapter = _reads(args, crew)
    jql = board_humans.inbox_jql(crew, slug)
    found = adapter.search("inbox", jql)
    if found is None:
        return _carry_reads("inbox", [("inbox", jql)], [])
    keys = [h["key"] for h in found if isinstance(h, dict) and h.get("key")]
    label = board_humans.question_label(crew, slug)
    print(f"inbox {slug} ({label}): " + (", ".join(keys) if keys else "nothing open"))
    return 0


def cmd_reply(state, args, crew, now):
    """The answer of this session's human on the ticket: a signed comment
    (`board_humans.reply_comment`), then this human's question label off; a question to another
    human stays theirs."""
    failures = _key_failure(crew, args.key, "reply")
    if failures:
        raise BoardError("\n".join(failures))
    who = _who(crew, verb="reply")
    adapter = _adapter(args, crew)
    text = board_humans.reply_comment(who, args.kind, args.text or "")
    label = board_humans.question_label(crew, who.split("@", 1)[1])
    print(f"{args.key}: {text}")
    _print_carry(adapter.comment(args.key, text) + adapter.unlabel(args.key, label))
    return 0


def cmd_claim(state, args, crew, now):
    key = args.key
    failures = _key_failure(crew, key, "claim")
    if failures:
        raise BoardError("\n".join(failures))
    who = _who(crew, verb="claim")
    role, human = who.split("@", 1)
    session = _caller()
    adapter = _reads(args, crew)
    ticket = adapter.ticket(key)
    if ticket is None:
        return _carry_reads("claim", [], [key])
    local = [
        {"body": row.get("body"), "created": row.get("ts")}
        for row in _read_jsonl(state.claims_path)
        if row.get("key") == key
    ]
    hours = (crew.get("board") or {}).get("claim_hours") or 4
    held = board_humans.held_claims(
        ticket.get("comments") or [], crew_mod.humans(crew), board_humans.shared_accounts(crew)
    )
    live = board_humans.live_claims(held + local, now, hours)
    if args.release:
        body = f"release {who} {session}"
    else:
        others = [c for w, c in live.items() if w != (role, human, session)]
        if others:
            c = others[-1]
            raise BoardError(
                f"board.py claim {key}: refused: claimed by {c['role']}@{c['human']} "
                f"({c['session'] or 'no session'}) at {_iso(c['at'])}, live for {hours} h"
            )
        body = f"claim {who} {session}"
    _append_jsonl(state.claims_path, {"key": key, "body": body, "ts": _iso(now)})
    print(f"{key}: {body}")
    _print_carry(adapter.comment(key, body))
    return 0


def cmd_decision(state, args, crew, now):
    failures = []
    if args.area not in crew_mod.ROLE_KEYS:
        failures.append(
            f"board.py decision: area {args.area!r} is no role key "
            f"({', '.join(crew_mod.ROLE_KEYS)})"
        )
    elif not crew_mod.holds_role(crew, args.area, os.environ):
        failures.append(f"board.py decision: this session does not hold roles.{args.area}")
    if args.kind not in DECISION_KINDS:
        failures.append(
            f"board.py decision: kind {args.kind!r} is not one of {', '.join(DECISION_KINDS)}"
        )
    if not _is_plan_slug(crew, args.key):
        failures += _key_failure(crew, args.key, "decision")
    if not args.text.strip():
        failures.append("board.py decision: missing --text")
    if failures:
        raise BoardError("\n".join(failures))
    text = args.text.strip()

    def mutate(board):
        item = {
            "id": state.next_id("D", board),
            "kind": "decision",
            "title": f"{args.area} {args.kind} {args.key}: {text}",
            "ts": _iso(now),
            "by": args.area,
        }
        append_log(board, [item])
        return item

    def log(item):
        state.append_decision(
            {**item, "area": args.area, "decision": args.kind, "key": args.key, "text": text}
        )

    print(json.dumps(state.write_board(mutate, after=log), ensure_ascii=False))
    return 0


def open_questions(state, board):
    """`owner_queue` questions no Accept, Deny or Withdraw closed: (open, obsolete). Open ones
    urgent first, each group oldest `since` first; obsolete ones (a resolved prompt,
    `blocked --clear`) apart."""
    logs = (state.questions(), state.answers())
    items = [
        q
        for q in board.get("owner_queue") or []
        if isinstance(q, dict)
        and isinstance(q.get("id"), str)
        and question_status(state, q["id"], board, logs)[0] == "open"
    ]
    items.sort(
        key=lambda q: (
            q.get("urgent") is not True,
            str(q.get("since") or ""),
            str(q.get("ts") or ""),
        )
    )
    return [q for q in items if not q.get("obsolete")], [q for q in items if q.get("obsolete")]


def close_merged(state, now):
    """Drop every `merge-go` question in `owner_queue` whose PR is MERGED or CLOSED, whatever its
    answer (open, accepted, the owner merging by hand) and whichever repo the PR is in (its
    `pr_url`); returns {id: (state, pr)}. `gh` runs before the board lock, never under it."""
    board = state.board()
    done = {}
    for q in board.get("owner_queue") or []:
        if not isinstance(q, dict) or q.get("cause") != "merge-go" or not q.get("pr_url"):
            continue
        if not isinstance(q.get("id"), str):
            continue
        pr, failure = _view_pr(str(q["pr_url"]), None)
        if failure is None and pr.get("state") in ("MERGED", "CLOSED"):
            done[q["id"]] = (pr["state"], str(pr.get("url") or q["pr_url"]))
    if not done:
        return {}

    def mutate(b):
        queue = b.get("owner_queue") or []
        gone = [q.get("id") for q in queue if isinstance(q, dict) and q.get("id") in done]
        if not gone:
            return UNCHANGED
        b["owner_queue"] = [q for q in queue if not (isinstance(q, dict) and q.get("id") in done)]
        return gone

    def log(gone):
        for qid in gone:
            state.append_question(
                {"id": qid, "ts": _iso(now), "outcome": "closed", "reason": f"PR {done[qid][0]}"}
            )

    gone = state.write_board(mutate, after=log)
    return {} if gone is UNCHANGED else {qid: done[qid] for qid in gone}


def cmd_close_merged(state, _args, _crew, now):
    gone = close_merged(state, now)
    for qid, (pr_state, url) in gone.items():
        print(f"closed {qid}: PR {pr_state} {url}")
    if not gone:
        print("closed: none")
    return 0


def cmd_news(state, args, crew, now):
    """`news add`: one item for the owner at the top of `news` (the coordinator's milestones)."""
    failures = []
    if not crew_mod.holds_role(crew, "coordinator", os.environ):
        failures.append("board.py news add: only the coordinator writes the owner's news")
    title = (args.title or "").strip()
    if not title or "\n" in title:
        failures.append("board.py news add: --title is one non-empty line")
    if failures:
        raise BoardError("\n".join(failures))

    def mutate(board):
        item = {"id": state.next_id("N", board), "kind": args.kind, "title": title}
        body = (args.body or "").strip()
        if body:
            item["body"] = body
        item["ts"] = _iso(now)
        news = board.get("news") if isinstance(board.get("news"), list) else []
        board["news"] = [item, *news]
        return item

    print(json.dumps(state.write_board(mutate), ensure_ascii=False))
    return 0


def cmd_news_worker(state, args, _crew, now):
    """`news worker`: the launcher's supervisor (`scripts/worker_supervisor.py`) puts one `todo`
    item for the human: a worker's stop it could not tell its starter, a permission prompt that
    waits. The id is the supervisor's (`W-…`); an item of that id already in `news` stays as it is."""
    title = (args.title or "").strip()
    if not title or "\n" in title or not str(args.id).startswith("W-"):
        raise BoardError("board.py news worker: --id W-… and a one-line --title")

    def mutate(board):
        news = board.get("news") if isinstance(board.get("news"), list) else []
        if any(isinstance(i, dict) and i.get("id") == args.id for i in news):
            return UNCHANGED
        item = {"id": args.id, "kind": "todo", "title": title, "ts": _iso(now)}
        if (args.body or "").strip():
            item["body"] = args.body.strip()
        board["news"] = [item, *news]
        return item

    result = state.write_board(mutate)
    print("unchanged" if result is UNCHANGED else json.dumps(result, ensure_ascii=False))
    return 0


def cmd_prune(state, _args, _crew, _now):
    state.write_board(lambda _board: UNCHANGED)  # the pass inside write_board does the work
    gone = [line["id"] for line in state.last_pruned]
    print("pruned: " + (", ".join(gone) if gone else "none"))
    return 0


def cmd_bundle(state, args, crew, now):
    if not crew_mod.holds_role(crew, "coordinator", os.environ):
        raise BoardError("board.py bundle: only the coordinator bundles")
    _route(state, crew, now)
    close_merged(state, now)
    date = crew_mod.today(now=now)

    def mutate(board):
        lines = state.decisions()
        last_marker = max((i for i, d in enumerate(lines) if "bundle" in d), default=-1)
        fresh = [d for d in lines[last_marker + 1 :] if d.get("kind") == "decision"]
        open_items, obsolete = open_questions(state, board)
        open_ids = [q["id"] for q in open_items]
        escalations = [
            r
            for r in fold_escalations(state.escalations()).values()
            if r["open"] and r["stage"] == "bundle"
        ]
        if not fresh and not open_ids and not obsolete and not escalations:
            return UNCHANGED
        body = [
            f"{area}: {d.get('decision')} {d.get('key')} {d.get('text')}"
            for area in crew_mod.ROLE_KEYS
            for d in fresh
            if d.get("area") == area
        ]
        if open_items:
            body.append(
                "open: "
                + ", ".join(
                    q["id"] + (" (urgent)" if q.get("urgent") is True else "") for q in open_items
                )
            )
        if obsolete:
            body.append("obsolete: " + ", ".join(f"{q['id']} ({q['obsolete']})" for q in obsolete))
        body += [_bundle_line(r) for r in escalations]
        taken = {i.get("id") for i in board.get("news") or [] if isinstance(i, dict)}
        taken |= {d.get("bundle") for d in lines}
        bid, n = f"B-{date}", 1
        while bid in taken:
            n += 1
            bid = f"B-{date}-{n}"
        item = {
            "id": bid,
            "kind": "todo",
            "title": f"Bundle {date}: {len(fresh)} decisions · {len(open_ids)} open questions"
            + (f" · {len(escalations)} escalations" if escalations else ""),
            "body": "\n".join(body),
            "ts": _iso(now),
        }
        board.setdefault("news", []).append(item)
        return item

    def mark(item):
        state.append_decision({"bundle": item["id"], "ts": item["ts"]})

    item = state.write_board(mutate, after=mark)
    print("bundle: nothing" if item is UNCHANGED else json.dumps(item, ensure_ascii=False))
    return 0


# --- escalation: the decision story between two owners ---------------------------------------


def _parse_minute(text):
    return datetime.strptime(text, MINUTE_FMT).replace(tzinfo=timezone.utc)


def fold_escalations(events):
    """`{E<n>: record}`: each record is its `open` event updated by its later events in log order."""
    records = {}
    for e in events:
        eid, kind = e.get("id"), e.get("event")
        if kind == "open" and isinstance(eid, str) and eid not in records:
            rec = {k: v for k, v in e.items() if k != "event"}
            rec["open"] = True
            records[eid] = rec
            continue
        rec = records.get(eid)
        if rec is None or not rec["open"]:
            continue
        if kind == "route":
            for k in ("stage", "waiting_on", "since", "sla_due", "advice_from"):
                if k in e:
                    rec[k] = e[k]
        elif kind == "advise":
            rec["recommendation"] = e.get("recommendation")
        elif kind == "settle":
            rec.update(open=False, outcome=e.get("outcome"), settled_by=e.get("by"))
    return records


def _print_carry(ops):
    """The `carry:` last stdout line naming what the session still carries; nothing to carry
    prints nothing (ticket_adapter.py)."""
    if ops:
        print("carry: " + json.dumps([op.as_json() for op in ops], ensure_ascii=False))
        print(_carry_note(len(ops)), file=sys.stderr)


def _carry_note(count):
    # the row says `ticket: pending`: a board Done over a ticket still In Review went unnoticed
    # while it said `carried`
    return (
        f"board.py: the ticket is not changed yet (row `ticket: pending`): run each of the "
        f"{count} `carry:` ops with your ticketing tool, then read the ticket back and "
        "compare its status. No ticketing tool answers (its MCP server disconnected): tell "
        "your starter which keys stay unmoved; never report the move as done"
    )


def _story_text(rec):
    a, b = rec["parties"]
    return "\n".join(
        [
            f"Escalation {rec['id']} ({a}/{b}): {rec['question']}",
            f"{a}: {rec['a']} (cost: {rec['a_cost']})",
            f"{b}: {rec['b']} (cost: {rec['b_cost']})",
            f"Reversible: {'yes' if rec['reversible'] else 'no'}"
            + (f" · touches {rec['touches']}" if rec.get("touches") else ""),
            f"Waiting on: {rec['waiting_on']} since {rec['since']}, due {rec['sla_due']}",
        ]
    )


def _advice_pending(rec):
    """Whether a `--touches` record still waits on the escalation role's recommendation."""
    return bool(rec.get("advice_from")) and not rec.get("recommendation")


def _advice_id(eid):
    """The id of the escalation holder's advice item beside the human's `todo` item `E<n>`."""
    return eid + "a"


def _drop_news(board, ids):
    """Remove every news item whose id is in `ids`; returns how many went."""
    news = board.get("news") or []
    kept = [i for i in news if not (isinstance(i, dict) and i.get("id") in ids)]
    board["news"] = kept
    return len(news) - len(kept)


def _bundle_line(rec):
    line = f"escalation {rec['id']} {rec['key']}: {rec['question']}"
    if _advice_pending(rec):
        line += " (advice pending)"
    elif rec.get("recommendation"):
        line += f" (advice: {rec['recommendation']})"
    return line


def _week(since):
    year, week, _ = _parse_minute(since).isocalendar()
    return f"{year}-W{week:02d}"


def _pair_counts(records, week):
    counts = {}
    for rec in records.values():
        if _week(rec["since_open"]) == week:
            pair = "/".join(sorted(rec["parties"]))
            counts[pair] = counts.get(pair, 0) + 1
    return counts


def _count_lines(counts, week, only_warn=False):
    out = []
    for pair in sorted(counts):
        n = counts[pair]
        if only_warn and n <= PAIR_WARN_AFTER:
            continue
        out.append(f"{pair} {n} in {week}")
        if n > PAIR_WARN_AFTER:
            out.append(
                f"warning: {pair}: more than two escalations this week; "
                "the right in crew.json is drawn wrong"
            )
    return out


def _locked(state, fn):
    """`fn(board)` under the board lock with board.json left untouched; returns what `fn` returned."""
    out = []

    def mutate(board):
        out.append(fn(board))
        return UNCHANGED

    state.write_board(mutate)
    return out[0]


def _open_failures(args, crew):
    verb = "board.py escalation open"
    failures = []
    for field in OPEN_FIELDS:
        value = getattr(args, field)
        if value is None or not value.strip():
            failures.append(f"{verb}: missing --{field.replace('_', '-')}")
    parties = []
    if args.parties and args.parties.strip():
        parties = [p.strip() for p in args.parties.split(",")]
        for p in parties:
            if p not in crew_mod.ROLE_KEYS:
                failures.append(
                    f"{verb}: party {p!r} is no role key ({', '.join(crew_mod.ROLE_KEYS)})"
                )
        if len(parties) != 2 or len(set(parties)) != 2:
            failures.append(f"{verb}: --parties names two different role keys")
        elif not failures and not any(crew_mod.holds_role(crew, p, os.environ) for p in parties):
            failures.append(
                f"{verb}: this session holds neither roles.{parties[0]} nor roles.{parties[1]}"
            )
    if args.key and args.key.strip():
        failures += _key_failure(crew, args.key.strip(), "escalation open")
    if args.reversible and args.reversible.strip() not in ("yes", "no"):
        failures.append(f"{verb}: --reversible {args.reversible!r} is not yes or no")
    if args.touches is not None and args.touches not in TOUCHES:
        failures.append(f"{verb}: --touches {args.touches!r} is not one of {', '.join(TOUCHES)}")
    return failures, parties


def _adapter(args, crew):
    """The ticketing adapter, built only by the verbs that call it (`select`, `move`,
    `escalation open|settle`, `signals`, `claim`, `ask --to`) and before their first write; an unknown `board.ticketing`
    leaves every other verb working. `args.adapter_given` is the tests' FakeAdapter."""
    if args.adapter_given is not None:
        return args.adapter_given
    try:
        return ticket_adapter.adapter_for(crew)
    except ValueError as exc:
        raise BoardError(f"crew: {exc}") from None


def cmd_escalation_open(state, args, crew, now):
    failures, parties = _open_failures(args, crew)
    if failures:
        raise BoardError("\n".join(failures))
    adapter = _adapter(args, crew)
    by = next(p for p in parties if crew_mod.holds_role(crew, p, os.environ))
    wait = _wait(crew, now, ",".join(parties))

    def write(board):
        event = {
            "id": state.next_id("E", board),
            "event": "open",
            "ts": _iso(now),
            "key": args.key.strip(),
            "parties": parties,
            "by": by,
            "question": args.question.strip(),
            "a": args.a.strip(),
            "a_cost": args.a_cost.strip(),
            "b": args.b.strip(),
            "b_cost": args.b_cost.strip(),
            "reversible": args.reversible.strip() == "yes",
            "touches": args.touches,
            "stage": "self",
            **wait,
            "since_open": wait["since"],
        }
        state.append_escalation(event)
        return event

    event = _locked(state, write)
    records = fold_escalations(state.escalations())
    rec = records[event["id"]]
    print(json.dumps({k: v for k, v in rec.items() if k != "since_open"}, ensure_ascii=False))
    week = _week(rec["since_open"])
    for line in _count_lines(_pair_counts(records, week), week, only_warn=True):
        print(line)
    _print_carry(adapter.comment(rec["key"], _story_text(rec)))
    return 0


def _holder_available(crew, board):
    """Whether the `roles.escalation` holder has a board line that is not `parked` (`idle` is)."""
    slug = (crew.get("roles") or {}).get("escalation")
    if not isinstance(slug, str):
        return False
    entry = crew_mod.members(crew).get(slug) or {}
    names = {slug.lower(), str(entry.get("name") or "").strip().lower()} - {""}
    lines = [
        s
        for s in board.get("sessions") or []
        if isinstance(s, dict) and str(s.get("name") or "").strip().lower() in names
    ]
    return any(s.get("state") != "parked" for s in lines)


def _next_stage(rec, crew, board):
    """(stage, waiting_on, advice_from) a record past its `sla_due` moves to."""
    if rec["stage"] == "self":
        if rec.get("touches"):
            return "bundle", "human", "escalation"
        if _holder_available(crew, board):
            return "escalation", "escalation", None
        target = (crew.get("fallback") or {}).get("escalation") or "human_bundle"
        if target != "human_bundle":
            return "escalation", target, None
    return "bundle", "human", None


def _route(state, crew, now):
    """Move every open record past its `sla_due`; returns the route events written."""
    moved = []

    def mutate(board):
        for rec in fold_escalations(state.escalations()).values():
            if not rec["open"] or rec["stage"] == "bundle":
                continue
            if now < _parse_minute(rec["sla_due"]):
                continue
            stage, waiting_on, advice_from = _next_stage(rec, crew, board)
            event = {"id": rec["id"], "event": "route", "ts": _iso(now), "from": rec["stage"]}
            event["stage"] = stage
            event.update(_wait(crew, now, waiting_on))
            if advice_from:
                event["advice_from"] = advice_from
            moved.append((event, rec))
        if not moved:
            return UNCHANGED
        news = board.setdefault("news", [])
        for event, rec in moved:
            kind = NEWS_KIND_BY_STAGE[event["stage"]]
            if any(
                isinstance(i, dict) and i.get("id") == rec["id"] and i.get("kind") == kind
                for i in news
            ):
                continue
            # one item per id: the human's todo replaces the holder's escalation item
            news[:] = [i for i in news if not (isinstance(i, dict) and i.get("id") == rec["id"])]
            item = {
                "id": rec["id"],
                "kind": kind,
                "title": f"Escalation {rec['id']} {rec['key']}: {rec['question']}",
                "body": _story_text({**rec, **event}),
                "ts": _iso(now),
            }
            if kind == "escalation":
                item["for"] = event["waiting_on"]
            news.append(item)
            if _advice_pending({**rec, **event}):
                # the human's todo keeps id E<n>; the holder's advice signal is E<n>a
                news.append(
                    {
                        **item,
                        "id": _advice_id(rec["id"]),
                        "kind": "escalation",
                        "for": event["advice_from"],
                        "title": f"Advice {rec['id']} {rec['key']}: {rec['question']}",
                    }
                )
        return moved

    def append_all(events):
        for event, _rec in events:
            state.append_escalation(event)

    state.write_board(mutate, after=append_all)
    for event, rec in moved:
        print(f"route: {rec['id']} {rec['key']} {event['from']} → {event['stage']}")
    return moved


def cmd_escalation_route(state, args, crew, now):
    if not crew_mod.holds_role(crew, "coordinator", os.environ):
        raise BoardError("board.py escalation route: only the coordinator routes")
    _route(state, crew, now)
    return 0


def _record(state, eid, verb):
    rec = fold_escalations(state.escalations()).get(eid)
    if rec is None:
        raise BoardError(f"board.py escalation {verb}: no escalation {eid}")
    if not rec["open"]:
        raise BoardError(f"board.py escalation {verb}: {eid} is settled")
    return rec


def cmd_escalation_advise(state, args, crew, now):
    verb = "board.py escalation advise"
    rec = _record(state, args.id, "advise")
    if not crew_mod.holds_role(crew, "escalation", os.environ):
        raise BoardError(f"{verb}: only roles.escalation advises")
    if not rec.get("touches"):
        raise BoardError(f"{verb}: {args.id} asks for no advice (opened without --touches)")
    if not args.recommendation.strip():
        raise BoardError(f"{verb}: missing --recommendation")
    event = {
        "id": args.id,
        "event": "advise",
        "ts": _iso(now),
        "by": "escalation",
        "recommendation": args.recommendation.strip(),
    }

    def drop(board):
        _drop_news(board, {_advice_id(args.id)})
        return event

    state.write_board(drop, after=state.append_escalation)
    print(json.dumps(event, ensure_ascii=False))
    return 0


def _settler(rec, args, crew):
    """The role settling `rec`, or a BoardError naming who may."""
    verb, eid, stage = "board.py escalation settle", rec["id"], rec["stage"]
    if args.via == "human":
        if stage != "bundle":
            raise BoardError(f"{verb}: --via human settles only a record at stage bundle")
        if not crew_mod.holds_role(crew, "coordinator", os.environ):
            raise BoardError(f"{verb}: only the coordinator settles for the human")
        if rec.get("advice_from") and not rec.get("recommendation"):
            raise BoardError(f"{verb}: {eid} waiting for the escalation role's recommendation")
        return "human"
    if stage == "self":
        held = [p for p in rec["parties"] if crew_mod.holds_role(crew, p, os.environ)]
        if not held:
            raise BoardError(f"{verb}: {eid} is at stage self; only a party settles it")
        return held[0]
    if stage == "escalation":
        role = rec["waiting_on"]
        if not crew_mod.holds_role(crew, role, os.environ):
            raise BoardError(f"{verb}: {eid} is at stage escalation; only roles.{role} settles it")
        return role
    raise BoardError(f"{verb}: {eid} is at stage bundle; the coordinator settles it --via human")


def cmd_escalation_settle(state, args, crew, now):
    rec = _record(state, args.id, "settle")
    by = _settler(rec, args, crew)
    if not args.outcome.strip():
        raise BoardError("board.py escalation settle: missing --outcome")
    adapter = _adapter(args, crew)
    event = {
        "id": args.id,
        "event": "settle",
        "ts": _iso(now),
        "stage": rec["stage"],
        "by": by,
        "outcome": args.outcome.strip(),
    }

    def drop(board):
        _drop_news(board, {args.id, _advice_id(args.id)})
        return event

    state.write_board(drop, after=state.append_escalation)
    print(json.dumps(event, ensure_ascii=False))
    text = f"Escalation {args.id} settled at stage {rec['stage']} by {by}: {event['outcome']}"
    _print_carry(adapter.comment(rec["key"], text))
    return 0


def cmd_escalation_list(state, args, crew, now):
    verb = "board.py escalation list"
    failures = []
    if args.waiting_on is not None and args.waiting_on not in (*crew_mod.ROLE_KEYS, "human"):
        failures.append(
            f"{verb}: --waiting-on {args.waiting_on!r} is no role key "
            f"({', '.join(crew_mod.ROLE_KEYS)} or human)"
        )
    if args.stage is not None and args.stage not in STAGES:
        failures.append(f"{verb}: --stage {args.stage!r} is not one of {', '.join(STAGES)}")
    if args.waiting_on is not None:
        roles = [args.waiting_on]
    else:
        roles = [r for r in crew_mod.ROLE_KEYS if crew_mod.holds_role(crew, r, os.environ)]
        if not roles:
            failures.append(f"{verb}: this session holds no role; pass --waiting-on ROLE")
    if failures:
        raise BoardError("\n".join(failures))
    out = []
    for rec in fold_escalations(state.escalations()).values():
        if not rec["open"] or (args.stage and rec["stage"] != args.stage):
            continue
        waiting = set(str(rec.get("waiting_on") or "").split(","))
        if _advice_pending(rec):
            waiting.add(rec["advice_from"])
        if not waiting & set(roles):
            continue
        out.append(
            f"{rec['id']} {rec['key']} {'/'.join(rec['parties'])} {rec['stage']} "
            f"since {rec['since']} due {rec['sla_due']}"
            + (" (advice pending)" if _advice_pending(rec) else "")
        )
    if not out:
        where = f" at {args.stage}" if args.stage else ""
        out = [f"escalations: none waiting on {','.join(roles)}{where}"]
    print("\n".join(out))
    return 0


def cmd_escalation_count(state, args, crew, now):
    week = _week(_minute(now).strftime(MINUTE_FMT))
    lines = _count_lines(_pair_counts(fold_escalations(state.escalations()), week), week)
    print("\n".join(lines) if lines else f"escalations: none in {week}")
    return 0


# --- moves: select, move, check (docs/board.md § Moves) --------------------------------------

MOVE_STATES = ("on_hold", "backlog", "in_progress", "in_review", "in_test", "done")
GH_TIMEOUT = 30
_PR_URL = re.compile(r"^https?://[^/]+/([^/]+)/([^/]+)/pull/(\d+)(?:[/?#].*)?$")
_PR_QUALIFIED = re.compile(r"^([\w.-]+)/([\w.-]+)#(\d+)$")


class Move:
    """What an entry rule reads: the key, the target state, the repo root, the plan, the crew,
    the parsed arguments; `extra` collects the fields a passing rule adds to the row."""

    def __init__(self, state, key, target, root, plan, crew, args):
        self.state, self.key, self.target = state, key, target
        self.root, self.plan, self.crew, self.args = root, plan, crew, args
        self.extra = {}
        self.warnings = []
        self.selected = {}  # what the select comment names (plan blob)
        self.source = None  # the state the story leaves (`_source_state`)


def _toplevel(verb):
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise BoardError(f"board.py {verb}: git not runnable: {exc.strerror}") from None
    if done.returncode != 0:
        raise BoardError(f"board.py {verb}: not inside a git checkout (no toplevel)")
    return Path(done.stdout.strip())


def _rel(root, plan):
    try:
        return plan.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def rule_gate(m):
    """The Ready gate's story checks on the plan blob `plan on main` found, never on the
    checkout (a stale or missing worktree plan is not what Selected starts from)."""
    blob = m.selected.get("plan")
    try:
        if blob:
            done = subprocess.run(
                ["git", "-C", str(m.root), "cat-file", "blob", blob],
                capture_output=True,
                text=True,
                check=False,
            )
            if done.returncode != 0:
                return [f"plan blob {blob[:12]}: unreadable ({done.stderr.strip() or 'git'})"]
            failures, warnings = ready_gate.story_failures(m.plan, done.stdout)
        else:
            failures, warnings = ready_gate.story_failures(m.plan)
    except OSError as exc:
        return [f"{m.plan}: unreadable ({type(exc).__name__})"]
    m.warnings += warnings
    return failures


def rule_selector(m):
    """With several humans only the product role selects, on the machine of a human who runs
    product: the start signal is its move. The select comment's `<role>@<human>` is fixed here,
    before any write, in every crew."""
    try:
        m.selected["who"] = _who(m.crew, verb=f"select {m.key}")
    except BoardError as exc:
        return [str(exc).split("refused: ", 1)[-1]]
    if not crew_mod.several_humans(m.crew):
        return []
    role = crew_mod.role_of_session(m.crew, os.environ) or "none"
    if role != "product":
        return [f"only the product role selects (roles.product); this session is {role}"]
    human = m.selected["who"].split("@", 1)[1]
    if "product" not in crew_mod.runs(m.crew, human):
        return [f"{human} does not run product (humans.{human}.runs)"]
    return []


def _human_of(m):
    """This session's human slug for an entry rule, or the refusal line."""
    try:
        found = crew_mod.current_human(m.crew)
    except crew_mod.CrewError as exc:
        return None, str(exc)
    if found is None:
        return None, (
            "several humans and none is this session's: set WE_HUMAN=<slug> or git config "
            "user.email to one of humans.*.email"
        )
    return found[0], None


def rule_owner(m):
    """With several humans only a human who owns the state the story leaves (`owns_states`)
    moves it on; out of a running state (`crew.RUNNING_STATES`) the refusal names the question
    to its owner instead. A ticket that already stands at the target, or past Selected on a late
    `select` (`ticket_already`), leaves no state, so no owner is asked."""
    if not crew_mod.several_humans(m.crew) or m.source is None or m.extra.get("ticket_already"):
        return []
    owners = crew_mod.state_owners(m.crew, m.source)
    if not owners:
        return []
    me, failure = _human_of(m)
    if failure:
        return [failure]
    if me in owners:
        return []
    line = f"{m.key} is {m.source}, owned by {', '.join(owners)}; this session works for {me}"
    if m.source in crew_mod.RUNNING_STATES:
        line += (
            f"; a change to running work is a question to its owner: board.py ask --to "
            f"{owners[0]} --key {m.key} --cause info --session <you> --key-title <title> "
            f'--ask "<the change>" --recommendation "<yours>"'
        )
    return [line]


def rule_plan_on_main(m):
    """The plan file is on `risk.rules_from` (default `origin/main`), after the select's one
    `git fetch` (`plan_tier.fetch_origin`); its blob goes into the select comment."""
    rel = _rel(m.root, m.plan)
    ref = str((m.crew.get("risk") or {}).get("rules_from") or "origin/main")
    if rel is None:
        return [f"plan {m.plan} lies outside {m.root}"]
    # the one fetch of a select (bounded): the tier after it reads the same ref unfetched
    m.warnings += plan_tier.fetch_origin(m.root, ref, "select")
    try:
        done = subprocess.run(
            ["git", "-C", str(m.root), "rev-parse", "--verify", "-q", f"{ref}:{rel}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return [f"git not runnable: {exc.strerror}"]
    if done.returncode != 0:
        return [f"plan {rel} is not on {ref}: merge the plan first"]
    m.selected["plan"] = done.stdout.strip()
    return []


def rule_tier(m):
    """The plan-only tier from `risk.command` on `risk.rules_from`; `none` without a command."""
    rel = _rel(m.root, m.plan)
    if rel is None:
        return [f"tier not computed: the plan lies outside {m.root}"]
    result = plan_tier.plan_tier(m.crew, m.root, m.key, rel)  # fetched by `plan on main`
    m.warnings += result.warnings
    if result.failure is not None:
        return [f"tier not computed: {result.failure}"]
    m.extra["tier"] = result.line
    return []


def rule_lenses(m):
    """The `ready-<KEY>` lens verdict, green and bound to the subject hash of the plan blob on
    main (`lens_verdict.py` § Subject); the warnings a
    green panel carries (`ready_panel.warning_ok_after_rounds`) go into the row as `carried`, the
    lens holders' decisions above the round cap (`ready_panel.max_rounds`) as `decided`, a
    derived round (a verdict file of 8.10.0 or older) as `round` with its origin. A plan whose
    computed tier is T0 needs no panel (L0 §Risk tiers: lenses judge a risk plan)."""
    if str(m.extra.get("tier") or "").split()[:1] == ["T0"]:
        m.extra["panel"] = "none (T0)"
        return []
    try:
        blob = m.selected.get("plan")
        binding = {"plan_blob": blob} if blob else None
        green, lines, carried, decided = lens_verdict.check_ready(
            m.root, f"ready-{m.key}", binding
        )
    except (lens_verdict.UnusableError, OSError) as exc:
        return [f"lens verdict unreadable: {exc}"]
    if not green:
        return lines
    if carried:
        m.extra["carried"] = carried
    if decided:
        m.extra["decided"] = decided
    try:
        round_, origin = lens_verdict.round_of(m.root, f"ready-{m.key}")
    except (lens_verdict.RefusedError, lens_verdict.UnusableError, OSError) as exc:
        return [f"lens verdict unreadable: {exc}"]
    if origin is not None:
        m.extra["round"] = f"{round_} ({origin})"
    return []


def rule_reopen(m):
    trigger = (m.args.reopen or "").strip()
    if not trigger:
        return ['on_hold needs --reopen "<trigger>" (what reopens it)']
    m.extra["reopen"] = trigger
    return []


def epic_approved(status):
    """The one reading of an approved epic plan: its `status:` starts with `approved`."""
    return str(status or "").startswith("approved")


def _show(root, spec):
    """`git show <spec>` in `root`, None when absent or unreadable."""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "show", spec], capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    return done.stdout.replace("\r\n", "\n") if done.returncode == 0 else None


def _epics_on_ref(root, ref, epic):
    """(name, text) of every `docs/plans/*-epic.md` on `ref` naming `epic` (`ready_gate.names_epic`)."""
    listing = _show(root, f"{ref}:docs/plans") or ""
    hits = []
    for name in sorted(n.strip() for n in listing.splitlines()):
        if not name.endswith("-epic.md"):
            continue
        text = _show(root, f"{ref}:docs/plans/{name}")
        if text is not None and ready_gate.names_epic(ready_gate.frontmatter(text), epic):
            hits.append((name, text))
    return hits


def rule_refiner(m):
    """`select --refiner`: a refiner selects its own story only when the story's epic plan on
    `risk.rules_from` is approved (`epic_approved`), its `line:` holds the key and it carries no
    `select: owner`; every other case is the product role's select. The story's `epic:` comes from
    the plan blob `plan on main` fixed, never from the checkout."""
    if not getattr(m.args, "refiner", False):
        return []
    reason = _off_line(m)
    if reason is None:
        return []
    owner = crew_mod.holder_name(m.crew, "product")
    return [f"{reason}; product ({owner}) selects" if owner else f"{reason}; product selects"]


def _off_line(m):
    """Why the product role selects this story instead of its refiner, None when the refiner may."""
    if (m.crew.get("select") or {}).get("refiner") is False:
        return "the crew sets `select.refiner: false`"
    ref = str((m.crew.get("risk") or {}).get("rules_from") or "origin/main")
    story = _show(m.root, str(m.selected.get("plan") or "")) or ""
    epic = ready_gate.frontmatter(story).get("epic", "").strip()
    if not epic or epic == "null":
        return f"{m.key} names no `epic:`"
    hits = _epics_on_ref(m.root, ref, epic)
    if len(hits) != 1:
        found = " and ".join(name for name, _ in hits) or "none"
        return f"no single epic plan on {ref} names {epic} ({found})"
    name, text = hits[0]
    meta = ready_gate.frontmatter(text)
    status = meta.get("status", "")
    line = ready_gate.line_keys(meta)
    checks = (
        (
            not epic_approved(status),
            f"epic {epic} is not approved ({name} status: {status or 'none'})",
        ),
        (meta.get("select", "").strip() == "owner", f"epic {epic} says `select: owner` ({name})"),
        (line is None, f"epic {epic} has no `line:` ({name})"),
        (
            line is not None and m.key not in line,
            f"{m.key} is not on the finish line of {epic} ({name} line: "
            f"{', '.join(line or []) or 'empty'})",
        ),
    )
    return next((why for off, why in checks if off), None)


def rule_epic_approved(m):
    epic = (m.args.epic or "").strip()
    if not epic:
        return ["backlog needs --epic <EPIC> (Backlog = the epic is approved)"]
    hits = ready_gate.find_epic_plan(m.root / "docs" / "plans", epic)
    if not hits:
        return [f"no epic plan under docs/plans names {epic}"]
    if len(hits) > 1:
        return [
            f"{epic} is named by more than one epic plan: " + " and ".join(p.name for p, _ in hits)
        ]
    path, text = hits[0]
    status = ready_gate.frontmatter(text).get("status", "")
    if not epic_approved(status):
        return [f"epic {epic} is not approved ({path.name} status: {status or 'none'})"]
    line = ready_gate.line_keys(ready_gate.frontmatter(text))
    if line is None:
        m.warnings.append(
            f"warning: epic {epic} has no `line:` yet ({path.name}); its master draws the line, "
            "until then every key moves"
        )
    elif m.key not in line:
        product = crew_mod.holder_name(m.crew, "product") or "the product owner"
        human = str((m.crew.get("human") or {}).get("name") or "the human")
        waiting = sum(1 for is_open, _ in ready_gate.extensions(text) if is_open)
        return [
            f"{m.key} is not on the finish line of {epic} ({path.name} line: "
            f"{', '.join(line) or 'empty'}); add it under `## Extensions` of {path.name} "
            f"({waiting} open): {product} pre-sorts, {human} decides each entry (into the "
            "epic's line, a follow-up epic, or dropped)"
        ]
    m.extra["epic"] = epic
    return []


SELECT_ONLY = "use board.py select (the Ready gate, the tier and the lenses decide Selected)"


REOPENABLE = ("in_review", "in_test")  # a revert of the merged PR or a failed test reopens
FAST_FROM = (
    None,
    "backlog",
)  # the fast lane: no plan file, no Selected; the PR's diff carries the class


def rule_pulled(m):
    """In Progress is pulled from Selected, pulled with `--fast` from Backlog or from no row (the
    fast lane of L0 §Units: the story has no plan file and its PR's diff carries the risk class;
    row `via: fast`), or reopened from in_review/in_test with `--reopen "<reason>"` (the revert
    PR or the failed test)."""
    reason = (getattr(m.args, "reopen", None) or "").strip()
    if m.source in REOPENABLE:
        if not reason:
            return [
                f'in_progress from {m.source} needs --reopen "<reason>" '
                "(the revert PR or the failed test)"
            ]
        m.extra["reopen"] = reason
        return []
    if m.extra.get("ticket_already"):
        return []
    if getattr(m.args, "fast", False) and m.source in FAST_FROM:
        m.extra["via"] = "fast"
        return []
    if m.source != "selected":
        was = "no row" if m.source is None else f"its last row is {m.source}"
        return [
            f"in_progress needs the key's last row to be selected ({was}); a small story off "
            "every risk path is pulled with --fast (L0 §Units, the fast lane); from "
            f'{" or ".join(REOPENABLE)} it reopens with --reopen "<reason>"'
        ]
    return []


def rule_reviewed(m):
    if not crew_mod.maps_state(m.crew, "in_test"):
        return ["the crew maps no in_test status (crew.json board.states.in_test)"]
    if m.extra.get("ticket_already"):
        return []
    if m.source != "in_review":
        return [f"in_test needs the key to be in_review (it is {m.source or 'none'})"]
    return []


def _own_repo(root):
    done = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    url = done.stdout.strip().rstrip("/") if done.returncode == 0 else ""
    name = re.split(r"[/:]", url)[-1] if url else ""
    return name[:-4] if name.endswith(".git") else name


def _foreign_repos(m):
    """The `**Repo:**` names of the story plan's phases other than the plan's own repo."""
    try:
        text = m.plan.read_text(encoding="utf-8")
    except OSError:
        return []
    own = _own_repo(m.root)
    return sorted({p.repo for p in ready_gate.phases(text) if p.repo and p.repo != own})


def _gh_argv(ref):
    found = _PR_QUALIFIED.match(ref)
    if found:
        return [found.group(3), "-R", f"{found.group(1)}/{found.group(2)}"]
    return [ref]


# A body line that names the tickets a PR delivers: `Ticket: …`, `Refs: …`, a bundle PR's
# `**Tickets:** A-1, A-2`, or `Closes A-1` (Markdown emphasis and list marks allowed before the
# word). The word is followed by a colon or directly by a key, so a prose bullet `- Fixes the
# crash seen after A-2` links nothing.
_TICKET_LINE = re.compile(
    r"^[\s>*_#-]*(?:tickets?|refs?|closes|fixes|resolves|delivers)[*_]*"
    r"(?:\s*:.*|\s+[*_`]*[A-Za-z][A-Za-z0-9]*-\d+.*)$",
    re.IGNORECASE | re.MULTILINE,
)


def _linked(key, pr):
    """The key as a whole token in the head branch or title, or on a ticket line of the body (a
    story delivered by a bundle PR or another story's PR)."""
    rx = re.compile(r"(?<![A-Z0-9-])" + re.escape(key) + r"(?![0-9])")
    if any(rx.search(str(pr.get(f) or "")) for f in ("headRefName", "title")):
        return True
    return any(rx.search(m.group(0)) for m in _TICKET_LINE.finditer(str(pr.get("body") or "")))


def _view_pr(ref, root):
    """(the PR's JSON, None) or (None, the failure) for one `gh pr view` of `ref`."""
    argv = [
        "gh",
        "pr",
        "view",
        *_gh_argv(ref),
        "--json",
        "state,mergedAt,headRefName,title,body,url",
    ]
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=GH_TIMEOUT, check=False, cwd=root
        )
    except FileNotFoundError:
        return None, f"PR {ref}: gh not found"
    except subprocess.TimeoutExpired:
        return None, f"PR {ref}: gh ran past {GH_TIMEOUT} s"
    if done.returncode != 0:
        why = (done.stderr.strip().splitlines() or [f"exit {done.returncode}"])[-1]
        return None, f"PR {ref}: gh pr view failed: {why}"
    try:
        pr = json.loads(done.stdout)
    except ValueError:
        return None, f"PR {ref}: gh printed no JSON"
    if not isinstance(pr, dict):
        return None, f"PR {ref}: gh printed no JSON object"
    return pr, None


def rule_pr_merged_and_linked(m):
    refs = [r.strip() for r in m.args.pr or [] if r.strip()]
    if not refs:
        return ["in_review needs --pr <ref> (a merged PR linked to the key)"]
    failures, urls, foreign = [], [], None
    for ref in refs:
        if not (_PR_URL.match(ref) or _PR_QUALIFIED.match(ref) or ref.isdigit()):
            failures.append(f"PR {ref} is no URL, <owner>/<repo>#<n> or number")
            continue
        if ref.isdigit():
            foreign = _foreign_repos(m) if foreign is None else foreign
            if foreign:
                failures.append(f"PR {ref} is ambiguous: name it <owner>/<repo>#{ref} or by URL")
                continue
        pr, failure = _view_pr(ref, m.root)
        if failure:
            failures.append(failure)
        elif pr.get("state") != "MERGED":
            failures.append(f"PR {ref} is not merged")
        elif not _linked(m.key, pr):
            failures.append(f"PR {ref} is not linked to {m.key}")
        else:
            urls.append(pr.get("url") or ref)
    if not failures:
        m.extra["pr"] = urls
    return failures


# `**Not proven:** …` (Markdown bold) is the form the crew's Done comments use.
NOT_PROVEN = re.compile(r"^\**Not proven:\**\s*\S", re.MULTILINE)
DONE_VIA_ACCEPT = (
    "done needs --comment-file FILE (an acceptance comment with a `Not proven:` line); "
    "a receipts verdict reaches done only through accept.py run --run-id"
)


def rule_in_review(m):
    """Done comes from in_review, or from in_test; with an owner of in_test (several humans) only
    from in_test. `--already-fixed` (a story another merged PR already fixed) comes from any
    state but done. A ticket already Done (`ticket_already`) gets its row."""
    if m.extra.get("ticket_already"):
        return []
    was = m.source or "none"
    if getattr(m.args, "already_fixed", None):
        return [f"{m.key} is done already"] if was == "done" else []
    tested = crew_mod.several_humans(m.crew) and crew_mod.state_owners(m.crew, "in_test")
    if was not in ("in_review", "in_test"):
        line = f"last move is {was}, not {'in_test' if tested else 'in_review'}"
        if was != "done":
            line += "; a story another merged PR already fixed: --already-fixed <owner>/<repo>#<n>"
        return [line]
    if tested and was != "in_test":
        return [f"{m.key} is in_review: Done comes from in_test (owned by {', '.join(tested)})"]
    return []


def _ac_numbers(values):
    return sorted({str(v) for v in values or []}, key=lambda n: (len(n), n))


def verdict_failures(entry, key):
    """Why a verdict entry does not prove `key` Done: the core classified it, the board re-checks
    the invariant so that no hand-edited file sets Done (docs/board.md § Acceptance)."""
    if not isinstance(entry, dict) or entry.get("key") != key:
        return [f"the verdict has no entry for {key}"]
    if entry.get("verdict") != "done":
        return [f"verdict is {entry.get('verdict')}, not done"]
    failures = []
    oracles = entry.get("oracles") or {}
    if not oracles.get("receipt") and not oracles.get("ci"):
        failures.append("the entry names no oracle")
    if oracles.get("walk") or entry.get("walk"):
        failures.append("the entry still has a walk")
    checks = [c for c in entry.get("checks") or [] if isinstance(c, dict)]
    for c in checks:
        observed = str(c.get("observed") or "")
        if c.get("status") != "PASS":
            failures.append(f"receipt check AC{c.get('ac')} is {c.get('status')}, not PASS")
        elif observed.startswith("NOT TESTABLE"):
            failures.append(f"receipt check AC{c.get('ac')} is NOT TESTABLE")
    checked = {str(c.get("ac")) for c in checks}
    for n in _ac_numbers(oracles.get("receipt")):
        if n not in checked:
            failures.append(f"receipt AC{n} has no check")
    if not str(entry.get("not_proven") or "").strip():
        failures.append("the entry has no not_proven line")
    return failures


def rule_done_evidence(m):
    """Exactly one source of evidence: a verdict entry (in-process from accept.py) or a comment
    file (the CLI) holding a `Not proven:` line."""
    entry, path = m.args.verdict_entry, m.args.comment_file
    fixed = (getattr(m.args, "already_fixed", None) or "").strip()
    if fixed or (entry is None and not path):
        return _already_fixed(m, fixed, path) if fixed else [DONE_VIA_ACCEPT]
    if entry is not None:
        failures = verdict_failures(entry, m.key)
        if failures:
            return failures
        m.extra.update(via="receipt", rc=m.args.rc)
        m.comment = done_comment(entry, m.args.rc, m.args.run_url)
        return []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        return [f"--comment-file {path}: {exc.strerror}"]
    if not NOT_PROVEN.search(text):
        return [f"--comment-file {path} has no line `Not proven: <what>`"]
    m.extra["via"] = "comment"
    m.comment = text.strip()
    return []


def _already_fixed(m, ref, path):
    """`--already-fixed REF`: the merged PR that fixed the story before it was built; the comment
    names it, a `--comment-file` beside it adds its text."""
    if not (_PR_URL.match(ref) or _PR_QUALIFIED.match(ref)):
        return [f"--already-fixed {ref} is no URL or <owner>/<repo>#<n>"]
    pr, failure = _view_pr(ref, Path.cwd())
    if failure:
        return [failure]
    if pr.get("state") != "MERGED":
        return [f"--already-fixed {ref} is not merged"]
    url = pr.get("url") or ref
    lines = [f"Already fixed on the default branch by {url} ({pr.get('title') or '-'})."]
    if path:
        try:
            lines.append(Path(path).read_text(encoding="utf-8").strip())
        except OSError as exc:
            return [f"--comment-file {path}: {exc.strerror}"]
    m.extra.update(via="already-fixed", pr=[url])
    m.comment = "\n\n".join(lines)
    return []


def done_comment(entry, rc, run_url):
    """The acceptance comment of a job-accepted story: one generator (docs/board.md § Acceptance)."""
    oracles = entry.get("oracles") or {}
    ci_tests = entry.get("ci_tests") or {}
    parts = []
    receipt = _ac_numbers(oracles.get("receipt"))
    if receipt:
        parts.append("receipt " + ", ".join(f"AC{n}" for n in receipt))
    ci = _ac_numbers(oracles.get("ci"))
    if ci:
        parts.append(
            "ci "
            + ", ".join(f"AC{n} ({ci_tests[n]})" if ci_tests.get(n) else f"AC{n}" for n in ci)
        )
    checks = [c for c in entry.get("checks") or [] if isinstance(c, dict)]
    personas = []
    for c in checks:
        if c.get("persona") and c["persona"] not in personas:
            personas.append(c["persona"])
    lines = [
        f"Accepted by the receipts job {rc} ({run_url})",
        "Oracle: " + (" · ".join(parts) or "none"),
        "Persona: " + (", ".join(personas) or "none"),
    ]
    lines += [
        f"Observed: AC{c.get('ac')} {c.get('status')} — {c.get('observed') or ''}".rstrip()
        for c in checks
    ]
    lines.append(f"Not proven: {str(entry.get('not_proven')).strip()}")
    return "\n".join(lines)


# One list of (group, rule) per target state, run in order; the first failing group stops the
# run. `selected` is exactly the Ready gate, the tier and the lenses: no rule asks a human.
ENTRY_RULES = {
    "on_hold": [("owner", rule_owner), ("reopen", rule_reopen)],
    "backlog": [("owner", rule_owner), ("epic", rule_epic_approved)],
    "selected": [
        ("role", rule_selector),
        ("owner", rule_owner),
        ("plan on main", rule_plan_on_main),
        ("refiner", rule_refiner),
        ("ready gate", rule_gate),
        ("tier", rule_tier),
        ("lenses", rule_lenses),
    ],
    "in_progress": [("owner", rule_owner), ("pulled", rule_pulled)],
    "in_review": [("owner", rule_owner), ("pr", rule_pr_merged_and_linked)],
    "in_test": [("owner", rule_owner), ("in review", rule_reviewed)],
    "done": [
        ("owner", rule_owner),
        ("in review", rule_in_review),
        ("evidence", rule_done_evidence),
    ],
}


def _caller():
    """The calling session's name for the row's `by`; its id or `unknown` when it has none."""
    try:
        return own_session_name()[0]
    except BoardError:
        return os.environ.get("CLAUDE_CODE_SESSION_ID") or "unknown"


def _writer(args):
    """The row's `by`: the calling session, or the script that moved in process
    (`main(writer=…)`, e.g. `we-worker close`), then with the session as `caller`."""
    writer = getattr(args, "writer", None)
    return {"by": writer, "caller": _caller()} if writer else {"by": _caller()}


def _transition(state, args, crew, now, target, head):
    """Run the target's entry rules, then write the row, call the adapter once and print the
    row and the `carry:` line; a refusal writes, calls and carries nothing."""
    adapter = _reads(args, crew)
    key = args.key
    failures = _key_failure(crew, key, head.split()[1])
    if failures:
        raise BoardError("\n".join(failures))
    source = _source_state(state, adapter, crew, key, head.split()[1])
    if source is CARRY:
        return _carry_reads(head.split()[1], [], [key])
    root = _toplevel(head.split()[1])
    plan = (
        Path(args.plan) if getattr(args, "plan", None) else root / "docs/plans" / f"{key}-story.md"
    )
    m = Move(state, key, target, root, plan, crew, args)
    m.source = source
    already = _ticket_already(crew, source, target)
    if already:
        m.extra["ticket_already"] = source
    for group, rule in ENTRY_RULES[target]:
        lines = rule(m)
        if lines:
            for line in m.warnings:
                print(line, file=sys.stderr)
            if target == "selected":
                raise BoardError("\n".join([f"{head}: refused ({group})", *lines]))
            raise BoardError("\n".join(f"{head}: refused: {line}" for line in lines))
    for line in m.warnings:
        print(line, file=sys.stderr)
    status = (crew.get("board") or {}).get("states", {}).get(target) or (
        crew_mod.DEFAULTS["board"]["states"][target]
    )
    row = state.record_transition(
        key,
        lambda _last: {
            "key": key,
            "from": m.source,
            "to": target,
            "ts": _iso(now),
            **_writer(args),
            **m.extra,
            "ticket": adapter.name,
        },
    )
    ops = _transition_ops(adapter, m, status, already)
    if "tier" in m.extra:
        print(f"tier: {m.extra['tier']}")
    if "round" in m.extra:
        print(f"round: {m.extra['round']}")
    for item in m.extra.get("carried", []):
        print(f"carried: {item['lens']}: {item['claim']} ({item['where'] or '-'})")
    for item in m.extra.get("decided", []):
        print(f"decided: {item['lens']} by {item['by']}: {item['sentence']}")
    print(json.dumps(row, ensure_ascii=False))
    _print_carry(ops)
    return 0


def _who(crew, env=None, verb="claim"):
    """`<role>@<human>` of the calling session, as a ticket comment names it across machines;
    refused (`BoardError`) when the crew cannot tell the session's human."""
    env = os.environ if env is None else env
    role = crew_mod.role_of_session(crew, env) or "session"
    try:
        found = crew_mod.current_human(crew, env)
    except crew_mod.CrewError as exc:
        raise BoardError(f"board.py {verb}: refused: {exc}") from None
    if found is None:
        raise BoardError(
            f"board.py {verb}: refused: several humans and none is this session's: set "
            "WE_HUMAN=<slug> or git config user.email to one of humans.*.email"
        )
    return f"{role}@{found[0]}"


def _select_comment(m):
    plan = str(m.selected.get("plan") or "")[:12] or "-"
    who = m.selected.get("who") or _who(m.crew, verb=f"select {m.key}")
    panel = m.extra.get("panel") or f"ready-{m.key}"
    return f"selected by {who}, plan {plan}, panel {panel}"


CARRY = object()  # `_source_state`: the session has to read the ticket first


def state_of_status(crew, status):
    """The board state a ticket status name maps to (`board.states`, case-insensitive), else None."""
    states = {
        **crew_mod.DEFAULTS["board"]["states"],
        **((crew.get("board") or {}).get("states") or {}),
    }
    want = str(status or "").strip().lower()
    return next(
        (st for st, name in states.items() if want and name and str(name).lower() == want), None
    )


def _status_bus(crew):
    """Several humans whose ticketing system carries the status (`board.ticketing` is not
    `none`): only then is the ticket's status the state every machine shares."""
    ticketing = str((crew.get("board") or {}).get("ticketing") or "none")
    return crew_mod.several_humans(crew) and ticketing != "none"


def _transition_ops(adapter, m, status, already):
    """The carry of a written row: the transition (none when the ticket already stands there),
    and for `selected` the select comment and the crew's `board.select_unlabel` labels."""
    ops = [] if already else adapter.move(m.key, status)
    if already:
        print(f"ticket already {m.source}: no transition")
    if m.target == "selected":
        comment = _select_comment(m)
        if already and m.source != m.target:
            comment += f"\nThe ticket stays {m.source}."
        ops += adapter.comment(m.key, comment)
        for label in (m.crew.get("board") or {}).get("select_unlabel") or []:
            ops += adapter.unlabel(m.key, label)
    return ops


FORWARD = ("backlog", "selected", "in_progress", "in_review", "in_test", "done")


def _ticket_already(crew, source, target):
    """With the ticket's status as the shared state: the ticket already stands at the target (a
    human or a session moved it first), or past Selected when the story is selected late. The
    row is still written; the ticket gets no transition back."""
    if not _status_bus(crew) or source not in FORWARD or target not in FORWARD:
        return False
    if source == target:
        return True
    return target == "selected" and FORWARD.index(source) > FORWARD.index(target)


def _source_state(state, adapter, crew, key, verb="move"):
    """The state a story leaves: with several humans the ticket's status (every machine moves
    the ticket, each keeps its own rows), `CARRY` while the session has to read it, refused
    (`BoardError`) for a status no `board.states` entry maps, since its owner is unknown; else
    the key's last local row (also with `board.ticketing: none`, where no ticket holds a status)."""
    if _status_bus(crew):
        ticket = adapter.ticket(key)
        if ticket is None:
            return CARRY
        status = ticket.get("status")
        if status is None:
            raise BoardError(
                f"board.py {verb} {key}: refused: the --input file names no status for {key}: "
                f'read the ticket and add "tickets": {{"{key}": {{"status": "<its status>", …}}}}'
            )
        found = state_of_status(crew, status)
        if found is None:
            raise BoardError(
                f"board.py {verb} {key}: refused: the ticket's status {status!r} maps to no board "
                "state (board.states), so its owner is unknown; map it in crew.json, or ask the "
                "coordinator to move the ticket"
            )
        return found
    last = state.last_rows().get(key)
    return last.get("to") if last else None


def cmd_select(state, args, crew, now):
    return _transition(state, args, crew, now, "selected", f"board.py select {args.key}")


def cmd_move(state, args, crew, now):
    head = f"board.py move {args.key} {args.state}"
    if args.state == "selected":
        raise BoardError(f"{head}: refused: {SELECT_ONLY}")
    if args.state == "done":
        adapter = _reads(args, crew)
        source = _source_state(state, adapter, crew, args.key)
        if source is CARRY:
            return _carry_reads("move", [], [args.key])
        row, ops, sample = move_done(
            state,
            args.key,
            crew,
            now,
            adapter,
            comment_file=args.comment_file,
            source=source,
            already_fixed=args.already_fixed,
        )
        print(json.dumps(row, ensure_ascii=False))
        if sample:
            print(sample)
        _print_carry(ops)
        return 0
    return _transition(state, args, crew, now, args.state, head)


def _sample_keeper(crew):
    lens = (crew.get("lenses") or {}).get("acceptance") or {}
    return lens.get("keeper") or (crew.get("roles") or {}).get("acceptance") or "roles.acceptance"


def _sample(state, crew, key, now):
    """Every `acceptance.done_sample`-th row `to: done, via: receipt` adds one `sample` log
    item for the acceptance keeper; the count is the log's, so it survives restarts.
    `lenses.acceptance.sample` is the lens sampler's (lens_verdict.py) and not read here."""
    n = (crew.get("acceptance") or {}).get("done_sample")
    if not isinstance(n, int) or n <= 0:
        return None
    count = sum(
        1 for r in state.transitions() if r.get("to") == "done" and r.get("via") == "receipt"
    )
    if count == 0 or count % n:
        return None
    keeper = _sample_keeper(crew)

    def mutate(board):
        append_log(
            board,
            [
                {
                    "id": state.next_id("S", board),
                    "kind": "sample",
                    "title": f"Sample {key}: accepted by the receipts job, {keeper} checks it post hoc",
                    "ts": _iso(now),
                }
            ],
        )

    state.write_board(mutate)
    return f"sample: {key} → {keeper}"


def move_done(
    state,
    key,
    crew,
    now,
    adapter,
    *,
    entry=None,
    rc=None,
    run_url=None,
    comment_file=None,
    source=None,
    already_fixed=None,
):
    """The `done` move: its entry rules, then the row, the adapter (transition, then comment) and
    the sample. Returns (row, ops, sample line or None); a refusal raises `BoardError` with one
    `board.py move <KEY> done: refused: <reason>` line per failure and writes nothing. `entry`
    (a verdict entry) comes only from accept.py, after its provenance check; the CLI passes
    `comment_file` or `already_fixed` (a merged PR that fixed the story before it was built).
    `source` is the state the story leaves (`_source_state`), default the key's last local row."""
    head = f"board.py move {key} done"
    failures = _key_failure(crew, key, "move")
    if failures:
        raise BoardError("\n".join(failures))
    args = argparse.Namespace(
        verdict_entry=entry,
        comment_file=comment_file,
        rc=rc,
        run_url=run_url,
        already_fixed=already_fixed,
    )
    m = Move(state, key, "done", None, None, crew, args)
    m.comment = None
    if source is None:
        # accept.py: with several humans the ticket's status decides, never the local row
        source = _source_state(state, adapter, crew, key, "move")
        if source is CARRY:
            raise BoardError(
                f"{head}: refused: several humans: the story's state comes from its ticket, which "
                f"this run cannot read; carry the read and run `board.py move {key} done "
                "--comment-file <the receipt comment> --input FILE`"
            )
    m.source = source
    already = _ticket_already(crew, source, "done")
    if already:
        m.extra["ticket_already"] = source
    for _group, rule in ENTRY_RULES["done"]:
        lines = rule(m)
        if lines:
            raise BoardError("\n".join(f"{head}: refused: {line}" for line in lines))
    status = ((crew.get("board") or {}).get("states") or {}).get("done") or (
        crew_mod.DEFAULTS["board"]["states"]["done"]
    )
    row = {
        "key": key,
        "from": m.source,
        "to": "done",
        "via": m.extra["via"],
        **({"rc": m.extra["rc"]} if m.extra.get("rc") else {}),
        **({"pr": m.extra["pr"]} if m.extra.get("pr") else {}),
        "ts": _iso(now),
        "by": _caller(),
        "ticket": adapter.name,
    }
    state.record_transition(key, lambda _last: row)
    ops = [] if already else adapter.move(key, status)
    if already:
        print(f"ticket already {source}: no transition")
    ops += adapter.comment(key, m.comment)
    sample = _sample(state, crew, key, now) if row["via"] == "receipt" else None
    return row, ops, sample


def _jira_snapshot(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise BoardError(f"board.py check: --jira {path}: {exc.strerror}", code=2) from None
    except ValueError:
        raise BoardError(f"board.py check: --jira {path}: no valid JSON", code=2) from None
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        raise BoardError(
            f"board.py check: --jira {path}: needs an object of key → status name", code=2
        )
    return data


def cmd_check(state, args, crew, now):
    snapshot = _jira_snapshot(args.jira)
    states = {
        **crew_mod.DEFAULTS["board"]["states"],
        **((crew.get("board") or {}).get("states") or {}),
    }
    by_name = {name: st for st, name in states.items()}
    order = list(crew_mod.STATES)
    last = state.last_rows()
    found = []
    for key, status in snapshot.items():
        st = by_name.get(status)
        if st is None:
            found.append((key, f'error: {key} jira "{status}" is no board state'))
            continue
        row = last.get(key)
        if row is None:
            if order.index(st) > order.index("backlog"):
                found.append((key, f'drift: {key} jira "{status}" board none'))
        elif row.get("to") != st:
            found.append((key, f'drift: {key} jira "{status}" board {row.get("to")}'))
    for session in state.board().get("sessions") or []:
        if not isinstance(session, dict):
            continue
        for key in session.get("keys") or []:
            if isinstance(key, str) and (last.get(key) or {}).get("to") == "in_review":
                found.append(
                    (
                        key,
                        f"drift: {key} session {session.get('name')} still holds it (board in_review)",
                    )
                )
    if not found:
        print(f"no drift ({len(snapshot)} keys)")
        return 0
    for _key, line in sorted(found, key=lambda x: x[0]):
        print(line)
    return 1


def _staging(crew):
    repo = board_staging.crew_repo(crew_mod.find())
    if not repo:
        raise BoardError("board.py staging: no GitHub origin for the crew's repo or the cwd")
    return board_staging.Staging(crew, repo)


def _sync_staging(state, staging, now):
    """Read the issues, write the `staging` block (and a past-SLA news item), print its lines."""
    try:
        block = board_staging.snapshot(staging, now)
    except board_staging.StagingError as exc:
        raise BoardError(f"board.py staging: {exc}") from None
    item = state.write_board(lambda board: board_staging.merge_block(board, block, now))
    for line in board_staging.status_lines(block):
        print(line)
    if item:
        print(f"news: {item['id']} {item['title']}")
    return 0


def _holder(verb):
    try:
        return own_session_name()[0]
    except BoardError as exc:
        raise BoardError(
            str(exc).replace("board.py set:", f"board.py {verb}:"), exc.code
        ) from None


def cmd_book(state, args, crew, now):
    until = board_staging.parse_time(args.until)
    if until is None:
        raise BoardError(f"board.py book: refused: --until {args.until!r} is no UTC time")
    holder = _holder("book")
    staging = _staging(crew)
    try:
        url = board_staging.book(staging, holder, until, now)
    except board_staging.StagingError as exc:
        raise BoardError(str(exc), exc.code) from None
    print(f"booked staging for {holder} until {board_staging.minute(until)}: {url}")
    return _sync_staging(state, staging, now)


def cmd_unbook(state, args, crew, now):
    holder = _caller() if args.rc else _holder("unbook")
    staging = _staging(crew)
    try:
        closed = board_staging.unbook(staging, holder, args.rc, now)
    except board_staging.StagingError as exc:
        raise BoardError(str(exc), exc.code) from None
    what = f"acceptance of {args.rc}" if args.rc else f"booking of {holder}"
    print(f"closed {what}: " + " ".join(f"#{n}" for n in closed))
    return _sync_staging(state, staging, now)


def cmd_staging(state, args, crew, now):
    return _sync_staging(state, _staging(crew), now)


def _add_escalation_verbs(verbs):
    e = verbs.add_parser("escalation", help="the decision story between two owners")
    ev = e.add_subparsers(dest="step", required=True)
    eo = ev.add_parser("open", help="open the decision story (a party)")
    for field in OPEN_FIELDS:
        eo.add_argument("--" + field.replace("_", "-"), dest=field)
    eo.add_argument("--touches", help=f"one of {', '.join(TOUCHES)}: the human decides")
    eo.set_defaults(run=cmd_escalation_open)
    er = ev.add_parser("route", help="move records past their SLA (the coordinator)")
    er.set_defaults(run=cmd_escalation_route)
    ea = ev.add_parser("advise", help="the escalation role's recommendation on a --touches record")
    ea.add_argument("id")
    ea.add_argument("--recommendation", required=True)
    ea.set_defaults(run=cmd_escalation_advise)
    es = ev.add_parser("settle", help="close a record with its outcome")
    es.add_argument("id")
    es.add_argument("--outcome", required=True)
    es.add_argument("--via", choices=("human",))
    es.set_defaults(run=cmd_escalation_settle)
    el = ev.add_parser("list", help="open records waiting on a role (default: the caller's)")
    el.add_argument("--waiting-on", dest="waiting_on", metavar="ROLE")
    el.add_argument("--stage", help=f"one of {', '.join(STAGES)}")
    el.set_defaults(run=cmd_escalation_list)
    ec = ev.add_parser("count", help="escalations per role pair this ISO week")
    ec.set_defaults(run=cmd_escalation_count)


def _add_news_verbs(verbs):
    verbs.add_parser(
        "bundle", help="the coordinator's evening bundle as one news item"
    ).set_defaults(run=cmd_bundle)
    n = verbs.add_parser("news", help="the owner's news (the coordinator)")
    steps = n.add_subparsers(dest="step", required=True)
    add = steps.add_parser("add", help="one item at the top of news, for the owner")
    add.add_argument("--title", required=True)
    add.add_argument("--body")
    add.add_argument("--kind", choices=NEWS_KINDS, default="info")
    add.set_defaults(run=cmd_news)
    wk = steps.add_parser(
        "worker", help="the launcher's item for the human (worker_supervisor.py)"
    )
    wk.add_argument("--id", required=True)
    wk.add_argument("--title", required=True)
    wk.add_argument("--body")
    wk.set_defaults(run=cmd_news_worker)


def _add_staging_verbs(verbs):
    bk = verbs.add_parser("book", help="book staging for this session until a UTC minute")
    bk.add_argument("target", choices=("staging",))
    bk.add_argument("--until", required=True, metavar="UTC", help="YYYY-MM-DDTHH:MMZ")
    bk.set_defaults(run=cmd_book)
    ub = verbs.add_parser("unbook", help="close this session's booking, or an RC's acceptance")
    ub.add_argument("rc", nargs="?", help="the RC tag whose acceptance closes")
    ub.set_defaults(run=cmd_unbook)
    verbs.add_parser(
        "staging", help="mirror booking and acceptance into the board file"
    ).set_defaults(run=cmd_staging)


def _add_move_verbs(verbs):
    sel = verbs.add_parser("select", help="move a story to Selected: Ready gate, tier, lenses")
    sel.add_argument("key")
    sel.add_argument("--plan", help="the story plan (default docs/plans/<KEY>-story.md)")
    sel.add_argument("--input", metavar="FILE", help="several humans: the ticket read carried")
    sel.add_argument(
        "--refiner",
        action="store_true",
        help="a refiner's own select: only a key on its approved epic's line, no `select: owner`",
    )
    sel.set_defaults(run=cmd_select)

    mv = verbs.add_parser("move", help="move a story to a state whose entry rule holds")
    mv.add_argument("key")
    mv.add_argument("state", choices=(*MOVE_STATES[:2], "selected", *MOVE_STATES[2:]))
    mv.add_argument("--pr", action="append", metavar="REF", help="in_review: a merged PR (repeat)")
    mv.add_argument(
        "--reopen",
        metavar="TEXT",
        help="on_hold: what reopens it; in_progress from in_review/in_test: why (revert, failed test)",
    )
    mv.add_argument("--epic", metavar="EPIC", help="backlog: the approved epic")
    mv.add_argument(
        "--fast",
        action="store_true",
        help="in_progress from backlog or no row: the fast lane, a small story without a plan file",
    )
    mv.add_argument(
        "--comment-file",
        dest="comment_file",
        metavar="FILE",
        help="done: an acceptance comment holding a `Not proven:` line",
    )
    mv.add_argument(
        "--already-fixed",
        dest="already_fixed",
        metavar="REF",
        help="done from any state: the merged PR (<owner>/<repo>#<n> or URL) that fixed it already",
    )
    mv.add_argument("--input", metavar="FILE", help="several humans: the ticket read carried")
    mv.set_defaults(run=cmd_move)

    ck = verbs.add_parser("check", help="board-vs-ticketing drift over a snapshot")
    ck.add_argument("--jira", required=True, metavar="FILE", help="JSON object key → status name")
    ck.set_defaults(run=cmd_check)


def _add_remote_ask(q):
    q.add_argument("--to", metavar="HUMAN", help="a human on another machine: asked on the ticket")
    q.add_argument("--input", metavar="FILE", help="several humans: the ticket read carried")


def _add_human_verbs(verbs):
    sg = verbs.add_parser("signals", help="ticket transitions and replies for this human's roles")
    sg.add_argument("--input", metavar="FILE", help="the reads the session carried")
    sg.set_defaults(run=cmd_signals)
    cl = verbs.add_parser("claim", help="claim a ticket for this role and human, or --release")
    cl.add_argument("key")
    cl.add_argument("--release", action="store_true", help="end this session's claim")
    cl.add_argument("--input", metavar="FILE", help="the ticket read the session carried")
    cl.set_defaults(run=cmd_claim)
    ib = verbs.add_parser(
        "inbox", help="the open questions to this session's human (ticket labels)"
    )
    ib.add_argument("--input", metavar="FILE", help="the search the session carried")
    ib.set_defaults(run=cmd_inbox)
    rp = verbs.add_parser("reply", help="answer a question to this human on its ticket")
    rp.add_argument("key")
    rp.add_argument("kind", choices=board_humans.KINDS)
    rp.add_argument("--text", default="", help="the answer's words")
    rp.set_defaults(run=cmd_reply)
    for name, text in (
        ("withdraw", "take back your own open question"),
        ("supersede", "replace your own open question by a newer one"),
    ):
        wd = verbs.add_parser(name, help=text)
        wd.add_argument("id")
        if name == "supersede":
            wd.add_argument(
                "--by", required=True, metavar="QID", help="the open question that replaces it"
            )
        else:
            wd.add_argument(
                "--for",
                dest="for_",
                metavar="QID",
                help="withdrawn in favour of this question (a refused supersede of it names you)",
            )
        wd.add_argument("--reason", default="", help="one line why")
        wd.set_defaults(run=cmd_withdraw)


def _add_flow_verbs(verbs):
    lg = verbs.add_parser("log", help="a line in the flow log (the coordinator)")
    lv = lg.add_subparsers(dest="what", required=True)
    lc = lv.add_parser("correction", help="the human corrected a session")
    lc.add_argument("session")
    lc.add_argument("kind", help="one lower-case token")
    lc.set_defaults(run=cmd_log)

    bl = verbs.add_parser("blocked", help="mark or clear a session's blocked wait (self-checked)")
    bl.add_argument("name")
    bl.add_argument("--kind", choices=BLOCKED_KINDS)
    bl.add_argument("--waiting-on", dest="waiting_on", metavar="ROLE")
    bl.add_argument("--starter", metavar="NAME", help="the session that started it")
    bl.add_argument("--key", metavar="KEY")
    bl.add_argument(
        "--command", metavar="TEXT", help="the pending command, filtered by the caller"
    )
    bl.add_argument("--clear", action="store_true", help="end the wait")
    bl.set_defaults(run=cmd_blocked)


def _add_read_verbs(verbs):
    sh = verbs.add_parser("show", help="one question with its answers and status (read-only)")
    sh.add_argument("id")
    sh.set_defaults(run=cmd_show)
    pa = verbs.add_parser("path", help="print the board file a verb without --board writes")
    pa.add_argument("--crew-only", action="store_true", help="only the crew's board.file")
    pa.set_defaults(run=cmd_path)


def parser():
    p = argparse.ArgumentParser(prog="board.py", description="The board's verbs for a session.")
    p.add_argument(
        "--board",
        help=f"the board file (default: the crew's board.file, else {DEFAULT_BOARD})",
    )
    verbs = p.add_subparsers(dest="verb", required=True)
    a = verbs.add_parser("answer", help="write back an answer the owner gave in a chat")
    a.add_argument("id")
    a.add_argument("kind", choices=KINDS)
    a.add_argument("--session", required=True, help="the session whose chat the answer came in")
    a.add_argument("--via", required=True, choices=("chat",))
    a.add_argument("--quote", help="the owner's own words")
    a.add_argument(
        "--text-file", metavar="PATH", help="the owner's words from a file, - for stdin"
    )
    a.set_defaults(run=cmd_answer)
    _add_read_verbs(verbs)

    s = verbs.add_parser(
        "set",
        help="write this session's own board line",
        description=(
            "Writes the line named as `claude agents` lists this session. Fields: "
            f"{', '.join(SET_FIELDS)}; state is one of {', '.join(SESSION_STATES)}; "
            "waiting_on a role key or human; an empty value clears a field."
        ),
    )
    s.add_argument(
        "--for", dest="for_", metavar="NAME", help="another session's line (coordinator)"
    )
    s.add_argument(
        "--session", metavar="NAME", help="this session's own name, checked (as `ask` takes it)"
    )
    s.add_argument("assignments", nargs="+", metavar="field=value")
    s.set_defaults(run=cmd_set)

    q = verbs.add_parser("ask", help="post a question for the owner after the cold reader")
    for field in ASK_FIELDS:
        q.add_argument("--" + field.replace("_", "-"), dest=field)
    q.add_argument("--text-file", metavar="PATH", help="the --ask text from a file, - for stdin")
    q.add_argument("--urgent", action="store_true", help="bundle lists it before the others")
    q.add_argument("--pr", metavar="REF", help="the open PR a merge-go question is about")
    q.add_argument("--one-way", metavar="CLASS", help="merge-go on a one-way PR: Accept reads Go")
    q.add_argument(
        "--kind",
        dest="ask_kind",
        choices=("question", "task"),
        default="question",
        help="task: the pane labels Accept as Taken",
    )
    q.add_argument("--source", metavar="CMD_OR_LINK", help="where the fact in the ask comes from")
    q.add_argument("--owner", metavar="MEMBER", help="the member who owns the subject")
    q.add_argument(
        "--component", metavar="NAME", help="owner: the member whose components hold it"
    )
    q.add_argument("--replace", metavar="QID", help="replace this open question on the same --key")
    q.add_argument(
        "--distinct",
        action="store_true",
        help="another question on a key and cause that already has an open one",
    )
    _add_remote_ask(q)
    q.set_defaults(run=cmd_ask)
    _add_human_verbs(verbs)
    verbs.add_parser(
        "close-merged", help="drop merge-go questions whose PR merged or closed"
    ).set_defaults(run=cmd_close_merged)
    verbs.add_parser(
        "prune", help="drop answered questions and handled news from the board"
    ).set_defaults(run=cmd_prune)
    _add_flow_verbs(verbs)

    d = verbs.add_parser(
        "decision", help="record a cut, fence or process decision of the caller's area"
    )
    d.add_argument("area")
    d.add_argument("kind")
    d.add_argument("--key", required=True)
    d.add_argument("--text", required=True)
    d.set_defaults(run=cmd_decision)

    _add_news_verbs(verbs)

    _add_escalation_verbs(verbs)

    _add_move_verbs(verbs)
    _add_staging_verbs(verbs)
    return p


# Verbs that load no crew: they work where the crew file is missing or broken.
CREWLESS_VERBS = ("answer", "show", "path")
# The crew guard (`crew_guard`): verbs that only read pass it.
READ_VERBS = ("path", "show", "check", "escalation list", "escalation count")


def _verb_name(args):
    step = getattr(args, "step", None)
    return f"{args.verb} {step}" if args.verb == "escalation" and step else args.verb


def _is_member(crew, pin):
    """Whether the companion `pin` (WESIDE_COMPANION) is a member of `crew`, by slug, name or a
    human's name for it (`crew.member`)."""
    return crew_mod.member(crew or {}, pin) is not None


def _session_crew(cwd, env):
    """(crew id or None, crew file or None, crew or None, why none): the calling session's crew.
    A pin (WESIDE_COMPANION) that is no member of the cwd's crew counts as no crew."""
    try:
        crew_path, crew = crew_mod.find_and_load(cwd)
    except crew_mod.CrewError as exc:
        return None, None, None, f"no crew (the crew file is unreadable: {exc})"
    if crew_path is None:
        return None, None, None, f"no crew (no crew file found from {cwd})"
    cid = crew_mod.crew_id(crew_path)
    pin = str(env.get("WESIDE_COMPANION") or "").strip()
    if pin and not _is_member(crew, pin):
        return None, crew_path, crew, f"no crew (the pinned companion {pin} is no member of {cid})"
    return cid, crew_path, crew, None


def crew_guard(args, env=None, cwd=None):
    """(refusal or None, the board to stamp after the write or None) for a `board.py` call.

    Refused (two crews, AC11): a writing verb of a session without a crew on the default board
    (no `--board`), and a writing verb of a crew's session on a board whose stamp
    (`crew.stamp_path`) names another crew. The session's own board, resolved from its crew, is
    stamped by its first write. A session without a crew that names a board with `--board` passes
    and writes under the board's own stamp: the explicit file is the intent, and only a second
    crew's session can mistake another crew's board for its own."""
    verb = _verb_name(args)
    if verb in READ_VERBS:
        return None, None
    env = os.environ if env is None else env
    cwd = Path(cwd or Path.cwd())
    target = Path(args.board).expanduser() if args.board else default_board(cwd)
    cid, crew_path, crew, why = _session_crew(cwd, env)
    stamp = crew_mod.read_stamp(target)
    mine = None
    if cid is not None:
        mine = crew_mod.board_file(crew_path, crew, env, DEFAULT_BOARD)
    if cid is None:
        if args.board:
            return None, None
        owner = f"crew {stamp}" if stamp else "the default board, no crew stamped yet"
        return _guard_text(verb, why, target, owner), None
    if stamp is not None and stamp != cid:
        return _guard_text(verb, why or f"crew {cid}", target, f"crew {stamp}", mine), None
    own = mine is not None and _same_file(mine, target)
    return None, (target if own and stamp is None else None)


def _same_file(a, b):
    return Path(a).expanduser().resolve() == Path(b).expanduser().resolve()


def _guard_text(verb, caller, target, owner, mine=None):
    fix = (
        f"name your own crew's board with --board {mine}"
        if mine is not None
        else "run it from a session of the board's crew, or name the board meant with --board FILE"
    )
    return (
        f"board.py {verb}: refused: this session's crew is {caller}; the board {target} belongs "
        f"to {owner}. Nothing was written. {fix} (`board.py path` in your crew's repo prints it)."
    )


ANSWER_WORDS = {
    "yes": "accept",
    "ok": "accept",
    "go": "accept",
    "approve": "accept",
    "no": "deny",
    "reject": "deny",
    "later": "followup",
    "more": "followup",
    "discuss": "followup",
    "info": "followup",
}


def _flag_to_field(argv, i):
    """(`field=value`, next index) when argv[i] is a `set` field written as a flag, else None."""
    flag, _, inline = argv[i].partition("=")
    field = flag.lstrip("-").replace("-", "_")
    if not flag.startswith("--") or field not in SET_FIELDS:
        return None
    if inline or argv[i].endswith("="):
        return f"{field}={inline}", i + 1
    value = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else ""
    return f"{field}={value}", i + 2 if value else i + 1


def _usage_hint(argv):
    """The corrected call for an argparse refusal the measured week saw most: `set` fields
    passed as flags, an answer kind or `--via` outside its choices; None for any other."""
    rest = list(argv)
    lead = rest[:2] if rest[:1] == ["--board"] else []
    rest = rest[len(lead) :]
    if not rest:
        return None
    verb, tail, out, changed, i = rest[0], rest[1:], [], False, 0
    if verb == "set":
        while i < len(tail):
            hit = _flag_to_field(tail, i)
            if hit:
                out.append(hit[0])
                i, changed = hit[1], True
            else:
                out.append(tail[i])
                i += 1
    elif verb == "answer":
        for j, word in enumerate(tail):
            meant = word
            if j == 1 and word not in KINDS and word.lower() in ANSWER_WORDS:
                meant = ANSWER_WORDS[word.lower()]
            elif j > 0 and tail[j - 1] == "--via" and word != "chat":
                meant = "chat"
            changed = changed or meant != word
            out.append(meant)
    return _corrected([*lead, verb, *out]) if changed else None


def main(argv=None, now=None, adapter=None, writer=None):
    """`adapter` is the tests' FakeAdapter; None means the crew's transport (`adapter_for`).
    `writer` names a script moving in process (the transitions row's `by`); no CLI flag sets it."""
    try:
        args = parser().parse_args(argv)
    except SystemExit as exc:
        hint = _usage_hint(sys.argv[1:] if argv is None else argv) if exc.code == 2 else None
        if hint:
            print(hint, file=sys.stderr)
        raise
    try:
        crew = None if args.verb in CREWLESS_VERBS else load_crew()
        args.adapter_given = adapter
        args.writer = writer
        now = now or _now()
        refusal, stamp_board = crew_guard(args)
        if refusal:
            raise BoardError(refusal, code=3)
        coordinator = bool(crew) and crew_mod.holds_role(crew, "coordinator", os.environ)
        state = StateDir(args.board or default_board(), now=now, stamps_updated=coordinator)
        code = args.run(state, args, crew, now)
        if stamp_board is not None and code == 0 and Path(stamp_board).expanduser().exists():
            cid, *_ = _session_crew(Path.cwd(), os.environ)
            if cid is not None:
                crew_mod.write_stamp(stamp_board, cid)
        return code
    except BoardError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
