#!/usr/bin/env python3
"""Print the PR body's test line: tests added and removed in the branch against its base.

    test-delta.py <base>        e.g. test-delta.py origin/main

Reads `git diff -M -U0 <base>...HEAD` (from the merge base, renames detected) and prints one
line, `Tests: +N / -M (net ±K)`. Visibility only: exit 0 whatever the numbers.

Counted, one per definition line, anchored at the line start:
- Python (`.py`): `def test_…(` and `async def test_…(`, methods included.
- JS/TS (`.js .jsx .mjs .cjs .ts .tsx`): `it(` and `test(`, with modifiers such as `.each`,
  `.only`, `.skip`.
A name both removed and added in the diff (a moved test, a reformatted signature) cancels out.

Not counted: parametrize rows and `.each` table rows (the definition counts once), other
languages, `describe` blocks, snapshot or golden files, a test whose definition line starts
with something other than the patterns above.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter

_PY = re.compile(r"^\s*(?:async\s+)?def\s+(test\w*)\s*\(")
_JS = re.compile(r"^\s*(?:it|test)(?:\.\w+)*\s*\((.*)$")
_JS_NAME = re.compile(r"""(['"`])(.*?)\1""")
_JS_EXT = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")


def _test_name(path: str, line: str) -> str | None:
    if path.endswith(".py"):
        m = _PY.match(line)
        return m.group(1) if m else None
    if path.endswith(_JS_EXT):
        m = _JS.match(line)
        if not m:
            return None
        literal = _JS_NAME.search(m.group(1))
        return literal.group(2) if literal else m.group(1).strip()
    return None


def count(diff: str) -> tuple[int, int]:
    """(added, removed) test definitions in a unified diff, same names cancelled."""
    added: Counter[str] = Counter()
    removed: Counter[str] = Counter()
    path, in_header = "", True
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            path, in_header = line.rsplit(" b/", 1)[-1], True
            continue
        if line.startswith("@@"):
            in_header = False
            continue
        if in_header or line[:1] not in ("+", "-"):
            continue
        name = _test_name(path, line[1:])
        if name is not None:
            (added if line[0] == "+" else removed)[name] += 1
    return sum((added - removed).values()), sum((removed - added).values())


def render(plus: int, minus: int) -> str:
    net = plus - minus
    sign = "+" if net > 0 else "-" if net < 0 else "±"
    return f"Tests: +{plus} / -{minus} (net {sign}{abs(net)})"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    out = subprocess.run(
        ["git", "diff", "-M", "-U0", "--no-color", "--no-ext-diff", f"{argv[1]}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        print(f"test-delta: git diff failed: {out.stderr.strip()}", file=sys.stderr)
        return 1
    print(render(*count(out.stdout)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
