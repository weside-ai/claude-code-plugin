"""The PR rule of the command centre against `arm_pr.sh`'s own `READ`, `JQ` and `verdict()`.

`flow_report.py` holds a copy of the rule (no merge decision reads the command centre); these tests
run the shell's text, cut from `arm_pr.sh` at test time, against the copy, so a change to either
side without the other turns red.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import flow_report as fr  # noqa: E402

ARM = (HERE.parent / "arm_pr.sh").read_text(encoding="utf-8")


def _quoted(var: str) -> str:
    found = re.search(rf"^{var}='(.*?)'$", ARM, re.MULTILINE | re.DOTALL)
    assert found, f"{var} not found in arm_pr.sh"
    return found.group(1)


def _function(name: str) -> str:
    found = re.search(rf"^{name}\(\) {{.*?^}}$", ARM, re.MULTILINE | re.DOTALL)
    assert found, f"{name}() not found in arm_pr.sh"
    return found.group(0)


def run_ctx(name, status="COMPLETED", conclusion="SUCCESS", required=False, **times):
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "isRequired": required,
        "startedAt": times.get("started"),
        "completedAt": times.get("completed"),
        "checkSuite": {"createdAt": times.get("created", "2026-04-01T09:00:00Z")},
    }


def status_ctx(name, state, required=False):
    return {
        "__typename": "StatusContext",
        "context": name,
        "state": state,
        "isRequired": required,
        "createdAt": "2026-04-01T09:00:00Z",
    }


def pr_node(contexts, head="a" * 40, last=None, **extra):
    return {
        "id": "PR_1",
        "number": 7,
        "state": "OPEN",
        "isDraft": False,
        "headRefOid": head,
        "baseRefName": "main",
        "mergeStateStatus": "BLOCKED",
        "reviewDecision": None,
        "labels": {"nodes": [{"name": "risk"}, {"name": "x"}]},
        "autoMergeRequest": None,
        "commits": {
            "nodes": [
                {
                    "commit": {
                        "oid": last or head,
                        "statusCheckRollup": {"contexts": {"nodes": contexts}},
                    }
                }
            ]
        },
        **extra,
    }


# Every class of JQ: status SUCCESS/PENDING/EXPECTED/ERROR, check run running, green, neutral,
# skipped, red, cancelled; required only for the PR; plus the drop of a lagging last commit.
CONTEXTS = [
    status_ctx("ci/status-ok", "SUCCESS"),
    status_ctx("ci/status-pending", "PENDING", required=True),
    status_ctx("ci/status-expected", "EXPECTED"),
    status_ctx("ci/status-error", "ERROR"),
    run_ctx("running", status="IN_PROGRESS", conclusion=None, started="2026-04-01T09:01:00Z"),
    run_ctx("queued", status="QUEUED", conclusion=None),
    run_ctx("green"),
    run_ctx("neutral", conclusion="NEUTRAL"),
    run_ctx("skipped", conclusion="SKIPPED"),
    run_ctx("red", conclusion="FAILURE"),
    run_ctx("cancelled", conclusion="CANCELLED"),
    run_ctx("pr-only", required=True),
    # a completed run whose check run still says IN_PROGRESS: the set conclusion is the verdict
    run_ctx("stale-status-green", status="IN_PROGRESS", conclusion="SUCCESS"),
    run_ctx("stale-status-red", status="IN_PROGRESS", conclusion="FAILURE"),
]


def jq_lines(node: dict) -> list:
    doc = {"data": {"repository": {"pullRequest": node}}}
    out = subprocess.run(
        ["jq", "-r", _quoted("JQ")],
        input=json.dumps(doc),
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.splitlines()


needs_jq = pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")


@needs_jq
def test_parity_with_arm_pr_jq():
    node = pr_node(CONTEXTS)
    head, *checks = jq_lines(node)
    assert head.split("\t") == [
        "PR_1",
        "OPEN",
        "false",
        "a" * 40,
        "main",
        "BLOCKED",
        "NONE",
        "risk,x",
    ]
    mine = [
        "\t".join([c["v"], str(c["required"]).lower(), c["name"]]) for c in fr.head_contexts(node)
    ]
    assert checks == mine
    assert {c["name"]: c["v"] for c in fr.head_contexts(node)}["stale-status-green"] == "pass"
    # a last commit that is not the head lists no check, on both sides
    lagging = pr_node(CONTEXTS, last="b" * 40)
    assert jq_lines(lagging)[1:] == [] and fr.head_contexts(lagging) == []


def test_parity_with_arm_pr_read():
    """Every field `READ` asks for is asked by `PR_STATE_FIELDS` too (the copy reads no less)."""
    words = set(re.findall(r"[A-Za-z_]+", _quoted("READ")))
    words -= {"query", "repository", "owner", "name", "pullRequest", "number", "String", "Int"}
    words -= {"on", "CheckRun", "StatusContext", "first", "last", "pullRequestNumber"}
    mine = set(re.findall(r"[A-Za-z_]+", fr.PR_STATE_FIELDS))
    assert words - mine == set()


def bash_verdict(required: list, checks: list) -> str:
    script = _function("verdict") + '\nREQUIRED=$(cat "$1"); CHECKS=$(cat "$2"); verdict\n'
    with tempfile.TemporaryDirectory() as d:
        req, chk = Path(d) / "req", Path(d) / "chk"
        req.write_text("\n".join(required))
        chk.write_text(
            "\n".join("\t".join([c["v"], str(c["required"]).lower(), c["name"]]) for c in checks)
        )
        out = subprocess.run(
            ["bash", "-c", script, "verdict", str(req), str(chk)],
            capture_output=True,
            text=True,
            check=True,
        )
    return out.stdout.strip()


def py_verdict(required: list, checks: list) -> str:
    v, fails = fr.pr_verdict(checks, required)
    return f"fail:{', '.join(fails)}" if v == "fail" else v


def c(name, v, required=False):
    return {"name": name, "v": v, "required": required}


# One case per rule of verdict(): absent is not green, a required fail, a required pending, a
# check required only for the PR, a red check that is not required, no required check at all
# (every check must pass), no check at all, and a name listed twice (any fail wins).
VERDICT_CASES = [
    (["test"], []),
    (["test"], [c("lint", "pass")]),
    (["test"], [c("test", "pass")]),
    (["test"], [c("test", "fail")]),
    (["test"], [c("test", "pending")]),
    (["test"], [c("test", "pass"), c("review", "fail", True)]),
    (["test"], [c("test", "pass"), c("review", "pending", True)]),
    (["test"], [c("test", "pass"), c("lint", "fail")]),
    ([], [c("lint", "pass"), c("x", "pass")]),
    ([], [c("lint", "pass"), c("x", "fail")]),
    ([], [c("lint", "pending")]),
    (["test"], [c("test", "pass"), c("test", "fail")]),
    (["test", "lint"], [c("test", "fail"), c("lint", "fail")]),
]


@pytest.mark.parametrize(("required", "checks"), VERDICT_CASES)
def test_parity_with_arm_pr_verdict(required, checks):
    assert py_verdict(required, checks) == bash_verdict(required, checks)


def test_pending_required_counts_absent_and_pr_required():
    checks = [c("test", "pass"), c("review", "pending", True)]
    assert fr.pending_required(checks, ["test", "lint"]) == ["lint", "review"]


def test_open_pr_states_asks_one_aliased_query():
    seen = []

    def run(body):
        seen.append(body)
        return {"data": {"repository": {"pr7": pr_node([]), "pr9": None}}}

    got = fr.open_pr_states(run, "acme/app", [7, 9])
    assert list(got) == [7] and len(seen) == 1
    assert "isRequired(pullRequestNumber: 7)" in seen[0]["query"]
    assert "isRequired(pullRequestNumber: 9)" in seen[0]["query"]
    assert fr.open_pr_state(run, "acme/app", 7)["number"] == 7
