#!/usr/bin/env python3
"""PreToolUse hook: no `gh pr ready` while the default branch is red.

A PR made ready while the default branch fails a gate (two PRs that merged past each other) runs its
full lanes and fails on code it does not touch; a crew's builders held `gh pr ready` until the fix
landed, then merged the default branch once, pushed once and went green on the first run. Contract:
`skills/pr/SKILL.md` step 4.

  * Opt-in per repo: `.weside/config.json` `ci.hold_ready_on_red_main` is `true` (every workflow
    that runs on a push to the default branch) or a list of workflow names (only those). Absent,
    `false` or unreadable: the hook does nothing.
  * Fires on `gh pr ready` without `--undo`, in command position (`gh pr ready --undo` is
    `draft_reason_gate.py`'s).
  * Red: per workflow, the newest completed push run on the default branch that was not cancelled
    or skipped concluded `failure`, `timed_out` or `startup_failure`. A run still in progress does
    not count, the run before it does.
  * Override: one line `**Ready on red main:** <reason>` in the PR body (outside fenced code, no
    `<placeholder>`), e.g. for the PR that fixes the default branch.
  * `git push` is never held: the fix itself reaches the default branch by a push, a push saves
    work off the machine, and the push alone does not tell which branch carries the fix.
  * Fail-open when the config, the default branch, the runs or the body cannot be read, and on
    every other error.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verification_gate as vg

_OVERRIDE = re.compile(r"^\s*\*\*Ready on red main:\*\*[ \t]*\S", re.MULTILINE)
_PLACEHOLDER = re.compile(r"<[^<>\n]+>")
_FENCE = re.compile(r"^\s{0,3}(```|~~~).*?^\s{0,3}\1", re.MULTILINE | re.DOTALL)
_REPO_FLAGS = ("-R", "--repo")
_RED = ("failure", "timed_out", "startup_failure")
_PASSED_OVER = ("cancelled", "skipped", "neutral", "stale", "")


def _ready(argv: list[str]) -> tuple[int, str | None, str | None] | None:
    """(index of `gh`, PR selector, repo) for a `gh pr ready` without `--undo` in command position."""
    for i, tok in enumerate(argv):
        bare = tok.lstrip("({$")
        if bare != "gh" and not bare.endswith("/gh"):
            continue
        if tok == bare and not vg._starts_a_command(argv, i):
            continue
        repo, j = None, i + 1
        while j < len(argv) and argv[j].startswith("-"):
            if argv[j] in _REPO_FLAGS and j + 1 < len(argv):
                repo, j = argv[j + 1], j + 2
                continue
            if argv[j].startswith("--repo="):
                repo = argv[j].split("=", 1)[1]
            j += 1
        if [a.rstrip(";&|") for a in argv[j : j + 2]] != ["pr", "ready"]:
            continue
        args = [a.rstrip(";&|") for a in vg._args_from(argv, j + 2)]
        if "--undo" in args:
            continue
        selector, k = None, 0
        while k < len(args):
            if args[k] in _REPO_FLAGS and k + 1 < len(args):
                repo, k = args[k + 1], k + 2
                continue
            if args[k].startswith("--repo="):
                repo = args[k].split("=", 1)[1]
            elif args[k] and not args[k].startswith("-") and selector is None:
                selector = args[k]
            k += 1
        return i, selector, repo
    return None


def _armed(root: str | None) -> bool | list[str]:
    """`True`, a list of workflow names, or `False` when the repo has not opted in."""
    if not root:
        return False
    try:
        with open(os.path.join(root, ".weside", "config.json")) as fh:
            value = (json.load(fh).get("ci") or {}).get("hold_ready_on_red_main")
    except Exception:
        return False
    if value is True:
        return True
    if isinstance(value, list):
        names = [n for n in value if isinstance(n, str) and n.strip()]
        return names or False
    return False


def _gh(args: list[str], cwd: str | None) -> str | None:
    try:
        out = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=20, check=False, cwd=cwd or None
        )
    except Exception:
        return None
    return out.stdout if out.returncode == 0 else None


def _red_workflows(
    repo: str | None, cwd: str | None, only: bool | list[str]
) -> tuple[str, list[str]]:
    """(default branch, `name (sha)` of each red workflow); an unreadable answer is not red."""
    on_repo = ["-R", repo] if repo else []
    branch = _gh(
        [
            "repo",
            "view",
            *([repo] if repo else []),
            "--json",
            "defaultBranchRef",
            "-q",
            ".defaultBranchRef.name",
        ],
        cwd,
    )
    branch = (branch or "").strip()
    if not branch:
        return "", []
    raw = _gh(
        [
            "run",
            "list",
            *on_repo,
            "-b",
            branch,
            "-e",
            "push",
            "-L",
            "50",
            "--json",
            "workflowName,status,conclusion,headSha,createdAt",
        ],
        cwd,
    )
    try:
        runs = json.loads(raw or "")
    except Exception:
        return branch, []
    runs = sorted(runs, key=lambda r: r.get("createdAt") or "", reverse=True)
    newest: dict[str, dict] = {}
    for run in runs:
        name = run.get("workflowName") or ""
        if name in newest or (only is not True and name not in only):
            continue
        if run.get("status") != "completed" or (run.get("conclusion") or "") in _PASSED_OVER:
            continue
        newest[name] = run
    red = [
        f"{name} ({(run.get('headSha') or '')[:8]})"
        for name, run in newest.items()
        if run.get("conclusion") in _RED
    ]
    return branch, sorted(red)


def _overridden(body: str | None) -> bool:
    """True when the body carries a filled-in override line, or cannot be read (fail open)."""
    if body is None:
        return True
    unfenced = _FENCE.sub("", body)
    for match in _OVERRIDE.finditer(unfenced):
        line = unfenced[match.start() :].split("\n", 1)[0]
        if not _PLACEHOLDER.search(line):
            return True
    return False


def _body(selector: str | None, repo: str | None, cwd: str | None) -> str | None:
    view = ["pr", "view", *([selector] if selector else []), *(["-R", repo] if repo else [])]
    raw = _gh([*view, "--json", "body"], cwd)
    try:
        return json.loads(raw or "")["body"]
    except Exception:
        return None


def refusal(payload: dict) -> str | None:
    if payload.get("tool_name") != "Bash":
        return None
    command = (payload.get("tool_input") or {}).get("command", "")
    if "gh" not in command or "ready" not in command:
        return None
    argv = vg._argv_or_none(command)
    found = _ready(argv)
    if found is None:
        return None
    at, selector, repo = found
    cwd = vg._cwd_after_cd(argv, payload.get("cwd"), stop=at)
    only = _armed(vg._repo_root(cwd))
    if only is False:
        return None
    branch, red = _red_workflows(repo, cwd, only)
    if not red or _overridden(_body(selector, repo, cwd)):
        return None
    return (
        f"`gh pr ready` holds: `{branch}` is red on {', '.join(red)}, so this PR's full lanes would "
        f"fail on code it does not touch. Wait until the fix is on `{branch}` (its producer names "
        f"the PR), then merge `origin/{branch}` once, push once and run `gh pr ready` again. "
        f"This PR is the fix, or it must go ready anyway: add one line "
        f"`**Ready on red main:** <reason>` to the PR body "
        f"(`gh pr edit {selector or '<PR>'} --body-file <file>`), then retry."
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    try:
        reason = refusal(payload)
    except Exception as exc:  # fail open: a gate that guesses wrong is worse than none
        print(f"main_red_gate: skipped ({type(exc).__name__}: {exc})", file=sys.stderr)
        return
    if reason is None:
        return
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


if __name__ == "__main__":
    main()
