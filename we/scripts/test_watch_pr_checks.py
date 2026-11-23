"""watch-pr-checks.sh against a stub `gh` that replays one rollup per call.

The fixture is a real `gh pr view --json headRefOid,statusCheckRollup` answer (PR #57, 2026-10-04).
"""

import copy
import fcntl
import json
import os
import shutil
import stat
import subprocess
import threading
import time
from pathlib import Path

import pytest

HERE = Path(__file__).parent
SCRIPT = HERE / "watch-pr-checks.sh"
REAL = json.loads((HERE / "fixtures" / "pr-checks-rollup.json").read_text())
SHA = REAL["headRefOid"]
MERGE = "merge: UNKNOWN/UNKNOWN"
RISK_RULES = HERE.parents[1] / ".weside" / "risk-paths"
UNKNOWN_CLASS = "arm: arm_pr.sh 57 (class unknown: a one-way class arms only after the human's yes on the board)"
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
    required=(),
):
    """`answers` replays `gh pr view`, `runs` `gh run list --commit <sha>`, `comments` the
    `gh pr view --json comments` read, `required` the base branch's required check names (its
    ruleset). Every call's argv and cwd land in `calls.log`."""
    gh = tmp_path / "gh"
    log = tmp_path / "calls.log"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        f'a="$*"; echo "$(pwd) | ${{a%%--json*}}" >> "{log}"\n'
        '[ -n "$GH_NOTICE" ] && printf "%s\\n" "$GH_NOTICE" >&2\n'
        'if [ "$1 $2" = "repo view" ]; then [ -n "$GH_REPO_VIEW_FAIL" ] && exit 1; echo o/r; exit 0; fi\n'
        'if [ "$1 $2" = "pr merge" ]; then [ -n "$GH_MERGE_FAIL" ] && { echo "$GH_MERGE_FAIL" >&2; exit 1; }; exit 0; fi\n'
        'if [ "$1 $2" = "run view" ] && [[ " $* " == *" --json "* ]]; then f=$(mktemp); printf "%s" "${GH_RUN_JOBS:-{\\"jobs\\":[]\\}}" > "$f"; '
        'while [ $# -gt 0 ]; do [ "$1" = --jq ] && q=$2; shift; done; jq -r "$q" "$f"; exit 0; fi\n'
        'if [ "$1 $2" = "run view" ]; then printf "%s\\n" "${GH_LOG_FAILED:-}"; exit 0; fi\n'
        'if [ "$1 $2" = "run rerun" ]; then exit 0; fi\n'
        'if [ "$1 $2" = "pr view" ] && [[ " $* " == *" files "* ]]; then [ -n "$GH_FILES_FAIL" ] && exit 1; printf "%s\\n" ${GH_PR_FILES:-we/x.py}; exit 0; fi\n'
        'if [ "$1" = api ]; then f=$(mktemp); case "$2" in rate_limit) n=$(cat "$GH_RATE_DIR/count" 2>/dev/null || echo 0); echo $((n+1)) > "$GH_RATE_DIR/count"; r="$GH_RATE_DIR/$n.json"; [ -f "$r" ] || r="$GH_RATE_DIR/last.json"; cp "$r" "$f" 2>/dev/null || echo "{}" > "$f" ;; *annotations*) printf "%s" "${GH_ANNOTATIONS:-[]}" > "$f" ;; *compare*) printf "%s" "${GH_COMPARE:-{\\"ahead_by\\":0,\\"commits\\":[]\\}}" > "$f" ;; '
        '*rules/branches/*) [ -n "$GH_RULES_FAIL" ] && { echo "HTTP 403" >&2; exit 1; }; printf "%s" "${GH_RULES:-[]}" > "$f" ;; '
        '*/branches/*) echo "{}" > "$f" ;; *) echo \'{"default_branch":"main"}\' > "$f" ;; esac; '
        'while [ $# -gt 0 ]; do [ "$1" = --jq ] && q=$2; shift; done; jq -r "$q" "$f"; exit 0; fi\n'
        'if [ "$1 $2" = "run list" ]; then '
        + _queue(tmp_path, "runs", list(runs))
        + '; elif [[ " $* " == *" comments "* ]]; then '
        + _queue(tmp_path, "comments", list(comments))
        + "; else "
        + _queue(tmp_path, "views", answers)
        + '; [ -n "$GH_RM_ON_MERGED" ] && grep -q MERGED "$f" && rm -rf "$GH_RM_ON_MERGED"'
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
        "WATCH_MIN_INTERVAL": "0",
        "WE_STATE_DIR": str(tmp_path / "state"),
        "GH_RATE_DIR": str(tmp_path / "rate"),
        "GH_RULES": json.dumps(
            [
                {
                    "type": "required_status_checks",
                    "parameters": {"required_status_checks": [{"context": n} for n in required]},
                }
            ]
        ),
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


# What gh 2.105.0 prints on stderr after `gh pr view`: a preview notice, never part of the answer.
NOTICE = "\n".join(
    [
        "",
        "A new preview command is available: gh event listen",
        "Stream repository events to your terminal as they happen.",
        "",
        "Try it: gh event listen --repo o/r",
        "Hide this notice: gh config set notices false",
        "",
    ]
)


def test_notices_on_stderr_never_become_the_head(tmp_path):
    code, out = run(
        tmp_path, [_pending(_green()), _green()], timeout_s="5", env_extra={"GH_NOTICE": NOTICE}
    )
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])


def test_a_failing_gh_names_its_error_not_a_notice(tmp_path):
    code, out = run(tmp_path, ["FAIL"], max_errors="2", env_extra={"GH_NOTICE": NOTICE})
    assert (code, out) == (
        2,
        ["gh failed 2 times in a row: GraphQL: Could not resolve to a PullRequest"],
    )


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


def _run_lists(tmp_path):
    return [c for c in (tmp_path / "calls.log").read_text().splitlines() if "| run list" in c]


def test_running_and_green_ticks_read_no_runs_until_the_one_green_confirmation(tmp_path):
    # `gh run list` is REST, the quota the 22.11. outage drained: a running tick reads only the
    # GraphQL rollup, and the green verdict confirms with one run read.
    running = _pending(_green())
    code, out = run(tmp_path, [running, running, running, _green()])
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])
    assert int((tmp_path / "views" / "count").read_text()) >= 5
    assert len(_run_lists(tmp_path)) == 1


def test_a_red_tick_reads_the_runs_once(tmp_path):
    code, out = run(
        tmp_path, [_pending(_green()), _pending(_green()), _pending(_green()), REAL], "--fail-fast"
    )
    assert code == 1, out
    assert len(_run_lists(tmp_path)) == 1


def test_a_green_rollup_with_an_open_run_stays_pending(tmp_path):
    # A run queued before its first check registered is in no rollup: the confirmation read sees it.
    queued = [{"databaseId": 7, "attempt": 1, "status": "queued"}]
    done = [{"databaseId": 7, "attempt": 1, "status": "completed"}]
    code, out = run(tmp_path, [_green()], runs=[queued, queued, done])
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])
    assert len(_run_lists(tmp_path)) == 3


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
    # The quota read is the account's, not the repo's: it carries no -R, but stays in the same dir.
    assert all(c.startswith(f"{tmp_path} | ") for c in rest), rest
    rest = [c for c in rest if " api rate_limit " not in c]
    assert rest and all(" -R o/r " in c for c in rest), rest


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
    assert all(c.startswith(f"{main} | ") for c in calls[1:]), calls
    assert all(" -R o/r " in c for c in calls[1:] if " api rate_limit " not in c), calls


def test_a_merge_that_removes_the_start_worktree_still_exits_0(tmp_path):
    """`/we:merged` removes the tree the watcher started in: the merge stays the good end."""
    _, wt = make_worktree(tmp_path, "git@github.com:acme/app.git")
    merged = {**_green(), "state": "MERGED"}
    code, out = run(
        tmp_path, [_pending(_green()), merged], cwd=wt, env_extra={"GH_RM_ON_MERGED": str(wt)}
    )
    assert not wt.exists()
    assert (code, out) == (0, [f"final {SHA}: merged"])


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
    assert all(" -R acme/app " in c for c in calls[1:] if " api rate_limit " not in c), calls


def test_a_non_github_origin_is_no_fallback(tmp_path):
    _, wt = make_worktree(tmp_path, "git@gitlab.com:acme/app.git")
    code, out = run(
        tmp_path, [_green()], cwd=wt, max_errors="2", env_extra={"GH_REPO_VIEW_FAIL": "1"}
    )
    assert code == 2 and out and out[-1].startswith("gh failed 2 times"), out


@pytest.mark.parametrize("state, code, word", [("MERGED", 0, "merged"), ("CLOSED", 8, "closed")])
def test_a_merged_or_closed_pr_is_never_red(tmp_path, state, code, word):
    # The merge cancelled the checks; the old watcher said `final … red`.
    cancelled = copy.deepcopy(REAL)
    for c in cancelled["statusCheckRollup"]:
        c["conclusion"] = "CANCELLED"
    gone = {**cancelled, "state": state}
    got, out = run(tmp_path, [_pending(_green()), gone])
    assert (got, out) == (code, [f"final {SHA}: {word}"])


@pytest.mark.parametrize(
    "state, news, calls",
    [("MERGED", "1", ["news merged --pr o/r#57"]), ("MERGED", "0", []), ("CLOSED", "1", [])],
)
def test_a_merge_hands_the_pr_to_the_board_news_once(tmp_path, state, news, calls):
    """A merged PR goes to `board.py news merged` (it judges the rule paths); off with
    WATCH_RULES_NEWS=0, never on a closed PR."""
    log = tmp_path / "python3.log"
    shim = tmp_path / "python3"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        f'case "$1" in */board.py) shift; echo "$*" >> "{log}"; exit 0 ;; esac\n'
        f'exec "{shutil.which("python3")}" "$@"\n'
    )
    shim.chmod(0o755)
    run(
        tmp_path,
        [_pending(_green()), {**_green(), "state": state}],
        env_extra={"WATCH_RULES_NEWS": news},
    )
    assert (log.read_text().splitlines() if log.exists() else []) == calls


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
    assert (code, out) == (0, [f"final {SHA}: merged"])
    assert int((tmp_path / "views" / "count").read_text()) >= 5


@pytest.mark.parametrize(
    "patch, note",
    [
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


@pytest.mark.parametrize(
    "merge, patch, step",
    [
        ({"armer": "workflow"}, {}, "the repo's workflow arms a ready PR"),
        (
            {"armer": "workflow"},
            {"isDraft": True},
            "the repo's workflow arms it once ready: gh pr ready 57",
        ),
        (
            {"armer": "workflow", "hold_labels": ["review"]},
            {"labels": [{"name": "docs"}, {"name": "review"}]},
            "label review: the human merges",
        ),
        ({"hold_labels": ["review"]}, {"labels": [{"name": "docs"}]}, UNKNOWN_CLASS),
    ],
    ids=["workflow-ready", "workflow-draft", "hold-label", "other-label"],
)
def test_auto_merge_off_names_the_crews_armer(tmp_path, merge, patch, step):
    """Red arm: every unarmed PR was told `arm_pr.sh`, which refuses a workflow armer and a hold label."""
    (tmp_path / ".git").mkdir()  # bounds the crew lookup at tmp_path
    (tmp_path / ".weside").mkdir()
    crew = {"version": 2, "roles": {}, "members": {}, "merge": merge}
    (tmp_path / ".weside" / "crew.json").write_text(json.dumps(crew))
    merged = {**_green(), **patch, "state": "MERGED"}
    code, out = run(tmp_path, [{**_green(), **patch}] * 3 + [merged], "--until-merged")
    assert (code, out[0]) == (
        0,
        f"waiting {SHA}: green · {MERGE} · auto-merge off — {step} — watching to the merge",
    )


def test_until_merged_says_auto_merge_off_once_and_watches_to_the_merge(tmp_path):
    """Red: the watcher ended on `auto-merge off` and its master sat beside a PR that merged later."""
    unarmed = _green()
    armed = {**unarmed, "autoMergeRequest": {"enabledAt": "x"}, "mergeStateStatus": "BLOCKED"}
    merged = {**armed, "state": "MERGED"}
    code, out = run(tmp_path, [unarmed] * 5 + [armed, armed, merged], "--until-merged")
    assert (code, out) == (
        0,
        [
            f"waiting {SHA}: green · {MERGE} · auto-merge off — {UNKNOWN_CLASS} — watching to the merge",
            f"final {SHA}: merged",
        ],
    )


def _risk_clone(tmp_path, path):
    """A clone whose origin/main carries the plugin's risk rules and a PR head commit touching
    `path` beside it (not checked out); returns the head SHA."""

    def git(*args):
        return subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    (tmp_path / ".weside").mkdir()
    shutil.copy(RISK_RULES, tmp_path / ".weside" / "risk-paths")
    git("init", "-q", "-b", "main")
    git("add", ".weside/risk-paths")
    git("commit", "-q", "-m", "rules")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    git("checkout", "-q", "-b", "pr")
    (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / path).write_text("x\n")
    git("add", path)
    git("commit", "-q", "-m", "head")
    head = git("rev-parse", "HEAD")
    git("checkout", "-q", "main")
    return head


@pytest.mark.parametrize(
    ("path", "step"),
    [
        (
            "we/scripts/arm_pr.sh",
            "one-way brake-change: arm only after the human's yes on the board",
        ),
        ("README.md", "arm: arm_pr.sh 57"),
    ],
    ids=["one-way", "two-way"],
)
def test_auto_merge_off_names_a_one_way_class(tmp_path, path, step):
    """Red arm: the hint said `arm: arm_pr.sh <PR>` for a one-way head too, an arm the human's yes
    on the board has to come first for."""
    head = _risk_clone(tmp_path, path)
    unarmed = {**_green(), "headRefOid": head, "baseRefName": "main"}
    code, out = run(tmp_path, [unarmed] * 3 + [{**unarmed, "state": "MERGED"}], "--until-merged")
    assert (code, out[0]) == (
        0,
        f"waiting {head}: green · {MERGE} · auto-merge off — {step} — watching to the merge",
    )


def test_until_merged_ends_an_unarmed_pr_blocked_past_the_grace(tmp_path, monkeypatch):
    """A required review holds an unarmed PR too: polling it to the lifetime cap helps nobody."""
    monkeypatch.setenv("WATCH_BLOCKED_GRACE", "0")
    unarmed = {**_green(), "mergeStateStatus": "BLOCKED"}
    code, out = run(tmp_path, [unarmed] * 6, "--until-merged")
    assert code == 0 and out[-1].startswith(f"final {SHA}: green") and "BLOCKED" in out[-1], out


def test_until_merged_follows_a_moved_head_to_the_merge(tmp_path):
    """Red: a push during the watch ended it with exit 3 and nobody watched the new head."""
    new = "b" * 40
    armed = {**_green(), "autoMergeRequest": {"enabledAt": "x"}, "mergeStateStatus": "BLOCKED"}
    moved = {**armed, "headRefOid": new}
    code, out = run(
        tmp_path, [_pending(armed), moved, moved, {**moved, "state": "MERGED"}], "--until-merged"
    )
    assert (code, out) == (0, [f"head moved {SHA} -> {new} — watching it", f"final {new}: merged"])
    lock = (tmp_path / "state" / "watch-locks" / "o-r-57.lock").read_text()
    assert f"head {new} (follows new heads)" in lock, lock


def test_until_merged_judges_the_new_head_from_scratch(tmp_path):
    new = "b" * 40
    moved = {**REAL, "headRefOid": new}
    code, out = run(tmp_path, [_pending(_green()), _pending(moved), moved], "--until-merged")
    assert code == 1 and out[0] == f"head moved {SHA} -> {new} — watching it", out
    assert out[-1].startswith(f"final {new}: red"), out


def test_human_merge_waits_past_auto_merge_off_and_blocked_until_merged(tmp_path, monkeypatch):
    """A one-way PR is never armed: --until-merged ended on `auto-merge off` in seconds."""
    monkeypatch.setenv("WATCH_BLOCKED_GRACE", "0")
    unarmed = {**_green(), "mergeStateStatus": "BLOCKED"}
    merged = {**unarmed, "state": "MERGED"}
    code, out = run(tmp_path, [unarmed] * 5 + [merged], "--human-merge")
    assert (code, out) == (0, [f"final {SHA}: merged"])


def test_human_merge_still_stops_on_a_conflict(tmp_path):
    code, out = run(tmp_path, [{**_green(), "mergeStateStatus": "DIRTY"}], "--human-merge")
    assert (code, out) == (
        0,
        [f"final {SHA}: green · merge: DIRTY/UNKNOWN — conflicts with the base: merge it"],
    )


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


def test_a_cancelled_run_replaced_by_a_newer_run_counts_for_nothing(tmp_path):
    """`gh pr ready` cancelled the draft run (red `ci-summary`, cancelled `Repo`); the ready run of
    the same workflow is still queued, its jobs not yet on the head. Red arm: --fail-fast ended
    `red · failed: Repo` on the draft run's leftovers while the ready run went on."""
    d = _green()
    base = d["statusCheckRollup"][1]
    old_repo, old_sum = copy.deepcopy(base), copy.deepcopy(base)
    old_repo.update(name="Repo", conclusion="CANCELLED", detailsUrl=RUN_URL.format(100, 1))
    old_sum.update(name="ci-summary", conclusion="FAILURE", detailsUrl=RUN_URL.format(100, 2))
    d["statusCheckRollup"] += [old_repo, old_sum]
    cancelled = {
        "databaseId": 100,
        "attempt": 1,
        "status": "completed",
        "conclusion": "cancelled",
        "workflowName": "CI",
        "event": "pull_request",
    }
    queued = {**cancelled, "databaseId": 101, "status": "queued", "conclusion": ""}
    done = {**queued, "status": "completed", "conclusion": "success"}
    # the ready run reports Repo and ci-summary green, newer than the draft run's rows
    ready = copy.deepcopy(d)
    for name, job in (("Repo", 3), ("ci-summary", 4)):
        new = copy.deepcopy(base)
        new.update(
            name=name, startedAt="2026-10-05T00:00:00Z", detailsUrl=RUN_URL.format(101, job)
        )
        ready["statusCheckRollup"].append(new)
    code, out = run(
        tmp_path, [d, d, ready], "--fail-fast", runs=[[cancelled, queued], [cancelled, done]]
    )
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])
    # the newer run finished without reporting the cancelled check: it is the latest, so red
    (tmp_path / "d").mkdir()
    code, out = run(tmp_path / "d", [d], runs=[[cancelled, done]])
    assert code == 1 and out[-1].startswith(f"final {SHA}: red · failed: "), out
    assert "Repo" in out[-1], out
    # without a newer run of that workflow and event the cancelled run still counts
    (tmp_path / "b").mkdir()
    other = {**done, "event": "workflow_dispatch"}
    code, out = run(tmp_path / "b", [d], runs=[[cancelled, other]])
    assert code == 1 and out[-1].startswith(f"final {SHA}: red · failed: "), out
    # only leftovers of the replaced run: nothing to judge yet, never green
    (tmp_path / "c").mkdir()
    only_old = {**d, "statusCheckRollup": [old_repo, old_sum]}
    code, out = run(tmp_path / "c", [only_old], runs=[[cancelled, queued]], timeout_s="0")
    assert code == 4, out


# --- quota, one watcher per PR, interval floor ------------------------------------------------


def _sleep_stub(tmp_path):
    """A `sleep` beside the stub gh that only logs its argument into calls.log."""
    stub = tmp_path / "sleep"
    stub.write_text(
        f'#!/usr/bin/env bash\necho "$(pwd) | sleep $*" >> "{tmp_path / "calls.log"}"\n'
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)


def _rate(tmp_path, *answers):
    d = tmp_path / "rate"
    d.mkdir(exist_ok=True)
    for i, a in enumerate(answers):
        (d / f"{i}.json").write_text(json.dumps(a))
    (d / "last.json").write_text(json.dumps(answers[-1]))


def _limits(core, graphql, reset):
    return {
        "resources": {
            "core": {"remaining": core, "reset": reset},
            "graphql": {"remaining": graphql, "reset": reset},
        }
    }


def test_quota_under_the_floor_sleeps_until_the_reset_before_any_poll(tmp_path):
    reset = int(time.time()) + 120
    _rate(tmp_path, _limits(4000, 10, reset), _limits(5000, 5000, reset + 3600))
    _sleep_stub(tmp_path)
    code, out = run(tmp_path, [_green()])
    assert code == 0, out
    assert out[0].startswith("quota: 10 left, sleeping until "), out
    calls = [c.split(" | ", 1)[1] for c in (tmp_path / "calls.log").read_text().splitlines()]
    first_view = next(i for i, c in enumerate(calls) if c.startswith("pr view"))
    slept = [c for c in calls[:first_view] if c.startswith("sleep ")]
    assert slept and int(slept[0].split()[1]) >= 115, calls
    assert calls.index(slept[0]) > calls.index(
        next(c for c in calls if c.startswith("api rate_limit"))
    )


def test_quota_above_the_floor_polls_at_once(tmp_path):
    _rate(tmp_path, _limits(600, 600, int(time.time()) + 600))
    _sleep_stub(tmp_path)
    code, out = run(tmp_path, [_green()])
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])


def _hold(tmp_path, line):
    d = tmp_path / "state" / "watch-locks"
    d.mkdir(parents=True)
    f = (d / "o-r-57.lock").open("a+")
    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    f.truncate(0)
    f.write(line + "\n")
    f.flush()
    return f


needs_flock = pytest.mark.skipif(not shutil.which("flock"), reason="the lock needs flock(1)")


@needs_flock
def test_a_second_watcher_on_the_same_pr_exits_14_naming_the_holder(tmp_path):
    held = _hold(tmp_path, f"pid 4242 head {SHA}")
    try:
        code, out = run(tmp_path, [_green()], "--sha", SHA)
    finally:
        held.close()
    assert (code, out) == (
        14,
        [f"watcher already running on o/r#57: pid 4242 head {SHA} — this one exits"],
    )
    calls = (tmp_path / "calls.log").read_text()
    assert "pr view" not in calls and "run list" not in calls, calls


@needs_flock
def test_a_holder_that_follows_new_heads_turns_a_second_away_at_once(tmp_path):
    held = _hold(tmp_path, "pid 4242 head " + "b" * 40 + " (follows new heads)")
    try:
        code, out = run(tmp_path, [_green()], "--sha", SHA)
    finally:
        held.close()
    assert code == 14 and "follows new heads" in out[0], out


@needs_flock
def test_a_watcher_for_a_new_head_waits_for_the_old_one_to_end(tmp_path):
    held = _hold(tmp_path, "pid 4242 head " + "b" * 40)
    threading.Timer(1.0, held.close).start()
    code, out = run(tmp_path, [_green()], "--sha", SHA)
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])
    lock = (tmp_path / "state" / "watch-locks" / "o-r-57.lock").read_text()
    assert lock.startswith("pid ") and lock.strip().endswith(f"head {SHA}"), lock


def test_the_interval_never_drops_under_60_seconds(tmp_path):
    _sleep_stub(tmp_path)
    code, out = run(
        tmp_path,
        [_pending(_green()), _green()],
        env_extra={"WATCH_INTERVAL": "5", "WATCH_MIN_INTERVAL": ""},
    )
    assert code == 0, out
    slept = [
        int(c.rsplit(" ", 1)[1])
        for c in (tmp_path / "calls.log").read_text().splitlines()
        if " | sleep " in c
    ]
    assert slept and min(slept) == 60, slept


REQUIRED_EARLY = [REAL["statusCheckRollup"][0]["name"]]  # the check run 7 reports


def _merged_early(conclusion):
    """A PR merged by hand while CI run 7 on its head still runs; the run then ends `conclusion`."""
    open_run = {"databaseId": 7, "attempt": 1, "status": "in_progress", "conclusion": ""}
    closed_run = {**open_run, "status": "completed", "conclusion": conclusion.lower()}
    running = _pending(_green())
    running["statusCheckRollup"][0]["detailsUrl"] = RUN_URL.format(7, 1)
    merged = {**running, "state": "MERGED", "mergeCommit": {"oid": "m" * 40}}
    done = copy.deepcopy(merged)
    done["statusCheckRollup"][0].update(status="COMPLETED", conclusion=conclusion)
    return [running, merged, merged, done], [[open_run], [open_run], [open_run], [closed_run]]


@pytest.mark.parametrize("mode", [(), ("--until-merged",)])
def test_a_merge_before_ci_ended_is_watched_to_merged_green(tmp_path, mode):
    """Red arm: the watcher ended `final … merged` at the hand merge, the head's run still open."""
    views, runs = _merged_early("SUCCESS")
    code, out = run(tmp_path, views, *mode, runs=runs, required=REQUIRED_EARLY)
    assert (code, out) == (
        0,
        [
            f"merged {SHA} · merge commit {'m' * 12} before its CI ended — watching the head's runs to their end",
            f"final {SHA}: merged-green · merge commit {'m' * 12}",
        ],
    )


def test_a_merge_before_ci_ended_that_turns_red_has_its_own_exit(tmp_path):
    views, runs = _merged_early("FAILURE")
    code, out = run(tmp_path, views, "--until-merged", runs=runs, required=REQUIRED_EARLY)
    name = REAL["statusCheckRollup"][0]["name"]
    assert code == 15, out
    assert out[-1] == (
        f"final {SHA}: merged-red · merge commit {'m' * 12} · failed: {name}"
        " — the base branch carries it: fix it first"
    )


@pytest.mark.parametrize("verdict", ["WARNING", "BLOCKING"])
def test_a_codex_verdict_after_a_merge_before_ci_ended_ends_merged_red(tmp_path, verdict):
    """Red arm: exit 6 sent a PR already merged to /we:ci-review, the base branch unnamed."""
    views, runs = _merged_early("SUCCESS")
    views = [_with_codex(views[0], status="IN_PROGRESS", conclusion="")] + [
        _with_codex(v, "FAILURE") for v in views[1:]
    ]
    code, out = run(
        tmp_path,
        views,
        "--until-merged",
        runs=runs,
        comments=[_codex(verdict)],
        required=REQUIRED_EARLY,
    )
    assert (code, out[-1]) == (
        15,
        f"final {SHA}: merged-red · merge commit {'m' * 12} · codex {verdict}"
        " — the base branch carries it: fix it first",
    ), out


@pytest.mark.parametrize(
    "required, env",
    [(["Python Lint & Format"], {}), (["Python Lint & Format"], {"GH_RULES_FAIL": "1"}), ([], {})],
    ids=["required-green", "required-unreadable", "none-required"],
)
def test_an_auto_merge_past_an_open_non_required_run_is_the_end(tmp_path, required, env):
    """Red arm: GitHub merged on green required checks while a non-required run was still open,
    and the watcher read the merge as one past the checks: merged-red (exit 15) on that run's red."""
    views, runs = _merged_early("FAILURE")
    code, out = run(tmp_path, views, runs=runs, required=required, env_extra=env)
    assert (code, out) == (0, [f"final {SHA}: merged · merge commit {'m' * 12}"])


def test_a_run_created_after_the_merge_counts_for_nothing(tmp_path):
    """A `pull_request: closed` workflow on the head, even one whose job carries a required name,
    is no CI of the merged head: the red non-required check stays the merge's `(red: …)`."""
    armed = {
        **_failed_with_run("auto-merge"),
        "autoMergeRequest": {"enabledAt": "x"},
        "mergeStateStatus": "UNSTABLE",
    }
    merged = copy.deepcopy({**armed, "state": "MERGED", "mergedAt": "2026-10-04T04:00:00Z"})
    merged["statusCheckRollup"][1].update(  # Python Lint & Format, from the closed-event run 8
        status="QUEUED", conclusion="", startedAt=None, detailsUrl=RUN_URL.format(8, 1)
    )
    done = {"databaseId": 123, "attempt": 1, "status": "completed", "conclusion": "failure"}
    late = {
        "databaseId": 8,
        "attempt": 1,
        "status": "queued",
        "conclusion": "",
        "event": "pull_request",
        "createdAt": "2026-10-04T04:00:05Z",
    }
    code, out = run(
        tmp_path,
        [armed, armed, armed, merged],
        "--until-merged",
        runs=[[done], [done], [done, late]],  # the first view is read before the loop
        required=["Python Lint & Format"],
    )
    assert code == 7, out
    assert out[-1] == f"final {SHA}: merged (red: auto-merge)"


def test_a_merge_after_ci_ended_names_its_merge_commit(tmp_path):
    merged = {**_green(), "state": "MERGED", "mergeCommit": {"oid": "m" * 40}}
    code, out = run(tmp_path, [merged])
    assert (code, out) == (0, [f"final {SHA}: merged · merge commit {'m' * 12}"])


def test_a_failed_draft_run_replaced_by_an_open_run_prints_no_failure(tmp_path):
    """Red arm: the draft run's red ci-summary printed `fail: ci-summary` while the ready run ran."""
    d = _green()
    base = d["statusCheckRollup"][1]
    old_sum = copy.deepcopy(base)
    old_sum.update(name="ci-summary", conclusion="FAILURE", detailsUrl=RUN_URL.format(100, 2))
    d["statusCheckRollup"].append(old_sum)
    draft = {
        "databaseId": 100,
        "attempt": 1,
        "status": "completed",
        "conclusion": "failure",
        "workflowName": "CI",
        "event": "pull_request",
    }
    queued = {**draft, "databaseId": 101, "status": "queued", "conclusion": ""}
    done = {**queued, "status": "completed", "conclusion": "success"}
    ready = copy.deepcopy(d)
    new = copy.deepcopy(base)
    new.update(
        name="ci-summary", startedAt="2026-10-05T00:00:00Z", detailsUrl=RUN_URL.format(101, 4)
    )
    ready["statusCheckRollup"].append(new)
    code, out = run(
        tmp_path, [d, d, ready], runs=[[draft, queued], [draft, queued], [draft, done]]
    )
    assert (code, out) == (0, [f"final {SHA}: green · {MERGE}"])
