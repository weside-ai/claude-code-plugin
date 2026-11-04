#!/usr/bin/env python3
"""The cold reader of `board.py ask`: one `claude -p` run that sees only the question.

`read(question, timeout=90)` starts `claude -p` in an empty temporary directory, with the body of
`templates/cold-reader.md` as the system prompt and that file's `model` and `effort` (a template,
not a listed agent: it costs the session listing nothing), no tools,
no session file, no MCP server (`--strict-mcp-config` with an empty config), no user, project or
local settings (`--setting-sources ""`, so no hooks and no plugins from them), hooks off and no
plugins enabled through `--settings`, and no slash commands. It runs without `CLAUDE_CONFIG_DIR`
(the global login, never a pinned profile) and without a companion pin. The question goes on stdin
as one JSON object (`ask`, `recommendation`, `key_title`, `question_label`,
`recommendation_label`); nothing from the board or a transcript goes in.

It returns the last JSON object of the reader's output (`decides`, `on_yes`, `form`). A reader that
cannot run raises `ReaderError` naming the cause: no `claude`, a non-zero exit, the timeout, or no
parseable answer. What is still not cold: managed (policy) settings and the instruction files Claude
Code always loads apply to the child too; it judges understandability, not truth.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from lens_verdict import RefusedError, parse_answer  # noqa: E402

AGENT = Path(__file__).resolve().parent.parent / "templates" / "cold-reader.md"
TIMEOUT_S = 90
QUESTION_KEYS = ("ask", "recommendation", "key_title", "question_label", "recommendation_label")
STRIPPED_ENV = ("CLAUDE_CONFIG_DIR", "WESIDE_COMPANION")
SETTINGS = {"disableAllHooks": True, "enabledPlugins": {}}


class ReaderError(Exception):
    """The reader could not give a verdict; the message names the cause."""


def agent_parts(path: Path = AGENT) -> tuple[dict, str]:
    """(frontmatter scalars, body) of the reader's agent file."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ReaderError(f"{path.name}: no frontmatter")
    head, _, body = text[4:].partition("\n---\n")
    meta = {}
    for line in head.splitlines():
        key, sep, value = line.partition(":")
        if sep and not line.startswith(" "):
            meta[key.strip()] = value.strip()
    return meta, body.lstrip("\n")


def argv(meta: dict, tmp: Path) -> list[str]:
    return [
        "claude",
        "-p",
        "--model",
        meta["model"],
        "--effort",
        meta["effort"],
        "--system-prompt-file",
        str(tmp / "reader.md"),
        "--tools",
        "",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--mcp-config",
        str(tmp / "mcp.json"),
        "--setting-sources",
        "",
        "--settings",
        str(tmp / "settings.json"),
        "--disable-slash-commands",
        "--output-format",
        "text",
    ]


def read(question: dict, timeout: float | None = None) -> dict:
    timeout = TIMEOUT_S if timeout is None else timeout
    missing = [k for k in QUESTION_KEYS if k not in question]
    if missing:
        raise ValueError(f"question lacks {', '.join(missing)}")
    meta, body = agent_parts()
    for key in ("model", "effort"):
        if not meta.get(key):
            raise ReaderError(f"{AGENT.name}: no {key} in the frontmatter")
    env = {k: v for k, v in os.environ.items() if k not in STRIPPED_ENV}
    payload = json.dumps({k: question[k] for k in QUESTION_KEYS}, ensure_ascii=False)
    with tempfile.TemporaryDirectory(prefix="cold-reader-") as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "reader.md").write_text(body, encoding="utf-8")
        (tmp / "mcp.json").write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
        (tmp / "settings.json").write_text(json.dumps(SETTINGS), encoding="utf-8")
        cwd = tmp / "cwd"
        cwd.mkdir()
        try:
            out = subprocess.run(
                argv(meta, tmp),
                input=payload,
                capture_output=True,
                text=True,
                cwd=str(cwd),
                env=env,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            raise ReaderError("no claude on PATH") from None
        except subprocess.TimeoutExpired:
            raise ReaderError(f"timeout after {timeout:g} s") from None
    if out.returncode != 0:
        tail = (out.stderr.strip().splitlines() or [""])[-1]
        raise ReaderError(f"claude -p exited {out.returncode}: {tail}".rstrip(": "))
    try:
        return parse_answer(out.stdout)
    except RefusedError:
        raise ReaderError("no parseable answer") from None
