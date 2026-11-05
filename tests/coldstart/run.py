#!/usr/bin/env python3
"""The cold-start harness: each scenario of ``tests/coldstart/`` as a real cold ``claude -p`` session.

A scenario is ``tests/coldstart/<dir>/<name>.yaml``; its id is ``<dir>/<name>`` (``card-cornerstone``
exists once per role). Keys: ``id`` (= ``<name>``), ``role``, ``crew`` (a fixture path in this repo),
``prompt``, ``expect``, and optionally ``env`` (only ``WE_ROLE``/``WESIDE_COMPANION``), ``world``
(``{path: value}``: a value naming an existing file of this repo is copied, any other string is the
file's text), ``mcp`` (``{name: server}``, the only way a session gets an MCP server), ``refire``,
``routing`` and ``judge``.

Per run, the session is isolated like ``we/scripts/cold_reader.py``'s reader, minus what a
cold start needs (the plugin's own hooks, slash commands, Claude Code's prompt, three read tools):

- a fresh ``git init`` repo under ``$TMPDIR`` (refused when it lies under ``$HOME``, so no
  ``AGENTS.md``/``CLAUDE.md`` ancestor), holding the scenario's ``crew`` as ``.weside/crew.json``
  and its ``world`` files;
- ``claude -p --plugin-dir <checkout>/we --setting-sources "" --strict-mcp-config --mcp-config
  <empty unless mcp:> --no-session-persistence --model MODEL --effort EFFORT --json-schema
  <schema.json> --output-format stream-json --verbose --tools Read,Glob,Grep --max-budget-usd
  <rates.json run_budget_usd>``;
- the caller's environment minus ``CLAUDE_CONFIG_DIR`` (the global login, as ``env -u
  CLAUDE_CONFIG_DIR`` does), ``WESIDE_COMPANION`` and ``WE_ROLE`` (a harness started from a worker
  would otherwise run every scenario as that worker), plus the scenario's ``env``.

The harness refuses to start while ``~/.claude/CLAUDE.md`` exists (Claude Code loads it whatever
``--setting-sources`` says). Every verb holds the workspace test slot (``fcntl.flock`` on
``WESIDE_TESTS_LOCK``, default ``/tmp/weside-tests.lock``) from before its first session to its
end, and runs at most ``MAX_JOBS`` sessions in parallel inside it. A run that fails (no ``claude``,
a non-zero exit, the timeout, no parseable answer) is a miss naming the cause; nothing retries.

Usage:
  python3 tests/coldstart/run.py run <id>... [--jobs J]
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import yaml

SUITE = Path(__file__).resolve().parent
REPO = SUITE.parent.parent
PLUGIN = REPO / "we"
SCHEMA = SUITE / "schema.json"
RATES = SUITE / "rates.json"
MODEL = "claude-opus-5-5"
EFFORT = "medium"
TOOLS = "Read,Glob,Grep"
STRIPPED_ENV = ("CLAUDE_CONFIG_DIR", "WESIDE_COMPANION", "WE_ROLE")
SCENARIO_ENV = ("WE_ROLE", "WESIDE_COMPANION")
REQUIRED = ("id", "role", "crew", "prompt", "expect")
TIMEOUT_S = 300
MAX_JOBS = 2
DEFAULT_RUN_BUDGET_USD = 1.0
LOCK_ENV = "WESIDE_TESTS_LOCK"
LOCK_DEFAULT = "/tmp/weside-tests.lock"


class ScenarioError(Exception):
    """A scenario the harness refuses before any model call; the message names the file."""


class RefusedError(Exception):
    """The harness refuses to start; the message names the cause."""


@dataclass
class Result:
    sid: str
    hit: bool
    reason: str
    tokens: int
    wall_s: float
    events: list | None = None

    def line(self) -> str:
        return f"{self.sid} {'hit' if self.hit else 'miss'} {self.reason} tokens={self.tokens}"


# --- scenarios -------------------------------------------------------------------------------


def scenario_paths() -> list[Path]:
    return sorted(SUITE.glob("*/*.yaml"))


def sid_of(path: Path) -> str:
    return f"{path.parent.name}/{path.stem}"


def load(path: Path) -> dict:
    """The parsed scenario plus ``sid``; ``ScenarioError`` names the file and the defect."""
    rel = path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else str(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ScenarioError(f"{rel}: does not parse: {exc}") from None
    if not isinstance(data, dict):
        raise ScenarioError(f"{rel}: not a mapping")
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise ScenarioError(f"{rel}: lacks {', '.join(missing)}")
    if not (REPO / str(data["crew"])).is_file():
        raise ScenarioError(f"{rel}: crew {data['crew']} does not exist")
    env = data.get("env") or {}
    bad = sorted(set(env) - set(SCENARIO_ENV))
    if bad:
        raise ScenarioError(f"{rel}: env key {', '.join(bad)} not allowed")
    data["env"] = {k: str(v) for k, v in env.items()}
    data["world"] = data.get("world") or {}
    data["sid"] = sid_of(path)
    return data


def resolve(ids: list[str]) -> list[dict]:
    """Scenarios by id (``<dir>/<name>``, or a ``<name>`` that is unique)."""
    paths = {sid_of(p): p for p in scenario_paths()}
    out = []
    for want in ids:
        hits = [p for sid, p in paths.items() if want in (sid, sid.split("/", 1)[1])]
        if len(hits) != 1:
            names = ", ".join(sorted(sid_of(p) for p in hits)) or "none"
            raise ScenarioError(f"{want}: {len(hits)} scenarios match ({names})")
        out.append(load(hits[0]))
    return out


def rates() -> dict:
    if not RATES.is_file():
        return {}
    return json.loads(RATES.read_text(encoding="utf-8"))


# --- isolation -------------------------------------------------------------------------------


def check_host(home: Path | None = None) -> None:
    home = Path(os.environ.get("HOME", "~")).expanduser() if home is None else home
    user_md = home / ".claude" / "CLAUDE.md"
    if user_md.exists():
        raise RefusedError(f"{user_md} exists: Claude Code would load it into every cold session")


def temp_root() -> Path:
    """A fresh directory under ``$TMPDIR`` (default ``/tmp``), refused under ``$HOME``."""
    base = Path(os.environ.get("TMPDIR") or "/tmp").resolve()
    home = Path(os.environ.get("HOME", "~")).expanduser().resolve()
    if base == home or home in base.parents:
        raise RefusedError(
            f"TMPDIR {base} lies under HOME {home}: an AGENTS.md ancestor would load"
        )
    return Path(tempfile.mkdtemp(prefix="coldstart-", dir=str(base)))


def prepare(scn: dict, root: Path) -> tuple[Path, Path]:
    """(repo, mcp config) of one run under ``root``."""
    repo = root / "repo"
    (repo / ".weside").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    shutil.copyfile(REPO / scn["crew"], repo / ".weside" / "crew.json")
    for rel, value in scn["world"].items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        source = REPO / str(value)
        if len(str(value)) < 256 and "\n" not in str(value) and source.is_file():
            shutil.copyfile(source, target)
        else:
            target.write_text(str(value), encoding="utf-8")
    mcp = root / "mcp.json"
    mcp.write_text(json.dumps({"mcpServers": scn.get("mcp") or {}}), encoding="utf-8")
    return repo, mcp


def argv(scn: dict, mcp: Path, budget_usd: float) -> list[str]:
    return [
        "claude",
        "-p",
        "--plugin-dir",
        str(PLUGIN),
        "--setting-sources",
        "",
        "--strict-mcp-config",
        "--mcp-config",
        str(mcp),
        "--no-session-persistence",
        "--model",
        MODEL,
        "--effort",
        EFFORT,
        "--json-schema",
        SCHEMA.read_text(encoding="utf-8"),
        "--output-format",
        "stream-json",
        "--verbose",
        "--tools",
        TOOLS,
        "--max-budget-usd",
        str(budget_usd),
        str(scn["prompt"]).strip(),
    ]


def child_env(scn: dict, environ: dict | None = None) -> dict:
    env = dict(os.environ if environ is None else environ)
    for key in STRIPPED_ENV:
        env.pop(key, None)
    env.update(scn["env"])
    return env


# --- stream-json -----------------------------------------------------------------------------


def parse_stream(text: str) -> tuple[dict | None, list[dict], int, str]:
    """(answer, tool_use events, tokens, error) of one stream-json transcript."""
    events, answer, tokens, error = [], None, 0, "no result event"
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(event)
        if event.get("type") != "result":
            continue
        usage = event.get("usage") or {}
        tokens = sum(
            int(usage.get(k) or 0)
            for k in (
                "input_tokens",
                "output_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
            )
        )
        answer = event.get("structured_output")
        if not isinstance(answer, dict):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                answer = json.loads(event.get("result") or "")
        error = "" if isinstance(answer, dict) else "no parseable answer"
        if not isinstance(answer, dict):
            answer = None
    return answer, events, tokens, error


# --- one session -----------------------------------------------------------------------------


def run_one(scn: dict, budget_usd: float, timeout: float = TIMEOUT_S) -> Result:
    start = time.monotonic()
    root = temp_root()
    try:
        repo, mcp = prepare(scn, root)
        try:
            proc = subprocess.run(
                argv(scn, mcp, budget_usd),
                cwd=str(repo),
                env=child_env(scn),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            return Result(scn["sid"], False, "claude not found", 0, time.monotonic() - start)
        except subprocess.TimeoutExpired:
            return Result(
                scn["sid"], False, f"timeout {timeout:.0f}s", 0, time.monotonic() - start
            )
        answer, events, tokens, error = parse_stream(proc.stdout)
        wall = time.monotonic() - start
        if proc.returncode != 0:
            return Result(scn["sid"], False, f"exit {proc.returncode}", tokens, wall, events)
        if answer is None:
            return Result(scn["sid"], False, error, tokens, wall, events)
        return Result(scn["sid"], True, "answer", tokens, wall, events)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- the test slot ---------------------------------------------------------------------------


def lock_path() -> Path:
    return Path(os.environ.get(LOCK_ENV) or LOCK_DEFAULT)


def holder(path: Path) -> str:
    """``pid <n> (<cmdline>)`` of the process ``/proc/locks`` names on ``path``, else ``unknown``."""
    try:
        st = os.stat(path)
        locks = Path("/proc/locks").read_text()
    except OSError:
        return "unknown"
    for line in locks.splitlines():
        parts = line.split()
        if "->" in parts or len(parts) < 6 or parts[1] != "FLOCK":
            continue
        dev_ino = parts[5].split(":")
        if len(dev_ino) == 3 and int(dev_ino[2]) == st.st_ino:
            pid = parts[4]
            try:
                cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").strip()
            except OSError:
                cmd = b""
            return f"pid {pid} ({cmd.decode(errors='replace')[:120]})"
    return "unknown"


@contextlib.contextmanager
def test_slot(out=None):
    """Hold the workspace test slot for the block; wait, saying for whom, while another holds it."""
    out = sys.stderr if out is None else out
    path = lock_path()
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o666)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"waiting for test slot (held by {holder(path)})", file=out, flush=True)
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def run_many(scns: list[dict], jobs: int, budget_usd: float) -> list[Result]:
    """Every scenario once, at most ``jobs`` at a time; the caller holds the test slot."""
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run_one, scn, budget_usd) for scn in scns]
        results = []
        for future in futures:
            result = future.result()
            print(result.line(), flush=True)
            results.append(result)
    return results


# --- CLI -------------------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="run.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="verb", required=True)
    run = sub.add_parser("run", help="one run of each named scenario")
    run.add_argument("ids", nargs="+")
    run.add_argument("--jobs", type=int, default=1)
    return p


def main(args: list[str] | None = None) -> int:
    ns = parser().parse_args(args)
    if not 1 <= ns.jobs <= MAX_JOBS:
        print(
            f"--jobs {ns.jobs}: at most {MAX_JOBS} sessions run in the test slot", file=sys.stderr
        )
        return 2
    try:
        check_host()
        scns = resolve(ns.ids)
        budget = float(rates().get("run_budget_usd", DEFAULT_RUN_BUDGET_USD))
        temp_root().rmdir()  # refuses a TMPDIR under HOME before the slot is taken
    except (ScenarioError, RefusedError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    with test_slot():
        results = run_many(scns, ns.jobs, budget)
    return 0 if all(r.hit for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
