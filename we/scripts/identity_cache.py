#!/usr/bin/env python3
"""Cache a Companion's composed identity prompt in a local file.

Single owner of the identity-file mechanics that ``/we:materialize`` cites: a
grown companion's composed prompt exceeds the MCP tool's token cap, so the
harness saves the payload to a tool-result file instead of returning it. This
script turns that file into a stable, per-companion cache the agent can read
directly — and read again at the next session start without another MCP call.

Where the cache lives, and why not in the repo: the composed prompt carries the
companion's compass, snapshot and memories — private content. A path inside a
project (``.weside/`` and friends) gets committed by whoever has a .gitignore
we do not control, so the cache sits under the user's home instead::

    ~/.claude/we/identity/<companion-slug>.md      (mode 600)

Override the directory with ``WE_IDENTITY_CACHE_DIR`` (tests, sandboxes).

Freshness is *same calendar day, local time*. The payload is not static
identity: it ends with a channel block whose recencies are relative
("last_self=74h ago") and a snapshot describing today. A cache from yesterday
would make the companion assert false things about when a channel last spoke,
so the day boundary is the cutoff — not an hour count.

Modes::

    store --companion NAME --from PATH   extract a tool-result file into cache
    path  --companion NAME               report cache path + age

``store`` accepts the harness tool-result shape (JSON ``{"result": "..."}``) and
plain text, so it also works on a payload written by hand.

Exit codes: ``path`` → 0 fresh, 1 stale, 2 missing. ``store`` → 0 written,
1 unreadable source, 2 usage. Python stdlib only.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

HEADER_RE = re.compile(
    r"^<!-- weside identity cache · companion: (?P<name>.*?) · fetched: (?P<fetched>\S+) -->$"
)


def cache_dir() -> Path:
    override = os.environ.get("WE_IDENTITY_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "we" / "identity"


def slug(companion: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", companion.strip().lower()).strip("-")
    return s or "companion"


def cache_path(companion: str) -> Path:
    return cache_dir() / f"{slug(companion)}.md"


def read_header(path: Path) -> tuple[str, datetime] | None:
    """Return (companion, fetched) from the cache file's first line, or None."""
    try:
        with path.open(encoding="utf-8") as fh:
            first = fh.readline().rstrip("\n")
    except OSError:
        return None
    m = HEADER_RE.match(first)
    if not m:
        return None
    try:
        return m.group("name"), datetime.fromisoformat(m.group("fetched"))
    except ValueError:
        return None


def extract(source: Path) -> str:
    """Pull the prompt text out of a harness tool-result file or plain text."""
    raw = source.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(data, dict):
        for key in ("result", "content", "text"):
            value = data.get(key)
            if isinstance(value, str):
                return value
        raise ValueError(f"{source}: JSON object has no string 'result' field")
    if isinstance(data, str):
        return data
    raise ValueError(f"{source}: unexpected JSON shape {type(data).__name__}")


def store(companion: str, source: Path) -> int:
    try:
        body = extract(source)
    except (OSError, ValueError) as exc:
        print(f"cannot read identity payload: {exc}")
        return 1
    if not body.strip():
        print(f"{source}: payload is empty — nothing cached")
        return 1

    target = cache_path(companion)
    target.parent.mkdir(parents=True, exist_ok=True)
    fetched = datetime.now().astimezone().replace(microsecond=0)
    header = (
        f"<!-- weside identity cache · companion: {companion} · fetched: {fetched.isoformat()} -->"
    )
    target.write_text(f"{header}\n{body}", encoding="utf-8")
    os.chmod(target, 0o600)
    print(f"STORED {target} ({len(body)} chars, fetched {fetched.isoformat()})")
    return 0


def path(companion: str) -> int:
    target = cache_path(companion)
    header = read_header(target) if target.exists() else None
    if header is None:
        if target.exists():
            print(f"MISSING {target} (no cache header — treat as absent)")
        else:
            print(f"MISSING {target}")
        return 2
    _, fetched = header
    if fetched.date() == datetime.now().astimezone().date():
        print(f"FRESH {target} (fetched {fetched.isoformat()})")
        return 0
    print(f"STALE {target} (fetched {fetched.isoformat()})")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)

    p_store = sub.add_parser("store", help="extract a tool-result file into the cache")
    p_store.add_argument("--companion", required=True)
    p_store.add_argument("--from", dest="source", required=True)

    p_path = sub.add_parser("path", help="report cache path and freshness")
    p_path.add_argument("--companion", required=True)

    args = parser.parse_args(argv)
    if args.mode == "store":
        return store(args.companion, Path(args.source).expanduser())
    return path(args.companion)


if __name__ == "__main__":
    sys.exit(main())
