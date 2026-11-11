#!/usr/bin/env python3
"""The one runner of a repo's risk classifier on a commit range: the merge hook
(`hooks/automerge_gate.py`, a PR's class) and the T2 panel's carry (`lens_verdict.py`, the delta
between two heads) both call it, so the same range gets the same class.

`rules(root, git)` picks the classifier from `RULES_FROM` (`origin/main`), fetched first: the
crew's `risk.command` blob (from `risk.rules_from`), else the plugin's `risk_paths.py` (the repo's
own blob of `we/scripts/risk_paths.py` when it carries one) over `.weside/risk-paths`, else no
rules (class T0) — unless `RULES_FROM` carries a crew file: a crew without rules is a reason, never
T0. `run(root, git, found, head, base, timeout)` writes the classifier to a temp file and runs it
with `base` in a no-checkout worktree of `head`; line 1 must match `CLASS_LINE`. The worktree and
the temp dir go whatever happens.

`git(root, *args, timeout=...)` is the caller's git: stdout, or None on any failure (the hook passes
its own, cut to its time budget). Python 3.9, stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional

RULES_FROM = "origin/main"
CLASS_LINE = re.compile(r"^T[02]( one-way (\S+))?$")
RISK_PATHS = Path(__file__).resolve().with_name("risk_paths.py")
CLASSIFY_TIMEOUT = 60

Git = Callable[..., Optional[str]]
Found = tuple  # (argv prefix with a {file} slot, blob spec or None, rules ref)


def plain_git(root: str, *args: str, timeout: float = 20) -> str | None:
    """stdout of `git <args>` in `root`, or None on any failure (no repo hooks)."""
    try:
        out = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=root,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 else None


def crew_present(root: str, git: Git, ref: str = RULES_FROM) -> bool:
    """`ref` carries a crew file of its own, parsing or not."""
    return git(root, "cat-file", "-e", f"{ref}:.weside/crew.json") is not None


def crew_on(root: str, git: Git, ref: str = RULES_FROM) -> dict:
    """`ref`'s `.weside/crew.json` as a dict; {} when it has none or it does not parse."""
    raw = git(root, "show", f"{ref}:.weside/crew.json")
    try:
        doc = json.loads(raw or "")
    except ValueError:
        return {}
    return doc if isinstance(doc, dict) else {}


def fetch_rules(root: str, ref: str, git: Git) -> bool:
    """Fetch `origin/<branch>` so the rules are current; False when it cannot be fetched (a ref
    outside `origin/` is not fetched and must exist)."""
    remote, _, branch = ref.partition("/")
    if remote == "origin" and branch:
        refspec = f"+refs/heads/{branch}:refs/remotes/origin/{branch}"
        if git(root, "fetch", "-q", "--no-tags", "origin", refspec, timeout=60) is None:
            return False
    return git(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}") is not None


def rules(root: str, git: Git) -> Found | None | str:
    """(argv prefix with a {file} slot, blob spec to write there or None, rules ref);
    None when the repo uses no rules (class T0); a str is the reason it cannot be computed."""
    if not fetch_rules(root, RULES_FROM, git):
        return (
            f"`git fetch origin {RULES_FROM.split('/', 1)[1]}` failed; the rules must be current"
        )
    crew_doc = crew_on(root, git)
    risk = crew_doc.get("risk") or {}
    rules_from = risk.get("rules_from") if isinstance(risk.get("rules_from"), str) else RULES_FROM
    command = risk.get("command")
    if isinstance(command, str) and command.strip():
        parts = command.split()
        return ["{file}", *parts[1:]], f"{rules_from}:{parts[0]}", rules_from
    if git(root, "cat-file", "-e", f"{rules_from}:.weside/risk-paths") is None:
        if crew_doc or crew_present(root, git, rules_from):
            return (
                f"this repo has a crew (`.weside/crew.json` on {rules_from}) but no risk rules: "
                f"neither `risk.command` in the crew nor `.weside/risk-paths` on {rules_from}, "
                "so the hook cannot tell a one-way PR from a two-way one. Land a "
                "`.weside/risk-paths` (`/we:setup` writes a starter; without one-way sections it "
                "brakes nothing, on purpose) or a `risk.command` first; the PR that lands it is "
                "refused here too, so the owner merges that one by hand"
            )
        return None
    own = f"{rules_from}:we/scripts/risk_paths.py"
    blob = own if git(root, "cat-file", "-e", own) is not None else None
    return [sys.executable, "{file}"], blob, rules_from


def exec_in_tree(
    root: str,
    git: Git,
    blob: str | None,
    args: list[str],
    tree_ref: str,
    timeout: float,
) -> tuple[subprocess.CompletedProcess | None, str | None]:
    """(the finished run, None) or (None, why): the script `blob` (a `<ref>:<path>` spec, or None
    for the plugin's `risk_paths.py`) written to a temp file and run as `<file> <args>` in a
    no-checkout worktree of `tree_ref`. Every argv entry `{file}` is the script. The temp dir goes
    and `git worktree prune` drops the scratch tree's entry, always (never `remove --force`)."""
    tmp = tempfile.mkdtemp(prefix="we-merge-class.")
    tree = os.path.join(tmp, "head")
    try:
        script = os.path.join(tmp, "classifier")
        if blob is None:
            shutil.copyfile(RISK_PATHS, script)
        else:
            body = git(root, "show", blob)
            if body is None:
                return None, f"`{blob}` is missing"
            Path(script).write_text(body, encoding="utf-8")
        os.chmod(script, 0o700)
        added = git(
            root, "worktree", "add", "--no-checkout", "--detach", tree, tree_ref, timeout=60
        )
        if added is None:
            return None, f"`git worktree add` of {tree_ref[:9]} failed"
        argv = [script if a == "{file}" else a for a in args]
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        try:
            out = subprocess.run(
                argv,
                cwd=tree,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return None, f"the classifier ran past {timeout:.0f} s"
        except OSError as exc:
            return None, f"the classifier is not runnable: {exc.strerror}"
        return out, None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        git(root, "worktree", "prune")


def run(
    root: str,
    git: Git,
    found: Found,
    head: str,
    base: str,
    timeout: float = CLASSIFY_TIMEOUT,
) -> tuple[list[str] | None, str | None]:
    """(output lines with the class as line 1, None) or (None, why): the classifier on `base` in
    a no-checkout worktree of `head` (`exec_in_tree`)."""
    prefix, blob, _rules_from = found
    out, why = exec_in_tree(root, git, blob, [*prefix, base], head, timeout)
    if out is None:
        return None, why
    lines = out.stdout.splitlines() or [""]
    line = lines[0].strip()
    if out.returncode != 0 or not CLASS_LINE.match(line):
        last = (out.stderr.strip().splitlines() or [line or "no output"])[-1]
        return None, f"the classifier exited {out.returncode}: {last}"
    return [line, *lines[1:]], None
