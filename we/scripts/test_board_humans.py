"""board.py with several humans: select's comment and red arms, signals, claim, ask --to and the
reply read back (docs/board.md § Several humans)."""

from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
import test_board as tb
import ticket_adapter

CLEAR, KEY, NOW = tb.CLEAR, tb.KEY, tb.NOW
act, answer_with, ask_argv, board_of = tb.act, tb.answer_with, tb.ask_argv, tb.board_of
carry_of, git, green_lenses, jsonl, transitions = (
    tb.carry_of,
    tb.git,
    tb.green_lenses,
    tb.jsonl,
    tb.transitions,
)
crewless, crewed, moving = tb.crewless, tb.crewed, tb.moving  # the fixtures

HUMANS = {
    "alice": {
        "name": "Alice",
        "email": "alice@example.com",
        "owns_states": ["selected", "in_progress", "in_review"],
        "runs": ["coordinator", "architecture", "acceptance", "masters"],
    },
    "bob": {
        "name": "Bob",
        "email": "bob@example.com",
        "owns_states": ["backlog"],
        "runs": ["product"],
        "companions": {"product": "Paula"},
    },
}
SIGNALS = [{"state": "selected", "role": "coordinator", "jql_window": "35m"}]
JQL = 'project = PROJ AND status changed to "Selected for Development" after -35m'


def with_humans(state_dir, **board):
    path = state_dir / "work" / ".weside" / "crew.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["humans"] = HUMANS
    data["board"] = {
        "signals": SIGNALS,
        "jql_scope": "project = PROJ",
        **board,
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def as_(monkeypatch, human, companion=None, role=None):
    monkeypatch.setenv("WE_HUMAN", human)
    if companion:
        monkeypatch.setenv("WESIDE_COMPANION", companion)
    if role:
        monkeypatch.setenv("WE_ROLE_ID", role)


def ago(**delta):
    return (NOW - timedelta(**delta)).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


def committed(state_dir):
    work = state_dir / "work"
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "crew")
    git(work, "update-ref", "refs/remotes/origin/main", "HEAD")


# --- select ----------------------------------------------------------------------------------


class TestSelect:
    def test_a_green_select_comments_who_selected_with_plan_and_panel(self, moving, monkeypatch):
        with_humans(moving)
        committed(moving)
        green_lenses(moving)
        as_(monkeypatch, "bob", "Paula")
        adapter = ticket_adapter.FakeAdapter({KEY: "Backlog"})
        assert act(moving, "select", KEY, adapter=adapter) == 0
        blob = git(moving / "work", "rev-parse", f"origin/main:docs/plans/{KEY}-story.md")
        assert adapter.calls == [
            ("move", KEY, "Selected for Development"),
            (
                "comment",
                KEY,
                f"selected by product@bob, plan {blob.strip()[:12]}, panel ready-{KEY}",
            ),
        ]
        assert transitions(moving)[-1]["to"] == "selected"

    def test_another_role_than_product_is_refused(self, moving, monkeypatch, capsys):
        with_humans(moving)
        committed(moving)
        green_lenses(moving)
        as_(monkeypatch, "alice", "Otto")
        adapter = ticket_adapter.FakeAdapter({KEY: "Backlog"})
        assert act(moving, "select", KEY, adapter=adapter) == 1
        err = capsys.readouterr().err
        assert f"board.py select {KEY}: refused (role)" in err
        assert "this session is coordinator" in err
        assert adapter.calls == [] and transitions(moving) == []

    def test_a_plan_not_on_main_is_refused(self, moving, monkeypatch, capsys):
        with_humans(moving)
        work = moving / "work"
        plan = work / "docs" / "plans" / f"{KEY}-story.md"
        text = plan.read_text(encoding="utf-8")
        git(work, "rm", "-q", str(plan))
        committed(moving)
        plan.write_text(text, encoding="utf-8")
        as_(monkeypatch, "bob", "Paula")
        adapter = ticket_adapter.FakeAdapter({KEY: "Backlog"})
        assert act(moving, "select", KEY, adapter=adapter) == 1
        err = capsys.readouterr().err
        assert f"board.py select {KEY}: refused (plan on main)" in err
        assert f"plan docs/plans/{KEY}-story.md is not on origin/main" in err
        assert adapter.calls == []

    def test_a_red_panel_is_refused(self, moving, monkeypatch, capsys):
        with_humans(moving)
        committed(moving)
        as_(monkeypatch, "bob", "Paula")
        adapter = ticket_adapter.FakeAdapter({KEY: "Backlog"})
        assert act(moving, "select", KEY, adapter=adapter) == 1
        assert f"board.py select {KEY}: refused (lenses)" in capsys.readouterr().err
        assert adapter.calls == []


# --- signals ---------------------------------------------------------------------------------


class TestSignals:
    def test_hits_become_news_for_the_owning_role_once(self, crewed, monkeypatch, capsys):
        with_humans(crewed)
        as_(monkeypatch, "alice", "Otto")
        hits = ["PROJ-12", {"key": "PROJ-13", "changed": ago(minutes=10)}]
        adapter = ticket_adapter.FakeAdapter(searches={JQL: hits})
        assert act(crewed, "signals", adapter=adapter) == 0
        out = capsys.readouterr().out
        assert "signal S1: PROJ-12 → Selected for Development (signal for coordinator)" in out
        news = [n for n in board_of(crewed)["news"] if n["id"].startswith("S")]
        assert [(n["id"], n["for"], n["key"], n["kind"]) for n in news] == [
            ("S1", "coordinator", "PROJ-12", "todo"),
            ("S2", "coordinator", "PROJ-13", "todo"),
        ]
        assert act(crewed, "signals", adapter=adapter) == 0
        assert "signals: nothing new" in capsys.readouterr().out
        assert len([n for n in board_of(crewed)["news"] if n["id"].startswith("S")]) == 2
        # the same ticket selected again later is a new transition
        again = ticket_adapter.FakeAdapter(
            searches={JQL: [{"key": "PROJ-13", "changed": ago(minutes=1)}]}
        )
        assert act(crewed, "signals", adapter=again) == 0
        assert "signal S3: PROJ-13" in capsys.readouterr().out

    def test_a_human_who_runs_no_signalled_role_searches_nothing(
        self, crewed, monkeypatch, capsys
    ):
        with_humans(crewed)
        as_(monkeypatch, "bob", "Paula")
        adapter = ticket_adapter.FakeAdapter(searches={JQL: ["PROJ-12"]})
        assert act(crewed, "signals", adapter=adapter) == 0
        assert adapter.calls == []
        assert "signals: nothing new" in capsys.readouterr().out

    def test_jira_carries_the_search_then_reads_the_input(
        self, crewed, monkeypatch, capsys, tmp_path
    ):
        with_humans(crewed, ticketing="jira")
        as_(monkeypatch, "alice", "Otto")
        assert act(crewed, "signals") == 0
        out = capsys.readouterr().out
        assert carry_of(out) == [{"op": "search", "state": "selected", "jql": JQL}]
        assert not any(n["id"].startswith("S") for n in board_of(crewed)["news"])
        reads = tmp_path / "reads.json"
        reads.write_text(json.dumps({"hits": {"selected": ["PROJ-12"]}}), encoding="utf-8")
        assert act(crewed, "signals", "--input", str(reads)) == 0
        assert "signal S1: PROJ-12" in capsys.readouterr().out


# --- claim -----------------------------------------------------------------------------------


class TestClaim:
    def test_a_live_claim_of_another_human_refuses(self, crewed, monkeypatch, capsys):
        with_humans(crewed)
        as_(monkeypatch, "alice", "Otto")
        comments = [
            {
                "author": "bob@example.com",
                "body": "claim product@bob Paula",
                "created": ago(hours=1),
            }
        ]
        adapter = ticket_adapter.FakeAdapter(tickets={"PROJ-12": {"comments": comments}})
        assert act(crewed, "claim", "PROJ-12", adapter=adapter) == 1
        err = capsys.readouterr().err
        assert "board.py claim PROJ-12: refused: claimed by product@bob (Paula)" in err
        assert adapter.calls == []

    def test_an_old_or_released_claim_lets_the_next_claim(self, crewed, monkeypatch, capsys):
        with_humans(crewed)
        as_(monkeypatch, "alice", "Otto")
        for comments in (
            [{"body": "claim product@bob Paula", "created": ago(hours=5)}],
            [
                {"body": "claim product@bob Paula", "created": ago(hours=2)},
                {"body": "release product@bob Paula", "created": ago(hours=1)},
            ],
        ):
            adapter = ticket_adapter.FakeAdapter(tickets={"PROJ-12": {"comments": comments}})
            assert act(crewed, "claim", "PROJ-12", adapter=adapter) == 0
            assert adapter.calls == [("comment", "PROJ-12", "claim coordinator@alice lead-12")]
        assert capsys.readouterr().out.startswith("PROJ-12: claim coordinator@alice lead-12")

    def test_the_local_claim_counts_and_release_ends_it(self, crewed, monkeypatch, capsys):
        with_humans(crewed, claim_hours=2)
        as_(monkeypatch, "alice", "Otto")
        assert act(crewed, "claim", "PROJ-12", adapter=ticket_adapter.FakeAdapter()) == 0
        monkeypatch.setenv("WESIDE_COMPANION", "Tess")
        assert act(crewed, "claim", "PROJ-12", adapter=ticket_adapter.FakeAdapter()) == 1
        assert "claimed by coordinator@alice" in capsys.readouterr().err
        # a claim older than claim_hours is dead
        later = NOW + timedelta(hours=3)
        assert (
            act(crewed, "claim", "PROJ-12", adapter=ticket_adapter.FakeAdapter(), now=later) == 0
        )
        monkeypatch.setenv("WESIDE_COMPANION", "Otto")
        adapter = ticket_adapter.FakeAdapter()
        assert act(crewed, "claim", "PROJ-12", "--release", adapter=adapter) == 0
        assert adapter.calls == [("comment", "PROJ-12", "release coordinator@alice lead-12")]
        rows = jsonl(crewed / "board-claims.jsonl")
        assert [r["body"].split()[0] for r in rows] == ["claim", "claim", "release"]

    def test_jira_carries_the_read_first(self, crewed, monkeypatch, capsys):
        with_humans(crewed, ticketing="jira")
        as_(monkeypatch, "alice", "Otto")
        assert act(crewed, "claim", "PROJ-12") == 0
        assert carry_of(capsys.readouterr().out) == [
            {"op": "read", "key": "PROJ-12", "fields": "labels,comments"}
        ]
        assert not (crewed / "board-claims.jsonl").exists()


# --- ask --to --------------------------------------------------------------------------------


class TestAskTo:
    def asked(self, crewed, monkeypatch, adapter):
        with_humans(crewed)
        answer_with(crewed, CLEAR)
        as_(monkeypatch, "alice", "Otto")
        assert act(crewed, *ask_argv(), "--to", "bob", adapter=adapter) == 0
        return board_of(crewed)["owner_queue"][-1]

    def test_posts_the_question_as_a_ticket_comment_and_label(self, crewed, monkeypatch):
        adapter = ticket_adapter.FakeAdapter()
        item = self.asked(crewed, monkeypatch, adapter)
        assert item["to"] == "bob" and item["label"] == "ask-bob" and item["key"] == "PROJ-12"
        assert adapter.calls == [
            (
                "comment",
                "PROJ-12",
                "ASK to Bob · Should the new checkout page go live for all users tonight? · "
                "Advice: Yes, tonight; a rollback takes minutes.",
            ),
            ("label", "PROJ-12", "ask-bob"),
        ]

    def test_jira_carries_comment_then_label(self, crewed, monkeypatch, capsys):
        with_humans(crewed, ticketing="jira")
        answer_with(crewed, CLEAR)
        as_(monkeypatch, "alice", "Otto")
        assert act(crewed, *ask_argv(), "--to", "bob") == 0
        ops = carry_of(capsys.readouterr().out)
        assert [o["op"] for o in ops] == ["comment", "label"]
        assert ops[1] == {"op": "label", "key": "PROJ-12", "add": "ask-bob"}

    def test_a_reply_is_read_back_as_an_answer_once(self, crewed, monkeypatch, capsys):
        item = self.asked(crewed, monkeypatch, ticket_adapter.FakeAdapter())
        later = NOW + timedelta(hours=1)
        ticket = {
            "labels": ["ask-bob"],
            "comments": [
                {"author": "Alice", "body": "ASK to Bob · …", "created": NOW.isoformat()},
                {
                    "author": "bob@example.com",
                    "body": "accept · go tonight",
                    "created": later.isoformat(),
                },
            ],
        }
        adapter = ticket_adapter.FakeAdapter(tickets={"PROJ-12": ticket})
        assert act(crewed, "signals", adapter=adapter, now=later) == 0
        assert f"answer {item['id']}: accept from bob on PROJ-12" in capsys.readouterr().out
        [line] = jsonl(crewed / "board-answers.jsonl")
        assert (line["id"], line["answer"], line["via"]) == (item["id"], "accept", "ticket")
        assert line["quote"] == "accept · go tonight"
        assert act(crewed, "signals", adapter=adapter, now=later) == 0
        assert len(jsonl(crewed / "board-answers.jsonl")) == 1

    def test_a_signed_reply_and_a_removed_label(self, crewed, monkeypatch):
        item = self.asked(crewed, monkeypatch, ticket_adapter.FakeAdapter())
        later = NOW + timedelta(minutes=5)
        signed = {
            "labels": ["ask-bob"],
            "comments": [
                {
                    "author": "bot",
                    "body": "product@bob: rather next week",
                    "created": later.isoformat(),
                }
            ],
        }
        assert (
            act(
                crewed,
                "signals",
                adapter=ticket_adapter.FakeAdapter(tickets={"PROJ-12": signed}),
                now=later,
            )
            == 0
        )
        [line] = jsonl(crewed / "board-answers.jsonl")
        assert (line["answer"], line["quote"]) == ("discuss", "rather next week")
        bare = {"labels": [], "comments": []}
        assert (
            act(
                crewed,
                "signals",
                adapter=ticket_adapter.FakeAdapter(tickets={"PROJ-12": bare}),
                now=later,
            )
            == 0
        )
        lines = jsonl(crewed / "board-answers.jsonl")
        assert lines[-1]["answer"] == "update" and "label ask-bob removed" in lines[-1]["quote"]
        assert item["id"] == lines[-1]["id"]

    @pytest.mark.parametrize(
        "to, key, message",
        [
            ("eve", "PROJ-12", "--to 'eve' is no human of the crew"),
            ("bob", "checkout-v2", "--to asks on a ticket: --key must be a ticket key"),
        ],
    )
    def test_refusals(self, crewed, monkeypatch, capsys, to, key, message):
        with_humans(crewed)
        answer_with(crewed, CLEAR)
        as_(monkeypatch, "alice", "Otto")
        before = (crewed / "board.json").read_bytes()
        assert act(crewed, *ask_argv(**{"--key": key}), "--to", to) == 1
        assert message in capsys.readouterr().err
        assert (crewed / "board.json").read_bytes() == before

    def test_to_the_local_human_is_a_local_ask(self, crewed, monkeypatch, capsys):
        adapter = ticket_adapter.FakeAdapter()
        with_humans(crewed)
        answer_with(crewed, CLEAR)
        as_(monkeypatch, "alice", "Otto")
        assert act(crewed, *ask_argv(), "--to", "alice", adapter=adapter) == 0
        item = board_of(crewed)["owner_queue"][-1]
        assert "to" not in item and adapter.calls == []
        assert re.match(r"posted Q\d+", capsys.readouterr().out)
