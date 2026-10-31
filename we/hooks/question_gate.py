#!/usr/bin/env python3
"""Stop hook: a question in plain text while background work runs is sent back once.

While a subagent, a `Monitor` or a background command runs, its notifications push a plain-text
question out of sight: on 29.10.2026 a question asked in prose was repeated in five later messages
and the user still could not find it. `AskUserQuestion` stays on screen until it is answered.

  * The last assistant text loses fenced code, inline code, URLs and quotes (`>` lines, text in
    quotation marks). It is a question when its last sentence ends with `?` (closing emphasis or
    brackets ignored).
  * Background work comes from the transcript (`transcript_path`), counted launched minus ended:
      - launched: a tool result whose `toolUseResult` has `status: "async_launched"` (`agentId`),
        a `backgroundTaskId` (Bash `run_in_background`, or a command the user backgrounded), or a
        `taskId` with `persistent` (Monitor);
      - ended: a `<task-notification>` with that `<task-id>` and a `<status>` of completed, failed
        or killed (a Monitor event carries no status and ends nothing), or a `TaskStop` with that
        `task_id`;
      - a teammate (`status: "teammate_spawned"`, by `name`) is busy from its spawn or a
        `SendMessage` to it until an `idle_notification` from it or a `TaskStop` with its name.
    Measured on three long transcripts (30.10.2026): every async agent and Monitor launch had its
    notification, every background command without one had a `TaskStop`; teammates are the weak
    signal (2 of 84 left neither an idle notification nor a `TaskStop`), a stale one costs one
    extra block.
  * No block where `AskUserQuestion` is denied: a `permissions.deny` entry `AskUserQuestion` (or
    `AskUserQuestion(...)`) in the user settings (`$CLAUDE_CONFIG_DIR` or `~/.claude`), the
    project's `.claude/settings.json` / `settings.local.json` (`$CLAUDE_PROJECT_DIR`, else the
    payload's `cwd`) or the managed settings. The session cannot call the tool, so the plain-text
    question with its recommendation at the end is the right form (owner, 31.10.2026).
  * One block per turn: no block while `stop_hook_active` is set. Never on SubagentStop or in a
    subagent. Fail-open on every error, an unreadable transcript or settings file included.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_FENCE = re.compile(r"^\s{0,3}(```|~~~).*?^\s{0,3}\1[^\n]*$", re.MULTILINE | re.DOTALL)
_INLINE = re.compile(r"`[^`\n]*`")
_URL = re.compile(r"https?://\S+")
_QUOTED = re.compile(r"\"[^\"\n]*\"|„[^“\n]*“|“[^”\n]*”|«[^»\n]*»")
_TRAILING = " \t\n*_)]}>.!:;\"'“”»"
_TERMINAL = ("completed", "failed", "killed")
_NOTIFICATION = re.compile(r"<task-notification>(.*?)</task-notification>", re.DOTALL)
_TASK_ID = re.compile(r"<task-id>(.*?)</task-id>")
_STATUS = re.compile(r"<status>(.*?)</status>")
_TEAMMATE = re.compile(
    r'<teammate-message teammate_id="([^"]*)"[^>]*>(.*?)</teammate-message>', re.DOTALL
)
# Only lines carrying one of these are parsed: a long transcript holds large request blobs.
_MARKERS = ("toolUseResult", "task-notification", "TaskStop", "SendMessage", "idle_notification")

REASON = (
    "Background work is still running, so a question in plain text scrolls away under its "
    "notifications. Ask it via AskUserQuestion, recommendation as the first option."
)


def ends_in_question(text: str) -> bool:
    text = _FENCE.sub(" ", text)
    lines = [line for line in text.splitlines() if not line.lstrip().startswith(">")]
    text = "\n".join(lines)
    for pattern in (_INLINE, _URL, _QUOTED):
        text = pattern.sub(" ", text)
    text = text.rstrip(_TRAILING.replace(".", "").replace("!", ""))
    return text.endswith("?")


def _strings(value: object) -> list[str]:
    """Every string inside a JSON value, unescaped (a dump would escape the quotes)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return [s for item in value for s in _strings(item)]
    return []


def _text_of(entry: dict) -> str:
    if entry.get("type") == "queue-operation":
        content = entry.get("content")
        return content if isinstance(content, str) else ""
    if entry.get("type") == "attachment":
        return "\n".join(_strings(entry.get("attachment")))
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


class _Ledger:
    """Background tasks launched and ended, teammates busy or idle."""

    def __init__(self) -> None:
        self.launched: set[str] = set()
        self.ended: set[str] = set()
        self.busy: dict[str, bool] = {}

    def tool_use(self, block: dict) -> None:
        args = block.get("input") or {}
        if block.get("name") == "TaskStop" and args.get("task_id"):
            self.ended.add(str(args["task_id"]))
            self.busy.pop(str(args["task_id"]), None)
        if block.get("name") == "SendMessage" and args.get("to") in self.busy:
            self.busy[args["to"]] = True

    def launch(self, result: dict) -> None:
        if result.get("status") == "async_launched" and result.get("agentId"):
            self.launched.add(str(result["agentId"]))
        elif result.get("status") == "teammate_spawned" and result.get("name"):
            self.busy[result["name"]] = True
        elif result.get("backgroundTaskId"):
            self.launched.add(str(result["backgroundTaskId"]))
        elif result.get("taskId") and "persistent" in result:
            self.launched.add(str(result["taskId"]))

    def notifications(self, text: str) -> None:
        for note in _NOTIFICATION.finditer(text):
            task, status = _TASK_ID.search(note.group(1)), _STATUS.search(note.group(1))
            if task and status and status.group(1).strip() in _TERMINAL:
                self.ended.add(task.group(1).strip())
        for name, body in _TEAMMATE.findall(text):
            if name in self.busy and '"idle_notification"' in body:
                self.busy[name] = False

    def running(self) -> int:
        return len(self.launched - self.ended) + sum(self.busy.values())


def running_work(transcript_path: str) -> int:
    """How many background tasks and busy teammates the transcript leaves open."""
    ledger = _Ledger()
    with open(transcript_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith('{"type":"api-request') or not any(m in line for m in _MARKERS):
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            kind = entry.get("type")
            content = (entry.get("message") or {}).get("content")
            if kind == "assistant" and isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        ledger.tool_use(block)
            elif kind in ("user", "queue-operation", "attachment"):
                result = entry.get("toolUseResult") if kind == "user" else None
                if isinstance(result, dict):
                    ledger.launch(result)
                ledger.notifications(_text_of(entry))
    return ledger.running()


_TOOL = "AskUserQuestion"
_MANAGED = (
    Path("/etc/claude-code/managed-settings.json"),
    Path("/Library/Application Support/ClaudeCode/managed-settings.json"),
)


def settings_files(payload: dict) -> list[Path]:
    """The settings files whose `permissions.deny` applies to this session."""
    config = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    project = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd")
    files = [Path(config) / "settings.json", *_MANAGED]
    if project:
        files += [Path(project) / ".claude" / n for n in ("settings.json", "settings.local.json")]
    return files


def tool_denied(payload: dict) -> bool:
    """True when a settings file denies AskUserQuestion; an unreadable file raises (fail-open)."""
    for path in settings_files(payload):
        if not path.is_file():
            continue
        deny = (json.loads(path.read_text(encoding="utf-8")).get("permissions") or {}).get("deny")
        for rule in deny or []:
            if isinstance(rule, str) and (rule == _TOOL or rule.startswith(_TOOL + "(")):
                return True
    return False


def decide(payload: dict) -> str | None:
    if payload.get("hook_event_name", "Stop") != "Stop" or payload.get("agent_id"):
        return None
    if payload.get("stop_hook_active"):
        return None
    text = payload.get("last_assistant_message") or ""
    path = payload.get("transcript_path")
    if not text or not path or not ends_in_question(text):
        return None
    if tool_denied(payload):
        return None
    return REASON if running_work(path) else None


def main() -> None:
    try:
        reason = decide(json.load(sys.stdin))
    except Exception:
        return
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
