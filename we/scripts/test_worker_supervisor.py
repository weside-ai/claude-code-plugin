"""worker_supervisor.py with fake sessions, a fake clock and temp repos: seen stops, cleanup, gc."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import worker_supervisor as ws

MIB = 1024 * 1024

DEAD_PID = 2**22 + 7  # above pid_max on a default kernel: no process holds it
NAME = "AC-12-impl"


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def _row(pid, **extra):
    return {
        "name": NAME,
        "id": "bg1",
        "sessionId": "s1",
        "kind": "background",
        "pid": pid,
        **extra,
    }


def _transcript(projects: Path, entries):
    d = projects / "-tree"
    d.mkdir(parents=True, exist_ok=True)
    (d / "s1.jsonl").write_text("".join(json.dumps(e) + "\n" for e in entries))


def _feed(*frames):
    """`sessions()` returning each frame once, the last one forever."""
    frames = list(frames)

    def sessions():
        return frames.pop(0) if len(frames) > 1 else frames[0]

    return sessions


@pytest.fixture
def box(tmp_path, monkeypatch):
    state, projects = tmp_path / "state", tmp_path / "projects"
    state.mkdir()
    monkeypatch.setenv("WE_WORKER_STATE_DIR", str(state))  # write_marker's launched.jsonl
    (state / f"{NAME}.settings.json").write_text("{}")
    (state / f"{NAME}.json").write_text(json.dumps({"deadline": "2999-01-01T00:00:00Z"}))
    sent, items = [], []
    clock = Clock()

    stops = []

    def run(*frames, send_ok=True, limits=None, tree="/tree"):
        return ws.supervise(
            NAME,
            tree,
            sessions=_feed(*frames),
            clock=clock,
            sleep=clock.sleep,
            send=lambda text: sent.append(text) or send_ok,
            board=lambda _tree, iid, title, _body="": items.append((iid, title)) or True,
            state=state,
            projects=projects,
            stop=lambda row: stops.append(row["id"]) or True,
            limits=limits,
            jobs=tmp_path / "jobs",
        )

    return {
        "state": state,
        "projects": projects,
        "sent": sent,
        "items": items,
        "stops": stops,
        "run": run,
        "jobs": tmp_path / "jobs",
    }


LIVE, GONE = [_row(os.getpid())], [_row(DEAD_PID)]
USAGE = {
    "type": "assistant",
    "isApiErrorMessage": True,
    "error": "rate_limit",
    "message": {"content": [{"type": "text", "text": "limit"}]},
}


@pytest.mark.parametrize(
    "entry, deadline, reason",
    [
        (USAGE, "2999-01-01T00:00:00Z", "usage-limit"),
        ({**USAGE, "error": "authentication_failed"}, "2999-01-01T00:00:00Z", "auth"),
        (
            {"type": "assistant", "message": {"content": "done"}},
            "1970-01-02T00:00:00Z",
            "time-limit",
        ),
    ],
)
def test_an_end_with_a_reason_tells_the_starter_once_and_keeps_a_resumable_workers_files(
    box, entry, deadline, reason
):
    _transcript(box["projects"], [entry])
    (box["state"] / f"{NAME}.json").write_text(json.dumps({"deadline": deadline}))
    assert box["run"](LIVE, LIVE, []) == reason
    (line,) = box["sent"]
    assert (
        f"ended ({reason})" in line and f"we-worker {NAME} --tree /tree --bg --resume s1" in line
    )
    assert not box["items"]
    kept = sorted(p.name for p in box["state"].iterdir())
    resume = f"{NAME}.resume.json"  # `--resume <name>` finds it once claude agents drops the row
    files = [f"{NAME}.json", resume, f"{NAME}.settings.json"]
    assert kept == ([resume] if reason == "time-limit" else files)
    assert ws.kept_session(box["state"], NAME) == "s1"


def test_a_starter_out_of_reach_gets_the_line_on_the_board(box):
    _transcript(box["projects"], [USAGE])
    box["run"](LIVE, GONE, send_ok=False)
    ((iid, title),) = box["items"]
    assert iid == f"W-{NAME}-end-s1" and "usage-limit" in title


def test_a_plain_end_or_a_stop_tells_nobody_and_a_resumed_name_keeps_its_files(box):
    _transcript(box["projects"], [{"type": "assistant", "message": {"content": "done"}}])
    assert box["run"](LIVE, GONE) == "ended" and not box["sent"]
    assert not list(box["state"].iterdir())
    _transcript(box["projects"], [USAGE])
    (box["state"] / f"{NAME}.json").write_text("{}")  # no settings file: we-worker stop ran
    assert box["run"](LIVE, GONE) == "stopped" and not box["sent"]
    (box["state"] / f"{NAME}.settings.json").write_text("{}")
    other = {**_row(os.getpid()), "id": "bg2", "sessionId": "s2", "pid": os.getppid()}
    box["run"](LIVE, [_row(DEAD_PID), other])
    assert (box["state"] / f"{NAME}.settings.json").exists()


def test_a_permission_prompt_older_than_15_min_is_one_board_item(box):
    _transcript(
        box["projects"],
        [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "toolu_0001abcd", "name": "Bash", "input": {}}
                    ]
                },
            }
        ],
    )
    waiting = [_row(os.getpid(), waitingFor="permission prompt")]
    frames = [LIVE] + [waiting] * 40 + [GONE]  # 40 polls of 30 s: 20 minutes on one prompt
    box["run"](*frames)
    assert [iid for iid, _t in box["items"]] == [f"W-{NAME}-0001abcd"]


# --- blocked notice and idle stop: one sample is 30 s, so 2 frames are a minute ----------------

ON = {"blocked_notify_minutes": 15 * 60.0, "idle_stop_minutes": 30 * 60.0}
SAID = {"type": "assistant", "message": {"content": [{"type": "text", "text": "x\nwaits on gh"}]}}


def _minutes(n, **row):
    return [[_row(os.getpid(), **row)]] * (2 * n)


def test_a_worker_blocked_15_min_is_named_to_its_starter_once_per_block(box):
    """Red: 312 of 485 worker hours were `blocked` and the starter was never told."""
    _transcript(box["projects"], [SAID])
    blocked = _minutes(20, state="blocked")
    box["run"](
        LIVE,
        *blocked,
        *_minutes(1, state="working"),
        *blocked,
        *_minutes(10, state="blocked"),
        GONE,
        limits=ON,
    )
    lines = [t for t in box["sent"] if "blocked" in t]
    assert len(lines) == 2, box["sent"]  # two blocks of 20 and 30 min, one line each
    assert lines[0].startswith(f"we-worker: {NAME} blocked since ") and lines[0].endswith(
        " UTC: waits on gh"
    ), lines[0]


def test_a_worker_first_listed_without_a_pid_stays_supervised_and_is_stopped_when_done(box):
    """Red arm (22.11.): a `claude --bg` row lists `pid: null` while it starts. The supervisor
    bound that `null`, found no row on its next poll and ended after 35 s ("ended" in its log)
    with the worker still running: a `done` card worker held a pool slot for over an hour."""
    starting = [_row(None, state="working")]
    box["run"](starting, *_minutes(31, state="done"), GONE, limits=ON)
    assert box["stops"] == ["bg1"]


def test_a_block_shorter_than_the_limit_or_a_notice_turned_off_says_nothing(box):
    box["run"](LIVE, *_minutes(14, state="blocked"), GONE, limits=ON)
    box["run"](
        LIVE, *_minutes(60, state="blocked"), GONE, limits={**ON, "blocked_notify_minutes": None}
    )
    assert not box["sent"] and not box["stops"]


def test_a_blocked_notice_the_socket_refuses_goes_to_the_board(box):
    box["run"](LIVE, *_minutes(16, state="blocked"), GONE, limits=ON, send_ok=False)
    ((iid, title),) = box["items"]
    assert iid.startswith(f"W-{NAME}-blocked-") and "no status line" in title


def test_a_done_worker_idle_30_min_is_stopped_once_and_its_starter_told(box):
    """Red: 161 workers sat idle after their report, median 0.84 h, p90 4 h."""
    box["run"](LIVE, *_minutes(29, state="done"), *_minutes(2, state="done"), GONE, limits=ON)
    assert box["stops"] == ["bg1"]
    assert any("stopped after 30 min idle" in t and "tree stays: /tree" in t for t in box["sent"])


@pytest.mark.parametrize(
    "rows",
    [
        _minutes(60, state="blocked"),
        _minutes(60, state="working", status="idle"),
        _minutes(29, state="done") + _minutes(1, state="working") + _minutes(29, state="done"),
        _minutes(60, status="idle"),  # a window worker that sent no report
    ],
    ids=["blocked", "working", "done-twice-under-the-limit", "window-without-report"],
)
def test_never_stopped_while_blocked_working_or_without_its_report(box, rows):
    box["run"](LIVE, *rows, GONE, limits=ON)
    assert not box["stops"]


def test_never_stopped_while_its_job_runs_a_background_task(box):
    """Red: a worker that reported and waits on its CI watcher reads `done`; 30 of 844 `done` job
    states still ran a background shell."""
    job = box["jobs"] / "bg1"
    job.mkdir(parents=True)
    job.joinpath("state.json").write_text(
        json.dumps({"state": "done", "inFlight": {"tasks": 1, "kinds": ["local_bash"]}})
    )
    box["run"](LIVE, *_minutes(60, state="done"), GONE, limits=ON)
    assert not box["stops"]
    job.joinpath("state.json").write_text(json.dumps({"state": "done", "inFlight": {"tasks": 0}}))
    box["run"](LIVE, *_minutes(31, state="done"), GONE, limits=ON)
    assert box["stops"] == ["bg1"]


def test_never_stopped_with_a_queued_start_of_its_name_or_the_stop_turned_off(box):
    (box["state"] / "queue").mkdir()
    (box["state"] / "queue" / f"{NAME}.json").write_text(
        json.dumps({"name": NAME, "queued_at": 1})
    )
    box["run"](LIVE, *_minutes(60, state="done"), GONE, limits=ON)
    (box["state"] / "queue" / f"{NAME}.json").unlink()
    box["run"](LIVE, *_minutes(60, state="done"), GONE, limits={**ON, "idle_stop_minutes": None})
    assert not box["stops"]


def test_never_stopped_when_its_marker_says_parked(box, repo):
    ws.wl.write_marker(repo, name=NAME, starter="lead", parked="checkpoint pending")
    box["run"](LIVE, *_minutes(60, state="done"), GONE, limits=ON, tree=str(repo))
    assert not box["stops"]


def test_a_window_worker_idle_after_its_report_is_stopped(box, repo):
    ws.wl.write_marker(repo, name=NAME, starter="lead")
    report = {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": "SendMessage", "input": {"to": "lead"}}]
        },
    }
    _transcript(box["projects"], [{"type": "user", "message": {"content": "go"}}, report])
    box["run"](LIVE, *_minutes(31, status="idle"), GONE, limits=ON, tree=str(repo))
    assert box["stops"] == ["bg1"]


@pytest.mark.parametrize(
    "block, want",
    [
        (
            {},
            {
                "blocked_notify_minutes": 900.0,
                "idle_stop_minutes": 1800.0,
                "unreported_notify_minutes": 300.0,
            },
        ),
        (
            {
                "blocked_notify_minutes": 0,
                "idle_stop_minutes": None,
                "unreported_notify_minutes": 0,
            },
            {
                "blocked_notify_minutes": None,
                "idle_stop_minutes": None,
                "unreported_notify_minutes": None,
            },
        ),
        (
            {"blocked_notify_minutes": 5, "idle_stop_minutes": "soon"},
            {
                "blocked_notify_minutes": 300.0,
                "idle_stop_minutes": 1800.0,
                "unreported_notify_minutes": 300.0,
            },
        ),
    ],
)
def test_idle_limits_read_the_workers_block(repo, block, want):
    (repo / ".weside").mkdir(exist_ok=True)
    (repo / ".weside" / "config.json").write_text(json.dumps({"workers": block}))
    assert ws.idle_limits(str(repo)) == want


# A worker's end always reaches its starter: a report left as its final text (no SendMessage)
# reached the master 103 min late.

QUIET = {**ON, "unreported_notify_minutes": 5 * 60.0}
GO = {"type": "user", "message": {"content": "go"}}
LAST = {
    "type": "assistant",
    "uuid": "u1",
    "message": {"content": [{"type": "text", "text": "report:\nAC 1 green, PR #7 open"}]},
}
SENT = {
    "type": "assistant",
    "uuid": "u2",
    "message": {"content": [{"type": "tool_use", "name": "SendMessage", "input": {"to": "lead"}}]},
}


def test_unreported_idle_line(box, repo):
    ws.wl.write_marker(repo, name=NAME, starter="lead")
    _transcript(box["projects"], [GO, LAST])
    box["run"](LIVE, *_minutes(20, state="idle"), GONE, limits=QUIET, tree=str(repo))
    lines = [t for t in box["sent"] if "without a report" in t]
    assert len(lines) == 1, box[
        "sent"
    ]  # once per turn, not once per poll, and no end line after it
    assert lines[0].startswith(f"we-worker: {NAME} idle since ") and lines[0].endswith(
        " UTC without a report: AC 1 green, PR #7 open"
    ), lines[0]
    box["sent"].clear()
    _transcript(box["projects"], [GO, LAST, SENT])  # the report went out: no line
    box["run"](LIVE, *_minutes(20, state="idle"), GONE, limits=QUIET, tree=str(repo))
    assert not [t for t in box["sent"] if "report" in t], box["sent"]


def test_plain_exit_line(box, repo):
    ws.wl.write_marker(repo, name=NAME, starter="lead")
    _transcript(box["projects"], [GO, LAST])
    assert (
        box["run"](LIVE, *_minutes(2, state="working"), GONE, limits=QUIET, tree=str(repo))
        == "ended"
    )
    assert box["sent"] == [f"we-worker: {NAME} ended without a report: AC 1 green, PR #7 open"]
    box["sent"].clear()
    (box["state"] / f"{NAME}.settings.json").write_text("{}")
    _transcript(box["projects"], [GO, LAST, SENT])
    box["run"](LIVE, GONE, limits=QUIET, tree=str(repo))
    assert not box["sent"]
    (box["state"] / f"{NAME}.settings.json").write_text("{}")
    _transcript(box["projects"], [GO, LAST])
    box["run"](LIVE, GONE, limits=QUIET, send_ok=False, tree=str(repo))
    ((iid, title),) = box["items"]
    assert iid == f"W-{NAME}-end-s1" and title.endswith(
        "ended without a report: AC 1 green, PR #7 open"
    )


def test_a_session_that_never_shows_up_keeps_its_files(box):
    assert box["run"]([]) == "never-seen"
    assert (box["state"] / f"{NAME}.settings.json").exists()


# --- gc ----------------------------------------------------------------------------------------


def _git(cwd, *args):
    subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path):
    origin, main = tmp_path / "origin.git", tmp_path / "repo"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(main))
    _git(main, "commit", "-q", "--allow-empty", "-m", "init")
    _git(main, "push", "-q", "origin", "HEAD:main")
    _git(main, "remote", "set-head", "origin", "main")
    return main


def _tree(repo, name, merged, dirty=False):
    path = repo.parent / f"repo-{name}"
    _git(repo, "worktree", "add", "-q", "-b", f"feat/{name}", str(path), "origin/main")
    _git(path, "commit", "-q", "--allow-empty", "-m", name)
    if merged:
        _git(path, "push", "-q", "origin", "HEAD:main")
    gd = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--absolute-git-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    Path(gd, "we-worker.json").write_text(json.dumps({"name": name}))
    if dirty:
        (path / "wip.txt").write_text("x")
    return path


def test_gc_removes_only_dead_sessions_own_files_and_lists_merged_clean_trees(
    tmp_path, repo, monkeypatch
):
    monkeypatch.setenv("PATH", f"{tmp_path / 'nobin'}{os.pathsep}/usr/bin:/bin")  # no gh
    state, jobs = tmp_path / "state", tmp_path / "jobs"
    state.mkdir()
    for n in ("AC-1-live", "AC-2-dead", "AC-3-fresh"):
        (state / f"{n}.settings.json").write_text("{}")
        (state / f"{n}.json").write_text("{}")
    for j in ("j-live", "j-gone"):
        (jobs / j).mkdir(parents=True)
        (jobs / j / "state.json").write_text(json.dumps({"state": "stopped", "sessionId": j}))
    merged_tree = _tree(repo, "AC-2-dead", merged=True)
    open_tree = _tree(repo, "AC-4-open", merged=False)
    dirty = _tree(repo, "AC-5-dirty", merged=True, dirty=True)
    live_tree = _tree(repo, "AC-1-live", merged=True)
    bare = repo.parent / "repo-AC-6-bare"  # no commit of its own: in origin/main, never "merged"
    _git(repo, "worktree", "add", "-q", "-b", "feat/AC-6-bare", str(bare), "origin/main")
    Path(_gd(bare), "we-worker.json").write_text(json.dumps({"name": "AC-6-bare"}))
    old = time.time() - 3600
    for p in [
        *state.iterdir(),
        *(Path(_gd(t), "we-worker.json") for t in (merged_tree, open_tree, dirty, live_tree)),
    ]:
        if "fresh" not in p.name:
            os.utime(p, (old, old))
    rows = [
        {"name": "AC-1-live", "id": "j-live", "sessionId": "x", "pid": os.getpid()},
        {"name": "AC-2-dead", "id": "old", "sessionId": "y", "pid": DEAD_PID},
    ]
    # a dead worker on a usage limit is resumable: its files stay 7 days, then go
    projects = tmp_path / "projects"
    (projects / "-p").mkdir(parents=True)
    (projects / "-p" / "z.jsonl").write_text(json.dumps(USAGE) + "\n")
    rows.append({"name": "AC-7-quota", "id": "q", "sessionId": "z", "pid": DEAD_PID})
    week = time.time() - 8 * 24 * 3600
    for n, age in (("AC-7-quota", old), ("AC-8-quota", week)):
        (state / f"{n}.json").write_text("{}")
        os.utime(state / f"{n}.json", (age, age))
    # a stopped worker's resume file stays 7 days like a resumable one's
    for n, age in (("AC-9-stopped", old), ("AC-10-stopped", week)):
        (state / f"{n}.resume.json").write_text("{}")
        os.utime(state / f"{n}.resume.json", (age, age))
    rows.append({"name": "AC-8-quota", "id": "q8", "sessionId": "z", "pid": DEAD_PID})
    # a queued start whose waiter died: gone once its deadline passed, kept before
    ws.enqueue(state, "AC-11-late", "/t", [], "brief", None, 60, time.time() - 3600)
    ws.enqueue(state, "AC-12-wait", "/t", [], None, None, 7200, time.time())
    run = lambda apply: ws.gc(  # noqa: E731
        repo, apply, sessions=lambda: rows, state=state, jobs=jobs, projects=projects
    )
    dry = run(False)
    assert (state / "AC-2-dead.json").exists() and Path(_gd(open_tree), "we-worker.json").exists()
    lines = run(True)
    assert dry == [x.replace("removed", "would remove") for x in lines]
    assert sorted(p.name for p in state.iterdir() if p.is_file()) == sorted(
        [f"{n}{s}" for n in ("AC-1-live", "AC-3-fresh") for s in (".json", ".settings.json")]
        + ["AC-7-quota.json", "AC-9-stopped.resume.json"]
    )
    assert [d["name"] for d in ws.queued(state)] == ["AC-12-wait"]
    assert not (state / "queue" / "AC-11-late.brief.md").exists()
    assert sorted(p.name for p in jobs.iterdir()) == ["j-gone", "j-live"]  # never removed
    assert any(x.startswith("1 job directories") for x in lines)
    trees = [x for x in lines if x.startswith("worktree")]
    assert len(trees) == 1 and "repo-AC-2-dead" in trees[0] and "git worktree remove" in trees[0]
    assert Path(_gd(merged_tree), "we-worker.json").exists()  # the listed tree keeps its marker
    assert Path(_gd(live_tree), "we-worker.json").exists()
    assert not Path(_gd(open_tree), "we-worker.json").exists()
    assert f"keep {dirty}: uncommitted changes" in lines and dirty.exists()


def _gd(tree):
    return subprocess.run(
        ["git", "-C", str(tree), "rev-parse", "--absolute-git-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_gc_refuses_when_the_sessions_cannot_be_read(tmp_path, repo):
    def broken():
        raise ws.wl.LaunchError("claude agents --json timed out")

    with pytest.raises(ws.wl.LaunchError):
        ws.gc(repo, True, sessions=broken, state=tmp_path, jobs=tmp_path)


# --- queue -------------------------------------------------------------------------------------


@pytest.fixture
def queue(tmp_path):
    clock, sent, tried = Clock(), [], []

    def put(name, at, timeout_s=7200):
        ws.enqueue(tmp_path, name, "/tree", [name, "--bg"], "## Goal\n", "Lead", timeout_s, at)
        ws.set_waiter(tmp_path, name, os.getpid())

    def wait(name, results, on_sleep=None, room=lambda _state: True):
        """Run the waiter of `name`; `results` are the fake start's exit codes in turn (3: the
        capacity check refuses, 4: the machine has no room)."""
        codes = list(results)

        def start(doc):
            tried.append(doc["name"])
            return (codes.pop(0) if len(codes) > 1 else codes[0]), "we-worker: started"

        def sleep(s):
            clock.sleep(s)
            if on_sleep:
                on_sleep()

        return ws.wait_queue(
            tmp_path,
            name,
            start=start,
            room=room,
            clock=clock,
            sleep=sleep,
            send=lambda t: sent.append(t) is None,
        )

    return {
        "state": tmp_path,
        "clock": clock,
        "sent": sent,
        "tried": tried,
        "put": put,
        "wait": wait,
    }


def test_a_queued_start_waits_for_room_and_tells_its_starter(queue):
    queue["put"]("AC-1-a", queue["clock"]())
    assert queue["wait"]("AC-1-a", [3, 3, 0]) == "started"
    assert queue["tried"] == ["AC-1-a"] * 3
    (line,) = queue["sent"]
    assert "queued start of AC-1-a started after 1 min" in line
    assert not ws.queued(queue["state"])
    brief = queue["state"] / "queue" / "AC-1-a.brief.md"
    assert not brief.exists()


def test_a_queued_start_holds_at_the_resource_rule_before_it_tries(queue, tmp_path, monkeypatch):
    """Kiska (22.11.): the waiter checks the room rule the start checks; a start's exit 4 (no room)
    keeps it waiting like the cap's 3."""
    host = tmp_path / "host"
    group = host / "sys" / "fs" / "cgroup"
    group.mkdir(parents=True)
    (host / "proc" / "self").mkdir(parents=True)
    (host / "proc" / "self" / "cgroup").write_text("0::/\n")
    (group / "memory.max").write_text(f"{100 * MIB}\n")
    (group / "memory.current").write_text(f"{90 * MIB}\n")
    (group / "memory.stat").write_text(f"file {5 * MIB}\nshmem 0\n")  # 85 % >= 84 %
    monkeypatch.setenv("WE_WORKER_HOST_ROOT", str(host))
    assert not ws.machine_room(queue["state"])
    calls = []

    def room(state):
        calls.append(state)
        if len(calls) == 3:  # the peak is over: 40 %
            (group / "memory.current").write_text(f"{45 * MIB}\n")
        return ws.machine_room(state)

    queue["put"]("AC-1-a", queue["clock"]())
    assert queue["wait"]("AC-1-a", [4, 0], room=room) == "started"
    assert len(calls) == 4 and queue["tried"] == ["AC-1-a"] * 2  # held twice, then 4, then 0


def test_queued_starts_go_first_come_first_served(queue):
    t = queue["clock"]()
    queue["put"]("AC-1-a", t)
    queue["put"]("AC-2-b", t + 1)
    # the older entry leaves the queue after the first poll: only then does the younger one try
    drop = lambda: ws._drop(queue["state"], "AC-1-a")  # noqa: E731
    assert queue["wait"]("AC-2-b", [0], on_sleep=drop) == "started"
    assert queue["tried"] == ["AC-2-b"]
    assert queue["clock"]() > t + ws.QUEUE_POLL_S - 1  # it waited a poll behind AC-1-a


def test_a_queued_start_times_out_and_says_so(queue):
    queue["put"]("AC-1-a", queue["clock"](), timeout_s=90)
    assert queue["wait"]("AC-1-a", [3]) == "timeout"
    (line,) = queue["sent"]
    assert "timed out" in line and "nothing started" in line
    assert not ws.queued(queue["state"])


def test_stop_removes_a_queued_start_and_its_waiter_gives_up(queue):
    queue["put"]("AC-1-a", queue["clock"]())
    stop = lambda: ws._drop(queue["state"], "AC-1-a")  # noqa: E731  (unqueue without a kill)
    assert queue["wait"]("AC-1-a", [3], on_sleep=stop) == "removed"
    assert not queue["sent"]


def test_a_name_already_queued_refuses_unless_its_waiter_is_gone(queue):
    queue["put"]("AC-1-a", queue["clock"]())
    with pytest.raises(ws.wl.LaunchError, match="already queued"):
        queue["put"]("AC-1-a", queue["clock"]())
    # an entry without a waiter (none spawned) neither blocks its name nor the younger entries
    ws.enqueue(queue["state"], "AC-2-b", "/tree", [], None, None, 60, queue["clock"]())
    ws.enqueue(queue["state"], "AC-2-b", "/tree", [], None, None, 60, queue["clock"]())
    queue["put"]("AC-3-c", queue["clock"]())
    assert not ws._may_try(queue["state"], "AC-3-c")  # AC-1-a waits ahead
    ws.enqueue(
        queue["state"], "AC-4-u", "/tree", [], None, None, 60, queue["clock"](), lane="utility"
    )
    assert ws._may_try(queue["state"], "AC-4-u")  # a build entry never holds the utility lane
    ws._drop(queue["state"], "AC-1-a")
    assert ws._may_try(queue["state"], "AC-3-c")  # AC-2-b, without a waiter, is skipped
    # status: the position counts within its lane; a dead waiter is named, and restarted
    lines = ws.status_lines([], None, queue["state"], queue["state"], queue["clock"]())
    queued = {x.split()[1]: x for x in lines if x.startswith("queued ")}
    assert "position=1" in queued["AC-2-b"] and "position=2" in queued["AC-3-c"]
    assert "position=1" in queued["AC-4-u"] and "lane=utility" in queued["AC-4-u"]
    assert queued["AC-2-b"].endswith(" dead waiter") and "dead" not in queued["AC-3-c"]
    assert "--restart-waiters" in lines[-1]
    only = ws.status_lines([], "AC-3-c", queue["state"], queue["state"], queue["clock"]())
    assert not [x for x in only if "--restart-waiters" in x]  # its waiter lives
    spawned = []
    assert ws.restart_waiters(queue["state"], spawned.append) == ["AC-2-b", "AC-4-u"]
    assert spawned == ["AC-2-b", "AC-4-u"]


def test_a_waiter_tries_past_entries_only_their_own_repo_limit_may_hold(queue):
    """T2 panel on #308: a head from a repo with a lower 5h limit held every other repo's queued
    start for up to its 2 h timeout; the capacity check decides whether it may pass."""
    state, t = queue["state"], queue["clock"]()
    ws.enqueue(state, "AC-1-a", "/tree", [], None, None, 60, t, {"max_active_5h_percent": 40})
    ws.set_waiter(state, "AC-1-a", os.getpid())
    queue["put"]("AC-2-b", t + 1)
    queue["put"]("AC-3-c", t + 2)
    assert ws._may_try(state, "AC-2-b")
    assert not ws._may_try(state, "AC-3-c")  # AC-2-b holds the machine's limits
    (state / "pool.json").write_text('{"max_active_5h_percent": 40}')
    assert not ws._may_try(state, "AC-2-b")  # 40 is no lower limit on this machine


def test_a_waiter_with_only_the_pid_alive_holds_nobody_up(queue):
    """T2 panel on #308: a dead waiter whose pid another process took counted as living and held
    every start until its deadline. The start time recorded at `set_waiter` tells them apart."""
    state = queue["state"]
    queue["put"]("AC-1-a", queue["clock"]())
    queue["put"]("AC-2-b", queue["clock"]() + 1)
    path = state / "queue" / "AC-1-a.json"
    doc = json.loads(path.read_text())
    assert doc["waiter_start"] == ws.proc_start(os.getpid())
    assert ws.waiter_lives(doc) and not ws._may_try(state, "AC-2-b")
    path.write_text(json.dumps({**doc, "waiter_start": doc["waiter_start"] + 1}))  # pid reused
    assert not ws.waiter_lives(ws._read(path)) and ws._may_try(state, "AC-2-b")
    del doc["waiter_start"]  # an entry from before the start time: the pid alone decides
    path.write_text(json.dumps(doc))
    assert ws.waiter_lives(ws._read(path)) and not ws._may_try(state, "AC-2-b")


def test_with_an_unreadable_pool_file_only_the_head_tries(queue):
    """An unreadable `pool.json` leaves no machine limit to compare with: an entry ahead that
    only its own repo limit holds back is not passed, only the head tries."""
    state, t = queue["state"], queue["clock"]()
    ws.enqueue(state, "AC-1-a", "/tree", [], None, None, 60, t, {"max_active_5h_percent": 40})
    ws.set_waiter(state, "AC-1-a", os.getpid())
    queue["put"]("AC-2-b", t + 1)
    assert ws._may_try(state, "AC-2-b")  # readable: the head's lower limit lets it past
    (state / "pool.json").write_text("{not json")
    assert ws._may_try(state, "AC-1-a")
    assert not ws._may_try(state, "AC-2-b")


@pytest.mark.parametrize("name", ["../AC-1", "AC-1/x", ".hidden", "AC..1"])
def test_a_path_is_no_worker_name_for_the_state_dir(tmp_path, monkeypatch, name):
    monkeypatch.setenv("WE_WORKER_STATE_DIR", str(tmp_path))
    (tmp_path / "AC-1.json").write_text("{}")
    assert ws.main(["unqueue", "--name", name]) == 2
    assert (tmp_path / "AC-1.json").exists()


def test_remove_files_takes_the_brief_and_keeps_the_starter_log(tmp_path):
    """A worker's end removes its settings, marker and brief file; `launched.jsonl` stays."""
    for f in (f"{NAME}.settings.json", f"{NAME}.json", f"{NAME}.brief.md", "launched.jsonl"):
        (tmp_path / f).write_text("x")
    gone = ws._remove_files(tmp_path, NAME)
    assert sorted(gone) == sorted([f"{NAME}.settings.json", f"{NAME}.json", f"{NAME}.brief.md"])
    assert [p.name for p in tmp_path.iterdir()] == ["launched.jsonl"]
