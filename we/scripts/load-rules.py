#!/usr/bin/env python3
"""Print the `.claude/rules` guidance that applies to a set of files.

Claude Code loads these rules by itself. Every other agent — Codex, Gemini, a
foreign engine in a worker — does not, and a rule nobody loads governs nothing.
This script is that bridge, and it belongs to no single repo: the rules
directory is found from the git root, not from the script's own location.

Which rule applies to which file is decided by `rule_loading.py`, the plugin's one
implementation of Claude Code's rule-loading semantics.

Modes:
  (none)            the full Markdown bundle: every applicable rule, in full
  --list            one `always|matched <path>` line per rule, nothing else
  --explain <path>  why each rule does or does not apply to that one file
  --files-matching <glob>  the repo files one `paths:` glob loads for
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rule_loading import (
    Rule,
    applicable,
    list_files,
    load_rules,
    normalize_path,
    pattern_matches,
    repo_root,
)


def _git_changed_files(root: Path) -> list[str]:
    commands = [
        ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    paths: list[str] = []
    for command in commands:
        result = subprocess.run(command, cwd=root, check=False, text=True, capture_output=True)
        if result.returncode != 0:
            continue
        paths.extend(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(set(paths))


def _print_list(root: Path, always_on: list[Rule], path_matched: list[Rule]) -> None:
    for label, rules in (("always", always_on), ("matched", path_matched)):
        for rule in rules:
            print(f"{label}\t{rule.path.relative_to(root).as_posix()}")


def _print_markdown(root: Path, always_on: list[Rule], path_matched: list[Rule]) -> None:
    print("# Applicable rules")
    total = 0
    for title, rules in (("Always-on", always_on), ("Path-matched", path_matched)):
        print(f"\n## {title}")
        if not rules:
            print("\n_None_")
            continue
        for rule in rules:
            rel_path = rule.path.relative_to(root).as_posix()
            suffix = f" - {rule.description}" if rule.description else ""
            body = rule.path.read_text(encoding="utf-8").rstrip()
            total += len(body)
            print(f"\n### `{rel_path}`{suffix}\n")
            if rule.defect:
                print(f"> Frontmatter defect: {rule.defect}\n")
            print(body)
    print(f"\n---\n\n_{len(always_on) + len(path_matched)} rules, {total} characters._")


def _print_explain(root: Path, rules: list[Rule], target: str) -> None:
    print(f"# Why each rule applies to `{target}`\n")
    for rule in rules:
        rel_path = rule.path.relative_to(root).as_posix()
        note = f" ({rule.defect})" if rule.defect else ""
        if rule.is_always_on:
            print(f"- `{rel_path}` — **always-on**{note}")
            continue
        reason = rule.match_reason(target)
        if reason:
            print(f"- `{rel_path}` — **matched** by {reason}{note}")
        else:
            print(f"- `{rel_path}` — no match ({len(rule.patterns)} patterns tried){note}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="Files to match against.")
    parser.add_argument("--root", help="Repo root; default is the git root.")
    parser.add_argument(
        "--changed", action="store_true", help="Use changed and untracked git files."
    )
    parser.add_argument("--list", action="store_true", help="Only print matching rule paths.")
    parser.add_argument("--explain", help="Explain the verdict for one path.")
    parser.add_argument(
        "--files-matching", metavar="GLOB", help="List the repo files one `paths:` glob loads for."
    )
    args = parser.parse_args()

    root = repo_root(args.root)
    if args.files_matching:
        for rel in list_files(root):
            if pattern_matches(args.files_matching, rel):
                print(rel)
        return 0
    if not (root / ".claude" / "rules").is_dir():
        print(f"No rules directory under {root}", file=sys.stderr)
        return 1
    rules = load_rules(root)
    if rules and not rules[0].yaml_checked:
        print(
            "PyYAML not installed: YAML failures in rule frontmatter go undetected",
            file=sys.stderr,
        )

    if args.explain:
        _print_explain(root, rules, normalize_path(args.explain, root))
        return 0

    files = [normalize_path(path, root) for path in args.files]
    if args.changed:
        files.extend(_git_changed_files(root))
    files = sorted(set(files))

    always_on, path_matched = applicable(rules, files)

    if args.list:
        _print_list(root, always_on, path_matched)
        return 0

    if files:
        print("Matched files:")
        for file_path in files:
            print(f"- `{file_path}`")
        print()
    _print_markdown(root, always_on, path_matched)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
