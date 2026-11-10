"""accept.py: provenance before download, then the verdict carried onto the board (docs/board.md
§ Acceptance). The fixture verdict is the contract (fixtures/accept/accept_verdict.json)."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import accept  # noqa: E402
import board  # noqa: E402
import crew as crew_mod  # noqa: E402
import ticket_adapter  # noqa: E402
from test_board import NOW, crewed, crewless, jsonl, with_jira  # noqa: E402,F401

VERDICT = json.loads((HERE / "fixtures" / "accept" / "accept_verdict.json").read_text())
RUN_ID = "4242"
TAG = "v1.4.0-rc.2"
SHA = "a" * 40
WORKFLOW = ".github/workflows/release.yml"
RUN = {
    "id": 4242,
    "path": WORKFLOW,
    "event": "push",
    "head_branch": TAG,
    "head_sha": SHA,
    "html_url": "https://example.org/acme/app/actions/runs/4242",
}


class FakeGh:
    """The `gh` seam with fixed answers; `calls` records every read in order."""

    def __init__(
        self, run=None, verdict=None, artifacts=None, tags=None, main=None, ancestors=None
    ):
        self.run_meta = copy.deepcopy(RUN if run is None else run)
        self.verdict = copy.deepcopy(VERDICT if verdict is None else verdict)
        self.listed = (
            [{"name": f"staging-receipts-{TAG}", "expired": False}]
            if artifacts is None
            else artifacts
        )
        self.tags = {TAG: SHA} if tags is None else tags
        self.main = {WORKFLOW} if main is None else main
        self.ancestors = {SHA} if ancestors is None else ancestors
        self.calls = []

    def run(self, run_id):
        self.calls.append(("run", run_id))
        return copy.deepcopy(self.run_meta)

    def on_main(self, path):
        self.calls.append(("on_main", path))
        return path in self.main

    def tag_commit(self, tag):
        self.calls.append(("tag_commit", tag))
        return self.tags.get(tag)

    def is_ancestor(self, sha):
        self.calls.append(("is_ancestor", sha))
        return sha in self.ancestors

    def artifacts(self, run_id):
        self.calls.append(("artifacts", run_id))
        return self.listed

    def download(self, run_id, name, dest):
        self.calls.append(("download", run_id, name))
        path = Path(dest) / "accept.json"
        path.write_text(json.dumps(self.verdict), encoding="utf-8")
        return path


@pytest.fixture
def accepting(crewed):  # noqa: F811 (the fixture imported from test_board)
    """`work` as a git checkout with `.weside/config.json` naming the receipts workflow and the RC
    tag glob; the generic crew (coordinator `otto`, acceptance `tess`, member `ada`, `vic`)."""
    work = crewed / "work"
    (work / ".git").rmdir()
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    (work / ".weside" / "config.json").write_text(
        json.dumps({"acceptance": {"receipts_workflow": WORKFLOW, "rc_tag_glob": "v*-rc.*"}}),
        encoding="utf-8",
    )
    return crewed


def in_review(state_dir, *keys):
    state = board.StateDir(state_dir / "board.json")
    for key in keys:
        state.append_transition({"key": key, "to": "in_review"})


def accept_run(state_dir, gh, adapter=None, now=NOW):
    return accept.main(
        ["--board", str(state_dir / "board.json"), "run", "--run-id", RUN_ID],
        now=now,
        adapter=adapter,
        gh=gh,
    )


def queue(state_dir):
    return accept.main(["--board", str(state_dir / "board.json"), "queue"])


def rows(state_dir):
    return jsonl(state_dir / "board-transitions.jsonl")


def log(state_dir):
    return jsonl(state_dir / "board-accept.jsonl")


def carry_of(out):
    last = out.strip().splitlines()[-1]
    assert last.startswith("carry: "), out
    return json.loads(last[len("carry: ") :])


def only(*keys):
    v = copy.deepcopy(VERDICT)
    v["stories"] = [s for s in v["stories"] if s["key"] in keys]
    return v


class TestProvenance:
    @pytest.mark.parametrize(
        "gh, reason",
        [
            (
                lambda: FakeGh(run={**RUN, "path": ".github/workflows/branch.yml"}),
                "not the receipts workflow: .github/workflows/branch.yml",
            ),
            (lambda: FakeGh(main=set()), f"not the receipts workflow: {WORKFLOW}"),
            (
                lambda: FakeGh(run={**RUN, "event": "workflow_dispatch"}),
                f"not a push of an RC tag: workflow_dispatch {TAG}",
            ),
            (
                lambda: FakeGh(run={**RUN, "head_branch": "feat/x"}),
                "not a push of an RC tag: push feat/x",
            ),
            (
                lambda: FakeGh(tags={TAG: "b" * 40}),
                f"head_sha {SHA} is not the commit of {TAG}",
            ),
            (lambda: FakeGh(tags={}), f"head_sha {SHA} is not the commit of {TAG}"),
            (lambda: FakeGh(ancestors=set()), f"head_sha {SHA} of {TAG} is not on origin/main"),
        ],
    )
    def test_a_run_failing_a_condition_is_refused_before_any_download(
        self, accepting, capsys, gh, reason
    ):
        in_review(accepting, "PROJ-1")
        fake, adapter = gh(), ticket_adapter.FakeAdapter()
        assert accept_run(accepting, fake, adapter) == 1
        out, err = capsys.readouterr()
        assert err.strip() == f"refused: run {RUN_ID} {reason}"
        assert not [c for c in fake.calls if c[0] in ("artifacts", "download")]
        assert len(rows(accepting)) == 1 and log(accepting) == [] and adapter.calls == []
        assert "carry:" not in out

    @pytest.mark.parametrize(
        "change, names",
        [({"rc": "v1.4.0-rc.1"}, "v1.4.0-rc.1/4242"), ({"run_id": 4141}, f"{TAG}/4141")],
    )
    def test_a_verdict_naming_another_rc_or_run_is_refused(self, accepting, capsys, change, names):
        in_review(accepting, "PROJ-1")
        adapter = ticket_adapter.FakeAdapter()
        assert accept_run(accepting, FakeGh(verdict={**VERDICT, **change}), adapter) == 1
        out, err = capsys.readouterr()
        assert err.strip() == f"refused: run {RUN_ID} verdict names {names}, run is {TAG}/{RUN_ID}"
        assert len(rows(accepting)) == 1 and adapter.calls == [] and "carry:" not in out

    def test_a_path_with_its_ref_suffix_is_the_workflow(self, accepting):
        in_review(accepting, "PROJ-1")
        gh = FakeGh(run={**RUN, "path": f"{WORKFLOW}@refs/tags/{TAG}"}, verdict=only("PROJ-1"))
        assert accept_run(accepting, gh, ticket_adapter.FakeAdapter()) == 0

    def test_without_the_acceptance_config_it_exits_2_naming_it(self, accepting, capsys):
        (accepting / "work" / ".weside" / "config.json").write_text("{}", encoding="utf-8")
        assert accept_run(accepting, FakeGh()) == 2
        assert "acceptance.receipts_workflow and acceptance.rc_tag_glob not set" in (
            capsys.readouterr().err
        )


class TestExpired:
    @pytest.mark.parametrize(
        "listed",
        [[{"name": f"staging-receipts-{TAG}", "expired": True}], [], [{"name": "other"}]],
    )
    def test_expired_artifact_refuses(self, accepting, capsys, listed):
        in_review(accepting, "PROJ-1")
        gh = FakeGh(artifacts=listed)
        assert accept_run(accepting, gh, ticket_adapter.FakeAdapter()) == 1
        out, err = capsys.readouterr()
        assert err.strip() == f"refused: run {RUN_ID} verdict expired, rerun receipts on the RC"
        assert not [c for c in gh.calls if c[0] == "download"]
        assert len(rows(accepting)) == 1 and log(accepting) == [] and "carry:" not in out


class TestRunDone:
    def test_a_green_entry_moves_once_and_carries_transition_then_comment(self, accepting, capsys):
        with_jira(accepting)
        in_review(accepting, "PROJ-1")
        assert accept_run(accepting, FakeGh(verdict=only("PROJ-1"))) == 0
        out = capsys.readouterr().out
        row = rows(accepting)[-1]
        assert {k: row[k] for k in ("key", "from", "to", "via", "rc", "ticket")} == {
            "key": "PROJ-1",
            "from": "in_review",
            "to": "done",
            "via": "receipt",
            "rc": TAG,
            "ticket": "carried",
        }
        ops = carry_of(out)
        assert [(o["op"], o["key"]) for o in ops] == [
            ("transition", "PROJ-1"),
            ("comment", "PROJ-1"),
        ]
        assert ops[0]["status"] == "Done"
        kinds = [line.split(":")[0] for line in ops[1]["text"].splitlines()]
        assert kinds == [
            "Accepted by the receipts job " + TAG + " (https",
            "Oracle",
            "Persona",
        ] + ["Observed"] * 2 + ["Not proven"]

    def test_a_second_run_writes_nothing(self, accepting, capsys):
        with_jira(accepting)
        in_review(accepting, "PROJ-1")
        assert accept_run(accepting, FakeGh(verdict=only("PROJ-1"))) == 0
        capsys.readouterr()
        before = rows(accepting)
        assert accept_run(accepting, FakeGh(verdict=only("PROJ-1"))) == 0
        out = capsys.readouterr().out
        assert out.strip() == "skip: PROJ-1 already done"
        assert rows(accepting) == before

    def test_a_key_not_in_review_is_refused_and_the_run_goes_on(self, accepting, capsys):
        with_jira(accepting)
        board.StateDir(accepting / "board.json").append_transition(
            {"key": "PROJ-1", "to": "in_progress"}
        )
        assert accept_run(accepting, FakeGh(verdict=only("PROJ-1", "PROJ-5"))) == 1
        out, err = capsys.readouterr()
        assert "board.py move PROJ-1 done: refused: last move is in_progress, not in_review" in err
        assert [r["to"] for r in rows(accepting)] == ["in_progress"]
        assert "carry:" not in out and "hold: PROJ-5" in out


class TestWalkQueue:
    def test_a_walk_stays_in_review_and_is_queued_once_across_rcs(self, accepting, capsys):
        with_jira(accepting)
        in_review(accepting, "PROJ-2")
        assert accept_run(accepting, FakeGh(verdict=only("PROJ-2"))) == 0
        out = capsys.readouterr().out
        assert "carry:" not in out and len(rows(accepting)) == 1
        [line] = log(accepting)
        assert {k: line[k] for k in ("rc", "key", "outcome", "acs", "persona", "screen")} == {
            "rc": TAG,
            "key": "PROJ-2",
            "outcome": "walk",
            "acs": ["AC4"],
            "persona": "paid-user",
            "screen": "Settings",
        }
        assert queue(accepting) == 0
        assert capsys.readouterr().out.strip() == f"PROJ-2 AC4 paid-user · Settings (rc {TAG})"
        later = {**only("PROJ-2"), "rc": "v1.4.0-rc.3", "run_id": 4343}
        gh = FakeGh(
            run={**RUN, "id": 4343, "head_branch": "v1.4.0-rc.3"},
            tags={"v1.4.0-rc.3": SHA},
            artifacts=[{"name": "staging-receipts-v1.4.0-rc.3"}],
            verdict=later,
        )
        assert (
            accept.main(
                ["--board", str(accepting / "board.json"), "run", "--run-id", "4343"],
                now=NOW,
                gh=gh,
            )
            == 0
        )
        assert f"skip: PROJ-2 walk already queued (rc {TAG})" in capsys.readouterr().out
        assert len(log(accepting)) == 1

    def test_a_done_row_closes_the_queue_line(self, accepting, capsys):
        in_review(accepting, "PROJ-2")
        assert accept_run(accepting, FakeGh(verdict=only("PROJ-2"))) == 0
        path = accepting / "c.md"
        path.write_text("Walked it.\nNot proven: the small screen", encoding="utf-8")
        assert (
            board.main(
                [
                    "--board",
                    str(accepting / "board.json"),
                    "move",
                    "PROJ-2",
                    "done",
                    "--comment-file",
                    str(path),
                ],
                now=NOW,
            )
            == 0
        )
        capsys.readouterr()
        assert queue(accepting) == 0
        assert capsys.readouterr().out.strip() == "queue: empty"


class TestRedAndHold:
    @pytest.mark.parametrize(
        "owner, member", [("vic", "vic"), (None, "otto"), ("nobody", "otto"), ("Ada", "ada")]
    )
    def test_red_stays_in_review_and_routes_its_finding(self, accepting, capsys, owner, member):
        in_review(accepting, "PROJ-3")
        verdict = only("PROJ-3")
        verdict["stories"][0]["owner"] = owner
        assert accept_run(accepting, FakeGh(verdict=verdict)) == 0
        out = capsys.readouterr().out
        assert out.strip() == f"route: {member} PROJ-3 AC2-refund FAIL — 500 on POST /refund"
        [line] = log(accepting)
        assert (line["outcome"], line["owner"], line["finding"]) == (
            "red",
            member,
            "AC2-refund FAIL — 500 on POST /refund",
        )
        assert [r["to"] for r in rows(accepting)] == ["in_review"]

    @pytest.mark.parametrize(
        "reason",
        [
            "no plan",
            "AC2 has no oracle marker",
            "AC1 receipt check SKIP",
            "AC1 receipt check PLANNED",
            "no Not proven line",
        ],
    )
    def test_hold_names_its_reason_and_logs_it(self, accepting, capsys, reason):
        in_review(accepting, "PROJ-5")
        verdict = only("PROJ-5")
        verdict["stories"][0]["reason"] = reason
        assert accept_run(accepting, FakeGh(verdict=verdict)) == 0
        assert capsys.readouterr().out.strip() == f"hold: PROJ-5 {reason}"
        assert [(x["outcome"], x["reason"]) for x in log(accepting)] == [("hold", reason)]
        assert [r["to"] for r in rows(accepting)] == ["in_review"]

    def test_a_rerun_logs_red_and_hold_once_per_rc(self, accepting, capsys):
        in_review(accepting, "PROJ-3", "PROJ-5")
        for _ in range(2):
            assert accept_run(accepting, FakeGh(verdict=only("PROJ-3", "PROJ-5"))) == 0
        assert "skip: PROJ-3 red already recorded for" in capsys.readouterr().out
        assert [x["key"] for x in log(accepting)] == ["PROJ-3", "PROJ-5"]

    def test_the_whole_fixture_in_one_run(self, accepting, capsys):
        with_jira(accepting)
        in_review(accepting, "PROJ-1", "PROJ-2", "PROJ-3", "PROJ-5")
        assert accept_run(accepting, FakeGh()) == 0
        out = capsys.readouterr().out.strip().splitlines()
        assert out[-1].startswith("carry: ")
        assert sum(1 for line in out if line.startswith("carry:")) == 1
        assert [x["outcome"] for x in log(accepting)] == ["walk", "red", "hold"]
        assert [(o["op"], o["key"]) for o in carry_of("\n".join(out))] == [
            ("transition", "PROJ-1"),
            ("comment", "PROJ-1"),
        ]


class TestGhSeam:
    def test_tag_commit_prefers_the_peeled_line(self, monkeypatch):
        out = f"{'c' * 40}\trefs/tags/{TAG}\n{SHA}\trefs/tags/{TAG}^{{}}\n"
        monkeypatch.setattr(
            accept.Gh,
            "_out",
            lambda _self, argv, _what: subprocess.CompletedProcess(argv, 0, out, ""),
        )
        assert accept.Gh().tag_commit(TAG) == SHA

    def test_a_lightweight_tag_is_its_own_commit(self, monkeypatch):
        out = f"{SHA}\trefs/tags/{TAG}\n"
        monkeypatch.setattr(
            accept.Gh,
            "_out",
            lambda _self, argv, _what: subprocess.CompletedProcess(argv, 0, out, ""),
        )
        assert accept.Gh().tag_commit(TAG) == SHA


def test_without_board_queue_reads_the_crews_board(crewed, capsys, monkeypatch):  # noqa: F811
    """A second crew's /we:accept reads its own <stem>-accept.jsonl, never the default board's."""
    monkeypatch.setattr(board, "DEFAULT_BOARD", str(crewed / "board.json"))
    crew_file = crewed / "work" / ".weside" / "crew.json"
    data = json.loads(crew_file.read_text())
    data["board"] = {**(data.get("board") or {}), "file": "../../acme-board.json"}
    crew_file.write_text(json.dumps(data))
    walk = {"rc": "v1", "outcome": "walk", "acs": ["AC1"], "persona": "p", "screen": "s"}
    (crewed / "board-accept.jsonl").write_text(json.dumps({**walk, "key": "PROJ-1"}) + "\n")
    (crewed / "acme-board-accept.jsonl").write_text(json.dumps({**walk, "key": "PROJ-7"}) + "\n")
    assert accept.main(["queue"]) == 0
    assert capsys.readouterr().out.strip() == "PROJ-7 AC1 p · s (rc v1)"


def test_run_on_a_board_another_crew_stamped_is_refused(crewed, capsys, monkeypatch):  # noqa: F811
    """Review 09.11.: accept writes the board family like board.py does, so the same crew guard."""
    target = crewed / "board.json"
    monkeypatch.setattr(board, "DEFAULT_BOARD", str(target))
    target.write_text("{}")
    crew_mod.write_stamp(target, "acme/other-crew")
    assert accept.main(["--board", str(target), "run", "--run-id", "1"]) == 3
    assert "acme/other-crew" in capsys.readouterr().err
