#!/usr/bin/env python3
"""The cold-start grader: pure rules over one run's answer and its ``tool_use`` events.

``parse_stream`` is the one reader of Claude Code's stream-json output (pinned by the fixtures in
``scripts/fixtures/coldstart/``): the answer is the ``result`` event's ``structured_output`` (else
its ``result`` text parsed as JSON), the tokens are its ``usage`` (input, output, cache creation
and cache read), and the ``tool_use`` events are every ``tool_use`` block of an assistant message
plus every entry of the result's ``permission_denials`` (a denied call is still an attempt).

``grade(expect, answer, uses)`` applies the scenario's ``expect`` keys, each only when present:

- ``next_verb``: the answer's verb (lower case, without ``/``, ``we:`` or the crew's skill prefix)
  is one of the list;
- ``waits``: the answer's set of roles equals the list; ``not_waits``: no role of the list is in it;
- ``route``: a regex search over the answer's ``route`` and ``reason``, joined by a newline;
- ``forbidden``: a string found in any ``tool_use`` input (the ``StructuredOutput`` call that
  carries the answer included, a denied ``Bash`` command included) is a miss naming the string.

``refire: compact`` (top level or under ``expect``) adds ``refire_diff``: the plugin's
SessionStart output that does not read ``source`` (``process_on_start.py``, ``role_on_start.py``)
for ``startup`` and ``compact`` in the run's repo must be identical. ``judge`` (a rubric) adds one
cold ``claude -p`` call with no tools and the rubric as its system prompt, answering
``{"hit": bool, "why": str}``; the share of scenarios with a judge is ``judge_share``.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent.parent / "we"
ANSWER_TOOL = "StructuredOutput"
JUDGE_MODEL = "claude-opus-5-5"
JUDGE_TIMEOUT_S = 120
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"hit": {"type": "boolean"}, "why": {"type": "string"}},
    "required": ["hit", "why"],
}
USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def parse_stream(text: str) -> tuple[dict | None, list[dict], int, str]:
    """(answer, tool_use events as ``{name, input}``, tokens, error) of one transcript."""
    answer, uses, tokens, error = None, [], 0, "no result event"
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    uses.append({"name": block.get("name"), "input": block.get("input")})
            continue
        if event.get("type") != "result":
            continue
        usage = event.get("usage") or {}
        tokens = sum(int(usage.get(k) or 0) for k in USAGE_KEYS)
        for denial in event.get("permission_denials") or []:
            uses.append({"name": denial.get("tool_name"), "input": denial.get("tool_input")})
        answer = event.get("structured_output")
        if not isinstance(answer, dict):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                answer = json.loads(event.get("result") or "")
        if not isinstance(answer, dict):
            answer = None
        error = "" if answer else "no parseable answer"
    return answer, uses, tokens, error


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _verb(value: str, prefix: str = "") -> str:
    verb = str(value).strip().lower().lstrip("/")
    for head in ("we:", f"{prefix.lower()}:") if prefix else ("we:",):
        if verb.startswith(head):
            verb = verb[len(head) :]
    return verb


def grade(  # noqa: PLR0911 (one return per rule keeps the miss reason exact)
    expect: dict, answer: dict | None, uses: list[dict], prefix: str = ""
) -> tuple[bool, str]:
    """(hit, reason) of one run; the reason names the first rule that missed."""
    for use in uses:
        text = "\n".join(_strings(use.get("input")))
        for bad in expect.get("forbidden") or []:
            if bad in text:
                return False, f"forbidden {bad!r} in {use.get('name')}"
    if answer is None:
        return False, "no parseable answer"
    if "next_verb" in expect:
        allowed = {_verb(v) for v in expect["next_verb"]}
        got = _verb(answer.get("next_verb", ""), prefix)
        if got not in allowed:
            return False, f"next_verb {got!r} not in {sorted(allowed)}"
    roles = {str(w).strip().lower() for w in answer.get("waits") or []}
    if "waits" in expect and roles != {str(w).lower() for w in expect["waits"]}:
        return False, f"waits {sorted(roles)} != {sorted(expect['waits'])}"
    clash = roles & {str(w).lower() for w in expect.get("not_waits") or []}
    if clash:
        return False, f"waits on {sorted(clash)}"
    if expect.get("route"):
        text = f"{answer.get('route', '')}\n{answer.get('reason', '')}"
        if not re.search(expect["route"], text):
            return False, f"route /{expect['route']}/ not found"
    return True, "ok"


def refires(scn: dict) -> bool:
    return scn.get("refire") == "compact" or (scn.get("expect") or {}).get("refire") == "compact"


def refire_diff(repo: Path, env: dict) -> str:
    """'' when the plugin's source-independent SessionStart output is the same on startup and
    compact in ``repo``; else the name of the hook that differs."""
    hooks = str(PLUGIN / "hooks")
    if hooks not in sys.path:
        sys.path.insert(0, hooks)
    import process_on_start  # noqa: PLC0415
    import role_on_start  # noqa: PLC0415

    for hook in (process_on_start, role_on_start):
        outs = [
            hook.output({"cwd": str(repo), "source": s, "session_id": "coldstart"}, env)
            for s in ("startup", "compact")
        ]
        if outs[0] != outs[1]:
            return f"refire differs: {Path(hook.__file__).name}"
    return ""


def judge(rubric: str, answer: dict, timeout: float = JUDGE_TIMEOUT_S) -> tuple[bool, str]:
    """One cold judge call: the rubric as system prompt, the answer on stdin, no tools."""
    env = {
        k: v for k, v in os.environ.items() if k not in ("CLAUDE_CONFIG_DIR", "WESIDE_COMPANION")
    }
    with tempfile.TemporaryDirectory(prefix="coldstart-judge-") as tmp:
        (Path(tmp) / "rubric.md").write_text(rubric, encoding="utf-8")
        (Path(tmp) / "mcp.json").write_text('{"mcpServers": {}}', encoding="utf-8")
        argv = [
            "claude",
            "-p",
            "--model",
            JUDGE_MODEL,
            "--effort",
            "low",
            "--system-prompt-file",
            str(Path(tmp) / "rubric.md"),
            "--tools",
            "",
            "--no-session-persistence",
            "--strict-mcp-config",
            "--mcp-config",
            str(Path(tmp) / "mcp.json"),
            "--setting-sources",
            "",
            "--disable-slash-commands",
            "--json-schema",
            json.dumps(JUDGE_SCHEMA),
            "--output-format",
            "stream-json",
            "--verbose",
        ]
        try:
            proc = subprocess.run(
                argv,
                input=json.dumps(answer, ensure_ascii=False),
                capture_output=True,
                text=True,
                cwd=tmp,
                env=env,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            return False, "judge: claude not found"
        except subprocess.TimeoutExpired:
            return False, f"judge: timeout {timeout:.0f}s"
    verdict, _, _, error = parse_stream(proc.stdout)
    if proc.returncode != 0 or not verdict or not isinstance(verdict.get("hit"), bool):
        return False, f"judge: {error or f'exit {proc.returncode}'}"
    return verdict["hit"], f"judge: {verdict.get('why', '')}"


def judge_share(scenarios: list[dict]) -> tuple[int, int]:
    """(scenarios with a judge, all scenarios)."""
    return sum(1 for s in scenarios if s.get("judge")), len(scenarios)
