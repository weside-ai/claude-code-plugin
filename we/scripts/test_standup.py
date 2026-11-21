"""standup.py: the standup's document over fixture sources (no gh, no `claude agents`, no Jira)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import crew as crew_mod  # noqa: E402
import standup  # noqa: E402
import worker_launch  # noqa: E402
import worker_supervisor  # noqa: E402
from command_center import zentrale  # noqa: E402

FIX = HERE / "fixtures" / "standup"
UNTIL = "2026-11-21T18:00Z"


@pytest.fixture
def tree(tmp_path):
    """A copy of the fixture set (no git around it: the worker limit comes from its config)."""
    dst = tmp_path / "standup"
    shutil.copytree(FIX, dst)
    return dst


def _gh(root: Path, fail: bool = False):
    def reader(repo, since, until):
        if fail:
            raise RuntimeError("gh: exit 1")
        out = []
        for raw in json.loads((root / "prs.json").read_text())[repo]:
            p = dict(raw)
            p["merged"] = standup.fi.parse_ts(p["merged"])
            p["heads"] = [{"oid": str(h)} for h in p["heads"]]
            out.append(p)
        return out

    return reader


def run(root: Path, key=None, *, fail_gh=False, workers=None, **kw) -> dict:
    defaults = {
        "key": key,
        "until": standup.parse_until(UNTIL),
        "cwd": root / "repo",
        "board": str(root / "board" / "board.json"),
        "gh_reader": _gh(root, fail_gh),
        "agents": [],
        "branch_name": "main",
        "crew": json.loads(json.dumps(crew_mod.DEFAULTS)),
        "log_dir": root / "flow",
        "state_dir": root / "state",
        "repos": ["acme/app"],
        "zentrale_doc": json.loads((root / "zentrale.json").read_text()),
        "workers": json.loads((root / "workers.json").read_text()) if workers is None else workers,
    }
    defaults.update(kw)
    return standup.build(**defaults)


def edit_json(path: Path, fn) -> None:
    data = json.loads(path.read_text())
    fn(data)
    path.write_text(json.dumps(data))


def golden(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


# --- AC 1, 2: the views and their goldens ------------------------------------------------------


def test_portfolio_golden(tree):
    doc = run(tree)
    assert tuple(k for k in standup.FIELDS if k in doc) == standup.FIELDS
    assert doc["schema_version"] == 1 and doc["view"] == "portfolio"
    rows = {r["key"]: r for r in doc["portfolio"]}
    assert sorted(rows) == [
        "PROJ-9001",
        "PROJ-9010",
        "PROJ-9020",
    ]  # reached PROJ-9030, archived PROJ-9040 absent
    a = rows["PROJ-9001"]
    assert a["light"] == "red"
    assert a["line"] == {
        "done": 1,
        "total": 4,
        "stages": {"done": 1, "in_review": 1, "in_progress": 1, "selected": 1, "backlog": 0},
    }
    assert a["intensity"]["prs_merged"] == {"value": 2, "previous": 1, "trend": "up"}
    assert a["intensity"]["touch_h"]["trend"] == "up"
    assert a["next"] == {"key": "PROJ-9002", "stage": "in_review"}
    assert rows["PROJ-9020"]["light"] == "green" and rows["PROJ-9020"]["risk"] is None
    assert standup.render_md(doc, "de") == golden("portfolio.de.md")


def test_epic_golden(tree):
    doc = run(tree, "PROJ-9001")
    assert doc["view"] == "epic"
    e = doc["epic"]
    assert set(e) >= {"intent", "achieved", "next", "waiting", "intensity", "risks"}
    assert e["intent"]["serves"] == "questions per day"
    assert e["intent"]["line_goal"] == "2026-11-30"
    assert e["intent"]["success_criteria"] == [
        "Questions per day below 5",
        "Every answer lands in one pass",
    ]
    assert [p["number"] for p in e["achieved"]["prs"]] == [12, 11]
    assert [(m["key"], m["to"]) for m in e["achieved"]["moves"]] == [
        ("PROJ-9006", "done"),
        ("PROJ-9002", "in_review"),
    ]
    assert [(n["key"], n["line"], n["plan"]) for n in e["next"]] == [
        ("PROJ-9002", True, True),
        ("PROJ-9003", True, True),
        ("PROJ-9004", True, False),
        ("PROJ-9005", False, True),
    ]
    assert e["next"][3]["stage"] == "in_progress"  # from the fresh ticket snapshot
    assert {"utilization", "decisions", "signals"} <= set(doc)
    assert standup.render_md(doc, "de") == golden("epic.de.md")


# --- AC 3 and the scope order ------------------------------------------------------------------


@pytest.mark.parametrize(
    "key, branch, conversation, want",
    [
        ("PROJ-1", "feat/PROJ-2-x", ["PROJ-3"], ("PROJ-1", "argument")),
        (None, "feat/PROJ-2-x", ["PROJ-3"], ("PROJ-2", "branch")),
        (None, "main", ["PROJ-3"], ("PROJ-3", "conversation")),
        (None, "main", [], (None, "portfolio")),
    ],
)
def test_scope_order(key, branch, conversation, want):
    assert standup.scope(key, branch, conversation, crew_mod.DEFAULTS["naming"]["key"]) == want


def test_story_and_branch_scope(tree):
    doc = run(tree, "PROJ-9003")
    assert doc["view"] == "story"
    s = doc["story"]
    assert s["intent"]["key"] == "PROJ-9001"
    assert set(s["intent"]) == {"key", "title", "outcome", "serves"}
    assert "(serves questions per day)" in standup.render_md(doc, "en")
    assert s["stage"] == "in_progress" and [p["number"] for p in s["prs"]] == [13]
    assert s["waiting"][0]["question"] == "Q901"
    assert s["intensity"]["touch_h"]["value"] > 0
    # a worker on its story branch keeps its story, not the portfolio
    assert run(tree, branch_name="feat/PROJ-9003-money")["view"] == "story"
    branch = run(tree, "PROJ-9999")
    assert branch["view"] == "branch" and branch["scope"]["key"] == "PROJ-9999"
    assert run(tree, branch=True)["view"] == "branch"


# --- AC 4 --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cur, prev, want",
    [
        (11.0, 10.0, "flat"),  # exactly 1.1 x
        (11.01, 10.0, "up"),
        (9.0, 10.0, "flat"),  # exactly 0.9 x
        (8.99, 10.0, "down"),
        (1.0, 0.0, "up"),
        (0.0, 0.0, "flat"),
        (3.0, None, "n/a"),
    ],
)
def test_trend_band(cur, prev, want):
    assert standup.trend(cur, prev) == want


def test_window_and_trend(tree):
    doc = run(tree)
    assert doc["window"] == {
        "since": "2026-11-14T18:00:00Z",
        "until": "2026-11-21T18:00:00Z",
        "previous": {"since": "2026-11-07T18:00:00Z", "until": "2026-11-14T18:00:00Z"},
    }
    wide = run(tree, since="14d")["window"]
    assert wide["since"] == "2026-11-07T18:00:00Z"
    assert wide["previous"]["since"] == "2026-10-24T18:00:00Z"
    # no sampler file in the previous 14 days but 11-12, which now lies in the window: n/a
    assert run(tree, since="14d")["portfolio"][0]["intensity"]["touch_h"]["trend"] == "n/a"


# --- AC 5 --------------------------------------------------------------------------------------


def test_missing_sources_are_gaps(tree):
    full = run(tree)
    assert [g for g in full["gaps"] if "not read" in g] == []  # the red arm

    shutil.rmtree(tree / "flow")
    (tree / "board" / "board-tickets.json").unlink()
    doc = run(tree, fail_gh=True)
    assert [g for g in doc["gaps"] if "not read" in g] == [
        "tickets: not read (no snapshot)",
        "sampler: not read (no sample line in either window)",
        "github: not read (gh: exit 1)",
    ]
    row = doc["portfolio"][0]["intensity"]
    assert row["touch_h"] == {"value": None, "previous": None, "trend": "n/a"}
    assert row["prs_merged"]["value"] is None
    assert doc["achieved"]["prs"] is None
    assert doc["utilization"]["waiting_h"] is None
    md = standup.render_md(doc, "en")
    assert "| n/a · n/a |" in md and "PRs: n/a" in md


def test_unread_sessions_and_board_are_null_not_zero(tree, monkeypatch):
    """A session list or board that was not read is `null`/`n/a`, never an empty crew or 0."""
    import worker_launch  # noqa: PLC0415
    from command_center import zentrale  # noqa: PLC0415

    def no_sessions():
        raise RuntimeError("claude agents: exit 1")

    zdoc = json.loads((tree / "zentrale.json").read_text())
    monkeypatch.setattr(worker_launch, "sessions", no_sessions)
    monkeypatch.setattr(zentrale, "build", lambda **_kw: zdoc)

    def no_board(self):
        raise OSError("board.json: unreadable")

    monkeypatch.setattr(standup.board_mod.StateDir, "board", no_board)
    doc = run(tree, agents=None, zentrale_doc=None)
    gaps = doc["gaps"]
    assert "sessions: not read (claude agents: exit 1)" in gaps
    assert "utilization: n/a (sessions not read)" in gaps
    assert "board: not read (board.json: unreadable)" in gaps
    u = doc["utilization"]
    assert u["workers"]["used"] is None and u["workers"]["free"] is None
    assert u["build_masters"]["used"] is None and u["idle"]["masters"] is None
    assert u["idle"]["selected_without_master"] is None
    assert doc["orchestration"] is None
    assert "free_slots_plan_waiting" not in {s["id"] for s in doc["signals"]}
    assert doc["portfolio"][0]["intensity"]["done"]["value"] is None
    assert doc["achieved"]["moves"] is None
    md = standup.render_md(doc, "en")
    assert "moves: n/a" in md


# --- AC 6 --------------------------------------------------------------------------------------


def test_decisions_ranked_and_capped(tree):
    def seven(b):
        b["owner_queue"] = [
            {
                "id": f"Q{n}",
                "session": f"s{n}",
                "key": f"PROJ-80{n}",
                "ask": f"ask {n}",
                "recommendation": f"rec {n}",
                "cause": "plan",
                "ts": f"2026-11-1{n}T10:00:00Z",
            }
            for n in range(1, 8)
        ]
        held = [("Q6", "PROJ-806"), ("Q3", "PROJ-803")]
        b["sessions"] = [
            {"name": f"h{q}{i}", "waiting_on": "human", "keys": [k]}
            for q, k in held
            for i in range(3)
        ]

    edit_json(tree / "board" / "board.json", seven)
    d = run(tree)["decisions"]
    assert [x["id"] for x in d["items"]] == ["Q3", "Q6", "Q1", "Q2", "Q4"]
    assert d["more"] == 2
    assert d["items"][0]["recommendation"] == "rec 3"
    assert d["items"][0]["unblocks"] == {
        "sessions": ["hQ30", "hQ31", "hQ32"],
        "stories": ["PROJ-803"],
    }


def test_open_fork_is_a_decision(tree):
    """A story plan's `## Open Fork` on the default branch stands among the decisions."""
    plan = tree / "repo" / "docs" / "plans" / "PROJ-9002-story.md"
    text = plan.read_text()
    fork = (
        "## Open Fork\n\nCache per tenant or per user?\n\n- A: per tenant\n- B: per user\n"
        "- **Recommendation:** A, one invalidation path.\n\n"
    )
    plan.write_text(text.replace("## ", fork + "## ", 1) if "## " in text else text + fork)
    d = run(tree)["decisions"]
    item = next(x for x in d["items"] if x["id"] == "PROJ-9002 fork")
    assert item["question"] == "Cache per tenant or per user?"
    assert item["recommendation"] == "A, one invalidation path."
    assert item["unblocks"]["stories"] == ["PROJ-9002"]


# --- AC 7, 8 -----------------------------------------------------------------------------------

WAITERS = [
    {"name": "w-PROJ-9002", "state": "busy", "alive": True, "waits": "test-slot"},
    {"name": "w-PROJ-9003", "state": "busy", "alive": True, "waits": None},
    {"name": "w-lost", "state": "busy", "alive": True, "waits": "test-slot"},
]


def test_utilization_numbers(tree):
    u = run(tree, workers=WAITERS)["utilization"]
    assert u["workers"] == {
        "used": 3,
        "limit": 4,
        "free": 1,
        "source": "zentrale.working · worker_launch.cap_limits",
    }
    assert u["build_masters"]["used"] == 2 and u["build_masters"]["limit"] is None
    assert u["test_slot"]["holder"] == "w-PROJ-9003"
    assert u["test_slot"]["waiting"] == ["w-PROJ-9002", "w-lost"]
    assert u["gate_lock"]["holder"] is None
    assert u["accounts"]["with_room"] == 1 and u["accounts"]["total"] == 2
    assert u["idle"] == {"masters": ["m-9010"], "selected_without_master": ["PROJ-9004"]}
    assert u["waiting_h"] == {"lock": 4.5}
    assert u["flow_efficiency"] is not None and u["ci_rounds"] == 1
    assert u["build_masters"]["companions"] == 0
    gaps = run(tree)["gaps"]
    assert "build masters: no limit (no crew key)" in gaps
    assert "test-slot waiters: no source (we-worker status has no waits field)" in gaps


def test_build_masters_leave_out_companions(tree):
    """A crew member's session is a companion: counted apart, never as an epic's master."""
    edit_json(
        tree / "zentrale.json",
        lambda z: z["sections"]["working"].append(
            {"name": "Ada", "role": "master", "state": "idle", "keys": [], "group": "Ada"}
        ),
    )
    crew = json.loads(json.dumps(crew_mod.DEFAULTS))
    crew["members"] = {"ada": {"name": "Ada"}}
    u = run(tree, crew=crew)["utilization"]
    assert (u["build_masters"]["used"], u["build_masters"]["companions"]) == (2, 1)
    assert u["idle"]["masters"] == ["m-9010"]  # the idle companion is no idle master


def quiet(root: Path) -> None:
    """The fixture state in which no signal rule fires."""
    (root / "repo" / ".weside" / "config.json").write_text('{"workers": {"max_busy_sessions": 3}}')
    path = root / "board" / "board-transitions.jsonl"
    lines = [x for x in path.read_text().splitlines() if '"PROJ-9004"' not in x]
    path.write_text("\n".join(lines) + "\n")
    (root / "board" / "board-waits.jsonl").write_text("")

    def busy(z):
        for s in z["sections"]["working"]:
            if s["name"] == "m-9010":
                s["state"] = "busy"

    edit_json(root / "zentrale.json", busy)


def _sla(due):
    def fn(b):
        b["sessions"].append(
            {"name": "m-9010", "waiting_on": "human", "keys": ["PROJ-9011"], "sla_due": due}
        )
        b["sessions"] = [
            s for s in b["sessions"] if s.get("role") != "master" or s["name"] != "m-9010"
        ]

    return fn


def _heads(n):
    def fn(data):
        for p in data["acme/app"]:
            p["heads"] = list(range(n))

    return fn


def _transition(key, to):
    def fn(root):
        with open(root / "board" / "board-transitions.jsonl", "a") as f:
            f.write(json.dumps({"key": key, "to": to, "ts": "2026-11-21T09:00:00Z"}) + "\n")

    return fn


def _limit(n):
    def fn(root):
        (root / "repo" / ".weside" / "config.json").write_text(
            json.dumps({"workers": {"max_busy_sessions": n}})
        )

    return fn


def _waits(hours):
    def fn(root):
        row = {
            "key": "PROJ-9003",
            "session": "w-PROJ-9003",
            "waiting_on": "lock",
            "since": "2026-11-21T12:30Z",
            "ended": f"2026-11-21T{12 + hours}:30:00Z",
        }
        (root / "board" / "board-waits.jsonl").write_text(json.dumps(row) + "\n")

    return fn


def _idle(root):
    def fn(z):
        for s in z["sections"]["working"]:
            if s["name"] == "m-9010":
                s["state"] = "idle"

    edit_json(root / "zentrale.json", fn)


SIGNAL_CASES = [
    ("selected_without_master", _transition("PROJ-9004", "selected"), lambda _r: None),
    ("free_slots_plan_waiting", _limit(4), _limit(3)),
    ("test_slot_bottleneck", _waits(4), _waits(1)),  # 4 h vs 1 h of lock wait against ~29 h touch
    (
        "questions_past_sla",
        lambda r: edit_json(r / "board" / "board.json", _sla("2026-11-21T12:00Z")),
        lambda r: edit_json(r / "board" / "board.json", _sla("2026-11-21T19:00Z")),
    ),
    ("master_idle_without_worker", _idle, lambda _r: None),
    (
        "ci_rounds_high",
        lambda r: edit_json(r / "prs.json", _heads(3)),
        lambda r: edit_json(r / "prs.json", _heads(2)),
    ),
]


@pytest.mark.parametrize("sid, fire, stay", SIGNAL_CASES, ids=[c[0] for c in SIGNAL_CASES])
def test_signals_fire_and_stay_quiet(tree, tmp_path, sid, fire, stay):
    quiet(tree)
    assert run(tree)["signals"] == []
    other = tmp_path / "other"
    shutil.copytree(tree, other)
    fire(tree)
    fired = [s for s in run(tree)["signals"] if s["id"] == sid]
    assert len(fired) == 1
    assert set(fired[0]) == {"id", "kind", "evidence", "source", "threshold", "actor"}
    assert fired[0]["threshold"] == standup.SIGNALS[sid][1]
    stay(other)
    assert [s["id"] for s in run(other)["signals"]] == []


def test_signals_of_the_fixture(tree):
    sig = {s["id"]: s for s in run(tree, workers=WAITERS)["signals"]}
    assert sig["selected_without_master"]["evidence"] == {"keys": ["PROJ-9004"]}
    assert sig["selected_without_master"]["actor"] == "coordinator"
    assert sig["test_slot_bottleneck"]["evidence"]["waiters"] == ["w-PROJ-9002", "w-lost"]
    assert sig["test_slot_bottleneck"]["actor"] == "machinery"
    assert sig["master_idle_without_worker"]["actor"] == "m-9010"


# --- light rules --------------------------------------------------------------------------------


def _red_row(root):
    edit_json(
        root / "zentrale.json",
        lambda z: z["sections"]["red"].append(
            {"kind": "pr", "item": "acme/app#14", "title": "PROJ-9021 red"}
        ),
    )


def _queue(cause, one_way=None):
    def fn(root):
        edit_json(
            root / "board" / "board.json",
            lambda b: b["owner_queue"].append(
                {
                    "id": "Q990",
                    "key": "PROJ-9021",
                    "ask": "go?",
                    "cause": cause,
                    "one_way": one_way,
                    "ts": "2026-11-21T10:00:00Z",
                }
            ),
        )

    return fn


def _no_recent_work(root):
    for f in (root / "flow").glob("*.jsonl"):
        f.write_text(f.read_text().replace('"PROJ-9021"', "null"))


LIGHT_CASES = [
    ("green", lambda _r: None),
    ("red", _red_row),
    (
        "red",
        lambda r: edit_json(
            r / "board" / "board.json",
            lambda b: b["sessions"].append(
                {
                    "name": "x",
                    "waiting_on": "human",
                    "keys": ["PROJ-9021"],
                    "sla_due": "2026-11-21T10:00Z",
                }
            ),
        ),
    ),
    ("red", _queue("merge-go", "money")),
    ("yellow", _no_recent_work),
    ("yellow", _transition("PROJ-9021", "selected")),
    ("yellow", _queue("plan")),
]


@pytest.mark.parametrize("want, mutate", LIGHT_CASES)
def test_light_rules(tree, want, mutate):
    mutate(tree)
    rows = {r["key"]: r for r in run(tree)["portfolio"]}
    assert rows["PROJ-9020"]["light"] == want


# --- AC 9 --------------------------------------------------------------------------------------


def test_read_only(tree):
    def listing():
        return sorted(
            (str(p.relative_to(tree)), p.stat().st_mtime_ns, p.stat().st_size)
            for p in tree.rglob("*")
        )

    before = listing()
    run(tree)
    run(tree, "PROJ-9001")
    assert listing() == before


# --- AC 11 -------------------------------------------------------------------------------------


def test_utilization_golden_with_and_without_signal(tree, tmp_path):
    other = tmp_path / "quiet"
    shutil.copytree(tree, other)
    assert standup.render_utilization(run(tree), "de") == golden("utilization-signals.de.md")
    quiet(other)
    text = standup.render_utilization(run(other), "de")
    assert "kein Engpass gemessen" in text and "| id |" not in text
    assert text == golden("utilization-quiet.de.md")


# --- AC 12 -------------------------------------------------------------------------------------


def test_orchestration_map(tree):
    o = run(tree)["orchestration"]
    m = {x["master"]: x for x in o["masters"]}
    assert set(m) == {"m-9001", "m-9010"}
    first = m["m-9001"]
    assert first["epic"] == "PROJ-9001"
    stories = {s["key"]: s for s in first["stories"]}
    assert sorted(stories) == ["PROJ-9002", "PROJ-9003", "PROJ-9004", "PROJ-9005", "PROJ-9006"]
    assert stories["PROJ-9003"]["workers"] == [{"name": "w-PROJ-9003", "state": "busy"}]
    assert stories["PROJ-9002"]["workers"] == [{"name": "w-PROJ-9002", "state": "busy"}]
    assert stories["PROJ-9005"]["stage"] == "in_progress"
    assert m["m-9010"]["stories"][0]["workers"] == []
    assert o[standup.crew_view.NO_STARTER] == [
        {"name": "w-lost", "state": "busy", "key": "PROJ-9021"}
    ]


def test_cell_escapes_foreign_markup():
    assert standup.cell("a | b\nc `d`\x1b[31m") == "a \\| b c 'd'"


def test_plans_come_from_the_default_branch(tree):
    """A checkout behind main still shows main's line: plans are read through `git show`."""
    repo = tree / "repo"

    def git(*a):
        subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)

    git("init", "-q")
    git("-c", "user.email=t@example.com", "-c", "user.name=t", "add", "-A")
    git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "base")
    epic = repo / "docs" / "plans" / "PROJ-9010-epic.md"
    epic.write_text(epic.read_text().replace("line: [PROJ-9011]", "line: [PROJ-9011, PROJ-9012]"))
    git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qam", "main moves")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    git("reset", "-q", "--hard", "HEAD~1")  # the local checkout lags behind
    doc = run(tree, "PROJ-9010")
    assert doc["epic"]["intent"]["line"] == ["PROJ-9011", "PROJ-9012"]
    assert doc["sources"]["plans"] == "read"


# --- the orchestration view (`--orchestration --session`) --------------------------------------


def _orch(tree, monkeypatch, session="sid-9001", *, zentrale_fn=None, **kw):
    """The orchestration view with every slow source a raising fake: a call fails the test."""

    def boom(*a, **k):
        raise AssertionError("slow source read in the orchestration view")

    monkeypatch.setattr(standup.fi, "build", boom)
    monkeypatch.setattr(standup.flow_report, "fetch_prs", boom)
    monkeypatch.setattr(worker_supervisor, "status_records", boom)
    doc = json.loads((tree / "zentrale.json").read_text())
    for e in doc["sections"]["working"]:
        e["session_id"] = "sid-" + e["name"].split("-")[-1]
    calls = []

    def fake_build(**k):
        calls.append(k)
        return doc

    monkeypatch.setattr(zentrale, "build", zentrale_fn or fake_build)
    out = run(tree, session=session, gh_reader=boom, workers=[], zentrale_doc=None, **kw)
    return out, calls


def test_orchestration_view_golden(tree, monkeypatch):
    doc, calls = _orch(tree, monkeypatch)
    assert [c["fast"] for c in calls] == [True]
    assert "sampler" not in doc["sources"] and "github" not in doc["sources"]
    doc["scope"]["crew_repo"] = doc["scope"]["crew_repo"].replace(str(tree), "<tree>")
    assert json.dumps(doc, indent=1, sort_keys=True) + "\n" == golden("orchestration.json")


def test_orchestration_view_skips_the_scope_on_a_story_branch(tree, monkeypatch):
    doc, _ = _orch(tree, monkeypatch, branch_name="feat/PROJ-4242-x", key="PROJ-4242")
    assert doc["view"] == "orchestration" and doc["scope"]["from"] == "session"
    assert [m["master"] for m in doc["orchestration"]["masters"]] == ["m-9001"]


def test_orchestration_view_names_an_epic_without_plan(tree, monkeypatch):
    edit_json(
        tree / "board" / "board.json",
        lambda d: d["sessions"][1].update(epic="PROJ-7777", keys=["PROJ-7778"]),
    )
    doc, _ = _orch(tree, monkeypatch, session="sid-9010")
    (m,) = doc["orchestration"]["masters"]
    assert m["epic"] == "PROJ-7777" and [s["key"] for s in m["stories"]] == ["PROJ-7778"]
    assert (
        "orchestration: epic PROJ-7777 has no epic plan in repo; stories from the board line"
        in doc["gaps"]
    )


def test_orchestration_view_without_this_session_is_empty(tree, monkeypatch):
    doc, _ = _orch(tree, monkeypatch, session="sid-unknown")
    assert doc["orchestration"]["masters"] == []


def test_orchestration_view_without_sessions_is_null(tree, monkeypatch):
    def fail(**k):
        raise RuntimeError("claude agents: exit 1")

    monkeypatch.setattr(worker_launch, "sessions", fail)
    doc, _ = _orch(tree, monkeypatch, agents=None)
    assert doc["orchestration"] is None
    assert "sessions: not read (claude agents: exit 1)" in doc["gaps"]


def _git(repo: Path, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)


def _bridge(tmp_path, tree, *, stamp="acme/app", crews=1):
    """A state dir with a stamped board whose master line has no cwd; `crews` repos of crew
    `acme/app` stand on other lines' cwd."""
    boards = tmp_path / "we-state"
    boards.mkdir()
    lines = [{"name": "m-9001", "session_id": "sid-9001", "epic": "PROJ-9001"}]
    repos = []
    for i in range(crews):
        repo = tree / "repo" if i == 0 else tmp_path / f"repo{i}"
        repo.mkdir(exist_ok=True)
        (repo / ".weside").mkdir(exist_ok=True)
        (repo / ".weside" / "crew.json").write_text(
            json.dumps({"version": crew_mod.VERSION, "roles": {}, "members": {}})
        )
        _git(repo, "init", "-q")
        _git(repo, "remote", "add", "origin", "git@github.com:acme/app.git")
        lines.append({"name": f"lead-{i}", "session_id": f"other-{i}", "cwd": str(repo)})
        repos.append(repo)
    (boards / "board.json").write_text(json.dumps({"sessions": lines}))
    (boards / "other-board.json").write_text(json.dumps({"sessions": [{"name": "x"}]}))
    if stamp:
        (boards / "crew.id").write_text(stamp + "\n")
    return boards, repos


def test_crew_of_session_bridges_the_stamp_to_the_repo(tmp_path, tree):
    boards, (repo,) = _bridge(tmp_path, tree)
    assert standup.crew_of_session("sid-9001", boards) == (boards / "board.json", repo)
    assert standup.crew_of_session("sid-none", boards) == (None, None)


@pytest.mark.parametrize("stamp, crews", [(None, 1), ("acme/other", 1), ("acme/app", 2)])
def test_crew_of_session_without_one_repo_keeps_the_board(tmp_path, tree, stamp, crews):
    boards, _ = _bridge(tmp_path, tree, stamp=stamp, crews=crews)
    assert standup.crew_of_session("sid-9001", boards) == (boards / "board.json", None)


def test_orchestration_view_outside_the_crew_repo(tmp_path, tree, monkeypatch):
    """A master whose cwd has no crew (its plans live in the crew repo) still gets its epic."""
    boards, (repo,) = _bridge(tmp_path, tree)
    elsewhere = tmp_path / "plugin"
    elsewhere.mkdir()
    _git(elsewhere, "init", "-q")
    doc, calls = _orch(tree, monkeypatch, cwd=elsewhere, crew=None, board=None, boards_dir=boards)
    assert doc["scope"]["crew_repo"] == str(repo) and calls[0]["cwd"] == repo
    (m,) = doc["orchestration"]["masters"]
    assert m["epic"] == "PROJ-9001" and len(m["stories"]) == 5
    assert not [x for x in doc["gaps"] if x.startswith("orchestration:")]


def test_orchestration_view_without_crew_repo_says_so(tmp_path, tree, monkeypatch):
    boards, _ = _bridge(tmp_path, tree, stamp=None)
    elsewhere = tmp_path / "plugin"
    elsewhere.mkdir()
    _git(elsewhere, "init", "-q")
    doc, calls = _orch(tree, monkeypatch, cwd=elsewhere, crew=None, board=None, boards_dir=boards)
    assert doc["scope"]["crew_repo"] is None
    assert calls[0]["board"] == str(boards / "board.json")
    (m,) = doc["orchestration"]["masters"]
    assert m["epic"] == "PROJ-9001"
    assert (
        "orchestration: epic PROJ-9001 has no epic plan in plugin; stories from the board line"
        in doc["gaps"]
    )


def test_crew_of_session_takes_the_crew_files_repo_and_a_resumed_name(tmp_path, tree):
    """A repo pointing at the crew (`crew:` in its config) shares the crew id; the bridge names
    the repo holding the file. A resumed session has a new id: its live name finds the line."""
    boards, (repo,) = _bridge(tmp_path, tree)
    pointer = tmp_path / "a-pointer"
    (pointer / ".weside").mkdir(parents=True)
    _git(pointer, "init", "-q")
    rel = Path("..") / repo.relative_to(tmp_path) / ".weside" / "crew.json"
    (pointer / ".weside" / "config.json").write_text(json.dumps({"crew": str(rel)}))
    edit_json(
        boards / "board.json",
        lambda d: d["sessions"].append({"name": "p", "session_id": "p", "cwd": str(pointer)}),
    )
    assert standup.crew_of_session("new-id", boards, {"m-9001"}) == (boards / "board.json", repo)


def test_orchestration_view_finds_a_resumed_master_by_name(tree, monkeypatch):
    edit_json(tree / "board" / "board.json", lambda d: d["sessions"][0].update(session_id="old"))
    doc, _ = _orch(tree, monkeypatch, session="old")
    assert [m["master"] for m in doc["orchestration"]["masters"]] == ["m-9001"]
