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


@pytest.mark.usefixtures("fake_gh")
class TestFreezeVerbs:
    """Cases that need the fake `gh` only on PATH."""

    def test_a_failed_listing_still_freezes(self, state_dir):
        assert run(state_dir, "freeze", "--reason", "r", "--repo", "o/broken") == 0
        flag = json.loads((state_dir / "freeze.json").read_text())
        assert flag["not_disarmed"] == [{"repo": "o/broken", "why": "listing the open PRs failed"}]

    def test_the_default_repo_is_the_current_one(self, state_dir):
        assert run(state_dir, "freeze", "--reason", "r") == 0
        assert json.loads((state_dir / "freeze.json").read_text())["repos"] == ["o/here"]

    def test_a_blank_reason_is_refused(self, state_dir, capsys):
        assert run(state_dir, "freeze", "--reason", " ", "--repo", "o/r") == 1
        assert "a freeze needs a reason" in capsys.readouterr().err
        assert not (state_dir / "freeze.json").exists()

    def test_the_hook_reads_what_freeze_writes(self, state_dir):
        run(state_dir, "freeze", "--reason", "incident", "--repo", "o/r")
        flag = board_freeze.read_flag(board_freeze.flag_path(state_dir / "board.json"))
        assert flag["reason"] == "incident"


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

    def test_unfreeze_removes_the_flag_and_rearms_nothing(self, state_dir, fake_gh, capsys):
        run(state_dir, "freeze", "--reason", "incident", "--repo", "o/r")
        capsys.readouterr()
        before = len(fake_gh())
        assert run(state_dir, "unfreeze") == 0
        out = capsys.readouterr().out
        assert "re-arm through the hook: o/r#5" in out
        assert not (state_dir / "freeze.json").exists()
        assert len(fake_gh()) == before

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
