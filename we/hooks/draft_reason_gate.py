#!/usr/bin/env python3
"""PreToolUse hook: a PR becomes a draft only with a `**Draft:**` line in its body, and leaves
draft only when it does not conflict with its base.

A draft is for a PR that must not merge even when green; a fix round needs none, because a red
required check already blocks the merge and the Codex review skips drafts. Observed before the
owner's decision of 30.10.2026: one PR drafted five times during fix rounds, four drafts with no
reason in the body. Contract: `skills/pr/SKILL.md` step 4.

  * Fires on `gh pr create` with `--draft`/`-d` and on `gh pr ready --undo`, in command position
    (heredoc bodies lifted out first, as in `verification_gate.py`).
  * `create`: the body comes from `--body`/`-b` or `--body-file`/`-F` (a heredoc written in the
    same command counts). No body flag at all is a body without the line: denied.
  * `ready --undo`: the body comes from `gh pr view <selector> --json body`.
  * Passes when the body's first non-empty line starts with `**Draft:**` followed by a reason, and
    that line holds no `<placeholder>` (neither in the reason nor in the condition).
  * Fail-open when the body cannot be read (a substitution, `-`, `--web`, a missing file, a `gh`
    error) and on every other error.
  * `ready` (without `--undo`): denied while `gh pr view <selector> --json mergeable` says
    CONFLICTING. GitHub starts no `pull_request` workflow for a PR whose merge ref cannot be built,
    so a ready event on a conflicting PR starts no CI and no arming workflow, and a crew's board
    showed such a PR green and unarmed after the conflict was gone. UNKNOWN is read again up to
    READY_READS times; still UNKNOWN or unreadable passes.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verification_gate as vg

_DRAFT_LINE = re.compile(r"\s*\*\*Draft:\*\*[ \t]*\S")
_PLACEHOLDER = re.compile(r"<[^<>\n]+>")
_REPO_FLAGS = ("-R", "--repo")
READY_READS = 3  # GitHub computes `mergeable` lazily: UNKNOWN right after a push
READY_WAIT_S = 3.0
READY_VIEW_S = 12  # READY_READS reads and their waits stay inside the hook's 45-s timeout


def _ready(argv: list[str]) -> tuple[int, str | None, str | None, bool] | None:
    """(index of `gh`, PR selector, repo, `--undo` given) for a `gh pr ready` in command position."""
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
        if argv[j : j + 2] != ["pr", "ready"]:
            continue
        args = [a.rstrip(";&|") for a in vg._args_from(argv, j + 2)]
        selector, k = None, 0
        while k < len(args):
            if args[k] in _REPO_FLAGS and k + 1 < len(args):
                repo, k = args[k + 1], k + 2
                continue
            if args[k].startswith("--repo="):
                repo = args[k].split("=", 1)[1]
            elif not args[k].startswith("-") and selector is None:
                selector = args[k]
            k += 1
        return i, selector, repo, "--undo" in args
    return None


def _pr_view(
    selector: str | None, repo: str | None, cwd: str | None, fields: str, timeout: float = 20
) -> dict | None:
    view = ["gh", "pr", "view", *([selector] if selector else []), *(["-R", repo] if repo else [])]
    try:
        out = subprocess.run(
            [*view, "--json", fields],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=cwd or None,
        )
        data = json.loads(out.stdout) if out.returncode == 0 else None
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _pr_body(selector: str | None, repo: str | None, cwd: str | None) -> str | None:
    data = _pr_view(selector, repo, cwd, "body")
    return data.get("body") if data else None


def _conflicting(selector: str | None, repo: str | None, cwd: str | None) -> dict | None:
    """The PR's view when GitHub says CONFLICTING; None when mergeable, unknown or unreadable."""
    for attempt in range(READY_READS):
        data = _pr_view(selector, repo, cwd, "mergeable,baseRefName", READY_VIEW_S)
        state = (data or {}).get("mergeable")
        if state == "CONFLICTING":
            return data
        if state != "UNKNOWN":
            return None
        if attempt + 1 < READY_READS:
            time.sleep(READY_WAIT_S)
    return None


def _ready_refusal(selector: str | None, repo: str | None, cwd: str | None) -> str | None:
    data = _conflicting(selector, repo, cwd)
    if data is None:
        return None
    base = data.get("baseRefName") or "<base>"
    verb = f"gh pr ready {selector}" if selector else "gh pr ready"
    return (
        f"`{verb}` refused: the PR conflicts with `{base}`. GitHub starts no workflow for a conflicting "
        "PR, so this ready event would start no CI and no auto-merge arming, and nothing re-arms "
        f"it later. Merge `origin/{base}` in the PR's worktree, run the after-merge check, push "
        "once, then run `gh pr ready` again."
    )


def _denial(what: str, fix: str) -> str:
    return (
        f"{what} needs a reason: put one line `**Draft:** <reason> — ready when <condition>` at the "
        f"top of the PR body ({fix}), "
        "then retry. A draft is only for a PR that must not merge even when green (open product "
        "decision, unmerged dependency, a follow-up still landing on the branch, money path "
        "awaiting the owner). A fix round does not draft: a red required check already blocks "
        "the merge; disable auto-merge instead."
    )


def _has_reason(body: str | None) -> bool:
    """True when the body's first non-empty line is the filled-in line, or the body cannot be
    read (fail open)."""
    if body is None:
        return True
    first = next((line for line in body.splitlines() if line.strip()), "")
    return bool(_DRAFT_LINE.match(first)) and not _PLACEHOLDER.search(first)


def _create_refusal(command: str, rest: list[str], cwd: str | None) -> str | None:
    if not any(a.rstrip(";&|") in ("--draft", "-d") for a in rest) or "--web" in rest:
        return None
    _, body, seen = vg._body_of(command, cwd)
    if not seen:
        body = ""  # `--fill` or no body at all: nothing carries the line
    return (
        None
        if _has_reason(body)
        else _denial("`gh pr create --draft`", "the `--body-file` with that line first")
    )


def refusal(payload: dict) -> str | None:
    if payload.get("tool_name") != "Bash":
        return None
    command = (payload.get("tool_input") or {}).get("command", "")
    if "gh" not in command or not any(f in command for f in ("--draft", " ready", " -d")):
        return None
    argv = vg._argv_or_none(command)
    found = vg._pr_verb(argv)
    if found is not None and found[1] == "create":
        return _create_refusal(command, found[2], payload.get("cwd"))
    ready = _ready(argv)
    if ready is None:
        return None
    at, selector, repo, undo = ready
    cwd = vg._cwd_after_cd(argv, payload.get("cwd"), stop=at)
    if not undo:
        return _ready_refusal(selector, repo, cwd)
    body = _pr_body(selector, repo, cwd)
    return (
        None
        if _has_reason(body)
        else _denial(
            "`gh pr ready --undo`",
            f"`gh pr edit {selector or '<PR>'} --body-file <file>` with that line first",
        )
    )


def main() -> None:
    try:
        reason = refusal(json.load(sys.stdin))
    except Exception:
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
