"""Refresh weside MCP OAuth token if near expiry.

Workaround for Claude Code not auto-refreshing MCP OAuth tokens
(anthropics/claude-code#28262). Runs as SessionStart hook — checks
if the weside-mcp access token expires within 1 hour and refreshes
it using the stored refresh_token via Supabase's OAuth token endpoint.

Silent on success/skip. Prints nothing (no ">>> Hook says:" noise).
"""

import json
import os
import time
import urllib.error
import urllib.request

CREDENTIALS_PATH = os.path.expanduser("~/.claude/.credentials.json")
SUPABASE_URL = "https://pqykrwpmhjqjhpsnjxbd.supabase.co"
CLIENT_ID = "9114483b-1a59-460d-afa0-2534fd3bd1aa"
# Supabase anon key — this is a PUBLIC key, safe to embed in client code.
# See: https://supabase.com/docs/guides/api/api-keys
ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBxeWtyd3BtaGpxamhwc25qeGJkIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3Njk5ODU3NDksImV4cCI6MjA4NTU2MTc0OX0."
    "ADx_HD7O-xNMx-j4MDrhaJbRO71R-hJO6yTcf5wFWUA"
)
REFRESH_THRESHOLD_MS = 3600 * 1000  # 1 hour


def _find_weside_entry(creds: dict) -> dict | None:
    """Find the weside-mcp entry in mcpOAuth credentials."""
    mcp_oauth = creds.get("mcpOAuth", {})
    return next(
        (val for key, val in mcp_oauth.items() if "weside-mcp" in key and isinstance(val, dict)),
        None,
    )


def _needs_refresh(entry: dict) -> bool:
    """Check if token is near expiry and has a refresh token."""
    expires_at = entry.get("expiresAt", 0)
    remaining_ms = expires_at - int(time.time() * 1000)
    return remaining_ms <= REFRESH_THRESHOLD_MS and bool(entry.get("refreshToken"))


def _do_refresh(refresh_token: str) -> dict | None:
    """Call Supabase OAuth token endpoint. Returns response dict or None."""
    data = json.dumps(
        {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": CLIENT_ID}
    ).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/auth/v1/oauth/token",
        data=data,
        headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        return result if result.get("access_token") else None
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def main() -> None:
    if not os.path.exists(CREDENTIALS_PATH):
        return

    try:
        with open(CREDENTIALS_PATH) as f:
            creds = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    entry = _find_weside_entry(creds)
    if not entry or not _needs_refresh(entry):
        return

    result = _do_refresh(entry["refreshToken"])
    if not result:
        return

    # Update credentials with new token pair (refresh token rotation!)
    entry["accessToken"] = result["access_token"]
    entry["refreshToken"] = result.get("refresh_token", entry["refreshToken"])
    entry["expiresAt"] = (int(time.time()) + result.get("expires_in", 3600)) * 1000

    try:
        with open(CREDENTIALS_PATH, "w") as f:
            json.dump(creds, f, indent=2)
    except OSError:
        pass


if __name__ == "__main__":
    main()
