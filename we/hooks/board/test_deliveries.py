"""deliveries.py only appends checked rows: earlier lines stay, a bad row writes nothing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deliveries

ROW = {
    "id": "Q1",
    "answer_ts": "2026-11-03T16:00:00.000Z",
    "to": "asker",
    "role": "asker",
    "click_ts": "2026-11-03T16:00:00.000Z",
    "ts": "2026-11-03T16:00:03.000Z",
    "delivered": True,
}


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_append_keeps_what_the_file_holds(tmp_path):
    path = tmp_path / "we-state" / "board-deliveries.jsonl"
    deliveries.append(str(path), [{"epoch": "2026-11-03T15:00:00.000Z"}])
    deliveries.append(str(path), [ROW, {**ROW, "role": "coordinator", "to": "coord"}])
    assert lines(path) == [
        {"epoch": "2026-11-03T15:00:00.000Z"},
        ROW,
        {**ROW, "role": "coordinator", "to": "coord"},
    ]


@pytest.mark.parametrize(
    "bad",
    [
        {**ROW, "role": "reader"},
        {**ROW, "delivered": "yes"},
        {**ROW, "reason": 3},
        {**ROW, "extra": 1},
        {k: v for k, v in ROW.items() if k != "click_ts"},
        {"epoch": ""},
        ["Q1"],
    ],
)
def test_a_bad_row_writes_nothing_not_even_the_good_ones(tmp_path, bad):
    path = tmp_path / "board-deliveries.jsonl"
    with pytest.raises(ValueError):
        deliveries.append(str(path), [ROW, bad])
    assert not path.exists()


def test_main_appends_each_argument_as_one_row_and_refuses_with_exit_1(tmp_path, capsys):
    path = tmp_path / "d.jsonl"
    refused = {**ROW, "delivered": False, "reason": "No agent named 'asker' is reachable."}
    assert deliveries.main(["deliveries.py", "append", str(path), json.dumps(refused)]) == 0
    assert lines(path) == [refused]
    assert deliveries.main(["deliveries.py", "append", str(path), json.dumps({"id": 1})]) == 1
    assert "id must be a string" in capsys.readouterr().err
    assert deliveries.main(["deliveries.py", "rewrite", str(path), "{}"]) == 2
    assert lines(path) == [refused]


def test_the_held_notice_fixture_is_the_text_the_delivery_tests_raise():
    here = Path(__file__).resolve().parent
    notice = (here / "fixtures" / "delivery-notice.txt").read_text(encoding="utf-8").strip()
    assert notice.startswith("[Cross-session delivery notice]")
    assert "'" not in notice
    assert f"'{notice}'" in (here / "deliver.test.ts").read_text(encoding="utf-8")


def test_an_owner_copy_is_a_ledger_row(tmp_path):
    """Claude Review on #201: the deliverer writes `owner` rows; refusing them sent the copy again
    on every tick."""
    path = tmp_path / "board-deliveries.jsonl"
    deliveries.append(str(path), [{**ROW, "role": "owner", "to": "ada"}])
    assert json.loads(path.read_text())["role"] == "owner"
