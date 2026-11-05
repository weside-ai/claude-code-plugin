#!/usr/bin/env python3
"""The board's verbs for a session (docs/board.md § The file, § Answers, § Questions and decisions, § Escalations).

Usage:
  board.py [--board FILE] answer <id> <accept|deny|discuss|info|update> --session NAME --via chat
           [--quote "<the owner's words>"]
  board.py [--board FILE] set [--for NAME] <field>=<value> …       fields: waiting_on, state, now
  board.py [--board FILE] ask --session NAME --key KEY --key-title T --ask Q --recommendation R
           --cause <merge-go|plan|prod|cut-fence|access-click|info>
  board.py [--board FILE] decision <area> <cut|fence> --key KEY --text T
  board.py [--board FILE] bundle
  board.py [--board FILE] escalation open --key KEY --parties ROLE,ROLE --question Q --a T --a-cost C
           --b T --b-cost C --reversible <yes|no> [--touches <vision|money|law|priority>]
  board.py [--board FILE] escalation <route|count>
  board.py [--board FILE] escalation list [--waiting-on ROLE] [--stage STAGE]
  board.py [--board FILE] escalation advise E<n> --recommendation T
  board.py [--board FILE] escalation settle E<n> --outcome T [--via human]
  board.py [--board FILE] select <KEY> [--plan PATH]
  board.py [--board FILE] move <KEY> <on_hold|backlog|in_progress|in_review>
           [--reopen TRIGGER] [--epic EPIC] [--pr REF]…
  board.py [--board FILE] check --jira FILE

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
         `since`. It never writes `updated` or `updated_by`.
ask      posts a question for the owner after a cold reader (`cold_reader.py`) understood it
         without context; otherwise the reader's reason goes back as a `note` on the asking
         session's line and a `returned` news item. Every run past the field check leaves one line
         in board-questions.jsonl, text included. Prints `posted Q<n>`.
decision records an owner's cut or fence decision of their area (`roles.<area>`): one news item
         `D<n>` of kind `decision`, then one line in board-decisions.jsonl.
bundle   the coordinator's evening bundle: one news item `B-<date>` of kind `todo` listing the
         decisions since the last bundle by area and the open questions oldest first, then a
         marker line in board-decisions.jsonl. Nothing to show prints `bundle: nothing`. It runs
         `escalation route` first and lists the open bundle-stage escalations after the open
         questions.
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
select   moves a story to Selected when its `ENTRY_RULES["selected"]` hold, in order: the Ready
         gate (`ready_gate.story_failures`), the plan-only tier (`plan_tier.py`) and a green
         `ready-<KEY>` lens verdict (`lens_verdict.check`). The first failing group refuses with
         `board.py select <KEY>: refused (<group>)` and its lines; no rule asks a human.
move     moves a story to another state when that state's entry rule holds (docs/board.md
         § Moves): `on_hold` --reopen, `backlog` --epic of an approved epic plan, `in_progress`
         after a `selected` row, `in_review` with every --pr merged and linked (`gh pr view`). A
         refusal prints `board.py move <KEY> <state>: refused: <reason>` per failure.
         Both write one row to board-transitions.jsonl after every rule passed, call the
         ticketing adapter once (`ticket_adapter.py`, by `board.ticketing`) and, with
         `board.ticketing: jira`, print `carry: <JSON list>` as the last line for the session
         to execute with its ticketing tool. A refusal writes, calls and carries nothing.
check    compares a ticketing snapshot (`--jira FILE`: a JSON object key → status name, read by
         the session; the script reads no ticketing system) with the transitions log and the
         board: one `drift:` line per mismatch, one `error:` line per unknown status, exit 1;
         else `no drift (<n> keys)`. Exit 2 for an unusable snapshot.

Every write of board.json goes through `StateDir.write_board` (an exclusive lock on
board.json.lock, a re-read, then a temp file and `os.replace`). The JSONL files beside the board
only grow (O_APPEND). FILE defaults to ~/.claude/we-state/board.json (the pane's option
`boardFile` names another).
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import importlib.util
import json
import os
import re
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

import cold_reader  # noqa: E402
import crew as crew_mod  # noqa: E402
import lens_verdict  # noqa: E402
import plan_tier  # noqa: E402
import ready_gate  # noqa: E402
import ticket_adapter  # noqa: E402
import worker_launch as wl  # noqa: E402  (the one reader of `claude agents --json`)

DEFAULT_BOARD = "~/.claude/we-state/board.json"
KINDS = ("accept", "deny", "discuss", "info", "update")
CLOSING = ("accept", "deny")
# The one owner of the session state values; docs/board.md's `sessions[].state` row mirrors it.
SESSION_STATES = ("build", "ci", "active", "wait-owner", "idle", "parked", "done")
SET_FIELDS = ("waiting_on", "state", "now")
CAUSES = ("merge-go", "plan", "prod", "cut-fence", "access-click", "info")
DECISION_KINDS = ("cut", "fence")
ASK_FIELDS = ("session", "key", "key_title", "ask", "recommendation", "cause")
RETURN_PREFIX = "returned to "
TOUCHES = ("vision", "money", "law", "priority")
OPEN_FIELDS = ("key", "parties", "question", "a", "a_cost", "b", "b_cost", "reversible")
STAGES = ("self", "escalation", "bundle")
NEWS_KIND_BY_STAGE = {"escalation": "escalation", "bundle": "todo"}
PAIR_WARN_AFTER = 2  # escalations per role pair and ISO week before the crew's rights look wrong
LOCK_WAIT_S = 10.0
MINUTE_FMT = "%Y-%m-%dT%H:%MZ"
UNCHANGED = object()  # a `write_board` mutation returning this leaves board.json untouched


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

    def __init__(self, board_file):
        self.board_path = Path(board_file).expanduser()
        self.answers_path = self.board_path.with_name("board-answers.jsonl")
        self.questions_path = self.board_path.with_name("board-questions.jsonl")
        self.decisions_path = self.board_path.with_name("board-decisions.jsonl")
        self.escalations_path = self.board_path.with_name("board-escalations.jsonl")
        self.transitions_path = self.board_path.with_name("board-transitions.jsonl")
        self.lock_path = self.board_path.with_name(self.board_path.name + ".lock")

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
        mutated board (temp file + `os.replace`) unless `mutate` returned `UNCHANGED`. `after(result)`
        runs once the file is replaced, still under the lock: the place for a JSONL line that must
        not exist without its board change. Returns what `mutate` returned. The plugin's only
        writer of board.json."""
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
            board = self.board()
            result = mutate(board)
            if result is UNCHANGED:
                return result
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
            if after is not None:
                after(result)
            return result
        finally:
            os.close(fd)

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
        stamp = ts or _now().isoformat(timespec="milliseconds").replace("+00:00", "Z")
        return _answer_writer()(
            str(self.answers_path), qid, kind, stamp, session, via=via, quote=quote
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
            for field in ("owner_queue", "news")
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


def own_session_name(env=None):
    """(name, session id) of the calling session as `claude agents --json` lists it."""
    env = os.environ if env is None else env
    session_id = env.get("CLAUDE_CODE_SESSION_ID") or None
    try:
        rows = wl.sessions()
    except wl.LaunchError as exc:
        raise BoardError(f"board.py set: {exc}") from None
    try:
        return wl.lead_address(rows, session_id), session_id
    except wl.LaunchError:
        raise BoardError("board.py set: this session has no name; run /rename first") from None


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


def _parse_assignments(items, crew):
    fields, failures = {}, []
    roles = set(crew_mod.ROLE_KEYS) | {"human"}
    for item in items:
        if "=" not in item:
            failures.append(f"board.py set: {item!r} is no <field>=<value>")
            continue
        key, value = item.split("=", 1)
        if key not in SET_FIELDS:
            failures.append(
                f"board.py set: field {key!r} is not settable (only {', '.join(SET_FIELDS)})"
            )
        elif key == "waiting_on" and value and value not in roles:
            failures.append(
                f"board.py set: waiting_on {value!r} is no role key "
                f"({', '.join(crew_mod.ROLE_KEYS)} or human)"
            )
        elif key == "state" and value not in SESSION_STATES:
            failures.append(
                f"board.py set: state {value!r} is not one of {', '.join(SESSION_STATES)}"
            )
        elif key == "now" and "\n" in value:
            failures.append("board.py set: now is one line")
        else:
            fields[key] = value
    return fields, failures


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
    if not role:
        if line.get("waiting_on"):
            for key in ("waiting_on", "since", "sla_due"):
                line.pop(key, None)
        return
    if line.get("waiting_on") == role:
        return
    line.update(_wait(crew, now, role))


def cmd_set(state, args, crew, now):
    fields, failures = _parse_assignments(args.assignments, crew)
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

    def mutate(board):
        sessions = board.setdefault("sessions", [])
        line = next((s for s in sessions if isinstance(s, dict) and s.get("name") == name), None)
        if line is None:
            line = {"name": name}
            if session_id:
                line["session_id"] = session_id
            sessions.append(line)
        if "waiting_on" in fields:
            _apply_wait(line, fields["waiting_on"], crew, now)
        for key in ("state", "now"):
            if key in fields:
                line[key] = fields[key]
        return dict(line)

    print(json.dumps(state.write_board(mutate), ensure_ascii=False))
    return 0


def cmd_answer(state, args, crew, now):
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


def _key_failure(crew, key, verb):
    key_rx = (crew.get("naming") or {}).get("key") or crew_mod.DEFAULTS["naming"]["key"]
    if not re.fullmatch(key_rx, key):
        return [f"board.py {verb}: --key {key!r} does not match naming.key {key_rx}"]
    return []


def _ask_failures(args, crew):
    failures = []
    for field in ASK_FIELDS:
        value = getattr(args, field)
        if value is None or not value.strip():
            failures.append(f"board.py ask: missing --{field.replace('_', '-')}")
    if args.key and args.key.strip():
        failures += _key_failure(crew, args.key.strip(), "ask")
    if args.cause and args.cause.strip() and args.cause.strip() not in CAUSES:
        failures.append(f"board.py ask: --cause {args.cause!r} is not one of {', '.join(CAUSES)}")
    return failures


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


def cmd_ask(state, args, crew, now):
    failures = _ask_failures(args, crew)
    if failures:
        raise BoardError("\n".join(failures))

    fields = {f: getattr(args, f).strip() for f in ASK_FIELDS}
    base = {"ts": _iso(now), **fields}
    labels = crew.get("labels") or {}
    question = {
        "ask": fields["ask"],
        "recommendation": fields["recommendation"],
        "key_title": fields["key_title"],
        "question_label": crew.get("question_label") or "QUESTION",
        "recommendation_label": labels.get("recommendation") or "Recommendation",
    }
    try:
        answer = cold_reader.read(question)
    except cold_reader.ReaderError as exc:
        state.append_question({**base, "outcome": "reader-error", "reason": str(exc)})
        raise BoardError(f"board.py ask: reader-error: {exc}") from None
    reader = {k: answer.get(k) for k in ("decides", "on_yes", "form")}
    reason = _reader_verdict(answer)
    session = fields["session"]

    def asker_lines(board):
        for line in board.get("sessions") or []:
            if isinstance(line, dict) and line.get("name") == session:
                yield line

    if reason is not None:
        text = f"{RETURN_PREFIX}{session}: {reason}"

        def returned(board):
            # Only an empty note or an earlier return is replaced; another note stays and the
            # news item below carries the return.
            for line in asker_lines(board):
                if not str(line.get("note") or "").strip() or _is_return_note(line["note"]):
                    line["note"] = text
            board.setdefault("news", []).append(
                {
                    "id": state.next_id("R", board),
                    "kind": "returned",
                    "title": f"{fields['key']} {text}",
                    "ts": base["ts"],
                }
            )

        state.write_board(
            returned,
            after=lambda _r: state.append_question(
                {**base, "outcome": "returned", "reason": reason, "reader": reader}
            ),
        )
        raise BoardError(f"board.py ask: {text}")

    def posted(board):
        for line in asker_lines(board):
            if _is_return_note(line.get("note")):
                del line["note"]
        qid = state.next_id("Q", board)
        item = {"id": qid, **fields, "since": now.strftime("%Y-%m-%d"), "ts": base["ts"]}
        board.setdefault("owner_queue", []).append(item)
        return qid

    def log_posted(qid):
        state.append_question({"id": qid, **base, "outcome": "posted", "reader": reader})

    print(f"posted {state.write_board(posted, after=log_posted)}")
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
        board.setdefault("news", []).append(item)
        return item

    def log(item):
        state.append_decision(
            {**item, "area": args.area, "decision": args.kind, "key": args.key, "text": text}
        )

    print(json.dumps(state.write_board(mutate, after=log), ensure_ascii=False))
    return 0


def _open_questions(state, board):
    """Ids of `owner_queue` questions no Accept or Deny closed, oldest `since` first."""
    closed = {a.get("id") for a in state.answers() if a.get("answer") in CLOSING}
    items = [
        q
        for q in board.get("owner_queue") or []
        if isinstance(q, dict) and isinstance(q.get("id"), str) and q["id"] not in closed
    ]
    items.sort(key=lambda q: (str(q.get("since") or ""), str(q.get("ts") or "")))
    return [q["id"] for q in items]


def cmd_bundle(state, args, crew, now):
    if not crew_mod.holds_role(crew, "coordinator", os.environ):
        raise BoardError("board.py bundle: only the coordinator bundles")
    _route(state, crew, now)
    date = now.strftime("%Y-%m-%d")

    def mutate(board):
        lines = state.decisions()
        last_marker = max((i for i, d in enumerate(lines) if "bundle" in d), default=-1)
        fresh = [d for d in lines[last_marker + 1 :] if d.get("kind") == "decision"]
        open_ids = _open_questions(state, board)
        escalations = [
            r
            for r in fold_escalations(state.escalations()).values()
            if r["open"] and r["stage"] == "bundle"
        ]
        if not fresh and not open_ids and not escalations:
            return UNCHANGED
        body = [
            f"{area}: {d.get('decision')} {d.get('key')} {d.get('text')}"
            for area in crew_mod.ROLE_KEYS
            for d in fresh
            if d.get("area") == area
        ]
        if open_ids:
            body.append("open: " + ", ".join(open_ids))
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


def cmd_escalation_open(state, args, crew, now):
    failures, parties = _open_failures(args, crew)
    if failures:
        raise BoardError("\n".join(failures))
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
    _print_carry(args.adapter.comment(rec["key"], _story_text(rec)))
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
    _print_carry(args.adapter.comment(rec["key"], text))
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

MOVE_STATES = ("on_hold", "backlog", "in_progress", "in_review")  # `done` comes with its rule
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
    """The Ready gate's story checks on the checkout's plan."""
    try:
        failures, warnings = ready_gate.story_failures(m.plan)
    except OSError as exc:
        return [f"{m.plan}: unreadable ({type(exc).__name__})"]
    m.warnings += warnings
    return failures


def rule_tier(m):
    """The plan-only tier from `risk.command` on `risk.rules_from`; `none` without a command."""
    rel = _rel(m.root, m.plan)
    if rel is None:
        return [f"tier not computed: the plan lies outside {m.root}"]
    result = plan_tier.plan_tier(m.crew, m.root, m.key, rel, fetch=True)
    m.warnings += result.warnings
    if result.failure is not None:
        return [f"tier not computed: {result.failure}"]
    m.extra["tier"] = result.line
    return []


def rule_lenses(m):
    """The `ready-<KEY>` lens verdict, green and bound to the current plan blob."""
    try:
        green, lines = lens_verdict.check(m.root, f"ready-{m.key}")
    except (lens_verdict.UnusableError, OSError) as exc:
        return [f"lens verdict unreadable: {exc}"]
    return [] if green else lines


def rule_reopen(m):
    trigger = (m.args.reopen or "").strip()
    if not trigger:
        return ['on_hold needs --reopen "<trigger>" (what reopens it)']
    m.extra["reopen"] = trigger
    return []


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
    if not status.startswith("approved"):
        return [f"epic {epic} is not approved ({path.name} status: {status or 'none'})"]
    m.extra["epic"] = epic
    return []


SELECT_ONLY = "use board.py select (the Ready gate, the tier and the lenses decide Selected)"


def rule_pulled(m):
    last = m.state.last_rows().get(m.key)
    if last is None or last.get("to") != "selected":
        was = "no row" if last is None else f"its last row is {last.get('to')}"
        return [f"in_progress needs the key's last row to be selected ({was})"]
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


def _linked(key, pr):
    rx = re.compile(r"(?<![A-Z0-9-])" + re.escape(key) + r"(?![0-9])")
    return any(rx.search(str(pr.get(f) or "")) for f in ("headRefName", "title"))


def _view_pr(ref, root):
    """(the PR's JSON, None) or (None, the failure) for one `gh pr view` of `ref`."""
    argv = ["gh", "pr", "view", *_gh_argv(ref), "--json", "state,mergedAt,headRefName,title,url"]
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


# One list of (group, rule) per target state, run in order; the first failing group stops the
# run. `selected` is exactly the Ready gate, the tier and the lenses: no rule asks a human.
ENTRY_RULES = {
    "on_hold": [("reopen", rule_reopen)],
    "backlog": [("epic", rule_epic_approved)],
    "selected": [("ready gate", rule_gate), ("tier", rule_tier), ("lenses", rule_lenses)],
    "in_progress": [("pulled", rule_pulled)],
    "in_review": [("pr", rule_pr_merged_and_linked)],
}


def _caller():
    """The calling session's name for the row's `by`; its id or `unknown` when it has none."""
    try:
        return own_session_name()[0]
    except BoardError:
        return os.environ.get("CLAUDE_CODE_SESSION_ID") or "unknown"


def _transition(state, args, crew, now, target, head):
    """Run the target's entry rules, then write the row, call the adapter once and print the
    row and the `carry:` line; a refusal writes, calls and carries nothing."""
    key = args.key
    failures = _key_failure(crew, key, head.split()[1])
    if failures:
        raise BoardError("\n".join(failures))
    root = _toplevel(head.split()[1])
    plan = (
        Path(args.plan) if getattr(args, "plan", None) else root / "docs/plans" / f"{key}-story.md"
    )
    m = Move(state, key, target, root, plan, crew, args)
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
    adapter = args.adapter
    last = state.last_rows().get(key)
    row = {
        "key": key,
        "from": last.get("to") if last else None,
        "to": target,
        "ts": _iso(now),
        "by": _caller(),
        **m.extra,
        "ticket": adapter.name,
    }
    state.append_transition(row)
    ops = adapter.move(key, status)
    if "tier" in m.extra:
        print(f"tier: {m.extra['tier']}")
    print(json.dumps(row, ensure_ascii=False))
    _print_carry(ops)
    return 0


def cmd_select(state, args, crew, now):
    return _transition(state, args, crew, now, "selected", f"board.py select {args.key}")


def cmd_move(state, args, crew, now):
    head = f"board.py move {args.key} {args.state}"
    if args.state == "selected":
        raise BoardError(f"{head}: refused: {SELECT_ONLY}")
    return _transition(state, args, crew, now, args.state, head)


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


def _add_move_verbs(verbs):
    sel = verbs.add_parser("select", help="move a story to Selected: Ready gate, tier, lenses")
    sel.add_argument("key")
    sel.add_argument("--plan", help="the story plan (default docs/plans/<KEY>-story.md)")
    sel.set_defaults(run=cmd_select)

    mv = verbs.add_parser("move", help="move a story to a state whose entry rule holds")
    mv.add_argument("key")
    mv.add_argument("state", choices=(*MOVE_STATES[:2], "selected", *MOVE_STATES[2:]))
    mv.add_argument("--pr", action="append", metavar="REF", help="in_review: a merged PR (repeat)")
    mv.add_argument("--reopen", metavar="TRIGGER", help="on_hold: what reopens it")
    mv.add_argument("--epic", metavar="EPIC", help="backlog: the approved epic")
    mv.set_defaults(run=cmd_move)

    ck = verbs.add_parser("check", help="board-vs-ticketing drift over a snapshot")
    ck.add_argument("--jira", required=True, metavar="FILE", help="JSON object key → status name")
    ck.set_defaults(run=cmd_check)


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

    s = verbs.add_parser("set", help="write this session's own board line")
    s.add_argument(
        "--for", dest="for_", metavar="NAME", help="another session's line (coordinator)"
    )
    s.add_argument("assignments", nargs="+", metavar="field=value")
    s.set_defaults(run=cmd_set)

    q = verbs.add_parser("ask", help="post a question for the owner after the cold reader")
    for field in ASK_FIELDS:
        q.add_argument("--" + field.replace("_", "-"), dest=field)
    q.set_defaults(run=cmd_ask)

    d = verbs.add_parser("decision", help="record a cut or fence decision of the caller's area")
    d.add_argument("area")
    d.add_argument("kind")
    d.add_argument("--key", required=True)
    d.add_argument("--text", required=True)
    d.set_defaults(run=cmd_decision)

    b = verbs.add_parser("bundle", help="the coordinator's evening bundle as one news item")
    b.set_defaults(run=cmd_bundle)

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

    _add_move_verbs(verbs)
    return p


def main(argv=None, now=None, adapter=None):
    """`adapter` is the tests' FakeAdapter; None means the crew's transport (`adapter_for`)."""
    args = parser().parse_args(argv)
    try:
        crew = None if args.verb == "answer" else load_crew()
        if crew is not None:
            try:
                args.adapter = adapter or ticket_adapter.adapter_for(crew)
            except ValueError as exc:
                raise BoardError(f"crew: {exc}") from None
        return args.run(StateDir(args.board), args, crew, now or _now())
    except BoardError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
