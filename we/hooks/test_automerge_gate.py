"""Matrix for the auto-merge gate: `gh pr merge --auto` waits for a Codex verdict on the head.

The race it closes: auto-merge armed seconds after `gh pr create`, Codex posting BLOCKING after
the arm, the PR merged with the finding unread. `gh` is replaced by a fake; no network.

Run: `python3 -m pytest -q we/hooks/test_automerge_gate.py`
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).with_name("automerge_gate.py")
_spec = importlib.util.spec_from_file_location("automerge_gate", HOOK)
gate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["automerge_gate"] = gate  # dataclasses resolve their module by name
_spec.loader.exec_module(gate)

SHA = "abc123def4567890"
WORKFLOW = "name: Review\njobs:\n  publish:\n    name: Codex Review\n    runs-on: x\n"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/o/r.git"], cwd=tmp_path, check=True
    )
    first = _commit(tmp_path, {}, "root", allow_empty=True)
    _publish_main(tmp_path, first)
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "codex.yml").write_text(WORKFLOW)
    return tmp_path


def ruleset(*contexts: str) -> list[dict]:
    checks = [{"context": c, "integration_id": 15368} for c in contexts]
    return [
        {"type": "pull_request", "parameters": {}},
        {"type": "required_status_checks", "parameters": {"required_status_checks": checks}},
    ]


class FakeGh:
    def __init__(
        self,
        runs: list[dict] | None,
        comments: list[str] = (),
        fail: bool = False,
        rules: list[dict] | None = None,
        protection: list[str] | None = None,
        rules_fail: bool = False,
        body: str = "",
        head: str = SHA,
        node: dict | None = None,
        view_fail: bool = False,
        cards: list | None = None,
    ):
        self.runs, self.comments, self.fail, self.calls = runs, list(comments), fail, []
        self.body, self.head, self.node, self.view_fail = body, head, node, view_fail
        self.rules, self.protection, self.rules_fail = rules or [], protection, rules_fail
        # issue comments for the card read: a body (by a MEMBER) or (body, association, user type)
        self.cards = [c if isinstance(c, tuple) else (c, "MEMBER", "User") for c in cards or []]

    def __call__(self, args: list[str], _cwd: str | None) -> str | None:  # noqa: PLR0911
        self.calls.append(args)
        if self.fail:
            return None
        if args[:2] == ["pr", "view"] and "number,body" in args:
            return json.dumps({"number": 7, "body": self.body})
        if args[:2] == ["pr", "view"] and "comments" in args:
            return json.dumps({"comments": [{"body": b} for b in self.comments]})
        if args[:2] == ["pr", "view"] and self.view_fail:
            return None
        if args[:2] == ["api", "graphql"]:
            return None if self.node is None else json.dumps({"data": {"node": self.node}})
        if args[:2] == ["pr", "view"]:
            url = "https://github.com/o/r/pull/7"
            pr = {"headRefOid": self.head, "number": 7, "url": url, "baseRefName": "main"}
            return json.dumps(pr)
        if args[0] == "api" and args[1] == "repos/o/r/issues/7/comments":
            rows = [{"body": b, "assoc": a, "type": t} for b, a, t in self.cards]
            return "".join(json.dumps(r) + "\n" for r in rows)
        if args[0] == "api" and args[1].endswith("branches/main"):
            checks = {"contexts": self.protection or []}
            protection = {"protection": {"required_status_checks": checks}}
            body = self.rules if "/rules/" in args[1] else protection
            return None if self.rules_fail else json.dumps(body)
        if args[0] == "api":
            assert f"commits/{self.head}/check-runs" in args[1]
            return json.dumps({"check_runs": self.runs})
        raise AssertionError(args)


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path_factory, monkeypatch) -> Path:
    """No test reads the real board dir or the plugin's real lens_verdict.py."""
    state = tmp_path_factory.mktemp("state")
    monkeypatch.setattr(gate, "DEFAULT_BOARD", str(state / "board.json"))
    monkeypatch.setattr(gate, "LENS_VERDICT", state / "no-lens_verdict.py")
    return state


def refuse(repo: Path, command: str, fake: FakeGh, monkeypatch, **extra) -> str | None:
    monkeypatch.setattr(gate, "_gh", fake)
    payload = {"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": command}}
    payload.update(extra)
    return gate._refusal(payload)


def run(status: str = "completed", conclusion: str | None = "success", id_: int = 1) -> dict:
    return {"id": id_, "status": status, "conclusion": conclusion}


ARM = "gh pr merge 7 --auto --merge"


def test_arm_before_codex_reported_is_refused(repo: Path, monkeypatch) -> None:
    reason = refuse(repo, ARM, FakeGh(runs=[]), monkeypatch)
    assert reason is not None
    assert "no `Codex Review` check on head abc123def of PR #7 yet" in reason


@pytest.mark.parametrize("status", ["queued", "in_progress"])
def test_arm_while_codex_runs_is_refused(repo: Path, monkeypatch, status: str) -> None:
    reason = refuse(repo, ARM, FakeGh([run(status, None)]), monkeypatch)
    assert reason is not None and f"still {status}" in reason


def test_cancelled_run_has_no_verdict(repo: Path, monkeypatch) -> None:
    reason = refuse(repo, ARM, FakeGh([run(conclusion="cancelled")]), monkeypatch)
    assert reason is not None and "without a verdict" in reason


def test_verdict_error_is_refused(repo: Path, monkeypatch) -> None:
    fake = FakeGh([run(conclusion="failure")], ["<!-- codex-review -->\n<!-- VERDICT:ERROR -->"])
    reason = refuse(repo, ARM, fake, monkeypatch)
    assert reason is not None and "VERDICT:ERROR" in reason


def test_another_reviewers_verdict_is_not_codexs(repo: Path, monkeypatch) -> None:
    fake = FakeGh(
        [run(conclusion="failure")],
        [
            "<!-- codex-review -->\n<!-- VERDICT:ERROR -->",
            "<!-- claude-code-review -->\nCodex aside.\n<!-- VERDICT:PASS -->",
        ],
    )
    reason = refuse(repo, ARM, fake, monkeypatch)
    assert reason is not None and "VERDICT:ERROR" in reason


def test_blocking_is_a_verdict_and_passes(repo: Path, monkeypatch) -> None:
    fake = FakeGh(
        [run(conclusion="failure")], ["<!-- codex-review -->\n<!-- VERDICT:BLOCKING -->"]
    )
    assert refuse(repo, ARM, fake, monkeypatch) is None


def test_latest_rerun_decides(repo: Path, monkeypatch) -> None:
    fake = FakeGh([run(conclusion="cancelled", id_=1), run(conclusion="success", id_=2)])
    assert refuse(repo, ARM, fake, monkeypatch) is None


@pytest.mark.parametrize(
    "command",
    [
        "gh pr merge --auto --squash",
        "gh pr merge --squash --auto 7",
        "cd . && gh pr merge https://github.com/o/r/pull/7 --merge --auto",
        "GH_DEBUG=0 gh pr merge 7 --auto --merge",
        "timeout 30 gh pr merge 7 --auto --merge && echo done",
    ],
)
def test_auto_in_any_position_is_seen(repo: Path, monkeypatch, command: str) -> None:
    fake = FakeGh(runs=[])
    assert refuse(repo, command, fake, monkeypatch) is not None
    assert all("merge" not in call for call in fake.calls), fake.calls


def test_success_passes(repo: Path, monkeypatch) -> None:
    assert refuse(repo, ARM, FakeGh([run()]), monkeypatch) is None


def test_repo_without_codex_workflow_passes_offline(repo: Path, monkeypatch) -> None:
    (repo / ".github" / "workflows" / "codex.yml").unlink()
    fake = FakeGh(runs=[])
    assert refuse(repo, ARM, fake, monkeypatch) is None
    assert fake.calls == []


def test_configured_check_name_is_used(repo: Path, monkeypatch) -> None:
    (repo / ".weside").mkdir()
    (repo / ".weside" / "config.json").write_text(
        json.dumps({"review": {"codex_check": "AI Rev"}})
    )
    (repo / ".github" / "workflows" / "codex.yml").write_text("jobs:\n  a:\n    name: AI Rev\n")
    reason = refuse(repo, ARM, FakeGh(runs=[]), monkeypatch)
    assert reason is not None and "no `AI Rev` check" in reason


def test_required_codex_check_allows_the_arm_at_open(repo: Path, monkeypatch) -> None:
    fake = FakeGh(runs=[], rules=ruleset("CI Summary", "Codex Review"))
    assert refuse(repo, ARM, fake, monkeypatch) is None
    assert not any("check-runs" in " ".join(c) for c in fake.calls), fake.calls


def test_codex_check_in_classic_protection_allows_the_arm(repo: Path, monkeypatch) -> None:
    fake = FakeGh(runs=[], rules=ruleset("CI Summary"), protection=["Codex Review"])
    assert refuse(repo, ARM, fake, monkeypatch) is None


def test_configured_check_name_decides_the_requirement(repo: Path, monkeypatch) -> None:
    (repo / ".weside").mkdir()
    (repo / ".weside" / "config.json").write_text(
        json.dumps({"review": {"codex_check": "AI Rev"}})
    )
    (repo / ".github" / "workflows" / "codex.yml").write_text("jobs:\n  a:\n    name: AI Rev\n")
    assert refuse(repo, ARM, FakeGh(runs=[], rules=ruleset("AI Rev")), monkeypatch) is None
    reason = refuse(repo, ARM, FakeGh(runs=[], rules=ruleset("Codex Review")), monkeypatch)
    assert reason is not None and "no `AI Rev` check" in reason


def test_codex_check_not_required_waits_as_before(repo: Path, monkeypatch) -> None:
    fake = FakeGh(runs=[], rules=ruleset("CI Summary"), protection=["CI Summary"])
    reason = refuse(repo, ARM, fake, monkeypatch)
    assert reason is not None and "no `Codex Review` check on head abc123def" in reason


def test_rules_lookup_failure_keeps_todays_gate(repo: Path, monkeypatch) -> None:
    reason = refuse(repo, ARM, FakeGh(runs=[], rules_fail=True), monkeypatch)
    assert reason is not None and "no `Codex Review` check" in reason
    assert refuse(repo, ARM, FakeGh([run()], rules_fail=True), monkeypatch) is None


def test_gh_failure_fails_open(repo: Path, monkeypatch) -> None:
    assert refuse(repo, ARM, FakeGh(runs=[], fail=True), monkeypatch) is None


@pytest.mark.parametrize(
    "command",
    [
        "gh pr merge 7 --merge",
        "gh pr merge 7 --disable-auto",
        "echo 'gh pr merge 7 --auto'",
        "cat <<'EOF' > notes.md\ngh pr merge 7 --auto --merge\nEOF",
    ],
)
def test_not_an_arm_passes(repo: Path, monkeypatch, command: str) -> None:
    assert refuse(repo, command, FakeGh(runs=[]), monkeypatch) is None


@pytest.mark.parametrize("command", [ARM, "gh pr merge 7 --squash"])
def test_a_subagent_never_merges(repo: Path, monkeypatch, command: str) -> None:
    fake = FakeGh([run()])
    reason = refuse(repo, command, fake, monkeypatch, agent_id="a1", agent_type="we:dev-medium")
    assert reason is not None and "A worker never merges" in reason
    assert fake.calls == []


@pytest.mark.parametrize("command", [ARM, "gh pr merge 7 --squash"])
def test_a_process_worker_never_merges(repo: Path, monkeypatch, command: str) -> None:
    marker = {"name": "w1", "lead": "LEAD", "session_id": "s-w1"}
    (repo / ".git" / "we-worker.json").write_text(json.dumps(marker))
    fake = FakeGh([run()])
    reason = refuse(repo, command, fake, monkeypatch, session_id="s-w1")
    assert reason is not None and "A worker never merges" in reason
    assert fake.calls == []
    disarm = "gh pr merge 7 --disable-auto"
    assert refuse(repo, disarm, fake, monkeypatch, session_id="s-w1") is None
    reason = refuse(repo, command, fake, monkeypatch, session_id="s-lead")
    assert reason is None or "A worker never merges" not in reason


def test_a_subagent_may_disarm(repo: Path, monkeypatch) -> None:
    command = "gh pr merge 7 --disable-auto"
    assert refuse(repo, command, FakeGh([run()]), monkeypatch, agent_id="a1") is None


def test_hook_prints_a_deny(repo: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(gate, "_gh", FakeGh(runs=[]))
    payload = {"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": ARM}}
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(payload)))
    gate.main()
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


# The pre-merge receipt brake (`verification.pre_merge_receipt`).

RED = "## Verification\n\n- **Oracle:** cli\n\nreceipt red: `/c/r/x`\n"


def receipt_repo(repo: Path) -> Path:
    (repo / ".weside").mkdir(exist_ok=True)
    (repo / ".weside" / "config.json").write_text(
        json.dumps({"verification": {"pre_merge_receipt": "bash receipt.sh {KEY}"}})
    )
    return repo


@pytest.mark.parametrize(
    "line", ["receipt red: `/c/r/x`", "receipt red (not run: exit 3: backend down)"]
)
def test_a_red_receipt_refuses_the_arm_naming_the_line(repo: Path, monkeypatch, line: str) -> None:
    fake = FakeGh([run()], body=f"## Summary\n\n{line}\n")
    reason = refuse(receipt_repo(repo), ARM, fake, monkeypatch)
    assert reason is not None
    assert "receipt red on #7: run the pre-merge receipt green" in reason
    assert line in reason


def test_a_red_receipt_refuses_even_without_a_codex_workflow(repo: Path, monkeypatch) -> None:
    (repo / ".github" / "workflows" / "codex.yml").unlink()
    reason = refuse(receipt_repo(repo), ARM, FakeGh([run()], body=RED), monkeypatch)
    assert reason is not None and "receipt red on #7" in reason


@pytest.mark.parametrize(
    "body",
    [
        "receipt green: `/c/r/x`\n",
        "receipt green: `/c/r/x`\nreceipt not run on DEV: no DEV slot dev-usd-1\n",
        "## Summary\n\nNo receipt line.\n",
        "The last run said receipt red, fixed since.\n> receipt red: quoted\n",
        "```\nreceipt red: `/c/r/x`\n```\n",
    ],
)
def test_no_red_line_arms_as_today(repo: Path, monkeypatch, body: str) -> None:
    assert refuse(receipt_repo(repo), ARM, FakeGh([run()], body=body), monkeypatch) is None


def test_without_the_config_key_the_body_is_not_read(repo: Path, monkeypatch) -> None:
    fake = FakeGh([run()], body=RED)
    assert refuse(repo, ARM, fake, monkeypatch) is None
    assert not any("number,body" in call for call in fake.calls), fake.calls


def test_a_gh_failure_on_the_receipt_read_fails_open(repo: Path, monkeypatch) -> None:
    """Stated in the docstring: a brake against slips, not a barrier."""
    assert (
        refuse(receipt_repo(repo), ARM, FakeGh([run()], body=RED, fail=True), monkeypatch) is None
    )


def test_a_red_receipt_does_not_block_a_disarm(repo: Path, monkeypatch) -> None:
    disarm = "gh pr merge 7 --disable-auto"
    assert refuse(receipt_repo(repo), disarm, FakeGh([run()], body=RED), monkeypatch) is None


# The class, the call forms, the freeze and the T2 panel.

FAKE_CLASSIFIER = """#!/usr/bin/env bash
printf '%s\\n' "$*" > "$FAKE_LOG"
git rev-parse HEAD >> "$FAKE_LOG"
printf '%s\\nreview: high\\n' "$FAKE_CLASS"
exit "${FAKE_EXIT:-0}"
"""
CREW = {"version": 2, "human": {"name": "Ada"}, "risk": {"command": "bin/classify.sh"}}
NODE = {"number": 7, "repository": {"nameWithOwner": "o/r"}}


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return out.stdout.strip()


def _commit(repo: Path, files: dict[str, str], msg: str, allow_empty: bool = False) -> str:
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    _git(repo, "add", "-A")
    extra = ["--allow-empty"] if allow_empty else []
    _git(
        repo,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@x.invalid",
        "commit",
        "-q",
        *extra,
        "-m",
        msg,
    )
    return _git(repo, "rev-parse", "HEAD")


def _publish_main(repo: Path, sha: str) -> None:
    """`sha` becomes main on the repo's origin (a local bare repo standing in for github.com,
    through `url.<bare>.insteadOf`), so the hook's fetch of origin/main finds it."""
    bare = repo.parent / f"{repo.name}-origin.git"
    if not bare.exists():
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        _git(repo, "config", f"url.{bare.as_uri()}.insteadOf", "https://github.com/o/r.git")
    _git(repo, "push", "-q", "-f", "origin", f"{sha}:refs/heads/main")
    _git(repo, "update-ref", "refs/remotes/origin/main", sha)


@pytest.fixture()
def classed(repo: Path, monkeypatch, tmp_path_factory) -> dict:
    """`repo` whose origin/main carries a crew `risk.command`; a PR head on top of it."""
    log = tmp_path_factory.mktemp("log") / "classifier.log"
    main = _commit(
        repo,
        {
            ".weside/crew.json": json.dumps(CREW),
            "bin/classify.sh": FAKE_CLASSIFIER,
            "README.md": "x\n",
        },
        "main",
    )
    _publish_main(repo, main)
    head = _commit(repo, {"README.md": "y\n"}, "pr")
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("FAKE_CLASS", "T2 one-way money")
    monkeypatch.delenv("FAKE_EXIT", raising=False)
    return {"repo": repo, "main": main, "head": head, "log": log}


GRAPHQL_MERGE = (
    "gh api graphql -f query='mutation { mergePullRequest(input: "
    '{pullRequestId: "PR_kwDOabc"}) { clientMutationId } }\''
)
GRAPHQL_ARM = (
    "gh api graphql -f query='mutation { enablePullRequestAutoMerge(input: "
    '{pullRequestId: "PR_kwDOabc", mergeMethod: SQUASH}) { clientMutationId } }\''
)
FORMS = [
    ARM,
    "gh pr merge 7 --squash",
    "gh pr merge 7 --admin --squash",
    "gh api -X PUT repos/o/r/pulls/7/merge",
    "gh api --method PUT /repos/o/r/pulls/7/merge -f merge_method=squash",
    "gh api repos/o/r/pulls/7/merge -f merge_method=squash",
    GRAPHQL_MERGE,
    GRAPHQL_ARM,
    "echo 'Ada: merge du (Q999)' && gh pr merge 7 --squash",
]


@pytest.mark.parametrize("command", FORMS)
def test_one_way_is_refused_in_every_call_form(classed: dict, monkeypatch, command: str) -> None:
    fake = FakeGh([run()], head=classed["head"], node=NODE)
    reason = refuse(classed["repo"], command, fake, monkeypatch)
    assert reason is not None
    assert "`T2 one-way money`: one-way (money)" in reason
    assert "No session merges or arms it" in reason
    assert (
        "merges itself 2 h after a green T2 panel on its head, once Ada got the push line"
        in reason
    )
    assert "`veto` label stops it" in reason and "/we:lens t2 7" in reason
    assert "by hand" not in reason
    assert "hand over the link and the class" in reason
    assert "herself" not in reason and " her " not in reason
    assert "PR #7 (https://github.com/o/r/pull/7)" in reason
    assert not any(c[:2] == ["pr", "merge"] for c in fake.calls), fake.calls


def test_the_classifier_runs_mains_blob_on_merge_base_to_head(classed: dict, monkeypatch) -> None:
    fake = FakeGh([run()], head=classed["head"])
    assert refuse(classed["repo"], ARM, fake, monkeypatch) is not None
    args, ran_on = classed["log"].read_text().splitlines()
    assert args == classed["main"]
    assert ran_on == classed["head"]
    worktrees = _git(classed["repo"], "worktree", "list", "--porcelain")
    assert worktrees.count("worktree ") == 1, worktrees


def test_a_pr_that_rewrites_classifier_and_crew_is_classified_by_main(
    classed: dict, monkeypatch
) -> None:
    head = _commit(
        classed["repo"],
        {
            "bin/classify.sh": "#!/usr/bin/env bash\necho T0\n",
            ".weside/crew.json": json.dumps({"version": 2, "risk": {"command": None}}),
            ".weside/config.json": json.dumps({"risk": {"command": "true"}}),
        },
        "lower the brake",
    )
    fake = FakeGh([run()], head=head)
    reason = refuse(classed["repo"], ARM, fake, monkeypatch)
    assert reason is not None and "`T2 one-way money`" in reason


@pytest.mark.parametrize(
    ("env", "why"),
    [
        ({"FAKE_EXIT": "2"}, "the classifier exited 2"),
        ({"FAKE_CLASS": "critical-review"}, "the classifier exited 0: critical-review"),
        ({"FAKE_CLASS": "T2 one-way"}, "the classifier exited 0"),
    ],
)
def test_a_class_not_computed_refuses(classed: dict, monkeypatch, env: dict, why: str) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    reason = refuse(classed["repo"], ARM, FakeGh([run()], head=classed["head"]), monkeypatch)
    assert reason is not None
    assert reason.startswith("Merge refused, class not computed:")
    assert why in reason


def test_a_gh_failure_while_classifying_refuses(classed: dict, monkeypatch) -> None:
    fake = FakeGh([run()], head=classed["head"], view_fail=True)
    reason = refuse(classed["repo"], ARM, fake, monkeypatch)
    assert reason is not None and "class not computed: `gh pr view`" in reason


def test_an_unknown_head_refuses(classed: dict, monkeypatch) -> None:
    fake = FakeGh([run()], head="f" * 40)
    reason = refuse(classed["repo"], "gh pr merge 7 --squash", fake, monkeypatch)
    assert reason is not None and "class not computed: no merge base" in reason


@pytest.mark.parametrize(
    "command",
    [
        "gh pr merge 7 -R other/repo --squash",
        "gh -R other/repo pr merge 7 --squash",
        "gh pr merge https://github.com/other/repo/pull/7 --squash",
        "gh api -X PUT repos/other/repo/pulls/7/merge",
    ],
)
def test_a_repo_without_local_checkout_refuses(classed: dict, monkeypatch, command: str) -> None:
    reason = refuse(classed["repo"], command, FakeGh([run()]), monkeypatch)
    assert reason is not None and "no local checkout of other/repo" in reason


FOREIGN = [
    "gh pr merge 7 -R other/repo --squash",
    "gh -R other/repo pr merge 7 --squash",
    "gh pr merge https://github.com/other/repo/pull/7 --squash",
    "gh api -X PUT repos/other/repo/pulls/7/merge",
    'cd "$(git rev-parse --show-toplevel)" && gh pr merge 7 --squash',
]


@pytest.mark.parametrize("command", FOREIGN)
def test_without_rules_a_foreign_target_merges_as_before(
    repo: Path, monkeypatch, command: str
) -> None:
    """No `.weside/risk-paths`, no crew file: the hook classifies nothing, so it refuses no
    merge for want of a checkout (the plugin's users outside weside)."""
    assert refuse(repo, command, FakeGh([run()]), monkeypatch) is None


def test_without_rules_a_non_github_origin_merges_as_before(repo: Path, monkeypatch) -> None:
    _git(repo, "remote", "set-url", "origin", "git@git.example.org:o/r.git")
    reason = refuse(repo, "gh pr merge 7 -R o/r --squash", FakeGh([run()]), monkeypatch)
    assert reason is None


@pytest.mark.parametrize("command", FOREIGN[:4])
def test_risk_paths_alone_keep_a_foreign_target_refused(
    repo: Path, monkeypatch, command: str
) -> None:
    main = _commit(repo, {".weside/risk-paths": "[money]\npath pay.py\n"}, "rules")
    _publish_main(repo, main)
    reason = refuse(repo, command, FakeGh([run()]), monkeypatch)
    assert reason is not None and "no local checkout of other/repo" in reason


def test_a_crew_file_alone_keeps_a_foreign_target_refused(repo: Path, monkeypatch) -> None:
    (repo / ".weside").mkdir()
    (repo / ".weside" / "crew.json").write_text(json.dumps({"version": 2}))
    reason = refuse(repo, "gh pr merge 7 -R other/repo --squash", FakeGh([run()]), monkeypatch)
    assert reason is not None and "no local checkout of other/repo" in reason


def test_the_named_repo_is_its_own_checkout(classed: dict, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_CLASS", "T0")
    fake = FakeGh([run()], head=classed["head"])
    assert refuse(classed["repo"], "gh pr merge 7 -R O/R --squash", fake, monkeypatch) is None


def test_t0_merges_and_arms_as_before(classed: dict, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_CLASS", "T0")
    fake = FakeGh([run()], head=classed["head"], node=NODE)
    for command in FORMS:
        assert refuse(classed["repo"], command, fake, monkeypatch) is None, command
    reason = refuse(classed["repo"], ARM, FakeGh(runs=[], head=classed["head"]), monkeypatch)
    assert reason is not None and "Auto-merge waits for the Codex verdict" in reason


def test_a_graphql_arm_waits_for_codex_too(classed: dict, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_CLASS", "T0")
    fake = FakeGh(runs=[], head=classed["head"], node=NODE)
    reason = refuse(classed["repo"], GRAPHQL_ARM, fake, monkeypatch)
    assert reason is not None and "no `Codex Review` check on head" in reason


@pytest.mark.parametrize(
    ("command", "node", "why"),
    [
        (GRAPHQL_MERGE, None, "PR_kwDOabc did not resolve"),
        ("gh api graphql -f query='mutation { mergePullRequest(input: $i) { x } }'", NODE, "0 "),
    ],
)
def test_an_unresolvable_graphql_merge_refuses(
    repo: Path, monkeypatch, command: str, node: dict | None, why: str
) -> None:
    reason = refuse(repo, command, FakeGh([run()], node=node), monkeypatch)
    assert reason is not None and "class not computed" in reason and why in reason


def test_a_graphql_query_from_a_file_is_read(classed: dict, monkeypatch) -> None:
    (classed["repo"] / "q.graphql").write_text(GRAPHQL_MERGE.split("query=")[1].strip("'"))
    fake = FakeGh([run()], head=classed["head"], node=NODE)
    command = "gh api graphql -F query=@q.graphql"
    reason = refuse(classed["repo"], command, fake, monkeypatch)
    assert reason is not None and "one-way (money)" in reason


@pytest.mark.parametrize(
    "command",
    [
        "gh api repos/o/r/pulls/7/merge",
        "gh api -X GET repos/o/r/pulls/7/merge",
        "gh api repos/o/r/pulls/7",
        "gh api graphql -f query='{ viewer { login } }'",
        "gh pr view 7 --json mergeable",
    ],
)
def test_reads_are_no_merge(classed: dict, monkeypatch, command: str) -> None:
    fake = FakeGh([run()], head=classed["head"])
    assert refuse(classed["repo"], command, fake, monkeypatch) is None
    assert fake.calls == []


def test_risk_paths_classifies_a_repo_without_risk_command(repo: Path, monkeypatch) -> None:
    main = _commit(
        repo,
        {".weside/risk-paths": "[brake-change]\npath gate.py\n", "gate.py": "a\n"},
        "main",
    )
    _publish_main(repo, main)
    head = _commit(repo, {".weside/risk-paths": "", "gate.py": "b\n"}, "empty rules + gate")
    reason = refuse(repo, ARM, FakeGh([run()], head=head), monkeypatch)
    assert reason is not None
    assert "`T2 one-way brake-change`" in reason
    assert "the brake's core, only The owner merges it, by hand" in reason
    assert "merges itself" not in reason


MERGE = "gh pr merge 7 --squash"


def test_a_crew_without_rules_refuses_every_merge(repo: Path, monkeypatch) -> None:
    """A crew on main with neither `risk.command` nor `.weside/risk-paths` cannot
    tell one-way from two-way; it refuses instead of deciding T0 in silence."""
    main = _commit(repo, {".weside/crew.json": json.dumps({"version": 2})}, "crew, no rules")
    _publish_main(repo, main)
    head = _commit(repo, {"pay.py": "x\n"}, "pr")
    for command in (MERGE, ARM):
        reason = refuse(repo, command, FakeGh([run()], head=head), monkeypatch)
        assert reason is not None, command
        assert "class not computed" in reason
        assert "no risk rules" in reason and "`.weside/risk-paths`" in reason
        assert "`risk.command`" in reason


@pytest.mark.parametrize("rules", ["", "# no brake, on purpose\n", "[t2]\npath docs/**\n"])
def test_risk_paths_without_a_one_way_section_merges_and_says_so(
    repo: Path, monkeypatch, capsys, rules: str
) -> None:
    """A rules file without a one-way section brakes nothing on purpose (a crew's
    choice) and the allowed merge carries one line saying so."""
    files = {".weside/crew.json": json.dumps({"version": 2}), ".weside/risk-paths": rules}
    main = _commit(repo, files, "crew, empty brake")
    _publish_main(repo, main)
    head = _commit(repo, {"pay.py": "x\n"}, "pr")
    fake = FakeGh([run()], head=head)
    assert refuse(repo, MERGE, fake, monkeypatch) is None
    assert gate.NOTICES == [
        "risk-paths: no one-way classes configured (`.weside/risk-paths` on origin/main has no "
        "one-way section), so no PR here waits for the owner's merge."
    ]
    payload = {"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": MERGE}}
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(payload)))
    gate.main()
    out = json.loads(capsys.readouterr().out)
    assert out == {"systemMessage": gate.NOTICES[0]}


def test_risk_paths_with_a_one_way_section_say_nothing(repo: Path, monkeypatch) -> None:
    main = _commit(repo, {".weside/risk-paths": "[money]\npath pay.py\n"}, "rules")
    _publish_main(repo, main)
    head = _commit(repo, {"README.md": "y\n"}, "pr")
    assert refuse(repo, MERGE, FakeGh([run()], head=head), monkeypatch) is None
    assert gate.NOTICES == []


def test_deleting_a_one_way_section_stays_a_user_merge(repo: Path, monkeypatch) -> None:
    """owner 06.11.2026: emptying the rules is no way out of a user merge, because main's rules
    classify the PR that empties them."""
    rules = "[brake-change]\npath .weside/risk-paths\n[money]\npath pay.py\n"
    main = _commit(repo, {".weside/risk-paths": rules}, "rules")
    _publish_main(repo, main)
    head = _commit(repo, {".weside/risk-paths": "# no brake\n"}, "drop every section")
    reason = refuse(repo, MERGE, FakeGh([run()], head=head), monkeypatch)
    assert reason is not None and "`T2 one-way brake-change`" in reason


def test_mains_own_risk_paths_blob_is_preferred(repo: Path, monkeypatch) -> None:
    own = "import sys\nprint('T2 one-way terraform-secrets')\nprint('review: high')\n"
    main = _commit(
        repo,
        {".weside/risk-paths": "[t2]\npath x\n", "we/scripts/risk_paths.py": own},
        "main",
    )
    _publish_main(repo, main)
    head = _commit(repo, {"we/scripts/risk_paths.py": "print('T0')\n"}, "lower it")
    reason = refuse(repo, ARM, FakeGh([run()], head=head), monkeypatch)
    assert reason is not None and "one-way (terraform-secrets)" in reason


def test_rules_without_a_fetchable_main_refuse(repo: Path, monkeypatch) -> None:
    (repo / ".weside").mkdir()
    (repo / ".weside" / "risk-paths").write_text("[money]\npath x\n")
    _git(repo, "remote", "set-url", "origin", "https://github.com/o/r-gone.git")
    reason = refuse(repo, "gh pr merge 7 --squash", FakeGh([run()]), monkeypatch)
    assert reason is not None and "`git fetch origin main` failed" in reason


def test_a_worker_is_refused_before_any_class_work(classed: dict, monkeypatch) -> None:
    fake = FakeGh([run()], head=classed["head"])
    reason = refuse(classed["repo"], ARM, fake, monkeypatch, agent_id="a1")
    assert reason is not None and "A worker never merges" in reason
    assert fake.calls == [] and not classed["log"].exists()


# The freeze flag.


def _freeze(state: Path, text: str | None = None) -> None:
    flag = {"since": "2026-11-04T10:00:00Z", "by": "ops", "reason": "incident on main"}
    (state / "freeze.json").write_text(text if text is not None else json.dumps(flag))


@pytest.mark.parametrize("command", FORMS)
def test_freeze_refuses_every_form(
    repo: Path, monkeypatch, _isolated_state: Path, command: str
) -> None:
    _freeze(_isolated_state)
    fake = FakeGh([run()], node=NODE)
    reason = refuse(repo, command, fake, monkeypatch)
    assert reason is not None
    assert "Merges are frozen since 2026-11-04T10:00:00Z by ops: incident on main" in reason


def test_a_torn_freeze_flag_still_freezes(repo: Path, monkeypatch, _isolated_state: Path) -> None:
    _freeze(_isolated_state, "{not json")
    reason = refuse(repo, ARM, FakeGh([run()]), monkeypatch)
    assert reason is not None and "freeze flag is unreadable" in reason


def test_a_disarm_passes_a_freeze(repo: Path, monkeypatch, _isolated_state: Path) -> None:
    _freeze(_isolated_state)
    assert refuse(repo, "gh pr merge 7 --disable-auto", FakeGh([run()]), monkeypatch) is None


def test_the_crews_board_file_names_the_state_dir(
    repo: Path, monkeypatch, tmp_path_factory
) -> None:
    other = tmp_path_factory.mktemp("board")
    _freeze(other)
    (repo / ".weside").mkdir()
    (repo / ".weside" / "crew.json").write_text(
        json.dumps(
            {
                "version": 2,
                "roles": {},
                "members": {},
                "board": {"file": str(other / "board.json")},
            }
        )
    )
    reason = refuse(repo, ARM, FakeGh([run()]), monkeypatch)
    assert reason is not None and "Merges are frozen" in reason


def test_a_relative_crew_board_file_resolves_beside_the_crew_file(
    repo: Path, monkeypatch, tmp_path_factory
) -> None:
    (repo / ".weside" / "state").mkdir(parents=True)
    _freeze(repo / ".weside" / "state")
    (repo / ".weside" / "crew.json").write_text(
        json.dumps(
            {"version": 2, "roles": {}, "members": {}, "board": {"file": "state/board.json"}}
        )
    )
    monkeypatch.chdir(tmp_path_factory.mktemp("elsewhere"))
    reason = refuse(repo, ARM, FakeGh([run()]), monkeypatch)
    assert reason is not None and "Merges are frozen" in reason


# The T2 panel (lens_verdict.py; faked here).

FAKE_LENS = """
from pathlib import Path
CALLS = []
def check(root, vid):
    Path(root, ".lens-called").write_text(vid)
    green = Path(root, ".lens-green").exists()
    return green, ["lens architecture: " + ("green" if green else "missing"),
                   "panel " + vid + ": " + ("green" if green else "red")]
"""


@pytest.fixture()
def lens(monkeypatch, tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("lens") / "lens_verdict.py"
    path.write_text(FAKE_LENS)
    monkeypatch.setattr(gate, "LENS_VERDICT", path)
    return path


@pytest.mark.parametrize("command", [ARM, "gh pr merge 7 --squash", GRAPHQL_MERGE])
def test_t2_without_green_panel_is_refused(
    classed: dict, monkeypatch, lens: Path, command: str
) -> None:
    monkeypatch.setenv("FAKE_CLASS", "T2")
    reason = refuse(
        classed["repo"], command, FakeGh([run()], head=classed["head"], node=NODE), monkeypatch
    )
    assert reason is not None
    assert "PR #7 is T2 and its lens panel is not green: lens architecture: missing" in reason
    assert (classed["repo"] / ".lens-called").read_text() == "t2-pr7"


def test_t2_with_green_panel_passes(classed: dict, monkeypatch, lens: Path) -> None:
    monkeypatch.setenv("FAKE_CLASS", "T2")
    (classed["repo"] / ".lens-green").write_text("")
    assert refuse(classed["repo"], ARM, FakeGh([run()], head=classed["head"]), monkeypatch) is None


# Regression: a core classifier's two-way `[brake-review]` section prints line 1 `T2` with a
# `brake-review:` hit line. Such a PR goes to the panel (and the card, below) and is
# never refused as one-way; it passed before the split and must keep passing.
BRAKE_REVIEW = (
    "T2\nreview: high\n"
    ".github/workflows/main-autofix.yml\tbrake-review: path .github/workflows/main-autofix.yml"
)


def test_a_brake_review_hit_is_two_way(classed: dict, monkeypatch, lens: Path) -> None:
    monkeypatch.setenv("FAKE_CLASS", BRAKE_REVIEW)
    red = refuse(classed["repo"], ARM, FakeGh([run()], head=classed["head"]), monkeypatch)
    assert red is not None and "one-way" not in red
    assert "PR #7 is T2 and its lens panel is not green" in red
    (classed["repo"] / ".lens-green").write_text("")
    red = refuse(classed["repo"], ARM, FakeGh([run()], head=classed["head"]), monkeypatch)
    assert red is not None and "one-way" not in red and "`brake-review` hit" in red
    card = [_card(classed["head"][:10])]
    fake = FakeGh([run()], head=classed["head"], cards=card)
    assert refuse(classed["repo"], ARM, fake, monkeypatch) is None


def test_the_core_never_points_at_the_self_merge_window(
    classed: dict, monkeypatch, lens: Path
) -> None:
    """Red arm of refusal 3's split: the core class with a green panel still refuses, and its text
    names the owner's hand, never the self-merge window."""
    monkeypatch.setenv("FAKE_CLASS", "T2 one-way brake-change")
    (classed["repo"] / ".lens-green").write_text("")
    reason = refuse(classed["repo"], ARM, FakeGh([run()], head=classed["head"]), monkeypatch)
    assert reason is not None and "one-way (brake-change)" in reason
    assert "only Ada merges it, by hand" in reason and "merges itself" not in reason


def test_a_green_panel_never_lifts_one_way(classed: dict, monkeypatch, lens: Path) -> None:
    (classed["repo"] / ".lens-green").write_text("")
    reason = refuse(classed["repo"], ARM, FakeGh([run()], head=classed["head"]), monkeypatch)
    assert reason is not None and "one-way (money)" in reason


def test_a_broken_verdict_reader_counts_red(classed: dict, monkeypatch, lens: Path) -> None:
    monkeypatch.setenv("FAKE_CLASS", "T2")
    lens.write_text("def check(root, vid):\n    raise RuntimeError('torn file')\n")
    reason = refuse(classed["repo"], ARM, FakeGh([run()], head=classed["head"]), monkeypatch)
    assert reason is not None and "the verdict reader failed (RuntimeError: torn file)" in reason


def test_without_lens_verdict_the_panel_check_is_off(classed: dict, monkeypatch, capsys) -> None:
    monkeypatch.setenv("FAKE_CLASS", "T2")
    assert refuse(classed["repo"], ARM, FakeGh([run()], head=classed["head"]), monkeypatch) is None
    assert "T2 panel check off" in capsys.readouterr().err


# Review round: a merge the hook cannot read is refused, not let through.


def test_cd_with_tilde_reaches_the_checkout(classed: dict, monkeypatch, tmp_path_factory) -> None:
    monkeypatch.setenv("HOME", str(classed["repo"].parent))
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    command = f"cd ~/{classed['repo'].name} && gh pr merge 7 --squash"
    fake = FakeGh([run()], head=classed["head"])
    reason = refuse(elsewhere, command, fake, monkeypatch)
    assert reason is not None and "one-way (money)" in reason


def test_a_cd_the_hook_cannot_resolve_refuses(classed: dict, monkeypatch) -> None:
    command = 'cd "$(git rev-parse --show-toplevel)" && gh pr merge 7 --squash'
    reason = refuse(classed["repo"], command, FakeGh([run()]), monkeypatch)
    assert reason is not None
    assert "no local checkout of the repository this command runs in" in reason


def test_an_unparsable_merge_command_refuses(repo: Path, monkeypatch) -> None:
    reason = refuse(repo, "gh pr merge 7 --squash # don't wait", FakeGh([run()]), monkeypatch)
    assert reason is not None and "does not parse as shell words" in reason


def test_an_unparsable_command_without_a_merge_passes(repo: Path, monkeypatch) -> None:
    assert refuse(repo, "echo don't merge yet; gh pr view 7", FakeGh([run()]), monkeypatch) is None


def test_a_graphql_query_from_a_pipe_refuses(repo: Path, monkeypatch) -> None:
    command = "cat q.json | gh api graphql --input -"
    reason = refuse(repo, command, FakeGh([run()], node=NODE), monkeypatch)
    assert reason is not None and "comes from stdin, which the hook cannot read" in reason


def test_a_graphql_heredoc_is_read(classed: dict, monkeypatch) -> None:
    command = (
        "gh api graphql --input - <<'EOF'\n"
        '{"query": "mutation { mergePullRequest(input: {pullRequestId: \\"PR_kwDOabc\\"}) '
        '{ clientMutationId } }"}\nEOF'
    )
    fake = FakeGh([run()], head=classed["head"], node=NODE)
    reason = refuse(classed["repo"], command, fake, monkeypatch)
    assert reason is not None and "one-way (money)" in reason


def test_a_graphql_file_is_read_after_the_commands_cd(classed: dict, monkeypatch) -> None:
    sub = classed["repo"] / "sub"
    sub.mkdir()
    (sub / "q.graphql").write_text(GRAPHQL_MERGE.split("query=")[1].strip("'"))
    fake = FakeGh([run()], head=classed["head"], node=NODE)
    reason = refuse(
        classed["repo"], "cd sub && gh api graphql -F query=@q.graphql", fake, monkeypatch
    )
    assert reason is not None and "one-way (money)" in reason


def test_the_rules_are_fetched_before_classifying(classed: dict, monkeypatch) -> None:
    repo = classed["repo"]
    _git(repo, "update-ref", "refs/remotes/origin/main", f"{classed['main']}~0")
    stale = _commit(repo, {"other.txt": "x\n"}, "unrelated")
    _git(repo, "update-ref", "refs/remotes/origin/main", stale)  # local ref ahead of origin
    fake = FakeGh([run()], head=classed["head"])
    reason = refuse(repo, ARM, fake, monkeypatch)
    assert reason is not None and "one-way (money)" in reason
    assert _git(repo, "rev-parse", "refs/remotes/origin/main") == classed["main"]


def test_a_failed_rules_fetch_refuses(classed: dict, monkeypatch) -> None:
    _git(classed["repo"], "remote", "set-url", "origin", "https://github.com/o/r-gone.git")
    _git(
        classed["repo"],
        "config",
        "url.file:///nonexistent.insteadOf",
        "https://github.com/o/r-gone.git",
    )
    reason = refuse(classed["repo"], ARM, FakeGh([run()], head=classed["head"]), monkeypatch)
    assert reason is not None and "`git fetch origin main` failed" in reason


def _crew_board(repo: Path, board_file: Path) -> None:
    (repo / ".weside").mkdir(exist_ok=True)
    (repo / ".weside" / "crew.json").write_text(
        json.dumps({"version": 2, "roles": {}, "members": {}, "board": {"file": str(board_file)}})
    )


def test_the_default_freeze_does_not_reach_a_crew_with_its_own_board(
    repo: Path, monkeypatch, _isolated_state: Path, tmp_path_factory
) -> None:
    """A crew with its own `board.file` is a separate team; a freeze on the default
    board, `*` included, does not stop it. Its own board's freeze does."""
    flag = {
        "since": "s",
        "by": "ops",
        "reason": "incident on main",
        "repos": ["*"],
        "scoped": True,
    }
    _freeze(_isolated_state, json.dumps(flag))
    other = tmp_path_factory.mktemp("board")
    _crew_board(repo, other / "board.json")
    (repo / ".weside" / "risk-paths").write_text("[t2]\npath docs/**\n")
    main = _commit(repo, {}, "crew + rules")
    _publish_main(repo, main)
    head = _commit(repo, {"README.md": "y\n"}, "pr")
    assert refuse(repo, MERGE, FakeGh([run()], head=head), monkeypatch) is None
    _freeze(other, json.dumps(flag))
    reason = refuse(repo, MERGE, FakeGh([run()], head=head), monkeypatch)
    assert reason is not None and "Merges are frozen" in reason


@pytest.mark.parametrize(
    ("repos", "frozen"),
    [
        (["o/r"], True),
        (["O/R"], True),
        (["acme/core"], False),
        (["*"], True),
        ([], True),
        (None, True),
    ],
)
def test_a_freeze_counts_only_for_the_repos_it_names(
    repo: Path, monkeypatch, _isolated_state: Path, repos, frozen: bool
) -> None:
    """`repos` scopes the flag; `*`, an empty or missing list fail closed."""
    flag = {"since": "s", "by": "ops", "reason": "incident on main", "scoped": True}
    if repos is not None:
        flag["repos"] = repos
    _freeze(_isolated_state, json.dumps(flag))
    reason = refuse(repo, MERGE, FakeGh([run()]), monkeypatch)
    assert (reason is not None and "Merges are frozen" in reason) is frozen, reason


def test_a_flag_from_an_older_writer_freezes_every_repo(
    repo: Path, monkeypatch, _isolated_state: Path
) -> None:
    """Before per-repo scope, `repos` was only the disarm list: such a flag still stops all."""
    flag = {"since": "s", "by": "ops", "reason": "incident", "repos": ["other/repo"]}
    _freeze(_isolated_state, json.dumps(flag))
    reason = refuse(repo, MERGE, FakeGh([run()]), monkeypatch)
    assert reason is not None and "Merges are frozen" in reason


def test_a_freeze_on_another_repo_still_refuses_a_target_it_names(
    repo: Path, monkeypatch, _isolated_state: Path
) -> None:
    flag = {
        "since": "s",
        "by": "ops",
        "reason": "core incident",
        "repos": ["other/repo"],
        "scoped": True,
    }
    _freeze(_isolated_state, json.dumps(flag))
    reason = refuse(repo, "gh pr merge 7 -R other/repo --squash", FakeGh([run()]), monkeypatch)
    assert reason is not None and "Merges are frozen" in reason


@pytest.mark.parametrize(
    "selector",
    ["-R github.com/o/r", "-R https://github.com/o/r.git", "https://github.com/o/r/pull/7"],
)
def test_a_host_or_url_form_target_still_meets_its_freeze(
    repo: Path, monkeypatch, _isolated_state: Path, selector: str
) -> None:
    flag = {"since": "s", "by": "ops", "reason": "incident", "repos": ["o/r"], "scoped": True}
    _freeze(_isolated_state, json.dumps(flag))
    sel = f"7 {selector}" if selector.startswith("-R") else selector
    command = f"gh pr merge {sel} --squash"
    reason = refuse(repo, command, FakeGh([run()]), monkeypatch)
    assert reason is not None and "Merges are frozen" in reason


@pytest.mark.parametrize("how", ["env", "command", "set-default", "upstream"])
def test_a_merge_gh_may_route_elsewhere_meets_every_freeze(
    repo: Path, monkeypatch, _isolated_state: Path, how: str
) -> None:
    """Without `-R`, `gh` may target `GH_REPO` or a `gh repo set-default` remote, not origin."""
    flag = {
        "since": "s",
        "by": "ops",
        "reason": "incident",
        "repos": ["other/repo"],
        "scoped": True,
    }
    _freeze(_isolated_state, json.dumps(flag))
    command = MERGE
    if how == "env":
        monkeypatch.setenv("GH_REPO", "other/repo")
    elif how == "command":
        command = f"GH_REPO=other/repo {MERGE}"
    elif how == "set-default":
        _git(repo, "config", "remote.origin.gh-resolved", "base")
    else:
        _git(repo, "remote", "add", "upstream", "https://github.com/other/repo.git")
    if how != "env":
        monkeypatch.delenv("GH_REPO", raising=False)
    reason = refuse(repo, command, FakeGh([run()]), monkeypatch)
    assert reason is not None and "Merges are frozen" in reason


def test_a_broken_crew_without_rules_refuses_too(repo: Path, monkeypatch) -> None:
    main = _commit(repo, {".weside/crew.json": "{not json"}, "crew, no rules")
    _publish_main(repo, main)
    head = _commit(repo, {"pay.py": "x\n"}, "pr")
    reason = refuse(repo, MERGE, FakeGh([run()], head=head), monkeypatch)
    assert reason is not None and "no risk rules" in reason
    assert "the owner merges that one by hand" in reason


def test_a_repo_that_only_points_at_another_crew_merges_as_before(repo: Path, monkeypatch) -> None:
    """A workspace repo whose `.weside/config.json` points at a crew elsewhere has no rules of
    its own to read; it keeps T0 as before (whether it should get rules is its owner's call)."""
    config = {".weside/config.json": json.dumps({"crew": "../shared/crew.json"})}
    main = _commit(repo, config, "pointer, no rules")
    _publish_main(repo, main)
    head = _commit(repo, {"pay.py": "x\n"}, "pr")
    assert refuse(repo, MERGE, FakeGh([run()], head=head), monkeypatch) is None


def test_a_crew_without_its_own_board_reads_the_default_board(
    repo: Path, monkeypatch, _isolated_state: Path
) -> None:
    (repo / ".weside").mkdir()
    (repo / ".weside" / "crew.json").write_text(json.dumps({"version": 2}))
    _freeze(_isolated_state)
    reason = refuse(repo, ARM, FakeGh([run()]), monkeypatch)
    assert reason is not None and "Merges are frozen" in reason


# Lars's review: an error never lets a merge through; the rules branch is always fetched.


def test_an_exception_in_the_gate_denies_a_merge(monkeypatch, capsys) -> None:
    def boom(_payload):
        raise RuntimeError("torn state")

    monkeypatch.setattr(gate, "_refusal", boom)
    payload = {"tool_name": "Bash", "cwd": "/", "tool_input": {"command": ARM}}
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(payload)))
    gate.main()
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert "the merge gate failed (RuntimeError: torn state)" in out["permissionDecisionReason"]


def test_an_exception_on_a_non_merge_command_stays_silent(monkeypatch, capsys) -> None:
    monkeypatch.setattr(gate, "_refusal", lambda _p: 1 / 0)
    payload = {"tool_name": "Bash", "cwd": "/", "tool_input": {"command": "ls"}}
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(payload)))
    gate.main()
    assert capsys.readouterr().out == ""


def test_an_unfetchable_rules_branch_denies_even_without_rules(repo: Path, monkeypatch) -> None:
    _git(
        repo,
        "config",
        "--unset-all",
        f"url.{(repo.parent / f'{repo.name}-origin.git').as_uri()}.insteadOf",
    )
    _git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    reason = refuse(repo, "gh pr merge 7 --squash", FakeGh([run()]), monkeypatch)
    assert reason is not None and "`git fetch origin main` failed" in reason


def test_a_fetched_main_without_rules_is_t0(repo: Path, monkeypatch) -> None:
    _git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    assert refuse(repo, "gh pr merge 7 --squash", FakeGh([run()]), monkeypatch) is None
    assert _git(repo, "rev-parse", "--verify", "-q", "refs/remotes/origin/main")


def test_every_call_takes_its_timeout_from_one_budget(monkeypatch) -> None:
    assert gate.BUDGET_SECONDS < 600  # hooks.json's timeout for this hook
    hooks = json.loads((HOOK.parent / "hooks.json").read_text())
    entries = [h for e in hooks["hooks"]["PreToolUse"] for h in e["hooks"]]
    (entry,) = [h for h in entries if "automerge_gate.py" in h["command"]]
    assert entry["timeout"] == 600
    monkeypatch.setattr(gate, "_DEADLINE", [gate.time.monotonic() + 5])
    assert gate._left(20) <= 5
    monkeypatch.setattr(gate, "_DEADLINE", [gate.time.monotonic() - 1])
    assert gate._left(20) == 0.1


# The security card verdict (brake stage 2): a T2 hit in `trust-loosening`, `money-path` or
# `brake-review` waits for the green panel AND a card PASS on the current head. Red arms ran
# against the 8.4.0 hook (git show origin/main), which reads line 1 only and let all three
# cases through on the panel.


def _hit(section: str) -> str:
    return f"T2\nreview: high\napps/x.py\t{section}: path apps/x.py (rules: origin/main abc)"


def _card(sha: str, overall: str = "PASS", number: int = 7) -> str:
    return (
        "<!-- security-card-review -->\n"
        f"## Security card review — #{number} @ `{sha}`\n\n"
        f"**Card:** `roles/security.md` · **Overall: {overall}**\n"
    )


@pytest.fixture()
def green(classed: dict, lens: Path) -> dict:
    (classed["repo"] / ".lens-green").write_text("")
    return classed


@pytest.mark.parametrize("section", ["trust-loosening", "money-path", "brake-review"])
def test_a_card_hit_without_card_verdict_is_refused(green: dict, monkeypatch, section) -> None:
    monkeypatch.setenv("FAKE_CLASS", _hit(section))
    for command in (ARM, "gh pr merge 7 --squash"):
        red = refuse(green["repo"], command, FakeGh([run()], head=green["head"]), monkeypatch)
        assert red is not None, command
        assert f"PR #7 is T2 with a `{section}` hit" in red
        assert "no card verdict is on the PR" in red
        assert "we-worker <KEY>-card --bg \"/<security holder's skill> security card" in red
        assert "<!-- security-card-review -->" in red


def test_a_card_pass_on_an_older_head_is_refused(green: dict, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_CLASS", _hit("trust-loosening"))
    old = green["main"][:10]
    fake = FakeGh([run()], head=green["head"], cards=[_card(old)])
    red = refuse(green["repo"], ARM, fake, monkeypatch)
    assert red is not None and f"the last card verdict is on the older head {old}" in red


def test_a_card_pass_on_the_head_lets_it_merge(green: dict, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_CLASS", _hit("trust-loosening"))
    comments = [_card(green["main"][:10]), _card(green["head"][:10])]
    fake = FakeGh([run()], head=green["head"], cards=comments)
    assert refuse(green["repo"], ARM, fake, monkeypatch) is None
    assert refuse(green["repo"], "gh pr merge 7 --squash", fake, monkeypatch) is None


def test_a_later_blocking_on_the_head_beats_a_pass(green: dict, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_CLASS", _hit("money-path"))
    head = green["head"][:10]
    fake = FakeGh([run()], head=green["head"], cards=[_card(head), _card(head, "BLOCKING")])
    red = refuse(green["repo"], ARM, fake, monkeypatch)
    assert red is not None and "the card verdict on this head is BLOCKING" in red


def test_a_comment_without_the_marker_is_no_card_verdict(green: dict, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_CLASS", _hit("brake-review"))
    forged = _card(green["head"][:10]).replace("<!-- security-card-review -->\n", "")
    fake = FakeGh([run()], head=green["head"], cards=[forged])
    assert "no card verdict is on the PR" in refuse(green["repo"], ARM, fake, monkeypatch)


def test_an_unreadable_comment_list_refuses(green: dict, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_CLASS", _hit("trust-loosening"))

    class NoComments(FakeGh):
        def __call__(self, args, cwd):
            return (
                None
                if args[1:2] == ["repos/o/r/issues/7/comments"]
                else super().__call__(args, cwd)
            )

    red = refuse(green["repo"], ARM, NoComments([run()], head=green["head"]), monkeypatch)
    assert red is not None and "the PR comments could not be read" in red


def test_the_crews_security_holder_names_the_skill(
    repo: Path, monkeypatch, lens, tmp_path_factory
):
    crew = {**CREW, "members": {"lars": {"name": "Lars"}}, "roles": {"security": "lars"}}
    main = _commit(
        repo,
        {".weside/crew.json": json.dumps(crew), "bin/classify.sh": FAKE_CLASSIFIER},
        "main",
    )
    _publish_main(repo, main)
    head = _commit(repo, {"README.md": "y\n"}, "pr")
    monkeypatch.setenv("FAKE_LOG", str(tmp_path_factory.mktemp("log") / "c.log"))
    monkeypatch.setenv("FAKE_CLASS", _hit("trust-loosening"))
    (repo / ".lens-green").write_text("")
    red = refuse(repo, ARM, FakeGh([run()], head=head), monkeypatch)
    assert red is not None and '--bg "/weside-lars security card review of PR #7' in red


def test_t2_without_a_card_hit_merges_on_the_panel_alone(green: dict, monkeypatch) -> None:
    for out in ("T2", "T2\nreview: high\napps/x.py\tt2: path apps/x.py"):
        monkeypatch.setenv("FAKE_CLASS", out)
        fake = FakeGh([run()], head=green["head"])
        assert refuse(green["repo"], ARM, fake, monkeypatch) is None
        assert not any("repos/o/r/issues/7/comments" in c for c in fake.calls), fake.calls


def test_the_panel_refuses_before_the_card(classed: dict, monkeypatch, lens: Path) -> None:
    monkeypatch.setenv("FAKE_CLASS", _hit("trust-loosening"))
    red = refuse(classed["repo"], ARM, FakeGh([run()], head=classed["head"]), monkeypatch)
    assert red is not None and "lens panel is not green" in red


@pytest.mark.parametrize(
    ("assoc", "kind", "counts"),
    [
        ("NONE", "User", False),
        ("CONTRIBUTOR", "User", False),
        ("FIRST_TIMER", "User", False),
        ("NONE", "Bot", True),
        ("COLLABORATOR", "User", True),
        ("OWNER", "User", True),
    ],
)
def test_only_the_crew_or_an_installed_app_signs(green: dict, monkeypatch, assoc, kind, counts):
    """An outside account's PASS on the head never lifts the brake (Claude Review on #181)."""
    monkeypatch.setenv("FAKE_CLASS", _hit("trust-loosening"))
    card = (_card(green["head"][:10]), assoc, kind)
    red = refuse(
        green["repo"], ARM, FakeGh([run()], head=green["head"], cards=[card]), monkeypatch
    )
    assert (red is None) is counts, red
