"""board.py: one class per verb on a shared state_dir (a temp board.json and its answers file)."""

from __future__ import annotations

import copy
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board  # noqa: E402

BOARD = {
    "updated_by": "coord",
    "owner_queue": [
        {"id": "Q1", "session": "asker", "ask": "Ship it?", "recommendation": "Ship on Monday"},
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

    def test_the_line_quotes_the_question_and_its_recommendation(self, state_dir):
        assert run(state_dir, "answer", "Q1", "accept", "--session", "c", "--via", "chat") == 0
        assert run(state_dir, "answer", "N1", "followup", "--session", "c", "--via", "chat") == 0
        q1, n1 = lines(state_dir)
        assert (q1["ask"], q1["recommendation"]) == ("Ship it?", "Ship on Monday")
        assert "ask" not in n1 and "recommendation" not in n1

    def test_a_news_id_is_known_too(self, state_dir):
        assert (
            run(state_dir, "answer", "N1", "followup", "--session", "coord", "--via", "chat") == 0
        )
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
            run(state_dir, "answer", "Q2", "followup", "--session", "coord", "--via", "chat") == 0
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
            "for i in range(300): s.append_answer('Q2', 'followup', sys.argv[3], via='chat', quote='x' * 200)"
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


def test_a_relative_crew_board_file_is_read_beside_the_crew_file(tmp_path, monkeypatch):
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
    assert board.default_board(work / "sub") == work / ".weside" / "state" / "board.json"


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
    "news": [{"id": "N2", "kind": "info", "title": "RC cut"}],
    "log": [{"id": "D3", "kind": "decision", "title": "hand-written"}],
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
            "session_id": "sid-12",
            "cwd": str(crewless / "work"),
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
            "cwd": str(crewless / "work"),
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
        "assignment, message, corrected",
        [
            ("waiting_on=legal", "waiting_on 'legal' is no role key", None),
            ("color=x", "field 'color' is not settable", None),
            ("keys=nope", "keys nope do not match the crew's naming.key", None),
            ("state=running", "state 'running' is not one of", None),
            ("waiting", "'waiting' is no <field>=<value>", None),
            # the three values the measured week refused most, each with the call it meant
            ("state=working", "state 'working' is not one of", "set now=x state=build"),
            ("state=refine", "state 'refine' is not one of", "set now=x state=active"),
            ("waiting_on=Hal", "waiting_on 'Hal' is no role key", "set now=x waiting_on=human"),
            ("waiting-on=human", "field 'waiting-on'", "set now=x waiting_on=human"),
        ],
    )
    def test_refusals_name_the_input_and_write_nothing(
        self, crewed, capsys, assignment, message, corrected
    ):
        before = (crewed / "board.json").read_bytes()
        assert go(crewed, "set", "now=x", assignment) == 1
        err = capsys.readouterr().err
        assert message in err
        assert (
            ("corrected call: board.py " + corrected in err)
            if corrected
            else ("corrected call" not in err)
        )
        assert (crewed / "board.json").read_bytes() == before

    def test_a_member_name_as_wait_names_the_role_it_holds(self, crewed, capsys):
        assert go(crewed, "set", "waiting_on=Otto (Q12)") == 1
        assert "corrected call: board.py set waiting_on=coordinator" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "argv, corrected",
        [
            (["set", "--now", "phase 3", "--state", "ci"], "set 'now=phase 3' state=ci"),
            (["answer", "Q1", "no", "--session", "a", "--via", "chat"], "answer Q1 deny"),
            (["answer", "Q1", "discuss", "--session", "a", "--via", "chat"], "answer Q1 followup"),
            (["answer", "Q1", "accept", "--session", "a", "--via", "board"], "--via chat"),
        ],
    )
    def test_a_flag_form_or_a_wrong_choice_prints_the_corrected_call(
        self, capsys, argv, corrected
    ):
        with pytest.raises(SystemExit):
            board.main(argv)
        err = capsys.readouterr().err
        assert f"corrected call: board.py {argv[0]}" in err and corrected in err

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


def qid_of(out):
    """The id of the one JSON object `ask` prints on stdout."""
    return json.loads(out)["id"]


def posted(qid):
    return json.dumps({"id": qid, "outcome": "posted"})


def answer_with(state_dir, answer):
    text = answer if isinstance(answer, str) else "Reading it cold.\n" + json.dumps(answer)
    (state_dir / "answer.txt").write_text(text, encoding="utf-8")


class TestAsk:
    @pytest.mark.parametrize("flag", [f for f in ASK if f != "--session"])
    @pytest.mark.parametrize("value", [None, "  "])
    def test_a_missing_or_blank_field_is_refused_before_the_reader(
        self, crewless, capsys, flag, value
    ):
        before = (crewless / "board.json").read_bytes()
        assert go(crewless, *ask_argv(**{flag: value})) == 1
        lines = capsys.readouterr().err.strip().splitlines()
        assert lines[0] == f"board.py ask: missing {flag}"
        # a missing key names the way out for a question without a story
        assert lines[1:] == ([board.NO_STORY_KEY] if flag == "--key" else [])
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
        err = capsys.readouterr().err
        assert message in err
        assert (board.NO_STORY_KEY in err) == (flag == "--key")
        assert not (crewless / "reader-calls.jsonl").exists()

    def test_a_clear_question_is_posted_with_the_next_id(self, crewless, capsys):
        (crewless / "board-answers.jsonl").write_text('{"id": "Q271", "answer": "accept"}\n')
        answer_with(crewless, CLEAR)
        # without --session the asker is this session's own name, as `set` finds it
        assert go(crewless, *ask_argv(**{"--session": None})) == 0
        assert capsys.readouterr().out.strip() == posted("Q272")
        item = board_of(crewless)["owner_queue"][-1]
        assert item == {
            "id": "Q272",
            "session": "lead-12",
            "asker_id": "sid-12",
            "answer_to": "asker",
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

    def test_show_prints_a_pane_answer_the_board_file_does_not_hold(self, crewless, capsys):
        """A pane click writes only the answers file; owner_queue keeps the item without an
        answer, so another session read it as open and repeated it (red arm: no verb read both)."""
        answer_with(crewless, CLEAR)
        assert go(crewless, *ask_argv()) == 0
        qid = qid_of(capsys.readouterr().out)
        assert go(crewless, "show", qid) == 0
        shown = json.loads(capsys.readouterr().out)
        assert (shown["id"], shown["status"], shown["answers"]) == (qid, "open", [])
        assert shown["ask"] == ASK["--ask"] and "reader" not in shown
        line = {"id": qid, "answer": "accept", "ts": "2026-11-03T10:50:00Z", "session": "pane"}
        (crewless / "board-answers.jsonl").write_text(json.dumps(line) + "\n")
        assert go(crewless, "show", qid) == 0
        shown = json.loads(capsys.readouterr().out)
        assert shown["status"] == "answered: accept" and shown["answers"] == [line]
        assert go(crewless, "show", "Q999") == 1
        assert "Q999 is in neither owner_queue nor the logs" in capsys.readouterr().err

    def test_show_prints_a_sessions_board_line_by_name(self, crewless, capsys):
        """A restarted master reads its own line with `show <session>`; red arm: "rust is in
        neither owner_queue nor the logs" although the line existed."""
        data = board_of(crewless)
        data["sessions"] = [{"name": "rust", "epic": "PROJ-7", "now": "building PROJ-8"}]
        (crewless / "board.json").write_text(json.dumps(data), encoding="utf-8")
        assert go(crewless, "show", "rust") == 0
        assert json.loads(capsys.readouterr().out)["now"] == "building PROJ-8"
        assert go(crewless, "show", "nobody") == 1
        assert "no session line carries that name" in capsys.readouterr().err

    def test_a_plan_slug_stands_for_a_key_before_the_ticket_exists(self, crewless, capsys):
        answer_with(crewless, CLEAR)
        assert go(crewless, *ask_argv(**{"--key": "onboarding-v2"})) == 0
        assert capsys.readouterr().out.strip() == posted(LIVE_NEXT_Q)
        assert board_of(crewless)["owner_queue"][-1]["key"] == "onboarding-v2"

    def test_withdraw_of_an_answered_and_pruned_question_names_its_state(self, crewless, capsys):
        """Red arm: the asker withdrew a question the owner had answered and a write had pruned
        a second earlier; `no open question` sent it hunting through the queue."""
        answer_with(crewless, CLEAR)
        assert go(crewless, *ask_argv()) == 0
        qid = qid_of(capsys.readouterr().out)
        line = {"id": qid, "answer": "accept", "ts": "2026-11-03T10:05:00Z", "session": "pane"}
        (crewless / "board-answers.jsonl").write_text(json.dumps(line) + "\n")
        assert go(crewless, "prune") == 0
        assert qid not in [q["id"] for q in board_of(crewless)["owner_queue"]]
        capsys.readouterr()
        assert go(crewless, "withdraw", qid, "--reason", "PR merged") == 0
        out = capsys.readouterr().out
        assert f"{qid}: nothing to withdraw, it is off the queue (answered: accept, pruned" in out
        assert go(crewless, "withdraw", "Q999") == 1
        assert "Q999 was never on" in capsys.readouterr().err

    def test_a_retry_with_the_same_text_returns_the_first_id(self, crewless, capsys):
        """Red arm: a retry after a success whose output a JSON parser could not read posted
        the same question twice."""
        answer_with(crewless, CLEAR)
        assert go(crewless, *ask_argv()) == 0
        first = json.loads(capsys.readouterr().out)
        assert first == {"id": LIVE_NEXT_Q, "outcome": "posted"}
        calls = (crewless / "reader-calls.jsonl").read_bytes()
        assert go(crewless, *ask_argv()) == 0
        out = capsys.readouterr()
        assert json.loads(out.out) == {"id": LIVE_NEXT_Q, "outcome": "repeat"}
        assert "nothing new was posted" in out.err
        assert (crewless / "reader-calls.jsonl").read_bytes() == calls
        assert [q["id"] for q in board_of(crewless)["owner_queue"]].count(LIVE_NEXT_Q) == 1
        # another recommendation is another question (here: a refused duplicate on the key)
        assert go(crewless, *ask_argv(**{"--recommendation": "No, Monday."})) == 1
        capsys.readouterr()
        # a re-ask after a withdraw posts anew, not a repeat of the withdrawn one
        assert go(crewless, "withdraw", LIVE_NEXT_Q, "--reason", "wrong key") == 0
        capsys.readouterr()
        assert go(crewless, *ask_argv()) == 0
        assert json.loads(capsys.readouterr().out)["outcome"] == "posted"

    def test_the_text_comes_from_a_file_or_stdin(self, crewless, capsys, monkeypatch):
        text = "May `migrate.py` run on prod tonight?"
        (crewless / "q.txt").write_text(text + "\n", encoding="utf-8")
        answer_with(crewless, CLEAR)
        assert (
            go(crewless, *ask_argv(**{"--ask": None}), "--text-file", str(crewless / "q.txt")) == 0
        )
        assert board_of(crewless)["owner_queue"][-1]["ask"] == text
        monkeypatch.setattr("sys.stdin", io.StringIO("Is `index.ts` ready?"))
        assert (
            go(crewless, *ask_argv(**{"--ask": None, "--key": "PROJ-13"}), "--text-file", "-") == 0
        )
        assert board_of(crewless)["owner_queue"][-1]["ask"] == "Is `index.ts` ready?"
        assert go(crewless, *ask_argv(), "--text-file", "-") == 2
        assert "--ask or --text-file, not both" in capsys.readouterr().err

    def test_a_return_of_shell_mangled_text_names_the_file_input(self, crewless, capsys):
        answer_with(crewless, {**CLEAR, "on_yes": ""})
        mangled = {"--ask": "May  run on prod tonight?"}  # `migrate.py` ran in the shell
        assert go(crewless, *ask_argv(**mangled)) == 1
        err = capsys.readouterr().err
        assert "shell-mangled" in err and "--text-file -" in err
        assert go(crewless, *ask_argv(**{"--ask": "May it run on prod tonight?"})) == 1
        assert "shell-mangled" not in capsys.readouterr().err

    def test_the_asker_starter_and_answer_to_are_stamped(self, crewless, capsys):
        work = crewless / "work"
        subprocess.run(["git", "init", "-q", str(work)], check=True)
        marker = {"name": "w-1", "starter": "lead-1"}
        (work / ".git" / "we-worker.json").write_text(json.dumps(marker))
        (work / ".weside").mkdir()
        (work / ".weside" / "config.json").write_text(
            json.dumps({"board": {"answer_to": "asker"}})
        )
        answer_with(crewless, CLEAR)
        assert go(crewless, *ask_argv()) == 0
        item = board_of(crewless)["owner_queue"][-1]
        assert (item["asker_id"], item.get("starter"), item["answer_to"]) == (
            "sid-12",
            "lead-1",
            "asker",
        )
        # a question asked for another session carries no id or starter of the caller
        assert go(crewless, *ask_argv(**{"--key": "PROJ-14", "--session": "other"})) == 0
        item = board_of(crewless)["owner_queue"][-1]
        assert "asker_id" not in item and "starter" not in item and item["answer_to"] == "asker"
        (work / ".weside" / "config.json").write_text(json.dumps({"board": {"answer_to": "me"}}))
        assert go(crewless, *ask_argv(**{"--key": "PROJ-13", "--ask": "Other?"})) == 0
        assert board_of(crewless)["owner_queue"][-1]["answer_to"] == "asker"
        assert "board.answer_to 'me'" in capsys.readouterr().err

    def test_answer_to_defaults_to_the_asker_and_coordinator_opts_out(self, crewless):
        """Flow first (Q954): without a value the answer goes to the asker; `coordinator` in the
        repo's config opts out. Red arm: the default `coordinator` stamped nothing here."""
        answer_with(crewless, CLEAR)
        assert go(crewless, *ask_argv()) == 0
        assert board_of(crewless)["owner_queue"][-1]["answer_to"] == "asker"
        work = crewless / "work"
        (work / ".weside").mkdir()
        (work / ".weside" / "config.json").write_text(
            json.dumps({"board": {"answer_to": "coordinator"}})
        )
        assert go(crewless, *ask_argv(**{"--key": "PROJ-14", "--ask": "Other?"})) == 0
        assert "answer_to" not in board_of(crewless)["owner_queue"][-1]


def test_the_crews_answer_to_beats_the_repo_config(crewed):
    """A companion asks the same way from any repo: the crew's `board.answer_to` wins."""
    (crewed / "work" / ".weside" / "config.json").write_text(
        json.dumps({"board": {"answer_to": "asker"}})
    )
    work = crewed / "work"
    assert "answer_to" not in board._asker_stamp(
        "x", crew={"board": {"answer_to": "coordinator"}}, cwd=work
    )
    assert (
        board._asker_stamp("x", crew={"board": {"answer_to": None}}, cwd=work)["answer_to"]
        == "asker"
    )
    (work / ".weside" / "config.json").write_text(
        json.dumps({"board": {"answer_to": "coordinator"}})
    )
    assert (
        board._asker_stamp("x", crew={"board": {"answer_to": "asker"}}, cwd=work)["answer_to"]
        == "asker"
    )


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
        assert capsys.readouterr().out.strip() == posted(LIVE_NEXT_Q)
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
        assert capsys.readouterr().out.strip() == posted(LIVE_NEXT_Q)
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
    """two crews, AC11: a writing verb refuses a board of another crew, and a crewless default write;
    a crewless session that names a board with `--board` writes it, stamped or not (the explicit
    file is the intent).

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

    def test_a_crewless_session_may_name_an_unstamped_board(self, crewless):
        assert go(crewless, "set", "state=build") == 0
        assert not (crewless / "crew.id").exists()

    def test_a_crewless_session_may_name_a_stamped_board(self, crewless):
        # Repro 20.11.: from a repo without a crew file, `--board <the crew's board> set` was
        # refused like the bare call; the explicit file is the intent, the stamp stays.
        (crewless / "crew.id").write_text("acme/first-crew\n")
        assert go(crewless, "set", "state=build") == 0
        assert (crewless / "crew.id").read_text() == "acme/first-crew\n"

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
        # The return is the asker's (exit, note, log line); the owner's news gets nothing.
        assert after["news"] == before["news"]
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

    def test_a_return_leaves_an_unrelated_note_and_writes_no_news(self, crewless, capsys):
        """Red arm: every return landed in the owner's news as `returned to <session>`,
        a line meant for the asker."""
        self.note_on_lead(crewless, "CI red on main")
        answer_with(crewless, {**CLEAR, "form": ["no recommendation"]})
        assert go(crewless, *ask_argv()) == 1
        after = board_of(crewless)
        assert line_of(crewless, "lead-12")["note"] == "CI red on main", "return overwrote a note"
        assert "returned to lead-12: no recommendation" in capsys.readouterr().err
        assert not any(i.get("kind") == "returned" for i in after["news"])
        [line] = jsonl(crewless / "board-questions.jsonl")
        assert line["outcome"] == "returned"

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
    def test_a_reader_that_cannot_run_posts_the_question_unread(
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
        assert go(crewless, *ask_argv()) == 0
        assert f"board.py ask: reader-error: {cause}; posted unread" in capsys.readouterr().err
        [line] = jsonl(crewless / "board-questions.jsonl")
        assert (line["outcome"], line["reader"]) == ("posted", {"error": cause})

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
        go(crewless, *ask_argv(**{"--ask": "Should checkout go live for everyone tonight?"}))
        assert capsys.readouterr().out.splitlines() == [posted("Q8"), posted("Q9")]


PR_URL = "https://github.com/o/r/pull/5"
HEAD_A = "a" * 40
HEAD_B = "b" * 40


@pytest.fixture
def merge_gh(crewless, monkeypatch):
    """The fake `gh` on PATH, answering `pr view` from gh.json (FAKE_BIN's `gh`)."""
    monkeypatch.setenv("FAKE_GH", str(crewless / "gh.json"))
    monkeypatch.setenv("FAKE_GH_LOG", str(crewless / "gh-calls.jsonl"))

    def answers(state, head=HEAD_A):
        pr = {
            "state": state,
            "url": PR_URL,
            "headRefName": "feat/PROJ-12-x",
            "headRefOid": head,
            "title": "t",
        }
        (crewless / "gh.json").write_text(
            json.dumps({PR_URL: {"pr": pr}, "5 -R o/r": {"pr": pr}}), encoding="utf-8"
        )

    answers("OPEN")
    return answers


@pytest.mark.usefixtures("merge_gh")
class TestOneWayGo:
    """One open question per one-way PR, and the human's yes as the skip of a Codex finding."""

    CODEX = (
        "--codex-finding",
        "https://github.com/o/r/pull/5#c1 retry loop",
        "--codex-reason",
        "the loop is capped at 3",
    )

    def one_way(self, *extra):
        return [
            *ask_argv(**{"--cause": "merge-go"}),
            "--pr",
            "o/r#5",
            "--one-way",
            "money",
            *extra,
        ]

    def test_a_new_head_replaces_the_open_question_under_supersede(
        self, crewless, merge_gh, capsys
    ):
        """Red arm: four questions for one PR stood on the board, one per head."""
        answer_with(crewless, CLEAR)
        assert go(crewless, *self.one_way()) == 0
        first = qid_of(capsys.readouterr().out)
        merge_gh("OPEN", head=HEAD_B)
        assert go(crewless, *self.one_way("--ask", "Merge the new head of #5 tonight?")) == 1
        assert f"{first} is the open one-way question on {PR_URL}" in capsys.readouterr().err
        assert (
            go(crewless, *self.one_way("--supersede", "--ask", "Merge the new head of #5?")) == 0
        )
        second = qid_of(capsys.readouterr().out)
        queue = [q for q in board_of(crewless)["owner_queue"] if q.get("pr_url") == PR_URL]
        assert [(q["id"], q["head"]) for q in queue] == [(second, HEAD_B)]
        old = [x for x in jsonl(crewless / "board-questions.jsonl") if x.get("id") == first][-1]
        assert (old["outcome"], old["by"]) == ("superseded", second)
        assert go(crewless, "show", first) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "superseded"

    @pytest.mark.parametrize(
        "extra, refusal",
        [
            (("--codex-finding", "x"), "needs both --codex-finding and --codex-reason"),
            (("--supersede",), "belong to a one-way merge-go question"),
        ],
    )
    def test_the_one_way_flags_are_refused_where_they_mean_nothing(
        self, crewless, capsys, extra, refusal
    ):
        argv = [*ask_argv(**{"--cause": "merge-go"}), "--pr", "o/r#5", *extra]
        if extra[0] == "--codex-finding":
            argv += ["--one-way", "money"]
        assert go(crewless, *argv) == 1
        assert refusal in capsys.readouterr().err

    def ask_with_finding(self, crewless, capsys):
        answer_with(crewless, CLEAR)
        assert go(crewless, *self.one_way(*self.CODEX)) == 0
        qid = qid_of(capsys.readouterr().out)
        item = board_of(crewless)["owner_queue"][-1]
        assert item["codex_reason"] == "the loop is capped at 3"
        assert item["ask"].splitlines()[-1] == (
            "On yes the Codex finding counts as skipped: https://github.com/o/r/pull/5#c1 retry "
            "loop (reason: the loop is capped at 3)"
        )
        return qid

    def comments(self, crewless):
        return [c for c in gh_calls(crewless) if isinstance(c, dict) and "comment" in c]

    def test_a_yes_in_the_chat_posts_one_go_comment_bound_to_the_head(self, crewless, capsys):
        qid = self.ask_with_finding(crewless, capsys)
        argv = ("answer", qid, "accept", "--session", "foxy", "--via", "chat", "--quote", "ja")
        assert go(crewless, *argv) == 0
        [comment] = self.comments(crewless)
        assert comment["comment"] == PR_URL
        lines = comment["body"].splitlines()
        assert lines[0] == f"<!-- board-go {qid} head={HEAD_A} -->"
        assert lines[1] == "> ja"
        assert (
            "Codex finding skipped on this yes: https://github.com/o/r/pull/5#c1 retry loop"
            in lines
        )
        assert "Reason of the asking session: the loop is capped at 3" in lines
        assert go(crewless, *argv) == 0  # a duplicate yes posts nothing again
        assert len(self.comments(crewless)) == 1

    def test_the_same_yes_after_the_question_left_the_board_runs_nothing(self, crewless, capsys):
        qid = self.ask_with_finding(crewless, capsys)
        argv = ("answer", qid, "accept", "--session", "foxy", "--via", "chat")
        assert go(crewless, *argv) == 0
        go(crewless, "prune")
        queue = board_of(crewless).get("owner_queue") or []
        assert all(q.get("id") != qid for q in queue)
        capsys.readouterr()
        assert go(crewless, *argv) == 0
        assert "is accepted and off the board; nothing runs again" in capsys.readouterr().out
        assert len(self.comments(crewless)) == 1

    def test_a_pane_yes_posts_it_too(self, crewless, capsys):
        answer_mod = board._answer_module()
        qid = self.ask_with_finding(crewless, capsys)
        path = str(crewless / "board-answers.jsonl")
        assert (
            answer_mod.main(["answer.py", path, qid, "accept", "2026-11-23T09:00:00.000Z", "lead"])
            == 0
        )
        [comment] = self.comments(crewless)
        assert comment["body"].splitlines()[:2] == [
            f"<!-- board-go {qid} head={HEAD_A} -->",
            "> Go (Accept on the board)",
        ]

    def test_a_failed_post_is_reported_and_the_same_yes_posts_it_again(
        self, crewless, capsys, monkeypatch
    ):
        qid = self.ask_with_finding(crewless, capsys)
        monkeypatch.setenv("FAKE_GH_COMMENT_EXIT", "1")
        argv = ("answer", qid, "accept", "--session", "foxy", "--via", "chat")
        assert go(crewless, *argv) == 3
        err = capsys.readouterr().err
        assert "the go comment on the PR failed: GraphQL: Resource not accessible" in err
        assert [
            a["answer"] for a in jsonl(crewless / "board-answers.jsonl") if a["id"] == qid
        ] == ["accept"]
        monkeypatch.setenv("FAKE_GH_COMMENT_EXIT", "0")
        assert go(crewless, *argv) == 0
        assert len(self.comments(crewless)) == 2  # the failed one and the one that went through
        logged = [
            x
            for x in jsonl(crewless / "board-questions.jsonl")
            if x.get("outcome") == "go-comment"
        ]
        assert [x["ok"] for x in logged] == [False, True]

    @pytest.mark.parametrize("kind", ["deny", "accept"])
    def test_no_comment_without_a_finding_or_on_a_deny(self, crewless, capsys, kind):
        answer_with(crewless, CLEAR)
        extra = self.CODEX if kind == "deny" else ()
        assert go(crewless, *self.one_way(*extra)) == 0
        qid = qid_of(capsys.readouterr().out)
        assert go(crewless, "answer", qid, kind, "--session", "foxy", "--via", "chat") == 0
        assert self.comments(crewless) == []


class TestRulesNews:
    """A merged PR that changes the crew's rules reaches the human as one news line, once."""

    def pr(
        self,
        crewless,
        files,
        state="MERGED",
        body="**Draft:** no\n\nCaps the retry loop at three.\n",
    ):
        pr = {
            "number": 5,
            "url": PR_URL,
            "state": state,
            "body": body,
            "files": [{"path": f} for f in files],
        }
        gh_answers(crewless, {PR_URL: {"pr": pr}, "5 -R o/r": {"pr": pr}})

    @pytest.fixture(autouse=True)
    def fake_gh(self, crewless, monkeypatch):
        monkeypatch.setenv("FAKE_GH", str(crewless / "gh.json"))
        monkeypatch.setenv("FAKE_GH_LOG", str(crewless / "gh-calls.jsonl"))

    def test_a_merged_rule_change_adds_one_line_once(self, crewless):
        self.pr(crewless, [".claude/rules/a.md", ".github/workflows/ci.yml", "src/x.py"])
        assert go(crewless, "news", "merged", "--pr", "o/r#5") == 0
        item = board_of(crewless)["news"][0]
        assert (item["id"], item["kind"]) == ("R-r-5", "info")
        assert item["title"] == "rules changed: r#5 merged (2 rule file(s))"
        assert item["body"].splitlines() == [
            "Caps the retry loop at three.",
            "changes .claude/rules/a.md, .github/workflows/ci.yml",
            PR_URL,
        ]
        assert go(crewless, "news", "merged", "--pr", PR_URL) == 0
        assert [n["id"] for n in board_of(crewless)["news"]].count("R-r-5") == 1
        # read and pruned: the id in the logs keeps it from coming back
        answered(crewless, "R-r-5", "read", "2026-11-03T09:59:00.000Z")
        go(crewless, "prune")
        assert all(n.get("id") != "R-r-5" for n in board_of(crewless).get("news") or [])
        assert go(crewless, "news", "merged", "--pr", PR_URL) == 0
        assert all(n.get("id") != "R-r-5" for n in board_of(crewless).get("news") or [])

    @pytest.mark.parametrize(
        "files, state, why",
        [
            (["src/x.py", "docs/a.md"], "MERGED", "no rule paths"),
            ([".weside/orchestrate.md"], "OPEN", "not merged"),
        ],
    )
    def test_no_line_without_a_merged_rule_change(self, crewless, capsys, files, state, why):
        self.pr(crewless, files, state=state)
        before = board_of(crewless).get("news")
        assert go(crewless, "news", "merged", "--pr", "o/r#5") == 0
        assert why in capsys.readouterr().out
        assert board_of(crewless).get("news") == before

    def test_an_unreadable_pr_fails_and_writes_nothing(self, crewless, capsys):
        gh_answers(crewless, {})
        assert go(crewless, "news", "merged", "--pr", "o/r#5") == 1
        assert "gh pr view failed" in capsys.readouterr().err


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
    def test_a_codex_skip_in_the_ask_is_returned_with_the_flags_to_use(self, crewless, capsys):
        """Red arm: the reader returned "two decisions" for a merge question that named its
        skipped Codex finding in --ask, and the asker dropped the sentence the rule asks for."""
        answer_with(crewless, {**CLEAR, "form": ["two decisions in one"]})
        ask = "Merge #5? The yes also skips Codex finding 1 (false positive)."
        assert (
            go(crewless, *self.merge_argv("--pr", "o/r#5", "--one-way", "money"), "--ask", ask)
            == 1
        )
        err = capsys.readouterr().err
        assert "two decisions in one" in err and "--codex-finding and --codex-reason" in err

    @pytest.mark.usefixtures("merge_gh")
    def test_an_open_one_way_pr_is_posted_with_its_url_and_class(self, crewless):
        answer_with(crewless, CLEAR)
        assert go(crewless, *self.merge_argv("--pr", "o/r#5", "--one-way", "money")) == 0
        item = board_of(crewless)["owner_queue"][-1]
        assert (item["cause"], item["pr_url"], item["one_way"]) == ("merge-go", PR_URL, "money")

    @pytest.mark.usefixtures("merge_gh")
    def test_a_merge_go_carries_the_required_checks_of_its_pr(self, crewless):
        """Red arm: a merge-go named one review skip while CI Summary was red and the backend
        tests cancelled; the merge left main red for hours."""
        data = json.loads((crewless / "gh.json").read_text())
        data[PR_URL] = {
            **data[PR_URL],
            "checks": [
                {"name": "lint", "bucket": "pass"},
                {"name": "CI Summary", "bucket": "fail"},
                {"name": "Backend (Test)", "bucket": "cancel"},
                {"name": "Codex Review", "bucket": "pending"},
            ],
            "checks_exit": 1,
        }
        (crewless / "gh.json").write_text(json.dumps(data), encoding="utf-8")
        answer_with(crewless, CLEAR)
        german = "Darf PR 5 nach main, obwohl der Codex-Review noch läuft?"
        assert go(crewless, *self.merge_argv("--pr", "o/r#5"), "--ask", german) == 0
        item = board_of(crewless)["owner_queue"][-1]
        assert item["checks"] == (
            "required checks: 1 green, 1 red (CI Summary), 1 cancelled (Backend (Test)),"
            " 1 pending (Codex Review)"
        )
        assert item["ask"] == f"{german}\n{item['checks']}"
        # The reader judges the asker's text alone: the tool's English checks line made it
        # return German merge questions, and a reworded retry passed (unstable verdict).
        read = json.loads(jsonl(crewless / "reader-calls.jsonl")[-1]["stdin"])
        assert read["ask"] == german

    @pytest.mark.usefixtures("merge_gh")
    def test_a_merge_go_on_a_pr_without_required_checks_says_so(self, crewless):
        answer_with(crewless, CLEAR)
        assert go(crewless, *self.merge_argv("--pr", "o/r#5")) == 0
        assert board_of(crewless)["owner_queue"][-1]["checks"] == (
            "required checks: none reported by gh"
        )

    def test_one_way_without_merge_go_is_refused(self, crewless, capsys):
        assert go(crewless, *ask_argv(), "--one-way", "money") == 1
        assert "--one-way belongs to a merge-go question" in capsys.readouterr().err

    def test_close_merged_drops_the_question_once_its_pr_merged(self, crewless, merge_gh, capsys):
        """Red arm: close-merged printed none while answered merge questions (an Accept, the
        owner's "I merge it by hand") had a merged PR, one of them in another repo."""
        other = "https://github.com/o/infra/pull/9"
        answer_with(crewless, CLEAR)
        go(crewless, *self.merge_argv("--pr", PR_URL, "--one-way", "money"))
        board.StateDir(crewless / "board.json").write_board(
            lambda b: b["owner_queue"].extend(
                [
                    {"id": "Q20", "cause": "merge-go", "pr_url": PR_URL, "session": "lead-12"},
                    {"id": "Q21", "cause": "merge-go", "pr_url": other, "session": "lead-12"},
                ]
            )
        )
        go(crewless, "close-merged")
        assert capsys.readouterr().out.strip().endswith("closed: none")
        assert [q["id"] for q in board_of(crewless)["owner_queue"]] == ["Q7", "Q8", "Q20", "Q21"]
        with (crewless / "board-answers.jsonl").open("a") as fh:  # Q8: "I merge it by hand"
            for qid in ("Q8", "Q20"):
                fh.write(json.dumps({"id": qid, "answer": "accept", "ts": "2026-11-03T10:01:00Z"}))
                fh.write("\n")
        merge_gh("MERGED")
        data = json.loads((crewless / "gh.json").read_text())
        data[other] = {"pr": {"state": "MERGED", "url": other}}
        (crewless / "gh.json").write_text(json.dumps(data), encoding="utf-8")
        assert go(crewless, "close-merged") == 0
        assert capsys.readouterr().out.strip().splitlines() == [
            f"closed Q8: PR MERGED {PR_URL}",
            f"closed Q20: PR MERGED {PR_URL}",
            f"closed Q21: PR MERGED {other}",
        ]
        assert [q["id"] for q in board_of(crewless)["owner_queue"]] == ["Q7"]
        closed = [q for q in jsonl(crewless / "board-questions.jsonl") if q["outcome"] == "closed"]
        assert [(q["id"], q["reason"]) for q in closed] == [
            ("Q8", "PR MERGED"),
            ("Q20", "PR MERGED"),
        ]
        # Q21 was open: it got the answer its asker reads (no ledger here, so prune dropped it)
        last = jsonl(crewless / "board-answers.jsonl")[-1]
        assert (last["id"], last["answer"], last["pr"]) == ("Q21", "pr_merged", other)

    HAND: ClassVar[dict] = {
        "id": "Q20",
        "cause": "merge-go",
        "pr_url": PR_URL,
        "session": "lead-12",
    }

    @pytest.mark.parametrize("pr_state", ["MERGED", "CLOSED"])
    def test_a_hand_merge_reaches_the_asker_as_an_answer(self, crewless, merge_gh, pr_state):
        """Red arm (24.11.): the owner merged by hand, close-merged dropped the open question and
        wrote only a log line; nothing went to the answers file, so its asker kept waiting."""
        epoch_row(crewless)
        board.StateDir(crewless / "board.json").write_board(
            lambda b: b["owner_queue"].append(dict(self.HAND))
        )
        merge_gh(pr_state)
        assert go(crewless, "close-merged") == 0
        lines = [a for a in jsonl(crewless / "board-answers.jsonl") if a["id"] == "Q20"]
        kind = {"MERGED": "pr_merged", "CLOSED": "pr_closed"}[pr_state]
        assert [(a["answer"], a["pr"], a["session"]) for a in lines] == [
            (kind, PR_URL, "close-merged")
        ]
        # the deliverer finds the asker only on the board: the item stays until prune sees it carried
        assert "Q20" in [q["id"] for q in board_of(crewless)["owner_queue"]]
        status, *_ = board.question_status(board.StateDir(crewless / "board.json"), "Q20")
        assert status == f"answered: {kind}"
        assert go(crewless, "close-merged") == 0  # a second run writes nothing again
        assert len([a for a in jsonl(crewless / "board-answers.jsonl") if a["id"] == "Q20"]) == 1

    @pytest.mark.usefixtures("merge_gh")
    def test_an_open_pr_writes_no_answer(self, crewless):
        epoch_row(crewless)
        board.StateDir(crewless / "board.json").write_board(
            lambda b: b["owner_queue"].append(dict(self.HAND))
        )
        assert go(crewless, "close-merged") == 0
        assert not [a for a in jsonl(crewless / "board-answers.jsonl") if a.get("id") == "Q20"]

    def test_a_later_go_on_a_hand_merged_question_runs_nothing(self, crewless, merge_gh, capsys):
        """A Go after the hand merge is a duplicate: no answer line, no go comment on the PR."""
        epoch_row(crewless)
        item = {
            **self.HAND,
            "one_way": "money",
            "head": HEAD_A,
            "codex_finding": "retry loop",
            "codex_reason": "capped",
        }
        board.StateDir(crewless / "board.json").write_board(
            lambda b: b["owner_queue"].append(item)
        )
        merge_gh("MERGED")
        go(crewless, "close-merged")
        before = jsonl(crewless / "board-answers.jsonl")
        assert go(crewless, "answer", "Q20", "accept", "--session", "foxy", "--via", "chat") == 0
        assert "recorded as a duplicate" in capsys.readouterr().out
        assert jsonl(crewless / "board-answers.jsonl") == before
        dup = jsonl(crewless / "board-questions.jsonl")[-1]
        assert (dup["outcome"], dup["closed_by"]) == ("duplicate-answer", "pr_merged")
        calls = crewless / "gh-calls.jsonl"
        assert not any("comment" in argv for argv in (jsonl(calls) if calls.exists() else []))

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
        # A decision is for the record: the board's log, not the owner's news.
        assert not any(i.get("kind") == "decision" for i in board_of(crewed)["news"])
        item = board_of(crewed)["log"][-1]
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
        assert board_of(crewed)["log"][-1]["id"] == "D5"

    @pytest.mark.parametrize(
        "who, area, kind, message",
        [
            ("vic", "product", "fence", "this session does not hold roles.product"),
            ("ada", "legal", "fence", "area 'legal' is no role key"),
            ("ada", "product", "veto", "kind 'veto' is not one of cut, fence, process"),
            ("ada", "product", "fence", "--key 'proj-40' does not match naming.key"),
        ],
    )
    def test_refusals_write_nothing(self, crewed, capsys, monkeypatch, who, area, kind, message):
        pin(monkeypatch, who)
        before = (crewed / "board.json").read_bytes()
        key = "proj-40" if "proj-40" in message else "PROJ-40"
        assert decide(crewed, area=area, kind=kind, key=key) == 1
        assert message in capsys.readouterr().err
        assert (crewed / "board.json").read_bytes() == before
        assert not (crewed / "board-decisions.jsonl").exists()

    def test_a_process_decision_without_a_ticket_takes_a_plan_slug(self, crewed, monkeypatch):
        """Red arm: an owner's process decision without a ticket was refused ('jira-sync' does
        not match naming.key) and filed under an unrelated epic key."""
        pin(monkeypatch, "ada")
        assert decide(crewed, kind="process", key="jira-sync", text="weekly sync") == 0
        assert board_of(crewed)["log"][-1]["title"] == "product process jira-sync: weekly sync"


class TestNewsAdd:
    def test_the_coordinator_adds_one_item_at_the_top(self, crewed, monkeypatch, capsys):
        pin(monkeypatch, "otto")
        assert (
            go(
                crewed,
                "news",
                "add",
                "--title",
                "RC v2.5.0-rc.1 cut",
                "--body",
                "PROJ-40, PROJ-41",
            )
            == 0
        )
        item = json.loads(capsys.readouterr().out)
        assert item == {
            "id": "N3",
            "kind": "info",
            "title": "RC v2.5.0-rc.1 cut",
            "body": "PROJ-40, PROJ-41",
            "ts": "2026-11-03T10:00:00Z",
        }
        assert board_of(crewed)["news"][0] == item
        assert go(crewed, "news", "add", "--title", "Prod is live", "--kind", "gate") == 0
        assert [n["id"] for n in board_of(crewed)["news"]][:2] == ["N4", "N3"]

    @pytest.mark.parametrize(
        "who, title, message",
        [
            ("ada", "RC cut", "only the coordinator writes the owner's news"),
            ("otto", "two\nlines", "--title is one non-empty line"),
            ("otto", "  ", "--title is one non-empty line"),
        ],
    )
    def test_refusals_write_nothing(self, crewed, monkeypatch, capsys, who, title, message):
        pin(monkeypatch, who)
        before = (crewed / "board.json").read_bytes()
        assert go(crewed, "news", "add", "--title", title) == 1
        assert message in capsys.readouterr().err
        assert (crewed / "board.json").read_bytes() == before

    def test_a_worker_item_needs_no_coordinator_and_comes_once(self, crewed, monkeypatch, capsys):
        pin(monkeypatch, "ada")
        args = ("news", "worker", "--id", "W-AC-1-x-ab12", "--title", "AC-1-x waits 15 min")
        assert go(crewed, *args, "--body", "claude attach ab12") == 0
        assert go(crewed, *args) == 0
        assert capsys.readouterr().out.splitlines()[-1] == "unchanged"
        items = [n for n in board_of(crewed)["news"] if n["id"] == "W-AC-1-x-ab12"]
        assert len(items) == 1 and items[0]["kind"] == "todo"


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
        # the bundle's day is the one in the crew's time.zone: 23:30 UTC is Berlin's next day
        (crewed / "work" / ".weside" / "config.json").write_text(
            json.dumps({"time": {"zone": "Europe/Berlin"}}), encoding="utf-8"
        )
        pin(monkeypatch, "ada")
        decide(crewed, kind="cut", text="at night")
        pin(monkeypatch, "otto")
        go(crewed, "bundle", now=datetime(2026, 11, 21, 23, 30, tzinfo=timezone.utc))
        assert board_of(crewed)["news"][-1]["id"] == "B-2026-11-22"

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


def land(root):
    """Commit the checkout and point origin/main at it: select reads the plan blob on main."""
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", "plan")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")


def revise(plan, mark):
    """A new plan version a Ready panel sees: ``mark`` under ``## Context`` (a line at the end
    falls into ``## Documentation Impact``, which is no part of the panel's subject)."""
    plan.write_text(plan.read_text().replace("## Context\n", f"## Context\n{mark}\n", 1))


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
        land(moving / "work")
        before = (moving / "board.json").read_bytes()
        adapter = fake()
        assert act(moving, "select", KEY, adapter=adapter) == 1
        out, err = capsys.readouterr()
        lines = [x for x in err.splitlines() if not x.startswith("warning:")]
        assert lines == [
            f"board.py select {KEY}: refused (ready gate)",
            f"{moving / 'work' / 'docs' / 'plans' / f'{KEY}-story.md'}:23: AC2: no `**Then**`",
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
        answers.write_text('{"id": "Q7", "answer": "followup"}\n', encoding="utf-8")
        before = (moving / "board.json").read_bytes(), answers.read_bytes()
        assert act(moving, "select", KEY, adapter=fake()) == 0
        after = (moving / "board.json").read_bytes(), answers.read_bytes()
        assert after == before, "select wrote board.json or the answers file"
        sub = board.parser()._subparsers._group_actions[0].choices["select"]
        options = {s for a in sub._actions for s in a.option_strings} - {"-h", "--help"}
        assert options == {"--plan", "--input", "--refiner"}
        assert [g for g, _ in board.ENTRY_RULES["selected"]] == [
            "role",
            "owner",
            "plan on main",
            "refiner",
            "ready gate",
            "tier",
            "lenses",
        ]


class TestSelectRefiner:
    """`select --refiner` selects only a key on the line of its approved epic without
    `select: owner`; the epic plan is read on main, never in the checkout."""

    def epic(self, root, old, new):
        path = root / "docs" / "plans" / "PROJ-1-epic.md"
        path.write_text(path.read_text().replace(old, new, 1), encoding="utf-8")

    @pytest.mark.parametrize(
        "change, line",
        [
            (
                ("line: [PROJ-12, PROJ-13]\n", ""),
                "epic PROJ-1 has no `line:` (PROJ-1-epic.md); product (Ada) selects",
            ),
            (
                ("line: [PROJ-12, PROJ-13]", "line: [PROJ-13]"),
                f"{KEY} is not on the finish line of PROJ-1 (PROJ-1-epic.md line: PROJ-13); "
                "product (Ada) selects",
            ),
            (
                ("status: approved", "status: approved\nselect: owner"),
                "epic PROJ-1 says `select: owner` (PROJ-1-epic.md); product (Ada) selects",
            ),
            (
                ("status: approved", "status: draft"),
                "epic PROJ-1 is not approved (PROJ-1-epic.md status: draft); product (Ada) selects",
            ),
        ],
        ids=["no line", "off the line", "select owner", "draft with a line"],
    )
    def test_a_refiner_off_an_approved_line_is_refused(self, moving, capsys, change, line):
        root = moving / "work"
        green_lenses(moving)
        self.epic(root, *change)
        land(root)
        before = (moving / "board.json").read_bytes()
        adapter = fake()
        assert act(moving, "select", KEY, "--refiner", adapter=adapter) == 1
        out, err = capsys.readouterr()
        lines = [x for x in err.splitlines() if not x.startswith("warning:")]
        assert lines == [f"board.py select {KEY}: refused (refiner)", line]
        assert_untouched(moving, before, out, adapter)

    def test_a_story_without_an_epic_is_the_owner_s(self, moving, capsys):
        root = moving / "work"
        green_lenses(moving)
        plan = root / "docs" / "plans" / f"{KEY}-story.md"
        plan.write_text(plan.read_text().replace("epic: PROJ-1\n", "", 1), encoding="utf-8")
        land(root)
        assert act(moving, "select", KEY, "--refiner", adapter=fake()) == 1
        err = capsys.readouterr().err
        assert f"{KEY} names no `epic:`; product (Ada) selects" in err.splitlines()

    def test_the_epic_is_read_on_main_not_in_the_checkout(self, moving, capsys):
        root = moving / "work"
        green_lenses(moving)
        self.epic(root, "line: [PROJ-12, PROJ-13]", "line: [PROJ-13]")
        land(root)
        self.epic(root, "line: [PROJ-13]", "line: [PROJ-12, PROJ-13]")
        assert act(moving, "select", KEY, "--refiner", adapter=fake()) == 1
        assert "refused (refiner)" in capsys.readouterr().err

    def test_a_crew_without_refiner_selects_refuses_every_refiner(self, moving, capsys):
        green_lenses(moving)
        crew_path = moving / "work" / ".weside" / "crew.json"
        data = json.loads(crew_path.read_text(encoding="utf-8"))
        data["select"] = {"refiner": False}
        crew_path.write_text(json.dumps(data), encoding="utf-8")
        before = (moving / "board.json").read_bytes()
        adapter = fake()
        assert act(moving, "select", KEY, "--refiner", adapter=adapter) == 1
        out, err = capsys.readouterr()
        lines = [x for x in err.splitlines() if not x.startswith("warning:")]
        assert lines == [
            f"board.py select {KEY}: refused (refiner)",
            "the crew sets `select.refiner: false`; product (Ada) selects",
        ]
        assert_untouched(moving, before, out, adapter)

    def test_a_key_on_the_approved_line_selects(self, moving, capsys):
        green_lenses(moving)
        assert act(moving, "select", KEY, "--refiner", adapter=fake()) == 0, (
            capsys.readouterr().err
        )
        assert transitions(moving)[-1]["to"] == "selected"

    def test_a_plain_select_ignores_the_line(self, moving, capsys):
        root = moving / "work"
        green_lenses(moving)
        self.epic(root, "status: approved", "status: approved\nselect: owner")
        self.epic(root, "line: [PROJ-12, PROJ-13]", "line: [PROJ-13]")
        land(root)
        assert act(moving, "select", KEY, adapter=fake()) == 0, capsys.readouterr().err


class TestSelectLenses:
    @pytest.fixture(autouse=True)
    def risk_plan(self, moving, monkeypatch):  # noqa: ARG002 (order: after `moving` clears the env)
        """The panel judges a risk plan; a T0 plan selects without one (test below)."""
        monkeypatch.setenv("FAKE_RISK_LINE", "T2")

    def test_a_t0_plan_selects_without_a_panel(self, moving, monkeypatch):
        monkeypatch.delenv("FAKE_RISK_LINE")
        with_row(moving, KEY, "backlog")
        assert act(moving, "select", KEY, adapter=fake()) == 0
        assert transitions(moving)[-1]["panel"] == "none (T0)"

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
            revise(plan, "<!-- edited -->")
            land(root)
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
        land(moving / "work")
        read = []
        monkeypatch.setattr(
            lens_verdict, "check_ready", lambda *a: read.append(a) or (True, [], [], [])
        )
        assert act(moving, "select", KEY, adapter=fake()) == 1
        assert read == []
        assert "refused (ready gate)" in capsys.readouterr().err

    @pytest.mark.parametrize("checkout", ["stale", "missing"])
    def test_select_reads_the_plan_on_main_not_the_checkout(self, moving, capsys, checkout):
        """A checkout behind main (an old plan, or none yet) selects what main carries."""
        root = moving / "work"
        vid = green_lenses(moving)
        plan = root / "docs" / "plans" / f"{KEY}-story.md"
        if checkout == "stale":
            plan.write_text(plan.read_text().replace("**Then** it writes", "it writes"))
        else:
            plan.unlink()
        assert act(moving, "select", KEY, adapter=fake()) == 0, capsys.readouterr().err
        assert transitions(moving)[-1]["to"] == "selected"
        assert vid == f"ready-{KEY}"

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
        revise(plan, "<!-- round 2 -->")
        land(root)
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

    def test_select_puts_the_holder_s_decision_above_the_round_cap_into_the_row(
        self, moving, capsys
    ):
        root = moving / "work"
        vid = f"ready-{KEY}"
        plan = root / "docs" / "plans" / f"{KEY}-story.md"
        blocking = {"severity": "BLOCKING", "claim": "too wide", "where": "plan:AC1"}
        blocking["question"] = "q"
        for n in (1, 2):
            revise(plan, f"<!-- round {n} -->")
            land(root)
            for entry in lens_verdict.plan(root, "ready", KEY)["entries"]:
                body = {"findings": [blocking] if entry["lens"] == "product" else []}
                lens_verdict.write(root, vid, entry["lens"], answer=json.dumps(body))
        revise(plan, "<!-- round 3 -->")
        land(root)
        with pytest.raises(lens_verdict.RefusedError, match="round cap: the lens holder decides"):
            lens_verdict.plan(root, "ready", KEY)
        lens_verdict.decide(root, vid, "product", "product", "Narrowed in the next story.")
        code = act(moving, "select", KEY, adapter=fake())
        out, err = capsys.readouterr()
        assert code == 0, err
        decided = [{"lens": "product", "by": "product", "sentence": "Narrowed in the next story."}]
        assert transitions(moving)[-1]["decided"] == decided
        assert "decided: product by product: Narrowed in the next story." in out.splitlines()

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
                revise(plan, "<!-- round 2 -->")
                land(root)
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

    def test_a_key_off_the_finish_line_is_refused_naming_the_extensions(self, moving, capsys):
        """PROJ-1's `line:` is [PROJ-12, PROJ-13]; PROJ-40 is new work. Red arm: on the rule
        before the finish line the move passes and writes a row."""
        before = (moving / "board.json").read_bytes()
        adapter = fake()
        assert act(moving, "move", "PROJ-40", "backlog", "--epic", "PROJ-1", adapter=adapter) == 1
        out, err = capsys.readouterr()
        assert err.splitlines()[0] == (
            "board.py move PROJ-40 backlog: refused: PROJ-40 is not on the finish line of PROJ-1 "
            "(PROJ-1-epic.md line: PROJ-12, PROJ-13); add it under `## Extensions` of "
            "PROJ-1-epic.md (1 open): Ada pre-sorts, Hal decides each entry "
            "(into the epic's line, a follow-up epic, or dropped)"
        ), err
        assert_untouched(moving, before, out, adapter)

    @pytest.mark.parametrize("key", ["PROJ-12", "PROJ-13"])
    def test_the_first_and_last_key_of_a_commented_line_move(self, moving, key):
        """`line: [A, B]  # note` kept `[` on A and `]  # note` on B. Red arm: both refused."""
        epic = moving / "work" / "docs" / "plans" / "PROJ-1-epic.md"
        text = epic.read_text(encoding="utf-8")
        epic.write_text(text.replace("PROJ-13]", "PROJ-13]  # a note", 1), encoding="utf-8")
        land(moving / "work")
        assert act(moving, "move", key, "backlog", "--epic", "PROJ-1", adapter=fake()) == 0

    def test_an_epic_without_a_line_warns_and_moves(self, moving, capsys):
        """A running epic from before the finish line: PROJ-2 has no `line:`."""
        assert act(moving, "move", KEY, "backlog", "--epic", "PROJ-3", adapter=fake()) == 0
        err = capsys.readouterr().err
        assert (
            "warning: epic PROJ-3 has no `line:` yet (PROJ-2-epic.md); its master draws the "
            "line, until then every key moves"
        ) in err.splitlines()

    def test_in_progress_after_another_state_is_refused(self, moving, capsys):
        with_row(moving, KEY, "backlog")
        assert act(moving, "move", KEY, "in_progress", adapter=fake()) == 1
        assert "(its last row is backlog)" in capsys.readouterr().err
        # --reopen does not open the way from any state: only from in_review/in_test
        assert act(moving, "move", KEY, "in_progress", "--reopen", "x", adapter=fake()) == 1
        assert "(its last row is backlog)" in capsys.readouterr().err

    @pytest.mark.parametrize("was", [None, "backlog"])
    def test_the_fast_lane_pulls_a_story_without_selected(self, moving, was):
        """A small story without a plan file is pulled straight to In Progress (red arm: the
        same move without --fast is refused, the test above)."""
        if was:
            with_row(moving, KEY, was)
        assert act(moving, "move", KEY, "in_progress", "--fast", adapter=fake()) == 0
        row = jsonl(moving / "board-transitions.jsonl")[-1]
        assert (row["to"], row["via"]) == ("in_progress", "fast")

    @pytest.mark.parametrize("was", ["in_review", "in_test"])
    def test_a_reverted_story_reopens_to_in_progress_only_with_a_reason(self, moving, capsys, was):
        """A story whose merged PR was reverted (or whose test failed) goes back to In Progress;
        the board followed the ticket nowhere before (red arm: no --reopen, refused)."""
        with_row(moving, KEY, was)
        adapter = fake()
        assert act(moving, "move", KEY, "in_progress", adapter=adapter) == 1
        out, err = capsys.readouterr()
        assert f'in_progress from {was} needs --reopen "<reason>"' in err
        assert len(transitions(moving)) == 1 and adapter.calls == [] and "carry:" not in out
        reason = "revert of the merged PR"
        assert act(moving, "move", KEY, "in_progress", "--reopen", reason, adapter=adapter) == 0
        row = transitions(moving)[-1]
        assert (row["from"], row["to"], row["reopen"]) == (was, "in_progress", reason)
        status = board.crew_mod.DEFAULTS["board"]["states"]["in_progress"]
        assert adapter.calls == [("move", KEY, status)]

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


class TestMoveDoneAlreadyFixed:
    def test_a_story_fixed_by_another_merged_pr_moves_to_done_from_backlog(self, moving, capsys):
        with_row(moving, KEY, "backlog")
        gh_answers(moving, {"9 -R acme/app": pr(title="fix: other story", headRefName="fix/x")})
        adapter = fake()
        argv = ["move", KEY, "done", "--already-fixed", "acme/app#9"]
        assert act(moving, *argv, adapter=adapter) == 0, capsys.readouterr().err
        row = transitions(moving)[-1]
        assert (row["from"], row["to"], row["via"]) == ("backlog", "done", "already-fixed")
        assert row["pr"] == [MERGED["url"]]
        assert adapter.calls[0] == ("move", KEY, "Done")
        op, _key, text = adapter.calls[1]
        assert op == "comment" and text.startswith(
            f"Already fixed on the default branch by {MERGED['url']}"
        )

    @pytest.mark.parametrize(
        "last, ref, answer, message",
        [
            (
                "backlog",
                "acme/app#9",
                pr(state="OPEN"),
                "--already-fixed acme/app#9 is not merged",
            ),
            ("backlog", "9", None, "--already-fixed 9 is no URL or <owner>/<repo>#<n>"),
            ("done", "acme/app#9", pr(), f"{KEY} is done already"),
        ],
    )
    def test_refusals(self, moving, capsys, last, ref, answer, message):
        with_row(moving, KEY, last)
        if answer:
            gh_answers(moving, {"9 -R acme/app": answer})
        before = transitions(moving)
        assert act(moving, "move", KEY, "done", "--already-fixed", ref, adapter=fake()) == 1
        err = capsys.readouterr().err
        assert err.strip() == f"board.py move {KEY} done: refused: {message}"
        assert transitions(moving) == before

    def test_the_backlog_refusal_names_the_flag(self, moving, capsys):
        with_row(moving, KEY, "backlog")
        assert act(moving, "move", KEY, "done", "--comment-file", "x", adapter=fake()) == 1
        assert "--already-fixed <owner>/<repo>#<n>" in capsys.readouterr().err


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

    def test_linked_by_a_ticket_line_in_the_body_passes(self, moving, capsys):
        """A story delivered by a bundle PR or another story's PR. Red arm: refused "not linked"
        although the PR body listed the key on its ticket line."""
        body = f"## Summary\nx\n\n**Tickets:** PROJ-1, {KEY}, PROJ-3\n"
        gh_answers(moving, {"7 -R acme/app": pr(headRefName="feat/x", title="t", body=body)})
        assert act(moving, "move", KEY, "in_review", "--pr", "acme/app#7", adapter=fake()) == 0
        gh_answers(
            moving, {"9 -R acme/app": pr(headRefName="feat/x", title="t", body=f"Closes {KEY}\n")}
        )
        assert act(moving, "move", KEY, "in_review", "--pr", "acme/app#9", adapter=fake()) == 0
        # a key mentioned in passing in the prose, even on a line opening with Fixes, is no link
        prose = f"## Summary\n- Fixes the export crash seen after {KEY}\n"
        gh_answers(moving, {"8 -R acme/app": pr(headRefName="feat/x", title="t", body=prose)})
        assert act(moving, "move", KEY, "in_review", "--pr", "acme/app#8", adapter=fake()) == 1
        assert "is not linked" in capsys.readouterr().err

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
        fields = ["--json", "state,mergedAt,headRefName,headRefOid,title,body,url"]
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
        assert transitions(moving)[-1]["ticket"] == "pending"

    def test_select_removes_the_crews_select_labels(self, moving, capsys):
        """Red arm: every select needed the owner's release label removed by hand."""
        with_jira(moving)
        path = moving / "work" / ".weside" / "crew.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["board"]["select_unlabel"] = ["READY"]
        path.write_text(json.dumps(data), encoding="utf-8")
        green_lenses(moving)
        assert act(moving, "select", KEY) == 0
        carried = carry_of(capsys.readouterr().out)
        assert carried[-1] == {"op": "unlabel", "key": KEY, "remove": "READY"}

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


def news_of(state_dir, kind, field="news"):
    return [n for n in board_of(state_dir).get(field) or [] if n.get("kind") == kind]


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
        out, err = capsys.readouterr()
        assert (
            "the ticket is not changed yet (row `ticket: pending`): run each of the 2 `carry:` ops"
            in err
        )
        assert "never report the move as done" in err
        row = transitions(crewed)[-1]
        assert {k: row[k] for k in ("key", "from", "to", "via", "ticket")} == {
            "key": DONE_KEY,
            "from": "in_review",
            "to": "done",
            "via": "comment",
            "ticket": "pending",
        }
        assert carry_of(out) == [
            {"op": "transition", "key": DONE_KEY, "status": "Done"},
            {"op": "comment", "key": DONE_KEY, "text": text},
        ]

    def test_a_bold_not_proven_line_counts(self, crewed):
        with_row(crewed, DONE_KEY, "in_review")
        text = "Walked Settings.\n**Not proven:** the small screen"
        assert (
            act(crewed, "move", DONE_KEY, "done", "--comment-file", comment_file(crewed, text))
            == 0
        )
        assert transitions(crewed)[-1]["to"] == "done"

    def test_a_green_entry_moves_via_receipt_with_the_generated_comment(self, crewed):
        with_row(crewed, DONE_KEY, "in_review")
        row, ops, sample = done_in_process(
            crewed, ticket_adapter.SessionTransport(), verdict_entry()
        )
        assert list(row) == ["key", "from", "to", "via", "rc", "ts", "by", "ticket"]
        assert (row["via"], row["rc"], row["ticket"]) == ("receipt", "v1.4.0-rc.2", "pending")
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
        # A sample is for the acceptance keeper, not the owner: the board's log.
        assert news_of(crewed, "sample") == []
        [item] = news_of(crewed, "sample", field="log")
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
        assert set(new) - set(old) == {
            "blocked",
            "waiting_on",
            "sla_due",
            "updated_at",
            "session_id",  # the line takes the sampled session's id
        }
        assert {
            k: v
            for k, v in new.items()
            if k not in ("blocked", "waiting_on", "since", "sla_due", "updated_at", "session_id")
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
        go(crewed, *ask_argv(**{"--session": WORKER, "--cause": "info", "--ask": "Ship tonight?"}))
        agents(crewed, {**BLOCKED_ROW, "state": "working", "waitingFor": None})
        capsys.readouterr()
        later = datetime(2026, 11, 3, 10, 7, tzinfo=timezone.utc)
        assert go(crewed, "blocked", WORKER, "--clear", now=later) == 0
        assert json.loads(capsys.readouterr().out)["obsolete"] == ["Q8"]
        queue = {q["id"]: q for q in board_of(crewed)["owner_queue"]}
        assert sorted(queue) == ["Q7", "Q8", "Q9"]
        assert queue["Q8"]["obsolete"] == "prompt resolved at 11:07"  # Berlin
        assert "obsolete" not in queue["Q9"] and "obsolete" not in queue["Q7"]

    def test_clear_of_a_chat_wait_marks_its_info_question_obsolete(self, crewed, capsys):
        # Q874, Q883, Q891, Q892 (20.11.): the detector asked "worker waits over 30 min on its
        # starter" (cause info); the starter answered or the worker stopped, the wait was cleared,
        # and the question stayed open until the owner answered a dead one.
        agents(crewed, {**BLOCKED_ROW, "state": "idle", "waitingFor": None})
        go(crewed, "blocked", WORKER, "--kind", "chat", "--waiting-on", "coordinator")
        answer_with(crewed, CLEAR)
        go(crewed, *ask_argv(**{"--session": WORKER, "--cause": "info"}))
        go(crewed, *ask_argv(**{"--session": WORKER, "--cause": "access-click"}))
        agents(crewed)  # the worker stopped
        capsys.readouterr()
        later = datetime(2026, 11, 3, 10, 40, tzinfo=timezone.utc)
        assert go(crewed, "blocked", WORKER, "--clear", now=later) == 0
        assert json.loads(capsys.readouterr().out)["obsolete"] == ["Q8"]
        queue = {q["id"]: q for q in board_of(crewed)["owner_queue"]}
        assert queue["Q8"]["obsolete"] == "prompt resolved at 11:40"
        assert "obsolete" not in queue["Q9"]

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

    def test_an_undelivered_close_stays_however_old(self, crewless):
        """Red arm: prune never drops an answer its asker has not received; after
        PRUNE_AFTER_H the deliverer routes it to the coordinator (deliver.ts) and the delivered
        route row lets it go."""
        epoch_row(crewless)
        ts = "2026-11-01T09:00:00.000Z"
        answered(crewless, "Q7", "accept", ts)
        go(crewless, "prune", now=NOW + timedelta(days=3))
        assert [q["id"] for q in board_of(crewless)["owner_queue"]] == ["Q7"]
        delivered_row(crewless, "Q7", ts, "2026-11-02T09:00:01.000Z", role="route")
        go(crewless, "prune", now=NOW + timedelta(days=3))
        assert board_of(crewless)["owner_queue"] == []

    def test_a_duplicate_answer_before_delivery_keeps_it(self, crewless):
        """Red arm: a second answer names the question (`closed_by`), yet the first one has not
        reached its asker: it stays."""
        epoch_row(crewless)
        answered(crewless, "Q7", "accept", "2026-11-03T09:59:00.000Z")
        assert go(crewless, "answer", "Q7", "deny", "--session", "foxy", "--via", "chat") == 0
        go(crewless, "prune")
        assert [q["id"] for q in board_of(crewless)["owner_queue"]] == ["Q7"]

    @pytest.mark.parametrize(
        "fields",
        [
            {"cause": "merge-go", "one_way": "money", "pr_url": PR_URL},
            {"cause": "window-go"},
        ],
        ids=["one-way-merge-go", "window-go"],
    )
    @pytest.mark.parametrize("answer", ["accept", "deny"])
    def test_an_answered_go_leaves_the_queue_once_its_asker_has_it(self, crewless, fields, answer):
        """Red arm: an accepted one-way merge-go or window-go stayed in `owner_queue` after its
        asker had the answer (four answered questions hung there on one day); the asker keeps
        the go in its prompt and `board.py show`, the owner's queue keeps only what waits."""
        path = crewless / "board.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        q7 = next(q for q in data["owner_queue"] if q["id"] == "Q7")
        q7.update(fields)
        path.write_text(json.dumps(data), encoding="utf-8")
        epoch_row(crewless)
        ts = "2026-11-03T09:59:00.000Z"
        answered(crewless, "Q7", answer, ts)
        go(crewless, "prune")
        assert [q["id"] for q in board_of(crewless)["owner_queue"]] == ["Q7"]  # not carried yet
        delivered_row(crewless, "Q7", ts, "2026-11-03T09:59:04.000Z", role="asker")
        go(crewless, "prune")
        assert board_of(crewless)["owner_queue"] == []

    def test_an_earlier_followup_still_owed_to_the_asker_keeps_it(self, crewless):
        epoch_row(crewless)
        answered(crewless, "Q7", "followup", "2026-11-03T09:00:00.000Z")
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

    def test_a_question_the_coordinator_asked_goes_once_its_prompt_is_delivered(self, crewless):
        """Red arm: the coordinator as asker gets no asker row (deliver.ts `recipientsOf`); its
        delivered coordinator row carries the answer, or the question stays on the queue."""
        path = crewless / "board.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        next(q for q in data["owner_queue"] if q["id"] == "Q7")["session"] = "coord"
        path.write_text(json.dumps(data), encoding="utf-8")
        epoch_row(crewless)
        ts = "2026-11-03T09:59:00.000Z"
        answered(crewless, "Q7", "accept", ts, session="foxy")
        go(crewless, "prune")
        assert [q["id"] for q in board_of(crewless)["owner_queue"]] == ["Q7"]
        delivered_row(crewless, "Q7", ts, "2026-11-03T09:59:03.000Z")
        go(crewless, "prune")
        assert board_of(crewless)["owner_queue"] == []

    def test_followup_and_update_keep_the_question(self, crewless):
        answered(crewless, "Q7", "followup", "2026-11-01T09:00:00.000Z")
        answered(crewless, "Q7", "update", "2026-11-01T10:00:00.000Z")
        go(crewless, "prune")
        assert [q["id"] for q in board_of(crewless)["owner_queue"]] == ["Q7"]

    def test_read_news_and_expired_returns_and_bundles_go(self, crewless):
        def seed(b):
            b["news"] = [
                {"id": "N3", "kind": "info", "title": "read it"},
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
        answered(crewless, "N3", "read", "2026-11-03T09:59:00.000Z")
        answered(crewless, "E2", "read", "2026-11-01T09:00:00.000Z")
        go(crewless, "prune")
        # A returned item goes at once, whatever its age: the asker has it.
        assert [n["id"] for n in board_of(crewless)["news"]] == ["N5", "E2"]
        reasons = {q["id"]: q["reason"] for q in jsonl(crewless / "board-questions.jsonl")}
        assert reasons == {
            "N3": "read",
            "R1": "returned",
            "R2": "returned",
            "B-2026-11-01": "expired",
        }

    def test_a_write_moves_decisions_samples_and_lines_without_an_id_into_the_log(self, crewless):
        """Red arm: the owner's news showed `decision` items and kept the hand-written
        lines of 04.11. (`text`, `key`, no id), which the pane could not even draw."""

        def seed(b):
            b["news"] = [
                {
                    "ts": "2026-11-04T16:14:52Z",
                    "key": "—",
                    "text": "Security stays with its owner",
                },
                {"ts": "2026-11-04T11:51:46Z", "key": "PROJ-27", "text": "Finish the build first"},
                {"ts": "2026-11-03T13:30Z", "kind": "milestone", "title": "infra #1130 merged"},
                {"id": "N4", "kind": "info", "title": "RC cut"},
                {"id": "D21", "kind": "decision", "title": "coordinator process PROJ-89: sync"},
                {"id": "S2", "kind": "sample", "title": "Sample PROJ-15"},
                "a loose line",
            ]
            b["log"] = [{"id": f"D{i}", "kind": "decision", "title": "old"} for i in range(1, 49)]

        board.StateDir(crewless / "board.json", now=NOW).write_board(seed)
        after = board_of(crewless)
        assert after["news"] == [{"id": "N4", "kind": "info", "title": "RC cut"}]
        assert len(after["log"]) == board.LOG_KEEP
        assert after["log"][-6:] == [
            {"title": "Security stays with its owner", "ts": "2026-11-04T16:14:52Z"},
            {"title": "PROJ-27: Finish the build first", "ts": "2026-11-04T11:51:46Z"},
            {"title": "infra #1130 merged", "ts": "2026-11-03T13:30Z", "kind": "milestone"},
            {"id": "D21", "kind": "decision", "title": "coordinator process PROJ-89: sync"},
            {"id": "S2", "kind": "sample", "title": "Sample PROJ-15"},
            {"title": "a loose line"},
        ]
        # The next id counts the log too: D21 is never handed out again.
        assert board.StateDir(crewless / "board.json").next_id("D", after) == "D49"

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


def test_set_writes_a_parked_sessions_wake_trigger(crewless):
    """Red arm: the wake triggers of parked sessions lived only in the coordinator's memory file."""
    assert go(crewless, "set", "state=parked", "wake=plan of PROJ-12 on main") == 0
    line = line_of(crewless, "lead-12")
    assert (line["state"], line["wake"]) == ("parked", "plan of PROJ-12 on main")
    assert go(crewless, "set", "wake=") == 0 and "wake" not in line_of(crewless, "lead-12")


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


def test_ask_dates_its_question_in_the_humans_time_zone(crewed, capsys):
    """23:30 UTC is already the next day in Berlin: the day Foxy reads is Berlin's."""
    (crewed / "work" / ".weside" / "config.json").write_text(
        json.dumps({"time": {"zone": "Europe/Berlin"}}), encoding="utf-8"
    )
    answer_with(crewed, CLEAR)
    late = datetime(2026, 11, 21, 23, 30, tzinfo=timezone.utc)
    assert go(crewed, *ask_argv(), now=late) == 0
    assert board_of(crewed)["owner_queue"][-1]["since"] == "2026-11-22"


def test_ask_owner_by_name_and_an_unknown_owner_is_refused(crewed, capsys):
    answer_with(crewed, CLEAR)
    assert go(crewed, *ask_argv(), "--owner", "ada") == 0
    assert board_of(crewed)["owner_queue"][-1]["owner"] == "Ada"
    assert go(crewed, *ask_argv(**{"--ask": "Ship it tonight?"}), "--owner", "nobody") == 1
    assert "--owner 'nobody' is no crew member" in capsys.readouterr().err


def test_a_second_question_with_the_same_cause_on_an_open_key_is_refused_before_the_reader(
    crewless, capsys
):
    """Red arm: the same question twice in 3 minutes; a warning let the second one through."""
    answer_with(crewless, CLEAR)
    assert go(crewless, *ask_argv()) == 0
    first = qid_of(capsys.readouterr().out)
    before = (crewless / "board.json").read_bytes()
    reads = (crewless / "reader-calls.jsonl").read_bytes()
    assert (
        go(crewless, *ask_argv(**{"--ask": "Should checkout go live for everyone tonight?"})) == 1
    )
    err = capsys.readouterr().err
    assert f"refused: {first} on PROJ-12 (cause prod) is still open" in err
    assert f"--replace {first}" in err
    assert (crewless / "board.json").read_bytes() == before
    assert (crewless / "reader-calls.jsonl").read_bytes() == reads


def test_another_cause_on_an_open_key_warns_and_replace_takes_the_first_off(crewless, capsys):
    answer_with(crewless, CLEAR)
    assert go(crewless, *ask_argv()) == 0
    first = qid_of(capsys.readouterr().out)
    plan = {"--cause": "plan", "--ask": "Is the checkout plan ready to build?"}
    assert go(crewless, *ask_argv(**plan)) == 0
    out = capsys.readouterr()
    assert f"warning: {first} on PROJ-12 is still open" in out.err
    second = qid_of(out.out)
    assert go(crewless, *ask_argv(**plan), "--replace", second) == 0
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
    first = qid_of(capsys.readouterr().out)
    assert go(crewless, *ask_argv(**{"--key": "PROJ-13"}), "--replace", first) == 1
    assert f"--replace {first}: that question is on 'PROJ-12', not 'PROJ-13'" in (
        capsys.readouterr().err
    )
    assert first in [q["id"] for q in board_of(crewless)["owner_queue"]]


def test_set_takes_epic_and_its_own_name_as_session(crewless, capsys):
    """Red arm: `set --session <own name>` was an unrecognized argument and `epic=` not settable,
    although the compaction hook says "set `epic` on your board line"."""
    assert go(crewless, "set", "--session", "lead-12", "epic=PROJ-7", "state=build") == 0
    assert line_of(crewless, "lead-12")["epic"] == "PROJ-7"
    assert go(crewless, "set", "epic=42") == 0
    assert line_of(crewless, "lead-12")["epic"] == "42"
    assert go(crewless, "set", "epic=") == 0
    assert "epic" not in line_of(crewless, "lead-12")
    assert go(crewless, "set", "epic=not a key") == 1
    assert "epic 'not a key' is neither" in capsys.readouterr().err
    # another session's name is no way around --for
    assert go(crewless, "set", "--session", "other-3", "state=idle") == 1
    assert "set writes this session's own line, named lead-12" in capsys.readouterr().err


def test_distinct_lets_another_question_on_the_same_key_and_cause_through(crewless, capsys):
    """Red arm: two unrelated prod questions on one key; the second was refused as a duplicate
    and had to go onto another key."""
    answer_with(crewless, CLEAR)
    assert go(crewless, *ask_argv()) == 0
    first = qid_of(capsys.readouterr().out)
    assert go(crewless, *ask_argv(**{"--ask": "Other step: may the delta run tonight?"})) == 1
    assert "add `--distinct`" in capsys.readouterr().err
    assert (
        go(
            crewless,
            *ask_argv(**{"--ask": "Other step: may the delta run tonight?"}),
            "--distinct",
        )
        == 0
    )
    out = capsys.readouterr()
    assert f"warning: {first} on PROJ-12 is still open" in out.err
    assert [q.get("key") for q in board_of(crewless)["owner_queue"]].count("PROJ-12") == 2


def test_docs_name_every_flag_of_every_verb():
    """`ask --replace`, `ask --distinct` and the answer kind `withdraw`
    existed only in the code. Red arm: a flag or answer kind docs/board.md does not name."""
    import argparse  # noqa: PLC0415

    docs = (Path(__file__).resolve().parent.parent / "docs" / "board.md").read_text()
    missing = []

    def walk(p, path):
        for act in p._actions:
            if isinstance(act, argparse._SubParsersAction):
                for name, sub in act.choices.items():
                    walk(sub, (*path, name))
            elif path and any(o.startswith("--") for o in act.option_strings):
                flag = next(o for o in act.option_strings if o.startswith("--"))
                if flag != "--help" and flag not in docs:
                    missing.append(f"{' '.join(path)} {flag}")

    walk(board.parser(), ())
    answer = board.parser()._subparsers._group_actions[0].choices["answer"]
    kinds = next(a for a in answer._actions if a.dest == "kind").choices
    chat = docs.split("### Answers given in a chat", 1)[1].split("\n## ", 1)[0]
    missing += [f"answer {k}" for k in kinds if f"`{k}`" not in chat]
    assert not missing, f"docs/board.md names none of: {missing}"


def test_set_after_a_rename_takes_over_the_line_of_the_same_session(crewless):
    """A renamed session keeps one line: `set` under the new name finds its line by session id,
    renames it and keeps its fields (two lines with one session_id seen 24.11.)."""
    data = board_of(crewless)
    data["sessions"] = [
        {"name": "old", "session_id": "sid-12", "epic": "PROJ-7", "keys": ["PROJ-8"]}
    ]
    (crewless / "board.json").write_text(json.dumps(data), encoding="utf-8")
    assert go(crewless, "set", "now=phase 3") == 0
    sessions = board_of(crewless)["sessions"]
    assert len(sessions) == 1
    line = sessions[0]
    assert (line["name"], line["session_id"], line["epic"], line["keys"], line["now"]) == (
        "lead-12",
        "sid-12",
        "PROJ-7",
        ["PROJ-8"],
        "phase 3",
    )


def test_set_with_a_new_session_id_keeps_the_named_line(crewless):
    """A session with a new id after /clear or a resume keeps its line and the line takes the id
    (board line `rust` kept d3401f3c while its tail reported ff3188f1, 24.11.)."""
    data = board_of(crewless)
    data["sessions"] = [{"name": "lead-12", "session_id": "old", "epic": "PROJ-7"}]
    (crewless / "board.json").write_text(json.dumps(data), encoding="utf-8")
    assert go(crewless, "set", "now=phase 3") == 0
    sessions = board_of(crewless)["sessions"]
    assert [(s["name"], s["session_id"], s["epic"]) for s in sessions] == [
        ("lead-12", "sid-12", "PROJ-7")
    ]


def test_set_keeps_the_id_of_a_live_session_sharing_the_name(crewless, capsys):
    """Two live sessions named alike took the line from each other on every `set`, and delivery
    flipped between their tails. Red arm: the line takes the second session's id."""
    data = board_of(crewless)
    data["sessions"] = [{"name": "lead-12", "session_id": "sid-a", "epic": "PROJ-7"}]
    (crewless / "board.json").write_text(json.dumps(data), encoding="utf-8")
    both = [{"sessionId": "sid-a", "name": "lead-12"}, {"sessionId": "sid-12", "name": "lead-12"}]
    (crewless / "agents.json").write_text(json.dumps(both), encoding="utf-8")
    assert go(crewless, "set", "now=x") == 0
    line = line_of(crewless, "lead-12")
    assert (line["session_id"], line["now"], "cwd" in line) == ("sid-a", "x", False)
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and "sid-a" in err[0] and "/rename" in err[0]
    # the old id no longer listed under this name: the line takes the caller's
    (crewless / "agents.json").write_text(
        json.dumps([{"sessionId": "sid-a", "name": "elsewhere"}, both[1]]), encoding="utf-8"
    )
    assert go(crewless, "set", "now=y") == 0
    assert line_of(crewless, "lead-12")["session_id"] == "sid-12"


def test_set_takes_the_line_from_a_dead_row_sharing_the_name(crewless, capsys, monkeypatch):
    """`claude agents` keeps a dead worker's row: a worker restarted under its name with a new id
    never took its line and every call warned /rename. Red arm: the line keeps `sid-a`."""
    data = board_of(crewless)
    data["sessions"] = [{"name": "lead-12", "session_id": "sid-a"}]
    (crewless / "board.json").write_text(json.dumps(data), encoding="utf-8")
    both = [
        {"sessionId": "sid-a", "name": "lead-12", "pid": 4242},
        {"sessionId": "sid-12", "name": "lead-12"},
    ]
    (crewless / "agents.json").write_text(json.dumps(both), encoding="utf-8")
    monkeypatch.setattr(board.wl, "_pid_lives", lambda pid: str(pid) != "4242")
    assert go(crewless, "set", "now=x") == 0
    assert line_of(crewless, "lead-12")["session_id"] == "sid-12"
    assert "/rename" not in capsys.readouterr().err


def test_blocked_keeps_the_id_of_a_live_session_sharing_the_name(crewed, capsys):
    data = board_of(crewed)
    data["sessions"] = [{"name": WORKER, "session_id": "sid-a"}]
    (crewed / "board.json").write_text(json.dumps(data), encoding="utf-8")
    agents(crewed, BLOCKED_ROW, {**BLOCKED_ROW, "sessionId": "sid-a", "pid": os.getpid()})
    assert go(crewed, "blocked", WORKER, "--kind", "permission", "--starter", "lead-12") == 0
    assert line_of(crewed, WORKER)["session_id"] == "sid-a"
    assert "/rename" in capsys.readouterr().err


def test_set_folds_a_duplicate_line_of_the_same_session(crewless):
    """A board that already held two lines of one session kept both. Red arm: two lines remain."""
    data = board_of(crewless)
    data["sessions"] = [
        {"name": "old", "session_id": "sid-12", "topic": "kept", "now": "stale"},
        {"name": "lead-12", "session_id": "sid-12", "epic": "PROJ-7"},
    ]
    (crewless / "board.json").write_text(json.dumps(data), encoding="utf-8")
    assert go(crewless, "set", "now=x") == 0
    sessions = board_of(crewless)["sessions"]
    assert [(s["name"], s["session_id"], s["epic"], s["topic"], s["now"]) for s in sessions] == [
        ("lead-12", "sid-12", "PROJ-7", "kept", "x")
    ]


def test_set_refreshes_the_own_lines_cwd(crewed, monkeypatch):
    """A session restarted in another repo kept the old `cwd` on its line. Red arm: `/repo-a` stays."""
    data = board_of(crewed)
    data["sessions"] = [
        {"name": "lead-12", "session_id": "sid-12", "cwd": "/repo-a"},
        {"name": "other", "session_id": "sid-o", "cwd": "/repo-o"},
    ]
    (crewed / "board.json").write_text(json.dumps(data), encoding="utf-8")
    (crewed / "agents.json").write_text(
        json.dumps([{"sessionId": "sid-12", "name": "lead-12", "cwd": "/repo-b"}]), "utf-8"
    )
    assert go(crewed, "set", "now=x") == 0
    assert line_of(crewed, "lead-12")["cwd"] == "/repo-b"
    pin(monkeypatch, "otto")
    assert go(crewed, "set", "--for", "other", "now=y") == 0
    assert (line_of(crewed, "other")["cwd"], line_of(crewed, "other")["session_id"]) == (
        "/repo-o",
        "sid-o",
    )
    assert go(crewed, "set", "cwd=/x") != 0


def test_show_line_prints_each_status(crewless, capsys):
    """A question closed by a hand merge was passed on as waiting. Red arm: `show` takes one id."""
    data = board_of(crewless)
    data["owner_queue"] = [
        {"id": "Q8", "key": "PROJ-2", "ask": "Open one?\nmore", "since": "2026-11-02"}
    ]
    (crewless / "board.json").write_text(json.dumps(data), encoding="utf-8")
    log = crewless / "board-questions.jsonl"
    rows = [
        {
            "id": "Q7",
            "ts": "2026-11-01T09:00Z",
            "outcome": "posted",
            "key": "PROJ-1",
            "ask": "Merge?",
        },
        {"id": "Q7", "ts": "2026-11-02T21:06Z", "outcome": "closed", "reason": "PR 9 merged"},
    ]
    log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    capsys.readouterr()
    assert go(crewless, "show", "Q7", "Q8") == 0
    assert capsys.readouterr().out.splitlines() == [
        "Q7 closed 2026-11-02T21:06Z (PR 9 merged) · PROJ-1 · Merge?",
        "Q8 open 2026-11-02 · PROJ-2 · Open one?",
    ]
    assert go(crewless, "show", "Q7", "Q404", "--line") == 1
    assert capsys.readouterr().out.splitlines()[-1] == "Q404 unknown"
    assert go(crewless, "show", "Q7") == 0
    assert json.loads(capsys.readouterr().out)["status"] == "closed"
