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


def run(
    tmp_path,
    answers,
    *args,
    runs=([],),
    comments=({"comments": []},),
    timeout_s="900",
    max_errors="10",
    quiet="0",
    env_extra=None,
    cwd=None,
):
    """`answers` replays `gh pr view`, `runs` `gh run list --commit <sha>`, `comments` the
    `gh pr view --json comments` read. Every call's argv and cwd land in `calls.log`."""
    gh = tmp_path / "gh"
    log = tmp_path / "calls.log"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        f'a="$*"; echo "$(pwd) | ${{a%%--json*}}" >> "{log}"\n'
        'if [ "$1 $2" = "repo view" ]; then [ -n "$GH_REPO_VIEW_FAIL" ] && exit 1; echo o/r; exit 0; fi\n'
        'if [ "$1 $2" = "pr merge" ]; then [ -n "$GH_MERGE_FAIL" ] && { echo "$GH_MERGE_FAIL" >&2; exit 1; }; exit 0; fi\n'
        'if [ "$1 $2" = "run view" ] && [[ " $* " == *" --json "* ]]; then f=$(mktemp); printf "%s" "${GH_RUN_JOBS:-{\\"jobs\\":[]\\}}" > "$f"; '
        'while [ $# -gt 0 ]; do [ "$1" = --jq ] && q=$2; shift; done; jq -r "$q" "$f"; exit 0; fi\n'
        'if [ "$1 $2" = "run view" ]; then printf "%s\\n" "${GH_LOG_FAILED:-}"; exit 0; fi\n'
        'if [ "$1 $2" = "run rerun" ]; then exit 0; fi\n'
        'if [ "$1 $2" = "pr view" ] && [[ " $* " == *" files "* ]]; then [ -n "$GH_FILES_FAIL" ] && exit 1; printf "%s\\n" ${GH_PR_FILES:-we/x.py}; exit 0; fi\n'
        'if [ "$1" = api ]; then f=$(mktemp); case "$2" in *annotations*) printf "%s" "${GH_ANNOTATIONS:-[]}" > "$f" ;; *compare*) printf "%s" "${GH_COMPARE:-{\\"ahead_by\\":0,\\"commits\\":[]\\}}" > "$f" ;; *) echo \'{"default_branch":"main"}\' > "$f" ;; esac; '
        'while [ $# -gt 0 ]; do [ "$1" = --jq ] && q=$2; shift; done; jq -r "$q" "$f"; exit 0; fi\n'
        'if [ "$1 $2" = "run list" ]; then '
        + _queue(tmp_path, "runs", list(runs))
        + '; elif [[ " $* " == *" comments "* ]]; then '
        + _queue(tmp_path, "comments", list(comments))
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
        "WATCH_MAX_INTERVAL": "0",
        **(env_extra or {}),
    }
    env.pop("WATCH_REPO", None)
    res = subprocess.run(
        ["bash", str(SCRIPT), "57", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd or tmp_path,
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
        ("DIRTY", "UNKNOWN", "merge: DIRTY/UNKNOWN — conflicts with the base: merge it"),
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


def _codex(verdict, sha=SHA):
    body = (
        "<!-- codex-review -->\n## Codex Review\n\n"
        f"Reviewed commit `{sha}`.\n\n<!-- VERDICT:{verdict} -->\n"
        "<!-- history-start -->\n- `0000000` · ✅ PASS\n<!-- history-end -->"
    )
    return {"comments": [{"body": "unrelated"}, {"body": body}]}


def _with_codex(d, conclusion="SUCCESS", status="COMPLETED"):
    d = copy.deepcopy(d)
    d["statusCheckRollup"].append(
        {
            "__typename": "CheckRun",
            "name": "Codex Review",
            "status": status,
            "conclusion": conclusion,
        }
    )
    return d


def test_outside_a_repo_every_gh_call_names_the_repo_and_runs_from_the_callers_dir(tmp_path):
    code, out = run(tmp_path, [_green()])
    assert code == 0, out
    calls = (tmp_path / "calls.log").read_text().splitlines()
    # No git repo: the repo comes from `gh repo view`; every call stays in the caller's directory.
    assert calls[0] == f"{tmp_path} | repo view ", calls[0]
    rest = calls[1:]
    assert rest and all(c.startswith(f"{tmp_path} | ") and " -R o/r " in c for c in rest), rest


def make_worktree(tmp_path, remote):
    """A main checkout with `origin` = `remote` and a linked worktree; returns both paths."""
    main, wt = tmp_path / "main", tmp_path / "wt"
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run([*git, "init", "-q", str(main)], check=True)
    subprocess.run([*git, "-C", str(main), "commit", "-qm", "x", "--allow-empty"], check=True)
    subprocess.run([*git, "-C", str(main), "remote", "add", "origin", remote], check=True)
    subprocess.run([*git, "-C", str(main), "worktree", "add", "-q", str(wt)], check=True)
    return main.resolve(), wt


def test_from_a_worktree_gh_runs_in_the_main_checkout(tmp_path):
    """Regression: from `/` a gh that picks its account by directory answered
    "Could not resolve to a Repository"; the calls stay in the caller's repo instead, and
    `gh repo view` (set-default, a fork's upstream) still names the repo."""
    main, wt = make_worktree(tmp_path, "git@github.com:acme/app.git")
    code, out = run(tmp_path, [_green()], cwd=wt)
    assert code == 0, out
    calls = (tmp_path / "calls.log").read_text().splitlines()
    assert calls[0] == f"{main} | repo view ", calls
    assert all(c.startswith(f"{main} | ") and " -R o/r " in c for c in calls[1:]), calls


@pytest.mark.parametrize(
    "remote",
    [
        "git@github.com:acme/app.git",
        "https://github.com/acme/app",
        "ssh://git@github.com/acme/app.git",
    ],
)
def test_a_failing_repo_view_falls_back_to_a_github_origin(tmp_path, remote):
    _, wt = make_worktree(tmp_path, remote)
    code, out = run(tmp_path, [_green()], cwd=wt, env_extra={"GH_REPO_VIEW_FAIL": "1"})
    assert code == 0, out
    calls = (tmp_path / "calls.log").read_text().splitlines()
    assert all(" -R acme/app " in c for c in calls[1:]), calls


def test_a_non_github_origin_is_no_fallback(tmp_path):
    _, wt = make_worktree(tmp_path, "git@gitlab.com:acme/app.git")
    code, out = run(
        tmp_path, [_green()], cwd=wt, max_errors="2", env_extra={"GH_REPO_VIEW_FAIL": "1"}
    )
    assert code == 2 and out and out[-1].startswith("gh failed 2 times"), out


@pytest.mark.parametrize("state, code, word", [("MERGED", 7, "merged"), ("CLOSED", 8, "closed")])
def test_a_merged_or_closed_pr_is_never_red(tmp_path, state, code, word):
    # The merge cancelled the checks; the old watcher said `final … red`.
    cancelled = copy.deepcopy(REAL)
    for c in cancelled["statusCheckRollup"]:
        c["conclusion"] = "CANCELLED"
    gone = {**cancelled, "state": state}
    got, out = run(tmp_path, [_pending(_green()), gone])
    assert (got, out) == (code, [f"final {SHA}: {word}"])


def test_expected_head_waits_past_a_red_old_head(tmp_path):
    new = "c" * 40
    fresh = {**_green(), "headRefOid": new}
    code, out = run(tmp_path, [REAL, REAL, _pending(fresh), fresh], "--sha", new)
    assert (code, out) == (0, [f"final {new}: green · {MERGE}"])


def test_expected_head_never_arriving_has_its_own_exit(tmp_path):
    code, out = run(tmp_path, [REAL], "--sha", "d" * 40, env_extra={"WATCH_HEAD_TIMEOUT": "0"})
    assert (code, out) == (5, [f"head never reached {'d' * 40} (still {SHA}) after 0s"])


@pytest.mark.parametrize("verdict", ["WARNING", "BLOCKING"])
def test_codex_warning_on_the_head_returns_before_the_merge(tmp_path, verdict):
    armed = {**_with_codex(_pending(_green()), "FAILURE"), "autoMergeRequest": {"enabledAt": "x"}}
    code, out = run(tmp_path, [armed], "--until-merged", comments=[_codex(verdict)])
    assert code == 6
    assert out == [
        "fail: Codex Review",
        f"final {SHA}: codex {verdict} · auto-merge disarmed — then /we:ci-review",
    ]
    assert "pr merge 57 -R o/r --disable-auto" in (tmp_path / "calls.log").read_text()


def test_codex_warning_on_an_unarmed_pr_disarms_nothing(tmp_path):
    code, out = run(
        tmp_path, [_with_codex(_pending(_green()), "FAILURE")], comments=[_codex("WARNING")]
    )
    assert (code, out) == (
        6,
        [
            "fail: Codex Review",
            f"final {SHA}: codex WARNING · auto-merge off — then /we:ci-review",
        ],
    )
    assert "pr merge" not in (tmp_path / "calls.log").read_text()


def test_a_failed_disarm_names_the_command(tmp_path):
    armed = {**_with_codex(_pending(_green()), "FAILURE"), "autoMergeRequest": {"enabledAt": "x"}}
    code, out = run(
        tmp_path, [armed], comments=[_codex("BLOCKING")], env_extra={"GH_MERGE_FAIL": "HTTP 403"}
    )
    assert code == 6
    assert out == [
        "fail: Codex Review",
        f"final {SHA}: codex BLOCKING · auto-merge on (disarm failed: HTTP 403) — run "
        "`gh pr merge 57 --disable-auto` — then /we:ci-review",
    ]


def test_a_red_review_check_on_an_armed_pr_disarms_it(tmp_path):
    armed = {**REAL, "autoMergeRequest": {"enabledAt": "x"}}
    code, out = run(tmp_path, [armed], "--fail-fast")
    assert code == 1
    assert out[-1].endswith("· auto-merge disarmed"), out
    assert "pr merge 57 -R o/r --disable-auto" in (tmp_path / "calls.log").read_text()


def test_a_red_check_that_is_no_review_leaves_auto_merge_armed(tmp_path):
    armed = {**REAL, "autoMergeRequest": {"enabledAt": "x"}}
    code, out = run(tmp_path, [armed], env_extra={"WATCH_REVIEW_RX": "^lint$"})
    assert code == 1
    assert "disarm" not in out[-1]
    assert "pr merge" not in (tmp_path / "calls.log").read_text()


def test_a_codex_warning_with_its_check_green_after_a_skip_does_not_stop(tmp_path):
    """core #6266: every finding was skipped with a reason, the `Codex Review` check turned green;
    the comment still says WARNING and must not disarm or stop the watch."""
    armed = {**_with_codex(_green()), "autoMergeRequest": {"enabledAt": "x"}}
    code, out = run(tmp_path, [armed], comments=[_codex("WARNING")])
    assert (code, out[-1]) == (0, f"final {SHA}: green · {MERGE}")
    assert "pr merge" not in (tmp_path / "calls.log").read_text()


def test_codex_pass_or_an_older_heads_warning_does_not_stop(tmp_path):
    code, out = run(tmp_path, [_with_codex(_green())], comments=[_codex("WARNING", "e" * 40)])
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])
    (tmp_path / "pass").mkdir()
    code, out = run(tmp_path / "pass", [_with_codex(_green())], comments=[_codex("PASS")])
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])


def test_codex_comment_is_not_read_while_its_check_runs(tmp_path):
    running = _with_codex(_green(), status="IN_PROGRESS", conclusion="")
    code, out = run(
        tmp_path, [running, running, running, _with_codex(_green())], comments=[_codex("PASS")]
    )
    assert code == 0, out
    # Three reads with Codex running, then one comment read once its check completed.
    assert int((tmp_path / "comments" / "count").read_text()) == 1


def test_until_merged_keeps_watching_green_until_merged(tmp_path):
    armed = {**_green(), "autoMergeRequest": {"enabledAt": "x"}, "mergeStateStatus": "BLOCKED"}
    merged = {**armed, "state": "MERGED"}
    code, out = run(tmp_path, [armed, armed, armed, armed, merged], "--until-merged")
    assert (code, out) == (7, [f"final {SHA}: merged"])
    assert int((tmp_path / "views" / "count").read_text()) >= 5


@pytest.mark.parametrize(
    "patch, note",
    [
        ({}, "merge: UNKNOWN/UNKNOWN · auto-merge off"),
        (
            {"autoMergeRequest": {"enabledAt": "x"}, "mergeStateStatus": "DIRTY"},
            "merge: DIRTY/UNKNOWN — conflicts with the base: merge it",
        ),
        (
            {"autoMergeRequest": {"enabledAt": "x"}, "mergeStateStatus": "BEHIND"},
            "merge: BEHIND/UNKNOWN — behind the base: merge it",
        ),
    ],
)
def test_until_merged_stops_on_green_that_will_not_merge(tmp_path, patch, note):
    code, out = run(tmp_path, [{**_green(), **patch}], "--until-merged")
    assert (code, out) == (0, [f"final {SHA}: green · {note}"])


def test_lifetime_cap_ends_the_watch(tmp_path):
    armed = {**_green(), "autoMergeRequest": {"enabledAt": "x"}, "mergeStateStatus": "BLOCKED"}
    code, out = run(tmp_path, [armed], "--until-merged", env_extra={"WATCH_MAX_LIFETIME": "1"})
    assert (code, out) == (9, [f"gave up after 1s on {SHA}"])


def test_until_merged_reports_a_green_pr_blocked_past_the_grace(tmp_path, monkeypatch):
    monkeypatch.setenv("WATCH_BLOCKED_GRACE", "0")
    armed = {**_green(), "autoMergeRequest": {"enabledAt": "x"}, "mergeStateStatus": "BLOCKED"}
    code, out = run(tmp_path, [armed] * 6, "--until-merged")
    assert code == 0 and out[-1].startswith(f"final {SHA}: green") and "BLOCKED" in out[-1], out


# Review 09.11. (sister crew): infra reruns, stale heads, missing runs, review quota, conflicts early.

SONNET_FAIL = "Claude Review (Analyze)"


def _only_failing(name, d=None):
    """The rollup with every check green but `name`, which failed in run 41."""
    d = copy.deepcopy(d or _green())
    for c in d["statusCheckRollup"]:
        if c["name"] == name:
            c.update(conclusion="FAILURE", detailsUrl=RUN_URL.format(41, 1))
    return d


def test_a_job_that_failed_on_a_5xx_is_rerun_once_and_counts_as_pending(tmp_path):
    lint = "Python Lint & Format"
    code, out = run(
        tmp_path,
        [_only_failing(lint), _only_failing(lint), _green()],
        env_extra={"GH_LOG_FAILED": "Error: HTTP 503 Service Unavailable from ghcr.io"},
    )
    assert code == 0, out
    assert out[0] == f'infra: {lint} failed on "HTTP 503" — rerun once (run 41)'
    assert out[-1] == f"final {SHA}: green · {MERGE}"
    calls = (tmp_path / "calls.log").read_text()
    assert calls.count("run rerun 41") == 1


def test_an_infra_failure_is_rerun_only_once(tmp_path):
    lint = "Python Lint & Format"
    code, out = run(
        tmp_path,
        [_only_failing(lint)],
        env_extra={"GH_LOG_FAILED": "connect: ETIMEDOUT registry.npmjs.org"},
    )
    assert code == 1
    assert sum(line.startswith("infra:") for line in out) == 1
    assert out[-1].startswith(f"final {SHA}: red · failed: {lint}")


def test_a_code_failure_is_not_rerun(tmp_path):
    lint = "Python Lint & Format"
    code, out = run(
        tmp_path, [_only_failing(lint)], env_extra={"GH_LOG_FAILED": "E501 line too long"}
    )
    assert code == 1 and not any(line.startswith("infra:") for line in out)
    assert "run rerun" not in (tmp_path / "calls.log").read_text()


def test_a_red_head_behind_the_default_branch_says_the_run_predates_it(tmp_path):
    lint = "Python Lint & Format"
    newest = "abcdef1234567890"
    code, out = run(
        tmp_path,
        [_only_failing(lint)],
        env_extra={
            "GH_COMPARE": json.dumps(
                {"ahead_by": 2, "commits": [{"sha": "0" * 16}, {"sha": newest}]}
            )
        },
    )
    assert code == 1
    assert out[-1].endswith(" · run predates abcdef123456 (main is 2 ahead: merge it, then rerun)")


def test_no_run_and_no_check_ends_with_its_own_exit(tmp_path):
    empty = {"headRefOid": SHA, "statusCheckRollup": []}
    code, out = run(tmp_path, [empty], env_extra={"WATCH_NO_RUN_TIMEOUT": "0"})
    assert (code, out) == (10, [f"no workflow ran on {SHA} after 0s"])


def test_a_review_that_failed_on_its_quota_keeps_auto_merge_and_exits_11(tmp_path):
    d = {**_only_failing(SONNET_FAIL), "autoMergeRequest": {"enabledAt": "x"}}
    code, out = run(
        tmp_path,
        [d],
        env_extra={
            "GH_LOG_FAILED": "##[error]Claude review failed: usage limit reached, resets 5am"
        },
    )
    assert code == 11
    assert out[-1] == (
        f"final {SHA}: review quota ({SONNET_FAIL}: usage limit) · auto-merge stays on"
        " — quota: rerun after the next verdict"
    )
    assert "pr merge" not in (tmp_path / "calls.log").read_text()


def test_a_codex_error_on_quota_exits_11(tmp_path):
    body = _codex("ERROR")
    body["comments"][1]["body"] += "\nCodex failed: You've hit your usage limit."
    code, out = run(tmp_path, [_with_codex(_green())], comments=[body])
    assert code == 11 and "review quota (codex: hit your usage limit)" in out[-1]


def test_a_codex_error_prints_its_reason_and_the_watch_goes_on(tmp_path):
    body = _codex("ERROR")
    body["comments"][1]["body"] += "\nCodex failed: model returned no review."
    code, out = run(tmp_path, [_with_codex(_green())], comments=[body])
    assert code == 0
    assert out[0] == "codex ERROR: Codex failed: model returned no review. — rerun the Codex check"


def test_a_conflict_ends_the_watch_before_the_checks(tmp_path):
    d = {**_pending(_green()), "mergeStateStatus": "DIRTY", "mergeable": "CONFLICTING"}
    code, out = run(tmp_path, [d])
    assert (code, out) == (12, [f"final {SHA}: conflicts with the base — merge it"])


def test_a_review_verdict_whose_echoed_script_names_quota_is_red_not_quota(tmp_path):
    """Claude Review on #198: the step's echoed `run:` script mentions `quota`; only the error
    annotation decides."""
    d = {**_only_failing(SONNET_FAIL), "autoMergeRequest": {"enabledAt": "x"}}
    log = (
        'Gate\t##[group]Run case "$CAUSE" in\n'
        "Gate\t\x1b[36;1m# Name the cause (auth · quota · refused · other)\x1b[0m\n"
        "Gate\t##[error]Claude review verdict BLOCKING — fix the findings, then push again."
    )
    code, out = run(tmp_path, [d], env_extra={"GH_LOG_FAILED": log})
    assert code == 1 and "auto-merge disarmed" in out[-1]


def test_a_failing_assertion_on_a_500_is_no_infra(tmp_path):
    lint = "Python Lint & Format"
    log = "E   assert resp.status_code == 500\nerror: status 500 in test_api"
    code, out = run(tmp_path, [_only_failing(lint)], env_extra={"GH_LOG_FAILED": log})
    assert code == 1 and not any(line.startswith("infra:") for line in out)


# A consumer crew's masters each reran a job blind that had never started (billing): zero steps.
ZERO_JOBS = json.dumps(
    {"jobs": [{"databaseId": 99, "name": "lint", "conclusion": "failure", "steps": []}]}
)
BILLING = json.dumps([{"message": "The job was not started because of a billing issue"}])


def _failed_with_run(name="Lint", run_id=123):
    d = _green()
    d["statusCheckRollup"][0].update(
        name=name,
        conclusion="FAILURE",
        detailsUrl=RUN_URL.format(run_id, 99),
        startedAt="2026-10-04T03:00:00Z",  # the newest run of its name on the head
    )
    return d


def test_a_failed_job_with_zero_steps_is_infra_not_red(tmp_path):
    code, out = run(
        tmp_path,
        [_failed_with_run()],
        env_extra={"GH_RUN_JOBS": ZERO_JOBS, "GH_ANNOTATIONS": BILLING},
    )
    assert code == 13, out
    assert out[-1] == (
        f"final {SHA}: infra · Lint: job never started (The job was not started because of a "
        "billing issue) — do not rerun, tell the coordinator"
    )
    assert "run rerun" not in (tmp_path / "calls.log").read_text()


@pytest.mark.parametrize(
    "extra",
    [{"GH_PR_FILES": ".github/workflows/ci.yml we/x.py"}, {"GH_FILES_FAIL": "1"}],
    ids=["workflow-change", "files-unreadable"],
)
def test_a_zero_step_job_on_a_pr_that_changes_a_workflow_stays_red(tmp_path, extra):
    """Red arm: a broken `runs-on:` or `if:` in the PR's own workflow fails the job before its
    first step; that is the PR's fault, so exit 13 never hides it (fail-closed when unreadable)."""
    code, out = run(
        tmp_path,
        [_failed_with_run()],
        env_extra={"GH_RUN_JOBS": ZERO_JOBS, "GH_ANNOTATIONS": BILLING, **extra},
    )
    assert code == 1 and out[-1].startswith(f"final {SHA}: red · failed: Lint"), out


def test_a_failed_job_that_ran_steps_stays_red(tmp_path):
    ran = json.dumps(
        {"jobs": [{"databaseId": 99, "name": "lint", "conclusion": "failure", "steps": [{}]}]}
    )
    code, out = run(tmp_path, [_failed_with_run()], env_extra={"GH_RUN_JOBS": ran})
    assert code == 1 and out[-1].startswith(f"final {SHA}: red · failed: Lint"), out


def test_until_merged_watches_past_a_red_non_required_check_to_the_merge(tmp_path):
    armed = {
        **_failed_with_run("auto-merge"),
        "autoMergeRequest": {"enabledAt": "x"},
        "mergeStateStatus": "UNSTABLE",
    }
    merged = {**armed, "state": "MERGED"}
    code, out = run(tmp_path, [armed, armed, armed, merged], "--until-merged")
    assert code == 7, out
    assert out[-1] == f"final {SHA}: merged (red: auto-merge)"  # red arm: the red stays visible
    assert sum(line.startswith("still merging: auto-merge red") for line in out) == 1


def test_until_merged_a_red_review_check_still_ends_red(tmp_path):
    """Red arm: a failed review is never watched past, merging or not."""
    armed = {
        **_failed_with_run("Claude Review"),
        "autoMergeRequest": {"enabledAt": "x"},
        "mergeStateStatus": "UNSTABLE",
    }
    code, out = run(tmp_path, [armed, armed, armed], "--until-merged")
    assert code == 1 and "red · failed: Claude Review" in out[-1], out


def test_until_merged_ends_red_when_the_pr_cannot_merge(tmp_path):
    blocked = {
        **_failed_with_run("auto-merge"),
        "autoMergeRequest": {"enabledAt": "x"},
        "mergeStateStatus": "BLOCKED",
    }
    code, out = run(tmp_path, [blocked], "--until-merged")
    assert code == 1 and "red · failed: auto-merge" in out[-1], out


def test_a_real_failure_beside_a_job_that_never_started_stays_red(tmp_path):
    """The zero-step job is a sibling in the same run, not the job behind this check (job 99)."""
    sibling = json.dumps(
        {"jobs": [{"databaseId": 7, "name": "deploy", "conclusion": "failure", "steps": []}]}
    )
    code, out = run(
        tmp_path,
        [_failed_with_run()],
        env_extra={"GH_RUN_JOBS": sibling, "GH_ANNOTATIONS": BILLING},
    )
    assert code == 1 and out[-1].startswith(f"final {SHA}: red · failed: Lint"), out


def test_only_the_newest_run_of_a_check_counts(tmp_path):
    """A draft run left a red `ci-summary` on the head; the ready run of the same workflow passed
    it. Red arm: the watcher printed `fail: ci-summary` and ended red although the PR was green."""
    d = _green()
    old, new = copy.deepcopy(d["statusCheckRollup"][1]), copy.deepcopy(d["statusCheckRollup"][1])
    old.update(name="ci-summary", conclusion="FAILURE", startedAt="2026-10-04T02:00:00Z")
    new.update(name="ci-summary", conclusion="SUCCESS", startedAt="2026-10-04T02:40:00Z")
    d["statusCheckRollup"] += [old, new]
    code, out = run(tmp_path, [d])
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])
    # the newer run still going keeps the check pending, the older red does not end it red
    running = copy.deepcopy(d)
    running["statusCheckRollup"][-1].update(status="IN_PROGRESS", conclusion="", startedAt=None)
    (tmp_path / "b").mkdir()
    code, out = run(tmp_path / "b", [running, d])
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])
    # gh writes a queued run's unset startedAt as zero time, not null: still the newest
    queued = copy.deepcopy(d)
    queued["statusCheckRollup"][-1].update(
        status="QUEUED", conclusion="", startedAt="0001-01-01T00:00:00Z"
    )
    (tmp_path / "q").mkdir()
    code, out = run(tmp_path / "q", [queued, queued, d], "--fail-fast")
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])
    # a check of the same name in another workflow is its own check
    other = copy.deepcopy(d)
    other["statusCheckRollup"][-2]["workflowName"] = "Nightly"
    (tmp_path / "c").mkdir()
    code, out = run(tmp_path / "c", [other])
    assert code == 1 and "fail: ci-summary" in out
