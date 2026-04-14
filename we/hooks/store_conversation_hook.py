#!/usr/bin/env python3
"""Stop hook: Per-turn conversation storage as companion memory.

After each meaningful turn, store the last exchange directly
via the weside MCP endpoint.

Auth (in priority order):
  1. Claude Code's own MCP OAuth token from ~/.claude/.credentials.json
     (auto-refreshed by Claude Code at session start — always fresh while
     a session with the we plugin is active).
  2. Fallback: ~/.weside/credentials.json (weside Go CLI credentials,
     for users who have the CLI but not the plugin). Auto-refreshes via
     Supabase refresh_token endpoint.

Flow:
  1. Check if autoStoreConversations is enabled
  2. Read hook stdin (last_assistant_message, transcript_path, etc.)
  3. Extract last real user message from transcript JSONL
  4. Filter: skip short messages, commands, tool-only turns
  5. Resolve token (Claude Code MCP OAuth → CLI credentials fallback)
  6. Call weside MCP store_conversations directly via HTTP (JSON-RPC over SSE)

Warnings on auth failure are emitted to stderr so Silent-Fails become visible.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request

MIN_USER_MSG_LENGTH = 50
MIN_TOTAL_LENGTH = 100
MAX_CONTENT_LENGTH = 500

SUPABASE_URL = "https://pqykrwpmhjqjhpsnjxbd.supabase.co"
MCP_URL = "https://api.weside.ai/mcp/"
CREDENTIALS_PATH = os.path.expanduser("~/.weside/credentials.json")
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


def _load_credentials() -> dict | None:
    """Load tokens from CLI credentials file."""
    try:
        with open(CREDENTIALS_PATH) as f:
            return json.load(f)
    except Exception:
        return None


def _save_credentials(creds: dict) -> None:
    """Save updated tokens back to CLI credentials file."""
    try:
        os.makedirs(os.path.dirname(CREDENTIALS_PATH), mode=0o700, exist_ok=True)
        with open(CREDENTIALS_PATH, "w") as f:
            json.dump(creds, f, indent=2)
        os.chmod(CREDENTIALS_PATH, 0o600)
    except Exception:
        pass


def _refresh_token(refresh_token: str) -> dict | None:
    """Refresh access token via Supabase (same as Go CLI — no anon key needed)."""
    data = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    ).encode()

    req = urllib.request.Request(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _load_claude_code_mcp_token() -> str | None:
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


def _get_valid_token() -> str | None:
    """Resolve a valid access token.

    Priority:
      1. Claude Code's MCP OAuth token (auto-refreshed by Claude Code)
      2. weside CLI credentials file (auto-refreshed via Supabase here)
    """
    # 1. Primary: Claude Code's own MCP OAuth token
    token = _load_claude_code_mcp_token()
    if token:
        return token

    # 2. Fallback: weside CLI credentials file
    creds = _load_credentials()
    if not creds or not creds.get("access_token"):
        return None

    token = creds["access_token"]
    exp = _decode_jwt_exp(token)

    # Token still valid (with 60s buffer)
    if exp and exp > time.time() + 60:
        return token

    # Try refresh
    refresh = creds.get("refresh_token")
    if not refresh:
        return None

    result = _refresh_token(refresh)
    if not result or not result.get("access_token"):
        return None

    # Save refreshed tokens
    creds["access_token"] = result["access_token"]
    if result.get("refresh_token"):
        creds["refresh_token"] = result["refresh_token"]
    _save_credentials(creds)

    return result["access_token"]


def _call_store_conversations(
    token: str,
    conversations: list[dict],
    source: str,
    source_detail: str,
) -> bool:
    """Call store_conversations via MCP JSON-RPC endpoint."""
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "hook-store",
            "method": "tools/call",
            "params": {
                "name": "store_conversations",
                "arguments": {
                    "conversations": json.dumps(conversations),
                    "source": source,
                    "source_detail": source_detail,
                },
            },
        }
    ).encode()

    req = urllib.request.Request(
        MCP_URL,
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

    # 5. Resolve token (Claude Code MCP OAuth → CLI credentials fallback)
    token = _get_valid_token()
    if not token:
        _warn(
            "no valid token (checked ~/.claude/.credentials.json mcpOAuth and "
            "~/.weside/credentials.json). Run `weside auth login` or reconnect "
            "the we MCP server — this turn was NOT stored as memory."
        )
        return

    # 6. Store directly via MCP
    project = os.path.basename(hook_input.get("cwd", os.getcwd()))
    exchange = [
        {
            "user_message": condense(user_msg),
            "assistant_response": condense(assistant_msg),
        }
    ]

    ok = _call_store_conversations(token, exchange, "claude_code", project)
    if not ok:
        _warn("store_conversations call failed — this turn was NOT stored as memory.")


if __name__ == "__main__":
    main()
