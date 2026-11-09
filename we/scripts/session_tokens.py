#!/usr/bin/env python3
"""Appends this session's token use to a story plan's `## Updates Log`.

    session_tokens.py --plan <plan> --step refine

The line grammar is owned by `references/story-plan.md` § Updates Log lines:

    - 2026-11-03 refine tokens: in=12 out=34567 cache_read=1234567 cache_write=23456 models=m session=fbae4d4e
    - 2026-11-03 refine tokens: absent (no session transcript)

It measures only a session of its own: `.weside/config.json` → `agents.worker_launch` is a command
template (`references/worker-dispatch.md` § Worker launch backend). A subagent inherits the calling
session's `CLAUDE_CODE_SESSION_ID`, so summing that transcript would count the caller's whole
session; under `subagent` the line says `absent (subagent: no own session id)`.

Measured: the transcript `${CLAUDE_CONFIG_DIR:-~/.claude}/projects/*/<id>.jsonl` plus
`<id>/subagents/*.jsonl`, `message.usage` of `type == "assistant"` lines, each `message.id` counted
once (a streamed message repeats its usage on several lines). A line that is not JSON is skipped
and counted as `skipped=N`. Whatever goes wrong, the script exits 0 and the line says why: a value
nobody measured is written `absent (<reason>)`, never `0`. The report message after the line is not
counted.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import claude_home
from worker_launch import SUBAGENT, LaunchError, backend

HEADER = "## Updates Log"
USAGE_KEYS = (
    ("in", "input_tokens"),
    ("out", "output_tokens"),
    ("cache_read", "cache_read_input_tokens"),
    ("cache_write", "cache_creation_input_tokens"),
)
NOT_A_MODEL = {"<synthetic>"}


def transcripts(session_id: str, config_dir: Path) -> list[Path]:
    """The session's transcript files: the main one first, then its subagents."""
    projects = config_dir / "projects"
    main = sorted(projects.glob(f"*/{session_id}.jsonl"))
    subs = sorted(projects.glob(f"*/{session_id}/subagents/*.jsonl"))
    return main + subs


def measure(files: Iterable[Path]) -> tuple[dict[str, int], list[str], int, int]:
    """Summed usage, sorted models, skipped lines, counted messages; each `message.id` once."""
    totals = {key: 0 for key, _ in USAGE_KEYS}
    models = set()
    seen = set()
    skipped = 0
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            skipped += 1
            continue
        for raw in lines:
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except ValueError:
                skipped += 1
                continue
            if not isinstance(row, dict) or row.get("type") != "assistant":
                continue
            message = row.get("message")
            if not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
                continue
            mid = message.get("id")
            if mid is not None:
                if mid in seen:
                    continue
                seen.add(mid)
            usage = message["usage"]
            for key, field in USAGE_KEYS:
                value = usage.get(field)
                if isinstance(value, int):
                    totals[key] += value
            model = message.get("model")
            if isinstance(model, str) and model and model not in NOT_A_MODEL:
                models.add(model)
    return totals, sorted(models), skipped, len(seen)


def _absent(reason: str) -> str:
    # The reader takes the reason up to the first `)`.
    return "absent ({})".format(reason.replace("(", "[").replace(")", "]").strip())


def token_text(plan: Path, env: dict[str, str]) -> str:
    """The part after `tokens: ` for this session."""
    try:
        mode = backend(plan.resolve().parent)
    except LaunchError as exc:
        return _absent(f"worker_launch unreadable: {exc}")
    if mode == SUBAGENT:
        return _absent("subagent: no own session id")
    session_id = env.get("CLAUDE_CODE_SESSION_ID", "").strip()
    if not session_id:
        return _absent("no session id")
    config_dir = claude_home.config_dir(env)
    files = transcripts(session_id, config_dir)
    if not files:
        return _absent("no session transcript")
    totals, models, skipped, counted = measure(files)
    if counted == 0:
        suffix = f", skipped={skipped}" if skipped else ""
        return _absent(f"no assistant usage in transcript{suffix}")
    parts = [f"{key}={totals[key]}" for key, _ in USAGE_KEYS]
    if models:
        parts.append("models=" + ",".join(models))
    parts.append(f"session={session_id[:8]}")
    if skipped:
        parts.append(f"skipped={skipped}")
    return " ".join(parts)


def append_line(text: str, line: str) -> str:
    """`text` with `line` as the last item of `## Updates Log`, the section created at the end."""
    lines = text.splitlines()
    start = next((i for i, row in enumerate(lines) if row.strip() == HEADER), None)
    if start is None:
        body = text.rstrip("\n")
        return f"{body}\n\n{HEADER}\n\n{line}\n"
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    last = end - 1
    while last > start and not lines[last].strip():
        last -= 1
    if lines[last].lstrip().startswith("- "):
        insert = [line]
    else:
        insert = ["", line]
    tail = lines[last + 1 :]
    if tail and tail[0].strip():
        insert.append("")
    out = lines[: last + 1] + insert + tail
    return "\n".join(out) + "\n"


def run(plan: Path, step: str, env: dict[str, str], today: str | None = None) -> str:
    """Appends the line to `plan` and returns it."""
    date = today or datetime.datetime.now().astimezone().date().isoformat()
    line = f"- {date} {step} tokens: {token_text(plan, env)}"
    plan.write_text(append_line(plan.read_text(encoding="utf-8"), line), encoding="utf-8")
    return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--step", required=True, help="the step measured, e.g. refine")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", args.step):
        print(f"session_tokens: step {args.step!r} is not a lower-case word", file=sys.stderr)
        return 2
    try:
        print(run(args.plan, args.step, dict(os.environ)))
    except OSError as exc:
        print(f"session_tokens: {args.plan}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
