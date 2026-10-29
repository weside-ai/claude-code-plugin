"""conflict_gate.py as Claude Code runs it: a subprocess with a stub `gh` and a real transcript."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "conflict_gate.py"
URL = "https://github.com/o/r/pull/7"


def _transcript(tmp: Path, url: str = URL) -> Path:
    lines = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "Bash",
                        "input": {"command": "gh pr create --title x --body-file b.md"},
                    }
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": url + "\n"}]
            },
        },
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t2",
                        "name": "Bash",
                        "input": {"command": "gh pr view 9"},
                    }
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t2",
                        "content": "https://github.com/o/r/pull/9",
                    }
                ]
            },
        },
    ]
    p = tmp / "t.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in lines))
    return p


def _run(tmp: Path, pr: dict | str, payload: dict | None = None):
    (tmp / "pr.json").write_text(pr if isinstance(pr, str) else json.dumps(pr))
    gh = tmp / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$*" >> "{tmp}/calls.log"\n'
        f'[ "$(cat "{tmp}/pr.json")" = FAIL ] && exit 1\n'
        f'cat "{tmp}/pr.json"\n'
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    env = {
        **os.environ,
        "PATH": f"{tmp}:{os.environ['PATH']}",
        "HOME": str(tmp),
        "WE_STATE_DIR": str(tmp / "state"),
    }
    body = {"session_id": "s1", "transcript_path": str(_transcript(tmp)), **(payload or {})}
    res = subprocess.run(
        ["python3", str(HOOK)],
        input=json.dumps(body),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout) if res.stdout.strip() else None


def _pr(**kw):
    return {
        "url": URL,
        "number": 7,
        "state": "OPEN",
        "mergeStateStatus": "DIRTY",
        "mergeable": "CONFLICTING",
        "headRefOid": "a" * 40,
        "autoMergeRequest": {"enabledAt": "x"},
        "body": "",
        "baseRefName": "main",
        **kw,
    }


def _unthrottle(tmp: Path):
    p = tmp / "state" / "conflict-gate" / "s1.json"
    s = json.loads(p.read_text())
    s["checked"] = 0
    p.write_text(json.dumps(s))


def test_own_dirty_pr_blocks_once_per_head(tmp_path):
    out = _run(tmp_path, _pr())
    assert out["decision"] == "block"
    assert "PR #7" in out["reason"] and "aaaaaaaaa" in out["reason"]
    # Only the `gh pr create` URL is the session's own; pull/9 came from a `gh pr view`.
    assert (tmp_path / "calls.log").read_text().splitlines() == [
        f"pr view {URL} --json url,number,state,mergeStateStatus,mergeable,headRefOid,"
        "autoMergeRequest,body,baseRefName"
    ]
    _unthrottle(tmp_path)
    assert _run(tmp_path, _pr()) is None  # same head: named already
    _unthrottle(tmp_path)
    assert _run(tmp_path, _pr(headRefOid="b" * 40))["decision"] == "block"  # new head


def test_throttle_skips_gh_between_sweeps(tmp_path):
    _run(tmp_path, _pr(mergeStateStatus="CLEAN", mergeable="MERGEABLE"))
    _run(tmp_path, _pr())
    assert len((tmp_path / "calls.log").read_text().splitlines()) == 1


def test_no_block_while_stop_hook_active(tmp_path):
    assert _run(tmp_path, _pr(), {"stop_hook_active": True}) is None


def test_user_merge_pr_without_auto_merge_is_left_alone(tmp_path):
    pr = _pr(autoMergeRequest=None, body="…\nuser merge: money path\n")
    assert _run(tmp_path, pr) is None


def test_clean_merged_and_gh_failure_let_the_stop_through(tmp_path):
    assert _run(tmp_path, _pr(mergeStateStatus="CLEAN", mergeable="MERGEABLE")) is None
    _unthrottle(tmp_path)
    assert _run(tmp_path, _pr(state="MERGED")) is None
    _unthrottle(tmp_path)
    assert _run(tmp_path, "FAIL") is None


def test_a_session_without_own_prs_calls_no_gh(tmp_path):
    t = tmp_path / "empty.jsonl"
    t.write_text("")
    assert _run(tmp_path, _pr(), {"transcript_path": str(t)}) is None
    assert not (tmp_path / "calls.log").exists()
