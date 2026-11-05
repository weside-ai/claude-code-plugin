#!/usr/bin/env python3
"""The cold-start receipt gate: a PR whose diff touches a suite input carries a green receipt for
exactly the inputs on its head.

The receipt is the block ``run.py release`` prints: the line ``<!-- coldstart-receipt -->`` and a
fenced JSON code block after it, pasted into the PR body. The gate reads the body from ``--body-file``
or the environment variable ``PR_BODY`` (the workflow passes it only through ``env:``; the body is
untrusted text, parsed as JSON and never executed), recomputes the affected set and the inputs
digest on the checked-out head (``affected.py``), and fails, naming the cause, on:

- ``no receipt``: affected scenarios and no marker in the body;
- ``receipt unreadable``: a marker without a parseable JSON block;
- ``receipt red: <reasons>``: the block's ``status`` is not ``green`` (a gated miss, a cap overrun);
- ``affected scenario left out: <id>``: an affected scenario of the head without a row of 3 runs;
- ``gated miss <id> <hits>/<runs>``: a scenario gated in the head's ``rates.json`` (or new to it)
  with fewer than 3 hits;
- ``receipt digest <a> != head <b>``: the block was written for other inputs or an older head.

A PR touching no suite input passes without a block. Tokens over ``rates.json``
``cost_target_tokens`` pass with one ``cost over target: <n> > <t>`` line, also written to
``$GITHUB_STEP_SUMMARY``. ``git`` failing exits 2: the check is red, never green by default. The
receipt is a record the worker writes, not proof that the runs happened; the digest is the only part
a machine checks.

Usage:
  python3 tests/coldstart/receipt_gate.py --base origin/main [--body-file <file>]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import affected

MARKER = "<!-- coldstart-receipt -->"
RUNS = 3
BLOCK = re.compile(r"```json[ \t]*\n(.*?)\n[ \t]*```", re.DOTALL)


def _rates(root: Path) -> dict:
    path = root / "tests" / "coldstart" / "rates.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def parse(body: str) -> dict | None:
    """The receipt block after the marker; None when there is none or it is not a JSON object."""
    after = body.split(MARKER, 1)[1]
    match = BLOCK.search(after)
    if not match:
        return None
    try:
        block = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return block if isinstance(block, dict) else None


def check(  # noqa: PLR0911 (one return per cause keeps the failure line exact)
    body: str, base: str, root: Path = affected.REPO
) -> tuple[bool, list[str]]:
    """(passed, lines): the verdict and what to print. Raises ``affected.GitError``."""
    ids = affected.affected(base, root)
    if not ids:
        return True, ["no suite input changed"]
    if MARKER not in body:
        return False, [f"no receipt: {len(ids)} affected scenarios ({', '.join(sorted(ids))})"]
    block = parse(body)
    if block is None:
        return False, ["receipt unreadable: no JSON block after the marker"]
    if block.get("status") != "green":
        reasons = "; ".join(str(r) for r in block.get("reasons") or []) or "status not green"
        return False, [f"receipt red: {reasons}"]
    rows = {r.get("id"): r for r in block.get("scenarios") or [] if isinstance(r, dict)}
    for sid in sorted(ids):
        row = rows.get(sid) or {}
        if row.get("status") != "run" or row.get("runs") != RUNS:
            return False, [f"affected scenario left out: {sid}"]
    measured = _rates(root).get("scenarios") or {}
    for sid in sorted(ids):
        gated = (measured.get(sid) or {}).get("gated", True)
        hits = rows[sid].get("hits")
        if gated and hits != RUNS:
            return False, [f"gated miss {sid} {hits}/{RUNS}"]
    head = affected.digest(ids, root)
    if block.get("digest") != head:
        return False, [f"receipt digest {block.get('digest')} != head {head}"]
    lines = [f"receipt green: {len(ids)} affected scenarios, digest {head}"]
    target = _rates(root).get("cost_target_tokens")
    tokens = block.get("tokens")
    if target and isinstance(tokens, int) and tokens > int(target):
        lines.append(f"cost over target: {tokens} > {target}")
    return True, lines


def main(args: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="receipt_gate.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--base", required=True)
    p.add_argument("--body-file")
    p.add_argument("--root", default=str(affected.REPO), help="the checkout (default: this one)")
    ns = p.parse_args(args)
    if ns.body_file:
        body = Path(ns.body_file).read_text(encoding="utf-8")
    else:
        body = os.environ.get("PR_BODY") or ""
    try:
        passed, lines = check(body, ns.base, Path(ns.root))
    except affected.GitError as exc:
        print(f"coldstart-receipt: {exc}", file=sys.stderr)
        return 2
    for line in lines:
        print(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("".join(f"- {line}\n" for line in lines))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
