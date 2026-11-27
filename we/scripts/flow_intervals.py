#!/usr/bin/env python3
"""Flow intervals: who in the crew works, who waits on whom, from the state files the plugin writes.

Usage:
  flow_intervals.py [--since 14d] [--until UTC] [--board FILE] [--project NAME] [--from FILE]…
                    [--note TEXT]… [--no-ci]
                    [--jsonl | --html FILE | --json | --page-data | --snapshot [DIR] | --snapshot-path]

Prints one JSON object per interval (JSON Lines, the default) or writes one self-contained HTML
page (``--html``); stderr names every source with the rows it read and the intervals written
(``answers``: the question waits an answer ended; ``transitions``: the story-stage intervals).
``--json`` prints one document ``{schema_version, generated_at, project, window, header, sources,
ci, lanes, now, intervals, gaps, summary}`` (``now``: per lane its interval that reaches the window's
end). ``--snapshot [DIR]`` writes that document and the page as ``flow-<project>.json`` and
``.html`` into DIR (default ``snapshot_dir()``: ``~/.claude/we-state/flow``) through a temp file and
``os.replace``, the JSON naming the page as ``page``; ``--snapshot-path`` prints the JSON's path
and reads nothing else (the ``/flow`` pane's section Crew flow reads it from there). No verb writes
anywhere else but the CI read's cache (``command_center/ci_source.py``, default
``/tmp/we-ci-cache-<uid>``; none with ``--no-ci``).
Write the file; publishing it is the caller's step. ``--since`` and ``--until`` take the forms of
``flow_report.py``. ``--board`` names the board whose logs to read (default: the crew's board,
``crew.resolve_board``); the sampler directory and the day zone come from the crew
(``flow_log.settings``), the worker markers from ``worker_supervisor.state_dir()``. Exit 0 whenever
it printed or wrote, 2 on a usage error (also: ``--project`` names another project than the stamp
beside the board).

Project: one page, one project. Its name (``resolve_project``) is the crew stamp beside the board
(``crew.read_stamp``, the crew id ``board.py`` writes there), else ``crew.crew_id`` of the crew file,
else none; ``--project`` names it when the board carries no stamp. The page's title reads
``Crew flow · <project>``, its header ``Project: <project>``, its JSON block ``project``. The sampler
and the worker markers are one per host and mix every project on it, so each sampled session is
attributed (``Attribution``) and kept only when it belongs, first match wins: its ``session_id``,
else its ``name``, is on a line of this board's ``sessions`` (the most reliable field: a session
writes its board line into its own project's board; a probe carries no cwd, and a board line's
``cwd`` names any repo the crew works in); it is a member of the crew (slug or name); a key of its
probes or of its name (``naming.key``) is one of the project's keys (this board's transitions log
and its lines' ``key``/``keys``/``epic``), which keeps a worker whose marker and starter are gone;
or it is a worker whose starter (marker ``starter_session``/``starter``, else a ``blocked`` event's
``starter``) belongs. Its ``blocked`` events and the locks it holds go with it. A board log's wait
(waits, questions) of a session that fails the same test is dropped too (the rows' keys count
for a session the sampler and the events did not judge; a judged one keeps one verdict): a
board that served several projects before each had its own keeps their old lines. A ``--from`` row
with a ``project`` field of another project is dropped; one without the field is kept. Every drop
is counted in a gap line (source ``project``) and on stderr, never silent.

Row contract (harness-neutral). Required: ``id, start, end, kind, who, source``; optional: ``key``,
``role``, ``waiting_on``; any other field is kept and ignored. Times are UTC ISO with ``Z``; ``id``
is a stable hash of ``who, start, kind``; ``source`` names the file stem the row came from
(``sampler``, ``waits``, ``blocked``, ``questions``, ``marker``, ``from:<file name>``). Kinds written
here: ``working``, ``waiting:human``, ``waiting:<role key>``, ``waiting:ci``, ``blocked``,
``idle-after-end``, ``idle``, ``parked``, ``no-data``, the overlay ``holding:<lock>`` (it may overlap
the lane's other kinds) and ``stage:<to>`` on a story lane. ``RESERVED`` kinds are named in the
tables and the legend when no row has them: ``waiting:lock`` has no producer (it needs a lock-wait event in the
flow log), ``waiting:ci`` has none on a run without CI rows (``--no-ci``, a gap, no session on a key). A
``--from`` file brings rows of any writer: a row without a required field or with an unparseable
time is refused on stderr (``<file>:<line>: <reason>``) and becomes a gap; an unknown kind keeps its
name.

Sources, per session lane (``who`` = the sampler's ``name``):

- ``sample`` probes of the flow log: a stretch between two probes takes the status of its later
  probe: ``busy`` makes it ``working``, anything else a candidate idle stretch. A probe gap over two
  ``interval_s`` ends a run; a session absent between two of its runs while the sampler probed is
  ``parked``. ``locks.<lock>`` ``{held, holder}`` yields ``holding:<lock>`` on the holder's lane from
  the first to the last consecutive probe with that holder; a holder that names no lane gets one of
  its own (group ``lock holders``).
- ``<board stem>-waits.jsonl``: ``since → ended`` as ``waiting:<waiting_on>``.
- ``blocked``/``unblocked`` events of the flow log: ``since → unblocked`` (else the window end);
  with ``waiting_on`` a ``waiting:<waiting_on>``, without it ``blocked`` on the event's ``starter``.
- ``<board stem>-questions.jsonl`` ``posted`` lines joined with ``-answers.jsonl``
  (``question_waits``): the asker waits on ``human`` from the post to the first answer that is not
  ``read``; without one, to the question's first closing line (``board.QUESTION_CLOSED``), else
  the window end.
- worker markers ``<name>.json``: the lane is a worker, its ``starter`` and ``started_at``
  (optional: without it the worker starts at its first probe); a lane without a sampled role that
  starts workers is a master. A marker goes when its worker ends, so an ended worker is known by
  its probes' ``role: worker`` and its starter by the launcher's line in ``launched.jsonl``
  (``worker_launch.record_launch``; it never goes), else by its ``blocked`` events; an ended
  worker with none of them has no starter (the page lists it without a master; stderr counts it,
  ``worker_launch.py backfill-starters`` recovers it).

- ``<board stem>-transitions.jsonl``: per story key one lane in group ``stories``, one ``stage:<to>``
  interval from each move to the next (the last open to the window end; ``done`` draws none);
  ``in_review`` carries ``label: waits on acceptance``. Stage hours count in no ratio and no wait.
- CI (``command_center/ci_source.py``, its docstring owns the queue/run contract and the cache):
  each PR head's ``waiting:ci`` with ``pr``, ``queue_s``, ``run_s`` and ``checks``, on the lane of
  every session whose probes carry the PR's key inside the head's span, as an explicit wait of the
  lowest priority. The header reads ``CI wait: gh check runs, fetched_at <ts>``; gh missing or
  failing is a gap ``no data: ci (gh …)``; ``--no-ci`` asks no gh and reads ``CI wait: off``.

Precedence inside a candidate idle stretch, top wins: an explicit wait (waits row, ``blocked`` event
with ``waiting_on``, open question) → ``waiting:<role key or human>``; a ``blocked`` event without
``waiting_on`` → ``blocked``; a CI head → ``waiting:ci``; a worker after the last busy probe of a run that ended before the
window end → ``idle-after-end`` on its starter; else ``idle``. A busy probe beats every wait. Equal
neighbours (kind, ``waiting_on``, ``key``, ``source``) merge. ``waiting_on`` resolves ``human`` to itself, a
role key through ``crew.roles`` to the lane of that member, a name to the lane of that name; what
names no lane stays as written (a matrix column without an edge).

Gaps: a ``no-data`` row (``who: "-"``) per window day without a sampler file or ``sample`` line,
per missing or unreadable log (``reason`` names it); every other interval is cut out of a sampler
gap, so no lane shows data for a day the sampler did not record.

Efficiency (``summary``): story = Σ ``working`` hours with its key between its first ``selected``
and the next ``in_review`` ÷ those hours; master = ``working`` ÷ alive hours, beside it the hours
other sessions' intervals wait on that master; worker = ``working`` ÷ (marker ``started_at`` → last
probe, clipped to the window, sampler gaps left out; stop = last probe, ±5 min), ``blocked`` and ``idle-after-end`` hours in columns of their
own. ``holding:<lock>`` counts in no ratio. ``format_summary`` is the one formatter both readers
print (hours one decimal, ratios two).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import board as board_mod  # noqa: E402  (owns which outcomes close a question)
import crew as crew_mod  # noqa: E402
import flow_log  # noqa: E402
import worker_supervisor  # noqa: E402

if str(HERE / "command_center") not in sys.path:
    sys.path.insert(0, str(HERE / "command_center"))

ISO = "%Y-%m-%dT%H:%M:%SZ"
REQUIRED = ("id", "start", "end", "kind", "who", "source")
NO_PROJECT = "none (no crew stamp, no crew, no --project)"
RESERVED = ("waiting:ci", "waiting:lock")
OVERLAY = "holding:"
STAGE = "stage:"
ASIDE = (OVERLAY, STAGE)  # kinds beside the session lanes: counted in no ratio, no wait
ACCEPTANCE = "waits on acceptance"
TERMINAL = {"done"}
SCHEMA_VERSION = 1
NOT_WAITING = {"working", "no-data"}
# The kinds of a session lane (module docstring § Row contract), `waiting:<role>` for every role key:
# the Zentrale's swimlanes (`hooks/board/zentrale.ts` GLYPH) draw each; a test binds the two lists.
LANE_KINDS = (
    "working",
    "waiting:human",
    "waiting:<role>",
    "waiting:ci",
    "blocked",
    "idle-after-end",
    "idle",
    "parked",
    "no-data",
)
FIXED_SENTENCE = "Not counted: waiting that only transcripts show; this page has no such source."
CI_LINE = "CI wait: no source yet"


# --- helpers (one home; flow_report imports them) ------------------------------------------------


def parse_ts(value: Any) -> datetime | None:
    """A UTC datetime from the logs' ISO forms (`Z`, milliseconds, minutes only), else None."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        ts = datetime.fromisoformat(text)
    except ValueError:
        # Python 3.9 reads no fraction of other than 3 or 6 digits
        found = re.fullmatch(r"(.*T\d\d:\d\d:\d\d)\.\d+(\+00:00)?", text)
        if not found:
            return None
        try:
            ts = datetime.fromisoformat(found.group(1) + (found.group(2) or ""))
        except ValueError:
            return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def parse_since(text: str, now: datetime) -> datetime:
    found = re.fullmatch(r"(\d+)([dh])", text.strip())
    if found:
        n = int(found.group(1))
        return now - (timedelta(days=n) if found.group(2) == "d" else timedelta(hours=n))
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"--since {text!r}: expected <n>d, <n>h or YYYY-MM-DD"
        ) from None


def read_jsonl_counted(path: Path) -> tuple:
    """`(rows, bad_lines)`: the JSON objects of a JSONL file and the count of the other lines."""
    out, bad = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except ValueError:
                bad += 1
                continue
            if isinstance(item, dict):
                out.append(item)
            else:
                bad += 1
    return out, bad


def read_jsonl(path: Path) -> list:
    return read_jsonl_counted(path)[0]


def locate_board(args, cwd: Path, crew_path: Path | None, crew: dict | None) -> tuple:
    """`(board file, state dir)`: `--board` and its folder, else the crew's board
    (`crew.resolve_board`) and state dir, else `(None, None)`: without a crew the
    default board belongs to no repo."""
    if args.board:
        board = Path(args.board).expanduser()
        return board, board.parent
    if crew_path is None:
        return None, None
    return crew_mod.resolve_board(cwd), crew_mod.state_dir(crew_path, crew)


def resolve_project(board: Path | None, crew_path: Path | None) -> str | None:
    """The project a board belongs to: its crew stamp, else the crew's id, else None."""
    stamp = crew_mod.read_stamp(board) if board is not None else None
    if stamp:
        return stamp
    return crew_mod.crew_id(crew_path) if crew_path is not None else None


def board_sessions(src, board: Path | None) -> list:
    """The `sessions` lines of the board file; a missing or unreadable board is a gap."""
    if board is None:
        return []
    try:
        doc = json.loads(Path(board).read_text(encoding="utf-8"))
    except FileNotFoundError:
        src.gap(
            "project", f"no data: board file {Path(board).name} (no session can be attributed)"
        )
        return []
    except (OSError, ValueError, UnicodeDecodeError):
        src.gap("project", f"source unreadable: board file {Path(board).name}")
        return []
    lines = doc.get("sessions") if isinstance(doc, dict) else None
    return [x for x in lines or [] if isinstance(x, dict)]


class Attribution:
    """Which sessions belong to the project (module docstring § Project)."""

    def __init__(
        self,
        lines: list,
        crew: dict,
        markers: dict,
        events: list,
        transitions: list,
        launched: dict | None = None,
    ):
        self.sids = {x["session_id"] for x in lines if isinstance(x.get("session_id"), str)}
        self.names = {x["name"].casefold() for x in lines if isinstance(x.get("name"), str)}
        for slug, entry in (crew.get("members") or {}).items():
            self.names.add(str(slug).casefold())
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                self.names.add(entry["name"].casefold())
        self.key_rx = re.compile((crew.get("naming") or {}).get("key") or r"[A-Z]+-\d+")
        # the project's keys: the stories its board moved and the keys its lines carry
        self.keys = {t["key"] for t in transitions if isinstance(t.get("key"), str)}
        for x in lines:
            for field in ("key", "keys", "epic"):
                self.keys.update(self.key_rx.findall(str(x.get(field) or "")))
        # a worker's starter: its marker, else its launcher's line, else the last `blocked` event
        self.starter: dict = {}
        for e in sorted(events, key=lambda e: str(e.get("ts"))):
            if isinstance(e.get("name"), str) and isinstance(e.get("starter"), str):
                self.starter[e["name"].casefold()] = (None, e["starter"])
        for name, line in (launched or {}).items():
            sid = (
                line.get("starter_session")
                if isinstance(line.get("starter_session"), str)
                else None
            )
            who = line.get("starter") if isinstance(line.get("starter"), str) else None
            if sid or who:
                self.starter[name.casefold()] = (sid or None, who or None)
        for name, m in markers.items():
            sid = m.get("starter_session") if isinstance(m.get("starter_session"), str) else None
            who = m.get("starter") if isinstance(m.get("starter"), str) else None
            if sid or who:
                self.starter[str(name).casefold()] = (sid, who)
        self.sid_of: dict = {}
        self.keys_of: dict = defaultdict(set)

    def see(self, entry: dict) -> None:
        """Learn a probe's `session_id` and `key` for its name."""
        name = entry["name"].casefold()
        if isinstance(entry.get("session_id"), str):
            self.sid_of.setdefault(name, entry["session_id"])
        if isinstance(entry.get("key"), str):
            self.keys_of[name].add(entry["key"])

    def direct(self, name: str, sid=None, keys=()) -> bool:
        if (sid is not None and sid in self.sids) or name.casefold() in self.names:
            return True
        mine = set(keys) | self.keys_of.get(name.casefold(), set())
        mine.update(self.key_rx.findall(name))
        return bool(mine & self.keys)

    def belongs(self, name: str, keys=(), seen=None) -> bool:
        """On the board, in the crew, on one of its keys, or started by a session that belongs
        (chains followed)."""
        if self.direct(name, self.sid_of.get(name.casefold()), keys):
            return True
        seen = seen or set()
        key = name.casefold()
        if key in seen or key not in self.starter:
            return False
        seen.add(key)
        s_sid, s_name = self.starter[key]
        if s_sid is not None and s_sid in self.sids:
            return True
        return bool(s_name) and self.belongs(s_name, (), seen)


def question_waits(questions: list, answers: list) -> list:
    """`[(posted ts, question line, answer ts or None)]` for every `posted` line: the earliest
    answer per `id` that is not `read`, whatever its time; an answer before the post counts as
    none (the rule of `flow_report.question_rows`)."""
    first: dict = {}
    for a in answers:
        ts = parse_ts(a.get("ts"))
        if ts and isinstance(a.get("id"), str) and a.get("answer") != "read":
            first[a["id"]] = min(first.get(a["id"], ts), ts)
    out = []
    for q in questions:
        ts = parse_ts(q.get("ts"))
        if q.get("outcome") != "posted" or ts is None:
            continue
        answered = first.get(q.get("id"))
        out.append((ts, q, answered if answered is not None and answered >= ts else None))
    return out


def iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime(ISO)


def hours(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 3600


def p90(values: list) -> float | None:
    """Nearest-rank 90th percentile."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)]


def _id(who: str, start: str, kind: str) -> str:
    return hashlib.sha256(f"{who}|{start}|{kind}".encode()).hexdigest()[:16]


def row(start, end, kind, who, source, **extra) -> dict:
    s, e = iso(start), iso(end)
    out = {
        "id": _id(who, s, kind),
        "start": s,
        "end": e,
        "kind": kind,
        "who": who,
        "source": source,
    }
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


# --- sources ------------------------------------------------------------------------------------


class Sources:
    """Reads each source once, counting rows and naming gaps."""

    def __init__(self, since: datetime, until: datetime):
        self.since, self.until = since, until
        self.counts: dict = {}
        self.gaps: list = []
        self.cuts: list = []

    def gap(self, source: str, reason: str, start=None, end=None, cut=False):
        """Name a gap; a `cut` gap (a span the sampler did not record) is cut out of every lane."""
        start, end = start or self.since, end or self.until
        item = {**row(start, end, "no-data", "-", source), "reason": reason}
        item["id"] = _id(source, iso(start), reason)
        self.gaps.append(item)
        if cut:
            self.cuts.append((start, end))

    def log(self, path: Path | None, label: str, source: str) -> list:
        """The rows of one JSONL log, or [] with its gap named."""
        self.counts.setdefault(source, {"rows": 0, "bad": 0, "intervals": 0})
        if path is None:
            self.gap(source, f"no data: {label} (no board)")
            return []
        try:
            rows, bad = read_jsonl_counted(path)
        except FileNotFoundError:
            self.gap(source, f"no data: {label}")
            return []
        except (OSError, UnicodeDecodeError):
            self.gap(source, f"source unreadable: {label}")
            return []
        self.counts[source]["rows"] += len(rows)
        self.counts[source]["bad"] += bad
        if bad:
            self.gap(source, f"unreadable lines: {label} ({bad})")
        return rows


def window_days(since: datetime, until: datetime, tz: str) -> list:
    zone = flow_log._zone(tz)
    first, last = (
        since.astimezone(zone).date(),
        (until - timedelta(seconds=1)).astimezone(zone).date(),
    )
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def day_span(day: date, tz: str, since: datetime, until: datetime) -> tuple:
    zone = flow_log._zone(tz)
    start = datetime(day.year, day.month, day.day, tzinfo=zone).astimezone(timezone.utc)
    end = (datetime(day.year, day.month, day.day, tzinfo=zone) + timedelta(days=1)).astimezone(
        timezone.utc
    )
    return max(start, since), min(end, until)


def read_sampler(src: Sources, log_dir: Path | None, tz: str) -> tuple:
    """`(samples [(ts, line)], events [line])` of the window; a day without a file or a `sample`
    line is a gap."""
    src.counts.setdefault("sampler", {"rows": 0, "bad": 0, "intervals": 0})
    src.counts.setdefault("blocked", {"rows": 0, "bad": 0, "intervals": 0})
    if log_dir is None:
        src.gap("sampler", "no data: sampler (flow.log_dir unset)", cut=True)
        return [], []
    samples, events = [], []
    for day in window_days(src.since, src.until, tz):
        a, b = day_span(day, tz, src.since, src.until)
        path = flow_log.path_for(log_dir, a, tz)
        label = f"sampler {day.isoformat()}"
        try:
            rows, bad = read_jsonl_counted(path)
        except FileNotFoundError:
            src.gap("sampler", f"no data: {label}", a, b, cut=True)
            continue
        except (OSError, UnicodeDecodeError):
            src.gap("sampler", f"source unreadable: {label}", a, b, cut=True)
            continue
        if bad:
            src.gap("sampler", f"unreadable lines: {label} ({bad})")
        src.counts["sampler"]["bad"] += bad
        found = False
        for line in rows:
            ts = flow_log.parse_ts(line.get("ts"))
            if ts is None:
                continue
            if line.get("type") == "sample":
                found = True
                if src.since <= ts <= src.until:
                    samples.append((ts, line))
                    src.counts["sampler"]["rows"] += 1
            elif line.get("type") in ("blocked", "unblocked"):
                events.append(line)
                src.counts["blocked"]["rows"] += 1
        if not found:
            src.gap("sampler", f"no data: {label}", a, b, cut=True)
    samples.sort(key=lambda x: x[0])
    return samples, events


def read_markers(src: Sources, state_dir: Path | None) -> dict:
    """`{name: marker}` of the worker markers `<name>.json` (the supervisor's side files left out)."""
    src.counts.setdefault("marker", {"rows": 0, "bad": 0, "intervals": 0})
    if state_dir is None or not Path(state_dir).is_dir():
        src.gap("marker", "no data: worker markers")
        return {}
    out, missing = {}, 0
    for path in sorted(Path(state_dir).glob("*.json")):
        if path.name.endswith((".settings.json", worker_supervisor.RESUME_SUFFIX)):
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            src.counts["marker"]["bad"] += 1
            continue
        if not isinstance(doc, dict):
            continue
        name = doc.get("name") if isinstance(doc.get("name"), str) else path.stem
        out[name] = doc
        src.counts["marker"]["rows"] += 1
        if not parse_ts(doc.get("started_at")):
            missing += 1
    src.missing_started = missing
    return out


def read_launched(src: Sources, state_dir: Path | None) -> dict:
    """`{name: line}` of the launcher's append-only `launched.jsonl`, read by its owner
    (`worker_launch.read_launched`), the newest line per name; it outlives the marker."""
    import worker_launch  # noqa: PLC0415 (the file's owner)

    src.counts.setdefault("launched", {"rows": 0, "bad": 0, "intervals": 0})
    if state_dir is None:
        return {}
    try:
        rows, bad = worker_launch.read_launched(Path(state_dir))
    except (OSError, UnicodeDecodeError):
        src.gap("launched", "source unreadable: launched.jsonl")
        return {}
    src.counts["launched"]["bad"] += bad
    out: dict = {}
    for line in sorted(rows, key=lambda x: str(x.get("ts"))):
        out[line["name"]] = line
        src.counts["launched"]["rows"] += 1
    return out


def read_foreign(src: Sources, paths: list) -> list:
    out = []
    for p in paths:
        path = Path(p)
        source = f"from:{path.name}"
        src.counts.setdefault(source, {"rows": 0, "bad": 0, "intervals": 0})
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            src.gap(source, f"source unreadable: {path.name}")
            continue
        for n, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except ValueError:
                item = None
            reason = None
            if not isinstance(item, dict):
                reason = "no JSON object"
            else:
                missing = [
                    k for k in REQUIRED if not isinstance(item.get(k), str) or not item.get(k)
                ]
                if missing:
                    reason = f"missing {', '.join(missing)}"
                elif parse_ts(item["start"]) is None or parse_ts(item["end"]) is None:
                    reason = "unparseable start or end"
            if reason:
                print(f"{path}:{n}: {reason}", file=sys.stderr)
                src.counts[source]["bad"] += 1
                src.gap(source, f"refused row: {path.name}:{n} ({reason})")
                continue
            src.counts[source]["rows"] += 1
            out.append({**item, "_file": path.name})
    return out


# --- intervals ----------------------------------------------------------------------------------


def member_names(crew: dict) -> set:
    """The crew members' slugs and names, case-folded: a session named so is a companion lane
    (group `companions`), not a master; `standup.py` splits its master count by the same rule."""
    out = set()
    for slug, entry in (crew.get("members") or {}).items():
        out.add(str(slug).casefold())
        if isinstance(entry, dict) and entry.get("name"):
            out.add(str(entry["name"]).casefold())
    return out


def _lane_lookup(names) -> dict:
    return {n.casefold(): n for n in names}


def resolve(raw, lanes_cf: dict, crew: dict) -> str | None:
    """The target of a wait: `human`, the lane a role key or name points at, else the raw value."""
    if not isinstance(raw, str) or not raw:
        return None
    if raw == "human":
        return raw
    roles = crew.get("roles") or {}
    if raw in roles or raw in crew_mod.ROLE_KEYS:
        slug = roles.get(raw)
        if not isinstance(slug, str):
            return raw
        names = [slug]
        entry = (crew.get("members") or {}).get(slug)
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.append(entry["name"])
        for name in names:
            if name.casefold() in lanes_cf:
                return lanes_cf[name.casefold()]
        return raw
    return lanes_cf.get(raw.casefold(), raw)


def _runs(probes: list, gapmax: float) -> list:
    runs, cur = [], []
    for p in probes:
        if cur and (p["ts"] - cur[-1]["ts"]).total_seconds() > gapmax:
            runs.append(cur)
            cur = []
        cur.append(p)
    if cur:
        runs.append(cur)
    return runs


def _explicit_waits(src, waits, events, questions, answers) -> dict:
    """`{who: [(start, end, prio, kind, raw target, source, key)]}` of every recorded wait."""
    out: dict = defaultdict(list)
    _waits_rows(src, waits, out)
    _blocked_events(src, events, out)
    _question_rows(src, questions, answers, out)
    return out


def _waits_rows(src, waits, out) -> None:
    for w in waits:
        who, since = w.get("session"), parse_ts(w.get("since"))
        if not isinstance(who, str) or since is None:
            src.counts["waits"]["bad"] += 1
            print(
                f"flow_intervals: waits row skipped (session or since unreadable): {w.get('since')!r}",
                file=sys.stderr,
            )
            continue
        end = parse_ts(w.get("ended")) or src.until
        raw = w.get("waiting_on") or "unknown"
        out[who].append((since, end, 0, f"waiting:{raw}", raw, "waits", w.get("key")))


def _blocked_events(src, events, out) -> None:
    unblocked = {}
    for e in events:
        ts = flow_log.parse_ts(e.get("ts"))
        if e.get("type") == "unblocked" and ts:
            unblocked.setdefault((e.get("name"), e.get("since")), ts)
    for e in events:
        if e.get("type") != "blocked" or not isinstance(e.get("name"), str):
            continue
        start = parse_ts(e.get("since")) or flow_log.parse_ts(e.get("ts"))
        if start is None:
            continue
        end = unblocked.get((e["name"], e.get("since"))) or src.until
        raw = e.get("waiting_on")
        if raw:
            out[e["name"]].append((start, end, 0, f"waiting:{raw}", raw, "blocked", e.get("key")))
        else:
            out[e["name"]].append(
                (start, end, 1, "blocked", e.get("starter"), "blocked", e.get("key"))
            )


def _question_rows(src, questions, answers, out) -> None:
    closed: dict = {}
    for q in questions:
        ts = parse_ts(q.get("ts"))
        shuts = q.get("outcome") in board_mod.QUESTION_CLOSED
        if ts and shuts and isinstance(q.get("id"), str):
            closed[q["id"]] = min(closed.get(q["id"], ts), ts)
    for ts, q, answered in question_waits(questions, answers):
        if not isinstance(q.get("session"), str):
            continue
        end = answered
        if answered is not None:
            src.counts["answers"]["intervals"] += 1
        if end is None:
            shut = closed.get(q.get("id"))
            end = shut if shut is not None and shut >= ts else src.until
        out[q["session"]].append((ts, end, 0, "waiting:human", "human", "questions", q.get("key")))


def _stage_rows(src, transitions, since, until, lanes: dict) -> list:
    """The stage rows; per story key one lane in group `stories` (added to `lanes`), one `stage:<to>` interval per
    move from that move to the next (the last open to the window end), clipped to the window; a
    terminal stage (`done`) draws none. `in_review` carries `label` "waits on acceptance"."""
    by_key: dict = defaultdict(list)
    for t in transitions:
        ts = parse_ts(t.get("ts"))
        if isinstance(t.get("key"), str) and ts and isinstance(t.get("to"), str) and t["to"]:
            by_key[t["key"]].append((ts, t["to"]))
    rows = []
    for key, items in sorted(by_key.items()):
        items.sort(key=lambda x: x[0])
        for i, (ts, to) in enumerate(items):
            end = items[i + 1][0] if i + 1 < len(items) else until
            start, end = max(ts, since), min(end, until)
            if to in TERMINAL or start >= end:
                continue
            extra = {"label": ACCEPTANCE} if to == "in_review" else {}
            rows.append(row(start, end, f"{STAGE}{to}", key, "transitions", key=key, **extra))
            src.counts["transitions"]["intervals"] += 1
            lanes.setdefault(key, _bare_lane(key, "stories"))
    return rows


def _aside(kind: str) -> bool:
    return kind.startswith(ASIDE)


def _classify(a, b, waits, tail, starter):
    """`(kind, raw target, source, key)` of an idle piece `[a, b)`."""
    active = [w for w in waits if w[0] <= a and w[1] >= b]
    if active:
        w = min(active, key=lambda w: (w[2], w[0]))
        return w[3], w[4], w[5], w[6], (w[7] if len(w) > 7 else {})
    if tail:
        return "idle-after-end", starter, "sampler", None, {}
    return "idle", None, "sampler", None, {}


def _merge(rows: list) -> list:
    out = []
    for r in sorted(rows, key=lambda r: (r["who"], r["start"])):
        last = out[-1] if out else None
        if (
            last
            and last["who"] == r["who"]
            and last["end"] == r["start"]
            and all(last.get(k) == r.get(k) for k in ("kind", "waiting_on", "key", "source", "pr"))
            and last.get("queue_s") == r.get("queue_s")
        ):
            last["end"] = r["end"]
            continue
        out.append(dict(r))
    for r in out:
        r["id"] = _id(r["who"], r["start"], r["kind"])
    return out


def _cut(rows: list, spans: list) -> list:
    """Every row with the spans the sampler did not record cut out."""
    spans = [s for s in spans if s[0] < s[1]]
    if not spans:
        return rows
    out = []
    for r in rows:
        pieces = [(parse_ts(r["start"]), parse_ts(r["end"]))]
        for ga, gb in spans:
            nxt = []
            for a, b in pieces:
                if a == b:
                    if not ga <= a < gb:
                        nxt.append((a, b))
                    continue
                if b <= ga or a >= gb:
                    nxt.append((a, b))
                    continue
                if a < ga:
                    nxt.append((a, ga))
                if b > gb:
                    nxt.append((gb, b))
            pieces = nxt
        for a, b in pieces:
            piece = dict(r, start=iso(a), end=iso(b))
            piece["id"] = _id(piece["who"], piece["start"], piece["kind"])
            out.append(piece)
    return out


def _lane(name: str, plist: list, ctx: dict) -> tuple:
    """`(rows, lane)` of one sampled session (module docstring § Sources, § Precedence)."""
    marker = ctx["markers"].get(name)
    roles = Counter(p.get("role") for p in plist if p.get("role"))
    worker = marker is not None or "worker" in roles
    role = "worker" if worker else (roles.most_common(1)[0][0] if roles else None)
    if role is None and name.casefold() in ctx["starters"]:
        role = "master"  # it starts workers
    starter = (marker or {}).get("starter") or ctx["event_starters"].get(name)
    runs = _runs(plist, ctx["gapmax"])
    rows: list = []
    for i, run in enumerate(runs):
        rows += _run_rows(name, run, role, starter, ctx)
        if i + 1 < len(runs):
            a, b = run[-1]["ts"], runs[i + 1][0]["ts"]
            if any(a < t < b for t in ctx["global_ts"]):
                rows.append(row(a, b, "parked", name, "sampler", role=role))
    if role == "worker":
        group = "workers"
    elif name.casefold() in ctx["member_cf"]:
        group = "companions"
    else:
        group = "masters" if role == "master" else "other"
    started = (marker or {}).get("started_at")
    return rows, {
        "name": name,
        "role": role,
        "group": group,
        "starter": starter,
        "parent": resolve(starter, ctx["lanes_cf"], ctx["crew"]) if starter else None,
        "session_id": next(
            (p["session_id"] for p in plist if isinstance(p.get("session_id"), str)), None
        ),
        "first": iso(plist[0]["ts"]),
        "last": iso(plist[-1]["ts"]),
        "started_at": started if parse_ts(started) else None,
    }


def _run_rows(name: str, run: list, role, starter, ctx: dict) -> list:
    """The status rows of one run of probes: a stretch takes its later probe's status."""
    lane_waits = ctx["explicit"].get(name, [])
    ended = (ctx["until"] - run[-1]["ts"]).total_seconds() > ctx["gapmax"]
    busy = [k for k, p in enumerate(run) if p.get("status") == "busy"]
    last_busy = busy[-1] if busy else None
    rows = []
    for k in range(1, len(run)):
        a, b, p = run[k - 1]["ts"], run[k]["ts"], run[k]
        if p.get("status") == "busy":
            rows.append(row(a, b, "working", name, "sampler", key=p.get("key"), role=role))
            continue
        tail = role == "worker" and ended and last_busy is not None and k > last_busy
        cuts = sorted({a, b} | {t for w in lane_waits for t in (w[0], w[1]) if a < t < b})
        for x, y in zip(cuts, cuts[1:]):
            kind, raw, source, wkey, extra = _classify(x, y, lane_waits, tail, starter)
            target = resolve(raw, ctx["lanes_cf"], ctx["crew"])
            rows.append(
                row(
                    x,
                    y,
                    kind,
                    name,
                    source,
                    key=wkey or p.get("key"),
                    role=role,
                    waiting_on=target,
                    **extra,
                )
            )
    return rows


CI_PRIO = 9  # below every recorded wait; a busy probe beats it anyway


def _ci_waits(src, ci: dict | None, transitions, probes, crew, explicit) -> str:
    """Lay each PR head's `waiting:ci` on the lanes whose probes carry its key inside the head's
    span (lowest priority: only an idle stretch shows it); returns the page's CI line."""
    src.counts.setdefault("ci", {"rows": 0, "bad": 0, "intervals": 0})
    if ci is None:  # chosen, not missing: named in the header and the JSON's `ci`, no gap row
        return "CI wait: off (--no-ci)"
    if ci.get("state") == "gap":
        src.gap("ci", ci.get("gap") or "no data: ci")
        return f"CI wait: {ci.get('gap') or 'no data: ci'}"
    import ci_source  # noqa: PLC0415 (command_center/, on sys.path below)

    pattern = (crew.get("naming") or {}).get("key") or r"[A-Z]+-\d+"
    for key, heads in ci_source.by_key(ci, transitions, pattern).items():
        for h in heads:
            a, b = parse_ts(h["start"]), parse_ts(h["end"])
            if not (a and b and a < b):
                continue
            src.counts["ci"]["rows"] += 1
            extra = {
                "pr": h["pr"],
                "queue_s": h["queue_s"],
                "run_s": h["run_s"],
                "checks": h["checks"],
            }
            for name, plist in probes.items():
                if any(p.get("key") == key and a <= p["ts"] <= b for p in plist):
                    explicit[name].append((a, b, CI_PRIO, "waiting:ci", "ci", "ci", key, extra))
    return f"CI wait: gh check runs, fetched_at {ci.get('fetched_at')}"


def build(
    board, state_dir, log_dir, tz, crew, since, until, foreign=(), project=None, ci=None
) -> dict:
    """The one builder both readers call: `{intervals, gaps, counts, lanes, transitions, markers,
    interval_s, missing_started, project, attribution, board_lines}`; only rows of `project` (module docstring
    § Project)."""
    crew = crew or crew_mod.DEFAULTS
    src = Sources(since, until)
    src.missing_started = 0
    samples, events = read_sampler(src, log_dir, tz)

    def beside(suffix):
        return board.with_name(f"{board.stem}-{suffix}.jsonl") if board is not None else None

    waits = src.log(beside("waits"), "waits log", "waits")
    transitions = src.log(beside("transitions"), "transitions log", "transitions")
    questions = src.log(beside("questions"), "questions log", "questions")
    answers = src.log(beside("answers"), "answers log", "answers")
    markers = read_markers(src, state_dir)
    launched = read_launched(src, state_dir)
    rows_from = read_foreign(src, list(foreign))
    lines = board_sessions(src, board)
    samples, events, markers, keep, attribution = attribute(
        src, board, crew, samples, events, markers, transitions, launched, lines
    )
    rows_from, foreign_dropped = _drop_foreign(rows_from, project, attribution)
    explicit = _explicit_waits(src, waits, events, questions, answers)
    _drop_logs(explicit, keep, attribution)
    _drop_gaps(src, attribution, foreign_dropped, project)
    # a marker goes when its worker ends; the launcher's line, else the flow log's `blocked`
    # events keep the starter
    event_starters = {
        e["name"]: e["starter"]
        for e in sorted(events, key=lambda e: str(e.get("ts")))
        if isinstance(e.get("name"), str) and isinstance(e.get("starter"), str) and e["starter"]
    }
    for name, line in launched.items():
        if isinstance(line.get("starter"), str) and line["starter"] and keep(name):
            event_starters[name] = line["starter"]

    interval = Counter(int(s.get("interval_s") or 300) for _, s in samples).most_common(1)
    interval_s = interval[0][0] if interval else 300
    gapmax = 2 * interval_s

    probes: dict = defaultdict(list)
    for ts, s in samples:
        for entry in s.get("sessions") or []:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str) and entry["name"]:
                probes[entry["name"]].append({"ts": ts, **entry})
    lanes_cf = _lane_lookup(probes)
    ci_line = _ci_waits(src, ci, transitions, probes, crew, explicit)
    member_cf = member_names(crew)

    ctx = {
        "crew": crew,
        "markers": markers,
        "event_starters": event_starters,
        "starters": {
            str(x).casefold()
            for x in [m.get("starter") for m in markers.values()] + list(event_starters.values())
            if x
        },
        "member_cf": member_cf,
        "lanes_cf": lanes_cf,
        "explicit": explicit,
        "global_ts": [ts for ts, _ in samples],
        "gapmax": gapmax,
        "until": until,
    }
    rows = []
    lanes: dict = {}
    for name, plist in probes.items():
        lane_rows, lanes[name] = _lane(name, plist, ctx)
        rows += lane_rows
    for lane in lanes.values():
        lane["parent"] = lane["parent"] if lane["parent"] in probes else None

    rows += _unsampled_waits(explicit, lanes, ctx, since)

    rows += _holding(samples, gapmax, lanes_cf, lanes)
    rows = _merge(rows)
    rows += _stage_rows(src, transitions, since, until, lanes)
    rows += rows_from
    for r in rows_from:
        lanes.setdefault(r["who"], _bare_lane(r["who"], "foreign", r.get("role")))
    rows = _cut(rows, src.cuts)
    for r in rows:
        key = r["source"] if r["source"] in src.counts else None
        if key and key != "transitions":  # `_stage_rows` counts its own
            src.counts[key]["intervals"] += 1
    return {
        "intervals": rows,
        "gaps": src.gaps,
        "counts": src.counts,
        "lanes": lanes,
        "transitions": transitions,
        "markers": markers,
        "interval_s": interval_s,
        "missing_started": src.missing_started,
        "cuts": src.cuts,
        "since": since,
        "until": until,
        "project": project,
        "attribution": attribution,
        "ci": ci,
        "ci_line": ci_line,
        "board_lines": lines,
    }


def attribute(
    src, board, crew, samples, events, markers, transitions, launched=None, lines=None
) -> tuple:
    """`(samples, events, markers, keep, counts)` with every sampled row of another
    project or of none dropped (module docstring § Project); `keep(name, keys)` judges the lanes
    of the board logs. `lines` are the board's session lines when the caller read them already."""
    if lines is None:
        lines = board_sessions(src, board)
    att = Attribution(lines, crew, markers, events, transitions, launched)
    for _ts, s in samples:
        for e in s.get("sessions") or []:
            if isinstance(e, dict) and isinstance(e.get("name"), str) and e["name"]:
                att.see(e)
    verdict: dict = {}

    def keep(name, keys=()) -> bool:
        if name not in verdict:
            verdict[name] = att.belongs(name, keys)
        return verdict[name]

    out, sampled, kept_rows, dropped_rows, dropped_locks = _filter_samples(samples, keep)
    kept_events = [e for e in events if not isinstance(e.get("name"), str) or keep(e["name"])]
    kept_markers = {n: m for n, m in markers.items() if keep(n)}
    dropped_sessions = sum(1 for n in sampled if not verdict[n])
    counts = {
        "kept_rows": kept_rows,
        "dropped_rows": dropped_rows,
        "kept_sessions": len(sampled) - dropped_sessions,
        "dropped_sessions": dropped_sessions,
        "dropped_events": len(events) - len(kept_events),
        "dropped_locks": dropped_locks,
        "dropped_log_rows": 0,
        "dropped_foreign": 0,
    }
    return out, kept_events, kept_markers, keep, counts


def _drop_logs(explicit: dict, keep, counts: dict) -> None:
    """Drop the recorded waits of a session of another project from the board logs in place."""
    for who in list(explicit):
        if not keep(who, {w[6] for w in explicit[who] if isinstance(w[6], str)}):
            counts["dropped_log_rows"] += len(explicit.pop(who))


def _drop_foreign(rows_from: list, project, counts: dict) -> tuple:
    """`(kept rows, {file: dropped})`: a `--from` row naming another `project` goes."""
    kept, dropped = [], Counter()
    for r in rows_from:
        file = r.pop("_file", None)
        other = r.get("project")
        if isinstance(other, str) and other and other != project:
            dropped[file] += 1
            continue
        kept.append(r)
    counts["dropped_foreign"] = sum(dropped.values())
    return kept, dropped


def _drop_gaps(src, counts: dict, foreign: Counter, project) -> None:
    c = counts
    if c["dropped_rows"] or c["dropped_events"] or c["dropped_locks"] or c["dropped_log_rows"]:
        src.gap(
            "project",
            f"not attributed to {project or NO_PROJECT}: {c['dropped_rows']} sampler rows of "
            f"{c['dropped_sessions']} sessions, {c['dropped_events']} blocked events, "
            f"{c['dropped_locks']} lock probes, {c['dropped_log_rows']} board log waits dropped",
        )
    for file, n in sorted(foreign.items()):
        src.gap("project", f"other project: {n} rows of {file} dropped")


def _filter_samples(samples, keep) -> tuple:
    """`(samples, sampled names, kept rows, dropped rows, dropped lock probes)`: each probe with
    only the sessions and the lock holders `keep` accepts."""
    kept_rows = dropped_rows = dropped_locks = 0
    sampled: set = set()
    out = []
    for ts, s in samples:
        sessions = []
        for e in s.get("sessions") or []:
            if not (isinstance(e, dict) and isinstance(e.get("name"), str) and e["name"]):
                continue
            sampled.add(e["name"])
            if keep(e["name"]):  # `see` recorded its session_id and keys
                sessions.append(e)
                kept_rows += 1
            else:
                dropped_rows += 1
        locks = s.get("locks") if isinstance(s.get("locks"), dict) else {}
        mine = {}
        for lock, held in locks.items():
            holder = held.get("holder") if isinstance(held, dict) else None
            if isinstance(holder, str) and held.get("held") and not keep(holder):
                dropped_locks += 1
                continue
            mine[lock] = held
        out.append((ts, {**s, "sessions": sessions, "locks": mine}))
    return out, sampled, kept_rows, dropped_rows, dropped_locks


def _bare_lane(name: str, group: str, role=None) -> dict:
    return {"name": name, "role": role, "group": group, "starter": None, "parent": None}


def _unsampled_waits(explicit: dict, lanes: dict, ctx: dict, since) -> list:
    """The recorded waits of a session the sampler never probed, as written."""
    rows = []
    for name, lw in explicit.items():
        if name in lanes:
            continue
        for w_start, w_end, _prio, kind, raw, source, key, *_extra in lw:
            start, end = max(w_start, since), min(w_end, ctx["until"])
            target = resolve(raw, ctx["lanes_cf"], ctx["crew"])
            if start < end:
                rows.append(row(start, end, kind, name, source, key=key, waiting_on=target))
        lanes[name] = _bare_lane(name, "other")
    return rows


def _holding(samples, gapmax, lanes_cf, lanes) -> list:
    out: list = []
    open_: dict = {}

    def close(lock):
        holder, first, last = open_.pop(lock)
        who = lanes_cf.get(holder.casefold())
        if who is None:
            who = holder
            lanes.setdefault(who, _bare_lane(who, "lock holders"))
        out.append(row(first, last, f"{OVERLAY}{lock}", who, "sampler"))

    prev = None
    for ts, s in samples:
        locks = s.get("locks") if isinstance(s.get("locks"), dict) else {}
        for lock in list(open_):
            held = locks.get(lock) if isinstance(locks.get(lock), dict) else {}
            same = held.get("held") and held.get("holder") == open_[lock][0]
            if not same or (prev and (ts - prev).total_seconds() > gapmax):
                close(lock)
        for lock, held in locks.items():
            if isinstance(held, dict) and held.get("held") and isinstance(held.get("holder"), str):
                if lock in open_:
                    open_[lock] = (open_[lock][0], open_[lock][1], ts)
                else:
                    open_[lock] = (held["holder"], ts, ts)
        prev = ts
    for lock in list(open_):
        close(lock)
    return out


# --- summary ------------------------------------------------------------------------------------


def _h(r) -> float:
    return hours(parse_ts(r["start"]), parse_ts(r["end"]))


def _clip_h(r, a, b) -> float:
    s, e = max(parse_ts(r["start"]), a), min(parse_ts(r["end"]), b)
    return max(0.0, hours(s, e))


def _stories(rows, transitions, since, until) -> list:
    """Per story in review in the window: working hours with its key ÷ selected → in_review."""
    stories = []
    by_key: dict = defaultdict(list)
    for t in transitions:
        ts = parse_ts(t.get("ts"))
        if isinstance(t.get("key"), str) and ts and isinstance(t.get("to"), str):
            by_key[t["key"]].append((ts, t["to"]))
    for key, items in sorted(by_key.items()):
        items.sort(key=lambda x: x[0])
        sel = next((ts for ts, to in items if to == "selected"), None)
        rev = next((ts for ts, to in items if to == "in_review" and sel and ts > sel), None)
        if sel is None or rev is None or not (since <= rev <= until):
            continue
        work = [r for r in rows if r["kind"] == "working" and r.get("key") == key]
        w = sum(_clip_h(r, sel, rev) for r in work)
        lead = hours(sel, rev)
        stories.append(
            {
                "key": key,
                "working_h": w,
                "lead_h": lead,
                "ratio": w / lead if lead else None,
                "sessions": len({r["who"] for r in work if _clip_h(r, sel, rev) > 0}),
            }
        )

    return stories


def _waiting(rows) -> dict:
    """Per kind that is no work: n, hours, median, p90; the reserved kinds named without a source."""
    waiting: dict = {}
    by_kind: dict = defaultdict(list)
    for r in rows:
        if r["kind"] in NOT_WAITING or _aside(r["kind"]):
            continue
        by_kind[r["kind"]].append(_h(r))
    for kind in sorted(set(by_kind) | set(RESERVED)):
        vals = by_kind.get(kind, [])
        waiting[kind] = {
            "n": len(vals),
            "hours": sum(vals),
            "median": statistics.median(vals) if vals else None,
            "p90": p90(vals),
            "no_source": kind in RESERVED and not vals,
        }

    return waiting


def summary(built: dict) -> dict:
    """The numbers both readers show (module docstring § Efficiency)."""
    rows, lanes = built["intervals"], built["lanes"]
    since, until = built["since"], built["until"]
    by_who: dict = defaultdict(list)
    for r in rows:
        by_who[r["who"]].append(r)

    stories = _stories(rows, built["transitions"], since, until)

    waited_on: dict = defaultdict(float)
    for r in rows:
        if r.get("waiting_on") and r["waiting_on"] != r["who"] and not _aside(r["kind"]):
            waited_on[r["waiting_on"]] += _h(r)

    masters, workers = [], []
    alive_kinds = lambda k: k not in ("parked", "no-data") and not _aside(k)  # noqa: E731
    for name in sorted(lanes):
        lane = lanes[name]
        mine = by_who.get(name, [])
        work = sum(_h(r) for r in mine if r["kind"] == "working")
        if lane["group"] == "masters":
            alive = sum(_h(r) for r in mine if alive_kinds(r["kind"]))
            masters.append(
                {
                    "who": name,
                    "working_h": work,
                    "alive_h": alive,
                    "ratio": work / alive if alive else None,
                    "waited_on_h": waited_on.get(name, 0.0),
                }
            )
        elif lane["group"] == "workers" and lane.get("first"):
            start = max(parse_ts(lane.get("started_at")) or parse_ts(lane["first"]), since)
            stop = min(parse_ts(lane["last"]), until)
            span = max(0.0, hours(start, stop)) - sum(
                max(0.0, hours(max(a, start), min(b, stop))) for a, b in built.get("cuts", [])
            )
            workers.append(
                {
                    "who": name,
                    "starter": lane.get("starter"),
                    "working_h": work,
                    "span_h": span,
                    "ratio": work / span if span > 0 else None,
                    "blocked_h": sum(_h(r) for r in mine if r["kind"] == "blocked"),
                    "idle_after_end_h": sum(_h(r) for r in mine if r["kind"] == "idle-after-end"),
                    "start_from": "marker" if lane.get("started_at") else "first probe",
                }
            )

    waiting = _waiting(rows)

    locks: dict = defaultdict(lambda: {"hours": 0.0, "n": 0})
    for r in rows:
        if r["kind"].startswith(OVERLAY):
            item = locks[(r["kind"][len(OVERLAY) :], r["who"])]
            item["hours"] += _h(r)
            item["n"] += 1

    waits = [
        r
        for r in rows
        if r.get("waiting_on") or r["kind"].startswith("waiting:") or r["kind"] == "blocked"
    ]
    waits = [r for r in waits if not _aside(r["kind"])]
    top = sorted(waits, key=lambda r: (-_h(r), r["start"], r["who"]))[:10]

    matrix: dict = defaultdict(lambda: defaultdict(float))
    for r in rows:
        if r.get("waiting_on") and not _aside(r["kind"]):
            matrix[r["who"]][r["waiting_on"]] += _h(r)

    return {
        "window": f"{iso(since)} → {iso(until)}",
        "interval_s": built["interval_s"],
        "stories": stories,
        "masters": masters,
        "workers": workers,
        "waiting": waiting,
        "locks": [{"lock": k[0], "holder": k[1], **v} for k, v in sorted(locks.items())],
        "top": [
            {
                "kind": r["kind"],
                "who": r["who"],
                "waiting_on": r.get("waiting_on"),
                "hours": _h(r),
                "start": r["start"],
            }
            for r in top
        ],
        "matrix": {w: dict(t) for w, t in sorted(matrix.items())},
    }


def fh(value) -> str:
    return "-" if value is None else f"{value:.1f}"


def fr(value) -> str:
    return "-" if value is None else f"{value:.2f}"


def _median_p90(vals) -> tuple:
    vals = [v for v in vals if v is not None]
    return (fr(statistics.median(vals)) if vals else "-"), fr(p90(vals))


def format_summary(s: dict) -> dict:
    """Every number as the string both readers print: hours one decimal, ratios two."""
    window = s["window"]
    stories = [
        {
            "key": x["key"],
            "working_h": fh(x["working_h"]),
            "lead_h": fh(x["lead_h"]),
            "ratio": fr(x["ratio"]),
            "sessions": str(x["sessions"]),
        }
        for x in s["stories"]
    ]
    masters = [
        {
            "who": x["who"],
            "working_h": fh(x["working_h"]),
            "alive_h": fh(x["alive_h"]),
            "ratio": fr(x["ratio"]),
            "waited_on_h": fh(x["waited_on_h"]),
        }
        for x in s["masters"]
    ]
    workers = [
        {
            "who": x["who"],
            "starter": x["starter"] or "-",
            "working_h": fh(x["working_h"]),
            "span_h": fh(x["span_h"]),
            "ratio": fr(x["ratio"]),
            "blocked_h": fh(x["blocked_h"]),
            "idle_after_end_h": fh(x["idle_after_end_h"]),
            "start": "start = marker" if x["start_from"] == "marker" else "start = first probe",
        }
        for x in s["workers"]
    ]
    waiting = {}
    for kind, v in s["waiting"].items():
        waiting[kind] = (
            {"n": "n/a", "hours": "n/a (no source yet)", "median": "-", "p90": "-"}
            if v["no_source"]
            else {
                "n": str(v["n"]),
                "hours": fh(v["hours"]),
                "median": fh(v["median"]),
                "p90": fh(v["p90"]),
            }
        )
    tables = {
        "stories": {
            "rows": stories,
            "n": str(len(stories)),
            "window": f"{window}; selected → in_review",
            "median": _median_p90([x["ratio"] for x in s["stories"]])[0],
            "p90": _median_p90([x["ratio"] for x in s["stories"]])[1],
        },
        "masters": {
            "rows": masters,
            "n": str(len(masters)),
            "window": f"{window}; alive = probed",
            "median": _median_p90([x["ratio"] for x in s["masters"]])[0],
            "p90": _median_p90([x["ratio"] for x in s["masters"]])[1],
        },
        "workers": {
            "rows": workers,
            "n": str(len(workers)),
            "window": f"{window}; stop = last probe, ±5 min",
            "median": _median_p90([x["ratio"] for x in s["workers"]])[0],
            "p90": _median_p90([x["ratio"] for x in s["workers"]])[1],
        },
    }
    return {
        "window": window,
        "sample_error": f"one probe every {s['interval_s']} s: each bar edge ±{round(s['interval_s'] / 60)} min",
        **tables,
        "waiting": waiting,
        "locks": [
            {"lock": x["lock"], "holder": x["holder"], "hours": fh(x["hours"]), "n": str(x["n"])}
            for x in s["locks"]
        ],
        "top": [
            {
                "kind": x["kind"],
                "who": x["who"],
                "waiting_on": x["waiting_on"] or "-",
                "hours": fh(x["hours"]),
                "start": x["start"],
            }
            for x in s["top"]
        ],
        "matrix": {w: {t: fh(h) for t, h in row_.items()} for w, row_ in s["matrix"].items()},
    }


# --- the page -----------------------------------------------------------------------------------


def page_data(built: dict, notes=()) -> dict:
    raw = summary(built)
    fmt = format_summary(raw)
    lanes = built["lanes"]
    intervals = []
    for r in built["intervals"]:
        item = dict(r)
        target = r.get("waiting_on")
        item["edge_to"] = target if target in lanes and target != r["who"] else None
        intervals.append(item)
    return {
        "project": built.get("project") or NO_PROJECT,
        "attribution": built.get("attribution"),
        "window": {"since": iso(built["since"]), "until": iso(built["until"])},
        "interval_s": built["interval_s"],
        "header": [fmt["sample_error"], FIXED_SENTENCE, built.get("ci_line") or CI_LINE, *notes],
        "gaps": [
            {"reason": g["reason"], "start": g["start"], "end": g["end"], "source": g["source"]}
            for g in built["gaps"]
        ],
        "gap_rows": built["gaps"],
        "lanes": [lanes[k] for k in sorted(lanes)],
        "intervals": intervals,
        "reserved": [k for k in RESERVED if raw["waiting"].get(k, {}).get("no_source")],
        "summary": fmt,
    }


def _text(value) -> str | None:
    """A board line's free-text field as one stripped line, None when absent or empty."""
    return " ".join(value.split()) or None if isinstance(value, str) else None


def now_rows(built: dict) -> list:
    """Per lane its last interval when it reaches the window's end (within two probe periods):
    who works and who waits now, since when and on whom; story lanes give their stage. Overlays
    and lanes gone before the end are left out. A lane with a board line (by name, else by
    `session_id`) carries that line's `topic` and its `now` as `board_now` (the document's own
    `now` is this list); without one both are None."""
    by_name: dict = {}
    by_sid: dict = {}
    for x in built.get("board_lines") or []:
        if isinstance(x.get("name"), str):
            by_name.setdefault(x["name"].casefold(), x)
        if isinstance(x.get("session_id"), str):
            by_sid.setdefault(x["session_id"], x)
    edge = iso(built["until"] - timedelta(seconds=2 * built["interval_s"]))
    last: dict = {}
    for r in sorted(built["intervals"], key=lambda r: r["end"]):
        if not r["kind"].startswith(OVERLAY) and r["who"] != "-":
            last[r["who"]] = r
    out = []
    for r in last.values():
        if r["end"] < edge:
            continue
        lane = built["lanes"].get(r["who"]) or {}
        line = by_name.get(r["who"].casefold()) or by_sid.get(lane.get("session_id")) or {}
        out.append(
            {
                "who": r["who"],
                "group": lane.get("group"),
                "starter": lane.get("starter"),
                "kind": r["kind"],
                "since": r["start"],
                "waiting_on": r.get("waiting_on"),
                "key": r.get("key"),
                "label": r.get("label"),
                "topic": _text(line.get("topic")),
                "board_now": _text(line.get("now")),
            }
        )
    return sorted(out, key=lambda x: (str(x["group"]), x["since"], x["who"]))


def json_doc(built: dict, notes=(), generated_at: datetime | None = None) -> dict:
    """`--json`: one document, its field list pinned by `test_flow_intervals_json_snapshot`."""
    data = page_data(built, notes)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso(generated_at or datetime.now(timezone.utc)),
        "project": data["project"],
        "window": data["window"],
        "header": data["header"],
        "sources": built["counts"],
        "ci": built.get("ci")
        or {"state": "off", "gap": "ci: off (--no-ci)", "fetched_at": None, "prs": []},
        "lanes": data["lanes"],
        "now": now_rows(built),
        "intervals": sorted(built["intervals"], key=lambda r: (r["who"], r["start"], r["kind"])),
        "gaps": built["gaps"],
        "summary": data["summary"],
    }


def snapshot_dir() -> Path:
    """Where the `/flow` pane reads the last snapshot: `~/.claude/we-state/flow`."""
    return Path.home() / ".claude" / "we-state" / "flow"


def snapshot_paths(directory: Path, project: str | None) -> tuple:
    """`(json, html)` of the snapshot of `project` in `directory`."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", project or "none").strip("-.") or "none"
    return directory / f"flow-{slug}.json", directory / f"flow-{slug}.html"


def write_snapshot(directory: Path, built: dict, notes=()) -> tuple:
    """Both snapshot files through a temp file and `os.replace`: a reader never sees half."""
    directory.mkdir(parents=True, exist_ok=True)
    js, page = snapshot_paths(directory, built.get("project"))
    doc = json_doc(built, notes)
    doc["page"] = str(page)
    for path, text in (
        (page, render_page(page_data(built, notes))),
        (js, json.dumps(doc, ensure_ascii=False, indent=1)),
    ):
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    return js, page


def embed_json(data: dict, escape: bool = True) -> str:
    """JSON for a `<script type="application/json">` block: `<`, `>`, `&` as JSON escapes."""
    text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    if escape:
        text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return text


def render_page(data: dict, escape: bool = True) -> str:
    parts = {
        "TITLE": html.escape(f"Crew flow · {data.get('project') or NO_PROJECT}"),
        "CSS": CSS,
        "DATA": embed_json(data, escape),
        "JS": JS,
    }
    # one pass: a placeholder inside a filled-in value (a project name, a key) stays text
    return re.sub(r"/\*(TITLE|CSS|DATA|JS)\*/", lambda m: parts[m.group(1)], PAGE)


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>/*TITLE*/</title>
<style>/*CSS*/</style></head>
<body><main id="app"></main>
<script type="application/json" id="flow-data">/*DATA*/</script>
<script>/*JS*/</script>
</body></html>
"""

CSS = """
:root{--bg:#fbfbf9;--fg:#1d1d1b;--mut:#6b6b66;--line:#e2e2dc;--card:#fff;
--working:#2f9e5b;--human:#d1453b;--coord:#e08a1e;--role:#c9a227;--ci:#2a8fa8;--blocked:#8a4fc7;
--iae:#8c2f2f;--idle:#cfcfc8;--parked:#ececE6;--unknown:#9a9a9a;--hold:#3b6fd1;--gap:#f3e3c3}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#151514;--fg:#ececea;
--mut:#9b9b95;--line:#30302d;--card:#1d1d1b;--idle:#45453f;--parked:#2a2a27;--gap:#4a3d22}}
:root[data-theme="dark"]{--bg:#151514;--fg:#ececea;--mut:#9b9b95;--line:#30302d;--card:#1d1d1b;
--idle:#45453f;--parked:#2a2a27;--gap:#4a3d22}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,-apple-system,sans-serif}
main{max-width:1200px;margin:0 auto;padding:12px 16px 120px}
h1{font-size:20px;margin:4px 0}h2{font-size:16px;margin:20px 0 6px}
.mut{color:var(--mut)}.hdr p{margin:2px 0}.gapline{background:var(--gap);padding:2px 6px;border-radius:4px;margin:2px 0}
.ctl{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}
.ctl button{font:inherit;padding:4px 10px;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:6px}
.ctl button.on{border-color:var(--fg)}
.chart{display:flex;border:1px solid var(--line);border-radius:6px;background:var(--card)}
.labels{flex:0 0 auto;max-width:42%;border-right:1px solid var(--line);z-index:2;background:var(--card)}
.scroll{flex:1 1 auto;overflow-x:auto;position:relative}
.track{position:relative}
.lab,.lane{height:24px;border-bottom:1px solid var(--line)}
.lab{padding:3px 6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12px;cursor:default}
.lab.grp{font-weight:600;background:var(--bg)}.lane.grp{background:var(--bg)}
.lab.fold{cursor:pointer;color:var(--mut)}
.lane{position:relative}
.bar{position:absolute;top:4px;height:15px;border-radius:2px;min-width:1px;cursor:pointer}
.hold{position:absolute;bottom:1px;height:3px;background:repeating-linear-gradient(90deg,var(--hold) 0 4px,transparent 4px 7px)}
.edge{position:absolute;width:1px;background:var(--mut);opacity:.6;pointer-events:none}
.axis{height:20px;position:relative;border-bottom:1px solid var(--line);font-size:11px;color:var(--mut)}
.tick{position:absolute;top:2px;padding-left:3px;border-left:1px solid var(--line);height:18px;white-space:nowrap}
.k-working{background:var(--working)}.k-waiting-human{background:var(--human)}
.k-waiting-coordinator{background:var(--coord)}.k-waiting-role{background:var(--role)}.k-waiting-ci{background:var(--ci)}
.k-blocked{background:var(--blocked)}.k-idle-after-end{background:var(--iae)}
.k-idle{background:var(--idle)}.k-parked{background:var(--parked);border:1px dashed var(--line)}
.k-unknown{background:var(--unknown)}
.k-stage{background:var(--idle);border:1px solid var(--working)}.k-stage-review{background:var(--human);opacity:.6}
.legend{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;margin:8px 0}
.legend span{display:inline-flex;align-items:center;gap:4px}.sw{width:12px;height:10px;display:inline-block;border-radius:2px}
.tip{position:fixed;left:8px;right:8px;bottom:8px;background:var(--card);border:1px solid var(--fg);border-radius:8px;
padding:8px 10px;font-size:13px;display:none;z-index:5;max-width:520px;margin:0 auto}
.tbl{overflow-x:auto}
table{border-collapse:collapse;font-size:12px;min-width:100%}
th,td{border-bottom:1px solid var(--line);padding:3px 6px;text-align:left;white-space:nowrap}
th{cursor:pointer;position:sticky;top:0;background:var(--card)}
td.num,th.num{text-align:right}
"""

JS = r"""
(function(){
var D=JSON.parse(document.getElementById('flow-data').textContent);
var app=document.getElementById('app');
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=String(text);return e;}
function add(p,c){p.appendChild(c);return c;}
function t(s){return Date.parse(s);}
var T0=t(D.window.since),T1=t(D.window.until),SPAN=Math.max(1,T1-T0);
function fmtT(ms){var d=new Date(ms);return d.toISOString().slice(5,16).replace('T',' ');}
function dur(ms){var m=Math.round(ms/60000);return m>=60?(Math.floor(m/60)+' h '+(m%60)+' min'):(m+' min');}
function kcls(k){if(k==='working'||k==='blocked'||k==='idle-after-end'||k==='idle'||k==='parked')return 'k-'+k;
 if(k==='waiting:human')return 'k-waiting-human';if(k==='waiting:coordinator')return 'k-waiting-coordinator';if(k==='waiting:ci')return 'k-waiting-ci';
 if(k.indexOf('waiting:')===0)return 'k-waiting-role';if(k==='stage:in_review')return 'k-stage-review';
 if(k.indexOf('stage:')===0)return 'k-stage';return 'k-unknown';}
var hdr=add(app,el('div','hdr'));
add(hdr,el('h1',null,'Crew flow \u00b7 '+D.project));
add(hdr,el('p',null,'Project: '+D.project));
add(hdr,el('p','mut','Window '+D.window.since+' \u2192 '+D.window.until+' (UTC)'));
D.header.forEach(function(s){add(hdr,el('p',null,s));});
D.gaps.forEach(function(g){add(hdr,el('p','gapline',g.reason));});
var byWho={};D.intervals.forEach(function(r){(byWho[r.who]=byWho[r.who]||[]).push(r);});
var lanes={};D.lanes.forEach(function(l){lanes[l.name]=l;});
var open={};
function order(){var out=[];var groups=[['masters','Masters'],['companions','Companions'],['other','Other sessions'],
 ['workers','Workers without a master on the page'],['stories','Stories (stage)'],['lock holders','Lock holders'],['foreign','Foreign rows']];
 var kids={};D.lanes.forEach(function(l){if(l.group==='workers'&&l.parent&&lanes[l.parent])(kids[l.parent]=kids[l.parent]||[]).push(l.name);});
 groups.forEach(function(g){var names=D.lanes.filter(function(l){return l.group===g[0]&&byWho[l.name]&&!(g[0]==='workers'&&l.parent&&lanes[l.parent]);}).map(function(l){return l.name;});
  if(!names.length)return;out.push({grp:g[1]});
  names.forEach(function(n){out.push({lane:n});var k=kids[n];if(k&&k.length){out.push({fold:n,count:k.length});
   if(open[n])k.forEach(function(c){if(byWho[c])out.push({lane:c,child:true});});}});});
 return out;}
var zoom=3*86400000;
var ctl=add(app,el('div','ctl'));
[['day',86400000],['3 days',3*86400000],['14 days',14*86400000]].forEach(function(z){var b=add(ctl,el('button',null,z[0]));
 b.type='button';b.onclick=function(){zoom=z[1];draw();};b.dataset.z=z[1];});
var legend=add(app,el('div','legend'));
[['working','working'],['waiting:human','waiting: human'],['waiting:coordinator','waiting: coordinator'],['waiting:product','waiting: other role'],['waiting:ci','waiting: CI'],
 ['blocked','blocked'],['idle-after-end','idle after end'],['idle','idle'],['parked','parked'],['stage:in_progress','story stage'],
 ['stage:in_review','waits on acceptance'],['x','other kind']].forEach(function(k){
 var s=add(legend,el('span'));add(s,el('i','sw '+kcls(k[0])));add(s,document.createTextNode(k[1]));});
var hs=add(legend,el('span'));add(hs,el('i','sw hold'));hs.firstChild.style.position='static';add(hs,document.createTextNode('holding a lock'));
D.reserved.forEach(function(k){add(legend,el('span','mut',k+': no source yet'));});
var chart=add(app,el('div','chart'));var labels=add(chart,el('div','labels'));var scroll=add(chart,el('div','scroll'));
var tip=add(document.body,el('div','tip'));
function show(r){tip.textContent='';var a=t(r.start),b=t(r.end);
 [['kind',r.kind],['who',r.who],['from',fmtT(a)+' \u2192 '+fmtT(b)],['duration',dur(b-a)],['key',r.key||'-'],
  ['waiting on',r.waiting_on||r.label||'-'],['source',r.source]].forEach(function(p){var d=add(tip,el('div'));add(d,el('b',null,p[0]+': '));add(d,document.createTextNode(p[1]));});
 tip.style.display='block';}
document.addEventListener('click',function(e){if(!e.target.classList||!e.target.classList.contains('bar'))tip.style.display='none';});
function draw(){Array.prototype.forEach.call(ctl.children,function(b){b.className=(+b.dataset.z===zoom)?'on':'';});
 labels.textContent='';scroll.textContent='';
 var vw=Math.max(200,scroll.clientWidth||300);var W=Math.max(vw,Math.round(vw*SPAN/zoom));
 function x(ms){return (Math.min(Math.max(ms,T0),T1)-T0)/SPAN*W;}
 var track=add(scroll,el('div','track'));track.style.width=W+'px';
 add(labels,el('div','axis'));var axis=add(track,el('div','axis'));
 var step=zoom<=86400000?6*3600000:86400000;for(var m=Math.ceil(T0/step)*step;m<T1;m+=step){var k=add(axis,el('div','tick',fmtT(m)));k.style.left=x(m)+'px';}
 var rows=order(),ypos={},y=20;
 rows.forEach(function(it){
  if(it.grp){add(labels,el('div','lab grp',it.grp));add(track,el('div','lane grp'));y+=25;return;}
  if(it.fold){var f=add(labels,el('div','lab fold',(open[it.fold]?'\u25be ':'\u25b8 ')+it.count+' workers'));
   f.onclick=function(){open[it.fold]=!open[it.fold];draw();};add(track,el('div','lane'));y+=25;return;}
  var name=it.lane;var lab=add(labels,el('div','lab',(it.child?'\u2003':'')+name));lab.title=name;
  var lane=add(track,el('div','lane'));ypos[name]=y+12;y+=25;
  byWho[name].forEach(function(r){var a=t(r.start),b=t(r.end);if(b<T0||a>T1)return;
   if(r.kind.indexOf('holding:')===0){var h=add(lane,el('div','hold'));h.style.left=x(a)+'px';h.style.width=Math.max(2,x(b)-x(a))+'px';
    h.title=r.kind;return;}
   var bar=add(lane,el('div','bar '+kcls(r.kind)));bar.style.left=x(a)+'px';bar.style.width=Math.max(1,x(b)-x(a))+'px';
   bar.onclick=function(){show(r);};bar.onmouseenter=function(){show(r);};});});
 D.intervals.forEach(function(r){if(!r.edge_to||ypos[r.who]==null||ypos[r.edge_to]==null)return;
  if(t(r.end)-t(r.start)<600000)return;var a=ypos[r.who],b=ypos[r.edge_to];
  var e=add(track,el('div','edge'));e.style.left=x(t(r.start))+'px';e.style.top=Math.min(a,b)+'px';e.style.height=Math.abs(a-b)+'px';});
 scroll.scrollLeft=W;}
function table(title,note,cols,rows){add(app,el('h2',null,title));if(note)add(app,el('p','mut',note));
 if(!rows.length){add(app,el('p','mut','none in the window'));return;}
 var wrap=add(app,el('div','tbl'));var tb=add(wrap,el('table'));var head=add(add(tb,el('thead')),el('tr'));var body=add(tb,el('tbody'));
 var sortBy=null,dir=1;
 function fill(){body.textContent='';var rs=rows.slice();if(sortBy!=null)rs.sort(function(p,q){var a=p[sortBy],b=q[sortBy];
  var na=parseFloat(a),nb=parseFloat(b);if(!isNaN(na)&&!isNaN(nb))return (na-nb)*dir;return String(a).localeCompare(String(b))*dir;});
  rs.forEach(function(r){var tr=add(body,el('tr'));cols.forEach(function(c){add(tr,el('td',c[2]?'num':null,r[c[0]]));});});}
 cols.forEach(function(c){var th=add(head,el('th',c[2]?'num':null,c[1]));th.onclick=function(){dir=(sortBy===c[0])?-dir:-1;sortBy=c[0];fill();};});
 fill();}
var S=D.summary;
var targets={};Object.keys(S.matrix).forEach(function(w){Object.keys(S.matrix[w]).forEach(function(k){targets[k]=1;});});
var tcols=Object.keys(targets).sort();
table('Who waits on whom (hours)',null,[['who','waiting']].concat(tcols.map(function(k){return [k,k,1];})),
 Object.keys(S.matrix).map(function(w){var r={who:w};tcols.forEach(function(k){r[k]=S.matrix[w][k]||'';});return r;}));
table('Top ten single waits','the sources do not record who ended a wait',[['kind','kind'],['who','who'],['waiting_on','waited on'],['hours','hours',1],['start','start']],S.top);
table('Story efficiency','n '+S.stories.n+' \u00b7 median '+S.stories.median+' \u00b7 '+S.stories.window,
 [['key','key'],['ratio','working \u00f7 lead',1],['working_h','working h',1],['lead_h','lead h',1],['sessions','sessions',1]],S.stories.rows);
table('Master efficiency','n '+S.masters.n+' \u00b7 median '+S.masters.median+' \u00b7 '+S.masters.window,
 [['who','master'],['ratio','working \u00f7 alive',1],['working_h','working h',1],['alive_h','alive h',1],['waited_on_h','others wait on it h',1]],S.masters.rows);
table('Worker efficiency','n '+S.workers.n+' \u00b7 median '+S.workers.median+' \u00b7 '+S.workers.window,
 [['who','worker'],['starter','starter'],['ratio','working \u00f7 span',1],['working_h','working h',1],['span_h','span h',1],
  ['blocked_h','blocked h',1],['idle_after_end_h','idle after end h',1],['start','start']],S.workers.rows);
table('Waiting by kind',null,[['kind','kind'],['n','n',1],['hours','hours',1],['median','median h',1],['p90','p90 h',1]],
 Object.keys(S.waiting).sort().map(function(k){var v=S.waiting[k];return {kind:k,n:v.n,hours:v.hours,median:v.median,p90:v.p90};}));
table('Locks held','counted in no ratio',[['lock','lock'],['holder','holder'],['hours','hours',1],['n','n',1]],S.locks);
draw();var rt;window.addEventListener('resize',function(){clearTimeout(rt);rt=setTimeout(draw,150);});
})();
"""


# --- CLI ----------------------------------------------------------------------------------------


def settings_for(crew: dict | None) -> tuple:
    """`(log_dir, tz)` from the crew in force (`flow_log.settings`, defaults without a crew)."""
    log_dir, tz, _flow = flow_log.settings(crew or crew_mod.DEFAULTS)
    return log_dir, tz


def load(cwd: Path, since_text: str, now: datetime, board_arg=None, project=None) -> dict:
    """`build` over the crew in force at `cwd` (its board, sampler and the workers' state dir), as
    `main` runs it; `worker_launch.py backfill-starters` reads its worker lanes."""
    try:
        crew_path, crew = crew_mod.find_and_load(cwd)
    except crew_mod.CrewError:
        crew_path, crew = None, None
    args = argparse.Namespace(board=board_arg)
    board, _state = locate_board(args, cwd, crew_path, crew)
    project = project or resolve_project(board, crew_path)
    log_dir, tz = settings_for(crew)
    since = parse_since(since_text, now)
    return build(board, worker_supervisor.state_dir(), log_dir, tz, crew, since, now, (), project)


def starterless(built: dict) -> list:
    """`[(name, session_id)]` of the worker lanes that name no starter."""
    return sorted(
        (n, lane.get("session_id"))
        for n, lane in built["lanes"].items()
        if lane["role"] == "worker" and not lane["starter"]
    )


def ci_doc(cwd: Path, since: datetime, until: datetime) -> dict:
    """The CI source's document for the repo at `cwd` (`command_center/ci_source.py`)."""
    import ci_source  # noqa: PLC0415

    fr = ci_source.fr
    return ci_source.collect(
        fr.norm_slug(fr.git(cwd, "remote", "get-url", "origin")), since, until
    )


def report_sources(built: dict, out=None) -> None:
    out = out or sys.stderr
    for name, c in sorted(built["counts"].items()):
        bad = f", {c['bad']} unreadable" if c["bad"] else ""
        print(
            f"flow_intervals: {name}: {c['rows']} rows read{bad}, {c['intervals']} intervals",
            file=out,
        )
    if built["missing_started"]:
        print(f"flow_intervals: markers without started_at: {built['missing_started']}", file=out)
    orphans = [
        n for n, lane in built["lanes"].items() if lane["role"] == "worker" and not lane["starter"]
    ]
    if orphans:
        print(f"flow_intervals: workers without a starter: {len(orphans)}", file=out)
    a = built.get("attribution") or {}
    print(
        f"flow_intervals: project {built.get('project') or NO_PROJECT}: "
        f"{a.get('kept_rows', 0)} sampler rows of {a.get('kept_sessions', 0)} sessions kept, "
        f"{a.get('dropped_rows', 0)} rows of {a.get('dropped_sessions', 0)} sessions dropped",
        file=out,
    )
    for g in built["gaps"]:
        print(f"flow_intervals: gap: {g['reason']}", file=out)


def main(argv=None, now: datetime | None = None, cwd: Path | None = None) -> int:
    p = argparse.ArgumentParser(prog="flow_intervals.py", description=__doc__.split("\n")[0])
    p.add_argument("--since", default="14d")
    p.add_argument("--until", help="the window's end, UTC YYYY-MM-DDTHH:MM (default: now)")
    p.add_argument("--board", help="board file whose logs to read (default: the crew's)")
    p.add_argument("--project", help="the project's name when its board carries no crew stamp")
    p.add_argument(
        "--from", dest="from_", action="append", default=[], help="a JSONL file of foreign rows"
    )
    p.add_argument("--note", action="append", default=[], help="a line for the page's header")
    fmt = p.add_mutually_exclusive_group()
    fmt.add_argument("--jsonl", action="store_true")
    fmt.add_argument("--html", metavar="FILE")
    fmt.add_argument("--json", action="store_true", help="one document (schema_version)")
    fmt.add_argument(
        "--page-data", action="store_true", help="the --html page's data block as JSON (crewd.py)"
    )
    fmt.add_argument(
        "--snapshot",
        nargs="?",
        const="",
        metavar="DIR",
        help="write flow-<project>.json and .html to DIR (default: snapshot_dir())",
    )
    fmt.add_argument(
        "--snapshot-path", action="store_true", help="print the snapshot's JSON path and stop"
    )
    p.add_argument("--no-ci", action="store_true", help="read no CI source (no gh call)")
    args = p.parse_args(argv)
    if args.until:
        now = parse_ts(args.until if args.until.endswith("Z") else args.until + "Z")
        if now is None:
            p.error(f"--until {args.until!r}: expected YYYY-MM-DDTHH:MM")
    now = now or datetime.now(timezone.utc).replace(microsecond=0)
    try:
        since = parse_since(args.since, now)
    except argparse.ArgumentTypeError as exc:
        p.error(str(exc))
    cwd = cwd or Path.cwd()
    try:
        crew_path, crew = crew_mod.find_and_load(cwd)
    except crew_mod.CrewError:
        crew_path, crew = None, None
    board, _state = locate_board(args, cwd, crew_path, crew)
    project = resolve_project(board, crew_path)
    if args.project:
        stamp = crew_mod.read_stamp(board) if board is not None else None
        if stamp and stamp != args.project:
            p.error(f"--project {args.project!r}: the board {board} belongs to {stamp!r}")
        project = args.project
    if args.snapshot_path:
        print(snapshot_paths(snapshot_dir(), project)[0])
        return 0
    log_dir, tz = settings_for(crew)
    ci = None if args.no_ci else ci_doc(cwd, since, now)
    built = build(
        board,
        worker_supervisor.state_dir(),
        log_dir,
        tz,
        crew,
        since,
        now,
        args.from_,
        project,
        ci,
    )
    report_sources(built)
    return _emit(args, built)


def _emit(args, built: dict) -> int:
    """Print or write `built` in the form the flags chose."""
    if args.snapshot is not None:
        js, page = write_snapshot(
            Path(args.snapshot).expanduser() if args.snapshot else snapshot_dir(), built, args.note
        )
        print(f"flow_intervals: wrote {js} and {page}", file=sys.stderr)
        print(js)
        return 0
    if args.json:
        print(json.dumps(json_doc(built, args.note), ensure_ascii=False, indent=1))
        return 0
    if args.page_data:
        print(json.dumps(page_data(built, args.note), ensure_ascii=False, sort_keys=True))
        return 0
    if args.html:
        Path(args.html).write_text(render_page(page_data(built, args.note)), encoding="utf-8")
        print(f"flow_intervals: wrote {args.html}", file=sys.stderr)
        return 0
    for r in sorted(built["intervals"], key=lambda r: (r["who"], r["start"], r["kind"])):
        print(json.dumps(r, ensure_ascii=False, sort_keys=True))
    for g in built["gaps"]:
        print(json.dumps(g, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
