#!/usr/bin/env python3
"""Stop hook: Per-turn conversation storage as companion memory.

After each meaningful turn, store the last exchange directly
via the weside MCP endpoint.

Auth: Claude Code's own MCP OAuth token from ~/.claude/.credentials.json
(auto-refreshed by Claude Code at session start — always fresh while
a session with the we plugin is active).

Flow:
  1. Check if autoStoreConversations is enabled
  2. Read hook stdin (last_assistant_message, transcript_path, etc.)
  3. Extract last real user message from transcript JSONL
  4. Filter: skip short messages, commands, tool-only turns
  5. Resolve token (Claude Code MCP OAuth)
  6. Call weside MCP store_conversations directly via HTTP (JSON-RPC over SSE)

Warnings on auth failure are emitted to stderr so Silent-Fails become visible.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

MIN_USER_MSG_LENGTH = 50
MIN_TOTAL_LENGTH = 100
MAX_CONTENT_LENGTH = 500

MCP_URL = "https://api.weside.ai/mcp/"
CLAUDE_CODE_CREDENTIALS_PATH = os.path.expanduser("~/.claude/.credentials.json")
MCP_OAUTH_KEY_PREFIX = "plugin:we:weside-mcp|"


def _warn(msg: str) -> None:
    """Emit a visible warning to stderr (surfaces silent auth failures)."""
    with contextlib.suppress(Exception):
        print(f"weside store_conversation_hook: {msg}", file=sys.stderr)


def _decode_jwt_exp(token: str) -> int | None:
    """Extract expiry timestamp from JWT without verification."""
    try:
        payload = token.split(".")[1]
        # Fix base64 padding
        payload += "=" * (4 - len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data.get("exp")
    except Exception:
        return None


def _get_valid_token() -> str | None:
    """Read the weside MCP OAuth access token managed by Claude Code itself.

    Claude Code stores per-MCP OAuth tokens in ~/.claude/.credentials.json under
    ``mcpOAuth['plugin:we:weside-mcp|<hash>']`` and auto-refreshes them when
    reconnecting to the MCP server at session start. Reading from here means the
    hook piggy-backs on Claude Code's own refresh loop instead of maintaining a
    second one.
    """
    try:
        with open(CLAUDE_CODE_CREDENTIALS_PATH) as f:
            data = json.load(f)
    except Exception:
        return None

    for key, entry in data.get("mcpOAuth", {}).items():
        if not isinstance(entry, dict) or not key.startswith(MCP_OAUTH_KEY_PREFIX):
            continue
        token = entry.get("accessToken")
        if not token:
            continue
        exp = _decode_jwt_exp(token)
        if exp and exp > time.time() + 60:
            return token
    return None


def _derive_repo_id(cwd: str) -> str:
    """Derive a stable repo identifier for the claude_code channel.

    Derivation order (first non-empty result wins):
    1. `.weside/config.json` top-level ``"repo_id"`` string field.
    2. ``git remote get-url origin`` normalised to ``<host>/<org>/<repo>``
       (strips the protocol prefix and a trailing ``.git``).
    3. ``os.path.basename(cwd)`` — the repo directory name.

    The backend keys the claude_code channel on
    ``channel_context_id = "group_claude_code_{repo_id}"``, so this value
    must be identical to what the council skill derives for the same repo.
    """
    # 1. .weside/config.json repo_id field
    with contextlib.suppress(Exception):
        config_path = os.path.join(cwd, ".weside", "config.json")
        with open(config_path) as f:
            cfg = json.load(f)
        rid = cfg.get("repo_id", "")
        if isinstance(rid, str) and rid.strip():
            return rid.strip()

    # 2. git origin remote URL → normalise to host/org/repo
    with contextlib.suppress(Exception):
        result = subprocess.run(
            ["git", "-C", cwd, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        url = result.stdout.strip()
        if url:
            # Strip trailing .git
            if url.endswith(".git"):
                url = url[:-4]
            # SSH: git@github.com:org/repo → github.com/org/repo
            if url.startswith("git@"):
                url = url[4:].replace(":", "/", 1)
            # HTTPS/HTTP: https://github.com/org/repo → github.com/org/repo
            elif "://" in url:
                url = url.split("://", 1)[1]
            if url:
                return url

    # 3. Fallback: directory name
    return os.path.basename(cwd) or "unknown"


def _derive_session_tag(transcript_path: str) -> str | None:
    """Derive a short session tag from a Claude Code transcript path."""
    with contextlib.suppress(Exception):
        filename = os.path.basename(transcript_path)
        stem, extension = os.path.splitext(filename)
        tag = stem[:8]
        if (
            extension == ".jsonl"
            and len(tag) == 8
            and all(char in "0123456789abcdefABCDEF" for char in tag)
        ):
            return tag
    return None


def _call_store_conversations(
    token: str,
    conversations: list[dict],
    source: str,
    source_detail: str,
    companion_name: str | None = None,
    repo_id: str | None = None,
) -> bool:
    """Call store_conversations via MCP JSON-RPC endpoint.

    companion_name pins memory writes to the configured companion for this
    session. Without it, routing falls back to backend defaults.
    """
    url = MCP_URL
    if companion_name:
        url = f"{MCP_URL}?companion={urllib.parse.quote(companion_name)}"

    arguments: dict = {
        "conversations": json.dumps(conversations),
        "source": source,
        "source_detail": source_detail,
    }
    if repo_id:
        arguments["repo_id"] = repo_id

    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "hook-store",
            "method": "tools/call",
            "params": {
                "name": "store_conversations",
                "arguments": arguments,
            },
        }
    ).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            # SSE format: "event: message\ndata: {...}"
            for line in body.splitlines():
                if line.startswith("data: "):
                    result = json.loads(line[6:])
                    return not result.get("result", {}).get("isError", True)
            return False
    except Exception:
        return False


def get_plugin_config() -> dict:
    """Read plugin config from Claude settings."""
    try:
        path = os.path.expanduser("~/.claude/settings.json")
        with open(path) as f:
            settings = json.load(f)
        return settings.get("pluginConfigs", {}).get("we@weside-ai", {}).get("options", {})
    except Exception:
        return {}


def _is_human_message(text: str) -> bool:
    """Check if a user message is actual human input (not system/command noise).

    Claude Code injects many non-human messages as type="user" in the transcript:
    - <command-name> — slash command invocations (/reload-plugins, /exit, etc.)
    - <local-command-caveat> — warnings about local command output
    - <local-command-stdout> — command stdout captures
    - <system-reminder> — system context injections (skills list, rules, etc.)
    - [Request interrupted — user cancelled mid-response

    Only actual human-typed messages should be stored as conversation memories.
    """
    noise_prefixes = (
        "<command-name>",
        "<local-command-",
        "<system-reminder>",
        "[Request interrupted",
    )
    return not any(text.startswith(p) for p in noise_prefixes)


def get_last_user_message(transcript_path: str) -> str | None:
    """Extract the last real human message from the transcript JSONL.

    Walks backwards through the transcript, skipping:
    - Tool results (toolUseResult entries)
    - System injections (<system-reminder>, <command-name>, etc.)
    - Interrupts ([Request interrupted])
    """
    try:
        with open(transcript_path) as f:
            lines = f.readlines()
    except Exception:
        return None

    for line in reversed(lines):
        try:
            entry = json.loads(line.strip())
        except (json.JSONDecodeError, ValueError):
            continue

        if entry.get("type") != "user":
            continue

        # Skip tool results
        if entry.get("toolUseResult"):
            continue

        msg = entry.get("message", {})
        content = msg.get("content", "")

        text = None
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, list):
            texts = [
                c.get("text", "")
                for c in content
                if isinstance(c, dict) and c.get("type") == "text"
            ]
            if texts:
                text = " ".join(texts).strip()

        # Skip system/command noise — only store real human input
        if text and _is_human_message(text):
            return text

    return None


def is_worth_storing(user_msg: str, assistant_msg: str) -> bool:
    """Filter out exchanges that aren't worth storing."""
    if len(user_msg) < MIN_USER_MSG_LENGTH:
        return False

    if len(user_msg) + len(assistant_msg) < MIN_TOTAL_LENGTH:
        return False

    # Skip CLI commands and slash commands
    technical_prefixes = (
        "/reload",
        "/exit",
        "/help",
        "/clear",
        "/plugin",
        "/mcp",
        "/tasks",
        "git ",
        "ls ",
        "cd ",
        "cat ",
    )
    lower = user_msg.lower().strip()
    return not any(lower.startswith(p) for p in technical_prefixes)


def condense(text: str, max_chars: int = MAX_CONTENT_LENGTH) -> str:
    """Truncate text, keeping meaningful content."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."


def main() -> None:
    # 1. Check plugin config
    config = get_plugin_config()
    if not config.get("autoStoreConversations", False):
        return

    # 2. Read hook stdin
    try:
        hook_input = json.loads(sys.stdin.read())
    except Exception:
        return

    # 3. Get the exchange
    assistant_msg = hook_input.get("last_assistant_message", "")
    transcript_path = hook_input.get("transcript_path", "")
    user_msg = get_last_user_message(transcript_path) if transcript_path else None

    if not user_msg or not assistant_msg:
        return

    # 4. Filter
    if not is_worth_storing(user_msg, assistant_msg):
        return

    # 5. Resolve token (Claude Code MCP OAuth, auto-refreshed by Claude Code)
    token = _get_valid_token()
    if not token:
        _warn(
            "no valid MCP OAuth token in ~/.claude/.credentials.json. "
            "Reconnect the we MCP server (e.g. /mcp) — this turn was NOT "
            "stored as memory."
        )
        return

    # 6. Store directly via MCP
    # Pass companion_name to pin routing to the configured companion.
    companion_name = config.get("companion") or None
    cwd = hook_input.get("cwd", os.getcwd())
    project = os.path.basename(cwd)
    source_detail = (
        f"{project}#{tag}" if (tag := _derive_session_tag(transcript_path)) else project
    )
    repo_id = _derive_repo_id(cwd)
    exchange = [
        {
            "user_message": condense(user_msg),
            "assistant_response": condense(assistant_msg),
        }
    ]

    ok = _call_store_conversations(
        token, exchange, "claude_code", source_detail, companion_name, repo_id
    )
    if not ok:
        _warn("store_conversations call failed — this turn was NOT stored as memory.")


if __name__ == "__main__":
    main()
