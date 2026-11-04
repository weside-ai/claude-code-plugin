"""board.py: one class per verb on a shared state_dir (a temp board.json and its answers file)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board  # noqa: E402

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


# ---------------------------------------------------------------------------------------------
# set, ask, decision, bundle: the session's own line, the owner's questions and the area decisions

import fcntl  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

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
        assert line_of(crewless, "lead-12") == {"name": "lead-12", "state": "ci", "now": "phase 3"}
        assert after["sessions"][1] == before["sessions"][1]
        assert {k: after[k] for k in after if k != "sessions"} == {
            k: before[k] for k in before if k != "sessions"
        }  # updated and updated_by untouched

    def test_appends_a_missing_line_with_name_and_session_id(self, crewless):
        (crewless / "agents.json").write_text(
            json.dumps([{"sessionId": "sid-12", "name": "fresh-1"}]), encoding="utf-8"
        )
        assert go(crewless, "set", "state=active") == 0
        assert line_of(crewless, "fresh-1") == {
            "name": "fresh-1",
            "session_id": "sid-12",
            "state": "active",
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
            ("topic=x", "field 'topic' is not settable"),
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
    "--cause": "merge-go",
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
            "cause": "merge-go",
            "since": "2026-11-03",
            "ts": "2026-11-03T10:00:00Z",
        }
        [line] = jsonl(crewless / "board-questions.jsonl")
        assert line["id"] == "Q272" and line["outcome"] == "posted"
        assert line["ask"] == ASK["--ask"] and line["cause"] == "merge-go"
        assert line["reader"] == CLEAR

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
            "merge-go",
        )

    def test_the_next_id_counts_the_log_too(self, crewless, capsys):
        answer_with(crewless, CLEAR)
        go(crewless, *ask_argv())
        board.StateDir(crewless / "board.json").write_board(lambda b: b.update(owner_queue=[]))
        go(crewless, *ask_argv())
        assert capsys.readouterr().out.split() == ["posted", "Q8", "posted", "Q9"]


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
