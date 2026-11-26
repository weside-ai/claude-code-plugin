#!/usr/bin/env python3
"""Replay the worker rights gate's logged denials through today's gate, offline: how many of them
would it still deny?

`brake_replay.py [--days 14] [--projects DIR] [--crew FILE] [--json]` reads the `deny` lines of the
gate `worker_rights_gate` in `<state dir>/brakes.jsonl` (`worker_rights.brake_log` owns the shape;
`crew.state_dir` finds the directory) from the last `--days` days, finds each one's command in its
session's transcript (`<projects>/*/<session_id>.jsonl`, default `claude_home.config_dir()/projects`:
the Bash call whose result names the logged item, paired in order within the session), and judges
it with `decide` of `hooks/worker_rights_gate.py` as a process worker (`WE_ROLE=worker`) in a
scratch repo on a keyed branch whose default branch carries the crew's `worker_rights` (`--crew`,
else the crew found from the current directory). `gh` is a stub that fails, so a merge line that
reaches its own-PR read stays denied: the replay never reads a PR or merges.

Prints three counts (logged, recovered, still denied), the logged items whose commands now pass,
and the still-denied items grouped. It never prints a command, which may carry a value: only item
names (`kind`: without crew strings, branches, numbers) and counts. A command the transcripts no longer hold counts as unrecovered. A `cd` into a
real tree is judged in that tree as it stands now, not as it stood. Exit 0, 2 on a bad call.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "hooks"))

GATE = "worker_rights_gate"
REPLAY_KEY = "REPLAY-1"


def denials(log: Path, since: dt.datetime) -> list[dict]:
    """The gate's `deny` lines in `log` from `since` on, oldest first."""
    rows = []
    try:
        lines = log.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get("type") != "deny" or row.get("gate") != GATE:
            continue
        try:
            ts = dt.datetime.strptime(str(row.get("ts")) + "+0000", "%Y-%m-%dT%H:%M:%SZ%z")
        except ValueError:
            continue
        if ts >= since:
            rows.append(row)
    return rows


def _text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(_text(c.get("text", "")) for c in content if isinstance(c, dict))
    return ""


def refused_calls(transcript: Path) -> Iterator[tuple[str, str]]:
    """(the result text, the command) of each Bash call in `transcript` the gate refused, in order."""
    commands: dict[str, str] = {}
    try:
        lines = transcript.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        try:
            content = (json.loads(line).get("message") or {}).get("content")
        except (ValueError, AttributeError):
            continue
        for part in content if isinstance(content, list) else []:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "tool_use" and part.get("name") == "Bash":
                commands[str(part.get("id"))] = str((part.get("input") or {}).get("command", ""))
            elif part.get("type") == "tool_result" and part.get("tool_use_id") in commands:
                text = _text(part.get("content"))
                if "never for a worker" in text or "not a worker right" in text:
                    yield text, commands[str(part.get("tool_use_id"))]


def recover(rows: list[dict], projects: Path) -> list[tuple[dict, str | None]]:
    """Each logged denial with its command from its session's transcript, None where none is
    left: a result naming the row's item, each result used once, in order."""
    calls: dict[str, list[tuple[str, str]]] = {}
    out = []
    for row in rows:
        sid = str(row.get("session_id") or "")
        if sid and sid not in calls:
            calls[sid] = [
                c for path in projects.glob(f"*/{sid}.jsonl") for c in refused_calls(path)
            ]
        pending = calls.get(sid, [])
        item = str(row.get("item") or "")
        hit = next((k for k, (text, _cmd) in enumerate(pending) if item and item in text), None)
        out.append((row, pending.pop(hit)[1] if hit is not None else None))
    return out


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def scratch_repo(root: Path, rights: dict) -> Path:
    """A repo on a keyed feature branch whose origin's default branch holds a crew with `rights`."""
    repo = root / "app"
    (repo / ".weside").mkdir(parents=True)
    crew = {"version": 2, "roles": {}, "members": {}, "worker_rights": rights}
    (repo / ".weside" / "crew.json").write_text(json.dumps(crew), encoding="utf-8")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", ".weside")
    _git(repo, "-c", "user.email=r@r", "-c", "user.name=r", "commit", "-q", "-m", "crew")
    _git(repo, "remote", "add", "origin", "git@github.com:acme/app.git")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    _git(repo, "checkout", "-q", "-b", f"feat/{REPLAY_KEY}-replay")
    return repo


def _crew_rights(crew_file: Path | None) -> dict:
    import crew as crew_mod  # noqa: PLC0415

    try:
        data = (
            json.loads(crew_file.read_text(encoding="utf-8"))
            if crew_file
            else crew_mod.find_and_load(Path.cwd())[1] or {}
        )
    except (OSError, ValueError, crew_mod.CrewError):
        data = {}
    block = data.get("worker_rights") if isinstance(data, dict) else None
    return block if isinstance(block, dict) else {}


def replay(recovered: list[tuple[dict, str | None]], rights: dict) -> list[str | None]:
    """The new gate's denial for each recovered command (None: it passes), in order."""
    import worker_rights_gate as gate  # noqa: PLC0415

    verdicts: list[str | None] = []
    with tempfile.TemporaryDirectory(prefix="brake-replay-") as tmp:
        root = Path(tmp)
        repo = scratch_repo(root, rights)
        stub = root / "bin"
        stub.mkdir()
        (stub / "gh").write_text("#!/bin/sh\necho 'replay: no gh' >&2\nexit 1\n")
        (stub / "gh").chmod(0o755)
        saved = dict(os.environ)
        os.environ.update(
            PATH=f"{stub}{os.pathsep}{saved.get('PATH', '')}",
            WE_ROLE="worker",
            WE_STORY_KEY=REPLAY_KEY,
            WE_STATE_DIR=str(root / "state"),  # `decide` writes nothing; a stray write lands here
        )
        try:
            for _row, command in recovered:
                if command is None:
                    continue
                payload = {
                    "tool_name": "Bash",
                    "cwd": str(repo),
                    "tool_input": {"command": command},
                }
                try:
                    verdict = gate.decide(payload, dict(os.environ))
                except Exception as exc:  # the hook fails open on a crash
                    verdict = gate.crashed(payload, dict(os.environ), exc)
                deny = verdict and verdict[0] == "deny"
                verdicts.append(verdict[1].rsplit(": ask ", 1)[0] if deny else None)
        finally:
            os.environ.clear()
            os.environ.update(saved)
    return verdicts


def kind(item: str) -> str:
    """`item` without the values it may name (a crew string, a branch, a PR number, a tag), so the
    report can go into a public PR body."""
    item = re.sub(r"crew deny_text \([^)]*\)", "crew deny_text", item)
    item = re.sub(r"\(crew deny_commands: [^)]*\)", "(crew deny_commands)", item)
    item = re.sub(
        r"\(main \(a git push from [^:)]*.*", "(main (a git push from the default branch))", item
    )
    item = re.sub(r"git push of the tag \S+?\)", "git push of a tag)", item)
    if item.startswith("not a worker right ("):
        item = re.split(r": | \(its head", item, maxsplit=1)[0]
    item = re.sub(r"\b[0-9a-f]{7,40}\b|\d+", "N", item)
    return re.sub(r"\b[\w.-]+/[\w./-]+", "<ref>", item)[:100]


def report(rows: list[dict], recovered: list[tuple[dict, str | None]], verdicts: list) -> dict:
    found = [row for row, command in recovered if command is not None]
    still = [kind(v) for v in verdicts if v]
    passing = collections.Counter(
        kind(str(row.get("item"))) for row, v in zip(found, verdicts) if v is None
    )
    return {
        "logged": len(rows),
        "recovered": len(found),
        "still_denied": len(still),
        "now_pass": dict(passing.most_common()),
        "still_denied_items": dict(collections.Counter(still).most_common()),
    }


def main(argv: list[str]) -> int:
    import claude_home  # noqa: PLC0415
    import crew as crew_mod  # noqa: PLC0415

    parser = argparse.ArgumentParser(prog="brake_replay.py")
    parser.add_argument("--days", type=float, default=14)
    parser.add_argument("--projects", type=Path, default=claude_home.config_dir() / "projects")
    parser.add_argument("--crew", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        path, crew = crew_mod.find_and_load(Path.cwd())
    except crew_mod.CrewError:
        path, crew = None, None
    log = crew_mod.state_dir(path, crew) / "brakes.jsonl"
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.days)
    rows = denials(log, since)
    recovered = recover(rows, args.projects)
    result = report(rows, recovered, replay(recovered, _crew_rights(args.crew)))
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(
        f"logged {result['logged']}, recovered {result['recovered']}, "
        f"still denied {result['still_denied']} (last {args.days:g} days)"
    )
    print("now pass, by logged item:")
    for item, n in result["now_pass"].items():
        print(f"  {n:4d}  {item}")
    print("still denied, by today's item:")
    for item, n in result["still_denied_items"].items():
        print(f"  {n:4d}  {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
