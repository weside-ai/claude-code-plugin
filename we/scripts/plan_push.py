#!/usr/bin/env python3
"""Land plan commits from a scratch worktree on the default branch by push.

Usage (inside the detached scratch worktree of `references/plan-commit.md`):

  plan_push.py [--remote origin] [--branch <default>]

The worktree holds one or more commits on top of the default branch. The script

1. refuses the main worktree, a dirty tree and a tree with nothing to land;
2. fetches and rebases the commits onto `<remote>/<default>`;
3. refuses any path the commits touch outside the allowed globs: `plans.push_paths` in
   `.weside/config.json` (default `docs/plans/**`), plus a staging-check file under the crew's
   `oracles.receipt_dir` that travels with a plan and still carries `state: planned`. Config and
   crew are read from `<remote>/<default>` (`git show`), never from the commits being landed nor
   from the main checkout's uncommitted copy, so the rules in force decide;
4. runs the secret scan over the commit range: `plans.secret_scan`, a command template with
   `{range}` and an optional `{report}` (a JSON report path in gitleaks' format), default
   `gitleaks git --log-opts={range} --redact --no-banner --report-format json --report-path {report}`
   when `gitleaks` is on PATH. No scanner and no configured command refuses; `"none"` skips the scan.
   A finding prints file and line from the report, never the matched value, and never the
   scanner's own output;
5. lands the commits by one of two routes, picked by `<remote>/<default>`:
   - **direct** (no `.github/workflows/docs-push.yml` there): pushes `HEAD:<default>`;
   - **workflow** (the file is there): pushes `HEAD` to `docs-push/<sha>`, dispatches
     `docs-push.yml` on `<default>` with that SHA (`gh workflow run`), finds its run by the
     run name `docs-push <sha>`, waits for it, and maps the failed step: `Check range` exit 1,
     `Secret scan` exit 4, `Push` with `main moved` a lost race, anything else exit 2 with the run
     URL. The workflow checks the range again with its own fixed globs and pushes with a token no
     session holds; the local checks here only refuse early. The `docs-push/<sha>` branch is
     deleted before the script ends, except past the wait cap: the run may still land, so its
     branch stays and is named;
   a lost race (a non-fast-forward, or `main moved`) fetches, rebases, checks again and retries,
   at most three times;
6. prints the landed commit and one line per file.

The path check reads the tree diff `<remote>/<default>..HEAD` (`git diff --no-renames`), and a range
holding a merge commit is refused: a merge commit's own changes appear in no `git log` file list.

Globs: `**/` matches zero or more whole directories, a bare `**` anything, `*` and `?` stay inside
one directory, `{a,b}` expands (the grammar of `risk_paths.py`).

Exit codes:
  0  landed
  1  refused (main worktree, dirty tree, nothing to land, a path outside the globs); nothing was
     pushed
  2  failed (a git error, a rebase conflict, retries used up; on the workflow route also `gh`
     missing or the dispatch refused, the run not found within 60 s, the wait cap of 10 min
     reached, or a failed step without a mapping: the run URL is printed, never a second dispatch);
     nothing was pushed by this script, except past the wait cap: that run may still land the
     commits, so the caller waits for it (its URL) and never takes the PR way meanwhile
  3  the server rejected the push: this repo takes no direct push, land by PR
  4  refused by the secret scan: a finding, or no scanner configured (or it did not run); nothing
     was pushed, and this commit lands by no route, the PR way included. Its own code because a
     caller falls back to a PR on 1, and that fallback would push the finding to the forge
Pinned by `scripts/test_plan_push.py`.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import crew  # noqa: E402
from risk_paths import _expand, _glob_regex  # noqa: E402

DEFAULT_PATHS = ["docs/plans/**"]
DEFAULT_SCAN = (
    "gitleaks git --log-opts={range} --redact --no-banner "
    "--report-format json --report-path {report}"
)
RETRIES = 3
PLANNED = re.compile(r"^state:\s*planned\s*(#.*)?$", re.M)
REFUSED, FAILED, REJECTED, SCAN_REFUSED = 1, 2, 3, 4
NO_PUSH_LINE = "this repo takes no direct push; land by PR"
WORKFLOW = "docs-push.yml"
WORKFLOW_PATH = f".github/workflows/{WORKFLOW}"
POLL, FIND_TIMEOUT, WAIT_CAP = 5.0, 60.0, 600.0


class PushError(Exception):
    """Ends the run with an exit code and a message."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


class StillRunningError(PushError):
    """The wait cap ended the wait, not the run: its `docs-push/<sha>` branch must stay."""


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if check and out.returncode != 0:
        raise PushError(FAILED, f"git {' '.join(args)}: {(out.stderr or out.stdout).strip()}")
    return out


def push(remote: str, branch: str) -> subprocess.CompletedProcess:
    return git("push", "--porcelain", remote, f"HEAD:refs/heads/{branch}", check=False)


def default_branch(remote: str) -> str:
    head = git("symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD", check=False)
    if head.returncode == 0 and head.stdout.strip():
        return head.stdout.strip().split("/", 1)[1]
    for name in ("main", "master"):
        if (
            git(
                "rev-parse", "--verify", "-q", f"refs/remotes/{remote}/{name}", check=False
            ).returncode
            == 0
        ):
            return name
    raise PushError(FAILED, f"no default branch on {remote}; pass --branch")


def load_config(base: str) -> dict[str, Any]:
    shown = git("show", f"{base}:.weside/config.json", check=False)
    if shown.returncode != 0:
        return {}
    try:
        data = json.loads(shown.stdout)
    except ValueError as exc:
        raise PushError(FAILED, f"{base}:.weside/config.json: {exc}") from exc
    plans = data.get("plans") if isinstance(data, dict) else None
    return plans if isinstance(plans, dict) else {}


def receipt_dir(base: str) -> str | None:
    """`oracles.receipt_dir` of the crew in `<base>`'s `.weside/` (a pointer outside it: None)."""
    with tempfile.TemporaryDirectory() as tmp:
        archive = subprocess.run(
            ["git", "archive", "--format=tar", base, ".weside"], capture_output=True, check=False
        )
        if archive.returncode != 0:
            return None
        subprocess.run(
            ["tar", "-x", "-C", tmp], input=archive.stdout, capture_output=True, check=False
        )
        path = crew.at(tmp)
        try:
            # paths=False: only `.weside/` is unpacked, so `files.*` elsewhere cannot exist here.
            data = crew.load(path, paths=False) if path else None
        except crew.CrewError:
            return None
    value = ((data or {}).get("oracles") or {}).get("receipt_dir")
    return value.strip("/") if isinstance(value, str) and value.strip("/") else None


def preflight() -> None:
    if git("rev-parse", "--is-inside-work-tree", check=False).stdout.strip() != "true":
        raise PushError(REFUSED, "not inside a git worktree")
    git_dir = Path(git("rev-parse", "--absolute-git-dir").stdout.strip())
    common = Path(git("rev-parse", "--git-common-dir").stdout.strip())
    if git_dir.resolve() == (Path.cwd() / common).resolve():
        raise PushError(
            REFUSED,
            "refused: this is the main worktree; commit in a detached scratch worktree "
            "(references/plan-commit.md step 2)",
        )
    if git("status", "--porcelain").stdout.strip():
        raise PushError(REFUSED, "refused: the tree is dirty; commit or remove the changes first")


def rebase(base: str) -> None:
    git("fetch", "--quiet", *base.split("/", 1))
    if git("rebase", "--quiet", base, check=False).returncode != 0:
        git("rebase", "--abort", check=False)
        raise PushError(
            FAILED, f"rebase onto {base} conflicts; resolve it in this tree and run again"
        )
    if git("rev-list", "--count", f"{base}..HEAD").stdout.strip() == "0":
        raise PushError(REFUSED, f"refused: nothing to land, HEAD has no commit beyond {base}")


def touched(base: str) -> list[str]:
    out = git("diff", "--no-renames", "--name-only", base, "HEAD").stdout
    return sorted({line for line in out.splitlines() if line.strip()})


def merges(base: str) -> list[str]:
    return git("rev-list", "--merges", f"{base}..HEAD").stdout.split()


def outside(paths: list[str], globs: list[str], receipts: str | None) -> list[str]:
    patterns = [_glob_regex(g) for glob in globs for g in _expand(glob)]
    plans = [p for p in paths if any(r.match(p) for r in patterns)]
    rest = [p for p in paths if p not in plans]
    if not plans or not receipts:
        return rest
    return [p for p in rest if not (p.startswith(receipts + "/") and _planned(p))]


def _planned(path: str) -> bool:
    shown = git("show", f"HEAD:{path}", check=False)
    return shown.returncode == 0 and bool(PLANNED.search(shown.stdout))


def scan(base: str, setting: Any) -> None:
    if setting == "none":
        return
    if isinstance(setting, str) and setting.strip():
        template = setting
    elif setting is None and shutil.which("gitleaks"):
        template = DEFAULT_SCAN
    else:
        raise PushError(
            SCAN_REFUSED,
            "refused: no secret scanner; install gitleaks or set plans.secret_scan in "
            '.weside/config.json (a command with {range}, or "none")',
        )
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        argv = [
            t.replace("{range}", f"{base}..HEAD").replace("{report}", str(report))
            for t in shlex.split(template)
        ]
        try:
            run = subprocess.run(argv, capture_output=True, text=True, check=False)
        except OSError as exc:
            raise PushError(
                SCAN_REFUSED, f"refused: secret scan did not run: {exc.strerror}"
            ) from exc
        if run.returncode == 0:
            return
        lines = _findings(report)
    detail = "\n".join(f"  {line}" for line in lines) or (
        f"  exit {run.returncode}, no report; run the scan yourself: {template}"
    )
    raise PushError(SCAN_REFUSED, f"refused: the secret scan found something:\n{detail}")


def _findings(report: Path) -> list[str]:
    try:
        items = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    lines = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            where = f"{item.get('File', '?')}:{item.get('StartLine', '?')}"
            rule = item.get("RuleID") or "finding"
            commit = str(item.get("Commit") or "")[:9]
            lines.append(f"{where}  ({rule}{', commit ' + commit if commit else ''})")
    return lines


def check(base: str, plans: dict[str, Any]) -> None:
    globs = plans.get("push_paths") or DEFAULT_PATHS
    if isinstance(globs, str):
        globs = [globs]
    bad = outside(touched(base), globs, receipt_dir(base))
    if bad:
        listed = "\n".join(f"  {p}" for p in bad)
        raise PushError(
            REFUSED,
            f"refused: paths outside plans.push_paths ({', '.join(globs)}):\n{listed}\n"
            "land these by PR (references/plan-commit.md step 5, the PR way)",
        )
    found = merges(base)
    if found:
        raise PushError(
            REFUSED,
            f"refused: a merge commit in the range ({', '.join(c[:9] for c in found)}); "
            f"rebase onto {base} so the range is linear, then run again",
        )
    scan(base, plans.get("secret_scan"))


def land(remote: str, branch: str | None) -> list[str]:
    preflight()
    branch = branch or default_branch(remote)
    base = f"{remote}/{branch}"
    for _attempt in range(RETRIES + 1):
        rebase(base)
        check(base, load_config(base))
        before = git("rev-parse", base).stdout.strip()
        if git("cat-file", "-e", f"{base}:{WORKFLOW_PATH}", check=False).returncode == 0:
            if by_workflow(remote, branch, base):
                return _landed(before, branch)
            continue
        out = push(remote, branch)
        if out.returncode == 0:
            return _landed(before, branch)
        text = out.stdout + out.stderr
        if "[remote rejected]" in text or "declined" in text:
            raise PushError(REJECTED, NO_PUSH_LINE)
        if not re.search(r"rejected|non-fast-forward|fetch first", text):
            raise PushError(FAILED, f"push failed: {text.strip()}")
    raise PushError(FAILED, f"push lost the race {RETRIES + 1} times; run again")


GITHUB_REPO = re.compile(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$")
REPO: list[str] = []


def pin_repo(remote: str) -> None:
    """`gh` talks to the repo `<remote>` points at, not to whatever it would pick itself."""
    url = git("remote", "get-url", remote, check=False).stdout.strip()
    found = GITHUB_REPO.search(url)
    REPO[:] = ["--repo", found.group(1)] if found else []


def gh(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["gh", *args, *REPO], capture_output=True, text=True, check=False)
    except OSError as exc:
        raise PushError(FAILED, f"gh {' '.join(args)}: {exc.strerror}") from exc


def gh_json(*args: str) -> Any:
    out = gh(*args)
    if out.returncode != 0:
        raise PushError(FAILED, f"gh {' '.join(args)}: {(out.stderr or out.stdout).strip()}")
    try:
        return json.loads(out.stdout)
    except ValueError as exc:
        raise PushError(FAILED, f"gh {' '.join(args)}: no JSON: {exc}") from exc


def by_workflow(remote: str, branch: str, base: str) -> bool:
    """Land HEAD through `docs-push.yml`; True landed, False lost the race (rebase and again)."""
    sha = git("rev-parse", "HEAD").stdout.strip()
    ref = f"refs/heads/docs-push/{sha}"
    pin_repo(remote)
    git("push", "--quiet", remote, f"HEAD:{ref}")
    keep = False
    try:
        run = _dispatch(branch, sha)
        failed = _failed_step(run)
        if failed is None:
            git("fetch", "--quiet", remote, branch)
            if git("merge-base", "--is-ancestor", sha, base, check=False).returncode != 0:
                raise PushError(
                    FAILED, f"the run succeeded but {base} does not hold {sha}: {run['url']}"
                )
            return True
        log = gh("run", "view", str(run["databaseId"]), "--log-failed").stdout
        if failed == "Push" and "main moved" in log:
            return False
        if failed == "Check range":
            raise PushError(
                REFUSED,
                f"refused: {WORKFLOW} refused the range (step Check range): {run['url']}\n"
                f"{_tail(log)}land these by PR (references/plan-commit.md step 5, the PR way)",
            )
        if failed == "Secret scan":
            raise PushError(
                SCAN_REFUSED,
                f"refused: the secret scan of {WORKFLOW} found something (step Secret scan); "
                f"file and line in the run, the value never: {run['url']}",
            )
        raise PushError(FAILED, f"{WORKFLOW} failed in step {failed}: {run['url']}")
    except StillRunningError:
        keep = True
        raise
    finally:
        if not keep:
            git("push", "--quiet", remote, "--delete", ref, check=False)


def _dispatch(branch: str, sha: str) -> dict[str, Any]:
    started = gh("workflow", "run", WORKFLOW, "--ref", branch, "-f", f"sha={sha}")
    if started.returncode != 0:
        raise PushError(
            FAILED,
            f"gh workflow run {WORKFLOW} --ref {branch} -f sha={sha}: "
            f"{(started.stderr or started.stdout).strip()}",
        )
    title, deadline = f"docs-push {sha}", time.monotonic() + FIND_TIMEOUT
    while True:
        runs = gh_json(
            "run",
            "list",
            "--workflow",
            WORKFLOW,
            "--event",
            "workflow_dispatch",
            "--limit",
            "20",
            "--json",
            "databaseId,displayTitle,url",
        )
        mine = [r for r in runs if isinstance(r, dict) and r.get("displayTitle") == title]
        if mine:
            run = max(mine, key=lambda r: r["databaseId"])
            break
        if time.monotonic() > deadline:
            raise PushError(FAILED, f"no run '{title}' of {WORKFLOW} within {FIND_TIMEOUT:.0f} s")
        time.sleep(POLL)
    deadline = time.monotonic() + WAIT_CAP
    while True:
        view = gh_json(
            "run", "view", str(run["databaseId"]), "--json", "status,conclusion,jobs,url"
        )
        if view.get("status") == "completed":
            return {**run, **view}
        if time.monotonic() > deadline:
            raise StillRunningError(
                FAILED,
                f"{WORKFLOW} still running after {WAIT_CAP:.0f} s, it may still land: "
                f"{run['url']}; its branch docs-push/{sha} stays until it ends",
            )
        time.sleep(POLL)


def _failed_step(run: dict[str, Any]) -> str | None:
    """None when the run succeeded, else the name of its first failed step."""
    if run.get("conclusion") == "success":
        return None
    for job in run.get("jobs") or []:
        for step in job.get("steps") or []:
            if step.get("conclusion") == "failure":
                return str(step.get("name"))
    return f"? (conclusion {run.get('conclusion')})"


def _tail(log: str, lines: int = 20) -> str:
    kept = [line.split("\t")[-1] for line in log.splitlines() if line.strip()][-lines:]
    return "".join(f"  {line}\n" for line in kept)


def _landed(before: str, branch: str) -> list[str]:
    head = git("log", "-1", "--format=%h %s").stdout.strip()
    files = git("diff", "--no-renames", "--name-status", f"{before}..HEAD").stdout.splitlines()
    return [f"landed on {branch}: {head}", *(f"  {line}" for line in files)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Land plan commits on the default branch by push."
    )
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default=None)
    args = parser.parse_args(argv)
    try:
        lines = land(args.remote, args.branch)
    except PushError as stop:
        print(str(stop), file=sys.stderr)
        return stop.code
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
