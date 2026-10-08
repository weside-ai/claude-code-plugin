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
MERGE = "merge: UNKNOWN/UNKNOWN"
RUN_URL = "https://github.com/o/r/actions/runs/{}/job/{}"

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


def _queue(tmp_path, name, answers):
    q = tmp_path / name
    q.mkdir()
    for i, a in enumerate(answers):
        (q / f"{i}.json").write_text(a if a == "FAIL" else json.dumps(a))
    # Each queue replays its answers in order, then repeats the last one.
    return (
        f'n=$(cat "{q}/count" 2>/dev/null || echo 0); echo $((n+1)) > "{q}/count"; '
        f'f="{q}/$n.json"; [ -f "$f" ] || f="{q}/{len(answers) - 1}.json"'
    )


def run(tmp_path, answers, *args, runs=([],), timeout_s="900", max_errors="10", quiet="0"):
    """`answers` replays `gh pr view`, `runs` replays `gh run list --commit <sha>`."""
    gh = tmp_path / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1 $2" = "run list" ]; then '
        + _queue(tmp_path, "runs", list(runs))
        + "; else "
        + _queue(tmp_path, "views", answers)
        + "; fi\n"
        '[ "$(cat "$f")" = FAIL ] && { echo "GraphQL: Could not resolve to a PullRequest" >&2; exit 1; }\n'
        # gh's --jq is jq; the stub delegates to the jq binary.
        'while [ $# -gt 0 ]; do [ "$1" = --jq ] && q=$2; shift; done; jq -r "$q" "$f"\n'
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "WATCH_INTERVAL": "0",
        "WATCH_QUIET": quiet,
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
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])


def test_a_failure_is_emitted_once_and_named_in_the_final_line(tmp_path):
    code, out = run(tmp_path, [_pending(REAL), _pending(REAL), REAL])
    assert code == 1
    assert out == [
        "fail: Claude Review",
        "fail: Claude Review (Analyze)",
        f"final {SHA}: red · failed: Claude Review (Analyze), Claude Review · " + MERGE,
    ]


def test_real_rollup_reports_both_red_review_checks(tmp_path):
    code, out = run(tmp_path, [REAL])
    assert code == 1
    assert out == [
        "fail: Claude Review (Analyze)",
        "fail: Claude Review",
        f"final {SHA}: red · failed: Claude Review (Analyze), Claude Review · " + MERGE,
    ]


def test_fail_fast_exits_on_the_first_failure_while_others_pend(tmp_path):
    d = _pending(REAL)
    d["statusCheckRollup"][1].update(status="QUEUED", conclusion="")
    code, out = run(tmp_path, [d], "--fail-fast")
    assert (code, out) == (
        1,
        ["fail: Claude Review", f"final {SHA}: red · failed: Claude Review · " + MERGE],
    )


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
    assert (code, out) == (
        1,
        ["fail: ci/legacy", f"final {SHA}: red · failed: ci/legacy · " + MERGE],
    )


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
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])


def _skipped_only():
    """What a head shows seconds after a push: two skipped checks, the real ones not yet registered."""
    d = copy.deepcopy(REAL)
    d["statusCheckRollup"] = copy.deepcopy(REAL["statusCheckRollup"][:2])
    for c in d["statusCheckRollup"]:
        c.update(status="COMPLETED", conclusion="SKIPPED")
    return d


def test_early_skipped_checks_are_not_green_while_more_register(tmp_path):
    later = _green()
    later["statusCheckRollup"][-1].update(status="IN_PROGRESS", conclusion="")
    code, out = run(tmp_path, [_skipped_only(), _skipped_only(), later, _green()])
    # Checked first: the old watcher said green on the second read, with two skipped checks.
    assert int((tmp_path / "views" / "count").read_text()) >= 4, out
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])


def test_green_needs_the_quiet_period_without_change(tmp_path):
    code, out = run(
        tmp_path, [_skipped_only(), _skipped_only(), _pending(_green()), _green()], quiet="1"
    )
    # A second of 0-interval reads: far more than the four scripted answers.
    assert int((tmp_path / "views" / "count").read_text()) > 4, out
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])


def test_a_queued_run_without_check_runs_is_pending(tmp_path):
    queued = [{"databaseId": 7, "attempt": 1, "status": "queued"}]
    done = [{"databaseId": 7, "attempt": 1, "status": "completed"}]
    later = _green()
    later["statusCheckRollup"][0].update(name="Backend Tests", conclusion="FAILURE")
    code, out = run(
        tmp_path, [_skipped_only(), _skipped_only(), later], runs=[queued, queued, done]
    )
    assert code == 1
    assert out == ["fail: Backend Tests", f"final {SHA}: red · failed: Backend Tests · {MERGE}"]


def test_a_rerun_not_yet_started_hides_its_old_failure(tmp_path):
    failed = _green()
    failed["statusCheckRollup"][0].update(conclusion="FAILURE", detailsUrl=RUN_URL.format(9, 1))
    rerun = copy.deepcopy(failed)  # the rollup still shows attempt 1's failure
    passed = _green()
    passed["statusCheckRollup"][0]["detailsUrl"] = RUN_URL.format(9, 2)
    queued = [{"databaseId": 9, "attempt": 2, "status": "queued"}]
    in_progress = [{"databaseId": 9, "attempt": 2, "status": "in_progress"}]
    done = [{"databaseId": 9, "attempt": 2, "status": "completed"}]
    code, out = run(
        tmp_path,
        [rerun, rerun, rerun, passed],
        "--fail-fast",
        runs=[queued, in_progress, done],
    )
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])


@pytest.mark.parametrize(
    "mss, mergeable, note",
    [
        ("CLEAN", "MERGEABLE", "merge: CLEAN/MERGEABLE"),
        ("BLOCKED", "MERGEABLE", "merge: BLOCKED/MERGEABLE"),
        ("DIRTY", "CONFLICTING", "merge: DIRTY/CONFLICTING — conflicts with the base: merge it"),
        (
            "UNKNOWN",
            "CONFLICTING",
            "merge: UNKNOWN/CONFLICTING — conflicts with the base: merge it",
        ),
    ],
)
def test_final_line_names_the_merge_state(tmp_path, mss, mergeable, note):
    d = {**_green(), "mergeStateStatus": mss, "mergeable": mergeable}
    code, out = run(tmp_path, [d])
    assert (code, out) == (0, [f"final {SHA}: green · {note}"])


def test_a_run_waiting_for_approval_does_not_hold_the_watcher(tmp_path):
    waiting = [{"databaseId": 8, "attempt": 1, "status": "waiting"}]
    code, out = run(tmp_path, [_green(), _green(), _green()], runs=[waiting, waiting, waiting])
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])
