"""watch-pr-checks.sh against a stub `gh` that replays one rollup per call.

The fixture is a real `gh pr view --json headRefOid,statusCheckRollup` answer (PR #57, 2026-10-04).
"""

import copy
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent
SCRIPT = HERE / "watch-pr-checks.sh"
REAL = json.loads((HERE / "fixtures" / "pr-checks-rollup.json").read_text())
SHA = REAL["headRefOid"]

pytestmark = pytest.mark.skipif(not shutil.which("jq"), reason="the stub gh delegates --jq to jq")


def _green():
    d = copy.deepcopy(REAL)
    for c in d["statusCheckRollup"]:
        c["conclusion"] = "SUCCESS"
    return d


def _pending(d):
    d = copy.deepcopy(d)
    d["statusCheckRollup"][0].update(status="IN_PROGRESS", conclusion="")
    return d


def run(tmp_path, answers, *args, timeout_s="900", max_errors="10"):
    replay = tmp_path / "answers"
    replay.mkdir()
    for i, a in enumerate(answers):
        (replay / f"{i}.json").write_text(a if a == "FAIL" else json.dumps(a))
    gh = tmp_path / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        f'n=$(cat "{tmp_path}/count" 2>/dev/null || echo 0); echo $((n+1)) > "{tmp_path}/count"\n'
        f'f="{replay}/$n.json"; [ -f "$f" ] || f="{replay}/{len(answers) - 1}.json"\n'
        '[ "$(cat "$f")" = FAIL ] && { echo "GraphQL: Could not resolve to a PullRequest" >&2; exit 1; }\n'
        # gh's --jq is jq; the stub delegates to the jq binary.
        'while [ $# -gt 0 ]; do [ "$1" = --jq ] && q=$2; shift; done; jq -r "$q" "$f"\n'
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "WATCH_INTERVAL": "0",
        "WATCH_REGISTER_TIMEOUT": timeout_s,
        "WATCH_MAX_ERRORS": max_errors,
    }
    res = subprocess.run(
        ["bash", str(SCRIPT), "57", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )
    return res.returncode, res.stdout.splitlines()


def test_empty_then_pending_then_green_says_only_green(tmp_path):
    empty = {"headRefOid": SHA, "statusCheckRollup": []}
    code, out = run(tmp_path, [empty, empty, _pending(_green()), _green()])
    assert (code, out) == (0, [f"final {SHA}: green"])


def test_a_failure_is_emitted_once_and_named_in_the_final_line(tmp_path):
    code, out = run(tmp_path, [_pending(REAL), _pending(REAL), REAL])
    assert code == 1
    assert out == [
        "fail: Claude Review",
        "fail: Claude Review (Analyze)",
        f"final {SHA}: red · failed: Claude Review (Analyze), Claude Review",
    ]


def test_real_rollup_reports_both_red_review_checks(tmp_path):
    code, out = run(tmp_path, [REAL])
    assert code == 1
    assert out == [
        "fail: Claude Review (Analyze)",
        "fail: Claude Review",
        f"final {SHA}: red · failed: Claude Review (Analyze), Claude Review",
    ]


def test_fail_fast_exits_on_the_first_failure_while_others_pend(tmp_path):
    d = _pending(REAL)
    d["statusCheckRollup"][1].update(status="QUEUED", conclusion="")
    code, out = run(tmp_path, [d], "--fail-fast")
    assert (code, out) == (1, ["fail: Claude Review", f"final {SHA}: red · failed: Claude Review"])


def test_a_new_head_is_never_reported_green(tmp_path):
    moved = {**_green(), "headRefOid": "b" * 40}
    code, out = run(tmp_path, [_pending(_green()), moved])
    assert (code, out) == (3, [f"head moved {SHA} -> {'b' * 40}"])


def test_status_context_items_count(tmp_path):
    d = _green()
    d["statusCheckRollup"].append(
        {"__typename": "StatusContext", "context": "ci/legacy", "state": "PENDING"}
    )
    done = copy.deepcopy(d)
    done["statusCheckRollup"][-1]["state"] = "ERROR"
    code, out = run(tmp_path, [d, done])
    assert (code, out) == (1, ["fail: ci/legacy", f"final {SHA}: red · failed: ci/legacy"])


def test_no_checks_ever_registered_times_out(tmp_path):
    empty = {"headRefOid": SHA, "statusCheckRollup": []}
    code, out = run(tmp_path, [empty], timeout_s="0")
    assert (code, out) == (4, [f"no checks on {SHA} after 0s"])


def test_gh_failing_every_time_ends_with_its_error(tmp_path):
    code, out = run(tmp_path, ["FAIL"], max_errors="3")
    assert (code, out) == (
        2,
        ["gh failed 3 times in a row: GraphQL: Could not resolve to a PullRequest"],
    )


def test_a_transient_gh_error_is_retried(tmp_path):
    code, out = run(tmp_path, ["FAIL", _green(), "FAIL", _green()], max_errors="2")
    assert (code, out) == (0, [f"final {SHA}: green"])
