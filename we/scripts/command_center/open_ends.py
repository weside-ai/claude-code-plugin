#!/usr/bin/env python3
"""Open ends of one project: what waits, on whom, since when. Read-only; one row per open end.

Usage:
  open_ends.py [--board FILE] [--tickets FILE] [--repo OWNER/NAME]… [--until UTC] [--no-gh] [--json]

Row contract (`rows[]`): `kind` (`question`, `wait`, `escalation`, `story`, `pr`), `item` (`Q4`,
the waiting session, `E2`, `ABC-12`, `acme/app#22`), `title`, `holder` (who must act next; `owner`
is the human), `for` (whose work stands still; empty when it is the holder), `master` (the master of
`for`, else of `holder`: the board line's `parent`, else a worker marker's starter, else the session
itself when its line says `role: master`), `since` (UTC ISO or `unknown`), `since_note` (`opened`,
`day` or empty), `age_s`, `source`, `classes` (a PR's: `red`, `draft`, `user merge`,
`green, not armed`, `waiting on CI`), `red` (true for a red PR).

Sources and holders:
- `question`: `board.open_questions` (open by `question_status`; obsolete ones only counted);
  holder `to_name` for a question to another human, else `owner`; since the item's `ts`, else
  its `since` day.
- `wait`: each board line with `waiting_on`: `human` → `owner`, a role key → the line of the
  member `roles.<role>` names, else `<role> (no session)`; since the line's `since`.
- `escalation`: each record of `board.fold_escalations` still open; holder the session of its
  `waiting_on` role.
- `story`: each key whose last transition is `to: in_progress`; holder the worker line holding
  the key, else any line holding it, else `no holder`. The ticket snapshot
  `<board stem>-tickets.json` (or `--tickets`; `ticket_snapshot.py` writes and reads it) adds keys
  only the ticket system has in progress (`source: tickets`, since `unknown`); one older than
  `flow.tickets_stale_min` adds none and the gap says `tickets: stale since <@taken>`, without a file
  `tickets: not read (no snapshot)`.
- `pr`: per repo the open PRs (`flow_report.OPEN_PRS_QUERY`, then `open_pr_states`) with the
  required names of each PR's base (`required_checks.sh`), classed by `arm_pr.sh`'s rule
  (`flow_report.pr_verdict`): draft; red (a failing required check); user merge (a body line
  `user merge:`; holder `owner`); green, not armed; waiting on CI (a required check pending longer
  than `CI_WAIT_LIMIT`). An armed PR under the limit, or armed and green, is no row. A PR an open
  `merge-go` question names stands as that question, not twice.

Project: rows whose session does not belong to the board's project (`flow_intervals.Attribution`)
are dropped and named in `attribution` (`not attributed to <project>: …`).

Every unread source is one `gaps` line `<source>: not read (<why>)`; the rest is built. Control
characters in every string are stripped. `schema_version` counts the shape; `test_zentrale.py`
pins the field list. Nothing is written: GitHub answers go through `flow_report.gh_runner`'s cache.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import board as boardlib  # noqa: E402
import crew as crew_mod  # noqa: E402
import flow_intervals as fi  # noqa: E402
import flow_report as fr  # noqa: E402
import ticket_snapshot  # noqa: E402

SCHEMA_VERSION = 1
CI_WAIT_LIMIT = timedelta(minutes=60)  # longer than a normal required run: stuck or never started
OWNER = "owner"
NO_HOLDER = "no holder"
ROW_FIELDS = (
    "kind",
    "item",
    "title",
    "holder",
    "for",
    "master",
    "since",
    "since_note",
    "age_s",
    "source",
    "classes",
    "red",
)
_CONTROL = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-_]|[\x00-\x1f\x7f-\x9f]")
_USER_MERGE = re.compile(r"^\s*user merge:", re.IGNORECASE | re.MULTILINE)
ISO = "%Y-%m-%dT%H:%M:%SZ"


def clean(value):
    """A string without C0, C1 and ESC sequences; other values as they are, nested."""
    if isinstance(value, str):
        return _CONTROL.sub("", value)
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, dict):
        return {clean(k): clean(v) for k, v in value.items()}
    return value


def iso(ts: datetime | None) -> str | None:
    return ts.astimezone(timezone.utc).strftime(ISO) if ts else None


def _since(value, zone: tzinfo = timezone.utc) -> tuple:
    """(datetime or None, note) of a stamp: an ISO time, or a `YYYY-MM-DD` day, which starts at
    midnight in `zone` (the crew's ``time.zone``, the zone `board.py` dates its days in)."""
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):  # before parse_ts,
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=zone), "day"  # which reads UTC
    ts = fi.parse_ts(value)
    return (ts, "") if ts is not None else (None, "")


class Crew:
    """Holder and master lookups over the board lines and the crew."""

    def __init__(self, lines: list, crew: dict, attribution=None, zone: tzinfo = timezone.utc):
        self.lines = lines
        self.crew = crew
        self.zone = zone
        self.by_name = {str(x.get("name")).casefold(): x for x in lines if x.get("name")}
        self.attribution = attribution

    def line(self, name) -> dict:
        return self.by_name.get(str(name or "").casefold(), {})

    def role_holder(self, role: str) -> str:
        if role == "human":
            return OWNER
        slug = (self.crew.get("roles") or {}).get(role)
        member = (self.crew.get("members") or {}).get(slug) or {}
        for who in (member.get("name"), slug, role):
            if who and self.line(who):
                return self.line(who)["name"]
        return f"{role} (no session)"

    def master(self, name) -> str:
        if not name or name in (OWNER, NO_HOLDER):
            return ""
        line = self.line(name)
        if line.get("parent"):
            return str(line["parent"])
        starter = self.attribution.starter.get(str(name).casefold()) if self.attribution else None
        if starter and starter[1]:
            return starter[1]
        return str(line.get("name") or name) if line.get("role") == "master" else ""

    def leader(self, key: str | None, number: int | None = None) -> str:
        """The session that leads a key or PR: the line whose `pr` names the number, else the
        worker line holding the key, else any line holding it."""
        if number is not None:
            for x in self.lines:
                if re.search(rf"(?:#|/pull/|^){number}$", str(x.get("pr") or "")):
                    return x["name"]
        if key:
            holding = [
                x for x in self.lines if key in (x.get("keys") or []) or x.get("key") == key
            ]
            holding.sort(key=lambda x: x.get("role") != "worker")
            if holding:
                return holding[0]["name"]
        return NO_HOLDER


def row(kind, item, title, holder, for_, master, since, note, source, until, **extra) -> dict:
    return {
        "kind": kind,
        "item": item,
        "title": title or "",
        "holder": holder or NO_HOLDER,
        "for": "" if for_ == holder else (for_ or ""),
        "master": master or "",
        "since": iso(since) if since else "unknown",
        "since_note": note,
        "age_s": int((until - since).total_seconds()) if since else None,
        "source": source,
        "classes": extra.get("classes", []),
        "red": bool(extra.get("red", False)),
    }


# --- board rows -----------------------------------------------------------------------------


def question_rows(state, board: dict, who: Crew, until) -> tuple:
    """(rows, obsolete count, merge-go PR refs)."""
    open_items, obsolete = boardlib.open_questions(state, board)
    out, merge_go = [], set()
    for q in open_items:
        since, note = _since(q.get("ts"), who.zone)
        if since is None:
            since, note = _since(q.get("since"), who.zone)
        asker = q.get("session") or ""
        holder = q.get("to_name") if q.get("to") else OWNER
        if q.get("cause") == "merge-go" and q.get("pr_url"):
            merge_go.add(_pr_ref(q["pr_url"]))
        out.append(
            row(
                "question",
                q["id"],
                q.get("key_title") or q.get("ask"),
                holder,
                asker,
                who.master(asker) or who.master(holder),
                since,
                note,
                "questions",
                until,
            )
        )
    return out, len(obsolete), merge_go


def _pr_ref(url: str) -> str | None:
    found = re.search(r"([\w.-]+)/([\w.-]+)/pull/(\d+)", str(url)) or re.search(
        r"^([\w.-]+)/([\w.-]+)#(\d+)$", str(url)
    )
    return f"{found.group(1)}/{found.group(2)}#{found.group(3)}".lower() if found else None


def wait_rows(who: Crew, until) -> list:
    out = []
    for x in who.lines:
        waiting = x.get("waiting_on")
        if not waiting or not x.get("name"):
            continue
        since, note = _since(x.get("since"), who.zone)
        holder = who.role_holder(str(waiting))
        out.append(
            row(
                "wait",
                x["name"],
                x.get("now") or x.get("topic") or "",
                holder,
                x["name"],
                who.master(x["name"]),
                since,
                note,
                "board",
                until,
            )
        )
    return out


def escalation_rows(state, who: Crew, until) -> list:
    out = []
    for eid, rec in boardlib.fold_escalations(state.escalations()).items():
        if not rec.get("open"):
            continue
        since, note = _since(rec.get("since"), who.zone)
        holder = who.role_holder(str(rec.get("waiting_on") or "")) if rec.get("waiting_on") else ""
        out.append(
            row(
                "escalation",
                eid,
                rec.get("question") or rec.get("key") or "",
                holder,
                "",
                who.master(holder),
                since,
                note,
                "escalations",
                until,
            )
        )
    return out


def story_rows(state, crew: dict, who: Crew, snapshot: dict, until) -> list:
    out, seen = [], set()
    for key, last in state.last_rows().items():
        if last.get("to") != "in_progress":
            continue
        seen.add(key)
        since, note = _since(last.get("ts"), who.zone)
        holder = who.leader(key)
        out.append(
            row(
                "story",
                key,
                last.get("title") or "",
                holder,
                holder,
                who.master(holder),
                since,
                note,
                "transitions",
                until,
            )
        )
    states = {
        **crew_mod.DEFAULTS["board"]["states"],
        **((crew.get("board") or {}).get("states") or {}),
    }
    name = str(states.get("in_progress") or "In Progress").casefold()
    for key, status in sorted(snapshot.items()):
        if key in seen or status.casefold() != name:
            continue
        holder = who.leader(key)
        out.append(
            row("story", key, "", holder, holder, who.master(holder), None, "", "tickets", until)
        )
    return out


# --- GitHub ---------------------------------------------------------------------------------


def classify(pr: dict, required: list, merge_go: bool, until: datetime) -> tuple:
    """(classes, since, note, red) of one open PR (module docstring § `pr`)."""
    checks = fr.head_contexts(pr)
    verdict, fails = fr.pr_verdict(checks, required)
    created = fi.parse_ts(pr.get("createdAt"))
    classes, times, red = [], [], False
    if pr.get("isDraft"):
        classes.append("draft")
        times.append((created, "opened"))
    if verdict == "fail":
        red = True
        classes.append("red")
        done = [
            fi.parse_ts(c.get("completed") or c.get("since")) for c in checks if c["name"] in fails
        ]
        times.append((min([d for d in done if d] or [created]), ""))
    user_merge = bool(_USER_MERGE.search(pr.get("body") or ""))
    if user_merge:
        classes.append("user merge")
        times.append((created, "opened"))
    armed = bool(pr.get("autoMergeRequest"))
    if not pr.get("isDraft") and not user_merge and not merge_go:
        if verdict == "pass" and not armed:
            classes.append("green, not armed")
            done = [fi.parse_ts(c.get("completed")) for c in checks if c["v"] == "pass"]
            done = [d for d in done if d]
            times.append((max(done), "") if done else (created, "opened"))
        elif verdict == "pending":
            waiting = []
            for name in fr.pending_required(checks, required):
                starts = [
                    fi.parse_ts(c.get("since"))
                    for c in checks
                    if c["name"] == name and c["v"] == "pending"
                ]
                if not starts:  # absent: never registered, waiting since the head's commit
                    commit = (((pr.get("commits") or {}).get("nodes") or [{}])[0] or {}).get(
                        "commit"
                    ) or {}
                    starts = [fi.parse_ts(commit.get("committedDate"))]
                waiting += [s for s in starts if s]
            if waiting and until - min(waiting) > CI_WAIT_LIMIT:
                classes.append("waiting on CI")
                times.append((min(waiting), ""))
    if not classes:
        return [], None, "", False
    since, note = min(times, key=lambda t: t[0] or until)
    return classes, since, note, red


def pr_rows(repo_doc: dict, who: Crew, merge_go: set, until: datetime) -> list:
    out = []
    repo = repo_doc["repo"]
    for number, pr in sorted(repo_doc["prs"].items()):
        ref = f"{repo}#{number}".lower()
        required = repo_doc["required"].get(pr.get("baseRefName") or "", [])
        classes, since, note, red = classify(pr, required, ref in merge_go, until)
        if not classes:
            continue
        key = fr.story_key(
            {"title": pr.get("title") or "", "branch": pr.get("headRefName") or ""}, fr.DEFAULT_KEY
        )
        leader = who.leader(key, number)
        holder = OWNER if "user merge" in classes else leader
        out.append(
            row(
                "pr",
                f"{repo}#{number}",
                pr.get("title"),
                holder,
                leader,
                who.master(leader),
                since,
                note,
                f"gh {repo}",
                until,
                classes=classes,
                red=red,
            )
        )
    return out


# --- the document ---------------------------------------------------------------------------


def attribution_for(board: Path | None, state, crew: dict, lines: list):
    if board is None:
        return None
    return fi.Attribution(lines, crew, {}, [], state.transitions() if state else [])


def attributed_rows(rows: list, attribution) -> tuple:
    """(rows of the project, dropped rows): a row stays when its session (`for`, else `holder`)
    belongs, when it names no session (`owner`, `no holder`) and is no question, when its key is
    the project's, or when it comes from the project's own transitions log."""
    kept, dropped = [], []
    for r in rows:
        name = r["for"] or r["holder"]
        keys = re.findall(attribution.key_rx, r["item"])
        on_session = name not in (OWNER, NO_HOLDER, "") and not name.endswith("(no session)")
        if (
            r["source"] == "transitions"
            or (not on_session and r["kind"] != "question")
            or attribution.belongs(name, keys)
            or (not on_session and set(keys) & attribution.keys)
        ):
            kept.append(r)
        else:
            dropped.append(r)
    return kept, dropped


def build(
    board: Path | None,
    crew_path: Path | None,
    crew: dict,
    until: datetime,
    *,
    ticket_file: Path | None = None,
    repos: list | None = None,
    zone: tzinfo | None = None,
) -> dict:
    """The open-ends document. `repos`: `[{repo, prs, required, default} or {repo, gap}]`, read
    by the caller (`gh_source.read_all`), so the board part never waits on GitHub."""
    project = fi.resolve_project(board, crew_path)
    gaps, header, rows, dropped = [], [f"Project: {project or fi.NO_PROJECT}"], [], []
    state = boardlib.StateDir(board) if board is not None else None
    doc_board: dict = {}
    if board is None:
        gaps.append("board: not read (no crew, no --board)")
    elif not board.is_file():
        gaps.append("board: not found")
    else:
        try:
            doc_board = state.board()
        except (boardlib.BoardError, OSError, ValueError) as exc:
            gaps.append(f"board: not read ({exc})")
    lines = [x for x in doc_board.get("sessions") or [] if isinstance(x, dict)]
    attribution = attribution_for(board, state, crew, lines)
    zone = zone or crew_mod.time_zone(crew_path.parent.parent if crew_path else None)
    who = Crew(lines, crew, attribution, zone)
    merge_go: set = set()
    if doc_board:
        q_rows, obsolete, merge_go = question_rows(state, doc_board, who, until)
        header.append(f"obsolete questions: {obsolete}")
        rows += q_rows + wait_rows(who, until) + escalation_rows(state, who, until)
        snap_path = ticket_file or ticket_snapshot.path_for(board)
        snapshot, line, fresh = ticket_snapshot.read(
            snap_path,
            until,
            float({**crew_mod.DEFAULTS["flow"], **(crew.get("flow") or {})}["tickets_stale_min"]),
        )
        snapshot = snapshot if fresh else {}  # a stale snapshot names no story as current
        (gaps if "not read" in line or "stale" in line else header).append(line)
        rows += story_rows(state, crew, who, snapshot, until)
    for repo in repos or []:
        if repo.get("gap"):
            gaps.append(f"PRs {repo['repo']}: not read ({repo['gap']})")
            continue
        prs = pr_rows(repo, who, merge_go, until)
        header.append(f"open PRs {repo['repo']}: {len(repo['prs'])}, waiting: {len(prs)}")
        if repo.get("more"):
            gaps.append(f"PRs {repo['repo']}: only the oldest {len(repo['prs'])} open PRs read")
        rows += prs
    if attribution is not None:
        rows, dropped = attributed_rows(rows, attribution)
    rows.sort(key=lambda r: (r["since"] != "unknown", r["since"]))
    attributed = ""
    if dropped:
        parts = []
        for kind in ("question", "wait", "escalation", "story", "pr"):
            items = [r["item"] for r in dropped if r["kind"] == kind]
            if items:
                parts.append(
                    f"{len(items)} {kind}{'s' if len(items) > 1 else ''} ({', '.join(items)})"
                )
        attributed = f"not attributed to {project}: " + ", ".join(parts)
    return clean(
        {
            "schema_version": SCHEMA_VERSION,
            "project": project,
            "built_at": iso(until),
            "header": header,
            "gaps": gaps,
            "attribution": attributed,
            "rows": rows,
        }
    )


def load_crew(cwd: Path | None = None) -> tuple:
    try:
        crew_path, crew = crew_mod.find_and_load(cwd)
    except crew_mod.CrewError:
        crew_path, crew = None, None
    return crew_path, crew or crew_mod.DEFAULTS


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="open_ends.py", description=__doc__.split("\n")[0])
    p.add_argument("--board")
    p.add_argument("--tickets")
    p.add_argument("--repo", action="append", default=[])
    p.add_argument("--until")
    p.add_argument("--no-gh", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    until = (
        fi.parse_ts(args.until)
        if args.until
        else datetime.now(timezone.utc).replace(microsecond=0)
    )
    crew_path, crew = load_crew()
    board, _ = fi.locate_board(args, Path.cwd(), crew_path, crew)
    repos = []
    if not args.no_gh:
        import gh_source  # noqa: PLC0415  (the shared GitHub reader of the command centre)

        repos = gh_source.read_all(args.repo or gh_source.repos_of(crew_path, crew), until)
    doc = build(
        board,
        crew_path,
        crew,
        until,
        ticket_file=Path(args.tickets) if args.tickets else None,
        repos=repos,
    )
    if args.json:
        print(json.dumps(doc, ensure_ascii=False, indent=1))
        return 0
    for line in doc["header"] + doc["gaps"] + ([doc["attribution"]] if doc["attribution"] else []):
        print(line)
    for r in doc["rows"]:
        print(f"{r['kind']:10} {r['item']:20} {r['holder']:20} {r['since']} {r['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
