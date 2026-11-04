#!/usr/bin/env python3
"""SessionStart hook, matcher ``compact``: give a compacted session its live context back.

Only in a repo with a crew that loads; a ``--agent`` session (``agent_type``) gets nothing. The
summary of a compaction keeps little of what the session was doing, so this prints, for this
session only, in this order:

1. ``Epic update first: …`` when ``epic_age_precompact.py`` flagged this ``session_id`` (the flag
   file under ``<board dir>/epic-age/`` is consumed);
2. its board line from the crew's ``board.file`` (board v7: ``sessions[]``, matched by
   ``session_id``, else the pin, else the tmux window name) with the open questions it asked
   (``owner_queue[]`` with ``session`` = its name);
3. for a master (``crew.role_of_session`` = ``master``) its epic: plan path and status, the last
   ``LOG_ENTRIES`` Updates Log entries by date, the open PRs (``scripts/epic_state.py``);
4. for a pin: reload the identity (``/we:materialize``, when the crew's ``weside_account``) and the
   role skill (``crew.skill_path``);
5. the hint to read its own memory file with open commitments.

Budget ``render_process.BUDGET``: the board fields are cut first (halved per round), then the
Updates Log entries; the instructions and the questions stay whole. Over budget anyway: a stderr
pointer, exit 1. ``gh`` and ``tmux`` are injected (``runner``) for the tests.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import crew as crewlib
import epic_state
import render_process

FIELDS = ("name", "role", "state", "topic", "now", "keys", "pr", "note", "status", "work", "epic")
FIELD_CAP = 1_500
LOG_ENTRIES = 3
LOG_CAP = 600
FLAG_DIR = "epic-age"
MEMORY = (
    "Before your next step, read your own memory file with open commitments (the task list via "
    "TaskList, else the checklist in your memory directory) and pick up what is still open."
)

Runner = Callable[..., subprocess.CompletedProcess]


def board_path(crew: dict[str, Any]) -> Path:
    return Path(os.path.expanduser(str(crew["board"]["file"])))


def tmux_window(env: Any, runner: Runner = subprocess.run) -> str:
    if not env.get("TMUX"):
        return ""
    try:
        done = runner(
            ["tmux", "display-message", "-p", "#W"], capture_output=True, text=True, timeout=2
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip()


def load_board(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def find_session(board: dict, session_id: str, pin: str, window: str) -> dict | None:
    sessions = [s for s in board.get("sessions") or [] if isinstance(s, dict)]
    for test in (
        lambda s: session_id and s.get("session_id") == session_id,
        lambda s: pin and pin in (s.get("companion"), s.get("name")),
        lambda s: window and s.get("name") == window,
    ):
        hit = next((s for s in sessions if test(s)), None)
        if hit:
            return hit
    return None


def fmt(value: object, cap: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= cap else text[: cap - 1] + "…"


def board_block(crew: dict, board: dict | None, line: dict | None, cap: int) -> str:
    path = crew["board"]["file"]
    coordinator = crewlib.holder_name(crew, "coordinator") or "the coordinator"
    if board is None:
        return f"Board: {path} unreadable; your board line could not be restored."
    if not line:
        return (
            f"Board: no line for this session in {path}. If you are a master, set yours "
            f"(`board.py set`, or tell {coordinator})."
        )
    rows = [f"- {k}: {fmt(line[k], cap)}" for k in FIELDS if line.get(k) not in (None, "", [])]
    human = str(crew["human"]["name"])
    label = crew["labels"]["recommendation"]
    asked = [
        q
        for q in board.get("owner_queue") or []
        if isinstance(q, dict) and q.get("session") == line.get("name")
    ]
    out = [f"Your board line ({path}, before the compaction):", *rows]
    if not asked:
        out.append("Open questions you asked: none on the board.")
        return "\n".join(out)
    out.append(f"Open questions you asked (waiting for {human}):")
    for q in asked:
        rec = f" · {label}: {fmt(q['recommendation'], 300)}" if q.get("recommendation") else ""
        out.append(f"- {q.get('id', '?')} {q.get('key', '')} · {fmt(q.get('ask', ''), 400)}{rec}")
    return "\n".join(out)


def companion_block(crew: dict, pin: str, cwd: str) -> str:
    coordinator = crewlib.holder_name(crew, "coordinator") or "the coordinator"
    skill = crewlib.skill_name(pin, crew) or pin
    found = crewlib.skill_path(pin, cwd)
    if found is None:
        reload = f"no role skill `{skill}` found; ask {coordinator}"
    elif found[1]:
        reload = f"then invoke the Skill tool with `{skill}` (your role skill)"
    else:
        reload = f"then read your role skill `{found[0]}` (not loaded in this repo)"
    if crew.get("weside_account"):
        first = (
            "The compaction dropped your identity prompt. Before your next reply, invoke the "
            f"Skill tool with `we:materialize` (cache first, cheap), {reload}."
        )
    else:
        first = f"Before your next reply, {reload.removeprefix('then ')}."
    return f"You are the companion {pin} (WESIDE_COMPANION={pin}). {first} Then continue as {pin}."


def epic_data(crew_path: Path, line: dict | None, cwd: Path, runner: Runner) -> dict[str, Any]:
    """The master's epic: plan, frontmatter, Updates Log and open PRs, or ``error``."""
    roots = list(dict.fromkeys([git_root(cwd, runner) or cwd, crew_path.parent.parent.resolve()]))
    try:
        plan = epic_state.resolve(line or {}, roots)
    except epic_state.EpicError as exc:
        return {"error": str(exc), "log": []}
    text = plan.read_text(encoding="utf-8")
    meta = epic_state.frontmatter(text)
    key = str(meta.get("ticket") or "")
    keys = [key, *epic_state.story_keys(plan.parent.parent.parent, key)] if key else []
    return {
        "plan": plan,
        "meta": meta,
        "log": epic_state.updates_log(text),
        "prs": epic_state.open_prs(cwd, keys, runner),
    }


def epic_block(data: dict[str, Any], entries: int) -> str:
    if "error" in data:
        return data["error"]
    meta, log, prs = data["meta"], data["log"], data["prs"]
    out = [
        f"Your epic {meta.get('ticket') or ''}: {data['plan']} (status: "
        f"{meta.get('status') or 'unknown'})"
    ]
    if not log:
        out.append("Updates Log: none in the plan.")
    elif entries:
        out.append(f"Updates Log, last {min(entries, len(log))} by date:")
        out += [f"- {d} — {fmt(t, LOG_CAP)}" for d, t in log[-entries:]]
    if prs is None:
        out.append("Open PRs: unknown (gh failed).")
    elif not prs:
        out.append("Open PRs: none.")
    else:
        out.append("Open PRs:")
        for pr in prs:
            repo = (pr.get("repository") or {}).get("nameWithOwner") or ""
            out.append(f"- {repo}#{pr.get('number')} {pr.get('title', '')} {pr.get('url', '')}")
    return "\n".join(out)


def git_root(cwd: Path, runner: Runner) -> Path | None:
    try:
        done = runner(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = done.stdout.strip()
    return Path(out).resolve() if done.returncode == 0 and out else None


def take_flag(crew: dict, session_id: str) -> bool:
    if not session_id or "/" in session_id:
        return False
    flag = board_path(crew).parent / FLAG_DIR / session_id
    try:
        flag.unlink()
    except OSError:
        return False
    return True


def render(
    hook_input: dict, env: Any, runner: Runner = subprocess.run
) -> tuple[str | None, str | None]:
    """(additionalContext or None, stderr line or None)."""
    if hook_input.get("agent_type"):
        return None, None
    cwd = str(hook_input.get("cwd") or os.getcwd())
    try:
        crew_path, crew = crewlib.find_and_load(cwd)
    except crewlib.CrewError:
        return None, None  # process_on_start.py names the fault
    if crew is None or crew_path is None:
        return None, None
    session_id = str(hook_input.get("session_id") or "")
    _, pin = crewlib.session_kind(env, None, hook_input)
    board = load_board(board_path(crew))
    window = "" if board is None else tmux_window(env, runner)
    line = find_session(board, session_id, pin, window) if board else None
    flagged = take_flag(crew, session_id)
    head = ["Context restored after compaction:"]
    if flagged:
        head.insert(
            0,
            "Epic update first: the epic's Updates Log is older than a day; run the "
            "epic update (`/we:epic` update) before your next story.",
        )
    tail = [companion_block(crew, pin, cwd)] if pin else []
    tail.append(MEMORY)
    master = crewlib.role_of_session(crew, env, hook_input) == "master"
    data = epic_data(crew_path, line, Path(cwd), runner) if master else None
    entries, cap = LOG_ENTRIES, FIELD_CAP
    while True:
        epic = epic_block(data, entries) if data else ""
        parts = [*head, board_block(crew, board, line, cap), *([epic] if epic else []), *tail]
        text = "\n\n".join(parts)
        if len(text) <= render_process.BUDGET:
            return text, None
        if cap > 80:
            cap //= 2
        elif entries:
            entries -= 1
        else:
            return (
                None,
                f"compact_on_start: {len(text)} chars > {render_process.BUDGET}; not loaded",
            )


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        data = {}
    text, error = render(data if isinstance(data, dict) else {}, os.environ)
    if error:
        print(error, file=sys.stderr)
        return 1
    if text is not None:
        out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
        json.dump(out, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
