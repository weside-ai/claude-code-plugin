"""arm_pr.sh against a fake `gh` that replays PR reads and arm answers and logs every call.

No case may reach a merge: the log is checked for `gh pr merge` and for a merge mutation in every
test, whatever the scenario. `ARM_PR_UNDER_TEST` swaps the script for a red arm against a variant.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
SCRIPT = Path(os.environ.get("ARM_PR_UNDER_TEST") or HERE / "arm_pr.sh")
OLD, NEW = "a" * 40, "b" * 40
REQUIRED = ["lint", "Claude Review"]
CLEAN = "GraphQL: Pull request Pull request is in clean status (enablePullRequestAutoMerge)"
MOVED = "GraphQL: Head sha didn't match expected head oid (enablePullRequestAutoMerge)"

pytestmark = pytest.mark.skipif(not shutil.which("jq"), reason="the fake gh delegates --jq to jq")

FAKE = r"""
import json, os, subprocess, sys
d = os.environ["FAKE_DIR"]
args = sys.argv[1:]
if os.environ.get("GH_NOTICE"):
    sys.stderr.write(os.environ["GH_NOTICE"] + "\n")
with open(os.path.join(d, "calls.log"), "a") as f:
    f.write(json.dumps(args) + "\n")
jq = args[args.index("--jq") + 1] if "--jq" in args else None
def out(obj):
    if jq is None:
        print(json.dumps(obj)); sys.exit(0)
    sys.exit(subprocess.run(["jq", "-r", jq], input=json.dumps(obj), text=True).returncode)
def pop(name):
    items = json.load(open(os.path.join(d, name + ".json")))
    n_path = os.path.join(d, name + ".n")
    n = int(open(n_path).read()) if os.path.exists(n_path) else 0
    open(n_path, "w").write(str(n + 1))
    return items[min(n, len(items) - 1)]
if args[:2] == ["repo", "view"]:
    print("o/r"); sys.exit(0)
if args[:2] == ["api", "graphql"]:
    query = next(a[6:] for a in args if a.startswith("query="))
    if query.lstrip().startswith("mutation"):
        answer = pop("arms")
        if answer == "ok":
            out({"data": {"enablePullRequestAutoMerge": {"pullRequest": {"autoMergeRequest": {}}}}})
        sys.stderr.write(answer + "\n"); sys.exit(1)
    s = pop("reads")
    nodes = [{"__typename": "CheckRun", "name": n, "status": st, "conclusion": c, "isRequired": r,
              "startedAt": at[0] if at else None}
             for n, st, c, r, *at in s.get("checks", [])]
    out({"data": {"repository": {"pullRequest": {
        "id": "PR_1", "state": s.get("state", "OPEN"), "isDraft": s.get("draft", False),
        "headRefOid": s["head"], "baseRefName": "main",
        "mergeStateStatus": s.get("merge", "CLEAN"), "reviewDecision": s.get("review"),
        "labels": {"nodes": [{"name": n} for n in s.get("labels", [])]},
        "commits": {"nodes": [{"commit": {"oid": s.get("commit", s["head"]),
            "statusCheckRollup": {"contexts": {"nodes": nodes}}}}]}}}}})
if args[0] == "api" and "/rules/branches/" in args[1]:
    out([{"type": "required_status_checks", "parameters": {"required_status_checks":
        [{"context": c} for c in json.load(open(os.path.join(d, "required.json")))]}}])
if args[0] == "api" and "/branches/" in args[1]:
    out({"name": "main", "protection": {"required_status_checks": {"contexts": []}}})
said = os.path.join(d, "comments.json")  # the PR's comment bodies; `pr comment` adds one
if args[:2] == ["pr", "view"]:
    out({"comments": [{"body": b} for b in (json.load(open(said)) if os.path.exists(said) else [])]})
if args[:2] == ["pr", "comment"]:
    if os.environ.get("FAKE_COMMENT_FAILS"):
        sys.stderr.write("HTTP 502: comment failed\n"); sys.exit(1)
    bodies = json.load(open(said)) if os.path.exists(said) else []
    json.dump([*bodies, args[args.index("--body") + 1]], open(said, "w"))
sys.exit(0)  # anything else, `gh pr merge` included, "succeeds": the log is the witness
"""


def check(name, status="COMPLETED", conclusion="SUCCESS", required=True, started=None):
    return [name, status, conclusion, required, *([started] if started else [])]


GREEN = [check("lint"), check("Claude Review")]
PENDING = [check("lint"), check("Claude Review", "IN_PROGRESS", None)]


def plain_checkout(tmp_path):
    """A git checkout whose origin/main carries no risk rules: every head classifies T0."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(
        tmp_path,
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "i",
    )
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")


def run(
    tmp_path, reads, arms, required=REQUIRED, merge=None, extra=(), env_extra=None, clone=True
):
    if clone and not (tmp_path / ".git").exists():  # the arm classifies fail-closed: a clone
        plain_checkout(tmp_path)
    if merge is not None:  # a crew with a `merge` block in the checkout; the base has none
        (tmp_path / ".weside").mkdir()
        crew = {"version": 2, "roles": {}, "members": {}, "merge": merge}
        (tmp_path / ".weside" / "crew.json").write_text(json.dumps(crew))
    for name, items in (("reads", reads), ("arms", arms), ("required", required)):
        (tmp_path / f"{name}.json").write_text(json.dumps(items))
    gh = tmp_path / "bin" / "gh"
    gh.parent.mkdir(exist_ok=True)
    gh.write_text(f"#!{sys.executable}\n{FAKE}")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    env = {
        **{
            k: v for k, v in os.environ.items() if k != "WE_ROLE"
        },  # a worker's suite: no worker arm
        "PATH": f"{gh.parent}:{os.environ['PATH']}",
        "FAKE_DIR": str(tmp_path),
        "ARM_INTERVAL": "0",
        "ARM_REGISTER_TIMEOUT": "2",
        **(env_extra or {}),
    }
    res = subprocess.run(
        ["bash", str(SCRIPT), "7", "--repo", "o/r", *extra],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=30,
        check=False,
    )
    (tmp_path / "stderr.log").write_text(res.stderr)
    log = tmp_path / "calls.log"
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    merges = [c for c in calls if c[:2] == ["pr", "merge"] or "mergePullRequest" in " ".join(c)]
    assert merges == [], f"the helper merged: {merges}"
    return res.returncode, res.stdout.strip().splitlines(), calls


def arm_calls(calls):
    return [c for c in calls if any(a.startswith("query=mutation") for a in c)]


def test_a_blocked_pr_is_armed_on_the_head_it_read(tmp_path):
    code, out, calls = run(tmp_path, [{"head": NEW, "checks": PENDING}], ["ok"])
    assert (code, out) == (0, [f"armed: auto-merge on {NEW} (merge)", "pending: Claude Review"])
    (arm,) = arm_calls(calls)
    assert f"sha={NEW}" in arm and "method=MERGE" in arm


@pytest.mark.parametrize(
    ("later", "arms", "code", "line"),
    [
        # The trap: the old head was green, a push landed, no check run is registered on the new
        # head and GitHub answers "clean". Nothing registers before the timeout.
        ([], [CLEAN], 8, f"no checks on {NEW} after 2s — not armed, run again"),
        # The head's checks register and a required one runs: the arm goes through now.
        (PENDING, [CLEAN, "ok"], 0, f"armed: auto-merge on {NEW} (merge)"),
        # A required check never registered is absent, not green, even with the rest passing.
        ([check("lint")], [CLEAN, CLEAN], 8, None),
        ([check("lint"), check("Claude Review", conclusion="FAILURE")], [CLEAN], 7, None),
        (GREEN, [CLEAN], 3, None),
        # Green checks, but a required review is missing: GitHub waits for it, so it is armed.
        (
            {"checks": GREEN, "merge": "BLOCKED", "review": "REVIEW_REQUIRED"},
            [CLEAN, "ok"],
            0,
            None,
        ),
        # A red check that is not required leaves the PR UNSTABLE, which GitHub merges.
        (
            {
                "checks": [*GREEN, check("Codex", conclusion="FAILURE", required=False)],
                "merge": "UNSTABLE",
            },
            [CLEAN],
            3,
            None,
        ),
    ],
    ids=[
        "no-checks",
        "then-pending",
        "required-absent",
        "required-red",
        "all-green",
        "review-missing",
        "unstable",
    ],
)
def test_a_clean_answer_never_merges(tmp_path, later, arms, code, line):
    first = {"head": NEW, "commit": OLD, "checks": GREEN}  # the rollup still shows the old head
    last = later if isinstance(later, dict) else {"checks": later}
    reads = [first, {"head": NEW}, {"head": NEW}, {"head": NEW, **last}]
    got, out, _ = run(tmp_path, reads, arms)
    assert got == code, out
    assert not any(o.startswith("ready") for o in out) or code == 3
    if line:  # the verdict line; `armed` adds its `pending:` line after it
        assert [o for o in out if not o.startswith("pending: ")][-1] == line
    if code == 3:
        assert out == [
            f"ready: all required checks green on {NEW} — merge: gh pr merge 7 --merge --match-head-commit {NEW}"
        ]
    if code == 7:
        assert out == [f"red: Claude Review on {NEW} — not armed"]


# A green rerun of a review after a red run on the same head (a real PR: red 21:41Z, green
# 22:15Z). Each name is judged by its newest run, whatever order GitHub lists them in.
RERUN_GREEN = [
    check("lint"),
    check("Claude Review", conclusion="FAILURE", started="2026-11-27T21:41:00Z"),
    check("Claude Review", started="2026-11-27T22:15:00Z"),
]


@pytest.mark.parametrize("order", [1, -1], ids=["red-listed-first", "green-listed-first"])
def test_a_green_rerun_replaces_an_older_red_run(tmp_path, order):
    checks = [RERUN_GREEN[0], *RERUN_GREEN[1:][::order]]
    code, out, _ = run(tmp_path, [{"head": NEW, "checks": checks}], [CLEAN])
    assert code == 3, out
    assert out[0].startswith(f"ready: all required checks green on {NEW}")


@pytest.mark.parametrize(
    "checks",
    [
        [check("lint"), check("Claude Review", conclusion="FAILURE")],
        # A red rerun after a green run on the same head: the newest run decides.
        [
            check("lint"),
            check("Claude Review", started="2026-11-27T21:41:00Z"),
            check("Claude Review", conclusion="FAILURE", started="2026-11-27T22:15:00Z"),
        ],
    ],
    ids=["red", "red-rerun"],
)
def test_a_red_required_check_is_never_armed(tmp_path, checks):
    # The PR is BLOCKED by its red review, so GitHub would accept the arm: the helper must not ask.
    code, out, calls = run(tmp_path, [{"head": NEW, "checks": checks, "merge": "BLOCKED"}], ["ok"])
    assert (code, out) == (7, [f"red: Claude Review on {NEW} — not armed"])
    assert arm_calls(calls) == []


@pytest.mark.parametrize(
    ("reads", "arms", "code", "line"),
    [
        (
            [{"head": NEW}, {"head": "c" * 40}],
            [MOVED],
            5,
            f"refused: head moved {NEW} -> {'c' * 40}",
        ),
        (
            [{"head": NEW}, {"head": "c" * 40}],
            [CLEAN],
            5,
            f"refused: head moved {NEW} -> {'c' * 40}",
        ),
        ([{"head": NEW, "draft": True}], ["ok"], 4, "refused: draft"),
    ],
    ids=["moved-on-arm", "moved-while-waiting", "draft"],
)
def test_refusals_never_arm(tmp_path, reads, arms, code, line):
    got, out, calls = run(tmp_path, reads, arms)
    assert (got, out[-1]) == (code, line)
    if code == 4:
        assert arm_calls(calls) == []


@pytest.mark.parametrize(
    "merge, labels, code, line",
    [
        (
            {"hold_labels": ["review"]},
            ["review"],
            4,
            "refused: label review — only the human merges it",
        ),
        (
            {"hold_labels": ["review"]},
            ["docs", "review"],
            4,
            "refused: label review — only the human merges it",
        ),
        ({"armer": "workflow"}, [], 4, "refused: armed by workflow — the step is gh pr ready"),
    ],
    ids=["hold-label", "hold-label-among-others", "workflow-armer"],
)
def test_crew_merge_block_refuses_before_any_arm(tmp_path, merge, labels, code, line):
    got, out, calls = run(
        tmp_path, [{"head": NEW, "checks": PENDING, "labels": labels}], ["ok"], merge=merge
    )
    assert (got, out[-1]) == (code, line)
    assert arm_calls(calls) == []


def test_a_label_outside_hold_labels_still_arms(tmp_path):
    reads = [{"head": NEW, "checks": PENDING, "labels": ["docs"]}]
    code, out, calls = run(tmp_path, reads, ["ok"], merge={"hold_labels": ["review"]})
    assert (code, out[0]) == (0, f"armed: auto-merge on {NEW} (merge)")
    assert len(arm_calls(calls)) == 1


def test_a_broken_crew_merge_block_is_a_crew_error_not_a_gh_failure(tmp_path):
    code, out, calls = run(
        tmp_path, [{"head": NEW, "checks": PENDING}], ["ok"], merge={"armer": "Workflow"}
    )
    assert code == 2 and out[-1].startswith("crew: ") and "merge.armer must be one of" in out[-1]
    assert arm_calls(calls) == []


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def base_crew(tmp_path, base_merge, head_merge):
    """A git checkout whose origin/main holds a crew with `base_merge` (None: no crew file) and
    whose working tree, the PR's own, holds a crew with `head_merge`."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    crew_file = tmp_path / ".weside" / "crew.json"
    crew_file.parent.mkdir()
    if base_merge is not None:
        crew_file.write_text(
            json.dumps({"version": 2, "roles": {}, "members": {}, "merge": base_merge})
        )
        _git(tmp_path, "add", ".weside")
    else:
        (tmp_path / "README").write_text("x")
        _git(tmp_path, "add", "README")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    crew_file.write_text(
        json.dumps({"version": 2, "roles": {}, "members": {}, "merge": head_merge})
    )


def test_a_pr_cannot_drop_the_hold_label_its_base_holds_it_with(tmp_path):
    base_crew(tmp_path, {"hold_labels": ["review"]}, {"hold_labels": []})
    reads = [{"head": NEW, "checks": PENDING, "labels": ["review"]}]
    code, out, calls = run(tmp_path, reads, ["ok"])
    assert (code, out[-1]) == (4, "refused: label review — only the human merges it")
    assert arm_calls(calls) == []


def test_a_base_without_a_crew_file_leaves_the_checkouts_block(tmp_path):
    base_crew(tmp_path, None, {"hold_labels": ["review"]})
    reads = [{"head": NEW, "checks": PENDING, "labels": ["review"]}]
    code, out, calls = run(tmp_path, reads, ["ok"])
    assert (code, out[-1]) == (4, "refused: label review — only the human merges it")
    assert arm_calls(calls) == []


def test_an_unreadable_base_is_a_crew_error_not_the_checkouts_block(tmp_path):
    base_crew(tmp_path, {"hold_labels": ["review"]}, {"hold_labels": []})
    _git(tmp_path, "update-ref", "-d", "refs/remotes/origin/main")
    reads = [{"head": NEW, "checks": PENDING, "labels": ["review"]}]
    code, out, calls = run(tmp_path, reads, ["ok"])
    assert (code, out[-1]) == (2, "crew: origin/main unreadable here (fetch it)")
    assert arm_calls(calls) == []


def checkout(tmp_path):
    """A git checkout whose HEAD is the PR head `--check` classifies (no risk-paths: no class)."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(
        tmp_path,
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "i",
    )
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.mark.parametrize(
    ("read", "code", "line"),
    [
        (
            {"checks": GREEN},
            0,
            "ready: all required checks green on {sha} — merge: gh pr merge 7 --merge --match-head-commit {sha}",
        ),
        ({"checks": PENDING}, 8, "pending: Claude Review on {sha} — not ready"),
        ({"checks": [check("lint")]}, 8, "pending: Claude Review on {sha} — not ready"),
        ({"checks": []}, 8, "no checks on {sha} — not ready"),
        (
            {"checks": GREEN, "merge": "BLOCKED", "review": "REVIEW_REQUIRED"},
            8,
            "not ready on {sha} (BLOCKED, review REVIEW_REQUIRED)",
        ),
        (
            {"checks": GREEN, "review": "CHANGES_REQUESTED"},
            8,
            "not ready on {sha} (CLEAN, review CHANGES_REQUESTED)",
        ),
        (
            {"checks": [check("lint"), check("Claude Review", conclusion="FAILURE")]},
            7,
            "red: Claude Review on {sha} — not ready",
        ),
    ],
    ids=[
        "ready",
        "pending",
        "required-absent",
        "no-checks",
        "review-required",
        "changes-requested",
        "red",
    ],
)
def test_check_reads_once_and_never_arms(tmp_path, read, code, line):
    sha = checkout(tmp_path)
    got, out, calls = run(
        tmp_path, [{"head": sha, **read}], ["ok"], extra=("--check", "--sha", sha)
    )
    assert (got, out) == (code, [line.replace("{sha}", sha)])
    assert arm_calls(calls) == []


NOTICE = "A new preview command is available: gh event listen\nHide this notice: gh config set notices false"


def test_notices_on_stderr_never_become_the_answer(tmp_path):
    sha = checkout(tmp_path)
    code, out, _ = run(
        tmp_path,
        [{"head": sha, "checks": GREEN}],
        ["ok"],
        extra=("--check", "--sha", sha),
        env_extra={"GH_NOTICE": NOTICE},
    )
    assert (code, out) == (
        0,
        [
            f"ready: all required checks green on {sha} — merge: gh pr merge 7 --merge --match-head-commit {sha}"
        ],
    )


def test_notices_on_stderr_still_arm(tmp_path):
    code, out, _ = run(
        tmp_path, [{"head": NEW, "checks": PENDING}], ["ok"], env_extra={"GH_NOTICE": NOTICE}
    )
    assert (code, out) == (0, [f"armed: auto-merge on {NEW} (merge)", "pending: Claude Review"])


def test_a_clean_answer_is_read_from_stderr_beside_a_notice(tmp_path):
    reads = [{"head": NEW, "checks": GREEN, "merge": "UNSTABLE"}]
    code, out, _ = run(tmp_path, reads, [CLEAN], env_extra={"GH_NOTICE": NOTICE})
    assert (code, out) == (
        3,
        [
            f"ready: all required checks green on {NEW} — merge: gh pr merge 7 --merge --match-head-commit {NEW}"
        ],
    )


def test_check_refuses_another_head(tmp_path):
    sha = checkout(tmp_path)
    reads = [{"head": NEW, "checks": GREEN}]
    got, out, calls = run(tmp_path, reads, ["ok"], extra=("--check", "--sha", sha))
    assert (got, out) == (5, [f"refused: head moved {sha} -> {NEW}"])
    assert arm_calls(calls) == []


def one_way_head(tmp_path, path="we/scripts/arm_pr.sh"):
    """The plugin's risk rules on origin/main; the PR head, a commit on a side branch touching a
    brake path, is not checked out: HEAD stays origin/main."""
    risk_checkout(tmp_path)
    _git(tmp_path, "checkout", "-q", "-b", "pr")
    (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / path).write_text("x\n")
    _git(tmp_path, "add", path)
    _git(tmp_path, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "brake")
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    _git(tmp_path, "checkout", "-q", "main")
    return sha


def comment_calls(calls):
    return [c for c in calls if c[:2] == ["pr", "comment"]]


LOUD = "one-way brake-change: merges only after the human's yes on the board (L0)"


def one_way_said(sha, how="armed"):
    return [
        "pr",
        "comment",
        "7",
        "--repo",
        "o/r",
        "--body",
        f"one-way brake-change {how} — merges only after the human's yes on the board (head {sha})",
    ]


def test_a_one_way_head_from_another_checkout_is_armed_and_said_loudly(tmp_path):
    """Red arm: a one-way class refused the arm until a go number the board had to hold; the
    human's yes on the board is the brake now, and the helper names the class on stdout and the PR."""
    sha = one_way_head(tmp_path)
    got, out, calls = run(tmp_path, [{"head": sha, "checks": PENDING}], ["ok"])
    assert (got, out) == (
        0,
        [LOUD, f"armed: auto-merge on {sha} (merge)", "pending: Claude Review"],
    )
    assert len(arm_calls(calls)) == 1
    assert comment_calls(calls) == [one_way_said(sha)]


def test_a_ready_one_way_pr_is_said_on_the_pr_too(tmp_path):
    sha = one_way_head(tmp_path)
    got, out, calls = run(tmp_path, [{"head": sha, "checks": GREEN}], [CLEAN])
    assert (got, out) == (
        3,
        [
            LOUD,
            f"ready: all required checks green on {sha} — merge: gh pr merge 7 --merge --match-head-commit {sha}",
        ],
    )
    assert comment_calls(calls) == [one_way_said(sha, "ready for the printed merge")]


@pytest.mark.parametrize(
    ("checks", "arms", "code", "how"),
    [(PENDING, ["ok"], 0, "armed"), (GREEN, [CLEAN], 3, "ready for the printed merge")],
    ids=["armed", "ready"],
)
def test_a_failed_one_way_comment_leaves_the_verdict(tmp_path, checks, arms, code, how):
    """The comment is a reminder, not a step of the arm: a failed post is one stderr line, and the
    verdict and its exit code stay what they were."""
    sha = one_way_head(tmp_path)
    got, out, calls = run(
        tmp_path, [{"head": sha, "checks": checks}], arms, env_extra={"FAKE_COMMENT_FAILS": "1"}
    )
    assert got == code and out[0] == LOUD, out
    assert out[1].startswith("armed: " if code == 0 else "ready: "), out
    assert comment_calls(calls) == [one_way_said(sha, how)]
    err = (tmp_path / "stderr.log").read_text().splitlines()
    assert err == ["one-way comment failed: HTTP 502: comment failed"], err


def test_the_one_way_comment_comes_once_per_head(tmp_path):
    """Red arm: a second arm on the same head commented again; another head's comment does not count."""
    sha = one_way_head(tmp_path)
    other = one_way_said(OLD)[-1]
    (tmp_path / "comments.json").write_text(json.dumps([other]))
    for _ in range(2):
        got, out, _calls = run(tmp_path, [{"head": sha, "checks": PENDING}], ["ok"])
        assert (got, out[0]) == (0, LOUD), out
    calls = [json.loads(x) for x in (tmp_path / "calls.log").read_text().splitlines()]
    assert comment_calls(calls) == [one_way_said(sha)]


def test_check_says_a_one_way_class_and_refuses_nothing_for_it(tmp_path):
    """Red arm: `--check` refused every one-way head, so it never answered `ready` for one."""
    sha = one_way_head(tmp_path)
    got, out, calls = run(
        tmp_path, [{"head": sha, "checks": GREEN}], ["ok"], extra=("--check", "--sha", sha)
    )
    assert (got, out) == (
        0,
        [
            LOUD,
            f"ready: all required checks green on {sha} — merge: gh pr merge 7 --merge --match-head-commit {sha}",
        ],
    )
    assert arm_calls(calls) == [] and comment_calls(calls) == []


@pytest.mark.parametrize("extra", [(), ("--check",)], ids=["arm", "check"])
def test_a_worker_never_arms_a_one_way_class(tmp_path, extra):
    """Red arm: a worker's refusal pointed it at a go number, a way the worker rights gate denies anyway."""
    sha = one_way_head(tmp_path)
    got, out, calls = run(
        tmp_path,
        [{"head": sha, "checks": GREEN}],
        ["ok"],
        extra=extra,
        env_extra={"WE_ROLE": "worker"},
    )
    assert (got, out) == (
        6,
        ["refused: one-way brake-change — the session that asked the human arms it"],
    )
    assert arm_calls(calls) == [] and comment_calls(calls) == []


def test_a_worker_still_arms_a_two_way_pr(tmp_path):
    code, out, _calls = run(
        tmp_path, [{"head": NEW, "checks": PENDING}], ["ok"], env_extra={"WE_ROLE": "worker"}
    )
    assert (code, out[0]) == (0, f"armed: auto-merge on {NEW} (merge)")


def test_a_two_way_head_from_another_checkout_still_arms(tmp_path):
    sha = one_way_head(tmp_path, "docs/notes.md")
    code, out, calls = run(tmp_path, [{"head": sha, "checks": PENDING}], ["ok"])
    assert (code, out[0]) == (0, f"armed: auto-merge on {sha} (merge)")
    assert len(arm_calls(calls)) == 1 and comment_calls(calls) == []


def test_a_head_missing_from_the_clone_is_not_classified(tmp_path):
    risk_checkout(tmp_path)
    got, out, calls = run(tmp_path, [{"head": NEW, "checks": PENDING}], ["ok"])
    assert (got, out) == (
        6,
        [f"refused: one-way not classified (head {NEW[:12]} not here (fetch it))"],
    )
    assert arm_calls(calls) == []


def pr_head_on_origin(tmp_path):
    """`work`, a clone whose origin (a bare repo) holds the one-way PR head only as
    `refs/pull/7/head`: the arm has to fetch it. Returns (work, sha)."""
    src, origin, work = tmp_path / "src", tmp_path / "origin.git", tmp_path / "work"
    src.mkdir()
    work.mkdir()
    sha = one_way_head(src)
    _git(tmp_path, "clone", "-q", "--bare", str(src), str(origin))
    _git(origin, "update-ref", "refs/pull/7/head", sha)
    _git(origin, "update-ref", "-d", "refs/heads/pr")
    _git(work, "init", "-q", "-b", "main")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "fetch", "-q", "origin", "main:refs/remotes/origin/main")
    _git(work, "checkout", "-q", "--detach", "origin/main")
    return work, sha


def test_the_fetched_pr_head_ref_is_dropped_after_the_class(tmp_path):
    """Red arm: every arm from another checkout left `refs/we-arm/pr-<N>` behind."""
    work, sha = pr_head_on_origin(tmp_path)
    got, out, _calls = run(work, [{"head": sha, "checks": PENDING}], ["ok"])
    assert (got, out[0]) == (0, LOUD), out  # classified on the fetched head, so the fetch happened
    left = subprocess.run(
        ["git", "for-each-ref", "refs/we-arm/"],
        cwd=work,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert left == ""


def test_outside_a_git_clone_it_refuses(tmp_path):
    """No clone, no class: the arm refuses instead of arming unclassified."""
    got, out, calls = run(
        tmp_path,
        [{"head": NEW, "checks": PENDING}],
        ["ok"],
        clone=False,
        env_extra={"GIT_CEILING_DIRECTORIES": str(tmp_path.parent)},
    )
    assert (got, out) == (6, ["refused: one-way not classified (not a git checkout)"])
    assert arm_calls(calls) == [] and comment_calls(calls) == []


def real_crew_checkout(tmp_path):
    """A checkout whose origin/main holds a crew file the way a real repo carries one: a `merge`
    block next to `files.*` paths that exist beside it. The base's crew is read at a revision
    (`crew.py merge --rev`), so its paths have no working tree to be checked against."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "goals.md").write_text("# Goals\n")
    (tmp_path / "docs" / "dod.md").write_text("# Done\n")
    (tmp_path / ".weside").mkdir()
    crew = {
        "version": 2,
        "roles": {},
        "members": {},
        "files": {"goals": "docs/goals.md", "dod": "docs/dod.md"},
        "merge": {"armer": "session", "hold_labels": ["hold-me"]},
    }
    (tmp_path / ".weside" / "crew.json").write_text(json.dumps(crew))
    (tmp_path / ".weside" / "risk-paths").write_text("# no one-way section: every diff is T0\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.mark.parametrize(
    ("labels", "code", "line"),
    [
        (
            [],
            0,
            "ready: all required checks green on {sha} — merge: gh pr merge 7 --merge --match-head-commit {sha}",
        ),
        (["hold-me"], 4, "refused: label hold-me — only the human merges it"),
    ],
    ids=["ready", "held-by-the-base-crew"],
)
def test_the_merge_tools_load_a_real_crew_file_at_a_revision(tmp_path, labels, code, line):
    """CI dry run of the merge tools on a crew with `files.*`: red on a crew read at a revision
    whose paths are checked against the temp dir it was written to (every arm then ended in
    `crew: … files.goals … does not exist`)."""
    sha = real_crew_checkout(tmp_path)
    crew = [sys.executable, str(HERE / "crew.py"), "merge"]
    for field, want in (("armer", "session"), ("hold_labels", "hold-me")):
        got = subprocess.run(
            [*crew, field, "--rev", sha], cwd=tmp_path, capture_output=True, text=True, check=False
        )
        assert (got.returncode, got.stdout.strip()) == (0, want), got.stderr
    reads = [{"head": sha, "checks": GREEN, "labels": labels}]
    got, out, calls = run(tmp_path, reads, ["ok"], extra=("--check", "--sha", sha))
    assert (got, out) == (code, [line.replace("{sha}", sha)])
    assert arm_calls(calls) == []


RISK_RULES = HERE.parents[1] / ".weside" / "risk-paths"


def risk_checkout(tmp_path):
    """A checkout whose origin/main carries the plugin's own risk rules; HEAD is origin/main."""
    (tmp_path / ".weside").mkdir()
    shutil.copy(RISK_RULES, tmp_path / ".weside" / "risk-paths")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", ".weside/risk-paths")
    _git(tmp_path, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "rules")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.mark.parametrize("extra", [(), ("--check",)], ids=["arm", "check"])
def test_an_uncommitted_risk_path_is_refused_not_armed(tmp_path, extra):
    sha = risk_checkout(tmp_path)
    stray = tmp_path / "we" / "process" / "zz-untracked.md"  # a brake path, untracked
    stray.parent.mkdir(parents=True)
    stray.write_text("x\n")
    got, out, calls = run(tmp_path, [{"head": sha, "checks": GREEN}], ["ok"], extra=extra)
    assert got == 6
    assert out == [
        "refused: one-way not classified (risk_paths.py exit 3: T? uncommitted changes under we/process/zz-untracked.md: commit first)"
    ]
    assert arm_calls(calls) == []


# A core-like crew: `risk.command` names the repo's own classifier, and `.weside/risk-paths` uses
# grammar only that classifier reads (`rules removed …`, `line …`), which risk_paths.py rejects.
CORE_RULES = """[brake-change]
path scripts/dev/risk-class.sh
rules removed brake-change,money,destructive-migration,terraform-secrets
line any .weside/risk-paths (^|\\n)[[:space:]]*\\[
"""


def command_crew(tmp_path, classifier, crew_risk=None):
    """A checkout whose origin/main (= HEAD) carries a crew naming `scripts/classify.sh` (body
    `classifier`) as `risk.command`, beside core-grammar risk rules."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / ".weside").mkdir()
    risk = {"command": "scripts/classify.sh"} if crew_risk is None else crew_risk
    crew = {"version": 2, "roles": {}, "members": {}, "risk": risk}
    (tmp_path / ".weside" / "crew.json").write_text(json.dumps(crew))
    (tmp_path / ".weside" / "risk-paths").write_text(CORE_RULES)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "classify.sh").write_text("#!/usr/bin/env bash\n" + classifier)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_the_plugin_classifier_rejects_core_grammar(tmp_path):
    """The reason the arm reads `risk.command`: risk_paths.py is a subset and exits 2 on core's rules."""
    command_crew(tmp_path, "echo T0\n")
    got = subprocess.run(
        [sys.executable, str(HERE / "risk_paths.py"), "origin/main"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert got.returncode == 2 and "not a rule: rules removed" in got.stderr


@pytest.mark.parametrize("extra", [(), ("--check",)], ids=["arm", "check"])
@pytest.mark.parametrize(
    ("classifier", "code", "line"),
    [
        ('[ "$1" = origin/main ] || exit 2\nprintf "T0\\nreview: standard\\n"\n', None, None),
        ('printf "T2\\nreview: high\\n"\n', None, None),
        ('printf "T2 one-way brake-change\\nreview: high\\n"\n', None, LOUD),
        (
            'echo "risk-class: rules parse error" >&2; exit 2\n',
            6,
            "refused: one-way not classified (scripts/classify.sh exit 2: risk-class: rules parse error)",
        ),
        (
            "echo banana\n",
            6,
            "refused: one-way not classified (scripts/classify.sh line 1: banana)",
        ),
        (
            "exit 0\n",
            6,
            "refused: one-way not classified (scripts/classify.sh line 1: empty)",
        ),
    ],
    ids=["T0", "T2", "one-way", "exit-2", "garbage", "silent"],
)
def test_the_arm_runs_the_crews_risk_command(tmp_path, extra, classifier, code, line):
    sha = command_crew(tmp_path, classifier)
    got, out, calls = run(tmp_path, [{"head": sha, "checks": PENDING}], ["ok"], extra=extra)
    if code is None:  # classified: the arm goes on to the checks, a one-way class said first
        said = [line] if line else []
        if extra:
            assert (got, out) == (8, [*said, f"pending: Claude Review on {sha} — not ready"])
        else:
            assert (got, out[: len(said) + 1]) == (
                0,
                [*said, f"armed: auto-merge on {sha} (merge)"],
            )
        return
    assert (got, out) == (code, [line])
    assert arm_calls(calls) == []


def test_a_base_without_any_risk_rules_is_not_classified(tmp_path):
    """No `.weside/risk-paths` and no `risk.command` on the base: T0, as before the crew's command
    was read (a repo whose default branch is not main has no origin/main either)."""
    command_crew(tmp_path, "echo T0\n", crew_risk={})
    _git(tmp_path, "rm", "-q", ".weside/risk-paths")
    _git(tmp_path, "commit", "-q", "-m", "no rules")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    got, out, _calls = run(
        tmp_path, [{"head": sha, "checks": PENDING}], ["ok"], extra=("--check",)
    )
    assert (got, out) == (8, [f"pending: Claude Review on {sha} — not ready"])


def test_a_missing_base_ref_is_no_class(tmp_path):
    """`origin/<base>` absent: the classifier cannot tell whether the base sets rules, so it
    refuses (exit 2) instead of printing T0."""
    command_crew(tmp_path, "echo T0\n")
    got = subprocess.run(
        [sys.executable, str(HERE / "risk_runner.py"), "here", "origin/gone"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (got.returncode, got.stdout.strip()) == (2, "no origin/gone here (fetch it)")
