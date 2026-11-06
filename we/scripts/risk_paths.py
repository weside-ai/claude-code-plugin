#!/usr/bin/env python3
"""Path-rule risk classifier for a repo without its own `risk.command` (crew.json).

Usage (run as a file, in the repository, on the branch or PR head):

  risk_paths.py <base>

Rules come only from `origin/main:.weside/risk-paths` (`git show`), never from the working tree, so
a PR that empties or rewrites the rules file is still classified by main's copy. The merge hook
(`hooks/automerge_gate.py`) runs this script itself, preferring `origin/main`'s blob of it, so a PR
that changes the classifier does not classify itself either.

Grammar, a subset of the rules file the core classifier reads:

  # comment
  [<section>]
  path <glob>

`<section>` is one of the one-way classes, in this fixed order of precedence: `brake-change`,
`money`, `destructive-migration`, `terraform-secrets`, `trust-loosening`; or `t2` (two-way).
A glob: `**/` matches zero or more whole directories, a bare `**` anything, `*` and `?` stay
inside one directory, `{a,b}` expands. A `line` or `from` rule, an unknown keyword or section, a
section without a rule, or a rule before the first section exits 2 naming it. A file without any
section (empty or comments only) is valid and classifies every diff `T0`: a crew that wants no brake
says so in a file (the merge hook then says it once per merge); a missing file is not that.

Diff: `git diff --name-only --no-renames <base>...HEAD`; `<base>` must be an ancestor of
`origin/main` (a base ahead of main would hide main's own changes), else exit 2.

Output (exit 0):

  line 1   `T0`, `T2` or `T2 one-way <class>` (the first class in the fixed order that matched)
  line 2   `review: high` for a one-way class, else `review: standard`
  then     one `<file>\t<class>: path <glob>` line per hit

Exit 2 on any failure (missing `origin/main`, missing or broken rules, a git error): a caller
treats it as "class not computed" and fails closed. Pinned by `scripts/test_risk_paths.py`.
"""

from __future__ import annotations

import re
import subprocess
import sys

RULES_FROM = "origin/main"
RULES_FILE = ".weside/risk-paths"
ONE_WAY = (
    "brake-change",
    "money",
    "destructive-migration",
    "terraform-secrets",
    "trust-loosening",
)
SECTIONS = (*ONE_WAY, "t2")


class RiskError(Exception):
    """A failure that must exit 2."""


def _git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    except OSError as exc:
        raise RiskError(f"git {args[0]}: {exc}") from exc
    if out.returncode != 0:
        raise RiskError(f"git {' '.join(args)}: {out.stderr.strip() or out.returncode}")
    return out.stdout


def _expand(token: str) -> list[str]:
    m = re.search(r"\{([^{}]*)\}", token)
    if not m:
        return [token]
    head, tail = token[: m.start()], token[m.end() :]
    return [p for alt in m.group(1).split(",") for p in _expand(head + alt.strip() + tail)]


def _glob_regex(glob: str) -> re.Pattern[str]:
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def parse_rules(text: str) -> dict[str, list[tuple[str, re.Pattern[str]]]]:
    """Section → [(glob as written, compiled pattern)]; RiskError on anything outside the grammar."""
    rules: dict[str, list[tuple[str, re.Pattern[str]]]] = {}
    section = None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        head = re.fullmatch(r"\[([^\]]+)\]", line)
        if head:
            section = head.group(1).strip()
            if section not in SECTIONS:
                raise RiskError(f"{RULES_FILE}:{n}: unknown section [{section}]")
            if section in rules:
                raise RiskError(f"{RULES_FILE}:{n}: section [{section}] twice")
            rules[section] = []
            continue
        keyword, _, rest = line.partition(" ")
        if keyword in ("line", "from"):
            raise RiskError(
                f"{RULES_FILE}:{n}: a `{keyword}` rule needs the repo's own risk.command"
            )
        if keyword != "path" or not rest.strip():
            raise RiskError(f"{RULES_FILE}:{n}: not a rule: {line}")
        if section is None:
            raise RiskError(f"{RULES_FILE}:{n}: rule before the first section")
        glob = rest.strip()
        for one in _expand(glob):
            rules[section].append((glob, _glob_regex(one)))
    for name, items in rules.items():
        if not items:
            raise RiskError(f"{RULES_FILE}: section [{name}] has no rule")
    return rules


def classify(changed: list[str], rules: dict[str, list[tuple[str, re.Pattern[str]]]]) -> list[str]:
    """The output lines for `changed` under `rules`."""
    hits: list[tuple[str, str, str]] = []
    for path in changed:
        for section in SECTIONS:
            seen = set()
            for glob, pattern in rules.get(section, []):
                if glob not in seen and pattern.match(path):
                    seen.add(glob)
                    hits.append((path, section, glob))
    found = {section for _, section, _ in hits}
    one_way = next((c for c in ONE_WAY if c in found), None)
    if one_way:
        lines = [f"T2 one-way {one_way}", "review: high"]
    elif "t2" in found:
        lines = ["T2", "review: standard"]
    else:
        lines = ["T0", "review: standard"]
    return lines + [f"{path}\t{section}: path {glob}" for path, section, glob in hits]


def run(argv: list[str]) -> list[str]:
    if len(argv) != 1 or argv[0].startswith("-"):
        raise RiskError("usage: risk_paths.py <base>")
    base = argv[0]
    _git("rev-parse", "--verify", "-q", f"{RULES_FROM}^{{commit}}")
    try:
        _git("merge-base", "--is-ancestor", base, RULES_FROM)
    except RiskError as exc:
        raise RiskError(f"base {base} is not an ancestor of {RULES_FROM}") from exc
    rules = parse_rules(_git("show", f"{RULES_FROM}:{RULES_FILE}"))
    diff = _git("diff", "--name-only", "--no-renames", f"{base}...HEAD")
    return classify([line for line in diff.splitlines() if line.strip()], rules)


def main(argv: list[str] | None = None) -> int:
    try:
        lines = run(sys.argv[1:] if argv is None else argv)
    except RiskError as exc:
        print(f"risk_paths: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
