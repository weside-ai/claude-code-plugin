"""watch-pr-conflicts.sh against a stub `gh` that replays one answer per PR and call."""

import json
import os
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent / "watch-pr-conflicts.sh"


def run(tmp_path, answers, *prs, lifetime="60"):
    """answers: {pr: [ {state, mergeStateStatus, mergeable, baseRefName} …]}, last one repeats."""
    for pr, seq in answers.items():
        q = tmp_path / f"q{pr}"
        q.mkdir()
        for i, a in enumerate(seq):
            (q / f"{i}.json").write_text(json.dumps({"baseRefName": "main", **a}))
    gh = tmp_path / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$(pwd) | $1 $2 $3 $4 $5" >> "{tmp_path}/calls.log"\n'
        'if [ "$1 $2" = "repo view" ]; then echo o/r; exit 0; fi\n'
        f'q="{tmp_path}/q$3"; n=$(cat "$q/count" 2>/dev/null || echo 0); echo $((n+1)) > "$q/count"\n'
        'f="$q/$n.json"; [ -f "$f" ] || f=$(ls "$q"/*.json | sort -V | tail -n 1)\n'
        'while [ $# -gt 0 ]; do [ "$1" = --jq ] && j=$2; shift; done; jq -r "$j" "$f"\n'
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    env = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "WATCH_INTERVAL": "0",
        "WATCH_MAX_LIFETIME": lifetime,
    }
    env.pop("WATCH_REPO", None)
    res = subprocess.run(
        ["bash", str(SCRIPT), *prs],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=30,
        check=False,
    )
    return res.returncode, res.stdout.splitlines()


OPEN_CLEAN = {"state": "OPEN", "mergeStateStatus": "CLEAN", "mergeable": "MERGEABLE"}


def test_first_pr_going_dirty_wakes_the_owner(tmp_path):
    dirty = {"state": "OPEN", "mergeStateStatus": "DIRTY", "mergeable": "CONFLICTING"}
    code, out = run(tmp_path, {"5": [OPEN_CLEAN], "6": [OPEN_CLEAN, OPEN_CLEAN, dirty]}, "5", "6")
    assert (code, out) == (
        1,
        ["6 DIRTY/CONFLICTING — merge origin/main, run the after-merge check, push"],
    )
    calls = (tmp_path / "calls.log").read_text().splitlines()
    assert all(c.startswith("/ | pr view ") for c in calls[1:])


def test_behind_counts_and_unknown_waits(tmp_path):
    unknown = {"state": "OPEN", "mergeStateStatus": "UNKNOWN", "mergeable": "UNKNOWN"}
    behind = {"state": "OPEN", "mergeStateStatus": "BEHIND", "mergeable": "MERGEABLE"}
    code, out = run(tmp_path, {"5": [unknown, unknown, behind]}, "5")
    assert (code, out) == (
        1,
        ["5 BEHIND/MERGEABLE — merge origin/main, run the after-merge check, push"],
    )


def test_merged_prs_leave_the_set_and_the_last_one_ends_it(tmp_path):
    merged = {"state": "MERGED", "mergeStateStatus": "UNKNOWN", "mergeable": "UNKNOWN"}
    closed = {"state": "CLOSED", "mergeStateStatus": "UNKNOWN", "mergeable": "UNKNOWN"}
    code, out = run(tmp_path, {"5": [merged], "6": [OPEN_CLEAN, closed]}, "5", "6")
    assert (code, out) == (7, ["all merged or closed: 5 6"])


def test_lifetime_cap(tmp_path):
    code, out = run(tmp_path, {"5": [OPEN_CLEAN]}, "5", lifetime="1")
    assert (code, out) == (9, ["gave up after 1s"])
