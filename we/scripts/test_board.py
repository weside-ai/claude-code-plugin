"""board.py: one class per verb on a shared state_dir (a temp board.json and its answers file)."""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board  # noqa: E402
import board_freeze  # noqa: E402

BOARD = {
    "updated_by": "coord",
    "owner_queue": [
        {"id": "Q1", "session": "asker", "ask": "Ship it?"},
        {"id": "Q2", "session": "asker"},
    ],
    "news": [{"id": "N1", "title": "Prod is on 2.4"}],
}


@pytest.fixture
def state_dir(tmp_path):
    (tmp_path / "board.json").write_text(json.dumps(BOARD), encoding="utf-8")
    return tmp_path


def run(state_dir, *argv):
    return board.main(["--board", str(state_dir / "board.json"), *argv])


def lines(state_dir):
    path = state_dir / "board-answers.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class TestAnswer:
    def test_appends_a_chat_line_with_via_and_quote_and_prints_it(self, state_dir, capsys):
        assert (
            run(
                state_dir,
                "answer",
                "Q1",
                "accept",
                "--session",
                "asker",
                "--via",
                "chat",
                "--quote",
                "go ahead",
            )
            == 0
        )
        [line] = lines(state_dir)
        assert {k: line[k] for k in ("id", "answer", "session", "via", "quote")} == {
            "id": "Q1",
            "answer": "accept",
            "session": "asker",
            "via": "chat",
            "quote": "go ahead",
        }
        assert line["ts"].endswith("Z") and len(line["ts"]) == len("2026-11-03T16:00:00.000Z")
        assert json.loads(capsys.readouterr().out) == line

    def test_a_news_id_is_known_too(self, state_dir):
        assert run(state_dir, "answer", "N1", "info", "--session", "coord", "--via", "chat") == 0
        assert [a["id"] for a in lines(state_dir)] == ["N1"]

    def test_refuses_an_unknown_id_by_name_and_writes_nothing(self, state_dir, capsys):
        assert run(state_dir, "answer", "Q9", "accept", "--session", "asker", "--via", "chat") == 1
        assert "Q9 is in neither owner_queue nor news" in capsys.readouterr().err
        assert lines(state_dir) == []

    @pytest.mark.parametrize("kind", ["yes", "read", "decided"])
    def test_refuses_a_kind_outside_the_five_by_name(self, state_dir, capsys, kind):
        with pytest.raises(SystemExit) as stop:
            run(state_dir, "answer", "Q1", kind, "--session", "asker", "--via", "chat")
        assert stop.value.code == 2
        assert f"invalid choice: '{kind}'" in capsys.readouterr().err
        assert lines(state_dir) == []

    def test_refuses_a_via_other_than_chat(self, state_dir):
        with pytest.raises(SystemExit):
            run(
                state_dir, "answer", "Q1", "accept", "--session", "asker", "--via", "chat in coord"
            )
        assert lines(state_dir) == []

    def test_a_second_answer_on_a_closed_id_is_a_recorded_duplicate(self, state_dir, capsys):
        assert run(state_dir, "answer", "Q1", "deny", "--session", "asker", "--via", "chat") == 0
        capsys.readouterr()
        assert run(state_dir, "answer", "Q1", "accept", "--session", "asker", "--via", "chat") == 0
        assert capsys.readouterr().out.strip() == (
            "board.py answer: Q1 is closed by deny; recorded as a duplicate, nothing runs again "
            "(a new question takes a new id)"
        )
        assert [a["answer"] for a in lines(state_dir)] == ["deny"]  # nothing to carry again
        log = (state_dir / "board-questions.jsonl").read_text().splitlines()
        [dup] = [json.loads(x) for x in log]
        assert {k: dup[k] for k in ("id", "outcome", "answer", "closed_by")} == {
            "id": "Q1",
            "outcome": "duplicate-answer",
            "answer": "accept",
            "closed_by": "deny",
        }

    def test_leaves_board_json_byte_identical(self, state_dir):
        before = (state_dir / "board.json").read_bytes()
        assert (
            run(state_dir, "answer", "Q2", "discuss", "--session", "coord", "--via", "chat") == 0
        )
        assert (state_dir / "board.json").read_bytes() == before

    def test_reads_a_file_holding_legacy_lines_without_error(self, state_dir):
        legacy = [
            '{"id": "Q1", "answer": "decided", "ts": "2026-11-01T10:00:00Z", "session": "coord", "via": "chat in coord"}',
            '{"id": "Q2", "answer": "entfällt", "ts": "2026-11-01T10:00:00Z"}',
            '{"id": "Q1",',
            '"a sentence"',
        ]
        (state_dir / "board-answers.jsonl").write_text("\n".join(legacy) + "\n", encoding="utf-8")
        assert run(state_dir, "answer", "Q1", "accept", "--session", "asker", "--via", "chat") == 0
        text = (state_dir / "board-answers.jsonl").read_text(encoding="utf-8").splitlines()
        assert text[:4] == legacy
        assert json.loads(text[4])["answer"] == "accept"

    def test_keeps_two_concurrent_writers_whole(self, state_dir):
        writer = (
            "import sys; sys.path.insert(0, sys.argv[1]); import board; s = board.StateDir(sys.argv[2])\n"
            "for i in range(300): s.append_answer('Q2', 'discuss', sys.argv[3], via='chat', quote='x' * 200)"
        )
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", writer, str(HERE), str(state_dir / "board.json"), name]
            )
            for name in ("one", "two")
        ]
        assert [p.wait(timeout=60) for p in procs] == [0, 0]
        got = lines(state_dir)
        assert len(got) == 600
        assert sorted({a["session"] for a in got}) == ["one", "two"]


FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write(json.dumps(args) + "\\n")
if args[:2] == ["pr", "list"]:
    repo = args[args.index("-R") + 1]
    if repo == "o/broken":
        sys.exit(1)
    print(json.dumps([
        {"number": 5, "autoMergeRequest": {"mergeMethod": "SQUASH"}},
        {"number": 6, "autoMergeRequest": None},
        {"number": 8, "autoMergeRequest": {"mergeMethod": "MERGE"}},
    ]))
elif args[:2] == ["pr", "merge"]:
    sys.exit(1 if args[2] == "8" else 0)
elif args[:2] == ["repo", "view"]:
    print("o/here")
elif args[:2] == ["issue", "list"]:
    repo = args[args.index("-R") + 1]
    if repo == "o/noissue":
        sys.exit(1)
    print(json.dumps([{"number": 3}] if repo == "o/frozen" else []))
elif args[:2] == ["issue", "create"]:
    repo = args[args.index("-R") + 1]
    if repo == "o/nocreate":
        sys.exit(1)
    print(f"https://github.com/{repo}/issues/41")
elif args[:2] == ["issue", "close"]:
    sys.exit(1 if os.environ.get("FAKE_GH_NO_CLOSE") else 0)
else:
    sys.exit(3)
"""


@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    log = tmp_path / "gh.log"
    monkeypatch.setenv("PATH", f"{bin_dir}:{__import__('os').environ['PATH']}")
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    return lambda: [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []


@pytest.fixture
def watched(state_dir, tmp_path, monkeypatch):
    """`state_dir/board.json` is the default board the merge hook reads; the cwd has no crew."""
    work = tmp_path / "work"
    (work / ".git").mkdir(parents=True)
    monkeypatch.chdir(work)
    monkeypatch.setattr(board, "DEFAULT_BOARD", str(state_dir / "board.json"))
    return state_dir


@pytest.mark.usefixtures("fake_gh")
class TestFreezeTarget:
    """`freeze`/`unfreeze` write only where the merge hook reads (`board_freeze.watched_board_files`)."""

    def test_freeze_refuses_a_board_the_hook_does_not_read(
        self, state_dir, tmp_path, monkeypatch, capsys
    ):
        work = tmp_path / "work"
        (work / ".git").mkdir(parents=True)
        monkeypatch.chdir(work)
        assert run(state_dir, "freeze", "--reason", "r", "--repo", "o/r") == 1
        err = capsys.readouterr().err
        assert f"the merge hook reads no freeze beside {state_dir / 'board.json'}" in err
        assert not (state_dir / "freeze.json").exists()

    def test_unfreeze_refuses_a_board_the_hook_does_not_read(
        self, state_dir, tmp_path, monkeypatch, capsys
    ):
        work = tmp_path / "work"
        (work / ".git").mkdir(parents=True)
        monkeypatch.chdir(work)
        (state_dir / "freeze.json").write_text(json.dumps({"reason": "x"}))
        assert run(state_dir, "unfreeze") == 1
        assert "the merge hook reads no freeze beside" in capsys.readouterr().err
        assert (state_dir / "freeze.json").exists()

    def test_a_relative_crew_board_file_is_read_beside_the_crew_file(self, tmp_path, monkeypatch):
        work = tmp_path / "work"
        (work / ".git").mkdir(parents=True)
        (work / ".weside" / "state").mkdir(parents=True)
        (work / ".weside" / "crew.json").write_text(
            json.dumps(
                {"version": 2, "roles": {}, "members": {}, "board": {"file": "state/board.json"}}
            )
        )
        (work / "sub").mkdir()
        monkeypatch.chdir(work / "sub")
        target = work / ".weside" / "state" / "board.json"
        assert (
            board.main(["--board", str(target), "freeze", "--reason", "r", "--repo", "o/r"]) == 0
        )
        flag_file = work / ".weside" / "state" / "freeze.json"
        assert json.loads(flag_file.read_text())["reason"] == "r"
        assert board_freeze.watched_board_files(work / "sub", board.DEFAULT_BOARD) == [target]


@pytest.mark.usefixtures("fake_gh", "watched")
class TestFreezeVerbs:
    """Cases that need the fake `gh` only on PATH."""

    def test_a_failed_listing_still_freezes(self, state_dir):
        assert run(state_dir, "freeze", "--reason", "r", "--repo", "o/broken") == 0
        flag = json.loads((state_dir / "freeze.json").read_text())
        assert flag["not_disarmed"] == [{"repo": "o/broken", "why": "listing the open PRs failed"}]

    def test_without_repo_the_freeze_covers_every_repo_and_disarms_the_current(
        self, state_dir, monkeypatch
    ):
        """owner 06.11.2026: a freeze without --repo, run from the workspace checkout,
        must still stop a merge in core; it disarms the current repo's armed PRs."""
        monkeypatch.setattr(board, "_crew_repos", lambda *_a, **_k: ["o/here"])
        assert run(state_dir, "freeze", "--reason", "r") == 0
        flag = json.loads((state_dir / "freeze.json").read_text())
        assert flag["repos"] == ["*"]
        assert {"repo": "o/here", "number": 5} in flag["disarmed"]
        assert board_freeze.covers(flag, "acme/core")

    def test_a_repo_that_names_no_repo_is_refused(self, state_dir, capsys):
        assert run(state_dir, "freeze", "--reason", "r", "--repo", "core") == 1
        assert "--repo takes OWNER/REPO or '*'" in capsys.readouterr().err
        assert not (state_dir / "freeze.json").exists()

    def test_a_url_repo_is_stored_as_its_slug(self, state_dir):
        assert (
            run(state_dir, "freeze", "--reason", "r", "--repo", "https://github.com/O/R.git") == 0
        )
        assert json.loads((state_dir / "freeze.json").read_text())["repos"] == ["o/r"]

    def test_an_explicit_repo_narrows_the_freeze(self, state_dir):
        assert run(state_dir, "freeze", "--reason", "r", "--repo", "acme/workspace") == 0
        flag = json.loads((state_dir / "freeze.json").read_text())
        assert flag["repos"] == ["acme/workspace"] and flag["scoped"] is True
        assert not board_freeze.covers(flag, "acme/core")
        assert board_freeze.covers(flag, "acme/workspace")

    def test_a_blank_reason_is_refused(self, state_dir, capsys):
        assert run(state_dir, "freeze", "--reason", " ", "--repo", "o/r") == 1
        assert "a freeze needs a reason" in capsys.readouterr().err
        assert not (state_dir / "freeze.json").exists()

    def test_the_hook_reads_what_freeze_writes(self, state_dir):
        run(state_dir, "freeze", "--reason", "incident", "--repo", "o/r")
        flag = board_freeze.read_flag(board_freeze.flag_path(state_dir / "board.json"))
        assert flag["reason"] == "incident"


@pytest.mark.usefixtures("watched")
class TestFreeze:
    def test_freeze_writes_the_flag_and_disarms_armed_prs(self, state_dir, fake_gh, capsys):
        assert run(state_dir, "freeze", "--reason", "incident", "--repo", "o/r", "--by", "k") == 0
        flag = json.loads((state_dir / "freeze.json").read_text())
        assert flag["reason"] == "incident" and flag["by"] == "k" and flag["since"]
        assert flag["disarmed"] == [{"repo": "o/r", "number": 5}]
        assert flag["not_disarmed"] == [
            {"repo": "o/r", "number": 8, "why": "--disable-auto failed"}
        ]
        merges = [c for c in fake_gh() if c[:2] == ["pr", "merge"]]
        assert merges == [
            ["pr", "merge", "5", "-R", "o/r", "--disable-auto"],
            ["pr", "merge", "8", "-R", "o/r", "--disable-auto"],
        ]
        assert json.loads(capsys.readouterr().out)["disarmed"] == flag["disarmed"]
        assert flag["issues"] == [{"repo": "o/r", "number": 41}]
        labels = [c for c in fake_gh() if c[:2] == ["label", "create"]]
        assert labels == [
            ["label", "create", "merge-freeze", "-R", "o/r", "--color", "b60205", "--force"]
        ]
        create = [c for c in fake_gh() if c[:2] == ["issue", "create"]]
        assert len(create) == 1 and create[0][create[0].index("--label") + 1] == "merge-freeze"
        assert create[0][create[0].index("--title") + 1] == "Merge freeze: incident"

    def test_unfreeze_removes_the_flag_and_rearms_nothing(self, state_dir, fake_gh, capsys):
        run(state_dir, "freeze", "--reason", "incident", "--repo", "o/r")
        capsys.readouterr()
        before = len(fake_gh())
        assert run(state_dir, "unfreeze") == 0
        out = capsys.readouterr().out
        assert "re-arm through the hook: o/r#5" in out
        assert not (state_dir / "freeze.json").exists()
        after = fake_gh()[before:]
        assert after == [
            ["issue", "close", "41", "-R", "o/r", "--comment", "Unfrozen: incident"]
        ]  # closes its own freeze issue, re-arms no PR

    def test_unfreeze_without_a_flag(self, state_dir, capsys):
        assert run(state_dir, "unfreeze") == 1
        assert "no freeze stands" in capsys.readouterr().err

    def test_unfreeze_lifts_a_torn_flag(self, state_dir):
        (state_dir / "freeze.json").write_text("{torn")
        assert run(state_dir, "unfreeze") == 0
        assert not (state_dir / "freeze.json").exists()

    @pytest.mark.usefixtures("fake_gh")
    def test_a_second_freeze_keeps_the_first_ones_disarmed(self, state_dir, capsys):
        run(state_dir, "freeze", "--reason", "one", "--repo", "o/r")
        flag = json.loads((state_dir / "freeze.json").read_text())
        flag["disarmed"].append({"repo": "o/old", "number": 1})
        (state_dir / "freeze.json").write_text(json.dumps(flag))
        run(state_dir, "freeze", "--reason", "two", "--repo", "o/r")
        again = json.loads((state_dir / "freeze.json").read_text())
        assert again["reason"] == "two" and again["since"] == flag["since"]
        assert {"repo": "o/old", "number": 1} in again["disarmed"]
        assert again["disarmed"].count({"repo": "o/r", "number": 5}) == 1
        capsys.readouterr()
        run(state_dir, "unfreeze")
        assert "o/r#5 o/old#1" in capsys.readouterr().out


@pytest.mark.usefixtures("fake_gh")
class TestFreezeIssue:
    """The freeze reaches GitHub as an open `merge-freeze` issue, which a repo's self-merge judge
    reads (`fixtures/brake-self-merge/judge.json`)."""

    def test_label_is_the_judges(self):
        judge = json.loads(
            (
                Path(board.__file__).parent / "fixtures" / "brake-self-merge" / "judge.json"
            ).read_text()
        )
        assert judge["freeze_label"] == board_freeze.FREEZE_LABEL

    def test_an_open_freeze_issue_is_not_opened_twice(self, watched, fake_gh):
        """Red arm: a repo with someone's freeze issue gets none of ours, and unfreeze leaves it."""
        assert run(watched, "freeze", "--reason", "r", "--repo", "o/frozen") == 0
        flag = json.loads((watched / "freeze.json").read_text())
        assert flag["issues"] == []
        assert not [c for c in fake_gh() if c[:2] == ["issue", "create"]]
        assert run(watched, "unfreeze") == 0
        assert not [c for c in fake_gh() if c[:2] == ["issue", "close"]]

    def test_a_failed_issue_write_is_recorded_and_the_flag_stands(self, watched, capsys):
        """Red arm: an issue that did not open exits 1 naming the repo; the flag stands."""
        assert run(watched, "freeze", "--reason", "r", "--repo", "o/nocreate") == 1
        assert "GitHub is not frozen in o/nocreate" in capsys.readouterr().err
        flag = json.loads((watched / "freeze.json").read_text())
        assert {"repo": "o/nocreate", "why": "opening the `merge-freeze` issue failed"} in flag[
            "not_disarmed"
        ]
        assert run(watched, "freeze", "--reason", "r", "--repo", "o/noissue") == 1
        flag = json.loads((watched / "freeze.json").read_text())
        assert {"repo": "o/noissue", "why": "listing the `merge-freeze` issues failed"} in flag[
            "not_disarmed"
        ]

    def test_a_failed_close_says_github_stays_frozen(self, watched, monkeypatch, capsys):
        run(watched, "freeze", "--reason", "r", "--repo", "o/r")
        monkeypatch.setenv("FAKE_GH_NO_CLOSE", "1")
        assert run(watched, "unfreeze") == 1
        assert "GitHub stays frozen: o/r#41" in capsys.readouterr().err
        assert not (watched / "freeze.json").exists()

    def test_a_star_freeze_opens_the_issue_in_every_crew_repo(self, watched, monkeypatch):
        monkeypatch.setattr(board, "_crew_repos", lambda *_a, **_k: ["o/a", "o/b"])
        assert run(watched, "freeze", "--reason", "r") == 0
        flag = json.loads((watched / "freeze.json").read_text())
        assert flag["repos"] == ["*"]
        assert flag["issues"] == [{"repo": "o/a", "number": 41}, {"repo": "o/b", "number": 41}]


class TestFreezePerCrew:
    """A crew's freeze sits beside its own board, named after the board's stem."""

    def test_flag_names_follow_the_board_stem(self, tmp_path):
        assert board_freeze.flag_path(tmp_path / "board.json") == tmp_path / "freeze.json"
        assert (
            board_freeze.flag_path(tmp_path / "acme-board.json")
            == tmp_path / "acme-board-freeze.json"
        )

    @pytest.mark.usefixtures("fake_gh")
    def test_a_freeze_in_crew_a_does_not_brake_crew_b(self, tmp_path, monkeypatch):
        """Red arm: crew A (`acme-board.json`) and crew B (`board.json`) keep their boards in one
        folder; A's freeze stands for A's merge hook and never for B's."""
        shared = tmp_path / "we-state"
        shared.mkdir()
        a, b = tmp_path / "a", tmp_path / "b"
        boards = ((a, shared / "acme-board.json"), (b, shared / "board.json"))
        for root, crew_board in ((r, {"file": str(f)}) for r, f in boards):
            (root / ".git").mkdir(parents=True)
            (root / ".weside").mkdir()
            doc = {"version": 2, "roles": {}, "members": {}}
            if crew_board:
                doc["board"] = crew_board
            (root / ".weside" / "crew.json").write_text(json.dumps(doc))
        default = str(shared / "board.json")
        monkeypatch.setattr(board, "DEFAULT_BOARD", default)
        monkeypatch.setattr(board, "_current_repo", lambda: None)
        monkeypatch.setattr(board, "_crew_repos", lambda *_a, **_k: [])
        monkeypatch.chdir(a)
        assert board.main(["freeze", "--reason", "incident in a", "--repo", "o/r"]) == 0

        def standing(root):
            files = board_freeze.watched_board_files(root, default)
            return [
                board_freeze.read_flag(board_freeze.flag_path(f))
                for f in files
                if board_freeze.read_flag(board_freeze.flag_path(f)) is not None
            ]

        assert [f["reason"] for f in standing(a)] == ["incident in a"]
        assert standing(b) == []


# ---------------------------------------------------------------------------------------------
# set, ask, decision, bundle: the session's own line, the owner's questions and the area decisions

import fcntl  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

import cold_reader  # noqa: E402

FAKE_BIN = HERE / "fixtures" / "board"
CREW = HERE / "fixtures" / "crew-v2-generic.json"
NOW = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
LIVE = {
    "updated": "2026-11-03T09:00:00Z",
    "updated_by": "coord",
    "owner_queue": [{"id": "Q7", "session": "asker", "since": "2026-11-01"}],
    "news": [{"id": "D3", "kind": "decision", "title": "hand-written"}],
    "sessions": [
        {"name": "lead-12", "state": "build", "now": "phase 2"},
        {"name": "other", "state": "active", "since": "2026-11-02T08:15Z", "note": None},
    ],
}


@pytest.fixture
def crewless(tmp_path, monkeypatch):
    """A cwd with no crew file above it, the fake `claude` first on PATH, an unpinned master."""
    work = tmp_path / "work"
    (work / ".git").mkdir(parents=True)
    monkeypatch.chdir(work)
    monkeypatch.setenv("PATH", f"{FAKE_BIN}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("WE_ROLE", "master")
    monkeypatch.delenv("WESIDE_COMPANION", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sid-12")
    agents = tmp_path / "agents.json"
    agents.write_text(json.dumps([{"sessionId": "sid-12", "name": "lead-12"}]), encoding="utf-8")
    monkeypatch.setenv("FAKE_AGENTS", str(agents))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "reader-calls.jsonl"))
    monkeypatch.setenv("FAKE_ANSWER", str(tmp_path / "answer.txt"))
    (tmp_path / "board.json").write_text(json.dumps(LIVE, indent=1), encoding="utf-8")
    return tmp_path


@pytest.fixture
def crewed(crewless):
    """The same with the generic crew (coordinator `otto`, product `ada`, sla tz Europe/Berlin)."""
    (crewless / "work" / ".weside").mkdir()
    shutil.copy(CREW, crewless / "work" / ".weside" / "crew.json")
    return crewless


def pin(monkeypatch, slug):
    monkeypatch.setenv("WESIDE_COMPANION", slug)


def go(state_dir, *argv, now=NOW):
    return board.main(["--board", str(state_dir / "board.json"), *argv], now=now)


def board_of(state_dir):
    return json.loads((state_dir / "board.json").read_text(encoding="utf-8"))


def line_of(state_dir, name):
    return next(s for s in board_of(state_dir)["sessions"] if s["name"] == name)


def jsonl(path):
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


class TestDaytimeDue:
    @pytest.mark.parametrize(
        "since, due",
        [
            ("2026-11-03T10:00", "2026-11-03T14:00"),  # inside the window
            ("2026-11-03T18:00", "2026-11-04T10:00"),  # across the evening edge
            ("2026-11-03T05:30", "2026-11-03T12:00"),  # before the window opens
        ],
    )
    def test_utc(self, since, due):
        start = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
        got = board.daytime_due(start, 4, "08-20", "UTC")
        assert got == datetime.fromisoformat(due).replace(tzinfo=timezone.utc)

    def test_berlin_across_the_dst_change(self):
        start = datetime(2026, 10, 24, 16, 0, tzinfo=timezone.utc)  # Sat 18:00 CEST
        due = board.daytime_due(start, 4, "08-20", "Europe/Berlin")
        assert due.strftime(board.MINUTE_FMT) == "2026-10-25T09:00Z"  # Sun 10:00 CET

    def test_a_bad_window_is_named(self):
        with pytest.raises(board.BoardError, match=r'sla\.daytime "20-08"'):
            board.daytime_due(NOW, 4, "20-08", "UTC")


class TestStateDir:
    def test_write_board_replaces_atomically_and_leaves_no_temp_file(self, crewless):
        state = board.StateDir(crewless / "board.json")
        state.write_board(lambda b: b.setdefault("news", []).append({"id": "N9"}))
        assert board_of(crewless)["news"][-1] == {"id": "N9"}
        assert sorted(p.name for p in crewless.iterdir() if p.name.startswith("board.json")) == [
            "board.json",
            "board.json.lock",
        ]

    def test_unchanged_leaves_the_file_byte_equal(self, crewless):
        before = (crewless / "board.json").read_bytes()
        board.StateDir(crewless / "board.json").write_board(lambda _b: board.UNCHANGED)
        assert (crewless / "board.json").read_bytes() == before

    def test_a_held_lock_is_named_after_the_wait(self, crewless, monkeypatch):
        monkeypatch.setattr(board, "LOCK_WAIT_S", 0.2)
        state = board.StateDir(crewless / "board.json")
        with open(state.lock_path, "w") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            with pytest.raises(
                board.BoardError, match=r"board\.json\.lock not taken within 0\.2 s"
            ):
                state.write_board(lambda _b: None)


class TestSet:
    def test_writes_only_its_own_line_found_by_name(self, crewless):
        before = board_of(crewless)
        assert go(crewless, "set", "now=phase 3", "state=ci") == 0
        after = board_of(crewless)
        assert line_of(crewless, "lead-12") == {
            "name": "lead-12",
            "state": "ci",
            "now": "phase 3",
            "updated_at": "2026-11-03T10:00Z",
        }
        assert after["sessions"][1] == before["sessions"][1]
        assert {k: after[k] for k in after if k != "sessions"} == {
            k: before[k] for k in before if k != "sessions"
        }  # updated and updated_by untouched: not the coordinator

    def test_appends_a_missing_line_with_name_and_session_id(self, crewless):
        (crewless / "agents.json").write_text(
            json.dumps([{"sessionId": "sid-12", "name": "fresh-1"}]), encoding="utf-8"
        )
        assert go(crewless, "set", "state=active") == 0
        assert line_of(crewless, "fresh-1") == {
            "name": "fresh-1",
            "session_id": "sid-12",
            "state": "active",
            "updated_at": "2026-11-03T10:00Z",
        }

    def test_the_wait_triple_its_keep_reset_and_clear(self, crewless):
        assert go(crewless, "set", "waiting_on=architecture") == 0
        line = line_of(crewless, "lead-12")
        assert (line["waiting_on"], line["since"], line["sla_due"]) == (
            "architecture",
            "2026-11-03T10:00Z",
            "2026-11-03T14:00Z",
        )
        later = datetime(2026, 11, 3, 11, 30, tzinfo=timezone.utc)
        go(crewless, "set", "waiting_on=architecture", now=later)
        assert line_of(crewless, "lead-12")["since"] == "2026-11-03T10:00Z"
        go(crewless, "set", "waiting_on=product", now=later)
        line = line_of(crewless, "lead-12")
        assert (line["since"], line["sla_due"]) == ("2026-11-03T11:30Z", "2026-11-03T15:30Z")
        go(crewless, "set", "waiting_on=")
        assert not {"waiting_on", "since", "sla_due"} & set(line_of(crewless, "lead-12"))

    def test_a_hand_written_since_survives_every_set(self, crewless, monkeypatch):
        monkeypatch.setenv("WESIDE_COMPANION", "")
        (crewless / "agents.json").write_text(
            json.dumps([{"sessionId": "sid-12", "name": "other"}]), encoding="utf-8"
        )
        for assignment in ("state=parked", "now=resting", "waiting_on="):
            assert go(crewless, "set", assignment) == 0
            assert line_of(crewless, "other")["since"] == "2026-11-02T08:15Z"

    def test_the_crew_sla_counts_berlin_daytime(self, crewed):
        go(
            crewed,
            "set",
            "waiting_on=human",
            now=datetime(2026, 10, 24, 16, 0, tzinfo=timezone.utc),
        )
        assert line_of(crewed, "lead-12")["sla_due"] == "2026-10-25T09:00Z"

    @pytest.mark.parametrize(
        "assignment, message",
        [
            ("waiting_on=legal", "waiting_on 'legal' is no role key"),
            ("color=x", "field 'color' is not settable"),
            ("keys=nope", "keys nope do not match the crew's naming.key"),
            ("state=running", "state 'running' is not one of"),
            ("waiting", "'waiting' is no <field>=<value>"),
        ],
    )
    def test_refusals_name_the_input_and_write_nothing(
        self, crewless, capsys, assignment, message
    ):
        before = (crewless / "board.json").read_bytes()
        assert go(crewless, "set", assignment) == 1
        assert message in capsys.readouterr().err
        assert (crewless / "board.json").read_bytes() == before

    def test_session_states_mirror_the_board_doc(self):
        doc = (HERE.parent / "docs" / "board.md").read_text(encoding="utf-8")
        row = next(x for x in doc.splitlines() if x.startswith("| `sessions[].state` |"))
        assert set(re.findall(r"`([a-z-]+)`", row.split("|")[2])) == set(board.SESSION_STATES)

    def test_for_is_the_coordinators(self, crewed, capsys, monkeypatch):
        pin(monkeypatch, "ada")
        assert go(crewed, "set", "--for", "other", "now=x") == 1
        assert (
            "board.py set: --for other: only the coordinator writes another session's line"
            in capsys.readouterr().err
        )
        pin(monkeypatch, "otto")
        assert go(crewed, "set", "--for", "other", "now=x") == 0
        assert line_of(crewed, "other")["now"] == "x"

    def test_a_session_without_a_name_is_sent_to_rename(self, crewless, capsys):
        (crewless / "agents.json").write_text(json.dumps([{"sessionId": "sid-12"}]), "utf-8")
        assert go(crewless, "set", "now=x") == 1
        assert (
            "board.py set: this session has no name; run /rename first" in capsys.readouterr().err
        )

    def test_a_failing_claude_agents_is_named(self, crewless, capsys, monkeypatch):
        monkeypatch.setenv("FAKE_AGENTS_EXIT", "3")
        assert go(crewless, "set", "now=x") == 1
        assert "board.py set: claude agents --json exited 3" in capsys.readouterr().err

    def test_two_concurrent_writers_both_land(self, crewed):
        writer = (
            "import sys; sys.path.insert(0, sys.argv[1]); import board\n"
            "for i in range(25): assert board.main(['--board', sys.argv[2], 'set', '--for', sys.argv[3], f'now={i}']) == 0"
        )
        env = {**os.environ, "WESIDE_COMPANION": "otto", "WE_ROLE": "master"}
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", writer, str(HERE), str(crewed / "board.json"), name],
                env=env,
                cwd=str(crewed / "work"),
            )
            for name in ("lead-12", "other")
        ]
        assert [p.wait(timeout=60) for p in procs] == [0, 0]
        assert line_of(crewed, "lead-12")["now"] == "24"
        assert line_of(crewed, "other")["now"] == "24"


ASK = {
    "--session": "lead-12",
    "--key": "PROJ-12",
    "--key-title": "Checkout flow",
    "--ask": "Should the new checkout page go live for all users tonight?",
    "--recommendation": "Yes, tonight; a rollback takes minutes.",
    "--cause": "prod",
}
CLEAR = {
    "decides": "whether the checkout page goes live tonight",
    "on_yes": "it ships",
    "form": [],
}


def ask_argv(**override):
    fields = {**ASK, **override}
    return ["ask", *[x for k, v in fields.items() if v is not None for x in (k, v)]]


def answer_with(state_dir, answer):
    text = answer if isinstance(answer, str) else "Reading it cold.\n" + json.dumps(answer)
    (state_dir / "answer.txt").write_text(text, encoding="utf-8")


class TestAsk:
    @pytest.mark.parametrize("flag", list(ASK))
    @pytest.mark.parametrize("value", [None, "  "])
    def test_a_missing_or_blank_field_is_refused_before_the_reader(
        self, crewless, capsys, flag, value
    ):
        before = (crewless / "board.json").read_bytes()
        assert go(crewless, *ask_argv(**{flag: value})) == 1
        assert capsys.readouterr().err.strip() == f"board.py ask: missing {flag}"
        assert not (crewless / "reader-calls.jsonl").exists()
        assert not (crewless / "board-questions.jsonl").exists()
        assert (crewless / "board.json").read_bytes() == before

    @pytest.mark.parametrize(
        "flag, value, message",
        [
            ("--key", "proj-12", "--key 'proj-12' does not match naming.key"),
            ("--key", "PROJ-12 PROJ-13", "does not match naming.key"),
            ("--cause", "gut-feeling", "--cause 'gut-feeling' is not one of merge-go"),
        ],
    )
    def test_a_bad_key_or_cause_is_refused_the_same_way(
        self, crewless, capsys, flag, value, message
    ):
        assert go(crewless, *ask_argv(**{flag: value})) == 1
        assert message in capsys.readouterr().err
        assert not (crewless / "reader-calls.jsonl").exists()

    def test_a_clear_question_is_posted_with_the_next_id(self, crewless, capsys):
        (crewless / "board-answers.jsonl").write_text('{"id": "Q271", "answer": "accept"}\n')
        answer_with(crewless, CLEAR)
        assert go(crewless, *ask_argv()) == 0
        assert capsys.readouterr().out.strip() == "posted Q272"
        item = board_of(crewless)["owner_queue"][-1]
        assert item == {
            "id": "Q272",
            "session": "lead-12",
            "key": "PROJ-12",
            "key_title": "Checkout flow",
            "ask": ASK["--ask"],
            "recommendation": ASK["--recommendation"],
            "cause": "prod",
            "since": "2026-11-03",
            "ts": "2026-11-03T10:00:00Z",
        }
        [line] = jsonl(crewless / "board-questions.jsonl")
        assert line["id"] == "Q272" and line["outcome"] == "posted"
        assert line["ask"] == ASK["--ask"] and line["cause"] == "prod"
        assert line["reader"] == CLEAR

    def test_a_plan_slug_stands_for_a_key_before_the_ticket_exists(self, crewless, capsys):
        answer_with(crewless, CLEAR)
        assert go(crewless, *ask_argv(**{"--key": "onboarding-v2"})) == 0
        assert capsys.readouterr().out.strip() == f"posted {LIVE_NEXT_Q}"
        assert board_of(crewless)["owner_queue"][-1]["key"] == "onboarding-v2"


# The id `ask` posts on a fresh LIVE board with no logs: one past LIVE's own highest Q.
LIVE_NEXT_Q = board.StateDir("/nonexistent/board.json").next_id("Q", LIVE)


class TestSecondCrew:
    """A second crew's board keeps its own logs and ids; board.json keeps its names."""

    def test_a_named_board_logs_beside_itself_under_its_stem(self, crewless, capsys):
        (crewless / "board-answers.jsonl").write_text('{"id": "Q407", "answer": "accept"}\n')
        (crewless / "board-questions.jsonl").write_text('{"id": "Q408", "outcome": "posted"}\n')
        other = crewless / "acme-board.json"
        other.write_text(json.dumps(LIVE), encoding="utf-8")
        answer_with(crewless, CLEAR)
        assert board.main(["--board", str(other), *ask_argv()], now=NOW) == 0
        assert capsys.readouterr().out.strip() == f"posted {LIVE_NEXT_Q}"
        [line] = jsonl(crewless / "acme-board-questions.jsonl")
        assert line["id"] == LIVE_NEXT_Q
        assert len(jsonl(crewless / "board-questions.jsonl")) == 1

    def test_the_default_board_keeps_its_log_names(self, tmp_path):
        state = board.StateDir(tmp_path / "board.json")
        names = [state.answers_path, state.questions_path, state.decisions_path]
        names += [state.escalations_path, state.transitions_path, state.waits_path]
        assert [p.name for p in names] == [
            f"board-{k}.jsonl"
            for k in ("answers", "questions", "decisions", "escalations", "transitions", "waits")
        ]

    def test_without_board_a_verb_writes_the_crews_board_file(self, crewed, capsys, monkeypatch):
        # Without the fix the verb writes DEFAULT_BOARD: keep that in tmp, never the real board.
        monkeypatch.setattr(board, "DEFAULT_BOARD", str(crewed / "board.json"))
        crew_file = crewed / "work" / ".weside" / "crew.json"
        data = json.loads(crew_file.read_text())
        data["board"] = {**(data.get("board") or {}), "file": "../../acme-board.json"}
        crew_file.write_text(json.dumps(data))
        (crewed / "acme-board.json").write_text(json.dumps(LIVE), encoding="utf-8")
        before = (crewed / "board.json").read_bytes()
        answer_with(crewed, CLEAR)
        assert board.main(ask_argv(), now=NOW) == 0
        assert capsys.readouterr().out.strip() == f"posted {LIVE_NEXT_Q}"
        assert (
            json.loads((crewed / "acme-board.json").read_text())["owner_queue"][-1]["id"]
            == LIVE_NEXT_Q
        )
        assert jsonl(crewed / "acme-board-questions.jsonl")[0]["id"] == LIVE_NEXT_Q
        assert (crewed / "board.json").read_bytes() == before

    def test_without_board_or_crew_file_the_default_board_is_refused(
        self, crewless, monkeypatch, capsys
    ):
        # two crews, AC11: a session without a crew no longer writes the default board.
        monkeypatch.setattr(board, "DEFAULT_BOARD", str(crewless / "board.json"))
        before = (crewless / "board.json").read_bytes()
        answer_with(crewless, CLEAR)
        assert board.main(ask_argv(), now=NOW) == 3
        assert "no crew" in capsys.readouterr().err
        assert (crewless / "board.json").read_bytes() == before
        assert not (crewless / "board-questions.jsonl").exists()

    def test_path_names_the_crews_board_and_crew_only_fails_without_one(
        self, crewed, capsys, monkeypatch
    ):
        monkeypatch.setattr(board, "DEFAULT_BOARD", str(crewed / "board.json"))
        assert board.main(["path", "--crew-only"]) == 1
        assert capsys.readouterr().out == ""
        crew_file = crewed / "work" / ".weside" / "crew.json"
        data = json.loads(crew_file.read_text())
        data["board"] = {**(data.get("board") or {}), "file": "../../acme-board.json"}
        crew_file.write_text(json.dumps(data))
        assert board.main(["path", "--crew-only"]) == 0
        assert capsys.readouterr().out.strip() == str((crewed / "acme-board.json").resolve())


def _crew_with(crewed, **top):
    crew_file = crewed / "work" / ".weside" / "crew.json"
    data = json.loads(crew_file.read_text())
    data.update(top)
    crew_file.write_text(json.dumps(data))
    return crew_file


class TestCrewGuard:
    """two crews, AC11: a writing verb refuses a board of another crew, and a crewless default write.

    Finding of 08.11.: a second crew's coordinator ran `board.py prune` without `--board` and
    removed the first crew's returned news. Red arm on origin/main: every refusal below wrote."""

    @pytest.fixture
    def own(self, crewed, monkeypatch):
        """The crewed session's own board is `crewed/board.json` (DEFAULT_BOARD points there)."""
        monkeypatch.setattr(board, "DEFAULT_BOARD", str(crewed / "board.json"))
        (crewed / "board.json").write_text(json.dumps(LIVE), encoding="utf-8")
        return crewed

    def test_the_own_crews_first_write_stamps_its_board(self, own):
        assert board.main(["set", "state=build"], now=NOW) == 0
        stamp = (own / "crew.id").read_text().strip()
        assert stamp == board.crew_mod.crew_id(own / "work" / ".weside" / "crew.json")
        assert board.main(["set", "state=ci"], now=NOW) == 0

    def test_a_board_stamped_for_another_crew_refuses_a_write(self, own, capsys):
        (own / "crew.id").write_text("acme/second-crew\n")
        before = (own / "board.json").read_bytes()
        assert board.main(["prune"], now=NOW) == 3
        err = capsys.readouterr().err
        assert "refused" in err and "crew acme/second-crew" in err and "--board" in err
        assert (own / "board.json").read_bytes() == before

    def test_an_explicit_board_of_another_crew_is_refused(self, own, capsys):
        other = own / "acme-board.json"
        other.write_text(json.dumps(LIVE), encoding="utf-8")
        (own / "acme-board-crew.id").write_text("acme/second-crew\n")
        before = other.read_bytes()
        assert board.main(["--board", str(other), "set", "state=build"], now=NOW) == 3
        err = capsys.readouterr().err
        assert "acme/second-crew" in err and str(own / "board.json") in err
        assert other.read_bytes() == before

    def test_a_pin_outside_the_crew_counts_as_no_crew(self, own, monkeypatch, capsys):
        pin(monkeypatch, "smu")
        before = (own / "board.json").read_bytes()
        assert board.main(["prune"], now=NOW) == 3
        err = capsys.readouterr().err
        assert "pinned companion smu is no member" in err and "--board" in err
        assert (own / "board.json").read_bytes() == before

    @pytest.mark.usefixtures("own")
    def test_a_member_pin_writes(self, monkeypatch):
        pin(monkeypatch, "otto")
        assert board.main(["set", "state=build"], now=NOW) == 0

    @pytest.mark.parametrize(
        "argv",
        [["path"], ["escalation", "list", "--waiting-on", "coordinator"], ["escalation", "count"]],
    )
    def test_reading_verbs_pass_for_a_foreign_session(self, own, monkeypatch, argv):
        (own / "crew.id").write_text("acme/second-crew\n")
        pin(monkeypatch, "smu")
        assert board.main(argv, now=NOW) == 0

    def test_freeze_passes_without_a_crew(self, crewless, monkeypatch):
        monkeypatch.setattr(board, "DEFAULT_BOARD", str(crewless / "board.json"))
        monkeypatch.setattr(board, "_current_repo", lambda: None)
        monkeypatch.setattr(board, "_crew_repos", lambda *_a, **_k: [])
        args = board.parser().parse_args(["freeze", "--reason", "stop"])
        assert board.crew_guard(args, env={}, cwd=crewless / "work") == (None, None)

    def test_unfreeze_passes_the_crewless_rule_but_not_another_crews_stamp(self, crewless):
        args = board.parser().parse_args(["unfreeze"])
        assert board.crew_guard(args, env={}, cwd=crewless / "work")[0] is None
        (crewless / "crew.id").write_text("acme/second-crew\n")
        args = board.parser().parse_args(["--board", str(crewless / "board.json"), "unfreeze"])
        refusal, _ = board.crew_guard(args, env={}, cwd=crewless / "work")
        assert refusal and "acme/second-crew" in refusal

    def test_a_crewless_session_may_name_an_unstamped_board(self, crewless):
        assert go(crewless, "set", "state=build") == 0
        assert not (crewless / "crew.id").exists()

    def test_a_relative_state_dir_moves_the_board(self, crewed, monkeypatch, capsys):
        monkeypatch.delenv("WE_STATE_DIR", raising=False)
        _crew_with(crewed, state_dir="../../second")
        assert board.main(["path"]) == 0
        assert capsys.readouterr().out.strip() == str((crewed / "second" / "board.json").resolve())


class TestAskReader:
    def test_the_reader_runs_cold_with_only_the_question(self, crewless, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(crewless / "pinned-profile"))
        pin(monkeypatch, "otto")
        answer_with(crewless, CLEAR)
        assert go(crewless, *ask_argv()) == 0
        [call] = jsonl(crewless / "reader-calls.jsonl")
        argv = call["argv"]
        assert argv[0] == "-p" and "--no-session-persistence" in argv
        assert argv[argv.index("--tools") + 1] == ""
        assert argv[argv.index("--setting-sources") + 1] == ""
        assert argv[argv.index("--model") + 1] == "haiku"
        assert "--strict-mcp-config" in argv and "--disable-slash-commands" in argv
        assert "--system-prompt-file" in argv and "--settings" in argv
        assert call["env"] == {"CLAUDE_CONFIG_DIR": None, "WESIDE_COMPANION": None}
        assert call["cwd_files"] == []
        assert json.loads(call["stdin"]) == {
            "ask": ASK["--ask"],
            "recommendation": ASK["--recommendation"],
            "key_title": "Checkout flow",
            "question_label": "QUESTION",
            "recommendation_label": "Recommendation",
        }

    def test_the_crew_labels_reach_the_reader(self, crewed):
        answer_with(crewed, CLEAR)
        go(crewed, *ask_argv())
        stdin = json.loads(jsonl(crewed / "reader-calls.jsonl")[0]["stdin"])
        assert (stdin["question_label"], stdin["recommendation_label"]) == ("ASK", "Advice")

    def test_a_bare_key_question_is_returned_visibly(self, crewless, capsys):
        answer_with(crewless, {"decides": "", "on_yes": "", "form": []})
        before = board_of(crewless)
        assert go(crewless, *ask_argv(**{"--ask": "PROJ-12 merge?"})) == 1
        reason = "reader cannot tell what is decided; reader cannot tell what happens on yes"
        assert capsys.readouterr().err.strip() == f"board.py ask: returned to lead-12: {reason}"
        after = board_of(crewless)
        assert after["owner_queue"] == before["owner_queue"]
        assert line_of(crewless, "lead-12")["note"] == f"returned to lead-12: {reason}"
        assert after["news"][-1] == {
            "id": "R1",
            "kind": "returned",
            "title": f"PROJ-12 returned to lead-12: {reason}",
            "ts": "2026-11-03T10:00:00Z",
        }
        [line] = jsonl(crewless / "board-questions.jsonl")
        assert (line["outcome"], line["reason"], line["ask"]) == (
            "returned",
            reason,
            "PROJ-12 merge?",
        )
        assert "id" not in line

    @pytest.mark.parametrize(
        "finding",
        ["two decisions in one", "more than 3 options", "no recommendation", "German text"],
    )
    def test_a_form_finding_returns_it(self, crewless, capsys, finding):
        answer_with(crewless, {**CLEAR, "form": [finding]})
        assert go(crewless, *ask_argv()) == 1
        assert f"returned to lead-12: {finding}" in capsys.readouterr().err
        assert "Q8" not in {q["id"] for q in board_of(crewless)["owner_queue"]}

    @staticmethod
    def note_on_lead(state_dir, note):
        board_now = board_of(state_dir)
        line = next(s for s in board_now["sessions"] if s["name"] == "lead-12")
        line["note"] = note
        (state_dir / "board.json").write_text(json.dumps(board_now), encoding="utf-8")

    def test_a_posted_question_clears_the_earlier_return(self, crewless):
        self.note_on_lead(crewless, "returned to lead-12: no recommendation")
        answer_with(crewless, CLEAR)
        assert go(crewless, *ask_argv()) == 0
        assert "note" not in line_of(crewless, "lead-12"), "a posted ask keeps the stale return"

    def test_a_posted_question_keeps_an_unrelated_note(self, crewless):
        self.note_on_lead(crewless, "CI red on main")
        answer_with(crewless, CLEAR)
        assert go(crewless, *ask_argv()) == 0
        assert line_of(crewless, "lead-12")["note"] == "CI red on main", (
            "posted ask dropped a note"
        )

    def test_a_return_leaves_an_unrelated_note_and_still_writes_news(self, crewless):
        self.note_on_lead(crewless, "CI red on main")
        answer_with(crewless, {**CLEAR, "form": ["no recommendation"]})
        assert go(crewless, *ask_argv()) == 1
        after = board_of(crewless)
        assert line_of(crewless, "lead-12")["note"] == "CI red on main", "return overwrote a note"
        assert after["news"][-1]["id"] == "R1"
        assert after["news"][-1]["title"] == "PROJ-12 returned to lead-12: no recommendation"

    def test_a_return_replaces_an_earlier_return(self, crewless):
        self.note_on_lead(crewless, "returned to lead-12: German text")
        answer_with(crewless, {**CLEAR, "form": ["no recommendation"]})
        assert go(crewless, *ask_argv()) == 1
        assert line_of(crewless, "lead-12")["note"] == "returned to lead-12: no recommendation"

    @pytest.mark.parametrize(
        "setup, cause",
        [
            ({"answer": "I cannot judge this."}, "no parseable answer"),
            ({"FAKE_EXIT": "1"}, "claude -p exited 1: model unavailable"),
            ({"FAKE_SLEEP": "3", "timeout": 1}, "timeout after 1 s"),
            ({"PATH": "empty"}, "no claude on PATH"),
        ],
    )
    def test_a_reader_that_cannot_run_posts_nothing(
        self, crewless, capsys, monkeypatch, setup, cause
    ):
        answer_with(crewless, setup.get("answer", CLEAR))
        for key in ("FAKE_EXIT", "FAKE_SLEEP"):
            if key in setup:
                monkeypatch.setenv(key, setup[key])
        if "timeout" in setup:
            monkeypatch.setattr(cold_reader, "TIMEOUT_S", setup["timeout"])
        if "PATH" in setup:
            (crewless / "empty").mkdir()
            monkeypatch.setenv("PATH", str(crewless / "empty"))
        before = (crewless / "board.json").read_bytes()
        assert go(crewless, *ask_argv()) == 1
        assert capsys.readouterr().err.strip() == f"board.py ask: reader-error: {cause}"
        assert (crewless / "board.json").read_bytes() == before
        [line] = jsonl(crewless / "board-questions.jsonl")
        assert (line["outcome"], line["reason"]) == ("reader-error", cause)

    def test_the_log_survives_removal_and_only_grows(self, crewless):
        answer_with(crewless, CLEAR)
        go(crewless, *ask_argv())
        log = crewless / "board-questions.jsonl"
        first = log.read_bytes()
        state = board.StateDir(crewless / "board.json")
        state.write_board(lambda b: b.update(owner_queue=[]))  # the coordinator strikes it
        answer_with(crewless, {**CLEAR, "on_yes": ""})
        go(crewless, *ask_argv())
        assert log.read_bytes().startswith(first) and len(log.read_bytes()) > len(first)
        posted = jsonl(log)[0]
        assert (posted["id"], posted["ask"], posted["recommendation"], posted["cause"]) == (
            "Q8",
            ASK["--ask"],
            ASK["--recommendation"],
            "prod",
        )

    def test_the_next_id_counts_the_log_too(self, crewless, capsys):
        answer_with(crewless, CLEAR)
        go(crewless, *ask_argv())
        board.StateDir(crewless / "board.json").write_board(lambda b: b.update(owner_queue=[]))
        go(crewless, *ask_argv())
        assert capsys.readouterr().out.split() == ["posted", "Q8", "posted", "Q9"]


PR_URL = "https://github.com/o/r/pull/5"


@pytest.fixture
def merge_gh(crewless, monkeypatch):
    """The fake `gh` on PATH, answering `pr view` from gh.json (FAKE_BIN's `gh`)."""
    monkeypatch.setenv("FAKE_GH", str(crewless / "gh.json"))
    monkeypatch.setenv("FAKE_GH_LOG", str(crewless / "gh-calls.jsonl"))

    def answers(state):
        pr = {"state": state, "url": PR_URL, "headRefName": "feat/PROJ-12-x", "title": "t"}
        (crewless / "gh.json").write_text(
            json.dumps({PR_URL: {"pr": pr}, "5 -R o/r": {"pr": pr}}), encoding="utf-8"
        )

    answers("OPEN")
    return answers


class TestMergeQuestion:
    def merge_argv(self, *extra):
        return [*ask_argv(**{"--cause": "merge-go"}), *extra]

    def test_a_merge_question_without_a_pr_is_refused_before_the_reader(self, crewless, capsys):
        assert go(crewless, *self.merge_argv()) == 1
        assert "a merge-go question needs --pr" in capsys.readouterr().err
        assert not (crewless / "reader-calls.jsonl").exists()

    @pytest.mark.parametrize("state", ["MERGED", "CLOSED"])
    def test_a_merge_question_on_a_pr_that_is_not_open_is_refused(
        self, crewless, merge_gh, capsys, state
    ):
        merge_gh(state)
        before = (crewless / "board.json").read_bytes()
        assert go(crewless, *self.merge_argv("--pr", "o/r#5")) == 1
        assert f"PR o/r#5 is {state}" in capsys.readouterr().err
        assert not (crewless / "reader-calls.jsonl").exists()
        assert (crewless / "board.json").read_bytes() == before

    @pytest.mark.usefixtures("merge_gh")
    def test_an_open_one_way_pr_is_posted_with_its_url_and_class(self, crewless):
        answer_with(crewless, CLEAR)
        assert go(crewless, *self.merge_argv("--pr", "o/r#5", "--one-way", "money")) == 0
        item = board_of(crewless)["owner_queue"][-1]
        assert (item["cause"], item["pr_url"], item["one_way"]) == ("merge-go", PR_URL, "money")

    def test_one_way_without_merge_go_is_refused(self, crewless, capsys):
        assert go(crewless, *ask_argv(), "--one-way", "money") == 1
        assert "--one-way belongs to a merge-go question" in capsys.readouterr().err

    def test_close_merged_drops_the_question_once_its_pr_merged(self, crewless, merge_gh, capsys):
        answer_with(crewless, CLEAR)
        go(crewless, *self.merge_argv("--pr", PR_URL, "--one-way", "money"))
        go(crewless, "close-merged")
        assert capsys.readouterr().out.strip().endswith("closed: none")
        assert [q["id"] for q in board_of(crewless)["owner_queue"]] == ["Q7", "Q8"]
        merge_gh("MERGED")
        assert go(crewless, "close-merged") == 0
        assert capsys.readouterr().out.strip() == "closed: Q8"
        assert [q["id"] for q in board_of(crewless)["owner_queue"]] == ["Q7"]
        closed = jsonl(crewless / "board-questions.jsonl")[-1]
        assert (closed["id"], closed["outcome"], closed["reason"]) == ("Q8", "closed", "PR MERGED")

    def test_close_merged_leaves_other_causes_and_questions_without_a_pr(self, crewless, merge_gh):
        board.StateDir(crewless / "board.json").write_board(
            lambda b: b["owner_queue"].extend(
                [
                    {"id": "Q20", "cause": "prod", "pr_url": PR_URL},
                    {"id": "Q21", "cause": "merge-go"},
                ]
            )
        )
        merge_gh("MERGED")
        go(crewless, "close-merged")
        assert [q["id"] for q in board_of(crewless)["owner_queue"]] == ["Q7", "Q20", "Q21"]


def decide(state_dir, area="product", kind="fence", key="PROJ-40", text="no paywall in v1"):
    return go(state_dir, "decision", area, kind, "--key", key, "--text", text)


class TestDecision:
    def test_the_area_holder_writes_the_item_and_the_line(self, crewed, monkeypatch):
        pin(monkeypatch, "ada")
        assert decide(crewed) == 0
        item = board_of(crewed)["news"][-1]
        assert item == {
            "id": "D4",
            "kind": "decision",
            "title": "product fence PROJ-40: no paywall in v1",
            "ts": "2026-11-03T10:00:00Z",
            "by": "product",
        }
        [line] = jsonl(crewed / "board-decisions.jsonl")
        assert {k: line[k] for k in item} == item
        assert decide(crewed, kind="cut", text="drop export") == 0
        assert board_of(crewed)["news"][-1]["id"] == "D5"

    @pytest.mark.parametrize(
        "who, area, kind, message",
        [
            ("vic", "product", "fence", "this session does not hold roles.product"),
            ("ada", "legal", "fence", "area 'legal' is no role key"),
            ("ada", "product", "veto", "kind 'veto' is not one of cut, fence"),
        ],
    )
    def test_refusals_write_nothing(self, crewed, capsys, monkeypatch, who, area, kind, message):
        pin(monkeypatch, who)
        before = (crewed / "board.json").read_bytes()
        assert decide(crewed, area=area, kind=kind) == 1
        assert message in capsys.readouterr().err
        assert (crewed / "board.json").read_bytes() == before
        assert not (crewed / "board-decisions.jsonl").exists()


class TestBundle:
    def test_bundles_new_decisions_by_area_and_open_questions(self, crewed, monkeypatch):
        pin(monkeypatch, "vic")
        decide(crewed, area="architecture", kind="cut", key="PROJ-41", text="one adapter")
        pin(monkeypatch, "ada")
        decide(crewed)
        pin(monkeypatch, "otto")
        assert go(crewed, "bundle") == 0
        item = board_of(crewed)["news"][-1]
        assert item["id"] == "B-2026-11-03" and item["kind"] == "todo"
        assert item["title"] == "Bundle 2026-11-03: 2 decisions · 1 open questions"
        assert item["body"].splitlines() == [
            "product: fence PROJ-40 no paywall in v1",
            "architecture: cut PROJ-41 one adapter",
            "open: Q7",
        ]
        assert jsonl(crewed / "board-decisions.jsonl")[-1] == {
            "bundle": "B-2026-11-03",
            "ts": "2026-11-03T10:00:00Z",
        }

    def test_the_marker_keeps_old_decisions_out(self, crewed, monkeypatch, capsys):
        board.StateDir(crewed / "board.json").write_board(lambda b: b.update(owner_queue=[]))
        pin(monkeypatch, "ada")
        decide(crewed)
        pin(monkeypatch, "otto")
        go(crewed, "bundle")
        capsys.readouterr()
        before = (crewed / "board.json").read_bytes()
        assert go(crewed, "bundle") == 0
        assert capsys.readouterr().out.strip() == "bundle: nothing"
        assert (crewed / "board.json").read_bytes() == before
        pin(monkeypatch, "ada")
        decide(crewed, kind="cut", text="later one")
        pin(monkeypatch, "otto")
        go(crewed, "bundle")
        item = board_of(crewed)["news"][-1]
        assert item["id"] == "B-2026-11-03-2"
        assert item["body"] == "product: cut PROJ-40 later one"

    def test_a_closed_question_is_not_open(self, crewed, monkeypatch, capsys):
        (crewed / "board-answers.jsonl").write_text('{"id": "Q7", "answer": "deny"}\n')
        pin(monkeypatch, "otto")
        assert go(crewed, "bundle") == 0
        assert capsys.readouterr().out.strip() == "bundle: nothing"

    def test_only_the_coordinator_bundles(self, crewed, monkeypatch, capsys):
        pin(monkeypatch, "ada")
        assert go(crewed, "bundle") == 1
        assert "only the coordinator bundles" in capsys.readouterr().err


class TestLogFollowsTheBoard:
    """A JSONL line is appended only after board.json was replaced: a failed write logs nothing."""

    @pytest.mark.parametrize(
        "verb, log",
        [
            ("posted", "board-questions.jsonl"),
            ("returned", "board-questions.jsonl"),
            ("decision", "board-decisions.jsonl"),
            ("bundle", "board-decisions.jsonl"),
        ],
    )
    def test_a_failed_board_write_appends_no_line(self, crewed, monkeypatch, verb, log):
        answer_with(
            crewed, CLEAR if verb == "posted" else {"decides": "", "on_yes": "", "form": []}
        )
        if verb == "bundle":
            pin(monkeypatch, "ada")
            decide(crewed)
            pin(monkeypatch, "otto")
        else:
            pin(monkeypatch, "ada")
        before = jsonl(crewed / log)

        def broken(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(board.os, "replace", broken)
        with pytest.raises(OSError, match="disk full"):
            if verb == "decision":
                decide(crewed)
            elif verb == "bundle":
                go(crewed, "bundle")
            else:
                go(crewed, *ask_argv())
        assert jsonl(crewed / log) == before, (
            f"{verb}: {log} grew although board.json was not written"
        )


# --- escalation (decision story) -------------------------------------------------------------

LATER = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)  # past the 14:00Z self SLA
NEXT_MORNING = datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc)  # past 19:00Z, across the night


@pytest.fixture
def escalating(crewed):
    """The generic crew with `fallback.escalation: human_bundle`; the escalation holder `nora`."""
    path = crewed / "work" / ".weside" / "crew.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["fallback"] = {"escalation": "human_bundle"}
    path.write_text(json.dumps(data), encoding="utf-8")
    return crewed


def with_jira(state_dir):
    path = state_dir / "work" / ".weside" / "crew.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["board"] = {"ticketing": "jira"}
    path.write_text(json.dumps(data), encoding="utf-8")


def holder_line(state_dir, state):
    def mutate(b):
        b["sessions"] = [s for s in b["sessions"] if s["name"] != "nora"]
        if state is not None:
            b["sessions"].append({"name": "nora", "state": state})

    board.StateDir(state_dir / "board.json").write_board(mutate)


def open_argv(key="PROJ-4", parties="product,architecture", touches=None, **drop):
    argv = {
        "--key": key,
        "--parties": parties,
        "--question": "Ship the paywall in v1?",
        "--a": "no paywall in v1",
        "--a-cost": "two weeks of revenue",
        "--b": "paywall in v1",
        "--b-cost": "a second billing seam",
        "--reversible": "yes",
    }
    if touches:
        argv["--touches"] = touches
    for flag in drop:
        argv.pop("--" + flag.replace("_", "-"))
    return ["escalation", "open", *[x for kv in argv.items() for x in kv]]


def esc_log(state_dir):
    return jsonl(state_dir / "board-escalations.jsonl")


def record(state_dir, eid="E1"):
    return board.fold_escalations(esc_log(state_dir))[eid]


def carry_of(out):
    last = out.strip().splitlines()[-1]
    assert last.startswith("carry: "), out
    return json.loads(last[len("carry: ") :])


def opened(state_dir, monkeypatch, who="ada", now=NOW, **kw):
    pin(monkeypatch, who)
    assert go(state_dir, *open_argv(**kw), now=now) == 0


class TestEscalation:
    def test_open_writes_the_decision_story(self, escalating, monkeypatch, capsys):
        opened(escalating, monkeypatch)
        out = capsys.readouterr().out
        assert "carry:" not in out  # ticketing none
        [line] = esc_log(escalating)
        assert line["event"] == "open" and line["id"] == "E1"
        rec = record(escalating)
        assert rec.pop("since_open") == "2026-11-03T10:00Z"  # the week `count` files it under
        assert {k: rec[k] for k in rec if k not in ("ts",)} == {
            "id": "E1",
            "key": "PROJ-4",
            "parties": ["product", "architecture"],
            "by": "product",
            "question": "Ship the paywall in v1?",
            "a": "no paywall in v1",
            "a_cost": "two weeks of revenue",
            "b": "paywall in v1",
            "b_cost": "a second billing seam",
            "reversible": True,
            "touches": None,
            "stage": "self",
            "waiting_on": "product,architecture",
            "since": "2026-11-03T10:00Z",
            "sla_due": "2026-11-03T14:00Z",
            "open": True,
        }

    def test_open_with_jira_carries_the_story_as_a_comment(self, escalating, monkeypatch, capsys):
        with_jira(escalating)
        opened(escalating, monkeypatch, who="vic")
        [op] = carry_of(capsys.readouterr().out)
        assert op["op"] == "comment" and op["key"] == "PROJ-4"
        assert op["text"].splitlines() == [
            "Escalation E1 (product/architecture): Ship the paywall in v1?",
            "product: no paywall in v1 (cost: two weeks of revenue)",
            "architecture: paywall in v1 (cost: a second billing seam)",
            "Reversible: yes",
            "Waiting on: product,architecture since 2026-11-03T10:00Z, due 2026-11-03T14:00Z",
        ]

    @pytest.mark.parametrize(
        "who, argv, message",
        [
            (
                "otto",
                open_argv(),
                "this session holds neither roles.product nor roles.architecture",
            ),
            ("ada", open_argv(question=1), "missing --question"),
            ("ada", open_argv(b_cost=1), "missing --b-cost"),
            ("ada", open_argv(reversible=1), "missing --reversible"),
            ("ada", open_argv(parties="product,sales"), "party 'sales' is no role key"),
            ("ada", open_argv(parties="product"), "--parties names two different role keys"),
            ("ada", open_argv(parties="product,product"), "--parties names two different"),
            ("ada", open_argv(key="nokey"), "does not match naming.key"),
            ("ada", [*open_argv()[:-1], "maybe"], "--reversible 'maybe' is not yes or no"),
            ("ada", open_argv(touches="taste"), "--touches 'taste' is not one of"),
        ],
    )
    def test_open_refusals_write_nothing(
        self, escalating, monkeypatch, capsys, who, argv, message
    ):
        pin(monkeypatch, who)
        before = (escalating / "board.json").read_bytes()
        assert go(escalating, *argv) == 1
        assert message in capsys.readouterr().err
        assert esc_log(escalating) == []
        assert (escalating / "board.json").read_bytes() == before

    def test_not_past_the_sla_does_not_move(self, escalating, monkeypatch):
        opened(escalating, monkeypatch)
        pin(monkeypatch, "otto")
        assert go(escalating, "escalation", "route", now=NOW.replace(hour=13, minute=59)) == 0
        assert record(escalating)["stage"] == "self"
        assert len(esc_log(escalating)) == 1

    def test_an_active_holder_gets_the_escalation(self, escalating, monkeypatch, capsys):
        holder_line(escalating, "active")
        opened(escalating, monkeypatch)
        pin(monkeypatch, "otto")
        assert go(escalating, "escalation", "route", now=LATER) == 0
        assert "route: E1 PROJ-4 self → escalation" in capsys.readouterr().out
        rec = record(escalating)
        assert (rec["stage"], rec["waiting_on"], rec["since"], rec["sla_due"]) == (
            "escalation",
            "escalation",
            "2026-11-03T15:00Z",
            "2026-11-03T19:00Z",
        )
        assert [i["kind"] for i in board_of(escalating)["news"] if i.get("id") == "E1"] == [
            "escalation"
        ]

    def test_idle_holder_gets_escalation(self, escalating, monkeypatch):
        holder_line(escalating, "idle")
        opened(escalating, monkeypatch)
        pin(monkeypatch, "otto")
        go(escalating, "escalation", "route", now=LATER)
        rec = record(escalating)
        assert (rec["stage"], rec["waiting_on"]) == ("escalation", "escalation"), (
            "an idle escalation holder can still decide; only parked or absent falls back"
        )

    @pytest.mark.parametrize("state", ["parked", None])
    def test_parked_or_absent_holder_falls_back_to_the_bundle(
        self, escalating, monkeypatch, state
    ):
        holder_line(escalating, state)
        opened(escalating, monkeypatch)
        pin(monkeypatch, "otto")
        go(escalating, "escalation", "route", now=LATER)
        rec = record(escalating)
        assert (rec["stage"], rec["waiting_on"]) == ("bundle", "human")
        [item] = [i for i in board_of(escalating)["news"] if i.get("id") == "E1"]
        assert item["kind"] == "todo"
        assert item["title"] == "Escalation E1 PROJ-4: Ship the paywall in v1?"
        # a second route leaves the bundle record and its single item alone
        go(escalating, "escalation", "route", now=NEXT_MORNING)
        assert [i.get("id") for i in board_of(escalating)["news"]].count("E1") == 1
        assert len(esc_log(escalating)) == 2

    def test_a_past_sla_escalation_goes_to_the_bundle(self, escalating, monkeypatch):
        holder_line(escalating, "active")
        opened(escalating, monkeypatch)
        pin(monkeypatch, "otto")
        evening = datetime(2026, 11, 3, 17, 0, tzinfo=timezone.utc)  # 18:00 Berlin
        go(escalating, "escalation", "route", now=evening)
        # two hours left today (to 20:00 Berlin), two more from 08:00 Berlin: due 09:00Z
        assert record(escalating)["sla_due"] == "2026-11-04T09:00Z"
        go(
            escalating,
            "escalation",
            "route",
            now=datetime(2026, 11, 4, 8, 59, tzinfo=timezone.utc),
        )
        assert record(escalating)["stage"] == "escalation"
        go(escalating, "escalation", "route", now=datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc))
        assert record(escalating)["stage"] == "bundle"

    def test_route_is_the_coordinators(self, escalating, monkeypatch, capsys):
        opened(escalating, monkeypatch)
        assert go(escalating, "escalation", "route", now=LATER) == 1
        assert "only the coordinator routes" in capsys.readouterr().err

    def test_bundle_routes_first_and_lists_the_record(self, escalating, monkeypatch):
        holder_line(escalating, "parked")
        opened(escalating, monkeypatch)
        pin(monkeypatch, "otto")
        assert go(escalating, "bundle", now=LATER) == 0
        item = board_of(escalating)["news"][-1]
        assert item["id"] == "B-2026-11-03"
        assert item["title"] == "Bundle 2026-11-03: 0 decisions · 1 open questions · 1 escalations"
        assert item["body"].splitlines() == [
            "open: Q7",
            "escalation E1 PROJ-4: Ship the paywall in v1?",
        ]

    def test_settle_by_a_party_at_self(self, escalating, monkeypatch, capsys):
        with_jira(escalating)
        opened(escalating, monkeypatch)
        capsys.readouterr()
        pin(monkeypatch, "vic")
        assert go(escalating, "escalation", "settle", "E1", "--outcome", "no paywall") == 0
        [op] = carry_of(capsys.readouterr().out)
        assert op == {
            "op": "comment",
            "key": "PROJ-4",
            "text": "Escalation E1 settled at stage self by architecture: no paywall",
        }
        rec = record(escalating)
        assert rec["open"] is False and rec["outcome"] == "no paywall"

    @pytest.mark.parametrize(
        "stage_now, who, via, message",
        [
            (NOW, "nora", None, "E1 is at stage self; only a party settles it"),
            (NOW, "otto", "human", "--via human settles only a record at stage bundle"),
            (LATER, "ada", None, "E1 is at stage escalation; only roles.escalation settles it"),
            (LATER, "nora", "human", "--via human settles only a record at stage bundle"),
        ],
    )
    def test_settle_refusals(self, escalating, monkeypatch, capsys, stage_now, who, via, message):
        holder_line(escalating, "active")
        opened(escalating, monkeypatch)
        pin(monkeypatch, "otto")
        go(escalating, "escalation", "route", now=stage_now)
        before = esc_log(escalating)
        pin(monkeypatch, who)
        argv = ["escalation", "settle", "E1", "--outcome", "x"] + (["--via", via] if via else [])
        assert go(escalating, *argv, now=stage_now) == 1
        assert message in capsys.readouterr().err
        assert esc_log(escalating) == before

    def test_settle_by_the_holder_and_by_the_coordinator_for_the_human(
        self, escalating, monkeypatch, capsys
    ):
        holder_line(escalating, "active")
        opened(escalating, monkeypatch)
        opened(escalating, monkeypatch, key="PROJ-5")
        pin(monkeypatch, "otto")
        go(escalating, "escalation", "route", now=LATER)
        pin(monkeypatch, "nora")
        assert go(escalating, "escalation", "settle", "E1", "--outcome", "a", now=LATER) == 0
        pin(monkeypatch, "otto")
        go(escalating, "escalation", "route", now=NEXT_MORNING)  # past E2's 19:00Z
        assert record(escalating, "E2")["stage"] == "bundle"
        assert (
            go(escalating, "escalation", "settle", "E2", "--outcome", "b", "--via", "human") == 0
        )
        assert not record(escalating, "E1")["open"] and not record(escalating, "E2")["open"]
        assert (
            go(escalating, "escalation", "settle", "E2", "--outcome", "c", "--via", "human") == 1
        )
        assert "E2 is settled" in capsys.readouterr().err

    def test_touches_goes_to_bundle_with_advice(self, escalating, monkeypatch):
        holder_line(escalating, "active")
        opened(escalating, monkeypatch, touches="money")
        pin(monkeypatch, "otto")
        go(escalating, "escalation", "route", now=LATER)
        rec = record(escalating)
        assert (rec["stage"], rec["advice_from"], rec["touches"]) == (
            "bundle",
            "escalation",
            "money",
        ), "a money question goes to the human with the escalation role's advice"
        assert any(i.get("id") == "E1" for i in board_of(escalating)["news"])

    def test_settle_waits_for_advice(self, escalating, monkeypatch, capsys):
        holder_line(escalating, "active")
        opened(escalating, monkeypatch, touches="vision")
        pin(monkeypatch, "otto")
        go(escalating, "escalation", "route", now=LATER)
        capsys.readouterr()
        assert (
            go(escalating, "escalation", "settle", "E1", "--outcome", "x", "--via", "human") == 1
        )
        assert "waiting for the escalation role's recommendation" in capsys.readouterr().err
        go(escalating, "bundle", now=LATER)
        assert (
            "escalation E1 PROJ-4: Ship the paywall in v1? (advice pending)"
            in (board_of(escalating)["news"][-1]["body"])
        )
        assert go(escalating, "escalation", "advise", "E1", "--recommendation", "a") == 1
        assert "only roles.escalation advises" in capsys.readouterr().err
        pin(monkeypatch, "nora")
        assert go(escalating, "escalation", "advise", "E1", "--recommendation", "take a") == 0
        assert record(escalating)["recommendation"] == "take a"
        pin(monkeypatch, "otto")
        assert (
            go(escalating, "escalation", "settle", "E1", "--outcome", "a", "--via", "human") == 0
        )

    def test_advise_needs_a_touches_record(self, escalating, monkeypatch, capsys):
        opened(escalating, monkeypatch)
        pin(monkeypatch, "nora")
        assert go(escalating, "escalation", "advise", "E1", "--recommendation", "a") == 1
        assert "E1 asks for no advice" in capsys.readouterr().err

    def test_count_per_pair(self, escalating, monkeypatch, capsys):
        opened(escalating, monkeypatch)
        opened(escalating, monkeypatch, who="vic", parties="architecture,product", key="PROJ-5")
        out = capsys.readouterr().out
        assert "warning" not in out
        pin(monkeypatch, "otto")
        go(escalating, "escalation", "count")
        assert capsys.readouterr().out.splitlines() == ["architecture/product 2 in 2026-W45"]
        opened(escalating, monkeypatch, key="PROJ-6")
        out = capsys.readouterr().out.splitlines()
        assert out[-2:] == [
            "architecture/product 3 in 2026-W45",
            "warning: architecture/product: more than two escalations this week; "
            "the right in crew.json is drawn wrong",
        ]
        go(escalating, "escalation", "count")
        assert capsys.readouterr().out.splitlines() == out[-2:]
        # another week counts apart
        go(escalating, "escalation", "count", now=datetime(2026, 11, 10, 10, tzinfo=timezone.utc))
        assert capsys.readouterr().out.strip() == "escalations: none in 2026-W46"

    def test_a_failed_board_write_appends_no_route_line(self, escalating, monkeypatch):
        opened(escalating, monkeypatch)
        pin(monkeypatch, "otto")

        def broken(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(board.os, "replace", broken)
        with pytest.raises(OSError, match="disk full"):
            go(escalating, "escalation", "route", now=LATER)
        assert len(esc_log(escalating)) == 1


class TestEscalationSignal:
    """A record routed to stage `escalation` reaches its holder: a news item and `list`."""

    def test_a_routed_record_shows_in_list_waiting_on_its_role(
        self, escalating, monkeypatch, capsys
    ):
        holder_line(escalating, "active")
        opened(escalating, monkeypatch)
        opened(escalating, monkeypatch, key="PROJ-5", now=LATER)  # still at self
        pin(monkeypatch, "otto")
        go(escalating, "escalation", "route", now=LATER)
        capsys.readouterr()
        assert go(escalating, "escalation", "list", "--waiting-on", "escalation") == 0
        assert capsys.readouterr().out.splitlines() == [
            "E1 PROJ-4 product/architecture escalation since 2026-11-03T15:00Z "
            "due 2026-11-03T19:00Z"
        ]
        pin(monkeypatch, "nora")  # default: the caller's own role
        assert go(escalating, "escalation", "list") == 0
        assert capsys.readouterr().out.splitlines()[0].startswith("E1 PROJ-4 ")
        pin(monkeypatch, "ada")
        assert go(escalating, "escalation", "list") == 0
        assert [x.split()[0] for x in capsys.readouterr().out.splitlines()] == ["E2"]
        argv = ["escalation", "list", "--waiting-on", "product", "--stage", "bundle"]
        assert go(escalating, *argv) == 0
        assert capsys.readouterr().out.strip() == "escalations: none waiting on product at bundle"

    def test_list_refusals(self, escalating, monkeypatch, capsys):
        pin(monkeypatch, "zed")
        assert go(escalating, "escalation", "list") == 1
        assert "holds no role; pass --waiting-on" in capsys.readouterr().err
        assert go(escalating, "escalation", "list", "--waiting-on", "sales") == 1
        assert "--waiting-on 'sales' is no role key" in capsys.readouterr().err
        assert go(escalating, "escalation", "list", "--waiting-on", "human", "--stage", "x") == 1
        assert "--stage 'x' is not one of self, escalation, bundle" in capsys.readouterr().err

    def test_route_to_escalation_writes_one_news_item_for_the_holder(
        self, escalating, monkeypatch
    ):
        holder_line(escalating, "active")
        opened(escalating, monkeypatch)
        pin(monkeypatch, "otto")
        go(escalating, "escalation", "route", now=LATER)
        [item] = [i for i in board_of(escalating)["news"] if i.get("id") == "E1"]
        assert (item["kind"], item["for"], item["title"]) == (
            "escalation",
            "escalation",
            "Escalation E1 PROJ-4: Ship the paywall in v1?",
        )
        # moving on to the bundle replaces it: one item per id, now the human's todo
        go(escalating, "escalation", "route", now=NEXT_MORNING)
        [item] = [i for i in board_of(escalating)["news"] if i.get("id") == "E1"]
        assert item["kind"] == "todo"

    def test_a_failed_board_write_leaves_no_escalation_news(self, escalating, monkeypatch):
        holder_line(escalating, "active")
        opened(escalating, monkeypatch)
        pin(monkeypatch, "otto")
        before = (escalating / "board.json").read_bytes()

        def broken(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(board.os, "replace", broken)
        with pytest.raises(OSError, match="disk full"):
            go(escalating, "escalation", "route", now=LATER)
        assert (escalating / "board.json").read_bytes() == before
        assert len(esc_log(escalating)) == 1

    def test_a_touches_record_waits_on_the_holder_until_advised(
        self, escalating, monkeypatch, capsys
    ):
        holder_line(escalating, "active")
        opened(escalating, monkeypatch, touches="money")
        pin(monkeypatch, "otto")
        go(escalating, "escalation", "route", now=LATER)
        capsys.readouterr()
        pin(monkeypatch, "nora")
        assert go(escalating, "escalation", "list") == 0
        assert capsys.readouterr().out.splitlines() == [
            "E1 PROJ-4 product/architecture bundle since 2026-11-03T15:00Z "
            "due 2026-11-03T19:00Z (advice pending)"
        ]
        news = {
            i["id"]: i for i in board_of(escalating)["news"] if i.get("id", "").startswith("E1")
        }
        assert news["E1"]["kind"] == "todo" and "for" not in news["E1"]
        assert (news["E1a"]["kind"], news["E1a"]["for"], news["E1a"]["title"]) == (
            "escalation",
            "escalation",
            "Advice E1 PROJ-4: Ship the paywall in v1?",
        )
        # a second route adds no second advice item
        pin(monkeypatch, "otto")
        go(escalating, "escalation", "route", now=NEXT_MORNING)
        ids = [i.get("id") for i in board_of(escalating)["news"]]
        assert (ids.count("E1"), ids.count("E1a")) == (1, 1)
        pin(monkeypatch, "nora")
        assert go(escalating, "escalation", "advise", "E1", "--recommendation", "take a") == 0
        capsys.readouterr()
        assert go(escalating, "escalation", "list") == 0
        assert capsys.readouterr().out.strip() == "escalations: none waiting on escalation"
        ids = [i.get("id") for i in board_of(escalating)["news"]]
        assert "E1a" not in ids and "E1" in ids, "advice drops the holder's item, not the todo"

    def test_settle_drops_the_records_news_items(self, escalating, monkeypatch):
        holder_line(escalating, "active")
        opened(escalating, monkeypatch)
        opened(escalating, monkeypatch, key="PROJ-5")
        pin(monkeypatch, "otto")
        go(escalating, "escalation", "route", now=LATER)
        assert {"E1", "E2"} <= {i.get("id") for i in board_of(escalating)["news"]}
        pin(monkeypatch, "nora")
        assert go(escalating, "escalation", "settle", "E1", "--outcome", "a") == 0
        ids = [i.get("id") for i in board_of(escalating)["news"]]
        assert "E1" not in ids and "E2" in ids

    def test_settle_via_human_drops_the_todo(self, escalating, monkeypatch):
        holder_line(escalating, "parked")
        opened(escalating, monkeypatch)
        pin(monkeypatch, "otto")
        go(escalating, "escalation", "route", now=LATER)
        assert "E1" in [i.get("id") for i in board_of(escalating)["news"]]
        argv = ["escalation", "settle", "E1", "--outcome", "a", "--via", "human"]
        assert go(escalating, *argv) == 0
        assert "E1" not in [i.get("id") for i in board_of(escalating)["news"]]


# --- moves: select, move, check (the ticketing adapter, the transitions log, carry:) ---------

import lens_verdict  # noqa: E402
import test_plan_tier  # noqa: E402
import ticket_adapter  # noqa: E402

GATE_PLANS = HERE / "fixtures" / "ready_gate" / "plans"
KEY = "PROJ-12"
GREEN_LENS = '```json\n{"findings": []}\n```'


def git(root, *args):
    return test_plan_tier.git(root, *args)


@pytest.fixture
def moving(crewed, monkeypatch):
    """`work` as a git repo: the generic crew with `risk.command` bound to the fake classifier,
    a green story plan PROJ-12 (epic PROJ-1, a `lib-repo` phase), the gate's epic plans and a
    draft epic PROJ-5, all on `origin/main`; the fake `gh` reads $FAKE_GH."""
    work = crewed / "work"
    (work / ".git").rmdir()
    crew_path = work / ".weside" / "crew.json"
    data = json.loads(crew_path.read_text(encoding="utf-8"))
    data["risk"] = {"command": "scripts/risk"}
    crew_path.write_text(json.dumps(data), encoding="utf-8")
    plans = work / "docs" / "plans"
    plans.mkdir(parents=True)
    for name in ("PROJ-1-epic.md", "PROJ-2-epic.md"):
        shutil.copy(GATE_PLANS / name, plans / name)
    epic = (GATE_PLANS / "PROJ-1-epic.md").read_text(encoding="utf-8")
    (plans / "PROJ-5-epic.md").write_text(
        epic.replace("ticket: PROJ-1", "ticket: PROJ-5").replace(
            "status: approved", "status: draft"
        ),
        encoding="utf-8",
    )
    story = (GATE_PLANS / "green.md").read_text(encoding="utf-8")
    story = story.replace("[receipt]", "[`ci`: `tests/test_export.py`]")
    (plans / f"{KEY}-story.md").write_text(story, encoding="utf-8")
    (work / "scripts").mkdir()
    shutil.copy(test_plan_tier.RISK, work / "scripts" / "risk")
    git(work, "init", "-q", "-b", "main")
    git(work, "config", "user.email", "t@example.org")
    git(work, "config", "user.name", "t")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "base")
    git(work, "update-ref", "refs/remotes/origin/main", "HEAD")
    for var in ("FAKE_RISK_EXIT", "FAKE_RISK_LINE", "FAKE_RISK_LOG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("FAKE_GH", str(crewed / "gh.json"))
    monkeypatch.setenv("FAKE_GH_LOG", str(crewed / "gh-calls.jsonl"))
    (crewed / "gh.json").write_text("{}", encoding="utf-8")
    return crewed


def green_lenses(state_dir, key=KEY):
    root = state_dir / "work"
    vid = f"ready-{key}"
    panel = lens_verdict.plan(root, "ready", key)
    for entry in panel["entries"]:
        lens_verdict.write(root, vid, entry["lens"], answer=GREEN_LENS)
    return vid


def gh_answers(state_dir, table):
    (state_dir / "gh.json").write_text(json.dumps(table), encoding="utf-8")


def gh_calls(state_dir):
    return jsonl(state_dir / "gh-calls.jsonl")


def transitions(state_dir):
    return jsonl(state_dir / "board-transitions.jsonl")


def act(state_dir, *argv, adapter=None, now=NOW):
    return board.main(["--board", str(state_dir / "board.json"), *argv], now=now, adapter=adapter)


def fake():
    return ticket_adapter.FakeAdapter({KEY: "Backlog"})


def assert_untouched(state_dir, before, out, adapter):
    assert adapter.calls == [] and adapter.statuses == {KEY: "Backlog"}
    assert not (state_dir / "board-transitions.jsonl").exists()
    assert (state_dir / "board.json").read_bytes() == before
    assert "carry:" not in out


def with_row(state_dir, key, to):
    board.StateDir(state_dir / "board.json").append_transition({"key": key, "to": to})


class TestSelect:
    def test_a_plan_failing_the_gate_is_refused_with_its_lines(self, moving, capsys):
        plan = moving / "work" / "docs" / "plans" / f"{KEY}-story.md"
        plan.write_text(plan.read_text().replace("**Then** it writes", "it writes"))
        before = (moving / "board.json").read_bytes()
        adapter = fake()
        assert act(moving, "select", KEY, adapter=adapter) == 1
        out, err = capsys.readouterr()
        lines = [x for x in err.splitlines() if not x.startswith("warning:")]
        assert lines == [
            f"board.py select {KEY}: refused (ready gate)",
            f"{moving / 'work' / 'docs' / 'plans' / f'{KEY}-story.md'}: AC2: no `**Then**`",
        ]
        assert_untouched(moving, before, out, adapter)

    def test_a_tier_that_cannot_be_computed_is_refused(self, moving, monkeypatch, capsys):
        monkeypatch.setenv("FAKE_RISK_EXIT", "2")
        before = (moving / "board.json").read_bytes()
        adapter = fake()
        assert act(moving, "select", KEY, adapter=adapter) == 1
        out, err = capsys.readouterr()
        assert err.splitlines()[-2:] == [
            f"board.py select {KEY}: refused (tier)",
            "tier not computed: risk.command exit 2: risk: refused",
        ]
        assert_untouched(moving, before, out, adapter)

    def test_a_green_story_selects_with_its_tier(self, moving, monkeypatch, capsys):
        green_lenses(moving)
        monkeypatch.setenv("FAKE_RISK_LINE", "T2 one-way money")
        adapter = fake()
        assert act(moving, "select", KEY, adapter=adapter) == 0
        out = capsys.readouterr().out
        assert out.splitlines()[0] == "tier: T2 one-way money"
        [row] = transitions(moving)
        assert {k: row[k] for k in ("key", "from", "to", "tier", "ticket", "by")} == {
            "key": KEY,
            "from": None,
            "to": "selected",
            "tier": "T2 one-way money",
            "ticket": "fake",
            "by": "lead-12",
        }
        assert adapter.calls[0] == ("move", KEY, "Selected for Development")
        op, key, text = adapter.calls[1]
        assert (op, key) == ("comment", KEY)
        assert re.fullmatch(
            rf"selected by master@hal, plan [0-9a-f]{{12}}, panel ready-{KEY}", text
        ), text
        assert len(adapter.calls) == 2

    def test_select_never_asks(self, moving):
        green_lenses(moving)
        answers = moving / "board-answers.jsonl"
        answers.write_text('{"id": "Q7", "answer": "info"}\n', encoding="utf-8")
        before = (moving / "board.json").read_bytes(), answers.read_bytes()
        assert act(moving, "select", KEY, adapter=fake()) == 0
        after = (moving / "board.json").read_bytes(), answers.read_bytes()
        assert after == before, "select wrote board.json or the answers file"
        sub = board.parser()._subparsers._group_actions[0].choices["select"]
        options = {s for a in sub._actions for s in a.option_strings} - {"-h", "--help"}
        assert options == {"--plan", "--input"}
        assert [g for g, _ in board.ENTRY_RULES["selected"]] == [
            "role",
            "owner",
            "ready gate",
            "plan on main",
            "tier",
            "lenses",
        ]


class TestSelectLenses:
    @pytest.mark.parametrize("verdict", ["missing", "red", "stale"])
    def test_without_a_green_verdict_select_is_refused(self, moving, capsys, verdict):
        root = moving / "work"
        vid = f"ready-{KEY}"
        if verdict != "missing":
            panel = lens_verdict.plan(root, "ready", KEY)
            for entry in panel["entries"]:
                if verdict == "red" and entry["lens"] == "architecture":
                    lens_verdict.write(root, vid, entry["lens"], failed="the agent stopped")
                else:
                    lens_verdict.write(root, vid, entry["lens"], answer=GREEN_LENS)
        if verdict == "stale":
            plan = root / "docs" / "plans" / f"{KEY}-story.md"
            # an edit outside the margin sections (lens_verdict § Carried edit) moves the panel
            plan.write_text(plan.read_text().replace("\n## ", "\n<!-- edited -->\n\n## ", 1))
        before = (moving / "board.json").read_bytes()
        adapter = fake()
        assert act(moving, "select", KEY, adapter=adapter) == 1
        out, err = capsys.readouterr()
        _, expected = lens_verdict.check(root, vid)
        lines = err.splitlines()
        head = lines.index(f"board.py select {KEY}: refused (lenses)")
        assert lines[head + 1 :] == expected
        assert_untouched(moving, before, out, adapter)

    def test_a_failing_gate_never_reads_the_verdict(self, moving, monkeypatch, capsys):
        plan = moving / "work" / "docs" / "plans" / f"{KEY}-story.md"
        plan.write_text(plan.read_text().replace("**Then** it writes", "it writes"))
        read = []
        monkeypatch.setattr(
            lens_verdict, "check_panel", lambda *a: read.append(a) or (True, [], [])
        )
        assert act(moving, "select", KEY, adapter=fake()) == 1
        assert read == []
        assert "refused (ready gate)" in capsys.readouterr().err

    @pytest.mark.parametrize("rounds", [None, 2])
    def test_select_carries_the_warnings_of_round_n_into_the_row(self, moving, capsys, rounds):
        root = moving / "work"
        crew_path = root / ".weside" / "crew.json"
        data = json.loads(crew_path.read_text(encoding="utf-8"))
        if rounds is not None:
            data["ready_panel"] = {"warning_ok_after_rounds": rounds}
        crew_path.write_text(json.dumps(data), encoding="utf-8")
        vid = f"ready-{KEY}"
        plan = root / "docs" / "plans" / f"{KEY}-story.md"
        lens_verdict.plan(root, "ready", KEY)
        plan.write_text(plan.read_text() + "\n<!-- round 2 -->\n")
        panel = lens_verdict.plan(root, "ready", KEY)
        warning = {"severity": "WARNING", "claim": "name the error", "where": "plan:AC3"}
        warning["question"] = "q"
        for entry in panel["entries"]:
            body = {"findings": [warning] if entry["lens"] == "acceptance" else []}
            lens_verdict.write(root, vid, entry["lens"], answer=json.dumps(body))
        adapter = fake()
        code = act(moving, "select", KEY, adapter=adapter)
        out, err = capsys.readouterr()
        if rounds is None:
            assert code == 1 and "refused (lenses)" in err
            assert "lens acceptance: red (WARNING plan:AC3)" in err
            return
        assert code == 0, err
        carried = [{"lens": "acceptance", "claim": "name the error", "where": "plan:AC3"}]
        assert transitions(moving)[-1]["carried"] == carried
        assert "carried: acceptance: name the error (plan:AC3)" in out.splitlines()

    def test_select_prints_a_derived_round_with_its_origin(self, moving, capsys):
        """A verdict file of 8.10.0 (no ``round``) with logged runs on two plan blobs."""
        root = moving / "work"
        crew_path = root / ".weside" / "crew.json"
        data = json.loads(crew_path.read_text(encoding="utf-8"))
        data["ready_panel"] = {"warning_ok_after_rounds": 2}
        crew_path.write_text(json.dumps(data), encoding="utf-8")
        vid = f"ready-{KEY}"
        plan = root / "docs" / "plans" / f"{KEY}-story.md"
        path = lens_verdict.verdict_dir(root) / f"{vid}.json"
        for version in (1, 2):
            if version == 2:
                plan.write_text(plan.read_text() + "\n<!-- round 2 -->\n")
            panel = lens_verdict.plan(root, "ready", KEY)
            warning = {"severity": "WARNING", "claim": "name the error", "where": "plan:AC3"}
            warning["question"] = "q"
            for entry in panel["entries"]:
                body = {"findings": [warning] if entry["lens"] == "acceptance" else []}
                lens_verdict.write(root, vid, entry["lens"], answer=json.dumps(body))
            doc = json.loads(path.read_text(encoding="utf-8"))
            del doc["round"]
            path.write_text(json.dumps(doc), encoding="utf-8")
        code = act(moving, "select", KEY, adapter=fake())
        out, err = capsys.readouterr()
        assert code == 0, err
        assert any(
            line.startswith("round: 2 (derived: 2 plan blobs with logged lens verdicts: ")
            for line in out.splitlines()
        )
        assert transitions(moving)[-1]["round"].startswith("2 (derived: ")


class TestMove:
    @pytest.mark.parametrize(
        "argv, message",
        [
            (["on_hold"], 'on_hold needs --reopen "<trigger>"'),
            (["on_hold", "--reopen", " "], 'on_hold needs --reopen "<trigger>"'),
            (["backlog"], "backlog needs --epic <EPIC>"),
            (["backlog", "--epic", "PROJ-5"], "epic PROJ-5 is not approved (PROJ-5-epic.md"),
            (["backlog", "--epic", "PROJ-9"], "no epic plan under docs/plans names PROJ-9"),
            (["selected"], "use board.py select"),
            (["in_progress"], "in_progress needs the key's last row to be selected (no row)"),
            (["in_review"], "in_review needs --pr <ref>"),
        ],
    )
    def test_a_missing_entry_input_is_refused_naming_the_rule(self, moving, capsys, argv, message):
        before = (moving / "board.json").read_bytes()
        adapter = fake()
        assert act(moving, "move", KEY, *argv, adapter=adapter) == 1
        out, err = capsys.readouterr()
        assert err.startswith(f"board.py move {KEY} {argv[0]}: refused: {message}"), err
        assert_untouched(moving, before, out, adapter)

    def test_two_epic_plans_naming_the_epic_are_both_named(self, moving, capsys):
        plans = moving / "work" / "docs" / "plans"
        shutil.copy(plans / "PROJ-1-epic.md", plans / "PROJ-1b-epic.md")
        assert act(moving, "move", KEY, "backlog", "--epic", "PROJ-1", adapter=fake()) == 1
        assert (
            "PROJ-1 is named by more than one epic plan: PROJ-1-epic.md and PROJ-1b-epic.md"
            in (capsys.readouterr().err)
        )

    def test_in_progress_after_another_state_is_refused(self, moving, capsys):
        with_row(moving, KEY, "backlog")
        assert act(moving, "move", KEY, "in_progress", adapter=fake()) == 1
        assert "(its last row is backlog)" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "argv, extra",
        [
            (
                ["on_hold", "--reopen", "after the store review"],
                {"reopen": "after the store review"},
            ),
            (["backlog", "--epic", "PROJ-1"], {"epic": "PROJ-1"}),
            (["backlog", "--epic", "PROJ-3"], {"epic": "PROJ-3"}),  # linked_epics of PROJ-2
            (["in_progress"], {}),
        ],
    )
    def test_a_held_rule_moves_once_and_writes_one_row(self, moving, capsys, argv, extra):
        if argv[0] == "in_progress":
            with_row(moving, KEY, "selected")
        adapter = fake()
        assert act(moving, "move", KEY, *argv, adapter=adapter) == 0
        status = board.crew_mod.DEFAULTS["board"]["states"][argv[0]]
        assert adapter.calls == [("move", KEY, status)]
        row = transitions(moving)[-1]
        assert {k: row[k] for k in ("key", "to", "ticket", "by")} == {
            "key": KEY,
            "to": argv[0],
            "ticket": "fake",
            "by": "lead-12",
        }
        assert row["ts"] == "2026-11-03T10:00:00Z"
        assert {k: row[k] for k in extra} == extra
        assert json.loads(capsys.readouterr().out.splitlines()[-1]) == row


MERGED = {
    "state": "MERGED",
    "mergedAt": "2026-11-03T09:00:00Z",
    "headRefName": f"feat/{KEY}-export",
    "title": "feat: export",
    "url": "https://github.com/acme/app/pull/7",
}


def pr(**changes):
    return {"pr": {**MERGED, **changes}}


class TestMoveInReview:
    @pytest.mark.parametrize(
        "answer, message",
        [
            (pr(headRefName="feat/export", title="feat: no key"), "PR acme/app#7 is not linked"),
            (pr(headRefName="feat/PROJ-123-x", title="PROJ-123"), "PR acme/app#7 is not linked"),
            (pr(state="OPEN"), "PR acme/app#7 is not merged"),
            ({"exit": 1}, "PR acme/app#7: gh pr view failed: gh broke"),
        ],
    )
    def test_each_pr_must_be_merged_and_linked(self, moving, capsys, answer, message):
        gh_answers(moving, {"7 -R acme/app": answer})
        before = (moving / "board.json").read_bytes()
        adapter = fake()
        assert act(moving, "move", KEY, "in_review", "--pr", "acme/app#7", adapter=adapter) == 1
        out, err = capsys.readouterr()
        expected = message + (f" to {KEY}" if message.endswith("linked") else "")
        assert err.strip() == f"board.py move {KEY} in_review: refused: {expected}"
        assert_untouched(moving, before, out, adapter)

    def test_linked_by_title_alone_passes(self, moving):
        gh_answers(moving, {"7 -R acme/app": pr(headRefName="feat/x", title=f"{KEY}: export")})
        assert act(moving, "move", KEY, "in_review", "--pr", "acme/app#7", adapter=fake()) == 0

    def test_two_prs_with_one_unlinked_name_that_one(self, moving, capsys):
        gh_answers(
            moving,
            {
                "7 -R acme/app": pr(),
                "https://github.com/acme/lib-repo/pull/3": pr(headRefName="x", title="y"),
            },
        )
        argv = ["--pr", "acme/app#7", "--pr", "https://github.com/acme/lib-repo/pull/3"]
        assert act(moving, "move", KEY, "in_review", *argv, adapter=fake()) == 1
        assert capsys.readouterr().err.splitlines() == [
            f"board.py move {KEY} in_review: refused: PR https://github.com/acme/lib-repo/pull/3 "
            f"is not linked to {KEY}"
        ]

    def test_a_bare_number_is_ambiguous_when_the_plan_names_another_repo(self, moving, capsys):
        assert act(moving, "move", KEY, "in_review", "--pr", "7", adapter=fake()) == 1
        assert capsys.readouterr().err.strip() == (
            f"board.py move {KEY} in_review: refused: PR 7 is ambiguous: "
            "name it <owner>/<repo>#7 or by URL"
        )
        assert gh_calls(moving) == []

    def test_qualified_refs_and_urls_reach_gh_as_given(self, moving):
        url = "https://github.com/acme/lib-repo/pull/3"
        gh_answers(moving, {"7 -R acme/app": pr(), url: pr(url=url)})
        argv = ["--pr", "acme/app#7", "--pr", url]
        assert act(moving, "move", KEY, "in_review", *argv, adapter=fake()) == 0
        fields = ["--json", "state,mergedAt,headRefName,title,url"]
        assert gh_calls(moving) == [
            ["pr", "view", "7", "-R", "acme/app", *fields],
            ["pr", "view", url, *fields],
        ]
        assert transitions(moving)[-1]["pr"] == [MERGED["url"], url]

    def test_a_plan_of_its_own_repo_takes_a_bare_number(self, moving):
        git(moving / "work", "remote", "add", "origin", "https://example.org/acme/lib-repo.git")
        gh_answers(moving, {"7": pr()})
        assert act(moving, "move", KEY, "in_review", "--pr", "7", adapter=fake()) == 0


class TestJiraTransport:
    def test_select_carries_the_bound_status_as_the_last_line(self, moving, capsys):
        with_jira(moving)
        green_lenses(moving)
        assert act(moving, "select", KEY) == 0
        out = capsys.readouterr().out
        assert out.splitlines()[-1].startswith("carry: ")
        carried = carry_of(out)
        assert carried[0] == {"op": "transition", "key": KEY, "status": "Selected for Development"}
        assert carried[1]["op"] == "comment" and carried[1]["text"].startswith("selected by ")
        assert len(carried) == 2
        assert transitions(moving)[-1]["ticket"] == "carried"

    def test_a_refused_move_carries_nothing(self, moving, capsys):
        with_jira(moving)
        assert act(moving, "move", KEY, "in_progress") == 1
        out, err = capsys.readouterr()
        assert "carry:" not in out + err

    def test_ticketing_none_carries_nothing_and_says_so(self, moving, capsys):
        with_row(moving, KEY, "selected")
        assert act(moving, "move", KEY, "in_progress") == 0
        assert "carry:" not in capsys.readouterr().out
        assert transitions(moving)[-1]["ticket"] == "none"


def snapshot(state_dir, data):
    path = state_dir / "jira.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


class TestCheck:
    def test_a_transition_without_a_row_is_drift(self, moving, capsys):
        """The red arm of AC7: Jira moved on, the board's last row is still `selected`."""
        with_row(moving, KEY, "selected")
        assert act(moving, "check", "--jira", snapshot(moving, {KEY: "In Progress"})) == 1
        assert capsys.readouterr().out.splitlines() == [
            f'drift: {KEY} jira "In Progress" board selected'
        ]

    def test_a_key_with_no_row_beyond_backlog_is_drift(self, moving, capsys):
        jira = snapshot(moving, {"PROJ-2": "In Review", "PROJ-3": "Backlog", "PROJ-4": "On Hold"})
        assert act(moving, "check", "--jira", jira) == 1
        assert capsys.readouterr().out.splitlines() == [
            'drift: PROJ-2 jira "In Review" board none'
        ]

    def test_a_session_still_holding_a_reviewed_key_is_drift(self, moving, capsys):
        with_row(moving, KEY, "in_review")

        def hold(b):
            b["sessions"][0]["keys"] = [KEY]

        board.StateDir(moving / "board.json").write_board(hold)
        assert act(moving, "check", "--jira", snapshot(moving, {KEY: "In Review"})) == 1
        assert capsys.readouterr().out.splitlines() == [
            f"drift: {KEY} session lead-12 still holds it (board in_review)"
        ]

    def test_no_mismatch_is_exit_0_with_the_count(self, moving, capsys):
        with_row(moving, KEY, "selected")
        with_row(moving, KEY, "in_progress")
        jira = snapshot(moving, {KEY: "In Progress", "PROJ-3": "Backlog"})
        assert act(moving, "check", "--jira", jira) == 0
        assert capsys.readouterr().out.strip() == "no drift (2 keys)"

    def test_an_unknown_status_is_one_error_and_the_rest_is_judged(self, moving, capsys):
        with_row(moving, "PROJ-3", "selected")
        jira = snapshot(moving, {"PROJ-2": "Waiting for Godot", "PROJ-3": "In Review"})
        assert act(moving, "check", "--jira", jira) == 1
        assert capsys.readouterr().out.splitlines() == [
            'error: PROJ-2 jira "Waiting for Godot" is no board state',
            'drift: PROJ-3 jira "In Review" board selected',
        ]

    @pytest.mark.parametrize("content", [None, "{not json", '["PROJ-1"]', '{"PROJ-1": 3}'])
    def test_an_unusable_snapshot_is_exit_2(self, moving, capsys, content):
        path = moving / "jira.json"
        if content is not None:
            path.write_text(content, encoding="utf-8")
        assert act(moving, "check", "--jira", str(path)) == 2
        assert "board.py check: --jira" in capsys.readouterr().err


class TestTransitionsLog:
    def test_transitions_only_grow(self, crewless):
        state = board.StateDir(crewless / "board.json")
        state.append_transition({"key": "PROJ-1", "to": "selected"})
        first = state.transitions_path.read_bytes()
        state.append_transition({"key": "PROJ-1", "to": "in_progress"})
        assert state.transitions_path.read_bytes().startswith(first)
        assert [r["to"] for r in state.transitions()] == ["selected", "in_progress"]


class TestTicketAdapter:
    def test_the_transports_by_ticketing(self):
        assert isinstance(ticket_adapter.adapter_for({}), ticket_adapter.NoneAdapter)
        jira = ticket_adapter.adapter_for({"board": {"ticketing": "jira"}})
        assert isinstance(jira, ticket_adapter.SessionTransport)
        assert [op.as_json() for op in jira.move("PROJ-1", "Done")] == [
            {"op": "transition", "key": "PROJ-1", "status": "Done"}
        ]
        assert ticket_adapter.NoneAdapter().move("PROJ-1", "Done") == []

    def test_an_unknown_transport_is_named(self):
        with pytest.raises(
            ValueError, match=r"board\.ticketing 'carrier-pigeon' has no transport"
        ):
            ticket_adapter.adapter_for({"board": {"ticketing": "carrier-pigeon"}})


def with_ticketing(state_dir, name):
    path = state_dir / "work" / ".weside" / "crew.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["board"] = {**(data.get("board") or {}), "ticketing": name}
    path.write_text(json.dumps(data), encoding="utf-8")


class TestUnknownTicketing:
    """Only the verbs that call the adapter build it: an unknown `board.ticketing` leaves the
    others working and stops `select`, `move` and `escalation open|settle` before any write."""

    def test_verbs_without_the_adapter_work_with_an_unknown_ticketing(self, crewed, capsys):
        with_ticketing(crewed, "github")
        for argv in (("set", "now=phase 3", "state=ci"), ("escalation", "count")):
            code = go(crewed, *argv)
            assert capsys.readouterr().err == ""  # not "crew: board.ticketing 'github' …"
            assert code == 0
        assert line_of(crewed, "lead-12")["now"] == "phase 3"

    def test_a_move_names_the_unknown_ticketing_and_writes_nothing(self, moving, capsys):
        with_ticketing(moving, "github")
        with_row(moving, KEY, "selected")
        before = transitions(moving)
        assert act(moving, "move", KEY, "in_progress") == 1
        assert capsys.readouterr().err.strip() == (
            "crew: board.ticketing 'github' has no transport (known: none, jira)"
        )
        assert transitions(moving) == before

    def test_an_escalation_open_names_it_before_the_write(self, escalating, monkeypatch, capsys):
        with_ticketing(escalating, "github")
        pin(monkeypatch, "ada")
        assert go(escalating, *open_argv()) == 1
        assert capsys.readouterr().err.strip() == (
            "crew: board.ticketing 'github' has no transport (known: none, jira)"
        )
        assert esc_log(escalating) == []


# --- the done move (docs/board.md § Moves, § Acceptance) -------------------------------------

VERDICT = HERE / "fixtures" / "accept" / "accept_verdict.json"
DONE_KEY = "PROJ-1"


def verdict_entry(key=DONE_KEY, **changes):
    stories = json.loads(VERDICT.read_text(encoding="utf-8"))["stories"]
    entry = copy.deepcopy(next(s for s in stories if s["key"] == key))
    entry.update(changes)
    return entry


def comment_file(state_dir, text):
    path = state_dir / "comment.md"
    path.write_text(text, encoding="utf-8")
    return str(path)


def done_in_process(state_dir, adapter, entry, key=DONE_KEY, now=NOW):
    return board.move_done(
        board.StateDir(state_dir / "board.json"),
        key,
        board.load_crew(),
        now,
        adapter,
        entry=entry,
        rc="v1.4.0-rc.2",
        run_url="https://example.org/acme/app/actions/runs/4242",
    )


def set_sample(state_dir, sample, keeper=None, lens_sample=None):
    """`acceptance.done_sample` drives the Done-row sample; `lenses.acceptance.sample` is the lens
    sampler's (lens_verdict.py) and set apart so a test can show the two never mix."""
    path = state_dir / "work" / ".weside" / "crew.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["lenses"] = {"acceptance": {"sample": lens_sample, "keeper": keeper}}
    data.setdefault("acceptance", {})["done_sample"] = sample
    path.write_text(json.dumps(data), encoding="utf-8")


def news_of(state_dir, kind):
    return [n for n in board_of(state_dir).get("news") or [] if n.get("kind") == kind]


class TestMoveDone:
    @pytest.mark.parametrize(
        "last, argv, message",
        [
            (None, ["--comment-file", "C"], "last move is none, not in_review"),
            ("in_progress", ["--comment-file", "C"], "last move is in_progress, not in_review"),
            ("done", ["--comment-file", "C"], "last move is done, not in_review"),
            ("in_review", [], "done needs --comment-file FILE"),
            ("in_review", ["--comment-file", "NONE"], "has no line `Not proven: <what>`"),
            ("in_review", ["--comment-file", "EMPTY"], "has no line `Not proven: <what>`"),
        ],
    )
    def test_the_cli_refuses_naming_the_rule(self, crewed, capsys, last, argv, message):
        files = {
            "C": comment_file(crewed, "Checked on staging.\nNot proven: the native device\n"),
            "NONE": str(crewed / "none.md"),
            "EMPTY": str(crewed / "empty.md"),
        }
        (crewed / "none.md").write_text("Checked on staging.\nnot proven: lower case\n")
        (crewed / "empty.md").write_text("Checked.\nNot proven:   \n")
        if last:
            with_row(crewed, DONE_KEY, last)
        before_rows = transitions(crewed)
        adapter = ticket_adapter.FakeAdapter()
        argv = [files.get(a, a) for a in argv]
        assert act(crewed, "move", DONE_KEY, "done", *argv, adapter=adapter) == 1
        out, err = capsys.readouterr()
        assert err.startswith(f"board.py move {DONE_KEY} done: refused: "), err
        assert message in err.splitlines()[0], err
        assert transitions(crewed) == before_rows and adapter.calls == []
        assert "carry:" not in out

    def test_the_cli_has_no_verdict_flag(self, crewed, capsys):
        with_row(crewed, DONE_KEY, "in_review")
        with pytest.raises(SystemExit) as stop:
            act(crewed, "move", DONE_KEY, "done", "--verdict", str(VERDICT))
        assert stop.value.code == 2
        assert "unrecognized arguments: --verdict" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "entry, message",
        [
            (verdict_entry("PROJ-2"), f"the verdict has no entry for {DONE_KEY}"),
            (verdict_entry(verdict="walk"), "verdict is walk, not done"),
            (
                verdict_entry(walk=[{"ac": 4, "persona": "p", "screen": "s"}]),
                "the entry still has a walk",
            ),
            (
                verdict_entry(
                    checks=[
                        {"ac": 1, "persona": "p", "status": "FAIL", "observed": "500"},
                        {"ac": 2, "persona": "p", "status": "PASS", "observed": "ok"},
                    ]
                ),
                "receipt check AC1 is FAIL, not PASS",
            ),
            (
                verdict_entry(
                    checks=[
                        {"ac": 1, "persona": "p", "status": "PASS", "observed": "NOT TESTABLE: x"},
                        {"ac": 2, "persona": "p", "status": "PASS", "observed": "ok"},
                    ]
                ),
                "receipt check AC1 is NOT TESTABLE",
            ),
            (
                verdict_entry(checks=[{"ac": 1, "persona": "p", "status": "PASS"}]),
                "receipt AC2 has no check",
            ),
            (verdict_entry(not_proven=" "), "the entry has no not_proven line"),
            (
                verdict_entry(oracles={"receipt": [], "ci": [], "walk": []}, checks=[]),
                "the entry names no oracle",
            ),
        ],
    )
    def test_a_verdict_entry_that_proves_nothing_is_refused(self, crewed, entry, message):
        with_row(crewed, DONE_KEY, "in_review")
        before_rows = transitions(crewed)
        adapter = ticket_adapter.FakeAdapter()
        with pytest.raises(board.BoardError) as refused:
            done_in_process(crewed, adapter, entry)
        assert f"board.py move {DONE_KEY} done: refused: {message}" in str(refused.value)
        assert transitions(crewed) == before_rows and adapter.calls == []

    def test_a_comment_file_moves_via_comment_and_carries_its_text(self, crewed, capsys):
        with_jira(crewed)
        with_row(crewed, DONE_KEY, "in_review")
        text = "Walked Settings as paid-user.\nNot proven: the small screen"
        assert (
            act(crewed, "move", DONE_KEY, "done", "--comment-file", comment_file(crewed, text))
            == 0
        )
        out = capsys.readouterr().out
        row = transitions(crewed)[-1]
        assert {k: row[k] for k in ("key", "from", "to", "via", "ticket")} == {
            "key": DONE_KEY,
            "from": "in_review",
            "to": "done",
            "via": "comment",
            "ticket": "carried",
        }
        assert carry_of(out) == [
            {"op": "transition", "key": DONE_KEY, "status": "Done"},
            {"op": "comment", "key": DONE_KEY, "text": text},
        ]

    def test_a_green_entry_moves_via_receipt_with_the_generated_comment(self, crewed):
        with_row(crewed, DONE_KEY, "in_review")
        row, ops, sample = done_in_process(
            crewed, ticket_adapter.SessionTransport(), verdict_entry()
        )
        assert list(row) == ["key", "from", "to", "via", "rc", "ts", "by", "ticket"]
        assert (row["via"], row["rc"], row["ticket"]) == ("receipt", "v1.4.0-rc.2", "carried")
        assert transitions(crewed)[-1] == row and sample is None
        assert [op.op for op in ops] == ["transition", "comment"]
        assert ops[1].value.splitlines() == [
            "Accepted by the receipts job v1.4.0-rc.2 "
            "(https://example.org/acme/app/actions/runs/4242)",
            "Oracle: receipt AC1, AC2 · ci AC3 (tests/test_export.py::test_export_csv)",
            "Persona: free-user",
            "Observed: AC1 PASS — 200 with a CSV of 3 rows",
            "Observed: AC2 PASS — 429 after the 6th export",
            "Not proven: the export on a native device",
        ]

    def test_sample_every_nth(self, crewed):
        set_sample(crewed, 5, keeper="tess")
        state = board.StateDir(crewed / "board.json")
        samples = []
        for i in range(1, 7):
            key = f"PROJ-{10 + i}"
            with_row(crewed, key, "in_review")
            if i == 3:  # a comment move between them never counts
                with_row(crewed, "PROJ-99", "in_review")
                path = comment_file(crewed, "Not proven: the device")
                board.move_done(
                    state,
                    "PROJ-99",
                    board.load_crew(),
                    NOW,
                    ticket_adapter.FakeAdapter(),
                    comment_file=path,
                )
            entry = verdict_entry(key=DONE_KEY)
            entry["key"] = key
            _row, _ops, sample = done_in_process(
                crewed, ticket_adapter.FakeAdapter(), entry, key=key
            )
            samples.append(sample)
        assert samples == [None, None, None, None, "sample: PROJ-15 → tess", None]
        [item] = news_of(crewed, "sample")
        assert item == {
            "id": "S1",
            "kind": "sample",
            "title": "Sample PROJ-15: accepted by the receipts job, tess checks it post hoc",
            "ts": "2026-11-03T10:00:00Z",
        }

    def test_the_keeper_defaults_to_the_acceptance_role(self, crewed):
        set_sample(crewed, 1)
        with_row(crewed, DONE_KEY, "in_review")
        _row, _ops, sample = done_in_process(crewed, ticket_adapter.FakeAdapter(), verdict_entry())
        assert sample == f"sample: {DONE_KEY} → tess"

    @pytest.mark.parametrize(
        "done_sample, lens_sample, expected", [(None, 1, None), (1, None, "x")]
    )
    def test_the_done_sample_reads_its_own_key_not_the_lens_one(
        self, crewed, done_sample, lens_sample, expected
    ):
        set_sample(crewed, done_sample, lens_sample=lens_sample)
        with_row(crewed, DONE_KEY, "in_review")
        _row, _ops, sample = done_in_process(crewed, ticket_adapter.FakeAdapter(), verdict_entry())
        assert sample == (expected and f"sample: {DONE_KEY} → tess")

    def test_the_done_sample_defaults_to_every_fifth(self):
        assert board.crew_mod.DEFAULTS["acceptance"]["done_sample"] == 5

    def test_sample_null_writes_none(self, crewed):
        set_sample(crewed, None)
        with_row(crewed, DONE_KEY, "in_review")
        _row, _ops, sample = done_in_process(crewed, ticket_adapter.FakeAdapter(), verdict_entry())
        assert sample is None and news_of(crewed, "sample") == []


# ---------------------------------------------------------------------------------------------
# the flow verbs: log correction, blocked, ask --urgent, the waits log

WORKER = "proj-12-build"
BLOCKED_ROW = {
    "sessionId": "sid-w",
    "name": WORKER,
    "status": "idle",
    "state": "blocked",
    "waitingFor": "permission prompt",
    "pid": 4242,
}


def bind_flow(state_dir, **flow):
    path = state_dir / "work" / ".weside" / "crew.json"
    crew = json.loads(path.read_text(encoding="utf-8"))
    crew["flow"] = {"log_dir": str(state_dir / "flow"), **flow}
    path.write_text(json.dumps(crew), encoding="utf-8")


def agents(state_dir, *rows):
    base = [{"sessionId": "sid-12", "name": "lead-12", "status": "busy"}]
    (state_dir / "agents.json").write_text(json.dumps(base + list(rows)), encoding="utf-8")


def flow_lines(state_dir):
    return (
        [
            json.loads(x)
            for p in sorted((state_dir / "flow").glob("*.jsonl"))
            for x in p.read_text(encoding="utf-8").splitlines()
        ]
        if (state_dir / "flow").exists()
        else []
    )


def waits(state_dir):
    return jsonl(state_dir / "board-waits.jsonl")


class TestLogCorrection:
    def test_the_coordinator_writes_one_correction_line(self, crewed, monkeypatch, capsys):
        bind_flow(crewed)
        pin(monkeypatch, "otto")
        before = (crewed / "board.json").read_bytes()
        assert go(crewed, "log", "correction", "lead-12", "scope") == 0
        [line] = flow_lines(crewed)
        assert line == {
            "type": "correction",
            "ts": "2026-11-03T10:00:00Z",
            "session": "lead-12",
            "kind": "scope",
            "by": "otto",
        }
        assert (crewed / "flow" / "sampler-2026-11-03.jsonl").exists()  # Berlin day
        assert json.loads(capsys.readouterr().out) == line
        assert (crewed / "board.json").read_bytes() == before

    def test_any_other_role_is_refused_and_nothing_written(self, crewed, monkeypatch, capsys):
        bind_flow(crewed)
        pin(monkeypatch, "ada")
        assert go(crewed, "log", "correction", "lead-12", "scope") == 1
        assert (
            "board.py log correction: only the coordinator records a correction"
            in capsys.readouterr().err
        )
        assert flow_lines(crewed) == []

    @pytest.mark.parametrize("kind", ["Scope", "two words", "scope!", "", "1x"])
    def test_a_kind_that_is_no_lower_case_token_is_refused(
        self, crewed, monkeypatch, capsys, kind
    ):
        bind_flow(crewed)
        pin(monkeypatch, "otto")
        assert go(crewed, "log", "correction", "lead-12", kind) == 1
        assert f"kind {kind!r} is no lower-case token" in capsys.readouterr().err
        assert flow_lines(crewed) == []

    def test_an_unbound_crew_is_refused_naming_the_key(self, crewed, monkeypatch, capsys):
        pin(monkeypatch, "otto")
        assert go(crewed, "log", "correction", "lead-12", "scope") == 1
        assert (
            "board.py log correction: flow.log_dir is unset in the crew" in capsys.readouterr().err
        )


class TestBlocked:
    def test_a_permission_prompt_marks_the_line_waiting_on_human(self, crewed):
        agents(crewed, BLOCKED_ROW)
        before = board_of(crewed)
        argv = [
            "blocked",
            WORKER,
            "--kind",
            "permission",
            "--starter",
            "lead-12",
            "--key",
            "PROJ-12",
        ]
        assert go(crewed, *argv, "--command", "x" * 300) == 0
        after = board_of(crewed)
        line = line_of(crewed, WORKER)
        assert line == {
            "name": WORKER,
            "session_id": "sid-w",
            "waiting_on": "human",
            "since": "2026-11-03T10:00Z",
            "sla_due": "2026-11-03T14:00Z",
            "updated_at": "2026-11-03T10:00Z",
            "blocked": {
                "kind": "permission",
                "starter": "lead-12",
                "starter_session_id": "sid-12",
                "key": "PROJ-12",
                "since": "2026-11-03T10:00:00Z",
                "waiting_for": "permission prompt",
                "command": "x" * 200,
            },
        }
        assert after["sessions"][:2] == before["sessions"]  # no other line touched
        assert {k: after[k] for k in after if k not in ("sessions", "updated")} == {
            k: before[k] for k in before if k not in ("sessions", "updated")
        }

    def test_an_existing_line_gains_only_the_wait_fields(self, crewed):
        agents(crewed, {**BLOCKED_ROW, "name": "other", "sessionId": "sid-o"})
        old = line_of(crewed, "other")
        assert go(crewed, "blocked", "other", "--kind", "permission") == 0
        new = line_of(crewed, "other")
        assert set(new) - set(old) == {"blocked", "waiting_on", "sla_due", "updated_at"}
        assert {
            k: v
            for k, v in new.items()
            if k not in ("blocked", "waiting_on", "since", "sla_due", "updated_at")
        } == {k: v for k, v in old.items() if k not in ("since", "updated_at")}

    @pytest.mark.parametrize(
        "row, kind, message",
        [
            (
                {**BLOCKED_ROW, "state": "working", "waitingFor": None},
                "permission",
                f"board.py blocked: {WORKER} is not blocked on a permission prompt right now",
            ),
            (
                {**BLOCKED_ROW, "status": "busy", "state": "working"},
                "chat",
                f"board.py blocked: {WORKER} is not idle right now",
            ),
            (None, "permission", f"board.py blocked: {WORKER} is not running"),
        ],
    )
    def test_it_refuses_unless_the_session_is_so_right_now(
        self, crewed, capsys, row, kind, message
    ):
        agents(crewed, *([row] if row else []))
        before = (crewed / "board.json").read_bytes()
        extra = ["--waiting-on", "product"] if kind == "chat" else []
        assert go(crewed, "blocked", WORKER, "--kind", kind, *extra) == 1
        assert message in capsys.readouterr().err
        assert (crewed / "board.json").read_bytes() == before

    @pytest.mark.parametrize(
        "kind, waiting_on, message",
        [
            ("chat", None, "board.py blocked: --kind chat needs --waiting-on <role key or human>"),
            ("chat", "legal", "board.py blocked: waiting_on 'legal' is no role key"),
            ("permission", "product", "board.py blocked: a permission prompt waits on human"),
        ],
    )
    def test_waiting_on_stays_a_role_key_or_human(self, crewed, capsys, kind, waiting_on, message):
        agents(crewed, {**BLOCKED_ROW, "state": "blocked" if kind == "permission" else "idle"})
        extra = ["--waiting-on", waiting_on] if waiting_on else []
        assert go(crewed, "blocked", WORKER, "--kind", kind, *extra) == 1
        assert message in capsys.readouterr().err
        assert WORKER not in [s["name"] for s in board_of(crewed)["sessions"]]

    def test_the_same_wait_again_writes_nothing(self, crewed, capsys):
        agents(crewed, BLOCKED_ROW)
        go(crewed, "blocked", WORKER, "--kind", "permission", "--command", "make deploy")
        before = (crewed / "board.json").read_bytes()
        capsys.readouterr()
        later = datetime(2026, 11, 3, 10, 1, tzinfo=timezone.utc)
        assert (
            go(
                crewed,
                "blocked",
                WORKER,
                "--kind",
                "permission",
                "--command",
                "make deploy",
                now=later,
            )
            == 0
        )
        assert capsys.readouterr().out.strip() == f"board.py blocked: {WORKER} unchanged"
        assert (crewed / "board.json").read_bytes() == before

    def test_a_chat_wait_moves_from_the_starter_to_human_keeping_its_start(self, crewed):
        agents(crewed, {**BLOCKED_ROW, "state": "idle", "waitingFor": None})
        go(
            crewed,
            "blocked",
            WORKER,
            "--kind",
            "chat",
            "--waiting-on",
            "coordinator",
            "--starter",
            "lead-12",
            "--key",
            "PROJ-12",
        )
        later = datetime(2026, 11, 3, 10, 31, tzinfo=timezone.utc)
        go(
            crewed,
            "blocked",
            WORKER,
            "--kind",
            "chat",
            "--waiting-on",
            "human",
            "--starter",
            "lead-12",
            now=later,
        )
        line = line_of(crewed, WORKER)
        assert (line["waiting_on"], line["since"]) == ("human", "2026-11-03T10:31Z")
        assert line["blocked"]["since"] == "2026-11-03T10:00:00Z"
        assert waits(crewed) == [
            {
                "key": "PROJ-12",
                "session": WORKER,
                "waiting_on": "coordinator",
                "since": "2026-11-03T10:00Z",
                "ended": "2026-11-03T10:31:00Z",
                "duration_s": 1860,
            }
        ]

    def test_clear_removes_the_wait_once_and_logs_it(self, crewed, capsys):
        agents(crewed, BLOCKED_ROW)
        go(crewed, "blocked", WORKER, "--kind", "permission", "--key", "PROJ-12")
        agents(crewed)  # the worker is gone
        later = datetime(2026, 11, 3, 10, 5, tzinfo=timezone.utc)
        capsys.readouterr()
        assert go(crewed, "blocked", WORKER, "--clear", now=later) == 0
        out = json.loads(capsys.readouterr().out)
        assert out == {
            "cleared": WORKER,
            "kind": "permission",
            "key": "PROJ-12",
            "since": "2026-11-03T10:00:00Z",
            "duration_s": 300,
            "obsolete": [],
        }
        assert not {"blocked", "waiting_on", "since", "sla_due"} & set(line_of(crewed, WORKER))
        assert [(w["key"], w["waiting_on"], w["duration_s"]) for w in waits(crewed)] == [
            ("PROJ-12", "human", 300)
        ]
        assert go(crewed, "blocked", WORKER, "--clear", now=later) == 0
        assert (
            capsys.readouterr().out.strip()
            == f"board.py blocked: {WORKER} carries no wait to clear"
        )
        assert len(waits(crewed)) == 1

    def test_clear_refuses_while_the_prompt_still_stands(self, crewed, capsys):
        agents(crewed, BLOCKED_ROW)
        go(crewed, "blocked", WORKER, "--kind", "permission")
        before = (crewed / "board.json").read_bytes()
        assert go(crewed, "blocked", WORKER, "--clear") == 1
        assert (
            f"board.py blocked: {WORKER} is still blocked on a permission prompt"
            in capsys.readouterr().err
        )
        assert (crewed / "board.json").read_bytes() == before

    def test_clear_marks_the_prompts_question_obsolete_never_deletes_it(self, crewed, capsys):
        agents(crewed, BLOCKED_ROW)
        go(crewed, "blocked", WORKER, "--kind", "permission")
        answer_with(crewed, CLEAR)
        go(crewed, *ask_argv(**{"--session": WORKER, "--cause": "access-click"}))
        go(crewed, *ask_argv(**{"--session": WORKER, "--cause": "info"}))
        agents(crewed, {**BLOCKED_ROW, "state": "working", "waitingFor": None})
        capsys.readouterr()
        later = datetime(2026, 11, 3, 10, 7, tzinfo=timezone.utc)
        assert go(crewed, "blocked", WORKER, "--clear", now=later) == 0
        assert json.loads(capsys.readouterr().out)["obsolete"] == ["Q8"]
        queue = {q["id"]: q for q in board_of(crewed)["owner_queue"]}
        assert sorted(queue) == ["Q7", "Q8", "Q9"]
        assert queue["Q8"]["obsolete"] == "prompt resolved at 11:07"  # Berlin
        assert "obsolete" not in queue["Q9"] and "obsolete" not in queue["Q7"]

    def test_the_obsolete_reason_speaks_the_crews_label(self, crewed):
        path = crewed / "work" / ".weside" / "crew.json"
        crew = json.loads(path.read_text(encoding="utf-8"))
        crew["labels"]["prompt_resolved"] = "Prompt erledigt um"
        path.write_text(json.dumps(crew), encoding="utf-8")
        agents(crewed, BLOCKED_ROW)
        go(crewed, "blocked", WORKER, "--kind", "permission")
        answer_with(crewed, CLEAR)
        go(crewed, *ask_argv(**{"--session": WORKER, "--cause": "access-click"}))
        agents(crewed)
        go(crewed, "blocked", WORKER, "--clear")
        assert board_of(crewed)["owner_queue"][-1]["obsolete"] == "Prompt erledigt um 11:00"

    def test_a_key_outside_naming_key_is_refused(self, crewed, capsys):
        agents(crewed, BLOCKED_ROW)
        assert go(crewed, "blocked", WORKER, "--kind", "permission", "--key", "proj-12") == 1
        assert (
            "board.py blocked: --key 'proj-12' does not match naming.key"
            in capsys.readouterr().err
        )
        assert WORKER not in [s["name"] for s in board_of(crewed)["sessions"]]

    def test_a_chat_wait_clears_without_asking_claude(self, crewed, monkeypatch):
        agents(crewed, {**BLOCKED_ROW, "state": "idle", "waitingFor": None})
        go(crewed, "blocked", WORKER, "--kind", "chat", "--waiting-on", "coordinator")
        monkeypatch.setenv("FAKE_AGENTS_EXIT", "3")
        assert go(crewed, "blocked", WORKER, "--clear") == 0
        assert "blocked" not in line_of(crewed, WORKER)

    def test_clear_asks_claude_agents_outside_the_board_lock(self, crewed, monkeypatch, capsys):
        agents(crewed, BLOCKED_ROW)
        go(crewed, "blocked", WORKER, "--kind", "permission")
        lock = crewed / "board.json.lock"
        calls = []

        def probe(fail):
            def rows():
                with open(lock, "w") as other:
                    try:
                        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        calls.append("free")
                        fcntl.flock(other, fcntl.LOCK_UN)
                    except BlockingIOError:
                        calls.append("held")
                if fail:
                    raise board.BoardError("board.py blocked: claude agents --json timed out")
                return []

            return rows

        monkeypatch.setattr(board, "_agent_rows", probe(fail=True))
        before = (crewed / "board.json").read_bytes()
        assert go(crewed, "blocked", WORKER, "--clear") == 1
        assert "timed out" in capsys.readouterr().err
        assert (crewed / "board.json").read_bytes() == before
        monkeypatch.setattr(board, "_agent_rows", probe(fail=False))
        assert go(crewed, "blocked", WORKER, "--clear") == 0
        assert calls == ["free", "free"]
        assert "blocked" not in line_of(crewed, WORKER)

    def test_set_by_the_session_itself_ends_the_blocked_mark(self, crewed, monkeypatch):
        agents(crewed, {**BLOCKED_ROW, "sessionId": "sid-12", "name": "lead-12"})
        go(crewed, "blocked", "lead-12", "--kind", "permission")
        pin(monkeypatch, "")
        assert go(crewed, "set", "waiting_on=architecture") == 0
        line = line_of(crewed, "lead-12")
        assert line["waiting_on"] == "architecture" and "blocked" not in line
        assert go(crewed, "blocked", "lead-12", "--clear") == 0  # nothing left to clear
        assert line_of(crewed, "lead-12")["waiting_on"] == "architecture"

    def test_without_the_verb_argparse_refuses(self):
        # the red arm of AC 13 against a board.py without `blocked`
        assert "blocked" in board.parser()._subparsers._group_actions[0].choices


class TestUrgent:
    def test_ask_urgent_marks_the_item_and_the_log(self, crewless):
        answer_with(crewless, CLEAR)
        assert go(crewless, *ask_argv(), "--urgent") == 0
        assert board_of(crewless)["owner_queue"][-1]["urgent"] is True
        assert jsonl(crewless / "board-questions.jsonl")[-1]["urgent"] is True

    def test_a_plain_ask_carries_no_urgent_field(self, crewless):
        answer_with(crewless, CLEAR)
        go(crewless, *ask_argv())
        assert "urgent" not in board_of(crewless)["owner_queue"][-1]

    def test_bundle_lists_urgent_first_oldest_first_within(self, crewed, monkeypatch):
        queue = [
            {"id": "Q1", "since": "2026-10-30", "ts": "2026-10-30T09:00:00Z"},
            {"id": "Q2", "since": "2026-11-02", "ts": "2026-11-02T09:00:00Z", "urgent": True},
            {"id": "Q3", "since": "2026-11-01", "ts": "2026-11-01T09:00:00Z", "urgent": True},
            {
                "id": "Q4",
                "since": "2026-10-31",
                "ts": "2026-10-31T09:00:00Z",
                "obsolete": "prompt resolved at 09:10",
            },
        ]
        board.StateDir(crewed / "board.json").write_board(lambda b: b.update(owner_queue=queue))
        pin(monkeypatch, "otto")
        assert go(crewed, "bundle") == 0
        body = board_of(crewed)["news"][-1]["body"].splitlines()
        assert body == [
            "open: Q3 (urgent), Q2 (urgent), Q1",
            "obsolete: Q4 (prompt resolved at 09:10)",
        ]


class TestWaitsLog:
    def test_set_logs_a_wait_when_it_ends_or_changes(self, crewless):
        go(crewless, "set", "waiting_on=architecture")
        assert waits(crewless) == []
        go(
            crewless,
            "set",
            "waiting_on=architecture",
            now=datetime(2026, 11, 3, 10, 20, tzinfo=timezone.utc),
        )
        assert waits(crewless) == []  # the same wait goes on
        go(
            crewless,
            "set",
            "waiting_on=product",
            now=datetime(2026, 11, 3, 10, 30, tzinfo=timezone.utc),
        )
        go(crewless, "set", "waiting_on=", now=datetime(2026, 11, 3, 11, 0, tzinfo=timezone.utc))
        assert waits(crewless) == [
            {
                "key": None,
                "session": "lead-12",
                "waiting_on": "architecture",
                "since": "2026-11-03T10:00Z",
                "ended": "2026-11-03T10:30:00Z",
                "duration_s": 1800,
            },
            {
                "key": None,
                "session": "lead-12",
                "waiting_on": "product",
                "since": "2026-11-03T10:30Z",
                "ended": "2026-11-03T11:00:00Z",
                "duration_s": 1800,
            },
        ]

    def test_the_key_comes_from_the_lines_keys(self, crewless):
        board.StateDir(crewless / "board.json").write_board(
            lambda b: b["sessions"][0].update(
                keys=["PROJ-12"], waiting_on="human", since="2026-11-03T09:00Z"
            )
        )
        go(crewless, "set", "waiting_on=")
        assert [(w["key"], w["duration_s"]) for w in waits(crewless)] == [("PROJ-12", 3600)]

    def test_a_failed_board_write_logs_no_wait(self, crewless, monkeypatch):
        go(crewless, "set", "waiting_on=architecture")

        def broken(*_a):
            raise OSError("disk full")

        monkeypatch.setattr(board.os, "replace", broken)
        with pytest.raises(OSError):
            go(crewless, "set", "waiting_on=")
        assert waits(crewless) == []


def test_a_star_freeze_without_a_repo_here_records_what_it_could_not_disarm(tmp_path):
    flag = board_freeze.freeze(
        tmp_path / "freeze.json", "r", ["*"], "k", gh=lambda _args: None, disarm=[]
    )
    assert flag["repos"] == ["*"]
    assert flag["not_disarmed"] == [
        {"repo": "*", "why": "no repo here for a `merge-freeze` issue"},
        {"repo": "*", "why": "no repo here to disarm; armed PRs elsewhere still auto-merge"},
    ]


def answered(state_dir, qid, kind, ts, session="coord"):
    with open(state_dir / "board-answers.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": qid, "answer": kind, "ts": ts, "session": session}) + "\n")


def delivered_row(state_dir, qid, answer_ts, ts, role="coordinator", ok=True):
    row = {"id": qid, "answer_ts": answer_ts, "to": "coord", "role": role}
    row.update({"click_ts": answer_ts, "ts": ts, "delivered": ok})
    with open(state_dir / "board-deliveries.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


EPOCH = {"epoch": "2026-11-01T00:00:00.000Z"}


def epoch_row(state_dir):
    with open(state_dir / "board-deliveries.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(EPOCH) + "\n")


class TestPrune:
    """A closed question leaves `owner_queue` once its asker is carried; handled news leave `news`."""

    def test_an_accept_carried_to_the_asker_leaves_the_queue(self, crewless, capsys):
        epoch_row(crewless)
        answered(crewless, "Q7", "accept", "2026-11-03T09:59:00.000Z")
        delivered_row(crewless, "Q7", "2026-11-03T09:59:00.000Z", "2026-11-03T09:59:03.000Z")
        go(crewless, "prune")
        assert [q["id"] for q in board_of(crewless)["owner_queue"]] == ["Q7"]  # coordinator only
        capsys.readouterr()
        delivered_row(
            crewless, "Q7", "2026-11-03T09:59:00.000Z", "2026-11-03T09:59:04.000Z", role="asker"
        )
        assert go(crewless, "prune") == 0
        assert board_of(crewless)["owner_queue"] == []
        assert capsys.readouterr().out.strip() == "pruned: Q7"
        line = jsonl(crewless / "board-questions.jsonl")[-1]
        assert {k: line[k] for k in ("id", "outcome", "field", "reason", "answer")} == {
            "id": "Q7",
            "outcome": "pruned",
            "field": "owner_queue",
            "reason": "answered",
            "answer": "accept",
        }

    def test_a_refused_asker_counts_once_the_route_line_is_delivered(self, crewless):
        epoch_row(crewless)
        ts = "2026-11-03T09:59:00.000Z"
        answered(crewless, "Q7", "deny", ts)
        delivered_row(crewless, "Q7", ts, "2026-11-03T09:59:04.000Z", role="asker", ok=False)
        go(crewless, "prune")
        assert [q["id"] for q in board_of(crewless)["owner_queue"]] == ["Q7"]
        delivered_row(crewless, "Q7", ts, "2026-11-03T09:59:09.000Z", role="route")
        go(crewless, "prune")
        assert board_of(crewless)["owner_queue"] == []

    def test_an_undelivered_close_stays_a_day_then_goes(self, crewless):
        """An answered question never stays for good: undelivered, it waits PRUNE_AFTER_H."""
        epoch_row(crewless)
        answered(crewless, "Q7", "accept", "2026-11-03T08:00:00.000Z")
        go(crewless, "prune")
        assert [q["id"] for q in board_of(crewless)["owner_queue"]] == ["Q7"]
        go(crewless, "prune", now=NOW + timedelta(hours=board.PRUNE_AFTER_H))
        assert board_of(crewless)["owner_queue"] == []

    def test_a_duplicate_answer_takes_the_question_off(self, crewless):
        epoch_row(crewless)
        answered(crewless, "Q7", "accept", "2026-11-03T09:59:00.000Z")
        assert [q["id"] for q in board_of(crewless)["owner_queue"]] == ["Q7"]
        assert go(crewless, "answer", "Q7", "deny", "--session", "foxy", "--via", "chat") == 0
        go(crewless, "prune")
        assert board_of(crewless)["owner_queue"] == []

    def test_an_earlier_discuss_still_owed_to_the_asker_keeps_it(self, crewless):
        epoch_row(crewless)
        answered(crewless, "Q7", "discuss", "2026-11-03T09:00:00.000Z")
        answered(crewless, "Q7", "accept", "2026-11-03T09:59:00.000Z")
        delivered_row(
            crewless, "Q7", "2026-11-03T09:59:00.000Z", "2026-11-03T09:59:04.000Z", role="asker"
        )
        go(crewless, "prune")
        assert [q["id"] for q in board_of(crewless)["owner_queue"]] == ["Q7"]

    def test_leftovers_older_than_the_epoch_go_on_any_write(self, crewless):
        epoch_row(crewless)
        answered(crewless, "Q7", "accept", "2026-10-30T08:00:00.000Z")
        assert go(crewless, "set", "now=phase 3") == 0
        assert board_of(crewless)["owner_queue"] == []

    def test_an_answer_from_the_askers_own_session_owes_it_nothing(self, crewless):
        epoch_row(crewless)
        answered(crewless, "Q7", "accept", "2026-11-03T09:59:00.000Z", session="asker")
        go(crewless, "prune")
        assert board_of(crewless)["owner_queue"] == []

    def test_discuss_and_update_keep_the_question(self, crewless):
        answered(crewless, "Q7", "discuss", "2026-11-01T09:00:00.000Z")
        answered(crewless, "Q7", "update", "2026-11-01T10:00:00.000Z")
        go(crewless, "prune")
        assert [q["id"] for q in board_of(crewless)["owner_queue"]] == ["Q7"]

    def test_read_news_and_expired_returns_and_bundles_go(self, crewless):
        def seed(b):
            b["news"] = [
                {"id": "D3", "kind": "decision", "title": "read it"},
                {"id": "R1", "kind": "returned", "title": "old", "ts": "2026-11-02T09:00:00Z"},
                {"id": "R2", "kind": "returned", "title": "fresh", "ts": "2026-11-03T09:00:00Z"},
                {
                    "id": "B-2026-11-01",
                    "kind": "todo",
                    "title": "old",
                    "ts": "2026-11-01T19:00:00Z",
                },
                {"id": "N5", "kind": "gate", "title": "unread", "ts": "2026-10-01"},
                {"id": "E2", "kind": "escalation", "title": "open", "ts": "2026-10-01T09:00:00Z"},
            ]

        board.StateDir(crewless / "board.json", now=NOW).write_board(seed)
        answered(crewless, "D3", "read", "2026-11-03T09:59:00.000Z")
        answered(crewless, "E2", "read", "2026-11-01T09:00:00.000Z")
        go(crewless, "prune")
        assert [n["id"] for n in board_of(crewless)["news"]] == ["R2", "N5", "E2"]

    def test_a_pruned_id_is_not_handed_out_again(self, crewless):
        board.StateDir(crewless / "board.json").write_board(
            lambda b: b["news"].append(
                {"id": "R4", "kind": "returned", "title": "x", "ts": "2026-11-01T09:00:00Z"}
            )
        )
        go(crewless, "prune")
        state = board.StateDir(crewless / "board.json")
        assert state.next_id("R", board_of(crewless)) == "R5"

    def test_nothing_to_prune_leaves_the_file_byte_equal(self, crewless, capsys):
        before = (crewless / "board.json").read_bytes()
        assert go(crewless, "prune") == 0
        assert (crewless / "board.json").read_bytes() == before
        assert capsys.readouterr().out.strip() == "pruned: none"


class TestSessionStamp:
    def test_set_stamps_updated_at_on_the_line(self, crewless):
        go(crewless, "set", "now=phase 3")
        assert line_of(crewless, "lead-12")["updated_at"] == "2026-11-03T10:00Z"
        assert line_of(crewless, "other").get("updated_at") is None

    def test_blocked_and_clear_stamp_updated_at(self, crewed):
        # Review #192: a line the sampler rewrites must not read as stale from an old `set`.
        agents(crewed, {**BLOCKED_ROW, "name": "other", "sessionId": "sid-o"})
        assert go(crewed, "blocked", "other", "--kind", "permission") == 0
        assert line_of(crewed, "other")["updated_at"] == "2026-11-03T10:00Z"


def test_a_coordinator_write_stamps_the_boards_updated_and_another_does_not(tmp_path):
    """board.ts lapses an Update mark and ages the header on `updated` once the orchestrator
    rewrote the board: its writes move it, a worker's status ping does not (Claude Review #197)."""
    path = tmp_path / "board.json"
    path.write_text(json.dumps({"updated": "2000-01-01T00:00:00+00:00", "updated_by": "Lea"}))
    board.StateDir(path).write_board(lambda b: b.setdefault("questions", []))
    assert json.loads(path.read_text())["updated"] == "2000-01-01T00:00:00+00:00"
    board.StateDir(path, stamps_updated=True).write_board(lambda b: b.setdefault("news", []))
    data = json.loads(path.read_text())
    assert data["updated"][:4] >= "2026" and data["updated_by"] == "Lea"


def test_main_stamps_updated_only_for_the_coordinator(crewed, monkeypatch):
    before = board_of(crewed)["updated"]
    assert go(crewed, "set", "now=x") == 0
    assert board_of(crewed)["updated"] == before
    pin(monkeypatch, "otto")
    (crewed / "agents.json").write_text(json.dumps([{"sessionId": "sid-12", "name": "Otto"}]))
    assert go(crewed, "set", "now=y") == 0
    assert board_of(crewed)["updated"] != before


def test_a_transition_row_is_built_and_appended_under_the_board_lock(tmp_path):
    """Review 09.11.: `from` is read from the log under the same lock that appends the row."""
    import fcntl  # noqa: PLC0415

    state = board.StateDir(tmp_path / "board.json")
    held = []

    def build(last):
        fd = os.open(str(state.lock_path), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            held.append(False)
        except BlockingIOError:
            held.append(True)
        finally:
            os.close(fd)
        return {"key": "AC-1", "from": last.get("to") if last else None, "to": "selected"}

    state.record_transition("AC-1", build)
    row = state.record_transition("AC-1", build)
    assert held == [True, True]
    assert row["from"] == "selected"


# Review 09.11. (/we:optimize § A): set topic/keys, ask --kind task/--source/--owner, duplicates.


def test_set_writes_topic_and_keys_and_clears_them(crewless):
    assert go(crewless, "set", "topic=Handoff", "keys=PROJ-12,PROJ-13") == 0
    line = line_of(crewless, "lead-12")
    assert line["topic"] == "Handoff" and line["keys"] == ["PROJ-12", "PROJ-13"]
    assert go(crewless, "set", "topic=", "keys=") == 0
    line = line_of(crewless, "lead-12")
    assert "topic" not in line and "keys" not in line


def test_ask_stamps_kind_source_and_owner_by_component(crewed, capsys):
    answer_with(crewed, CLEAR)
    argv = [
        *ask_argv(),
        "--kind",
        "task",
        "--source",
        "gh run view 41",
        "--component",
        "architecture",
    ]
    assert go(crewed, *argv) == 0
    item = board_of(crewed)["owner_queue"][-1]
    assert item["kind"] == "task" and item["source"] == "gh run view 41" and item["owner"] == "Vic"


def test_ask_owner_by_name_and_an_unknown_owner_is_refused(crewed, capsys):
    answer_with(crewed, CLEAR)
    assert go(crewed, *ask_argv(), "--owner", "ada") == 0
    assert board_of(crewed)["owner_queue"][-1]["owner"] == "Ada"
    assert go(crewed, *ask_argv(), "--owner", "nobody") == 1
    assert "--owner 'nobody' is no crew member" in capsys.readouterr().err


def test_a_second_question_on_an_open_key_warns_and_replace_takes_the_first_off(crewless, capsys):
    answer_with(crewless, CLEAR)
    assert go(crewless, *ask_argv()) == 0
    first = capsys.readouterr().out.strip().split()[-1]
    assert go(crewless, *ask_argv()) == 0
    out = capsys.readouterr()
    assert f"warning: {first} on PROJ-12 is still open" in out.err
    second = out.out.strip().split()[-1]
    assert go(crewless, *ask_argv(), "--replace", second) == 0
    out = capsys.readouterr()
    queue_ids = [q["id"] for q in board_of(crewless)["owner_queue"]]
    assert second not in queue_ids and first in queue_ids
    lines = jsonl(crewless / "board-questions.jsonl")
    assert {"id": second, "outcome": "replaced"}.items() <= next(
        x for x in lines if x.get("outcome") == "replaced"
    ).items()


def test_replace_of_an_unknown_id_is_refused(crewless, capsys):
    answer_with(crewless, CLEAR)
    assert go(crewless, *ask_argv(), "--replace", "Q999999") == 1
    assert "--replace Q999999: no open question with that id" in capsys.readouterr().err


def test_replace_of_a_question_on_another_key_is_refused(crewless, capsys):
    """Claude Review on #201: a mistyped id never drops an unrelated question."""
    answer_with(crewless, CLEAR)
    assert go(crewless, *ask_argv()) == 0
    first = capsys.readouterr().out.strip().split()[-1]
    assert go(crewless, *ask_argv(**{"--key": "PROJ-13"}), "--replace", first) == 1
    assert f"--replace {first}: that question is on 'PROJ-12', not 'PROJ-13'" in (
        capsys.readouterr().err
    )
    assert first in [q["id"] for q in board_of(crewless)["owner_queue"]]
