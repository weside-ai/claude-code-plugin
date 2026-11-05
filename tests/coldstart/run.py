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
The crew's ``board.file`` is pointed into the run's temp directory, so a cold session never reads
or writes the caller's board or served log. Grading: ``grade.py``.

``measure --runs N`` runs every scenario N times (10 for the record) and writes ``rates.json``:
per scenario ``runs``, ``hits``, ``gated`` (true at >= 9/10) and, below that, the ``defect`` line a
human fills in (the process text, card or ``description`` the misses point at); plus the date,
model pin, inputs digest and Claude Code version, and the tokens and wall time of one full run of
the suite. Its caps (``run_budget_usd``, ``release_cap``, ``cost_target_tokens``) are kept.

``release --base <ref>`` runs each scenario ``affected.py`` names for ``<ref>...HEAD`` 3x fresh,
keeps every other scenario's measured rate from ``rates.json``, and prints the receipt block
(``RECEIPT_MARKER`` and a fenced JSON block) to paste into the PR body. Before the first session it
refuses uncommitted suite inputs (the digest reads HEAD) and an affected set whose runs exceed
``release_cap.runs``; a session whose turn comes after ``release_cap.wall_minutes`` does not start
and its scenario is ``not run``. Either cap makes the receipt ``status: red`` with the reason; no
scenario is left out. Tokens over ``cost_target_tokens`` print ``cost over target: <n> > <t>``.

Usage:
  python3 tests/coldstart/run.py run <id>... [--jobs J]
  python3 tests/coldstart/run.py measure --runs 10 [--jobs J]
  python3 tests/coldstart/run.py release --base <ref> [--jobs J]
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import affected
import grade

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
RELEASE_RUNS = 3
GATE_HITS = 9  # of 10: a scenario at or above it is gated (its release runs must all hit)
RECEIPT_MARKER = "<!-- coldstart-receipt -->"


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
    uses: list | None = None

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
    crew = json.loads((REPO / scn["crew"]).read_text(encoding="utf-8"))
    board = dict(crew.get("board") or {})
    board["file"] = str(root / "state" / "board.json")  # never the caller's board or served log
    crew["board"] = board
    (repo / ".weside" / "crew.json").write_text(json.dumps(crew, indent=2), encoding="utf-8")
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
        answer, uses, tokens, error = grade.parse_stream(proc.stdout)
        if proc.returncode != 0:
            reason = f"exit {proc.returncode}"
            return Result(scn["sid"], False, reason, tokens, time.monotonic() - start, uses)
        prefix = str(json.loads((REPO / scn["crew"]).read_text()).get("skill_prefix") or "")
        hit, reason = grade.grade(scn["expect"] or {}, answer, uses, prefix)
        if answer is None and error:
            reason = error
        if hit and grade.refires(scn):
            diff = grade.refire_diff(repo, child_env(scn))
            hit, reason = (False, diff) if diff else (hit, reason)
        if hit and scn.get("judge"):
            hit, reason = grade.judge(str(scn["judge"]), answer)
        return Result(scn["sid"], hit, reason, tokens, time.monotonic() - start, uses)
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


def run_many(
    scns: list[dict], jobs: int, budget_usd: float, deadline: float | None = None
) -> list[Result | None]:
    """Each scenario once, at most ``jobs`` at a time, in order; the caller holds the test slot.
    A run whose turn comes after ``deadline`` (monotonic) does not start: its entry is None."""

    def one(scn: dict) -> Result | None:
        if deadline is None:
            return run_one(scn, budget_usd)
        left = deadline - time.monotonic()
        if left <= 0:
            return None
        return run_one(scn, budget_usd, timeout=min(TIMEOUT_S, left))

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(one, scn) for scn in scns]
        results = []
        for scn, future in zip(scns, futures):
            result = future.result()
            print(result.line() if result else f"{scn['sid']} not run (wall cap)", flush=True)
            results.append(result)
    return results


# --- release ---------------------------------------------------------------------------------


def plugin_version() -> str:
    return json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]


def receipt(base: str, ids: set[str], results: list, cap_reason: str, table: dict) -> dict:
    """The receipt of a ``release`` run: affected scenarios with their runs, the rest by rate."""
    rows, tokens, wall = [], 0, 0.0
    measured = table.get("scenarios") or {}
    for sid in sorted(affected.scenarios()):
        rate = measured.get(sid) or {}
        if sid in ids:
            mine = [r for s, r in results if s == sid]
            done = [r for r in mine if r is not None]
            tokens += sum(r.tokens for r in done)
            wall += sum(r.wall_s for r in done)
            rows.append(
                {
                    "id": sid,
                    "runs": len(done),
                    "hits": sum(1 for r in done if r.hit),
                    "gated": bool(rate.get("gated", True)),
                    "status": "run" if len(done) == RELEASE_RUNS else "not run",
                }
            )
        else:
            rows.append(
                {
                    "id": sid,
                    "runs": int(rate.get("runs", 0)),
                    "hits": int(rate.get("hits", 0)),
                    "gated": bool(rate.get("gated", False)),
                    "status": "rate" if rate else "unmeasured",
                }
            )
    reasons = [cap_reason] if cap_reason else []
    for row in rows:
        if row["id"] not in ids:
            continue
        if row["status"] == "not run":
            reasons.append(f"not run {row['id']}")
        elif row["gated"] and row["hits"] < RELEASE_RUNS:
            reasons.append(f"gated miss {row['id']} {row['hits']}/{row['runs']}")
    return {
        "status": "red" if reasons else "green",
        "reasons": reasons,
        "digest": affected.digest(ids),
        "base": base,
        "plugin_version": plugin_version(),
        "model": f"{MODEL} {EFFORT}",
        "affected": sorted(ids),
        "runs": sum(r["runs"] for r in rows if r["id"] in ids),
        "tokens": tokens,
        "wall_s": round(wall, 1),
        "scenarios": rows,
    }


def print_receipt(block: dict) -> None:
    print(RECEIPT_MARKER)
    print("```json")
    print(json.dumps(block, indent=1))
    print("```")


def cost_line(tokens: int, table: dict) -> str:
    target = table.get("cost_target_tokens")
    if target and tokens > int(target):
        return f"cost over target: {tokens} > {target}"
    return ""


def release(base: str, jobs: int, budget: float, table: dict) -> int:
    ids = affected.affected(base)
    if not ids:
        print("no suite input changed")
        print_receipt(receipt(base, ids, [], "", table))
        return 0
    cap = table.get("release_cap") or {}
    needed = len(ids) * RELEASE_RUNS
    cap_runs = int(cap.get("runs", 0))
    if needed > cap_runs:
        print_receipt(receipt(base, ids, [], f"cap runs {needed} > {cap_runs}", table))
        return 1
    scns = [s for s in resolve(sorted(ids)) for _ in range(RELEASE_RUNS)]
    print(f"affected: {', '.join(sorted(ids))} ({needed} runs)")
    wall_min = float(cap.get("wall_minutes", 0))
    with test_slot():
        deadline = time.monotonic() + wall_min * 60
        results = run_many(scns, jobs, budget, deadline)
    pairs = [(s["sid"], r) for s, r in zip(scns, results)]
    cap_reason = f"cap wall {wall_min:g} min" if any(r is None for _, r in pairs) else ""
    block = receipt(base, ids, pairs, cap_reason, table)
    print_receipt(block)
    line = cost_line(block["tokens"], table)
    if line:
        print(line)
    return 0 if block["status"] == "green" else 1


# --- measure ---------------------------------------------------------------------------------


def measure(runs: int, jobs: int, budget: float, table: dict) -> int:
    """Every scenario ``runs``x; writes the rates into ``rates.json``, keeping its caps and every
    ``defect`` line of a scenario that is still below the entry rule."""
    scns = [load(p) for p in scenario_paths()]
    batch = [s for s in scns for _ in range(runs)]
    with test_slot():
        results = run_many(batch, jobs, budget)
    old = table.get("scenarios") or {}
    rows = {}
    for scn in scns:
        mine = [r for s, r in zip(batch, results) if s["sid"] == scn["sid"] and r is not None]
        hits = sum(1 for r in mine if r.hit)
        row = {"runs": len(mine), "hits": hits, "gated": hits * 10 >= GATE_HITS * len(mine)}
        if not row["gated"]:
            row["defect"] = (old.get(scn["sid"]) or {}).get("defect")
        rows[scn["sid"]] = row
    done = [r for r in results if r is not None]
    table = dict(table)
    table["measured"] = {
        "date": time.strftime("%Y-%m-%d", time.gmtime()),
        "model": f"{MODEL} {EFFORT}",
        "digest": affected.digest(set(rows)),
        "runs_per_scenario": runs,
        "claude_code": claude_version(),
    }
    table["suite_tokens_one_run"] = round(sum(r.tokens for r in done) / runs)
    table["suite_wall_s_one_run"] = round(sum(r.wall_s for r in done) / runs, 1)
    table["scenarios"] = rows
    RATES.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
    for sid, row in rows.items():
        flag = "gated" if row["gated"] else "NOT gated: name its defect in rates.json"
        print(f"{sid} {row['hits']}/{row['runs']} {flag}")
    print(f"suite tokens one run: {table['suite_tokens_one_run']}")
    return 0


def claude_version() -> str:
    try:
        proc = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=30, check=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown"
    return proc.stdout.split(" ", 1)[0].strip() or "unknown"


# --- CLI -------------------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="run.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="verb", required=True)
    run = sub.add_parser("run", help="one run of each named scenario")
    run.add_argument("ids", nargs="+")
    run.add_argument("--jobs", type=int, default=1)
    mea = sub.add_parser("measure", help="every scenario N times, rates into rates.json")
    mea.add_argument("--runs", type=int, default=10)
    mea.add_argument("--jobs", type=int, default=1)
    rel = sub.add_parser("release", help="the affected scenarios 3x each, then the receipt")
    rel.add_argument("--base", required=True)
    rel.add_argument("--jobs", type=int, default=1)
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
        table = rates()
        budget = float(table.get("run_budget_usd", DEFAULT_RUN_BUDGET_USD))
        temp_root().rmdir()  # refuses a TMPDIR under HOME before the slot is taken
        if ns.verb == "release":
            dirty = affected.dirty_inputs()
            if dirty:
                raise RefusedError(f"uncommitted suite inputs: {', '.join(dirty)}")
            return release(ns.base, ns.jobs, budget, table)
        if ns.verb == "measure":
            return measure(ns.runs, ns.jobs, budget, table)
        scns = resolve(ns.ids)
    except (ScenarioError, RefusedError, affected.GitError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    with test_slot():
        results = run_many(scns, ns.jobs, budget)
    judged, total = grade.judge_share(scns)
    print(f"judge share: {judged}/{total}")
    return 0 if all(r and r.hit for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
