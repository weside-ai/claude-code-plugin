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
    answer.append(str(path), "Q1", "accept", "2026-10-30T18:12:00.000Z", "Samu")
    answer.append(str(path), "Q1", "info", "2026-10-30T18:13:00.000Z", None)
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert lines == [
        {"id": "Q1", "answer": "accept", "ts": "2026-10-30T18:12:00.000Z", "session": "Samu"},
        {"id": "Q1", "answer": "info", "ts": "2026-10-30T18:13:00.000Z", "session": None},
    ]


def test_an_unknown_answer_writes_nothing(tmp_path):
    path = tmp_path / "board-answers.jsonl"
    with pytest.raises(ValueError):
        answer.append(str(path), "Q1", "yes", "t", "Samu")
    assert not path.exists()


def test_main_takes_the_session_as_optional_last_argument(tmp_path):
    path = tmp_path / "a.jsonl"
    assert answer.main(["answer.py", str(path), "Q2", "discuss", "t"]) == 0
    assert json.loads(path.read_text())["session"] is None
    assert answer.main(["answer.py", str(path)]) == 2
