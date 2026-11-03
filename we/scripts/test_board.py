"""board.py: one class per verb on a shared state_dir (a temp board.json and its answers file)."""

from __future__ import annotations

import json
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

    def test_refuses_an_id_an_accept_or_deny_closed(self, state_dir, capsys):
        assert run(state_dir, "answer", "Q1", "deny", "--session", "asker", "--via", "chat") == 0
        assert run(state_dir, "answer", "Q1", "accept", "--session", "asker", "--via", "chat") == 1
        assert "Q1 is closed" in capsys.readouterr().err
        assert [a["answer"] for a in lines(state_dir)] == ["deny"]

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
