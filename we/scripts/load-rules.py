#!/usr/bin/env python3
"""Print the `.claude/rules` guidance that applies to a set of files.

Claude Code loads these rules by itself. Every other agent — Codex, Gemini, a
foreign engine in a worker — does not, and a rule nobody loads governs nothing.
This script is that bridge, and it belongs to no single repo: the rules
directory is found from the git root, not from the script's own location.

A rule with no `paths:` key in its frontmatter is always-on. A rule with
`paths:` applies when one of the given files matches one of its globs.

Modes:
  (none)            the full Markdown bundle: every applicable rule, in full
  --list            one `always|matched <path>` line per rule, nothing else
  --explain <path>  why each rule does or does not apply to that one file
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class Rule:
    path: Path
    description: str | None
    patterns: tuple[str, ...]
    defect: str | None

    @property
    def is_always_on(self) -> bool:
        return not self.patterns


def _repo_root(explicit: str | None) -> Path:
    """The repo the rules belong to: --root, else the git root, else cwd.

    A worktree answers with its own path, which is what a worker in one needs;
    `parents[N]` from the script's location would answer with the plugin cache.
    """
    if explicit:
        return Path(explicit).resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return Path.cwd().resolve()


def _parse_frontmatter(text: str) -> tuple[dict[str, object], str | None]:
    """(frontmatter, defect). A file that opens `---` and never closes it is a
    defect, never a silent 'no paths key, therefore always-on'."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return {}, None

    end = None
    for index, line in enumerate(lines[1:], start=1):
        if line == "---":
            end = index
            break

    if end is None:
        return {}, "unterminated frontmatter — treated as always-on"

    frontmatter: dict[str, object] = {}
    current_key: str | None = None
    for raw_line in lines[1:end]:
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        if not raw_line.startswith((" ", "\t")) and ":" in line:
            key, value = line.split(":", 1)
            current_key = key.strip()
            value = value.strip()
            frontmatter[current_key] = value.strip("\"'") if value else []
            continue

        if current_key and isinstance(frontmatter.get(current_key), list):
            stripped = line.strip()
            if stripped.startswith("- "):
                frontmatter[current_key].append(stripped[2:].strip().strip("\"'"))

    return frontmatter, None


def _load_rule(path: Path) -> Rule:
    frontmatter, defect = _parse_frontmatter(path.read_text(encoding="utf-8"))
    raw_paths = frontmatter.get("paths", [])
    patterns = tuple(str(item) for item in raw_paths) if isinstance(raw_paths, list) else ()
    description = frontmatter.get("description")
    if "globs" in frontmatter and "paths" not in frontmatter:
        defect = defect or "`globs:` is not `paths:` — this rule loads always"
    return Rule(
        path=path,
        description=str(description) if description else None,
        patterns=patterns,
        defect=defect,
    )


def _git_changed_files(root: Path) -> list[str]:
    commands = [
        ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    paths: list[str] = []
    for command in commands:
        result = subprocess.run(
            command,
            cwd=root,
            check=False,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            continue
        paths.extend(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(set(paths))


def _normalize_path(path: str, root: Path) -> str:
    """Repo-relative, the form `paths:` globs are written in.

    A relative argument is resolved against the CURRENT directory, not the root:
    somebody standing in `apps/backend` and typing `app/main.py` means that file,
    and reading it as repo-relative would silently match no rule at all.
    """
    candidate = Path(path)
    absolute = candidate if candidate.is_absolute() else (Path.cwd() / candidate)
    try:
        return absolute.resolve().relative_to(root).as_posix()
    except ValueError:
        return candidate.as_posix().lstrip("./")


def _match_reason(pattern: str, path: str) -> str | None:
    posix_path = PurePosixPath(path)
    if posix_path.match(pattern):
        return "glob"
    if fnmatch.fnmatchcase(path, pattern):
        return "fnmatch"

    # `dir/**/*.ext` means "zero or more directories below dir" — a flat file
    # directly in `dir` matches too, which neither matcher above grants.
    if "/**/" in pattern:
        flat = pattern.replace("/**/", "/")
        if posix_path.match(flat) or fnmatch.fnmatchcase(path, flat):
            return "globstar-zero-dirs"
    return None


def _matches(pattern: str, path: str) -> bool:
    return _match_reason(pattern, path) is not None


def _split(rules: list[Rule], files: list[str]) -> tuple[list[Rule], list[Rule]]:
    always_on = [rule for rule in rules if rule.is_always_on]
    path_matched = [
        rule
        for rule in rules
        if not rule.is_always_on
        and any(_matches(pattern, file_path) for pattern in rule.patterns for file_path in files)
    ]
    return always_on, path_matched


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
    for rule in sorted(rules, key=lambda item: item.path.as_posix()):
        rel_path = rule.path.relative_to(root).as_posix()
        if rule.defect:
            print(f"- `{rel_path}` — **defect**: {rule.defect}")
            continue
        if rule.is_always_on:
            print(f"- `{rel_path}` — **always-on** (no `paths:` key)")
            continue
        hits = [
            f"`{pattern}` ({reason})"
            for pattern in rule.patterns
            if (reason := _match_reason(pattern, target)) is not None
        ]
        if hits:
            print(f"- `{rel_path}` — **matched** by {', '.join(hits)}")
        else:
            print(f"- `{rel_path}` — no match ({len(rule.patterns)} patterns tried)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="Files to match against.")
    parser.add_argument("--root", help="Repo root; default is the git root.")
    parser.add_argument(
        "--changed", action="store_true", help="Use changed and untracked git files."
    )
    parser.add_argument("--list", action="store_true", help="Only print matching rule paths.")
    parser.add_argument("--explain", help="Explain the verdict for one path.")
    args = parser.parse_args()

    root = _repo_root(args.root)
    rules_dir = root / ".claude" / "rules"
    if not rules_dir.exists():
        print(f"No rules directory under {root}", file=sys.stderr)
        return 1

    rules = sorted(
        (_load_rule(path) for path in rules_dir.rglob("*.md")),
        key=lambda rule: rule.path.as_posix(),
    )

    if args.explain:
        _print_explain(root, rules, _normalize_path(args.explain, root))
        return 0

    files = [_normalize_path(path, root) for path in args.files]
    if args.changed:
        files.extend(_git_changed_files(root))
    files = sorted(set(files))

    always_on, path_matched = _split(rules, files)

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
