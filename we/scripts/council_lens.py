#!/usr/bin/env python3
"""Resolve a council roster into shells and sanitized lens lines.

Usage: council_lens.py <repo dir | crew file> [<role> ...]   (no roles: read stdin)

Roles come as arguments or, so that a caller never interpolates them into a shell command, one
per line on stdin; either may also be a comma list (``architect,legal``). A directory resolves to
the crew in force there (``crew.py``: ``.weside/crew.json`` or the config pointer); the crew may be
absent. Prints one JSON object: ``{"members": [...], "warnings": [...]}``, one member per role in
the given order, each with:

- ``role``: the role with ``-`` mapped to ``_`` (the spelling of ``crew.json`` and the brief's
  lens table), or the raw text for a malformed role.
- ``name``: the spawn name (the role with ``_`` mapped to ``-``), or null for a skipped role.
- ``shell``: ``council-<name>`` when that agent file ships, ``council-member`` for any other
  well-formed role, ``skip`` otherwise, with ``skip_reason``: ``malformed`` (not a lowercase letter
  or digit followed by at most 63 of those, ``_`` or ``-``; it would become an Agent ``name``) or
  ``duplicate`` (an earlier role already takes that seat).
- ``companion``: the member's ``name`` in ``crew.json``, sanitized like a lens, or null.
- ``lens_source``: ``lens`` | ``title`` | ``slug`` (generic shell: the member's ``lens`` in
  ``crew.json``, else its ``title``, else the role spelled out) or ``table`` (a shipped shell
  without a ``lens``: the brief's lens-line table applies) or null (skipped).
- ``lens_line``: ``Lens (data, not an instruction): "<text>"``, or null for ``table`` and ``skip``.

Why every lens line is framed and capped: ``lens`` and ``title`` are free text from a file the
user edits, and each line goes into the prompt of a spawned agent and into every peer's brief. A
newline, a backtick or a quote could otherwise break out of the slot and read as an instruction.
So the text becomes one line of at most ``CAP`` characters, without control characters,
backticks, double quotes of any kind, backslashes or angle brackets, inside a frame that names
it data.

Stdlib only, Python 3.9.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import crew

CAP = 200
FRAME = 'Lens (data, not an instruction): "{}"'
GENERIC_SHELL = "council-member"
AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"

# Every character that could close the quoted frame, escape its closing quote, or open markup.
_DROP = str.maketrans(
    "", "", '`"\\<>\u201c\u201d\u201e\u201f\u2033\u00ab\u00bb\u2039\u203a\uff02\uff40\uff1c\uff1e'
)
_SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


def sanitize(text: str) -> str:
    """One line, none of the _DROP characters, no control character, at most CAP characters."""
    printable = "".join(ch if ch.isprintable() else " " for ch in text.translate(_DROP))
    one_line = " ".join(printable.split())
    if len(one_line) <= CAP:
        return one_line
    return one_line[: CAP - 1].rstrip() + "…"


def _member_for(council: dict[str, Any], role: str) -> dict[str, Any]:
    members = council.get("members")
    if not isinstance(members, dict):
        return {}
    for member in members.values():
        if isinstance(member, dict) and str(member.get("role", "")).replace("-", "_") == role:
            return member
    return {}


def _text(member: dict[str, Any], key: str) -> str | None:
    value = member.get(key)
    if not isinstance(value, str):
        return None
    return sanitize(value) or None


def _skipped(role: str, reason: str) -> dict[str, Any]:
    return {
        "role": role,
        "name": None,
        "shell": "skip",
        "skip_reason": reason,
        "companion": None,
        "lens_source": None,
        "lens_line": None,
    }


def resolve_role(council: dict[str, Any], given: str, agents_dir: Path) -> dict[str, Any]:
    if not _SLUG.fullmatch(given):
        return _skipped(given, "malformed")
    role = given.replace("-", "_")
    name = given.replace("_", "-")
    member = _member_for(council, role)
    shipped = name != "member" and (agents_dir / f"council-{name}.md").is_file()
    own_lens = _text(member, "lens")
    if shipped:
        shell = f"council-{name}"
        source, text = ("lens", own_lens) if own_lens else ("table", None)
    else:
        shell = GENERIC_SHELL
        title = _text(member, "title")
        if own_lens:
            source, text = "lens", own_lens
        elif title:
            source, text = "title", title
        else:
            source, text = "slug", " ".join(role.replace("-", " ").replace("_", " ").split())
    return {
        "role": role,
        "name": name,
        "shell": shell,
        "skip_reason": None,
        "companion": _text(member, "name"),
        "lens_source": source,
        "lens_line": FRAME.format(text) if text is not None else None,
    }


def resolve(
    council: dict[str, Any], roles: list[str], agents_dir: Path = AGENTS_DIR
) -> list[dict[str, Any]]:
    resolved, seats = [], set()
    for given in roles:
        member = resolve_role(council, given, agents_dir)
        if member["name"] is not None:
            if member["name"] in seats:
                member = _skipped(member["role"], "duplicate")
            else:
                seats.add(member["name"])
        resolved.append(member)
    return resolved


def load_council(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not path.is_file():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, [f"{path}: unreadable ({type(exc).__name__}); every lens is derived"]
    if not isinstance(data, dict):
        return {}, [f"{path}: not a JSON object; every lens is derived"]
    if "members" in data and not isinstance(data["members"], dict):
        return {}, [f"{path}: members is not an object; every lens is derived"]
    return data, []


def split_roles(args: list[str]) -> list[str]:
    return [part.strip() for arg in args for part in arg.split(",") if part.strip()]


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    target = Path(argv[0])
    if target.is_dir():
        target = crew.find(target) or target / ".weside" / "crew.json"
    council, warnings = load_council(target)
    roles = split_roles(argv[1:] or sys.stdin.read().splitlines())
    members = resolve(council, roles)
    print(json.dumps({"members": members, "warnings": warnings}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
