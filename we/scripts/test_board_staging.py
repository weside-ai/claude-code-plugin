"""board.py book / unbook / staging: the staging booking and acceptance (docs/board.md § Staging).

A git work tree whose `origin` is acme/app holds the generic crew; the fake `claude` names the
calling session `lead-12`, the fake `gh` (fixtures/staging/gh) keeps the issues in a JSON file.
`fixtures/staging/issues.json` is the issue grammar the RC job writes and reads: acceptance #21
of v8.1.0-rc.3 opened 14 h before NOW, booking #22 of lead-7 expired an hour before NOW.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board  # noqa: E402
import board_staging  # noqa: E402

STAGING_BIN = HERE / "fixtures" / "staging"
CLAUDE_BIN = HERE / "fixtures" / "board"
ISSUES = STAGING_BIN / "issues.json"
CREW = HERE / "fixtures" / "crew-v2-generic.json"
NOW = datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc)
RC = "v8.1.0-rc.3"


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def env(tmp_path, monkeypatch):
    work = tmp_path / "work"
    (work / ".weside").mkdir(parents=True)
    shutil.copy(CREW, work / ".weside" / "crew.json")
    git(work, "init", "-q", "-b", "main")
    git(work, "remote", "add", "origin", "https://github.com/acme/app.git")
    monkeypatch.chdir(work)
    path = f"{STAGING_BIN}{os.pathsep}{CLAUDE_BIN}{os.pathsep}{os.environ['PATH']}"
    monkeypatch.setenv("PATH", path)
    monkeypatch.setenv("WE_ROLE", "master")
    monkeypatch.delenv("WESIDE_COMPANION", raising=False)
    monkeypatch.delenv("FAKE_GH_FAIL", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sid-12")
    agents = tmp_path / "agents.json"
    agents.write_text(json.dumps([{"sessionId": "sid-12", "name": "lead-12"}]), encoding="utf-8")
    monkeypatch.setenv("FAKE_AGENTS", str(agents))
    shutil.copy(ISSUES, tmp_path / "issues.json")
    monkeypatch.setenv("FAKE_GH_ISSUES", str(tmp_path / "issues.json"))
    monkeypatch.setenv("FAKE_GH_LOG", str(tmp_path / "gh-calls.jsonl"))
    (tmp_path / "board.json").write_text(json.dumps({"news": []}), encoding="utf-8")
    return tmp_path


def run(env, *argv, now=NOW):
    return board.main(["--board", str(env / "board.json"), *argv], now=now)


def issues(env):
    return {i["number"]: i for i in json.loads((env / "issues.json").read_text())["issues"]}


def edit_issues(env, change):
    path = env / "issues.json"
    data = json.loads(path.read_text())
    change(data["issues"])
    path.write_text(json.dumps(data))


def without_acceptance(env):
    edit_issues(env, lambda items: items.__setitem__(0, {**items[0], "state": "closed"}))


def calls(env, verb=None):
    path = env / "gh-calls.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    return [r for r in rows if verb is None or r[:2] == ["issue", verb]]


def board_file(env):
    return json.loads((env / "board.json").read_text())


def as_session(env, name):
    (env / "agents.json").write_text(json.dumps([{"sessionId": "sid-12", "name": name}]))


class TestBook:
    def test_an_open_acceptance_refuses_the_booking_naming_rc_and_since(self, env, capsys):
        assert run(env, "book", "staging", "--until", "2026-11-05T14:00Z") == 1
        assert capsys.readouterr().err.strip() == (
            f"board.py book: refused: {RC} in acceptance since 2026-11-04T20:00Z"
        )
        assert calls(env, "create") == []

    def test_without_acceptance_it_opens_one_booking_issue_and_writes_the_block(self, env, capsys):
        without_acceptance(env)
        assert run(env, "book", "staging", "--until", "2026-11-05T14:00Z") == 0
        [create] = calls(env, "create")
        assert create == [
            "issue",
            "create",
            "--repo",
            "acme/app",
            "--title",
            "staging booked by lead-12",
            "--label",
            "staging-booking",
            "--body",
            "holder: lead-12\nuntil: 2026-11-05T14:00Z\n",
        ]
        out = capsys.readouterr().out.splitlines()
        assert out[0] == (
            "booked staging for lead-12 until 2026-11-05T14:00Z: "
            "https://github.com/acme/app/issues/30"
        )
        assert out[1] == "staging: booked by lead-12 until 2026-11-05T14:00Z (#30)"
        block = board_file(env)["staging"]
        # lead-7's booking expired at 09:00: it neither blocks nor shows.
        assert block["booking"] == {"issue": 30, "holder": "lead-12", "until": "2026-11-05T14:00Z"}
        assert block["acceptance"] is None
        assert block["repo"] == "acme/app" and block["synced"] == "2026-11-05T10:00Z"

    def test_a_second_booking_while_one_is_open_is_refused_naming_its_holder(self, env, capsys):
        without_acceptance(env)
        assert run(env, "book", "staging", "--until", "2026-11-05T14:00Z") == 0
        as_session(env, "apps-3")
        capsys.readouterr()
        assert run(env, "book", "staging", "--until", "2026-11-05T16:00Z") == 1
        assert capsys.readouterr().err.strip() == (
            "board.py book: refused: booked by lead-12 until 2026-11-05T14:00Z (issue #30)"
        )
        assert len(calls(env, "create")) == 1

    def test_an_until_in_the_past_or_unreadable_is_refused(self, env, capsys):
        without_acceptance(env)
        assert run(env, "book", "staging", "--until", "2026-11-05T09:59Z") == 1
        assert capsys.readouterr().err.strip() == (
            "board.py book: refused: --until 2026-11-05T09:59Z is not in the future"
        )
        assert run(env, "book", "staging", "--until", "tomorrow") == 1
        assert capsys.readouterr().err.strip() == (
            "board.py book: refused: --until 'tomorrow' is no UTC time"
        )
        assert calls(env, "create") == []

    def test_an_unreadable_issue_list_refuses_fail_closed(self, env, capsys, monkeypatch):
        monkeypatch.setenv("FAKE_GH_FAIL", "list")
        assert run(env, "book", "staging", "--until", "2026-11-05T14:00Z") == 1
        assert capsys.readouterr().err.strip() == (
            "board.py book: refused: cannot read staging-acceptance issues (HTTP 502: gh broke)"
        )
        assert calls(env, "create") == []

    def test_a_booking_with_an_unreadable_until_blocks(self, env, capsys):
        without_acceptance(env)
        edit_issues(env, lambda items: items[1].update(body="holder: lead-7\nuntil: soon\n"))
        assert run(env, "book", "staging", "--until", "2026-11-05T14:00Z") == 1
        assert capsys.readouterr().err.strip() == (
            "board.py book: refused: booked by lead-7 until <unreadable> (issue #22)"
        )

    def test_the_repo_is_the_crew_files_origin_and_the_labels_come_from_the_crew(self, env):
        without_acceptance(env)
        crew_path = Path.cwd() / ".weside" / "crew.json"
        data = json.loads(crew_path.read_text())
        data["release"] = {**data.get("release", {}), "staging_booking_label": "slot"}
        crew_path.write_text(json.dumps(data))
        assert run(env, "book", "staging", "--until", "2026-11-05T14:00Z") == 0
        [create] = calls(env, "create")
        assert create[create.index("--label") + 1] == "slot"
        assert all(c[c.index("--repo") + 1] == "acme/app" for c in calls(env) if "--repo" in c)


class TestUnbook:
    def test_unbook_closes_the_callers_booking_early(self, env, capsys):
        without_acceptance(env)
        assert run(env, "book", "staging", "--until", "2026-11-05T14:00Z") == 0
        capsys.readouterr()
        assert run(env, "unbook") == 0
        out = capsys.readouterr().out.splitlines()
        assert out == ["closed booking of lead-12: #30", "staging: free"]
        assert issues(env)[30]["state"] == "closed"
        assert issues(env)[30]["comment"] == "unbooked 2026-11-05T10:00Z by lead-12"
        assert board_file(env)["staging"]["booking"] is None

    def test_unbook_leaves_another_sessions_booking_and_says_so(self, env, capsys):
        without_acceptance(env)
        assert run(env, "book", "staging", "--until", "2026-11-05T14:00Z") == 0
        as_session(env, "apps-3")
        capsys.readouterr()
        assert run(env, "unbook") == 1
        assert capsys.readouterr().err.strip() == (
            "board.py unbook: refused: apps-3 holds no open booking"
        )
        assert issues(env)[30]["state"] == "open"

    def test_unbook_rc_closes_that_rcs_acceptance(self, env, capsys):
        assert run(env, "unbook", RC) == 0
        out = capsys.readouterr().out.splitlines()
        assert out == [f"closed acceptance of {RC}: #21", "staging: free"]
        assert issues(env)[21]["state"] == "closed"
        assert issues(env)[21]["comment"] == "acceptance closed 2026-11-05T10:00Z by lead-12"
        assert board_file(env)["staging"]["acceptance"] is None

    def test_unbook_of_an_rc_without_acceptance_is_refused(self, env, capsys):
        assert run(env, "unbook", "v8.1.0-rc.2") == 1
        assert capsys.readouterr().err.strip() == (
            "board.py unbook: refused: no open acceptance for v8.1.0-rc.2"
        )
        assert calls(env, "close") == []


class TestStaging:
    def test_past_sla_acceptance_writes_one_news_item_for_the_coordinator(self, env, capsys):
        assert run(env, "staging") == 0
        out = capsys.readouterr().out.splitlines()
        assert out == [
            f"staging: {RC} in acceptance since 2026-11-04T20:00Z (#21), past 12 h",
            f"news: ST21 staging acceptance {RC} past 12 h",
        ]
        [item] = board_file(env)["news"]
        assert item == {
            "id": "ST21",
            "kind": "todo",
            "for": "coordinator",
            "title": f"staging acceptance {RC} past 12 h",
            "body": "opened 2026-11-04T20:00Z, issue #21 in acme/app",
            "ts": "2026-11-05T10:00:00Z",
        }
        acc = board_file(env)["staging"]["acceptance"]
        assert acc == {
            "issue": 21,
            "rc": RC,
            "opened": "2026-11-04T20:00Z",
            "due": "2026-11-05T08:00Z",
            "keys": "PROJ-12 PROJ-14",
            "past_sla": True,
            "news": "ST21",
        }

    def test_the_news_item_is_written_once_also_after_a_hotfix_carried_the_acceptance(
        self, env, capsys
    ):
        assert run(env, "staging") == 0
        board_path = env / "board.json"
        data = board_file(env)
        data["news"] = []  # the coordinator cleared the news; the block still remembers ST21
        board_path.write_text(json.dumps(data))

        def carry(items):
            items[0]["title"] = "v8.1.0-rc.4"
            items[0]["body"] = items[0]["body"].replace(RC, "v8.1.0-rc.4")

        edit_issues(env, carry)
        capsys.readouterr()
        assert run(env, "staging") == 0
        assert capsys.readouterr().out.splitlines() == [
            "staging: v8.1.0-rc.4 in acceptance since 2026-11-04T20:00Z (#21), past 12 h"
        ]
        assert board_file(env)["news"] == []
        assert board_file(env)["staging"]["acceptance"]["rc"] == "v8.1.0-rc.4"

    def test_a_fresh_acceptance_writes_no_news_and_the_label_alone_marks_it(self, env):
        early = datetime(2026, 11, 4, 21, 0, tzinfo=timezone.utc)
        assert run(env, "staging", now=early) == 0
        assert board_file(env)["news"] == []
        assert board_file(env)["staging"]["acceptance"]["past_sla"] is False
        edit_issues(env, lambda items: items[0]["labels"].append({"name": "past-sla"}))
        assert run(env, "staging", now=early) == 0
        assert [n["id"] for n in board_file(env)["news"]] == ["ST21"]

    def test_an_unreadable_list_exits_1_and_keeps_the_last_block(self, env, capsys, monkeypatch):
        assert run(env, "staging") == 0
        before = board_file(env)["staging"]
        monkeypatch.setenv("FAKE_GH_FAIL", "list")
        capsys.readouterr()
        assert run(env, "staging") == 1
        assert capsys.readouterr().err.strip() == (
            "board.py staging: cannot read staging-booking issues (HTTP 502: gh broke)"
        )
        assert board_file(env)["staging"] == before

    def test_no_github_origin_is_named(self, env, capsys):
        git(Path.cwd(), "remote", "set-url", "origin", "/srv/git/app.git")
        assert run(env, "staging") == 1
        assert capsys.readouterr().err.strip() == (
            "board.py staging: no GitHub origin for the crew's repo or the cwd"
        )


class TestGrammar:
    """The issue grammar shared with the RC job, pinned by the fixture text."""

    def test_the_fixture_bodies_parse_to_the_contract_fields(self):
        acc, booking = json.loads(ISSUES.read_text())["issues"]
        assert acc["body"] == "rc: v8.1.0-rc.3\nopened: 2026-11-04T20:00Z\nkeys: PROJ-12 PROJ-14\n"
        assert board_staging.body_field(booking["body"], "holder") == "lead-7"
        assert board_staging.parse_time(board_staging.body_field(booking["body"], "until")) == (
            datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
        )

    def test_crew_defaults_are_the_labels_and_hours_the_job_uses(self):
        assert board_staging.settings(board.crew_mod.DEFAULTS) == {
            "booking": "staging-booking",
            "acceptance": "staging-acceptance",
            "past_sla": "past-sla",
            "sla_hours": 12,
        }

    def test_a_crew_sla_of_zero_hours_stays_zero(self, env):
        crew_path = Path.cwd() / ".weside" / "crew.json"
        data = json.loads(crew_path.read_text())
        data["release"] = {**data.get("release", {}), "staging_sla_hours": 0}
        crew_path.write_text(json.dumps(data))
        assert run(env, "staging") == 0
        block = board_file(env)["staging"]
        assert block["sla_hours"] == 0
        assert block["acceptance"]["due"] == block["acceptance"]["opened"]
