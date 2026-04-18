#!/usr/bin/env python3
"""Validate YAML frontmatter in plugin Markdown files.

Checks that skills, commands, and agents have required frontmatter fields.
Uses regex parsing — no PyYAML dependency needed.

Usage:
    python3 scripts/validate-frontmatter.py we/skills/*/SKILL.md we/commands/*.md we/agents/*.md
"""

import re
import sys
from pathlib import Path

# Required fields by directory pattern
REQUIRED_FIELDS: dict[str, list[str]] = {
    "skills": ["name", "description"],
    "commands": ["description"],
    "agents": ["name", "description"],
}


def extract_frontmatter(content: str) -> dict[str, str] | None:
    """Extract YAML frontmatter fields from markdown content."""
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None

    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        kv = re.match(r"^(\w[\w-]*)\s*:\s*(.+)?", line)
        if kv:
            fields[kv.group(1)] = (kv.group(2) or "").strip()
    return fields


def get_category(filepath: str) -> str | None:
    """Determine the category (skills/commands/agents) from file path."""
    for category in REQUIRED_FIELDS:
        if f"/{category}/" in filepath or f"\\{category}\\" in filepath:
            return category
    return None


DOC_FILENAMES = {"CLAUDE.md", "README.md"}


def validate_file(filepath: str) -> list[str]:
    """Validate a single file's frontmatter. Returns list of error messages."""
    errors: list[str] = []
    path = Path(filepath)

    if not path.exists():
        return [f"{filepath}: file not found"]

    if path.name in DOC_FILENAMES:
        return []  # Documentation files, not skills/commands/agents

    content = path.read_text(encoding="utf-8")
    category = get_category(filepath)

    if not category:
        return []  # Not in a category we validate

    fields = extract_frontmatter(content)
    if fields is None:
        return [f"{filepath}: missing YAML frontmatter (no --- delimiters)"]

    required = REQUIRED_FIELDS[category]
    for field in required:
        if field not in fields or not fields[field]:
            errors.append(f"{filepath}: missing required field '{field}'")

    return errors


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: validate-frontmatter.py <file> [<file> ...]", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    for filepath in sys.argv[1:]:
        all_errors.extend(validate_file(filepath))

    if all_errors:
        for error in all_errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
