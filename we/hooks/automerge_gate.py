#!/usr/bin/env python3
"""PreToolUse hook: auto-merge is armed only once the Codex review on the PR's head has a verdict.

Codex is no required check, so GitHub merges past it: an arm before its verdict merges the
finding unread. The hook refuses `gh pr merge … --auto` while the Codex check on the PR's
`headRefOid` is missing, queued, running, cancelled, or ended with `VERDICT:ERROR` (the runner,
not a review) in the comment carrying `<!-- codex-review -->`. A BLOCKING or WARNING verdict lets it through: reading the finding is
`/we:ci-review`'s job, the hook only makes sure there is one to read.

  * The check name is `.weside/config.json` → `review.codex_check`, default `Codex Review`.
  * A repo whose `.github/workflows/` names no job by that name has no Codex review: allowed,
    decided offline before any `gh` call. With `-R <other repo>` the local tree says nothing about
    that repo, so a missing check there is allowed too.
  * In any subagent (`agent_id` in the payload) every `gh pr merge` except `--disable-auto` is
    refused: merging is the Lead's call in the main session (`references/worker-dispatch.md`
    § Dev-only worker contract).
  * Fail-open on a `gh` or network error: Codex is advisory, an arm is reversible with
    `--disable-auto`, and a hook that blocks every merge during a GitHub outage costs more than
    the race it closes.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verification_gate as vg

DEFAULT_CHECK = "Codex Review"
# `gh pr merge` flags that take a value — their value is not the PR selector.
_VALUED = frozenset(
    {
        "-b",
        "--body",
        "-F",
        "--body-file",
        "-t",
        "--subject",
        "-A",
        "--author-email",
        "--match-head-commit",
        "-R",
        "--repo",
    }
)
_NO_VERDICT = frozenset({"cancelled", "timed_out", "action_required", "stale", "startup_failure"})
_VERDICT = re.compile(r"VERDICT:([A-Z]+)")
# The Codex workflow's own comment marker: other reviewers post `VERDICT:` markers too.
_MARKER = "<!-- codex-review -->"


def _gh(args: list[str], cwd: str | None) -> str | None:
    """stdout of `gh <args>`, or None on any failure (the caller fails open)."""
    try:
        out = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=20, check=False, cwd=cwd or None
        )
    except Exception:
        return None
    return out.stdout if out.returncode == 0 else None


def _merge_call(argv: list[str]) -> tuple[int, str | None, list[str]] | None:
    """(index of `gh`, global `-R` value, the merge's own args) for a `gh pr merge` in command
    position, or None."""
    for i, tok in enumerate(argv):
        bare = tok.lstrip("({$")
        if bare != "gh" and not bare.endswith("/gh"):
            continue
        if tok == bare and not vg._starts_a_command(argv, i):
            continue
        repo, j = None, i + 1
        while j < len(argv) and argv[j].startswith("-"):
            if argv[j] in ("-R", "--repo") and j + 1 < len(argv):
                repo, j = argv[j + 1], j + 2
            else:
                if argv[j].startswith("--repo="):
                    repo = argv[j].split("=", 1)[1]
                j += 1
        if argv[j : j + 2] == ["pr", "merge"]:
            return i, repo, [a.rstrip(";&|") for a in vg._args_from(argv, j + 2)]
    return None


def _selector_and_repo(args: list[str], repo: str | None) -> tuple[str | None, str | None]:
    selector, k = None, 0
    while k < len(args):
        a = args[k]
        if a in ("-R", "--repo") and k + 1 < len(args):
            repo = args[k + 1]
        if a.startswith("--repo="):
            repo = a.split("=", 1)[1]
        if a in _VALUED:
            k += 2
            continue
        if not a.startswith("-") and selector is None:
            selector = a
        k += 1
    return selector, repo


def _check_name(root: str) -> str:
    try:
        with open(os.path.join(root, ".weside", "config.json")) as fh:
            name = (json.load(fh).get("review") or {}).get("codex_check")
    except Exception:
        name = None
    return name if isinstance(name, str) and name.strip() else DEFAULT_CHECK


def _workflow_names(root: str, name: str) -> bool:
    """Some workflow in `root` declares a job (or workflow) named exactly `name`."""
    pattern = re.compile(rf"^\s*name:\s*[\"']?{re.escape(name)}[\"']?\s*(#.*)?$", re.MULTILINE)
    folder = Path(root) / ".github" / "workflows"
    try:
        files = [p for p in folder.iterdir() if p.suffix in (".yml", ".yaml")]
    except OSError:
        return False
    for path in files:
        try:
            if pattern.search(path.read_text(encoding="utf-8", errors="replace")):
                return True
        except OSError:
            continue
    return False


def _codex_state(selector: str | None, repo: str | None, name: str, cwd: str | None) -> str | None:
    """Why the arm must wait, or None when Codex has a verdict on the head (or gh failed)."""
    view = ["pr", "view", *([selector] if selector else []), *(["-R", repo] if repo else [])]
    raw = _gh([*view, "--json", "headRefOid,number,url"], cwd)
    try:
        pr = json.loads(raw or "")
        sha, number = pr["headRefOid"], pr["number"]
        slug = re.search(r"github\.com/([^/]+/[^/]+)/pull/", pr["url"]).group(1)
    except Exception:
        return None
    raw = _gh(
        ["api", f"repos/{slug}/commits/{sha}/check-runs?check_name={quote(name)}&per_page=100"],
        cwd,
    )
    try:
        runs = json.loads(raw or "")["check_runs"]
    except Exception:
        return None
    head = f"head {sha[:9]} of PR #{number}"
    if not runs:
        return None if repo else f"no `{name}` check on {head} yet"
    run = max(runs, key=lambda r: r.get("id", 0))
    if run.get("status") != "completed":
        return f"`{name}` is still {run.get('status')} on {head}"
    conclusion = run.get("conclusion")
    if conclusion in _NO_VERDICT:
        return f"`{name}` ended `{conclusion}` on {head}, without a verdict"
    if conclusion == "failure":
        raw = _gh([*view, "--json", "comments"], cwd)
        try:
            comments = json.loads(raw or "")["comments"]
        except Exception:
            return None
        bodies = [c.get("body") or "" for c in comments if _MARKER in (c.get("body") or "")]
        verdicts = [m.group(1) for b in bodies for m in _VERDICT.finditer(b)]
        if verdicts and verdicts[-1] == "ERROR":
            return f"`{name}` on {head} says VERDICT:ERROR (the runner, not a review)"
    return None


def _refusal(payload: dict) -> str | None:
    if payload.get("tool_name") != "Bash":
        return None
    command = (payload.get("tool_input") or {}).get("command", "")
    if "merge" not in command or "gh" not in command:
        return None
    argv = vg._argv_or_none(command)
    found = _merge_call(argv)
    if found is None:
        return None
    at, repo, args = found
    if "--disable-auto" in args:
        return None
    if payload.get("agent_id"):
        return (
            "A subagent never merges and never arms auto-merge; that is the main session's call "
            "(worker-dispatch.md § Dev-only worker contract). Report the PR; the Lead arms "
            "auto-merge after `/we:ci-review`."
        )
    if "--auto" not in args:
        return None
    cwd = vg._cwd_after_cd(argv, payload.get("cwd"), stop=at)
    root = vg._repo_root(cwd)
    if not root:
        return None
    selector, repo = _selector_and_repo(args, repo)
    name = _check_name(root)
    if not repo and not _workflow_names(root, name):
        return None
    why = _codex_state(selector, repo, name, cwd)
    if why is None:
        return None
    return (
        f"Auto-merge waits for the Codex verdict: {why}. Codex is no required check, so an arm "
        "now merges its finding unread. Arm once the check on this head has a verdict (not "
        "pending, not ERROR; rerun an ERROR run), after `/we:ci-review` read it."
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    reason = _refusal(payload)
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
