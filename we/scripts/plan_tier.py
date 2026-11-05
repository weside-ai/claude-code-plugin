#!/usr/bin/env python3
"""The plan-only tier: the repo's `risk.command` run on a story plan before any diff exists.

`plan_tier(crew, repo_root, key, plan_rel, fetch=False) -> TierResult(line, failure, warnings)`.

The contract with `risk.command` (the crew's classifier, called `<command> <base> <KEY>`): it reads
the plan `docs/plans/<KEY>-story.md` from `HEAD`'s tree and the diff `<base>...HEAD`, prints the
tier as line 1 (`T<0-3>` or `T<n> one-way <class>`) and exits 0; any failure exits non-zero.

To keep the caller's checkout out of the plan's tier, the command never runs there:

1. `risk.command` unset → no tier, one warning, line `none`.
2. `ref` is `risk.rules_from`; with `fetch` (board.py select) `git fetch --quiet origin` runs
   first when `ref` is an `origin/` branch, and a failed fetch is one warning.
3. `ref`, the plan on `ref` and the command's blob on `ref` must exist; a plan missing on `ref`
   is its own failure and the command never runs.
4. The blob (`git cat-file blob`, the stored bytes) is written to a temp file, and a
   `git worktree add --no-checkout --detach` tree at `ref` is made: there `HEAD = base = ref`,
   so the diff is empty and the plan comes from `ref`'s tree.
5. The command runs in that tree with a 60 s timeout.
6. Line 1 must match `^T[0-3]( one-way \\S+)?$`, and a one-way class must be in `risk.one_way`.
7. The temp dir goes and `git worktree prune` drops the scratch tree's entry, always.

Python 3.9, stdlib only.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any, NamedTuple

TIER_LINE = re.compile(r"^T[0-3]( one-way (\S+))?$")
RUN_TIMEOUT = 60
NO_COMMAND = "warning: tier check off: crew.json names no risk.command"


class TierResult(NamedTuple):
    """`line` is the tier (`none` without a command); `failure` the reason it was not computed."""

    line: str | None
    failure: str | None
    warnings: list[str]


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=False, timeout=RUN_TIMEOUT
    )
    if check and done.returncode != 0:
        raise TierError(
            f"git {' '.join(args)}: {done.stderr.decode(errors='replace').strip() or 'failed'}"
        )
    return done


class TierError(Exception):
    pass


def plan_tier(
    crew: dict[str, Any], repo_root: Path, key: str, plan_rel: str, fetch: bool = False
) -> TierResult:
    risk = crew.get("risk") or {}
    command = risk.get("command")
    if not command:
        return TierResult("none", None, [NO_COMMAND])
    ref = str(risk.get("rules_from") or "origin/main")
    warnings: list[str] = []
    if fetch and ref.startswith("origin/"):
        done = _git(repo_root, "fetch", "--quiet", "origin", check=False)
        if done.returncode != 0:
            why = done.stderr.decode(errors="replace").strip().splitlines()
            warnings.append(
                f"warning: git fetch origin failed ({why[-1] if why else 'exit ' + str(done.returncode)}); "
                f"the tier reads the local {ref}"
            )
    try:
        return TierResult(_run(risk, repo_root, ref, key, plan_rel, str(command)), None, warnings)
    except TierError as exc:
        return TierResult(None, str(exc), warnings)


def _run(risk: dict[str, Any], root: Path, ref: str, key: str, plan_rel: str, command: str) -> str:
    words = shlex.split(command)
    if not words:
        raise TierError("risk.command is empty")
    if _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False).returncode:
        raise TierError(f"risk.rules_from {ref} is no commit here")
    if _git(root, "cat-file", "-e", f"{ref}:{plan_rel}", check=False).returncode:
        raise TierError(f"plan not on {ref}: {plan_rel}")
    blob = _git(root, "cat-file", "blob", f"{ref}:{words[0]}", check=False)
    if blob.returncode != 0:
        raise TierError(f"risk.command {words[0]} not on {ref}")
    try:
        with tempfile.TemporaryDirectory(prefix="we-plan-tier-") as tmp:
            script = Path(tmp) / "risk"
            script.write_bytes(blob.stdout)
            os.chmod(script, 0o700)
            tree = Path(tmp) / "wt"
            _git(root, "worktree", "add", "--no-checkout", "--detach", str(tree), ref)
            try:
                done = subprocess.run(
                    [str(script), *words[1:], ref, key],
                    cwd=str(tree),
                    capture_output=True,
                    text=True,
                    timeout=RUN_TIMEOUT,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                raise TierError(f"risk.command ran past {RUN_TIMEOUT} s") from None
            except OSError as exc:
                raise TierError(f"risk.command not runnable: {exc.strerror}") from None
    finally:
        # the temp dir is gone; prune drops the scratch tree's entry (never `remove --force`)
        _git(root, "worktree", "prune", check=False)
    if done.returncode != 0:
        last = (done.stderr or done.stdout).strip().splitlines()
        raise TierError(f"risk.command exit {done.returncode}" + (f": {last[-1]}" if last else ""))
    line = (done.stdout.splitlines() or [""])[0].strip()
    found = TIER_LINE.match(line)
    if not found:
        raise TierError(f"line 1 {line!r} is no tier (T0-T3, optionally one-way <class>)")
    one_way = list(risk.get("one_way") or [])
    if found.group(2) and found.group(2) not in one_way:
        raise TierError(f"one-way class {found.group(2)!r} is not in risk.one_way")
    return line
