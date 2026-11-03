"""answer.py only appends: earlier lines stay, each click is one JSON line."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import answer


def test_append_keeps_what_the_file_holds(tmp_path):
    path = tmp_path / "we-state" / "board-answers.jsonl"
    answer.append(str(path), "Q1", "accept", "2026-10-30T18:12:00.000Z", "Orchestrator")
    answer.append(str(path), "Q1", "info", "2026-10-30T18:13:00.000Z", None)
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert lines == [
        {
            "id": "Q1",
            "answer": "accept",
            "ts": "2026-10-30T18:12:00.000Z",
            "session": "Orchestrator",
        },
        {"id": "Q1", "answer": "info", "ts": "2026-10-30T18:13:00.000Z", "session": None},
    ]


def test_an_unknown_answer_writes_nothing(tmp_path):
    path = tmp_path / "board-answers.jsonl"
    with pytest.raises(ValueError):
        answer.append(str(path), "Q1", "yes", "t", "Orchestrator")
    assert not path.exists()


def test_main_takes_the_session_as_optional_last_argument(tmp_path):
    path = tmp_path / "a.jsonl"
    assert answer.main(["answer.py", str(path), "Q2", "discuss", "t"]) == 0
    assert json.loads(path.read_text())["session"] is None
    assert answer.main(["answer.py", str(path)]) == 2


def test_deny_and_read_are_answers_too(tmp_path):
    path = tmp_path / "board-answers.jsonl"
    answer.append(str(path), "Q3", "deny", "t1", "lead")
    answer.append(str(path), "N7", "read", "t2", None)
    assert [json.loads(line)["answer"] for line in path.read_text().splitlines()] == [
        "deny",
        "read",
    ]


def test_update_is_an_answer(tmp_path):
    path = tmp_path / "board-answers.jsonl"
    assert answer.main(["answer.py", str(path), "Q4", "update", "t", "lead"]) == 0
    assert json.loads(path.read_text()) == {
        "id": "Q4",
        "answer": "update",
        "ts": "t",
        "session": "lead",
    }


def test_a_pane_line_carries_no_via_and_the_command_line_refuses_one(tmp_path, capsys):
    path = tmp_path / "board-answers.jsonl"
    assert answer.main(["answer.py", str(path), "Q1", "accept", "t", "lead", "--via", "chat"]) == 2
    assert "board.py answer" in capsys.readouterr().err
    assert not path.exists()
    assert answer.main(["answer.py", str(path), "Q1", "accept", "t", "lead"]) == 0
    assert "via" not in json.loads(path.read_text())


def test_append_takes_via_and_quote_from_board_py(tmp_path):
    path = tmp_path / "board-answers.jsonl"
    line = answer.append(str(path), "Q1", "deny", "t", "lead", via="chat", quote="no")
    assert (
        json.loads(path.read_text())
        == line
        == {
            "id": "Q1",
            "answer": "deny",
            "ts": "t",
            "session": "lead",
            "via": "chat",
            "quote": "no",
        }
    )
