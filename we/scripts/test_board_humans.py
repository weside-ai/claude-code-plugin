"""board.py with several humans: select's comment and red arms, signals, claim, ask --to and the
reply read back (docs/board.md § Several humans)."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import timedelta

import board
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
        "account_id": "5b10ac8d82e05b22cc7d4ef5",
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

    def test_without_humans_the_role_group_drops_and_one_fetch_serves(
        self, moving, monkeypatch, capsys
    ):
        """A crew without `humans`: any caller selects (no `role` group), and the select fetches
        origin once, bounded, for both the plan check and the tier (red arm: two fetches)."""
        green_lenses(moving)
        monkeypatch.setenv("WESIDE_COMPANION", "Otto")  # the coordinator, not product
        fetches = []
        real = subprocess.run

        def counting(argv, *a, **kw):
            if "fetch" in argv:
                fetches.append(kw.get("timeout"))
            return real(argv, *a, **kw)

        monkeypatch.setattr(subprocess, "run", counting)
        adapter = ticket_adapter.FakeAdapter({KEY: "Backlog"})
        assert act(moving, "select", KEY, adapter=adapter) == 0, capsys.readouterr().err
        assert adapter.calls[0] == ("move", KEY, "Selected for Development")
        assert adapter.calls[1][2].startswith("selected by coordinator@")
        assert len(fetches) == 1 and fetches[0], fetches


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
        bob = "bob@example.com"
        for comments in (
            [{"author": bob, "body": "claim product@bob Paula", "created": ago(hours=5)}],
            [
                {"author": bob, "body": "claim product@bob Paula", "created": ago(hours=2)},
                {"author": bob, "body": "release product@bob Paula", "created": ago(hours=1)},
            ],
        ):
            adapter = ticket_adapter.FakeAdapter(tickets={"PROJ-12": {"comments": comments}})
            assert act(crewed, "claim", "PROJ-12", adapter=adapter) == 0
            assert adapter.calls == [("comment", "PROJ-12", "claim coordinator@alice lead-12")]
        assert capsys.readouterr().out.startswith("PROJ-12: claim coordinator@alice lead-12")

    def test_a_claim_from_a_stranger_s_account_blocks_nothing(self, crewed, monkeypatch):
        """Red arm of the author filter: only a crew account's comment holds a claim."""
        with_humans(crewed)
        as_(monkeypatch, "alice", "Otto")
        for author in ("eve@example.com", "Bob", ""):
            comments = [{"body": "claim product@bob Paula", "created": ago(hours=1)}]
            if author:
                comments[0]["author"] = author
            adapter = ticket_adapter.FakeAdapter(tickets={"PROJ-12": {"comments": comments}})
            assert act(crewed, "claim", "PROJ-12", adapter=adapter) == 0, author
            assert adapter.calls == [("comment", "PROJ-12", "claim coordinator@alice lead-12")]

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
            {"op": "read", "key": "PROJ-12", "fields": "status,labels,comments"}
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
        assert item["to_name"] == "Bob"
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
        """A signed reply counts from an explicitly shared account; from a stranger or from
        another human's own account (red arm: alice signing for bob) it never does."""
        item = self.asked(crewed, monkeypatch, ticket_adapter.FakeAdapter())
        with_humans(crewed, shared_accounts=["ops@example.com"])
        later = NOW + timedelta(minutes=5)
        signed = {
            "labels": ["ask-bob"],
            "comments": [
                {
                    "author": "eve@example.com",
                    "body": "product@bob: accept",
                    "created": later.isoformat(),
                },
                {
                    "author": "alice@example.com",
                    "body": "product@bob: deny",
                    "created": later.isoformat(),
                },
                {
                    "author": "ops@example.com",
                    "body": "product@bob: rather next week",
                    "created": later.isoformat(),
                },
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

    def test_the_question_comment_is_never_its_own_answer(self, crewed, monkeypatch, capsys):
        """Red arm: the question comment, written from the asked human's account (one ticketing
        login on both machines), is no reply of theirs."""
        adapter = ticket_adapter.FakeAdapter()
        item = self.asked(crewed, monkeypatch, adapter)
        posted = next(c[2] for c in adapter.calls if c[0] == "comment")
        later = NOW + timedelta(minutes=5)
        ticket = {
            "labels": ["ask-bob"],
            "comments": [
                {
                    "author": "bob@example.com",
                    "body": posted,
                    "created": later.isoformat(),
                }
            ],
        }
        adapter = ticket_adapter.FakeAdapter(tickets={"PROJ-12": ticket})
        assert act(crewed, "signals", adapter=adapter, now=later) == 0
        assert f"answer {item['id']}" not in capsys.readouterr().out
        assert not (crewed / "board-answers.jsonl").exists()

    def test_a_display_name_is_no_account(self, crewed, monkeypatch):
        """Red arm: a stranger whose display name is a crew human's answers nothing, plain or
        signed; the Jira accountId of the human counts."""
        item = self.asked(crewed, monkeypatch, ticket_adapter.FakeAdapter())
        later = NOW + timedelta(minutes=5)
        spoofed = {
            "labels": ["ask-bob"],
            "comments": [
                {"author": "Bob", "body": "accept · go", "created": later.isoformat()},
                {"author": "Alice", "body": "product@bob: accept", "created": later.isoformat()},
            ],
        }
        adapter = ticket_adapter.FakeAdapter(tickets={"PROJ-12": spoofed})
        assert act(crewed, "signals", adapter=adapter, now=later) == 0
        assert jsonl(crewed / "board-answers.jsonl") == []
        by_id = {
            "labels": ["ask-bob"],
            "comments": [
                {
                    "author": "5b10ac8d82e05b22cc7d4ef5",
                    "body": "Deny: not tonight",
                    "created": later.isoformat(),
                }
            ],
        }
        adapter = ticket_adapter.FakeAdapter(tickets={"PROJ-12": by_id})
        assert act(crewed, "signals", adapter=adapter, now=later) == 0
        [line] = jsonl(crewed / "board-answers.jsonl")
        assert (line["id"], line["answer"]) == (item["id"], "deny")

    def test_a_comment_after_accept_is_no_answer(self, crewed, monkeypatch, capsys):
        """Red arm: `signals` reads only open questions; a closed one is neither read nor answered."""
        item = self.asked(crewed, monkeypatch, ticket_adapter.FakeAdapter())
        later = NOW + timedelta(hours=1)
        bob = "bob@example.com"
        ticket = {
            "labels": ["ask-bob"],
            "comments": [{"author": bob, "body": "accept", "created": later.isoformat()}],
        }
        adapter = ticket_adapter.FakeAdapter(tickets={"PROJ-12": ticket})
        assert act(crewed, "signals", adapter=adapter, now=later) == 0
        weeks = later + timedelta(days=20)
        ticket["comments"].append(
            {"author": bob, "body": "the logo is still blurry", "created": weeks.isoformat()}
        )
        adapter = ticket_adapter.FakeAdapter(tickets={"PROJ-12": ticket})
        assert act(crewed, "signals", adapter=adapter, now=weeks) == 0
        assert [a["answer"] for a in jsonl(crewed / "board-answers.jsonl")] == ["accept"]
        assert item["id"] in capsys.readouterr().out

    @pytest.mark.parametrize("kind", ["accept", "deny", "withdraw"])
    def test_a_closed_question_carries_no_read(self, crewed, monkeypatch, capsys, kind):
        """Every CLOSING kind ends the read-back, the pane's Withdraw included."""
        with_humans(crewed, ticketing="jira")
        answer_with(crewed, CLEAR)
        as_(monkeypatch, "alice", "Otto")
        assert act(crewed, *ask_argv(), "--to", "bob") == 0
        qid = board_of(crewed)["owner_queue"][-1]["id"]
        line = {"id": qid, "answer": kind, "ts": NOW.isoformat(), "session": None}
        with (crewed / "board-answers.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")
        capsys.readouterr()
        assert act(crewed, "signals") == 0
        assert [o["op"] for o in carry_of(capsys.readouterr().out)] == ["search"]

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


def test_a_read_without_labels_is_no_removed_label(crewed, monkeypatch, tmp_path, capsys):
    """Red arm of the label-off answer: a ticket read without `labels`, or left out, answers nothing."""
    with_humans(crewed, ticketing="jira")
    answer_with(crewed, CLEAR)
    as_(monkeypatch, "alice", "Otto")
    assert act(crewed, *ask_argv(), "--to", "bob") == 0
    reads = tmp_path / "reads.json"
    reads.write_text(json.dumps({"tickets": {"PROJ-12": {"comments": []}}}), encoding="utf-8")
    assert act(crewed, "signals", "--input", str(reads)) == 0
    assert jsonl(crewed / "board-answers.jsonl") == []
    reads.write_text(json.dumps({"hits": {}}), encoding="utf-8")
    capsys.readouterr()
    assert act(crewed, "signals", "--input", str(reads)) == 0
    assert carry_of(capsys.readouterr().out)[-1] == {
        "op": "read",
        "key": "PROJ-12",
        "fields": "status,labels,comments",
    }
    assert jsonl(crewed / "board-answers.jsonl") == []


# --- follow-ups: who, claims, signals, owners, Done, inbox, reply, withdraw ------------------


def two_sessions(state_dir, monkeypatch, name):
    """The agents list with a second session `name` of the same human, and this session it."""
    agents = state_dir / "agents.json"
    rows = [{"sessionId": "sid-12", "name": "lead-12"}, {"sessionId": "sid-13", "name": name}]
    agents.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sid-13")


class TestWhoAndClaims:
    def test_an_unknown_human_is_refused_not_written_as_unknown(self, crewed, monkeypatch, capsys):
        with_humans(crewed)
        monkeypatch.setenv("WESIDE_COMPANION", "Otto")
        monkeypatch.delenv("WE_HUMAN", raising=False)
        adapter = ticket_adapter.FakeAdapter()
        assert act(crewed, "claim", "PROJ-12", adapter=adapter) == 1
        err = capsys.readouterr().err
        assert "board.py claim: refused: several humans and none is this session's" in err
        assert adapter.calls == [] and not (crewed / "board-claims.jsonl").exists()

    def test_two_sessions_of_one_human_cannot_claim_the_same_ticket(
        self, crewed, monkeypatch, capsys
    ):
        with_humans(crewed)
        as_(monkeypatch, "alice", "Otto")
        assert act(crewed, "claim", "PROJ-12", adapter=ticket_adapter.FakeAdapter()) == 0
        two_sessions(crewed, monkeypatch, "lead-13")
        assert act(crewed, "claim", "PROJ-12", adapter=ticket_adapter.FakeAdapter()) == 1
        assert "claimed by coordinator@alice (lead-12)" in capsys.readouterr().err

    def test_a_quoted_claim_or_one_from_a_stranger_does_not_count(self, crewed, monkeypatch):
        with_humans(crewed)
        as_(monkeypatch, "alice", "Otto")
        comments = [
            {
                "author": "eve@example.com",
                "body": "claim product@bob Paula",
                "created": ago(hours=1),
            },
            {
                "author": "bob@example.com",
                "body": "As agreed:\nclaim product@bob Paula",
                "created": ago(hours=1),
            },
        ]
        adapter = ticket_adapter.FakeAdapter(tickets={"PROJ-12": {"comments": comments}})
        assert act(crewed, "claim", "PROJ-12", adapter=adapter) == 0

    def test_a_claim_counts_only_for_its_author_s_human_or_a_shared_account(
        self, crewed, monkeypatch, capsys
    ):
        """Red arm: a claim for bob written from alice's account holds nothing; from a shared
        account it holds."""
        with_humans(crewed, shared_accounts=["ops@example.com"])
        as_(monkeypatch, "alice", "Otto")
        foreign = [
            {
                "author": "alice@example.com",
                "body": "claim product@bob Paula",
                "created": ago(hours=1),
            }
        ]
        adapter = ticket_adapter.FakeAdapter(tickets={"PROJ-12": {"comments": foreign}})
        assert act(crewed, "claim", "PROJ-12", adapter=adapter) == 0
        two_sessions(crewed, monkeypatch, "lead-13")
        as_(monkeypatch, "bob", "Paula")
        held = [
            {
                "author": "ops@example.com",
                "body": "claim coordinator@alice x",
                "created": ago(hours=1),
            }
        ]
        adapter = ticket_adapter.FakeAdapter(tickets={"PROJ-12": {"comments": held}})
        assert act(crewed, "claim", "PROJ-12", adapter=adapter) == 1
        assert "claimed by coordinator@alice" in capsys.readouterr().err


class TestSignalWithoutChange:
    def test_a_hit_without_change_time_signals_again_after_its_window(
        self, crewed, monkeypatch, capsys
    ):
        with_humans(crewed)
        as_(monkeypatch, "alice", "Otto")
        adapter = ticket_adapter.FakeAdapter(searches={JQL: ["PROJ-12"]})
        assert act(crewed, "signals", adapter=adapter) == 0
        assert act(crewed, "signals", adapter=adapter, now=NOW + timedelta(minutes=20)) == 0
        assert "signals: nothing new" in capsys.readouterr().out.splitlines()[-1]
        assert act(crewed, "signals", adapter=adapter, now=NOW + timedelta(hours=2)) == 0
        assert "signal S2: PROJ-12" in capsys.readouterr().out

    def test_signals_are_refused_without_a_jql_scope(self, crewed, monkeypatch, capsys):
        """Red arm: an unset board.jql_scope would search every project of the ticketing system."""
        with_humans(crewed, jql_scope=None)
        as_(monkeypatch, "alice", "Otto")
        adapter = ticket_adapter.FakeAdapter()
        assert act(crewed, "signals", adapter=adapter) == 1
        assert "board.jql_scope is unset" in capsys.readouterr().err
        assert adapter.calls == []


SHARED = {
    "alice": {
        "name": "Alice",
        "email": "alice@example.com",
        "decides": ["money", "prod"],
        "owns_states": ["selected", "in_progress", "in_review"],
        "runs": ["coordinator", "architecture", "acceptance", "masters"],
    },
    "bob": {
        "name": "Bob",
        "email": "bob@example.com",
        "owns_states": ["backlog", "in_test"],
        "runs": ["product"],
        "companions": {"product": "Paula"},
    },
    "cleo": {
        "name": "Cleo",
        "email": "cleo@example.com",
        "owns_states": ["backlog", "in_test"],
        "runs": ["product"],
        "companions": {"product": "Pia"},
    },
}


def shared(state_dir, **board):
    with_humans(state_dir, **{"states": {"in_test": "In Test"}, **board})
    path = state_dir / "work" / ".weside" / "crew.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["humans"] = SHARED
    path.write_text(json.dumps(data), encoding="utf-8")


class TestOwners:
    def test_a_move_out_of_a_running_state_by_a_non_owner_names_the_question(
        self, moving, monkeypatch, capsys
    ):
        shared(moving)
        as_(monkeypatch, "bob", "Paula")
        adapter = ticket_adapter.FakeAdapter({KEY: "In Progress"})
        assert act(moving, "move", KEY, "on_hold", "--reopen", "later", adapter=adapter) == 1
        err = capsys.readouterr().err
        assert f"{KEY} is in_progress, owned by alice; this session works for bob" in err
        assert f"board.py ask --to alice --key {KEY}" in err
        assert adapter.calls == [] and transitions(moving) == []

    def test_the_owner_moves_and_the_ticket_status_is_the_source(self, moving, monkeypatch):
        shared(moving)
        as_(monkeypatch, "alice", "Otto")
        # no local `selected` row on this machine: the ticket's status counts
        adapter = ticket_adapter.FakeAdapter({KEY: "Selected for Development"})
        assert act(moving, "move", KEY, "in_progress", adapter=adapter) == 0
        assert transitions(moving)[-1]["from"] == "selected"

    def test_a_shared_state_lets_each_owner_move(self, moving, monkeypatch):
        shared(moving)
        for human, name in (("bob", "Paula"), ("cleo", "Pia")):
            as_(monkeypatch, human, name)
            adapter = ticket_adapter.FakeAdapter({KEY: "Backlog"})
            assert act(moving, "move", KEY, "on_hold", "--reopen", "q1", adapter=adapter) == 0

    def test_a_status_no_board_state_maps_is_refused(self, moving, monkeypatch, capsys):
        """Red arm: a ticket in "Blocked" has no known owner; the move is refused, never let
        through by the last local row."""
        shared(moving)
        as_(monkeypatch, "bob", "Paula")
        adapter = ticket_adapter.FakeAdapter({KEY: "Blocked"})
        assert act(moving, "move", KEY, "on_hold", "--reopen", "later", adapter=adapter) == 1
        assert "status 'Blocked' maps to no board state" in capsys.readouterr().err
        assert adapter.calls == [("ticket", KEY)] or all(c[0] != "move" for c in adapter.calls)
        assert transitions(moving) == []

    def test_jira_carries_the_status_read_before_a_move(self, moving, monkeypatch, capsys):
        shared(moving, ticketing="jira")
        as_(monkeypatch, "alice", "Otto")
        assert act(moving, "move", KEY, "in_progress") == 0
        assert carry_of(capsys.readouterr().out) == [
            {"op": "read", "key": KEY, "fields": "status,labels,comments"}
        ]
        assert transitions(moving) == []

    def test_select_needs_a_human_who_runs_product(self, moving, monkeypatch, capsys):
        shared(moving)
        committed(moving)
        green_lenses(moving)
        path = moving / "work" / ".weside" / "crew.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["humans"]["alice"]["owns_states"].append("backlog")
        path.write_text(json.dumps(data), encoding="utf-8")
        as_(monkeypatch, "alice", "Ada")  # product's member, on a machine that runs no product
        adapter = ticket_adapter.FakeAdapter({KEY: "Backlog"})
        assert act(moving, "select", KEY, adapter=adapter) == 1
        assert "alice does not run product" in capsys.readouterr().err
        assert adapter.calls == []


class TestDoneByHumans:
    def done(self, state_dir, status, adapter=None):
        adapter = adapter or ticket_adapter.FakeAdapter({KEY: status})
        path = state_dir / "comment.md"
        path.write_text("Walked on staging.\nNot proven: the native app\n", encoding="utf-8")
        return act(state_dir, "move", KEY, "done", "--comment-file", str(path), adapter=adapter)

    def test_done_from_in_test_by_its_owner(self, moving, monkeypatch):
        shared(moving)
        as_(monkeypatch, "cleo", "Pia")
        assert self.done(moving, "In Test") == 0
        assert transitions(moving)[-1]["from"] == "in_test"

    def test_done_from_in_review_is_refused_when_in_test_has_owners(
        self, moving, monkeypatch, capsys
    ):
        shared(moving)
        as_(monkeypatch, "alice", "Tess", role="acceptance")
        assert self.done(moving, "In Review") == 1
        assert "Done comes from in_test (owned by bob, cleo)" in capsys.readouterr().err

    def test_in_test_comes_from_in_review_by_its_owner(self, moving, monkeypatch, capsys):
        shared(moving)
        as_(monkeypatch, "alice", "Otto")
        adapter = ticket_adapter.FakeAdapter({KEY: "In Review"})
        assert act(moving, "move", KEY, "in_test", adapter=adapter) == 0
        assert adapter.calls == [("move", KEY, "In Test")]
        adapter = ticket_adapter.FakeAdapter({KEY: "In Progress"})
        assert act(moving, "move", KEY, "in_test", adapter=adapter) == 1
        assert "in_test needs the key to be in_review" in capsys.readouterr().err

    def test_in_test_is_refused_in_a_crew_that_maps_no_in_test(self, moving, monkeypatch, capsys):
        """Red arm: a crew without board.states.in_test (weside-core maps none) gets no move to a
        status its ticketing system lacks."""
        shared(moving, states={})
        as_(monkeypatch, "alice", "Otto")
        adapter = ticket_adapter.FakeAdapter({KEY: "In Review"})
        assert act(moving, "move", KEY, "in_test", adapter=adapter) == 1
        assert "maps no in_test status" in capsys.readouterr().err
        assert all(c[0] != "move" for c in adapter.calls)


class TestInboxReplyWithdraw:
    def test_inbox_lists_the_tickets_labelled_for_this_human(self, crewed, monkeypatch, capsys):
        with_humans(crewed)
        as_(monkeypatch, "bob", "Paula")
        jql = 'project = PROJ AND labels = "ask-bob"'
        adapter = ticket_adapter.FakeAdapter(searches={jql: ["PROJ-12", "PROJ-20"]})
        assert act(crewed, "inbox", adapter=adapter) == 0
        assert "inbox bob (ask-bob): PROJ-12, PROJ-20" in capsys.readouterr().out

    def test_reply_comments_signed_and_takes_the_label_off(self, crewed, monkeypatch, capsys):
        with_humans(crewed, ticketing="jira")
        as_(monkeypatch, "bob", "Paula")
        assert act(crewed, "reply", "PROJ-12", "accept", "--text", "go tonight") == 0
        assert carry_of(capsys.readouterr().out) == [
            {"op": "comment", "key": "PROJ-12", "text": "product@bob accept · go tonight"},
            {"op": "unlabel", "key": "PROJ-12", "remove": "ask-bob"},
        ]

    def test_another_human_of_the_same_role_does_not_answer(self, crewed, monkeypatch, capsys):
        """Red arm: cleo runs product like bob, yet only bob answers a question to bob."""
        shared(crewed)
        answer_with(crewed, CLEAR)
        as_(monkeypatch, "alice", "Otto")
        assert act(crewed, *ask_argv(), "--to", "bob", adapter=ticket_adapter.FakeAdapter()) == 0
        later = NOW + timedelta(hours=1)
        ticket = {
            "labels": ["ask-bob"],
            "comments": [
                {"author": "cleo@example.com", "body": "accept", "created": later.isoformat()}
            ],
        }
        adapter = ticket_adapter.FakeAdapter(tickets={"PROJ-12": ticket})
        assert act(crewed, "signals", adapter=adapter, now=later) == 0
        out = capsys.readouterr().out
        assert "accept from cleo" not in out and "answer " not in out

    def test_the_asker_withdraws_and_supersedes_its_own_question(self, crewed, monkeypatch):
        with_humans(crewed)
        answer_with(crewed, CLEAR)
        as_(monkeypatch, "alice", "Otto")
        adapter = ticket_adapter.FakeAdapter()
        assert act(crewed, *ask_argv(), "--to", "bob", adapter=adapter) == 0
        assert act(crewed, *ask_argv(), "--to", "bob", adapter=adapter) == 0
        first, second = [q["id"] for q in board_of(crewed)["owner_queue"]][-2:]
        adapter = ticket_adapter.FakeAdapter()
        assert act(crewed, "supersede", first, "--by", second, adapter=adapter) == 0
        assert ("unlabel", "PROJ-12", "ask-bob") in adapter.calls
        assert act(crewed, "withdraw", second, "--reason", "settled in chat") == 0
        assert [q["id"] for q in board_of(crewed)["owner_queue"]][-2:] != [first, second]
        assert first not in [q["id"] for q in board_of(crewed)["owner_queue"]]
        outcomes = [(q["id"], q["outcome"]) for q in jsonl(crewed / "board-questions.jsonl")]
        assert (first, "superseded") in outcomes and (second, "withdrawn") in outcomes

    def test_another_session_cannot_withdraw(self, crewed, monkeypatch, capsys):
        with_humans(crewed)
        answer_with(crewed, CLEAR)
        as_(monkeypatch, "bob", "Paula")
        assert act(crewed, *ask_argv()) == 0
        qid = board_of(crewed)["owner_queue"][-1]["id"]
        two_sessions(crewed, monkeypatch, "lead-13")
        assert act(crewed, "withdraw", qid) == 1
        assert "only its asker or the coordinator takes it back" in capsys.readouterr().err

    def test_the_asker_matches_in_any_case_and_unknown_never_does(
        self, crewed, monkeypatch, capsys
    ):
        with_humans(crewed)
        answer_with(crewed, CLEAR)
        as_(monkeypatch, "bob", "Paula")
        assert act(crewed, *ask_argv()) == 0
        qid = board_of(crewed)["owner_queue"][-1]["id"]
        path = crewed / "board.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["owner_queue"][-1]["session"] = "unknown"
        path.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(board, "_caller", lambda: "unknown")
        assert act(crewed, "withdraw", qid) == 1  # red arm: two nameless sessions are no match
        capsys.readouterr()
        data["owner_queue"][-1]["session"] = "LEAD-12"
        path.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(board, "_caller", lambda: "lead-12")
        assert act(crewed, "withdraw", qid) == 0


class TestMergeGoReadsTheTicket:
    def test_a_story_on_hold_gets_no_merge_go(self, crewed, monkeypatch, capsys):
        with_humans(crewed)
        answer_with(crewed, CLEAR)
        as_(monkeypatch, "alice", "Otto")
        argv = [*ask_argv(**{"--cause": "merge-go"}), "--pr", "acme/app#5"]
        adapter = ticket_adapter.FakeAdapter({"PROJ-12": "On Hold"})
        assert act(crewed, *argv, adapter=adapter) == 1
        assert "PROJ-12 is On Hold on the ticket" in capsys.readouterr().err
        adapter = ticket_adapter.FakeAdapter({"PROJ-12": "In Progress"})
        act(crewed, *argv, adapter=adapter)  # past the hold, the PR check decides
        assert "On Hold" not in capsys.readouterr().err


def test_a_reply_takes_off_only_the_own_label(crewed, monkeypatch, capsys):
    """Red arm: cleo's reply leaves bob's question label on the ticket."""
    shared(crewed, ticketing="jira")
    as_(monkeypatch, "cleo", "Pia")
    assert act(crewed, "reply", "PROJ-12", "accept") == 0
    removed = [o["remove"] for o in carry_of(capsys.readouterr().out) if o["op"] == "unlabel"]
    assert removed == ["ask-cleo"]
