#!/usr/bin/env python3
r"""Splice the plan's `## Verification` block into a PR body, verbatim.

    pr-body-receipt.py <KEY> <body-in> <body-out>

Reads `docs/plans/<KEY>-story.md` from the git top level of the current directory, takes its
`## Verification` block with the verification gate's own section finder, and writes <body-in>
with that block to <body-out>: a receipt <body-in> already carries is replaced, otherwise the
block is appended. The result is checked with the gate's own rules; exit 1 names the problem.
Exit 2 before anything is read: a <KEY> that is no ticket key (`^[A-Z][A-Z0-9]+-\d+$`), or a
<body-out> that is the plan itself or a git-tracked file (swapped arguments once overwrote an
approved plan, 16.10.2026).

Optional: without a plan, or without a block in it, the author writes the block into the body
directly. When the plan has one, this script copies it instead of retyping it.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

_GATE = Path(__file__).resolve().parent.parent / "hooks" / "verification_gate.py"
_spec = importlib.util.spec_from_file_location("verification_gate", _GATE)
gate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(gate)


def _top_level() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    return Path(out.stdout.strip() or os.getcwd())


_KEY = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


def _tracked(path: str) -> bool:
    out = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", path],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.returncode == 0


def _argument_problem(key: str, body_out: str, plan_path: Path) -> str | None:
    if not _KEY.match(key):
        return f"<KEY> `{key}` is no ticket key (`^[A-Z][A-Z0-9]+-\\d+$`); argument order is <KEY> <body-in> <body-out>"
    if Path(body_out).resolve() == plan_path.resolve():
        return "<body-out> is the plan itself; pass a scratch path"
    if _tracked(body_out):
        return f"<body-out> `{body_out}` is tracked by git; pass a scratch path"
    return None


def splice(plan: str, body: str) -> str:
    """`body` carrying the plan's Verification block. ValueError when the plan has none."""
    span = gate._section_span(plan)
    if span is None:
        raise ValueError(
            "the plan carries no `## Verification` block: write it into the PR body yourself, "
            "`**Oracle:** not-observed — <reason>` when nothing was observed beyond tests"
        )
    block = plan[span[0] : span[2]].strip("\n")
    old = gate._section_span(body)
    if old is not None:
        head, tail = body[: old[0]], body[old[2] :]
        return head + block + "\n" + ("\n" + tail.lstrip("\n") if tail.strip() else "")
    return body.rstrip("\n") + ("\n\n" if body.strip() else "") + block + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    key, body_in, body_out = argv[1:]
    plan_path = _top_level() / "docs" / "plans" / f"{key}-story.md"
    problem = _argument_problem(key, body_out, plan_path)
    if problem:
        print(f"pr-body-receipt: {problem}", file=sys.stderr)
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    try:
        plan = plan_path.read_text(encoding="utf-8")
        body = Path(body_in).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"pr-body-receipt: {exc}", file=sys.stderr)
        return 1
    try:
        out = splice(plan, body)
    except ValueError as exc:
        print(f"pr-body-receipt: {plan_path}: {exc}", file=sys.stderr)
        return 1
    problem = gate._receipt_problem(out)
    if problem:
        print(
            f"pr-body-receipt: {plan_path} § Verification fails the gate: {problem}",
            file=sys.stderr,
        )
        return 1
    Path(body_out).write_text(out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
