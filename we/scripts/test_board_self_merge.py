"""board_self_merge.py and `board.py self-merge`: the self-merge notices of a repo's self-merge
window mirrored as board news, in the judge's grammar (`fixtures/brake-self-merge/judge.json`)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import board
import board_self_merge as sm
import pytest

JUDGE = json.loads(
    (Path(__file__).parent / "fixtures" / "brake-self-merge" / "judge.json").read_text()
)
HEAD = "a" * 40
NOW = datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc)


def comment(cid=901, body=None, login="github-actions[bot]", at="2026-11-07T08:00:00Z"):
    return {
        "id": cid,
        "user": {"login": login},
        "body": JUDGE["notice_sample"] if body is None else body,
        "created_at": at,
    }


def fake_gh(prs, comments, fail=None):
    calls = []

    def gh(args):
        calls.append(args)
        if fail and fail in args:
            raise sm.SelfMergeError("HTTP 502")
        if args[:2] == ["pr", "list"]:
            assert args[args.index("--label") + 1] == JUDGE["one_way_label"]
            return json.dumps(prs)
        if args[0] == "api":
            number = int(args[-1].split("/")[-2])
            return json.dumps([comments.get(number, [])])
        raise AssertionError(args)

    gh.calls = calls
    return gh


PR = {"number": 77, "url": "https://github.com/o/r/pull/77", "headRefOid": HEAD}


def test_the_judges_sample_notice_becomes_one_news_item():
    notices = sm.read_notices("o/r", fake_gh([PR], {77: [comment()]}))
    assert notices == [
        {
            "comment": 901,
            "class": "money",
            "merge_at": "2026-11-07T10:00Z",
            "created_at": "2026-11-07T08:00:00Z",
            "repo": "o/r",
            "number": 77,
            "url": PR["url"],
        }
    ]
    b = {}
    added = sm.merge(b, notices, ["o/r"], NOW)
    assert [i["id"] for i in added] == ["SM77-901"]
    item = b["news"][0]
    assert item["kind"] == "info"
    assert item["title"] == "self-merge window: #77 · one-way money · merges at 2026-11-07T10:00Z"
    assert PR["url"] in item["body"] and "`veto`" in item["body"]
    assert b["self_merge"]["seen"] == ["SM77-901"]


@pytest.mark.parametrize(
    "bad",
    [
        comment(login="weside-agent[bot]"),  # not the workflow's author
        comment(body=JUDGE["notice_sample"].replace("a" * 40, "b" * 40)),  # an older head
        comment(body="a plain comment"),  # no marker
    ],
    ids=["author", "old-head", "no-marker"],
)
def test_what_is_no_notice_never_reaches_the_board(bad):
    """Red arm: the same comment with one condition flipped is no notice."""
    assert sm.read_notices("o/r", fake_gh([PR], {77: [bad]})) == []


def test_a_notice_is_mirrored_once_even_after_the_owner_pruned_it():
    """Red arm: the seen list keeps a read and pruned item from coming back on the next sweep."""
    notices = sm.read_notices("o/r", fake_gh([PR], {77: [comment()]}))
    b = {}
    sm.merge(b, notices, ["o/r"], NOW)
    b["news"] = []  # read and pruned
    assert sm.merge(b, notices, ["o/r"], NOW) == []
    assert b["news"] == []


def test_a_new_notice_on_the_same_pr_is_a_new_item():
    """After a veto is lifted the workflow posts a new push line: a new comment, a new item."""
    b = {}
    sm.merge(b, sm.read_notices("o/r", fake_gh([PR], {77: [comment()]})), ["o/r"], NOW)
    later = comment(cid=955, at="2026-11-07T09:00:00Z")
    added = sm.merge(b, sm.read_notices("o/r", fake_gh([PR], {77: [later]})), ["o/r"], NOW)
    assert [i["id"] for i in added] == ["SM77-955"]
    assert [i["id"] for i in b["news"]] == ["SM77-955", "SM77-901"]


def test_a_failed_read_raises():
    with pytest.raises(sm.SelfMergeError):
        sm.read_notices("o/r", fake_gh([PR], {}, fail="api"))


def test_board_verb_writes_the_news_and_prints_lines(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(board, "_crew_repos", lambda *_a, **_k: ["o/r"])
    gh = fake_gh([PR], {77: [comment()]})
    monkeypatch.setattr(sm, "run_gh", gh)
    monkeypatch.setattr(sm.read_notices, "__defaults__", (gh,))
    assert board.main(["--board", str(state / "board.json"), "self-merge"]) == 0
    out = capsys.readouterr().out
    assert "self-merge: o/r#77 one-way money merges at 2026-11-07T10:00Z" in out
    assert "news: SM77-901" in out
    written = json.loads((state / "board.json").read_text())
    assert written["news"][0]["id"] == "SM77-901"
    assert written["self_merge"]["repos"] == ["o/r"]


def test_board_verb_fails_loud_and_keeps_the_board(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state"
    state.mkdir()
    (state / "board.json").write_text(json.dumps({"news": []}))
    monkeypatch.setattr(board, "_crew_repos", lambda *_a, **_k: ["o/r"])
    gh = fake_gh([PR], {}, fail="list")
    monkeypatch.setattr(sm.read_notices, "__defaults__", (gh,))
    assert board.main(["--board", str(state / "board.json"), "self-merge"]) == 1
    assert "board.py self-merge: o/r: HTTP 502" in capsys.readouterr().err
    assert json.loads((state / "board.json").read_text()) == {"news": []}
