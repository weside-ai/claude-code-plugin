#!/usr/bin/env python3
"""Carry a receipts job's verdict onto the board (docs/board.md § Acceptance).

Usage:
  accept.py [--board FILE] run --run-id ID
  accept.py [--board FILE] queue

The verdict contract (`accept.json`, version 1; fixture `fixtures/accept/accept_verdict.json`):
`{version, rc, run_id, run_url, stories: [{key, verdict, oracles: {receipt: [n], ci: [n],
walk: [n]}, ci_tests: {n: test}, checks: [{id, ac, persona, status, observed}], walk: [{ac,
persona, screen}], not_proven, owner, reason}]}`. `verdict` is `done`, `walk`, `red` or `hold`.
The repo's job writes it into the artifact `staging-receipts-<rc>` of its RC run; this script
only carries it.

run      takes a run id, never a file. Before anything is downloaded it reads, through one `gh`
         seam (`gh api repos/{owner}/{repo}/actions/runs/<id>`, `git ls-remote --tags origin`):
         (1) the run's `path` is `.weside/config.json` `acceptance.receipts_workflow` and that
         file exists on `origin/main`; (2) its `event` is `push` and its `head_branch` matches
         `acceptance.rc_tag_glob`; (3) its `head_sha` is the tag's peeled commit, an ancestor of
         `origin/main`. A failure exits 1 with `refused: run <id> <reason>`. An artifact listed
         `expired` or not listed exits 1 with `verdict expired, rerun receipts on the RC`. After
         the download (4) the verdict must name exactly that `rc` and `run_id`.
         Then per entry: a key whose last transitions row is `done` prints `skip: <KEY> already
         done`; `done` runs `board.move_done` (the board re-checks the entry); `walk` appends
         one line to board-accept.jsonl (one open line per key across RCs); `red` appends its
         finding and prints `route: <member> <KEY> <check> FAIL — <reason>` (the entry's
         `owner` when it is a crew member, else `roles.coordinator`); `hold` prints `hold: <KEY>
         <reason>`. A (key, rc) already logged is skipped, so a rerun writes nothing twice. One
         `carry:` line holds every op, last. A refused entry prints its lines and the run goes
         on; the exit is then 1. An unreadable verdict exits 2.
queue    the open walks: `<KEY> AC<n> <persona> · <screen> (rc <rc>)` per key whose last
         transitions row is not `done`, else `queue: empty`.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import board  # noqa: E402
import crew as crew_mod  # noqa: E402
import ticket_adapter  # noqa: E402

VERSION = 1
VERDICTS = ("done", "walk", "red", "hold")
EXPIRED = "verdict expired, rerun receipts on the RC"
GH_TIMEOUT = 60


class AcceptError(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


class Gh:
    """The one seam to GitHub and the remote: every read `run` makes before it trusts a verdict."""

    def __init__(self, cwd=None):
        self.cwd = cwd

    def _out(self, argv, what):
        try:
            done = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=GH_TIMEOUT,
                check=False,
                cwd=self.cwd,
            )
        except FileNotFoundError:
            raise AcceptError(f"{what}: {argv[0]} not found", 2) from None
        except subprocess.TimeoutExpired:
            raise AcceptError(f"{what}: {argv[0]} ran past {GH_TIMEOUT} s", 2) from None
        return done

    def _api(self, path, what):
        done = self._out(["gh", "api", path], what)
        if done.returncode != 0:
            why = (done.stderr.strip().splitlines() or [f"exit {done.returncode}"])[-1]
            raise AcceptError(f"{what}: gh api failed: {why}", 2)
        try:
            return json.loads(done.stdout)
        except ValueError:
            raise AcceptError(f"{what}: gh printed no JSON", 2) from None

    def run(self, run_id):
        return self._api(f"repos/{{owner}}/{{repo}}/actions/runs/{run_id}", f"run {run_id}")

    def artifacts(self, run_id):
        data = self._api(
            f"repos/{{owner}}/{{repo}}/actions/runs/{run_id}/artifacts?per_page=100",
            f"run {run_id} artifacts",
        )
        return data.get("artifacts") or [] if isinstance(data, dict) else []

    def on_main(self, path):
        self._out(["git", "fetch", "-q", "origin", "main"], "git fetch")
        return self._out(["git", "cat-file", "-e", f"origin/main:{path}"], "git").returncode == 0

    def tag_commit(self, tag):
        """The tag's peeled commit on origin, or None."""
        done = self._out(["git", "ls-remote", "--tags", "origin", tag], "git ls-remote")
        plain = peeled = None
        for line in done.stdout.splitlines():
            sha, _, ref = line.partition("\t")
            if ref == f"refs/tags/{tag}^{{}}":
                peeled = sha
            elif ref == f"refs/tags/{tag}":
                plain = sha
        return peeled or plain

    def is_ancestor(self, sha):
        argv = ["git", "merge-base", "--is-ancestor", sha, "origin/main"]
        return self._out(argv, "git merge-base").returncode == 0

    def download(self, run_id, name, dest):
        argv = ["gh", "run", "download", str(run_id), "-n", name, "-D", str(dest)]
        done = self._out(argv, f"run {run_id} download")
        if done.returncode != 0:
            why = (done.stderr.strip().splitlines() or [f"exit {done.returncode}"])[-1]
            raise AcceptError(f"run {run_id}: artifact {name} not downloaded: {why}", 2)
        return Path(dest) / "accept.json"


def acceptance_config(root):
    path = Path(root) / ".weside" / "config.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        config = {}
    except (OSError, ValueError) as exc:
        raise AcceptError(f"{path}: unreadable ({exc})", 2) from None
    section = (config.get("acceptance") if isinstance(config, dict) else None) or {}
    missing = [k for k in ("receipts_workflow", "rc_tag_glob") if not section.get(k)]
    if missing:
        raise AcceptError(
            f"{path}: acceptance.{' and acceptance.'.join(missing)} not set "
            "(the workflow whose RC run uploads the verdict, the RC tag glob)",
            2,
        )
    return section["receipts_workflow"], section["rc_tag_glob"]


def provenance(gh, run_id, workflow, tag_glob):
    """The run's tag after conditions (1) to (3), else AcceptError `refused: run <id> <reason>`."""

    def refuse(reason):
        return AcceptError(f"refused: run {run_id} {reason}")

    run = gh.run(run_id)
    path = str(run.get("path") or "")
    if path.split("@", 1)[0] != workflow or not gh.on_main(workflow):
        raise refuse(f"not the receipts workflow: {path or 'none'}")
    event, tag = run.get("event"), str(run.get("head_branch") or "")
    if event != "push" or not fnmatch.fnmatchcase(tag, tag_glob):
        raise refuse(f"not a push of an RC tag: {event} {tag or 'none'}")
    sha = str(run.get("head_sha") or "")
    if not sha or gh.tag_commit(tag) != sha:
        raise refuse(f"head_sha {sha or 'none'} is not the commit of {tag}")
    if not gh.is_ancestor(sha):
        raise refuse(f"head_sha {sha} of {tag} is not on origin/main")
    return tag, run.get("html_url")


def fetch_verdict(gh, run_id, tag):
    name = f"staging-receipts-{tag}"
    listed = [a for a in gh.artifacts(run_id) if isinstance(a, dict) and a.get("name") == name]
    if not listed or any(a.get("expired") for a in listed):
        raise AcceptError(f"refused: run {run_id} {EXPIRED}")
    with tempfile.TemporaryDirectory(prefix="we-accept-") as tmp:
        path = gh.download(run_id, name, tmp)
        try:
            verdict = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise AcceptError(f"run {run_id}: {name}/accept.json unreadable ({exc})", 2) from None
    if not isinstance(verdict, dict) or verdict.get("version") != VERSION:
        raise AcceptError(f"run {run_id}: accept.json is no version {VERSION} verdict", 2)
    if not isinstance(verdict.get("stories"), list):
        raise AcceptError(f"run {run_id}: accept.json has no stories list", 2)
    if verdict.get("rc") != tag or str(verdict.get("run_id")) != str(run_id):
        raise AcceptError(
            f"refused: run {run_id} verdict names {verdict.get('rc')}/{verdict.get('run_id')}, "
            f"run is {tag}/{run_id}"
        )
    return verdict


class Log:
    """<stem>-accept.jsonl beside the board (`board-accept.jsonl` for board.json): one line per (key, rc) outcome that is not a move."""

    def __init__(self, state):
        self.state = state
        self.path = state.log_path("accept")

    def lines(self):
        return board._read_jsonl(self.path)

    def append(self, line):
        return board._append_jsonl(self.path, line)

    def logged(self, key, rc):
        return any(x.get("key") == key and x.get("rc") == rc for x in self.lines())

    def open_walks(self):
        """`{key: first walk line}` for each key whose last transitions row is not `done`."""
        last = self.state.last_rows()
        out = {}
        for x in self.lines():
            key = x.get("key")
            if x.get("outcome") != "walk" or not isinstance(key, str):
                continue
            if (last.get(key) or {}).get("to") == "done":
                continue
            out.setdefault(key, x)
        return out


def _route_to(crew, owner):
    if isinstance(owner, str) and owner.strip():
        found = crew_mod.member(crew, owner)
        if found:
            return found[0]
    return (crew.get("roles") or {}).get("coordinator") or "roles.coordinator"


def _finding(entry):
    for c in entry.get("checks") or []:
        if not isinstance(c, dict):
            continue
        observed = str(c.get("observed") or "")
        if c.get("status") == "FAIL" or observed.startswith("NOT TESTABLE"):
            return f"{c.get('id') or 'AC' + str(c.get('ac'))} FAIL — {observed}".rstrip(" —")
    return f"FAIL — {entry.get('reason') or 'no failing check named'}"


def _walk_line(entry):
    items = [w for w in entry.get("walk") or [] if isinstance(w, dict)]
    uniq = lambda vals: list(dict.fromkeys(str(v) for v in vals if v))  # noqa: E731
    return {
        "acs": [f"AC{w.get('ac')}" for w in items],
        "persona": ", ".join(uniq(w.get("persona") for w in items)) or None,
        "screen": "; ".join(uniq(w.get("screen") for w in items)) or None,
    }


def _queue_line(x):
    return f"{x['key']} {', '.join(x.get('acs') or [])} {x.get('persona')} · {x.get('screen')} (rc {x.get('rc')})"


def carry_verdict(state, crew, adapter, verdict, now):
    """One pass over the entries; returns (ops, refused)."""
    log, rc, run_url = Log(state), verdict.get("rc"), verdict.get("run_url")
    ops, refused = [], False
    ts = board._iso(now)
    for entry in verdict["stories"]:
        key = entry.get("key") if isinstance(entry, dict) else None
        if not isinstance(key, str):
            print("refused: an entry without a key", file=sys.stderr)
            refused = True
            continue
        kind = entry.get("verdict")
        if (state.last_rows().get(key) or {}).get("to") == "done":
            print(f"skip: {key} already done")
            continue
        if kind == "done":
            try:
                row, moved, sample = board.move_done(
                    state, key, crew, now, adapter, entry=entry, rc=rc, run_url=run_url
                )
            except board.BoardError as exc:
                print(str(exc), file=sys.stderr)
                refused = True
                continue
            print(json.dumps(row, ensure_ascii=False))
            if sample:
                print(sample)
            ops += moved
            continue
        if kind not in VERDICTS:
            print(
                f"refused: {key} verdict {kind!r} is none of {', '.join(VERDICTS)}",
                file=sys.stderr,
            )
            refused = True
            continue
        if log.logged(key, rc):
            print(f"skip: {key} {kind} already recorded for {rc}")
            continue
        if kind == "walk":
            queued = log.open_walks().get(key)
            if queued:
                print(f"skip: {key} walk already queued (rc {queued.get('rc')})")
                continue
            line = log.append(
                {"rc": rc, "key": key, "outcome": "walk", **_walk_line(entry), "ts": ts}
            )
            print("walk: " + _queue_line(line))
        elif kind == "red":
            owner = _route_to(crew, entry.get("owner"))
            finding = _finding(entry)
            log.append(
                {
                    "rc": rc,
                    "key": key,
                    "outcome": "red",
                    "finding": finding,
                    "owner": owner,
                    "ts": ts,
                }
            )
            print(f"route: {owner} {key} {finding}")
        else:
            reason = entry.get("reason") or "no reason given"
            log.append({"rc": rc, "key": key, "outcome": "hold", "reason": reason, "ts": ts})
            print(f"hold: {key} {reason}")
    return ops, refused


def _toplevel():
    done = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise AcceptError("accept.py: not inside a git checkout (no toplevel)", 2)
    return Path(done.stdout.strip())


def cmd_run(state, args, now, adapter, gh):
    workflow, glob = acceptance_config(_toplevel())
    crew = board.load_crew()
    if adapter is None:
        try:
            adapter = ticket_adapter.adapter_for(crew)
        except ValueError as exc:
            raise AcceptError(f"crew: {exc}", 2) from None
    gh = gh or Gh()
    tag, _url = provenance(gh, args.run_id, workflow, glob)
    verdict = fetch_verdict(gh, args.run_id, tag)
    ops, refused = carry_verdict(state, crew, adapter, verdict, now)
    board._print_carry(ops)
    return 1 if refused else 0


def cmd_queue(state, args, now, adapter, gh):
    walks = Log(state).open_walks()
    print("\n".join(_queue_line(x) for x in walks.values()) if walks else "queue: empty")
    return 0


def parser():
    p = argparse.ArgumentParser(prog="accept.py", description="Carry a receipts job's verdict.")
    p.add_argument(
        "--board", help="the board file (default: the crew's board.file, else board.py's default)"
    )
    verbs = p.add_subparsers(dest="verb", required=True)
    r = verbs.add_parser("run", help="carry the verdict of one RC run")
    r.add_argument("--run-id", dest="run_id", required=True)
    r.set_defaults(run=cmd_run)
    q = verbs.add_parser("queue", help="the open walks")
    q.set_defaults(run=cmd_queue)
    return p


def main(argv=None, now=None, adapter=None, gh=None):
    """`adapter` and `gh` are the tests' fakes; None means the crew's transport and `Gh()`."""
    args = parser().parse_args(argv)
    try:
        state = board.StateDir(args.board or board.default_board())
        return args.run(state, args, now or board._now(), adapter, gh)
    except (AcceptError, board.BoardError) as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
