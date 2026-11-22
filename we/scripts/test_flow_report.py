"""flow_report.py: every row from recorded `gh` answers and board logs, `n/a` for a missing source,
the gh cache, and the Markdown file in the optimization store. No network: `gh` is a fake."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import flow_report as fr  # noqa: E402

FIX = HERE / "fixtures" / "flow_report"
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
CREW = {
    "version": 2,
    "roles": {"product": "ada", "architecture": "vic", "acceptance": "tess"},
    "members": {
        "ada": {"name": "Ada", "workplace": "."},
        "vic": {"name": "Vic", "workplace": "."},
        "tess": {"name": "Tess", "workplace": "."},
    },
    "state_dir": "state",
    "board": {"file": "state/board.json"},
}


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


REQUIRED = ["Lint", "Claude Review"]


def recorded_required(_repo):
    return list(REQUIRED)


def no_required(_repo):
    return []


class FakeGh:
    """Answers like `gh api graphql`: the recorded search pages, check suites and check runs per
    commit."""

    def __init__(self):
        self.bodies = []
        self.suites = load("suites.json")
        self.checks = load("checks.json")

    def __call__(self, body):
        self.bodies.append(body)
        variables = body["variables"]
        if "ids" in variables and "checkRuns" in body["query"]:
            nodes = [dict(self.checks.get(i[2:], {}), oid=i[2:]) for i in variables["ids"]]
            return {"data": {"nodes": nodes}}
        if "ids" in variables:
            nodes = [
                {"oid": i[2:], "checkSuites": {"nodes": self.suites.get(i[2:], [])}}
                for i in variables["ids"]
            ]
            return {"data": {"nodes": nodes}}
        if "is:open" in variables["q"]:
            return load("search-open.json")
        return load("search-merged.json")


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


TRANSITIONS = [
    {"key": "PROJ-0", "from": None, "to": "selected", "ts": "2026-10-20T08:00:00Z", "by": "pia"},
    {
        "key": "PROJ-0",
        "from": "in_review",
        "to": "done",
        "ts": "2026-10-25T08:00:00Z",
        "by": "tess",
    },
    {"key": "PROJ-1", "from": None, "to": "selected", "ts": "2026-11-01T08:00:00Z", "by": "pia"},
    {
        "key": "PROJ-1",
        "from": "selected",
        "to": "in_progress",
        "ts": "2026-11-01T10:00:00Z",
        "by": "master-1",
    },
    {
        "key": "PROJ-1",
        "from": "in_progress",
        "to": "selected",
        "ts": "2026-11-01T11:00:00Z",
        "by": "master-1",
    },
    {
        "key": "PROJ-1",
        "from": "selected",
        "to": "in_progress",
        "ts": "2026-11-01T12:00:00Z",
        "by": "master-1",
    },
    {
        "key": "PROJ-1",
        "from": "in_progress",
        "to": "in_review",
        "ts": "2026-11-02T16:00:00Z",
        "by": "master-1",
    },
    {"key": "PROJ-2", "from": None, "to": "selected", "ts": "2026-11-03T07:00:00Z", "by": "pia"},
    {
        "key": "PROJ-2",
        "from": "selected",
        "to": "in_progress",
        "ts": "2026-11-03T07:30:00Z",
        "by": "worker-x",
    },
    {
        "key": "PROJ-1",
        "from": "in_review",
        "to": "done",
        "ts": "2026-11-03T08:00:00Z",
        "by": "tess",
    },
    {
        "key": "PROJ-4",
        "from": "in_progress",
        "to": "in_review",
        "ts": "2026-11-08T12:00:00Z",
        "by": "we-worker close",
    },
    {"key": "PROJ-3", "from": None, "to": "selected", "ts": "2026-11-09T08:00:00Z", "by": "pia"},
    {
        "key": "PROJ-3",
        "from": "selected",
        "to": "in_progress",
        "ts": "2026-11-09T09:00Z",
        "by": "master-1",
    },
]
QUESTIONS = [
    {"id": "Q1", "ts": "2026-11-09T10:00:00Z", "cause": "plan", "outcome": "posted"},
    {"id": "Q2", "ts": "2026-11-09T11:00:00Z", "cause": "merge-go", "outcome": "posted"},
    {"ts": "2026-11-09T11:30:00Z", "cause": "plan", "outcome": "returned"},
    {"id": "Q0", "ts": "2026-10-01T10:00:00Z", "cause": "plan", "outcome": "posted"},
]
ANSWERS = [
    {"id": "Q1", "answer": "accept", "ts": "2026-11-09T12:00:00.000Z"},
    {"id": "Q2", "answer": "read", "ts": "2026-11-09T11:10:00Z"},
]
BRAKES = [
    {"ts": "2026-11-09T10:00:00Z", "type": "deny", "gate": "worker_rights_gate"},
    {"ts": "2026-11-09T10:05:00Z", "type": "brief", "ok": True},
    {"ts": "2026-11-09T10:06:00Z", "type": "outcome", "kind": "card", "pr": "7", "danger": "no"},
    {"ts": "2026-10-01T10:00:00Z", "type": "brief", "ok": True},
]
SEVERITY = [
    ("PROJ-1", 1, "p1", "red", 0, 2, False),
    ("PROJ-1", 2, "p2", "green", 0, 0, False),
    ("PROJ-1", 3, "p3", "green", 0, 0, False),
    ("PROJ-2", 1, "q1", "red", 1, 0, False),
]


def repo(tmp_path, crew=True, board=True):
    root = tmp_path / "app"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "remote", "add", "origin", "git@github.com:acme/app.git")
    lines = [
        {
            "kind": "severity",
            "id": f"ready-{k}",
            "lens": "architecture",
            "bound": b * 20,
            "round": r,
            "verdict": v,
            "failure": f,
            "ran_at": "2026-11-05T10:00:00Z",
            "blocking": bl,
            "warning": w,
            "note": 0,
        }
        for k, r, b, v, bl, w, f in SEVERITY
    ]
    jsonl(root / ".git" / "we-lens" / "samples.jsonl", lines)
    if crew:
        (root / ".weside").mkdir()
        (root / ".weside" / "crew.json").write_text(json.dumps(CREW), encoding="utf-8")
    if board:
        state = root / ".weside" / "state"
        jsonl(state / "board-transitions.jsonl", TRANSITIONS)
        jsonl(state / "board-questions.jsonl", QUESTIONS)
        jsonl(state / "board-answers.jsonl", ANSWERS)
        jsonl(state / "brakes.jsonl", BRAKES)
    return root


def report(root, *argv, run=None, required=recorded_required):
    args = fr.argparse.Namespace(
        since="10d", repo=None, board=None, gh_cache=None, review_match="review"
    )
    for flag, value in zip(argv[::2], argv[1::2]):
        setattr(args, flag, value)
    out = fr.build(args, NOW, root, run or FakeGh(), required)
    return {r["row"]: r for r in out["rows"]}, out


@pytest.fixture(autouse=True)
def no_state_env(monkeypatch, tmp_path):
    monkeypatch.delenv("WE_STATE_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def test_github_rows_from_the_recorded_answers(tmp_path):
    rows, out = report(repo(tmp_path))
    assert out["repo"] == "acme/app"
    r = rows["PR open → merge"]
    assert (r["n"], r["median"], r["p90"]) == (3, 4.0, 24.0)
    r = rows["Heads per code PR"]
    assert (r["n"], r["median"], r["p90"], r["value"]) == (3, 2, 2, "one head 33 %")
    assert rows["Docs-PR share"]["n"] == 5
    assert rows["Docs-PR share"]["value"] == "1 docs-only, 20 %"
    r = rows["Review red per PR: Review: Bot"]
    assert (r["n"], r["median"], r["p90"], r["value"]) == (4, 0, 1, "red on 25 % of PRs")
    assert "Review red per PR: Review gate rerun" not in rows  # a review event is no head
    r = rows["CI cancelled share"]
    assert (r["n"], r["value"]) == (11, "2 cancelled (18 %), newer push 100 % of them")
    assert rows["Code PRs by risk class"]["value"] == "one-way 1"
    r = rows["New tests per code PR"]  # #1 new line, #3 the line before cases, #5 none
    assert (r["n"], r["median"], r["p90"]) == (2, 1.5, 2)
    assert r["value"] == "cases median 5, p90 5 (n 1)"
    r = rows["PRs per story"]
    assert (r["n"], r["median"]) == (2, 1)
    assert r["value"].endswith("mean with docs PRs 1.50")
    since = NOW - timedelta(days=10)  # threads change nothing in the PRs, nor their order
    one, many = (fr.fetch_prs(FakeGh(), "acme/app", since, NOW, pool=n) for n in (1, 4))
    assert one == many and one


def test_board_rows_from_the_logs(tmp_path):
    rows, out = report(repo(tmp_path))
    r = rows["Lead time Selected → Done"]
    assert (r["n"], r["median"]) == (1, 48.0)  # PROJ-0 is done before the window
    assert rows["Share of lead time: Selected"]["median"] == pytest.approx(100 * 3 / 48)
    assert rows["Share of lead time: In Progress (no PR)"]["median"] == pytest.approx(
        100 * 23 / 48
    )
    assert rows["Share of lead time: In Progress (PR open)"]["median"] == pytest.approx(
        100 * 6 / 48
    )
    assert rows["Share of lead time: In Review"]["median"] == pytest.approx(100 * 16 / 48)
    r = rows["Stock now (age of In Review)"]
    assert r["value"] == "in_progress 2 · in_review 1 · done 2"
    assert (r["n"], r["median"]) == (3, 2.0)
    r = rows["Mismatch: merged PR, story before In Review"]
    assert (r["n"], r["value"]) == (1, "PROJ-2 #3 (in_progress)")
    r = rows["Mismatch: In Progress without open PR"]
    assert (r["n"], r["value"]) == (1, "PROJ-2")
    assert out["writers"]["selected→in_progress"] == {"master-1": 3, "worker-x": 1}
    assert out["writers"]["in_review→done"] == {"tess": 1}
    r = rows["Transition writers: In Review"]
    assert (r["n"], r["value"]) == (2, "we-worker close 1 of 2; bypassed by master-1 1")
    r = rows["Escapes after Done by risk class"]
    assert (r["n"], r["value"]) == (0, "routine 0/1")
    reopened = [  # a routine story and a one-way story (PR #3) each leave Done again
        {"key": "PROJ-9", "from": "in_test", "to": "done", "ts": "2026-11-04T08:00:00Z"},
        {"key": "PROJ-9", "from": "done", "to": "in_review", "ts": "2026-11-05T08:00:00Z"},
        {"key": "PROJ-2", "from": "in_progress", "to": "done", "ts": "2026-11-09T10:00:00Z"},
        {"key": "PROJ-2", "from": "done", "to": "in_progress", "ts": "2026-11-09T11:00:00Z"},
    ]
    log = tmp_path / "app" / ".weside" / "state" / "board-transitions.jsonl"
    jsonl(log, TRANSITIONS + reopened)
    rows, _ = report(tmp_path / "app")
    r = rows["Escapes after Done by risk class"]
    assert (r["n"], r["value"]) == (2, "one-way 1/1 · routine 1/2")


def test_questions_brakes_and_ready_rounds(tmp_path):
    rows, _ = report(repo(tmp_path))
    r = rows["Questions to the human per day"]
    assert r["n"] == 2
    assert r["value"] == "plan 0.1/d · merge-go 0.1/d"
    r = rows["Question answer time"]
    assert (r["n"], r["median"], r["value"]) == (1, 2.0, "1 unanswered")
    r = rows["Brakes per day"]
    assert (r["n"], r["value"]) == (2, "deny worker_rights_gate 0.1/d · brief 0.1/d")
    r = rows["Brake outcomes"]
    assert (r["n"], r["value"]) == (
        1,
        "brief: 0 danger · 0 false alarm · 1 unjudged; card: 0 danger · 1 false alarm · 0 unjudged; "
        "deny: 0 danger · 0 false alarm · 1 unjudged",
    )
    r = rows["Ready rounds"]
    assert (r["n"], r["median"], r["p90"]) == (2, 2.0, 3)
    assert r["value"].startswith("red on WARNING only: 1 of 2 red lens verdicts (50 %)")


def test_no_crew_no_board_prints_github_rows_and_na(tmp_path, capsys, monkeypatch):
    root = repo(tmp_path, crew=False, board=False)
    rows, out = report(root)
    assert rows["Heads per code PR"]["n"] == 3
    for name in (
        "Lead time Selected → Done",
        "Stock now (age of In Review)",
        "Escapes after Done by risk class",
        "Questions to the human per day",
        "Brakes per day",
        "Brake outcomes",
    ):
        assert rows[name]["value"].startswith("n/a ("), name
        assert rows[name]["n"] is None
    assert out["writers"] is None
    monkeypatch.chdir(root)
    assert (
        fr.main(["--since", "10d"], now=NOW, cwd=root, run=FakeGh(), required=recorded_required)
        == 0
    )
    text = capsys.readouterr().out
    assert "n/a (board log not found: no crew file)" in text
    assert "Heads per code PR" in text
    flow = text.split("\nFlow efficiency\n", 1)[1]
    assert re.search(r"^Flow efficiency +n/a \(board log not found: no crew file\)", flow, re.M)
    assert out["flow_efficiency"]["summary"] is None


def test_missing_gh_turns_the_github_rows_into_na(tmp_path, monkeypatch):
    only_git = tmp_path / "only-git"
    only_git.mkdir()
    (only_git / "git").symlink_to(shutil.which("git"))
    monkeypatch.setenv("PATH", str(only_git))
    rows, _ = report(repo(tmp_path), run=fr.gh_runner(None))
    for name in (
        "PR open → merge",
        "Docs-PR share",
        "Share of lead time: In Progress (PR open)",
        "Mismatch: In Progress without open PR",
        "Escapes after Done by risk class",
        "New tests per code PR",
    ):
        assert rows[name]["value"] == "n/a (gh not found)", name
    assert rows["Share of lead time: In Progress"]["n"] == 1
    assert rows["Lead time Selected → Done"]["n"] == 1


def test_the_gh_cache_answers_a_second_run(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    fake = bin_dir / "gh"
    empty = tmp_path / "empty-search.json"
    empty.write_text(
        json.dumps(
            {
                "data": {
                    "search": {
                        "issueCount": 0,
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [],
                    }
                }
            }
        )
    )
    fake.write_text(
        f"#!/bin/sh\ncat >/dev/null\necho x >> {calls}\ncat {empty}\n", encoding="utf-8"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    root = repo(tmp_path)
    cache = tmp_path / "cache"
    report(root, run=fr.gh_runner(cache, "w1"), required=no_required)
    first = len(calls.read_text().splitlines())
    assert first == 11  # ten day chunks and the open PRs, no commits to ask about
    rows, _ = report(root, run=fr.gh_runner(cache, "w1"), required=no_required)
    assert len(calls.read_text().splitlines()) == first
    assert rows["Docs-PR share"]["n"] == 0
    report(
        root, run=fr.gh_runner(cache, "w2"), required=no_required
    )  # another window asks again, open PRs too
    assert len(calls.read_text().splitlines()) == 2 * first
    report(root, run=fr.gh_runner(cache, "w2", ttl=0), required=no_required)  # too old: again
    assert len(calls.read_text().splitlines()) == 3 * first


def test_gh_runner_clears_stale_part_files(tmp_path):
    """A `*.part` left by a timed-out call goes once it is older than `PART_MAX_AGE_S`; a fresh
    one may still belong to a running write and stays."""
    stale, fresh = tmp_path / "a.json.1.part", tmp_path / "b.json.2.part"
    for f in (stale, fresh):
        f.write_text("{", encoding="utf-8")
    old = time.time() - fr.PART_MAX_AGE_S - 60
    os.utime(stale, (old, old))
    fr.gh_runner(tmp_path, "w")
    assert (stale.exists(), fresh.exists()) == (False, True)


def test_md_writes_into_the_store_or_says_why_not(tmp_path, capsys):
    root = repo(tmp_path)
    assert fr.main(["--md"], now=NOW, cwd=root, run=FakeGh(), required=recorded_required) == 0
    captured = capsys.readouterr()
    assert "nothing written" in captured.err
    assert captured.out.startswith("# Flow report acme/app")
    (root / ".weside" / "optimization").mkdir()
    assert fr.main(["--md"], now=NOW, cwd=root, run=FakeGh(), required=recorded_required) == 0
    target = root / ".weside" / "optimization" / "reports" / "flow-2026-11-10.md"
    text = target.read_text(encoding="utf-8")
    # the file's day is the one in time.zone: 12:00 UTC is already the 11th in Kiritimati (+14)
    (root / ".weside" / "config.json").write_text('{"time": {"zone": "Pacific/Kiritimati"}}')
    assert fr.main(["--md"], now=NOW, cwd=root, run=FakeGh(), required=recorded_required) == 0
    assert (target.parent / "flow-2026-11-11.md").is_file()
    assert "| Heads per code PR | 3 | 2 | 2 | one head 33 % |" in text
    assert "## Writers per transition" in text
    assert "## Flow efficiency" in text
    assert "| Waiting by kind: waiting:ci |  |  |  | n/a (no source yet) |  |" in text


def test_json_and_since_forms(tmp_path, capsys):
    root = repo(tmp_path)
    assert (
        fr.main(
            ["--json", "--since", "2026-11-08"],
            now=NOW,
            cwd=root,
            run=FakeGh(),
            required=recorded_required,
        )
        == 0
    )
    out = json.loads(capsys.readouterr().out)
    flow = {r["row"]: r for r in out["flow_efficiency"]["rows"]}
    assert flow["Worker efficiency (ratio)"]["value"].endswith("stop = last probe, ±5 min")
    assert (
        out["flow_efficiency"]["summary"]["waiting"]["waiting:ci"]["hours"]
        == "n/a (no source yet)"
    )
    assert out["since"] == "2026-11-08T00:00Z"
    assert out["until"] == "2026-11-10T12:00Z"
    with pytest.raises(SystemExit) as stop:
        fr.main(["--since", "soon"], now=NOW, cwd=root, run=FakeGh(), required=no_required)
    assert stop.value.code == 2


def test_story_key_prefers_the_title_and_upper_cases_a_branch_key():
    pr = {"title": "docs(PROJ-7): plan", "branch": "docs/proj-8-x"}
    assert fr.story_key(pr, "[A-Z]+-\\d+") == "PROJ-7"
    assert fr.story_key({"title": "fix", "branch": "fix/proj-8-x"}, "[A-Z]+-\\d+") == "PROJ-8"
    assert fr.story_key({"title": "chore", "branch": "renovate/deps"}, "[A-Z]+-\\d+") is None


def test_required_checks_red_heads_by_outcome(tmp_path):
    root = repo(tmp_path)
    rows, _ = report(root)
    r = rows["Required checks: red heads"]
    # Lint: #1 a1 fixed on a2, #3 c1 (timed out) fixed on c2, #4 d1 open; b1's cancel is no red.
    # Claude Review: #1 a1 rerun green on a1, #5 e1 a red status open; Docs is not required.
    assert r["n"] == 5
    assert r["checks"] == {
        "Claude Review": {"rerun green": 1, "open": 1},
        "Lint": {"fixed": 2, "open": 1},
    }
    assert r["value"] == (
        "Claude Review 2 (fixed 0, rerun green 1, open 1) · Lint 3 (fixed 2, rerun green 0, open 1)"
    )
    assert fr.CONSTRUCTION_ROW not in rows

    # A check red by construction (a version check) gets its own row, outside the totals.
    (root / ".weside").mkdir(exist_ok=True)
    (root / ".weside" / "config.json").write_text(
        json.dumps({"flow": {"construction_checks": ["Lint", "Not Required"]}}), encoding="utf-8"
    )
    rows, out = report(root)
    r = rows["Required checks: red heads"]
    assert (r["n"], r["checks"]) == (2, {"Claude Review": {"rerun green": 1, "open": 1}})
    built = rows[fr.CONSTRUCTION_ROW]
    assert (built["n"], built["value"]) == (3, "Lint 3 by construction")
    names = [x["row"] for x in out["rows"]]
    assert names.index(fr.CONSTRUCTION_ROW) == names.index("Required checks: red heads") + 1


def test_required_checks_na_without_required_checks_or_reader(tmp_path):
    root = repo(tmp_path)
    fake = FakeGh()
    rows, _ = report(root, run=fake, required=no_required)
    r = rows["Required checks: red heads"]
    assert r["value"] == "n/a (no required checks on the default branch)"
    assert not any("checkRuns" in b["query"] for b in fake.bodies)  # no check runs asked for

    def broken(repo):
        raise fr.SourceMissingError("gh: HTTP 404")

    rows, _ = report(root, required=broken)
    assert rows["Required checks: red heads"]["value"] == "n/a (gh: HTTP 404)"
    assert rows["Heads per code PR"]["n"] == 3  # the other GitHub rows stand


def test_required_checks_reads_through_the_shared_reader(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    fake = bin_dir / "gh"
    fake.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> {calls}\n'
        'case "$2" in\n'
        "  */rules/branches/*) printf 'Lint\\nClaude Review\\n' ;;\n"
        "  */branches/*) printf 'Lint\\n' ;;\n"
        "  *) echo main ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    assert fr.required_checks("acme/app") == ["Claude Review", "Lint"]
    asked = calls.read_text().splitlines()
    assert asked[0].startswith("api repos/acme/app --jq")  # the default branch first
    assert asked[1].startswith("api repos/acme/app/rules/branches/main")
    fake.write_text("#!/bin/sh\necho 'HTTP 403: forbidden' >&2\nexit 1\n", encoding="utf-8")
    with pytest.raises(fr.SourceMissingError, match="gh: HTTP 403: forbidden"):
        fr.required_checks("acme/app")
