#!/usr/bin/env python3
r"""Splice the plan's `## Verification` block into a PR body, verbatim.

    pr-body-receipt.py <KEY> <body-in> <body-out>

Reads `docs/plans/<KEY>-story.md` from the git top level of the current directory, takes its
`## Verification` block with the verification gate's own section finder, and writes <body-in>
with that block to <body-out>: a receipt <body-in> already carries is replaced, otherwise the
block is appended. The result is checked with the gate's own rules; exit 1 names the problem.
Exit 2 before anything is read: a <KEY> without a `docs/plans/<KEY>-story.md`, or a
<body-out> that is the plan itself or a git-tracked file (swapped arguments once overwrote an
approved plan, 16.10.2026).

Optional: without a plan, or without a block in it, the author writes the block into the body
directly. When the plan has one, this script copies it instead of retyping it.

**The pre-merge receipt line.** When `.weside/config.json` names `verification.pre_merge_receipt`
(a command with `{KEY}`), this script runs it after the splice (cwd the git top level, timeout
1200 s) and writes its verdict as lines directly under the spliced block, replacing any earlier
`receipt …` line. It is the only writer of that line; a session never types it. The command's
stdout contract and exit code map as follows:

  * exit 0 + `skip: …`                  → no line (the story has no receipt)
  * exit 0 + `report: <path>`           → `receipt green: <path>`
  * exit 0 + `not-run: <reason>` lines  → `receipt not run on DEV: <reasons>` (below the green
                                           line when a report came too); it blocks nothing
  * exit 1                              → `receipt red: <path>` (`not-run:` lines dropped)
  * any other exit, a timeout, a command not found
                                        → `receipt red (not run: <reason>)`

The path sits in a code span. `automerge_gate.py` refuses `gh pr merge --auto` while a line
starting `receipt red` stands in the PR body. A red receipt is a result, not a script error: the
exit code stays the splice's. Without the key, the body is the splice alone.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

_GATE = Path(__file__).resolve().parent.parent / "hooks" / "verification_gate.py"
_spec = importlib.util.spec_from_file_location("verification_gate", _GATE)
gate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(gate)


RECEIPT_TIMEOUT_S = 1200
_RECEIPT_LINE = re.compile(r"^receipt (red|green|not run on DEV)\b")
_FENCE = re.compile(r"^(`{3,}|~{3,})")


def _receipt_command(root: Path) -> str | None:
    """`verification.pre_merge_receipt` of the repo's config, or None (absent, unreadable)."""
    try:
        with open(root / ".weside" / "config.json", encoding="utf-8") as fh:
            block = json.load(fh).get("verification")
    except (OSError, ValueError, AttributeError):
        return None
    command = block.get("pre_merge_receipt") if isinstance(block, dict) else None
    return command if isinstance(command, str) and command.strip() else None


def _code_span(text: str) -> str:
    """`text` as a Markdown code span whose fence is longer than any backtick run in it."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def run_receipt(command: str, key: str, root: Path) -> list[str]:
    """The `receipt …` lines for this run of `command`; [] when the story has no receipt."""
    argv = [tok.replace("{KEY}", key) for tok in shlex.split(command)]
    try:
        done = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=RECEIPT_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [f"receipt red (not run: timeout after {RECEIPT_TIMEOUT_S} s)"]
    except FileNotFoundError:
        return [f"receipt red (not run: {argv[0] if argv else command} not found)"]
    if done.stderr:
        sys.stderr.write(done.stderr)
    lines = done.stdout.splitlines()

    def values(prefix: str) -> list[str]:
        return [ln[len(prefix) :].strip() for ln in lines if ln.startswith(prefix)]

    reports, not_run = values("report:"), values("not-run:")
    if done.returncode == 1:
        if not reports:
            return ["receipt red (not run: exit 1 without a `report:` line)"]
        return [f"receipt red: {_code_span(reports[-1])}"]
    if done.returncode != 0:
        said = [ln.strip() for ln in done.stderr.splitlines() if ln.strip()]
        why = f"exit {done.returncode}" + (f": {said[-1][:200]}" if said else "")
        return [f"receipt red (not run: {why})"]
    out = []
    if reports:
        out.append(f"receipt green: {_code_span(reports[-1])}")
    if not_run:
        out.append("receipt not run on DEV: " + "; ".join(not_run))
    return out


def _without_receipt_lines(body: str) -> str:
    kept, fenced = [], False
    for line in body.splitlines(keepends=True):
        if _FENCE.match(line.strip()):
            fenced = not fenced
        if not fenced and _RECEIPT_LINE.match(line.strip()):
            continue
        kept.append(line)
    return "".join(kept)


def with_receipt(spliced: str, lines: list[str]) -> str:
    """`spliced` without old `receipt …` lines, `lines` directly under its Verification block."""
    body = _without_receipt_lines(spliced)
    if not lines:
        return body
    span = gate._section_span(body)
    if span is None:  # the splice always leaves one; keep the lines rather than drop them
        return body.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n"
    head, tail = body[: span[2]].rstrip("\n"), body[span[2] :]
    block = head + "\n\n" + "\n".join(lines) + "\n"
    return block + ("\n" + tail.lstrip("\n") if tail.strip() else "")


def _top_level() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    return Path(out.stdout.strip() or os.getcwd())


def _tracked(path: str) -> bool:
    out = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", path],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.returncode == 0


def _argument_problem(key: str, body_out: str, plan_path: Path) -> str | None:
    if not plan_path.is_file():
        return f"no plan `docs/plans/{key}-story.md` for <KEY> `{key}`; argument order is <KEY> <body-in> <body-out>"
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
    root = _top_level()
    plan_path = root / "docs" / "plans" / f"{key}-story.md"
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
    command = _receipt_command(root)
    if command is not None:
        lines = run_receipt(command, key, root)
        out = with_receipt(out, lines)
        for line in lines:
            print(f"pr-body-receipt: {line}", file=sys.stderr)
    Path(body_out).write_text(out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
