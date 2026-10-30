#!/usr/bin/env python3
"""Live facts per running Claude Code session for the /board pane, as one JSON line.

Prints per session only verdict-sized facts: status, the WE_ROLE class, the
claude-swap profile's name (/board compares it with the masterProfile option)
and the permission mode. Never a value from the environment beyond the
profile name: /proc/<pid>/environ holds secrets, so
only the keys WE_ROLE and CLAUDE_CONFIG_DIR are looked at and neither is
printed as read.
"""

import json
import os
import re
import subprocess
import sys

SWAP_SESSIONS = os.path.expanduser("~/.local/share/claude-swap/sessions/")
CLAUDE_HOME = os.path.expanduser("~/.claude")
TAIL_BYTES = 262_144
MODE = re.compile(rb'"permissionMode":"(\w+)"')
WANTED = (b"WE_ROLE=", b"CLAUDE_CONFIG_DIR=")


def env_keys(pid):
    """WE_ROLE and CLAUDE_CONFIG_DIR of a process; every other key is dropped unread."""
    found = {}
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            for entry in f.read().split(b"\0"):
                if entry.startswith(WANTED):
                    key, _, value = entry.partition(b"=")
                    found[key.decode()] = value.decode(errors="replace")
    except OSError:
        return None
    return found


def role_class(value):
    if value is None:
        return None
    return value if value in ("master", "worker") else "other"


def profile_of(config_dir):
    """The claude-swap profile's folder name; 'other' for any other config dir, never its path."""
    if not config_dir:
        return None
    path = os.path.normpath(config_dir) + "/"
    if path.startswith(SWAP_SESSIONS):
        return path[len(SWAP_SESSIONS) :].split("/")[0] or "other"
    return "other"


def mode_of(config_dir, cwd, session_id):
    """The newest permissionMode in the tail of the session's transcript, under its config dir."""
    if not cwd or not session_id:
        return None
    projects = os.path.join(config_dir or CLAUDE_HOME, "projects")
    path = os.path.join(projects, re.sub(r"[^a-zA-Z0-9]", "-", cwd), f"{session_id}.jsonl")
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - TAIL_BYTES))
            hits = MODE.findall(f.read())
    except OSError:
        return None
    return hits[-1].decode() if hits else None


def main():
    run = subprocess.run(
        ["claude", "agents", "--json"], capture_output=True, text=True, timeout=20, check=False
    )
    if run.returncode != 0:
        print(json.dumps({"error": f"claude agents --json: exit {run.returncode}"}))
        return 0
    out = []
    for agent in json.loads(run.stdout):
        pid = agent.get("pid")
        env = env_keys(pid) if pid else None
        out.append(
            {
                "name": agent.get("name"),
                "pid": pid,
                "kind": agent.get("kind"),
                "status": agent.get("status"),
                "state": agent.get("state"),
                "weRole": role_class(env.get("WE_ROLE")) if env is not None else None,
                "profile": profile_of(env.get("CLAUDE_CONFIG_DIR")) if env is not None else None,
                "envRead": env is not None,
                "mode": mode_of(
                    (env or {}).get("CLAUDE_CONFIG_DIR"), agent.get("cwd"), agent.get("sessionId")
                ),
            }
        )
    print(json.dumps({"sessions": out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
