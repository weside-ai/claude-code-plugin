#!/usr/bin/env python3
"""The standup's one gather: intent, achieved, next, intensity, utilization, in one document.

Usage:
  standup.py [KEY] [--since 7d] [--until UTC] [--branch] [--json | --md] [--lang de|en]
             [--board FILE] [--tickets FILE] [--gh-cache DIR] [--conversation-keys K1,K2]

Read-only: it writes nothing but the `gh_runner` cache directory (`--gh-cache`, default
`ci_source.CACHE`) and the Zentrale's slow cache, both owned by their modules.

Scope (first hit wins; `/we:standup` § 1 owns the reading order): the KEY argument, else the
ticket key of the current branch (`naming.key` of the crew), else the first of
`--conversation-keys` (the stories the calling conversation started), else the portfolio.
`--branch` is the branch view. A key resolves to: an epic plan (`<KEY>-epic.md` or `ticket: KEY`)
→ `view: epic`; a story plan whose `epic:` names an epic plan → `view: story`; anything else →
`view: branch`, which the skill renders as its § 4 (the script adds no branch fields).

Document `{schema_version, view, scope, built_at, window: {since, until, previous: {since,
until}}, sources, gaps, portfolio | epic | story, utilization, signals, decisions,
orchestration}`. The window is `--since` (default 7 days) before `--until`; `previous` is the same
length before it. Every number of a source that was not read is `null` (`n/a` in `--md`, never
`0`) and the source is one `gaps` line `<source>: not read (<why>)`.

Sources, one call each (never per story):

| Source | Call | Gives |
|---|---|---|
| plans | `epic_state.frontmatter` over `docs/plans/*-epic.md` (not `_archive/`), `epic_state.story_keys`, `epic_state.finish_line` | epics, line, intent, story plans |
| board | `board.StateDir`: `board()`, `last_rows()` (stage per key), `transitions()` (moves in the window), `open_questions` | lines, questions, stages |
| tickets | `ticket_snapshot.read` | stage of keys without a board move (only when fresh) |
| flow | `flow_intervals.build` once over both windows | touch hours per key, worker hours, waits per `waiting_on`, story efficiency |
| github | `flow_report.fetch_prs` per repo of `gh_source.repos_of` through `flow_report.gh_runner` | merged PRs, heads (CI rounds) |
| zentrale | `zentrale.build` once | sessions (`crew_view`), red rows, locks line, accounts |
| workers | `worker_launch.cap_limits`, `worker_supervisor.status_records` | worker limit, busy, test-slot waiters (`waits`, optional) |

A PR belongs to the key `flow_report.story_key` finds (title, then branch).

Active epic: not archived, `status: approved`, and its line not reached or one of its keys moved
or had a `working` interval in the window. Its keys: `ticket:`, `line:` keys, the story plans whose
`epic:` names it. Stage per key: the board's last move, else the fresh ticket snapshot, else
`backlog`.

Light (first rule that fires): `red` when a red Zentrale row names one of its keys, a session
waiting on one of its keys is past `sla_due`, or a one-way merge-go of it lies with the owner;
`yellow` when an open line key had no `working` interval in the last 48 h, a Selected key has no
master, or an open question to the owner names one of its keys; else `green`.

Trend: `up` above 1.1 x the previous value, `down` below 0.9 x, `flat` otherwise, `n/a` when the
previous window has no data for it.

Signals (`SIGNALS`), fixed rules over the numbers; the skill judges and proposes, the script only
measures. Each signal: `{id, kind, evidence, source, threshold, actor}`.

Orchestration: per live master its epic (board line `epic`, else `epic_state.epic_number`), every
story of that epic with its stage, under each story the workers that master started on it
(`crew_view`'s `group`); a worker without a live starter stands under `crew_view.NO_STARTER`.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE / "command_center"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import board as board_mod  # noqa: E402
import crew as crew_mod  # noqa: E402
import crew_view  # noqa: E402
import epic_state  # noqa: E402
import flow_intervals as fi  # noqa: E402
import flow_log  # noqa: E402
import flow_report  # noqa: E402

SCHEMA_VERSION = 1
FIELDS = (
    "schema_version",
    "view",
    "scope",
    "built_at",
    "window",
    "sources",
    "gaps",
    "utilization",
    "signals",
    "decisions",
    "orchestration",
)
STAGES = ("done", "in_review", "in_progress", "selected", "backlog")
OPEN_STAGES = ("in_test", "in_review", "in_progress", "selected", "backlog", "on_hold")
DECISIONS_MAX = 5
ACHIEVED_MAX = 10
STALE_LINE_H = 48
LOCK_SHARE = 0.10
CI_ROUNDS_HIGH = 3
SIGNALS = {
    # id: (kind, threshold, actor)
    "selected_without_master": ("idle", "selected keys without master >= 1", "coordinator"),
    "free_slots_plan_waiting": (
        "idle",
        "free worker slots >= 1 and a line key without plan or waiting on product",
        "product",
    ),
    "test_slot_bottleneck": (
        "bottleneck",
        f"waiters >= 1 or waiting:lock hours > {LOCK_SHARE:.0%} of touch hours",
        "machinery",
    ),
    "questions_past_sla": ("waiting", "open owner questions past sla_due >= 1", "coordinator"),
    "master_idle_without_worker": (
        "idle",
        "master idle, no live worker, open line keys >= 1",
        "that master",
    ),
    "ci_rounds_high": (
        "bottleneck",
        f"median CI rounds per code PR >= {CI_ROUNDS_HIGH}",
        "machinery",
    ),
}
ISO = "%Y-%m-%dT%H:%M:%SZ"


def iso(ts: datetime | None) -> str | None:
    return ts.astimezone(timezone.utc).strftime(ISO) if ts else None


def parse_until(text: str | None) -> datetime:
    if not text:
        return datetime.now(timezone.utc).replace(microsecond=0)
    ts = fi.parse_ts(text)
    if ts is None:
        raise ValueError(f"--until: no UTC time: {text}")
    return ts


def parse_days(text: str | None) -> timedelta:
    m = re.fullmatch(r"(\d+)d", text or "7d")
    if not m or int(m.group(1)) < 1:
        raise ValueError(f"--since: needs <n>d, not {text}")
    return timedelta(days=int(m.group(1)))


def trend(cur, prev) -> str:
    """`up`/`down`/`flat`, `n/a` when either value is missing (module docstring § Trend)."""
    if cur is None or prev is None:
        return "n/a"
    if cur > 1.1 * prev:
        return "up"
    if cur < 0.9 * prev:
        return "down"
    return "flat"


def counted(cur, prev) -> dict:
    return {"value": cur, "previous": prev, "trend": trend(cur, prev)}


def _r(value, nd=1):
    return None if value is None else round(float(value), nd)


# --- plans -----------------------------------------------------------------------------------


def _section(text: str, title: str) -> list:
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip().casefold() == title.casefold()
            continue
        if inside:
            out.append(line)
    return out


def _first_sentence(lines: list) -> str:
    text = " ".join(x.strip() for x in lines if x.strip())
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    return (m.group(1) if m else text)[:300]


def _items(lines: list) -> list:
    return [
        re.sub(r"^(\d+\.|[-*])\s+", "", x.strip())
        for x in lines
        if re.match(r"^\s*(\d+\.|[-*])\s+", x)
    ]


def _line_keys(value, pattern: str) -> list:
    """The `line:` keys; a value `epic_state.frontmatter` left as text (a trailing comment) is
    searched for keys."""
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return re.findall(pattern, str(value or "").split("#", 1)[0])


def read_plans(root: Path, pattern: str) -> dict:
    """`{epics: {KEY: epic}, stories: {KEY: epic KEY or None}}` from `docs/plans` (no `_archive/`)."""
    plans = root / "docs" / "plans"
    if not plans.is_dir():
        raise FileNotFoundError(f"no {plans}")
    epics, stories = {}, {}
    for path in sorted(plans.glob("*-story.md")):
        meta = epic_state.frontmatter(path.read_text(encoding="utf-8"))
        key = str(meta.get("story") or meta.get("ticket") or path.name[: -len("-story.md")])
        stories[key] = meta.get("epic") or None
    for path in sorted(plans.glob("*-epic.md")):
        text = path.read_text(encoding="utf-8")
        meta = epic_state.frontmatter(text)
        key = str(meta.get("ticket") or path.name[: -len("-epic.md")])
        body = text.split("\n---", 1)[1] if text.startswith("---") and "\n---" in text else text
        title = next((x[2:].strip() for x in body.splitlines() if x.startswith("# ")), key)
        epics[key] = {
            "key": key,
            "title": re.sub(r"^(Epic|Plan)\s*:\s*", "", title),
            "status": meta.get("status"),
            "serves": meta.get("serves") if meta.get("serves") not in ("null", "") else None,
            "line": _line_keys(meta.get("line"), pattern),
            "line_goal": meta.get("line_goal") or None,
            "outcome": _first_sentence(_section(text, "Outcome")),
            "success_criteria": _items(_section(text, "Success Criteria")),
            "stories": epic_state.story_keys(root, key),
            "text": text,
        }
    return {"epics": epics, "stories": stories}


# --- the build -------------------------------------------------------------------------------


class Gather:
    """Each source read once; a failure is one gap line and `None`."""

    def __init__(self):
        self.gaps: list = []
        self.sources: dict = {}

    def read(self, name: str, fn):
        try:
            value = fn()
        except Exception as exc:
            why = (
                str(exc).strip().splitlines()[0][:160] if str(exc).strip() else type(exc).__name__
            )
            self.gaps.append(f"{name}: not read ({why})")
            self.sources[name] = "not read"
            return None
        self.sources[name] = "read"
        return value


def _default_gh(cache: Path | None):
    def reader(repo: str, since: datetime, until: datetime) -> list:
        window = f"{iso(since)}..{iso(until)}"
        return flow_report.fetch_prs(flow_report.gh_runner(cache, window), repo, since, until)

    return reader


def _branch_name(cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def scope(key, branch_name, conversation_keys, pattern) -> tuple:
    """`(key or None, why)`: argument, branch key, conversation, portfolio (module docstring)."""
    if key:
        return key, "argument"
    found = re.search(pattern, branch_name or "")
    if found:
        return found.group(0), "branch"
    for k in conversation_keys or ():
        if k:
            return k, "conversation"
    return None, "portfolio"


def _ticket_stages(snapshot: dict, crew: dict) -> dict:
    names = {
        **crew_mod.DEFAULTS["board"]["states"],
        **((crew.get("board") or {}).get("states") or {}),
    }
    back = {str(v).casefold(): k for k, v in names.items() if v}
    return {k: back[v.casefold()] for k, v in snapshot.items() if v.casefold() in back}


def build(  # noqa: PLR0912, PLR0915  one call per source, in order
    *,
    key: str | None = None,
    since: str | None = None,
    until: datetime | None = None,
    cwd: Path | None = None,
    board: str | None = None,
    tickets: str | None = None,
    gh_reader=None,
    agents=None,
    branch: bool = False,
    branch_name: str | None = None,
    conversation_keys=(),
    crew: dict | None = None,
    log_dir: Path | None = None,
    state_dir: Path | None = None,
    repos: list | None = None,
    zentrale_doc: dict | None = None,
    workers: list | None = None,
    worker_limit: int | None = None,
    gh_cache: Path | None = None,
) -> dict:
    """The document (module docstring). Every source can be injected; a test calls no gh,
    no `claude agents` and no ticket system."""
    until = until or datetime.now(timezone.utc).replace(microsecond=0)
    span = parse_days(since)
    w_since, p_since = until - span, until - 2 * span
    cwd = Path(cwd or Path.cwd())
    g = Gather()

    crew_path = None
    if crew is None:
        try:
            crew_path, crew = crew_mod.find_and_load(cwd)
        except crew_mod.CrewError:
            crew_path, crew = None, None
        crew = crew or crew_mod.DEFAULTS
    pattern = (crew.get("naming") or {}).get("key") or crew_mod.DEFAULTS["naming"]["key"]
    board_path, _ = fi.locate_board(SimpleNamespace(board=board), cwd, crew_path, crew)
    flow_dir, tz, flow_cf = flow_log.settings(crew)
    log_dir = log_dir if log_dir is not None else flow_dir

    doc: dict = {
        "schema_version": SCHEMA_VERSION,
        "built_at": iso(until),
        "window": {
            "since": iso(w_since),
            "until": iso(until),
            "previous": {"since": iso(p_since), "until": iso(w_since)},
        },
    }
    if branch:
        return _branch_doc(doc, None, "--branch", g)
    if branch_name is None and not key:
        branch_name = _branch_name(cwd)
    scoped, why = scope(key, branch_name, conversation_keys, pattern)

    plans = g.read("plans", lambda: read_plans(cwd, pattern))
    epics = (plans or {}).get("epics", {})
    story_epic = (plans or {}).get("stories", {})
    view, epic_key = "portfolio", None
    if scoped:
        if scoped in epics:
            view, epic_key = "epic", scoped
        elif story_epic.get(scoped) in epics:
            view, epic_key = "story", story_epic[scoped]
        else:
            return _branch_doc(doc, scoped, why, g)

    # board: lines, stages, moves, questions
    state = board_mod.StateDir(board_path) if board_path is not None else None

    def _board():
        if state is None:
            raise FileNotFoundError("no board")
        b = state.board()
        return {
            "board": b,
            "last": state.last_rows(),
            "transitions": state.transitions(),
            "questions": board_mod.open_questions(state, b)[0],
        }

    bd = g.read("board", _board) or {}
    lines = [s for s in (bd.get("board") or {}).get("sessions") or [] if isinstance(s, dict)]

    def _tickets():
        from command_center import ticket_snapshot  # noqa: PLC0415

        path = (
            Path(tickets)
            if tickets
            else (ticket_snapshot.path_for(board_path) if board_path is not None else None)
        )
        mapping, line, fresh = ticket_snapshot.read(
            path, until, float(flow_cf["tickets_stale_min"])
        )
        if not fresh:
            raise ValueError(re.sub(r"^tickets: (not read \((.*)\)|(.*))$", r"\2\3", line))
        return _ticket_stages(mapping, crew)

    ticket_stage = g.read("tickets", _tickets) or {}

    def stage_of(k: str) -> tuple:
        last = (bd.get("last") or {}).get(k)
        if last and last.get("to"):
            return last["to"], "board"
        if k in ticket_stage:
            return ticket_stage[k], "tickets"
        return "backlog", "none"

    # flow: one build over both windows
    def _flow():
        if log_dir is None:
            raise ValueError("flow.log_dir unset")
        project = fi.resolve_project(board_path, crew_path)
        import worker_supervisor  # noqa: PLC0415

        built = fi.build(
            board_path,
            state_dir if state_dir is not None else worker_supervisor.state_dir(),
            log_dir,
            tz,
            crew,
            p_since,
            until,
            project=project,
        )
        if not any(r["source"] == "sampler" for r in built["intervals"]):
            raise ValueError("no sample line in either window")
        return built

    built = g.read("sampler", _flow)

    # github: one fetch per repo over both windows
    def _prs():
        reader = gh_reader or _default_gh(gh_cache)
        names = repos
        if names is None:
            from command_center import gh_source  # noqa: PLC0415

            names = gh_source.repos_of(crew_path, crew)
        out = []
        for repo in names:
            for pr in reader(repo, p_since, until):
                out.append({**pr, "repo": repo, "key": flow_report.story_key(pr, pattern)})
        return out

    prs = g.read("github", _prs)

    # sessions, red rows, locks, accounts
    if agents is None and zentrale_doc is None:
        import worker_launch  # noqa: PLC0415

        agents = g.read("sessions", worker_launch.sessions)

    def _zentrale():
        if zentrale_doc is not None:
            return zentrale_doc
        from command_center import zentrale  # noqa: PLC0415

        return zentrale.build(
            until=until, cwd=cwd, board=board, tickets=tickets, agents=agents or []
        )

    zd = g.read("zentrale", _zentrale) or {}
    sections = zd.get("sections") or {}
    sessions = sections.get("working") or []

    def _workers():
        import worker_launch  # noqa: PLC0415
        import worker_supervisor  # noqa: PLC0415

        limit = (
            worker_limit
            if worker_limit is not None
            else worker_launch.cap_limits(cwd)["max_busy_sessions"]
        )
        records = workers
        if records is None:
            records = worker_supervisor.status_records(
                [dict(r) for r in agents or []],
                None,
                worker_supervisor.projects_dir(),
                worker_supervisor.state_dir(),
                until.timestamp(),
            )
        return {"limit": limit, "records": records}

    wk = g.read("workers", _workers)

    ctx = {
        "until": until,
        "since": w_since,
        "p_since": p_since,
        "epics": epics,
        "story_epic": story_epic,
        "bd": bd,
        "lines": lines,
        "stage_of": stage_of,
        "built": built,
        "prs": prs,
        "sessions": sessions,
        "zentrale": zd,
        "workers": wk,
        "pattern": pattern,
        "g": g,
    }
    active = [k for k in sorted(epics) if _is_active(ctx, epics[k])]
    ctx["active"] = active
    keys_of = {k: _epic_keys(ctx, epics[k]) for k in epics}
    ctx["keys_of"] = keys_of
    utilization = _utilization(ctx)
    ctx["utilization"] = utilization

    doc.update({"view": view, "scope": {"key": scoped, "from": why}})
    if view == "portfolio":
        doc["portfolio"] = [_epic_row(ctx, epics[k]) for k in active]
        doc["main_red"] = next(
            (r.get("title") for r in sections.get("red") or [] if r.get("kind") == "main"), None
        )
        doc["achieved"] = _achieved(ctx, {k for e in active for k in keys_of[e]})
    elif view == "epic":
        doc["epic"] = _epic_detail(ctx, epics[epic_key])
    else:
        doc["story"] = _story_detail(ctx, epics[epic_key], scoped)
    doc["utilization"] = utilization
    doc["signals"] = _signals(ctx)
    doc["decisions"] = _decisions(ctx)
    doc["orchestration"] = orchestration(sessions, lines, ctx)
    if prs is not None:
        loose = [p for p in prs if not p["key"] and _in(p.get("merged"), w_since, until)]
        if loose:
            g.gaps.append(f"prs: {len(loose)} without a key in title or branch")
    doc["sources"] = g.sources
    doc["gaps"] = g.gaps
    return _clean(doc)


def _branch_doc(doc, key, why, g) -> dict:
    doc.update({"view": "branch", "scope": {"key": key, "from": why}, "sources": g.sources})
    doc.update({"gaps": g.gaps, "utilization": None, "signals": [], "decisions": None})
    doc["orchestration"] = None
    return doc


_CONTROL = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-_]|[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _clean(value):
    if isinstance(value, str):
        return _CONTROL.sub("", value)
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    return value


def _in(ts, a, b) -> bool:
    return ts is not None and a <= ts <= b


# --- per epic --------------------------------------------------------------------------------


def _epic_keys(ctx, epic) -> list:
    out = [epic["key"], *epic["line"], *epic["stories"]]
    out += [k for k, e in ctx["story_epic"].items() if e == epic["key"]]
    return list(dict.fromkeys(out))


def _work_rows(ctx, keys, a, b) -> float | None:
    built = ctx["built"]
    if built is None:
        return None
    if not any(
        r["source"] == "sampler" and fi.parse_ts(r["end"]) > a and fi.parse_ts(r["start"]) < b
        for r in built["intervals"]
    ):
        return None
    return sum(
        fi._clip_h(r, a, b)
        for r in built["intervals"]
        if r["kind"] == "working" and r.get("key") in keys
    )


def _moves(ctx, keys, a, b, to) -> list:
    return [
        t
        for t in ctx["bd"].get("transitions") or []
        if t.get("key") in keys and t.get("to") == to and _in(fi.parse_ts(t.get("ts")), a, b)
    ]


def _is_active(ctx, epic) -> bool:
    if epic["status"] != "approved":
        return False
    last = {k: ctx["stage_of"](k)[0] for k in epic["line"]}
    line = epic_state.finish_line(epic["text"], last, ctx["until"].date())
    if line is None or not line["reached"]:
        return True
    keys = set(_epic_keys(ctx, epic))
    moved = any(
        t.get("key") in keys and _in(fi.parse_ts(t.get("ts")), ctx["since"], ctx["until"])
        for t in ctx["bd"].get("transitions") or []
    )
    return moved or bool(_work_rows(ctx, keys, ctx["since"], ctx["until"]))


def _line(ctx, epic) -> dict:
    counts = dict.fromkeys(STAGES, 0)
    for k in epic["line"]:
        st = ctx["stage_of"](k)[0]
        st = "in_review" if st == "in_test" else ("backlog" if st == "on_hold" else st)
        counts[st if st in counts else "backlog"] += 1
    return {"done": counts["done"], "total": len(epic["line"]), "stages": counts}


def _merged(ctx, keys, a, b) -> list | None:
    """The code PRs of `keys` merged in `[a, b]`; a docs-only PR is no delivery."""
    if ctx["prs"] is None:
        return None
    return [
        p
        for p in ctx["prs"]
        if p["key"] in keys and _in(p.get("merged"), a, b) and not p.get("docs_only")
    ]


def _intensity(ctx, keys) -> dict:
    s, p, u = ctx["since"], ctx["p_since"], ctx["until"]
    touch = (_r(_work_rows(ctx, keys, s, u)), _r(_work_rows(ctx, keys, p, s)))
    cur, prev = _merged(ctx, keys, s, u), _merged(ctx, keys, p, s)
    days = (u - s).total_seconds() / 86400
    rounds = None
    if cur is not None:
        heads = [len(x.get("heads") or []) for x in cur if not x.get("docs_only")]
        rounds = statistics.median(heads) if heads else None
    worker_h = None
    built = ctx["built"]
    if touch[0] is not None and built is not None:
        workers = {n for n, lane in built["lanes"].items() if lane.get("role") == "worker"}
        worker_h = _r(
            sum(
                fi._clip_h(r, s, u)
                for r in built["intervals"]
                if r["kind"] == "working" and r.get("key") in keys and r["who"] in workers
            )
        )
    return {
        "touch_h": counted(*touch),
        "worker_h": worker_h,
        "prs_merged": counted(
            None if cur is None else len(cur), None if prev is None else len(prev)
        ),
        "prs_per_day": None if cur is None else _r(len(cur) / days, 2),
        "ci_rounds": rounds,
        "done": counted(
            len(_moves(ctx, keys, s, u, "done")), len(_moves(ctx, keys, p, s, "done"))
        ),
    }


def _masters_holding(ctx) -> set:
    """Keys a live master holds: its board line's `keys` and the keys of the live workers it
    started (`crew_view`'s `group`); an epic on the line alone holds none of its stories."""
    live = {e["name"] for e in ctx["sessions"] if e.get("role") == "master"}
    held = set()
    for line in ctx["lines"]:
        if line.get("name") in live:
            held.update(k for k in line.get("keys") or [] if isinstance(k, str))
    for e in ctx["sessions"]:
        if e.get("role") == "worker" and e.get("group") in live:
            held.update(k for k in e.get("keys") or [] if isinstance(k, str))
    return held


def _past_sla(ctx, keys) -> list:
    out = []
    for line in ctx["lines"]:
        due = fi.parse_ts(line.get("sla_due"))
        late = line.get("waiting_on") and due and due < ctx["until"]
        if late and set(line.get("keys") or []) & set(keys):
            out.append(line.get("name"))
    return out


def _light(ctx, epic) -> tuple:  # noqa: PLR0911  first rule wins
    keys = set(ctx["keys_of"][epic["key"]])
    z = ctx["zentrale"].get("sections") or {}
    for r in z.get("red") or []:
        text = " ".join(str(r.get(f) or "") for f in ("item", "title", "for"))
        hit = sorted(k for k in keys if re.search(rf"\b{re.escape(k)}\b", text))
        if hit:
            return "red", f"{r.get('item')}: {r.get('title') or 'red'}"
    late = _past_sla(ctx, keys)
    if late:
        return "red", f"past SLA: {late[0]}"
    for q in ctx["bd"].get("questions") or []:
        if q.get("key") in keys and q.get("cause") == "merge-go" and q.get("one_way"):
            return "red", f"one-way merge-go {q['id']} with the owner"
    built = ctx["built"]
    if built is not None:
        recent = ctx["until"] - timedelta(hours=STALE_LINE_H)
        for k in epic["line"]:
            if ctx["stage_of"](k)[0] != "done" and not _work_rows(ctx, {k}, recent, ctx["until"]):
                return "yellow", f"{k}: no work in {STALE_LINE_H} h"
    held = _masters_holding(ctx)
    for k in sorted(keys):
        if ctx["stage_of"](k)[0] == "selected" and k not in held:
            return "yellow", f"{k}: selected, no master"
    for q in ctx["bd"].get("questions") or []:
        if q.get("key") in keys:
            return "yellow", f"{q['id']} open with the owner"
    return "green", None


def _next(ctx, epic) -> list:
    out = []
    for k in epic["line"]:
        st, _src = ctx["stage_of"](k)
        if st != "done":
            out.append({"key": k, "stage": st, "line": True, "plan": k in ctx["story_epic"]})
    for k in ctx["keys_of"][epic["key"]]:
        if k == epic["key"] or k in epic["line"]:
            continue
        st, _src = ctx["stage_of"](k)
        if st != "done":
            out.append({"key": k, "stage": st, "line": False, "plan": k in ctx["story_epic"]})
    return out


def _epic_row(ctx, epic) -> dict:
    light, risk = _light(ctx, epic)
    nxt = _next(ctx, epic)
    first = next((n for n in nxt if n["line"]), nxt[0] if nxt else None)
    return {
        "key": epic["key"],
        "title": epic["title"],
        "light": light,
        "line": _line(ctx, epic),
        "intensity": _intensity(ctx, ctx["keys_of"][epic["key"]]),
        "next": {"key": first["key"], "stage": first["stage"]} if first else None,
        "risk": risk,
    }


def _achieved(ctx, keys) -> dict:
    s, u = ctx["since"], ctx["until"]
    merged = _merged(ctx, keys, s, u)
    return {
        "prs": None
        if merged is None
        else [
            {
                "number": p["number"],
                "title": p["title"],
                "repo": p["repo"],
                "key": p["key"],
                "merged": iso(p["merged"]),
            }
            for p in sorted(merged, key=lambda p: (p["merged"], p["repo"], p["number"]))
        ],
        "moves": [
            {"key": t["key"], "to": t["to"], "ts": t["ts"]}
            for t in sorted(
                _moves(ctx, keys, s, u, "in_review") + _moves(ctx, keys, s, u, "done"),
                key=lambda t: (str(t.get("ts")), t["key"]),
            )
        ],
    }


def _waiting(ctx, keys) -> list:
    out = []
    for line in ctx["lines"]:
        if line.get("waiting_on") and set(line.get("keys") or []) & set(keys):
            since = fi.parse_ts(line.get("since"))
            out.append(
                {
                    "who": line.get("name"),
                    "keys": sorted(set(line.get("keys") or []) & set(keys)),
                    "waiting_on": line["waiting_on"],
                    "age_h": _r((ctx["until"] - since).total_seconds() / 3600) if since else None,
                }
            )
    for q in ctx["bd"].get("questions") or []:
        if q.get("key") in keys:
            ts = fi.parse_ts(q.get("ts"))
            out.append(
                {
                    "who": q.get("session"),
                    "keys": [q["key"]],
                    "waiting_on": "human",
                    "question": q["id"],
                    "age_h": _r((ctx["until"] - ts).total_seconds() / 3600) if ts else None,
                }
            )
    return sorted(out, key=lambda w: (-(w["age_h"] or 0), str(w["who"])))


def _intent(epic) -> dict:
    return {
        "key": epic["key"],
        "title": epic["title"],
        "outcome": epic["outcome"],
        "serves": epic["serves"],
        "line": epic["line"],
        "line_goal": epic["line_goal"],
        "success_criteria": epic["success_criteria"],
    }


def _epic_detail(ctx, epic) -> dict:
    keys = ctx["keys_of"][epic["key"]]
    light, risk = _light(ctx, epic)
    return {
        "intent": _intent(epic),
        "light": light,
        "achieved": {"line": _line(ctx, epic), **_achieved(ctx, set(keys))},
        "next": _next(ctx, epic),
        "waiting": _waiting(ctx, keys),
        "intensity": _intensity(ctx, set(keys)),
        "risks": [risk] if risk else [],
    }


def _story_detail(ctx, epic, key) -> dict:
    st, src = ctx["stage_of"](key)
    prs = None
    if ctx["prs"] is not None:
        prs = [
            {
                "number": p["number"],
                "title": p["title"],
                "repo": p["repo"],
                "state": p["state"],
                "merged": iso(p.get("merged")),
            }
            for p in ctx["prs"]
            if p["key"] == key
        ]
    return {
        "intent": {"key": epic["key"], "title": epic["title"], "outcome": epic["outcome"]},
        "key": key,
        "stage": st,
        "stage_source": src,
        "prs": prs,
        "waiting": _waiting(ctx, [key]),
        "intensity": _intensity(ctx, {key}),
    }


# --- utilization, signals, decisions ---------------------------------------------------------


def _accounts_room(accounts: list) -> int:
    n = 0
    for a in accounts:
        if not a.get("in_rotation", True):
            continue
        five = (a.get("five_hour") or {}).get("pct")
        seven = (a.get("seven_day") or {}).get("pct")
        limit = a.get("threshold") or 100
        if five is not None and five < limit and (seven is None or seven < 95):
            n += 1
    return n


def _lock(line: str, name: str) -> str | None:
    m = re.search(rf"{name} (free|held by \S+)", line or "")
    if not m:
        return None
    return None if m.group(1) == "free" else m.group(1)[len("held by ") :]


def _utilization(ctx) -> dict:  # noqa: PLR0915
    g, s, u = ctx["g"], ctx["since"], ctx["until"]
    sessions = ctx["sessions"] if ctx["zentrale"] else None
    out: dict = {}
    wk = ctx["workers"]
    busy = None
    if sessions is not None:
        busy = sum(1 for e in sessions if e.get("role") == "worker" and e.get("state") == "busy")
    limit = wk["limit"] if wk else None
    out["workers"] = {
        "used": busy,
        "limit": limit,
        "free": None if busy is None or limit is None else max(0, int(limit) - busy),
        "source": "zentrale.working · worker_launch.cap_limits",
    }
    masters = None if sessions is None else [e for e in sessions if e.get("role") == "master"]
    out["build_masters"] = {
        "used": None if masters is None else len(masters),
        "limit": None,
        "free": None,
        "source": "zentrale.working (no crew key for a limit)",
    }
    if masters is not None:
        g.gaps.append("build masters: no limit (no crew key)")
    locks = ((ctx["zentrale"].get("sections") or {}).get("ci") or {}).get("locks")
    waiters = None
    if wk is not None:
        recs = wk["records"]
        if any("waits" in r for r in recs):
            waiters = sorted(
                r["name"] for r in recs if r.get("waits") == "test-slot" and r.get("alive", True)
            )
        else:
            g.gaps.append("test-slot waiters: no source (we-worker status has no waits field)")
    out["test_slot"] = {
        "holder": _lock(locks, "test slot") if locks else None,
        "waiting": waiters,
        "source": "zentrale.ci.locks · worker_supervisor.status_records",
    }
    out["gate_lock"] = {
        "holder": _lock(locks, "gate lock") if locks else None,
        "source": "zentrale.ci.locks",
    }
    accounts = (ctx["zentrale"].get("sections") or {}).get("accounts")
    out["accounts"] = {
        "with_room": None if accounts is None else _accounts_room(accounts),
        "total": None if accounts is None else len(accounts),
        "source": "zentrale.accounts",
    }
    live_starters = {e.get("starter") for e in sessions or [] if e.get("role") == "worker"}
    out["idle"] = {
        "masters": None
        if masters is None
        else sorted(
            e["name"]
            for e in masters
            if e.get("state") == "idle" and e["name"] not in live_starters
        ),
        "selected_without_master": _selected_without_master(ctx),
    }
    built = ctx["built"]
    waits, touch = None, None
    if built is not None:
        waits = {}
        for r in built["intervals"]:
            if r["kind"].startswith("waiting:"):
                on = (
                    r["kind"][len("waiting:") :]
                    if r["kind"] in ("waiting:ci", "waiting:lock")
                    else (r.get("waiting_on") or r["kind"][len("waiting:") :])
                )
                h = fi._clip_h(r, s, u)
                if h > 0:
                    waits[on] = round(waits.get(on, 0.0) + h, 1)
        touch = _r(sum(fi._clip_h(r, s, u) for r in built["intervals"] if r["kind"] == "working"))
    out["waiting_h"] = waits
    out["touch_h"] = touch
    eff = None
    if built is not None:
        moved = {
            t["key"]
            for t in ctx["bd"].get("transitions") or []
            if t.get("to") == "in_review" and _in(fi.parse_ts(t.get("ts")), s, u)
        }
        stories = [x for x in fi.summary(built)["stories"] if x["key"] in moved]
        lead = sum(x["lead_h"] for x in stories)
        eff = _r(sum(x["working_h"] for x in stories) / lead, 2) if lead else None
    out["flow_efficiency"] = eff
    rounds = None
    if ctx["prs"] is not None:
        heads = [
            len(p.get("heads") or [])
            for p in ctx["prs"]
            if _in(p.get("merged"), s, u) and not p.get("docs_only")
        ]
        rounds = statistics.median(heads) if heads else None
    out["ci_rounds"] = rounds
    return out


def _selected_without_master(ctx) -> list:
    held = _masters_holding(ctx) if ctx["sessions"] else set()
    out = []
    for e in ctx["active"]:
        for k in ctx["keys_of"][e]:
            if k != e and ctx["stage_of"](k)[0] == "selected" and k not in held:
                out.append(k)
    return sorted(set(out))


def _signal(sid: str, evidence: dict, source: str, actor=None) -> dict:
    kind, threshold, default_actor = SIGNALS[sid]
    return {
        "id": sid,
        "kind": kind,
        "evidence": evidence,
        "source": source,
        "threshold": threshold,
        "actor": actor or default_actor,
    }


def _signals(ctx) -> list:  # noqa: PLR0912  one block per rule
    u = ctx["utilization"]
    out = []
    sel = u["idle"]["selected_without_master"]
    if sel:
        out.append(
            _signal(
                "selected_without_master",
                {"keys": sel},
                "standup.utilization.idle.selected_without_master",
            )
        )
    free = u["workers"]["free"]
    if free:
        waiting = []
        for e in ctx["active"]:
            for k in ctx["epics"][e]["line"]:
                if ctx["stage_of"](k)[0] == "done":
                    continue
                on_product = any(
                    k in (line.get("keys") or []) and line.get("waiting_on") == "product"
                    for line in ctx["lines"]
                )
                if k not in ctx["story_epic"] or on_product:
                    waiting.append(k)
        if waiting:
            out.append(
                _signal(
                    "free_slots_plan_waiting",
                    {"free_slots": free, "keys": sorted(waiting)},
                    "standup.utilization.workers.free · plans · board waiting_on",
                )
            )
    slot = u["test_slot"]
    lock_h = (u["waiting_h"] or {}).get("lock")
    touch = u["touch_h"]
    if (slot["waiting"] and len(slot["waiting"]) >= 1) or (
        lock_h is not None and touch and lock_h > LOCK_SHARE * touch
    ):
        out.append(
            _signal(
                "test_slot_bottleneck",
                {
                    "holder": slot["holder"],
                    "waiters": slot["waiting"],
                    "lock_h": lock_h,
                    "touch_h": touch,
                },
                "standup.utilization.test_slot · utilization.waiting_h.lock",
            )
        )
    late = []
    for q in ctx["bd"].get("questions") or []:
        if _past_sla(ctx, [q.get("key")]):
            late.append(q["id"])
    if late:
        out.append(
            _signal(
                "questions_past_sla", {"questions": late}, "board owner_queue · sessions[].sla_due"
            )
        )
    for name in u["idle"]["masters"] or []:
        line = next((x for x in ctx["lines"] if x.get("name") == name), {})
        epic = line.get("epic")
        open_keys = [
            k
            for k in (ctx["epics"].get(epic) or {}).get("line", [])
            if ctx["stage_of"](k)[0] != "done"
        ]
        if open_keys:
            out.append(
                _signal(
                    "master_idle_without_worker",
                    {"master": name, "epic": epic, "open_line_keys": open_keys},
                    "standup.utilization.idle.masters",
                    actor=name,
                )
            )
    rounds = u["ci_rounds"]
    if rounds is not None and rounds >= CI_ROUNDS_HIGH:
        out.append(
            _signal("ci_rounds_high", {"median_rounds": rounds}, "standup.utilization.ci_rounds")
        )
    return out


def _decisions(ctx) -> dict | None:
    if not ctx["bd"]:
        return None
    items = []
    for q in ctx["bd"].get("questions") or []:
        held = sorted(
            {
                line.get("name")
                for line in ctx["lines"]
                if line.get("waiting_on") == "human"
                and (
                    q.get("key") in (line.get("keys") or [])
                    or line.get("name") == q.get("session")
                )
            }
        )
        stories = [q["key"]] if q.get("key") else []
        items.append(
            {
                "id": q["id"],
                "key": q.get("key"),
                "question": str(q.get("ask") or "").split("\n")[0][:240],
                "recommendation": q.get("recommendation"),
                "unblocks": {"sessions": held, "stories": stories},
                "since": q.get("ts") or q.get("since"),
            }
        )
    items.sort(
        key=lambda d: (
            -(len(d["unblocks"]["sessions"]) + len(d["unblocks"]["stories"])),
            str(d["since"]),
            d["id"],
        )
    )
    return {"items": items[:DECISIONS_MAX], "more": max(0, len(items) - DECISIONS_MAX)}


def orchestration(sessions: list, lines: list, ctx: dict) -> dict:
    """Master → epic → stories → workers (module docstring § Orchestration)."""
    pattern = ctx["pattern"]
    out = {"masters": [], crew_view.NO_STARTER: []}
    by_line = {x.get("name"): x for x in lines}

    def worker_key(w):
        keys = [k for k in w.get("keys") or [] if isinstance(k, str)]
        if keys:
            return keys[0]
        m = re.search(pattern, w.get("name") or "")
        return m.group(0) if m else None

    workers = [e for e in sessions if e.get("role") == "worker"]
    for m in (e for e in sessions if e.get("role") == "master"):
        line = by_line.get(m["name"], {})
        epic = line.get("epic")
        if epic not in ctx["epics"]:
            number = epic_state.epic_number(line) if line else None
            epic = next((k for k in ctx["epics"] if number and k.endswith(f"-{number}")), epic)
        keys = list(ctx["keys_of"].get(epic, []))
        keys = [k for k in keys if k != epic] + [
            k for k in line.get("keys") or [] if k not in keys
        ]
        mine = [w for w in workers if w.get("group") == m["name"]]
        stories = []
        for k in keys:
            stories.append(
                {
                    "key": k,
                    "stage": ctx["stage_of"](k)[0],
                    "workers": [
                        {"name": w["name"], "state": w.get("state")}
                        for w in mine
                        if worker_key(w) == k
                    ],
                }
            )
        loose = [
            {"name": w["name"], "state": w.get("state"), "key": worker_key(w)}
            for w in mine
            if worker_key(w) not in keys
        ]
        out["masters"].append(
            {"master": m["name"], "epic": epic, "stories": stories, "other_workers": loose}
        )
    out[crew_view.NO_STARTER] = [
        {"name": w["name"], "state": w.get("state"), "key": worker_key(w)}
        for w in workers
        if w.get("group") == crew_view.NO_STARTER
    ]
    return out


# --- markdown --------------------------------------------------------------------------------

LABELS = {
    "en": {
        "portfolio": "Portfolio",
        "epic": "Epic",
        "light": "Light",
        "line": "Line",
        "intensity": "Intensity (trend)",
        "next": "Next step",
        "risk": "Risk",
        "achieved": "Achieved",
        "coming": "What comes",
        "decisions": "Your decisions",
        "utilization": "Utilization",
        "gaps": "Gaps",
        "question": "Question",
        "recommendation": "Recommendation",
        "unblocks": "Unblocks",
        "more": "more",
        "green": "green",
        "yellow": "yellow",
        "red": "red",
        "none": "nothing",
        "quiet": "no bottleneck measured",
        "signals": "Signals",
        "resource": "Resource",
        "used": "used",
        "free": "free",
        "limit": "limit",
        "waiting": "Waiting",
        "intent": "Intent",
        "serves": "serves",
        "criteria": "Success criteria",
        "story": "Story",
        "stage": "Stage",
        "plan": "plan",
        "window": "Window",
        "main_red": "main red",
        "workers": "workers",
        "build_masters": "build masters",
        "test_slot": "test slot",
        "gate_lock": "gate lock",
        "accounts": "accounts with room",
        "idle_masters": "masters idle without worker",
        "sel_no_master": "selected without master",
        "waiting_h": "waiting hours",
        "efficiency": "flow efficiency",
        "ci_rounds": "CI rounds per code PR",
        "evidence": "evidence",
        "source": "source",
        "threshold": "threshold",
        "actor": "actor",
        "held": "held by",
        "waiters": "waiters",
        "off_line": "off the line",
    },
    "de": {
        "portfolio": "Portfolio",
        "epic": "Epic",
        "light": "Ampel",
        "line": "Line",
        "intensity": "Intensität (Trend)",
        "next": "Nächster Schritt",
        "risk": "Risiko",
        "achieved": "Erreicht",
        "coming": "Was kommt",
        "decisions": "Deine Entscheidungen",
        "utilization": "Auslastung",
        "gaps": "Lücken",
        "question": "Frage",
        "recommendation": "Empfehlung",
        "unblocks": "Löst",
        "more": "weitere",
        "green": "grün",
        "yellow": "gelb",
        "red": "rot",
        "none": "nichts",
        "quiet": "kein Engpass gemessen",
        "signals": "Signale",
        "resource": "Ressource",
        "used": "belegt",
        "free": "frei",
        "limit": "Grenze",
        "waiting": "Wartet",
        "intent": "Vorhaben",
        "serves": "dient",
        "criteria": "Erfolgskriterien",
        "story": "Story",
        "stage": "Stand",
        "plan": "Plan",
        "window": "Fenster",
        "main_red": "main rot",
        "workers": "Worker",
        "build_masters": "Bau-Master",
        "test_slot": "Test-Slot",
        "gate_lock": "Gate-Lock",
        "accounts": "Konten mit Luft",
        "idle_masters": "Master idle ohne Worker",
        "sel_no_master": "Selected ohne Master",
        "waiting_h": "Wartestunden",
        "efficiency": "Flow-Effizienz",
        "ci_rounds": "CI-Runden je Code-PR",
        "evidence": "Beleg",
        "source": "Quelle",
        "threshold": "Schwelle",
        "actor": "wer",
        "held": "gehalten von",
        "waiters": "Wartende",
        "off_line": "außerhalb der Line",
    },
}
ARROW = {"up": "↑", "down": "↓", "flat": "→", "n/a": "n/a"}


def cell(value) -> str:
    """One table cell: no newline, pipe or backtick breaks the table."""
    text = _clean("n/a" if value is None else str(value))
    return re.sub(r"\s*\n\s*", " ", text).replace("|", "\\|").replace("`", "'")


def _num(value, unit="") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        value = f"{value:.1f}" if value != int(value) or unit == " h" else f"{int(value)}"
    return f"{value}{unit}"


def _trend_text(c: dict, unit="") -> str:
    if c["value"] is None:
        return "n/a"
    return f"{_num(c['value'], unit)} {ARROW[c['trend']]}"


def _line_text(line: dict) -> str:
    st = line["stages"]
    parts = [f"{k} {st[k]}" for k in STAGES[1:] if st[k]]
    return f"{line['done']}/{line['total']}" + (f" ({', '.join(parts)})" if parts else "")


def render_md(doc: dict, lang: str = "en") -> str:  # noqa: PLR0915
    lab = LABELS[lang]
    w = doc["window"]
    head = f"{w['since'][:10]} → {w['until'][:10]}"
    out = []
    if doc["view"] == "branch":
        return f"view: branch · {doc['scope'].get('key') or '-'} ({doc['scope']['from']})\n"
    if doc["view"] == "portfolio":
        out.append(f"## Standup · {lab['portfolio']} · {head}")
        out.append("")
        if doc.get("main_red"):
            out += [f"**{lab['main_red']}:** {cell(doc['main_red'])}", ""]
        out.append(
            f"| {lab['epic']} | {lab['light']} | {lab['line']} | {lab['intensity']} | {lab['next']} | {lab['risk']} |"
        )
        out.append("|---|---|---|---|---|---|")
        for r in doc["portfolio"]:
            it = r["intensity"]
            nxt = f"{r['next']['key']} {r['next']['stage']}" if r["next"] else "-"
            out.append(
                f"| {cell(r['key'] + ' ' + r['title'])} | {lab[r['light']]} | {_line_text(r['line'])} | "
                f"{_trend_text(it['touch_h'], ' h')} · {_trend_text(it['prs_merged'], ' PRs')} | "
                f"{cell(nxt)} | {cell(r['risk'] or '-')} |"
            )
        out.append("")
        out += _achieved_md(doc["achieved"], lab)
        out += _coming_md(doc, lab)
    elif doc["view"] == "epic":
        e = doc["epic"]
        i = e["intent"]
        out.append(f"## Standup · {cell(i['key'] + ' ' + i['title'])} · {head}")
        out.append("")
        out.append(f"**{lab['intent']}:** {cell(i['outcome'])}")
        meta = [
            f"{lab['serves']} {i['serves']}" if i["serves"] else None,
            f"line {', '.join(i['line'])}" if i["line"] else None,
            f"line_goal {i['line_goal']}" if i["line_goal"] else None,
        ]
        out.append(" · ".join(x for x in meta if x) or "-")
        for c in i["success_criteria"]:
            out.append(f"- {cell(c)}")
        out.append("")
        out.append(
            f"**{lab['light']}:** {lab[e['light']]} · **{lab['line']}:** {_line_text(e['achieved']['line'])}"
            f" · **{lab['risk']}:** {cell(', '.join(e['risks']) or '-')}"
        )
        out.append("")
        out += _achieved_md(e["achieved"], lab)
        out.append(f"### {lab['coming']}")
        out.append("")
        out.append(f"| {lab['story']} | {lab['stage']} | {lab['plan']} |")
        out.append("|---|---|---|")
        for n in e["next"]:
            tag = "" if n["line"] else f" ({lab['off_line']})"
            out.append(f"| {n['key']}{tag} | {n['stage']} | {'yes' if n['plan'] else 'no'} |")
        out.append("")
        if e["waiting"]:
            out.append(f"### {lab['waiting']}")
            out.append("")
            for x in e["waiting"]:
                q = f" {x['question']}" if x.get("question") else ""
                out.append(
                    f"- {cell(x['who'])} → {x['waiting_on']}{q} · {', '.join(x['keys'])} · {_num(x['age_h'], ' h')}"
                )
            out.append("")
        it = e["intensity"]
        out.append(
            f"**{lab['intensity']}:** {_trend_text(it['touch_h'], ' h')} · {lab['workers']} {_num(it['worker_h'], ' h')}"
            f" · {_trend_text(it['prs_merged'], ' PRs')} · done {_trend_text(it['done'])}"
            f" · {lab['ci_rounds']} {_num(it['ci_rounds'])}"
        )
        out.append("")
    else:
        s = doc["story"]
        out.append(f"## Standup · {s['key']} · {head}")
        out.append("")
        out.append(
            f"**{lab['epic']}:** {cell(s['intent']['key'] + ' ' + s['intent']['title'])} — {cell(s['intent']['outcome'])}"
        )
        out.append(
            f"**{lab['stage']}:** {s['stage']} · **{lab['intensity']}:** {_trend_text(s['intensity']['touch_h'], ' h')}"
        )
        for p in s["prs"] or []:
            out.append(f"- {p['repo']}#{p['number']} {cell(p['title'])} · {p['state']}")
        out.append("")
    out += _decisions_md(doc.get("decisions"), lab)
    out += render_utilization(doc, lang).splitlines()
    out.append("")
    if doc["gaps"]:
        out.append(f"### {lab['gaps']}")
        out.append("")
        out += [f"- {cell(g)}" for g in doc["gaps"]]
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def _achieved_md(a: dict, lab: dict) -> list:
    out = [f"### {lab['achieved']}", ""]
    if a["prs"] is None:
        out.append("- PRs: n/a")
    prs = list(reversed(a["prs"] or []))
    for p in prs[:ACHIEVED_MAX]:
        out.append(f"- {p['repo']}#{p['number']} {cell(p['title'])} · {p['merged'][:10]}")
    if len(prs) > ACHIEVED_MAX:
        out.append(f"- +{len(prs) - ACHIEVED_MAX} {lab['more']}")
    for m in a["moves"]:
        out.append(f"- {m['key']} → {m['to']} · {m['ts'][:10]}")
    if a["prs"] == [] and not a["moves"]:
        out.append(f"- {lab['none']}")
    out.append("")
    return out


def _coming_md(doc, lab) -> list:
    out = [f"### {lab['coming']}", ""]
    for r in doc["portfolio"]:
        out.append(
            f"- {r['key']}: {r['next']['key'] + ' ' + r['next']['stage'] if r['next'] else lab['none']}"
        )
    if not doc["portfolio"]:
        out.append(f"- {lab['none']}")
    out.append("")
    return out


def _decisions_md(d, lab) -> list:
    if d is None:
        return []
    out = [f"### {lab['decisions']}", ""]
    if not d["items"]:
        return [*out, f"- {lab['none']}", ""]
    out.append(f"| # | {lab['question']} | {lab['recommendation']} | {lab['unblocks']} |")
    out.append("|---|---|---|---|")
    for x in d["items"]:
        unb = ", ".join(x["unblocks"]["stories"] + x["unblocks"]["sessions"]) or "-"
        out.append(
            f"| {x['id']} | {cell(x['question'])} | {cell(x['recommendation'] or '-')} | {cell(unb)} |"
        )
    if d["more"]:
        out.append("")
        out.append(f"+{d['more']} {lab['more']}")
    out.append("")
    return out


def render_utilization(doc: dict, lang: str = "en") -> str:
    """The section Auslastung: numbers and signals only; the skill writes the verdict."""
    lab = LABELS[lang]
    u = doc["utilization"]
    out = [f"### {lab['utilization']}", ""]
    out.append(f"| {lab['resource']} | {lab['used']} | {lab['limit']} | {lab['free']} |")
    out.append("|---|---|---|---|")
    w, b = u["workers"], u["build_masters"]
    out.append(
        f"| {lab['workers']} | {_num(w['used'])} | {_num(w['limit'])} | {_num(w['free'])} |"
    )
    out.append(f"| {lab['build_masters']} | {_num(b['used'])} | n/a | n/a |")
    t = u["test_slot"]
    waiters = "n/a" if t["waiting"] is None else str(len(t["waiting"]))
    out.append(
        f"| {lab['test_slot']} | {cell(t['holder'] or '-')} | 1 | {lab['waiters']} {waiters} |"
    )
    out.append(f"| {lab['gate_lock']} | {cell(u['gate_lock']['holder'] or '-')} | 1 | - |")
    a = u["accounts"]
    out.append(f"| {lab['accounts']} | {_num(a['with_room'])} | {_num(a['total'])} | - |")
    out.append("")
    idle = u["idle"]
    out.append(
        f"- {lab['idle_masters']}: {', '.join(idle['masters']) if idle['masters'] else ('n/a' if idle['masters'] is None else '-')}"
    )
    out.append(f"- {lab['sel_no_master']}: {', '.join(idle['selected_without_master']) or '-'}")
    wh = u["waiting_h"]
    wh_text = (
        "n/a"
        if wh is None
        else (", ".join(f"{k} {v:.1f} h" for k, v in sorted(wh.items())) or "-")
    )
    out.append(f"- {lab['waiting_h']}: {wh_text}")
    out.append(
        f"- {lab['efficiency']}: {'n/a' if u['flow_efficiency'] is None else format(u['flow_efficiency'], '.2f')} · {lab['ci_rounds']}: {_num(u['ci_rounds'])}"
    )
    out.append("")
    sig = doc["signals"]
    if not sig:
        out.append(f"**{lab['signals']}:** {lab['quiet']}")
    else:
        out.append(f"**{lab['signals']}**")
        out.append("")
        out.append(
            f"| id | {lab['evidence']} | {lab['source']} | {lab['threshold']} | {lab['actor']} |"
        )
        out.append("|---|---|---|---|---|")
        for s in sig:
            ev = "; ".join(
                f"{k}={','.join(map(str, v)) if isinstance(v, list) else v}"
                for k, v in s["evidence"].items()
                if v is not None
            )
            out.append(
                f"| {s['id']} | {cell(ev)} | {cell(s['source'])} | {cell(s['threshold'])} | {cell(s['actor'])} |"
            )
    out.append("")
    return "\n".join(out)


# --- CLI -------------------------------------------------------------------------------------


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="standup.py", description=__doc__.split("\n")[0])
    p.add_argument("key", nargs="?")
    p.add_argument("--since", default="7d")
    p.add_argument("--until")
    p.add_argument("--branch", action="store_true")
    fmt = p.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true")
    fmt.add_argument("--md", action="store_true")
    p.add_argument("--lang", choices=sorted(LABELS), default="en")
    p.add_argument("--board")
    p.add_argument("--tickets")
    p.add_argument("--gh-cache")
    p.add_argument("--conversation-keys", default="")
    args = p.parse_args(argv)
    try:
        until = parse_until(args.until)
        parse_days(args.since)
    except ValueError as exc:
        print(f"standup.py: {exc}", file=sys.stderr)
        return 2
    import ci_source  # noqa: PLC0415

    doc = build(
        key=args.key,
        since=args.since,
        until=until,
        board=args.board,
        tickets=args.tickets,
        branch=args.branch,
        conversation_keys=[k for k in args.conversation_keys.split(",") if k],
        gh_cache=Path(args.gh_cache) if args.gh_cache else ci_source.CACHE,
    )
    if args.md:
        sys.stdout.write(render_md(doc, args.lang))
    else:
        print(json.dumps(doc, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
