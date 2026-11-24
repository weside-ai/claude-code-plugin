#!/usr/bin/env python3
"""The flow report: the loop's numbers in one table, each row with n, median, p90 and its source.

Usage:
  flow_report.py [--since 10d] [--until UTC] [--repo OWNER/NAME] [--json|--md] [--board FILE]
                 [--gh-cache DIR] [--review-match REGEX] [--from FILE]…

``--since`` takes ``<n>d``, ``<n>h`` or a UTC date ``YYYY-MM-DD``; the window ends now. ``--repo``
defaults to the ``origin`` remote of the current directory. Plain output is an aligned table;
``--json`` prints the rows as one JSON object; ``--md`` prints a Markdown table and writes it to
``reports/flow-<UTC date>.md`` in the repo's optimization store (``.weside/optimization/``,
``references/optimization-store.md``); without a store it writes nothing and says so on stderr.
``--gh-cache DIR`` keeps every ``gh`` answer in DIR and reuses it on the next run with the same
window (pin it with ``--until``), so a second run costs no API quota. ``--review-match`` names
the review workflows (regex, default ``review``).

Sources (read only; the script holds no credential):

- GitHub through ``gh api graphql`` (the session's login): PRs merged in the window and every open
  PR, their files, labels, commits and force pushes, and per commit the GitHub Actions check
  suites. A head is a commit or force-pushed SHA with a ``pull_request`` or
  ``pull_request_target`` suite; heads are ordered by their first suite. A PR is docs-only when
  every changed path is under ``docs/`` or ends in ``.md``; every other PR is a code PR.
- The transitions log ``<board stem>-transitions.jsonl`` beside the board file
  (``crew.resolve_board``; ``--board`` names another). Without a crew file and
  without ``--board`` the board rows print ``n/a``: the default board belongs to no repo.
- The question log ``<board stem>-questions.jsonl`` joined with ``<stem>-answers.jsonl`` by ``id``
  (``docs/board.md`` § Asking), and ``brakes.jsonl`` in the crew's state directory
  (``worker_rights.brake_log`` owns its lines): ``Brakes per day`` by type, ``Brake outcomes`` per
  type with its ``outcome`` lines' ``danger`` (``no`` is a false alarm) and the lines no one judged.
- The required checks of the default branch, live from its rulesets and branch protection
  (``required_checks.sh``, the reader ``arm_pr.sh`` uses), and per head the runs of every check
  (all attempts of a check run, the last state of a status). ``Required checks: red heads``
  counts per required check the heads of the window's PRs on which it concluded red (``RED``),
  each once by its outcome: ``rerun green`` (the same head later shows it green: a false alarm),
  ``fixed`` (a later head of the PR shows it green), else ``open``. Without a required check the
  row is ``n/a``. A required check named in ``flow.construction_checks`` of the repo's
  ``.weside/config.json`` (red by construction until a release commit, such as a version check)
  stays out of that row: ``Required checks: red by construction`` shows its heads as
  ``<name> <n> by construction``.
- ``lens_verdict.rounds`` for the Ready rounds of every key in the repo's severity log.
- The ``Tests:`` line ``test-delta.py`` writes into a PR body: new test functions and cases per
  merged code PR. An escape is a story's move out of Done in the window; its class comes from the
  risk labels of the key's merged code PRs (``routine`` without one).

A row whose source is missing prints ``n/a (<source> not found)``, never a zero. Exit 0 whenever a
table is printed, 2 on a usage error.

``Transition writers: In Review`` counts the window's moves to In Review by their ``by``: ``we-worker
close`` is the one writer (``worker_close.py``), any other writer bypassed it.

Last, the section ``Flow efficiency`` prints story, master and worker efficiency, the
group ``Waiting by kind``, the locks held and every gap of its sources, all as the strings of
``flow_intervals.format_summary`` (the flow page prints the same); ``--from FILE`` (repeatable)
adds a file of foreign interval rows (``flow_intervals.py`` § Row contract). It counts only the
rows of the board's project (``flow_intervals.py`` § Project): ``Flow project`` names it with the
rows kept and dropped, every drop is a ``Flow gap: project`` line. Without a board it prints
``n/a`` like the other board rows.

After the table, ``Writers per transition`` lists per transition kind (``from→to``) which
sessions (the row's ``by``) wrote it in the window: a transition the report trusts has one writer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import crew as crew_mod  # noqa: E402
import flow_intervals  # noqa: E402
import lens_verdict  # noqa: E402
import worker_supervisor  # noqa: E402
from flow_intervals import (  # noqa: E402  (one home: the lower module)
    hours,
    locate_board,
    p90,
    parse_since,
    parse_ts,
    question_waits,
    read_jsonl,
)

ACTIONS_APP_ID = 15368  # the GitHub Actions app: its check suites are workflow runs
RED = {"FAILURE", "TIMED_OUT", "STARTUP_FAILURE", "ACTION_REQUIRED"}
HEAD_EVENTS = {"pull_request", "pull_request_target"}  # a push to the PR's branch; reviews are not
DONE_LIKE = {"in_review", "in_test", "done"}
SHARE_STATES = ("selected", "in_progress", "in_review", "in_test")
COMMIT_BATCH = 100
DEFAULT_KEY = crew_mod.DEFAULTS["naming"]["key"]

PR_QUERY = """
query($q: String!, $after: String) {
  search(query: $q, type: ISSUE, first: 50, after: $after) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes { ... on PullRequest {
      number title body headRefName state isDraft createdAt mergedAt
      labels(first: 30) { nodes { name } }
      files(first: 100) { totalCount nodes { path } }
      timelineItems(first: 100, itemTypes: [PULL_REQUEST_COMMIT, HEAD_REF_FORCE_PUSHED_EVENT]) {
        nodes { __typename
          ... on PullRequestCommit { commit { id oid } }
          ... on HeadRefForcePushedEvent { beforeCommit { id oid } afterCommit { id oid } }
        }
      }
    } }
  }
}
"""

SUITE_QUERY = """
query($ids: [ID!]!) {
  nodes(ids: $ids) { ... on Commit { oid
    checkSuites(first: 20, filterBy: {appId: APP_ID}) { nodes {
      status conclusion createdAt workflowRun { event workflow { name } }
    } }
  } }
}
""".replace("APP_ID", str(ACTIONS_APP_ID))


CHECKS_QUERY = """
query($ids: [ID!]!) {
  nodes(ids: $ids) { ... on Commit { oid
    checkSuites(first: 30) { nodes {
      createdAt
      checkRuns(first: 50, filterBy: {checkType: ALL}) { nodes { name status conclusion startedAt completedAt } }
    } }
    status { contexts { context state createdAt } }
  } }
}
"""
GREEN = {"SUCCESS", "NEUTRAL", "SKIPPED"}


class SourceMissingError(Exception):
    """A source the report cannot read; its message is the `n/a (...)` text."""


# --- small helpers ------------------------------------------------------------------------------


def med(values: list) -> float | None:
    return statistics.median(values) if values else None


def pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.0f} %" if whole else "-"


def row(name, n=None, median=None, p90_=None, value="", source="", unit=""):
    return {
        "row": name,
        "n": n,
        "median": median,
        "p90": p90_,
        "unit": unit,
        "value": value,
        "source": source,
    }


def na(name: str, why: str) -> dict:
    return row(name, value=f"n/a ({why})", source="")


# --- GitHub -------------------------------------------------------------------------------------


Runner = Callable[[dict], dict]
PART_MAX_AGE_S = 600  # a write older than this has no thread left to finish it


def gh_runner(cache: Path | None, window: str = "", ttl: float | None = None) -> Runner:
    """`body -> response` through `gh api graphql --input -`; with `cache`, answers are kept there
    by a hash of the body and the `window` (`<since>..<until>`) and read back instead of asked
    again: the open-PR search and the suites carry no window of their own, so another window
    asks GitHub afresh. With `ttl` (seconds), a kept answer older than that is asked again.
    `run.fetched` collects each answer's fetch time (the cached file's mtime on a hit), read by
    `command_center/ci_source.py` as its `fetched_at`. Safe to call from several threads.
    A caller that gave up on a slow call leaves its `*.part` behind; the next runner on the cache
    removes those older than `PART_MAX_AGE_S`."""
    fetched: list = []
    if cache is not None and cache.is_dir():
        for part in cache.glob("*.part"):
            try:
                if time.time() - part.stat().st_mtime > PART_MAX_AGE_S:
                    part.unlink()
            except OSError:  # another runner removed it first
                pass

    def run(body: dict) -> dict:
        text = json.dumps(body, sort_keys=True)
        hit = None
        if cache is not None:
            digest = hashlib.sha256((window + "\n" + text).encode()).hexdigest()[:20]
            hit = cache / (digest + ".json")
            if hit.is_file() and (ttl is None or time.time() - hit.stat().st_mtime <= ttl):
                fetched.append(hit.stat().st_mtime)
                return json.loads(hit.read_text(encoding="utf-8"))
        try:
            out = subprocess.run(
                ["gh", "api", "graphql", "--input", "-"],
                input=text,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except FileNotFoundError:
            raise SourceMissingError("gh not found") from None
        except subprocess.SubprocessError as exc:
            raise SourceMissingError(f"gh: {exc}") from None
        if out.returncode != 0:
            first = (out.stderr or out.stdout).strip().splitlines()[:1]
            raise SourceMissingError(f"gh: {first[0] if first else 'exit ' + str(out.returncode)}")
        data = json.loads(out.stdout)
        if data.get("errors"):
            raise SourceMissingError(f"gh: {data['errors'][0].get('message', 'error')}")
        if hit is not None:
            hit.parent.mkdir(parents=True, exist_ok=True)
            part = hit.with_name(f"{hit.name}.{threading.get_ident()}.part")
            part.write_text(out.stdout, encoding="utf-8")
            part.replace(hit)  # a reader in another thread never sees half a file
        fetched.append(time.time())
        return data

    run.fetched = fetched  # type: ignore[attr-defined]
    return run


def _day_chunks(since: datetime, until: datetime):
    start = since
    while start < until:
        end = min(start + timedelta(days=1), until)
        yield start, end
        start = end


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _search(run: Runner, q: str) -> list:
    nodes, after = [], None
    while True:
        data = run({"query": PR_QUERY, "variables": {"q": q, "after": after}})
        found = data["data"]["search"]
        nodes += [n for n in found["nodes"] if n]
        if not found["pageInfo"]["hasNextPage"]:
            return nodes
        after = found["pageInfo"]["endCursor"]


def pmap(fn: Callable, items: list, pool: int = 1) -> list:
    """`[fn(x) for x in items]` on up to `pool` daemon threads, results in order; the first
    failure by position is raised once all ran. Daemon threads: a caller that gives up waiting
    does not hold the process open at exit."""
    if pool <= 1 or len(items) <= 1:
        return [fn(x) for x in items]
    results: list = [None] * len(items)
    errors: list = [None] * len(items)
    lock = threading.Lock()
    todo = iter(range(len(items)))

    def work():
        while True:
            with lock:
                i = next(todo, None)
            if i is None:
                return
            try:
                results[i] = fn(items[i])
            except Exception as exc:  # re-raised below in order
                errors[i] = exc

    threads = [threading.Thread(target=work, daemon=True) for _ in range(min(pool, len(items)))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for exc in errors:
        if exc is not None:
            raise exc
    return results


def fetch_prs(
    run: Runner,
    repo: str,
    since: datetime,
    until: datetime,
    checks: bool = False,
    open_prs: bool = True,
    pool: int = 1,
) -> list:
    """Every PR merged in the window (searched one day at a time: search stops at 1,000) and,
    with `open_prs`, every open PR, each with `heads` and `suites` from its commits' Actions
    suites; with `checks`, each head also carries `checks` (`head_checks`). `pool` > 1 asks the
    day searches and suite batches on that many threads; the result is the same."""
    queries = [
        f"repo:{repo} is:pr is:merged merged:{_iso(a)}..{_iso(b)}"
        for a, b in _day_chunks(since, until)
    ]
    if open_prs:
        queries.append(f"repo:{repo} is:pr is:open")
    by_number: dict = {}
    for found in pmap(lambda q: _search(run, q), queries, pool):
        for pr in found:
            by_number[pr["number"]] = pr
    prs = [by_number[k] for k in sorted(by_number)]
    ids, node_id = [], {}
    for pr in prs:
        for item in pr["timelineItems"]["nodes"]:
            for field in ("commit", "beforeCommit", "afterCommit"):
                if (item.get(field) or {}).get("id"):
                    ids.append(item[field]["id"])
                    node_id[item[field]["oid"]] = item[field]["id"]
    suites: dict = {}
    unique = list(dict.fromkeys(ids))
    batches = [unique[i : i + COMMIT_BATCH] for i in range(0, len(unique), COMMIT_BATCH)]
    for data in pmap(
        lambda ids: run({"query": SUITE_QUERY, "variables": {"ids": ids}}), batches, pool
    ):
        for node in data["data"]["nodes"]:
            if node and node.get("oid"):
                suites[node["oid"]] = node["checkSuites"]["nodes"]
    shaped = [shape_pr(pr, suites, node_id) for pr in prs]
    if checks:
        heads = [h for p in shaped for h in p["heads"]]
        found = head_checks(run, [node_id[h["oid"]] for h in heads if h["oid"] in node_id])
        for h in heads:
            h["checks"] = found.get(h["oid"], {})
    return shaped


def head_checks(run: Runner, ids: list) -> dict:
    """`{oid: {check name: [(time, conclusion), …] by time}}` for the commits `ids`: every
    attempt of a check run, the last state of a status context."""
    out: dict = {}
    unique = list(dict.fromkeys(ids))
    for i in range(0, len(unique), COMMIT_BATCH):
        data = run({"query": CHECKS_QUERY, "variables": {"ids": unique[i : i + COMMIT_BATCH]}})
        for node in data["data"]["nodes"]:
            if not node or not node.get("oid"):
                continue
            runs: dict = defaultdict(list)
            for suite in (node.get("checkSuites") or {}).get("nodes") or []:
                for cr in (suite.get("checkRuns") or {}).get("nodes") or []:
                    if cr.get("status") == "COMPLETED" and cr.get("conclusion"):
                        runs[cr["name"]].append(
                            (parse_ts(cr.get("completedAt")), cr["conclusion"])
                        )
            for ctx in ((node.get("status") or {}).get("contexts")) or []:
                state = {"SUCCESS": "SUCCESS", "FAILURE": "FAILURE", "ERROR": "FAILURE"}
                if ctx.get("state") in state:
                    runs[ctx["context"]].append(
                        (parse_ts(ctx.get("createdAt")), state[ctx["state"]])
                    )
            low = datetime.min.replace(tzinfo=timezone.utc)
            out[node["oid"]] = {k: sorted(v, key=lambda r: r[0] or low) for k, v in runs.items()}
    return out


def required_checks(repo: str, branch: str | None = None) -> list:
    """The required check names of `branch` (default: the default branch) through
    `required_checks.sh` (the one reader, shared with `arm_pr.sh`); a failure raises
    `SourceMissingError`."""
    try:
        out = subprocess.run(
            [
                "bash",
                str(HERE / "required_checks.sh"),
                "--repo",
                repo,
                *([branch] if branch else []),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.SubprocessError as exc:
        raise SourceMissingError(f"gh: {exc}") from None
    lines = [line for line in out.stdout.splitlines() if line.strip()]
    if out.returncode != 0:
        why = lines[-1] if lines else f"exit {out.returncode}"
        raise SourceMissingError(why.replace("gh failed: ", "gh: ", 1))
    return lines


# --- one open PR's state, by arm_pr.sh's rule ------------------------------------------------
#
# A copy of `arm_pr.sh`'s query (`READ`), its check classes (`JQ`) and its `verdict()`: the command
# centre (`command_center/open_ends.py`) reads them and no merge decision does, so the brake itself
# stays in `arm_pr.sh` alone. `command_center/test_pr_state.py` runs `arm_pr.sh`'s own `JQ` and
# `verdict()` against this copy and fails on any drift.

PR_STATE_FIELDS = """
  id number title body state isDraft createdAt headRefName headRefOid baseRefName mergeStateStatus
  reviewDecision autoMergeRequest { enabledAt } labels(first: 100) { nodes { name } }
  commits(last: 1) { nodes { commit { oid committedDate statusCheckRollup { contexts(first: 100) {
    nodes { __typename
      ... on CheckRun { name status conclusion isRequired(pullRequestNumber: NUMBER)
                        startedAt completedAt checkSuite { createdAt } }
      ... on StatusContext { context state isRequired(pullRequestNumber: NUMBER) createdAt }
    } } } } } }
"""

OPEN_PRS_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { name target { ... on Commit { oid statusCheckRollup { state
      contexts(first: 100) { nodes { __typename
        ... on CheckRun { name status conclusion startedAt checkSuite { createdAt } }
        ... on StatusContext { context state createdAt }
      } } } } } }
    pullRequests(states: OPEN, first: 50, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage }
      nodes { number }
    }
  }
}
"""


def pr_states_query(numbers: list) -> str:
    """One query for several PRs: an aliased `pullRequest` per number, each with its own
    `isRequired(pullRequestNumber:)` (GraphQL takes no per-node variable)."""
    parts = [
        f"pr{int(n)}: pullRequest(number: {int(n)}) {{"
        + PR_STATE_FIELDS.replace("NUMBER", str(int(n)))
        + "}"
        for n in numbers
    ]
    return (
        "query($owner: String!, $name: String!) {\n"
        "  repository(owner: $owner, name: $name) {\n" + "\n".join(parts) + "\n  }\n}\n"
    )


def context_class(node: dict) -> str:
    """`pass`, `pending` or `fail` of one rollup context: `arm_pr.sh`'s `JQ`."""
    if node.get("__typename") == "StatusContext":
        state = node.get("state")
        if state == "SUCCESS":
            return "pass"
        return "pending" if state in ("PENDING", "EXPECTED") else "fail"
    # A set conclusion is the verdict whatever the status says (GitHub can leave a completed
    # check run at IN_PROGRESS beside its conclusion); none and not COMPLETED is pending.
    if node.get("conclusion"):
        return "pass" if node.get("conclusion") in GREEN else "fail"
    if node.get("status") != "COMPLETED":
        return "pending"
    return "fail"


def head_contexts(pr: dict) -> list:
    """`[{name, v, required, status, since}]` of the PR's head commit (`JQ`'s check lines; a last
    commit that is not `headRefOid` lists none). `since`: when a pending context began waiting
    (a check run's `startedAt`, a queued run's suite `createdAt`, a status context's `createdAt`)."""
    commit = (((pr.get("commits") or {}).get("nodes") or [{}])[0] or {}).get("commit") or {}
    if commit.get("oid") != pr.get("headRefOid"):
        return []
    out = []
    for node in ((commit.get("statusCheckRollup") or {}).get("contexts") or {}).get("nodes") or []:
        if not node:
            continue
        since = node.get("createdAt") or node.get("startedAt")
        if node.get("__typename") != "StatusContext" and not node.get("startedAt"):
            since = (node.get("checkSuite") or {}).get("createdAt")
        out.append(
            {
                "name": node.get("name") or node.get("context"),
                "v": context_class(node),
                "required": node.get("isRequired") is True,
                "status": node.get("status") or node.get("state"),
                "since": since,
                "completed": node.get("completedAt"),
            }
        )
    return out


def pr_verdict(checks: list, required: list) -> tuple:
    """`(pending | pass | fail, [failing names])`: `arm_pr.sh`'s `verdict()`. A required name with
    no check on the head is pending (absent is not green); a check GitHub marks required for this
    PR counts too; with no required check at all every registered check must pass."""
    fails, pending = [], False
    for name in required:
        vs = [c["v"] for c in checks if c["name"] == name]  # every line of the name, as awk
        if "fail" in vs:
            fails.append(name)
        elif not vs or "pending" in vs:
            pending = True
    for c in checks:
        if c["name"] in required:
            continue
        if c["required"] or not required:
            if c["v"] == "fail":
                fails.append(c["name"])
            elif c["v"] == "pending":
                pending = True
    if fails:
        return "fail", fails
    if not checks or pending:
        return "pending", []
    return "pass", []


def pending_required(checks: list, required: list) -> list:
    """The required names (branch list plus `isRequired`) still pending or absent on the head:
    `arm_pr.sh`'s `pending_line`."""
    names = set(required) | {c["name"] for c in checks if c["required"]}
    out = []
    for name in sorted(names):
        vs = [c["v"] for c in checks if c["name"] == name]
        if not vs or "pending" in vs:
            out.append(name)
    return out


def open_pr_states(run: Runner, repo: str, numbers: list) -> dict:
    """`{number: PR node}` (fields `PR_STATE_FIELDS`) through the `Runner`."""
    if not numbers:
        return {}
    owner, name = repo.split("/", 1)
    data = run({"query": pr_states_query(numbers), "variables": {"owner": owner, "name": name}})
    repo_node = data["data"]["repository"] or {}
    return {int(n): repo_node.get(f"pr{int(n)}") for n in numbers if repo_node.get(f"pr{int(n)}")}


def open_pr_state(run: Runner, repo: str, number: int) -> dict | None:
    """One PR's node: `arm_pr.sh`'s query with the times."""
    return open_pr_states(run, repo, [number]).get(int(number))


def shape_pr(pr: dict, suites: dict, node_ids: dict | None = None) -> dict:
    """The fields the rows read: times, docs-only, labels and the heads with their runs."""
    files = pr.get("files") or {}
    paths = [f["path"] for f in files.get("nodes") or []]
    docs_only = bool(paths) and len(paths) >= (files.get("totalCount") or 0)
    docs_only = docs_only and all(p.startswith("docs/") or p.endswith(".md") for p in paths)
    oids = []
    for item in pr["timelineItems"]["nodes"]:
        for field in ("commit", "beforeCommit", "afterCommit"):
            oid = (item.get(field) or {}).get("oid")
            if oid and oid not in oids:
                oids.append(oid)
    heads = []
    for oid in oids:
        runs = [
            s
            for s in suites.get(oid) or []
            if (s.get("workflowRun") or {}).get("event") in HEAD_EVENTS
        ]
        if runs:
            first = min(
                parse_ts(s.get("createdAt")) or datetime.max.replace(tzinfo=timezone.utc)
                for s in runs
            )
            heads.append(
                {"oid": oid, "first": first, "runs": runs, "node_id": (node_ids or {}).get(oid)}
            )
    heads.sort(key=lambda h: h["first"])
    return {
        "number": pr["number"],
        "title": pr.get("title") or "",
        "branch": pr.get("headRefName") or "",
        "state": pr.get("state"),
        "created": parse_ts(pr.get("createdAt")),
        "merged": parse_ts(pr.get("mergedAt")),
        "labels": [n["name"] for n in (pr.get("labels") or {}).get("nodes") or []],
        "docs_only": docs_only,
        "heads": heads,
        "tests": tests_line(pr.get("body") or ""),
    }


TESTS_LINE = re.compile(
    r"^Tests: \+(\d+) / -(\d+)(?: functions, \+(\d+) / -(\d+) cases)?", re.MULTILINE
)


def tests_line(body: str) -> tuple | None:
    """(new functions, new cases or None) from the PR body's `Tests:` line (`test-delta.py`)."""
    found = TESTS_LINE.search(body)
    if not found:
        return None
    return int(found.group(1)), int(found.group(3)) if found.group(3) else None


def story_key(pr: dict, pattern: str) -> str | None:
    """The ticket key in the title, else in the branch (any case, returned upper case)."""
    found = re.search(pattern, pr["title"])
    if found:
        return found.group(0)
    found = re.search(pattern, pr["branch"]) or re.search(pattern, pr["branch"], re.IGNORECASE)
    return found.group(0).upper() if found else None


def risk_class(labels: list) -> str | None:
    for name in labels:
        if (
            re.fullmatch(r"T[0-3]", name)
            or "one-way" in name.lower()
            or name.lower().startswith("risk")
        ):
            return name
    return None


# --- GitHub rows --------------------------------------------------------------------------------


def github_rows(prs: list, since: datetime, review_match: str, src: str) -> list:
    in_window = [
        p
        for p in prs
        if (p["merged"] and p["merged"] >= since) or (p["created"] and p["created"] >= since)
    ]
    merged_code = [p for p in in_window if p["merged"] and not p["docs_only"]]
    rows = []

    open_merge = [hours(p["created"], p["merged"]) for p in merged_code if p["created"]]
    rows.append(
        row(
            "PR open → merge",
            len(open_merge),
            med(open_merge),
            p90(open_merge),
            unit="h",
            source=f"{src}: code PRs merged in the window",
        )
    )

    heads = [len(p["heads"]) for p in merged_code if p["heads"]]
    one = sum(1 for h in heads if h == 1)
    rows.append(
        row(
            "Heads per code PR",
            len(heads),
            med(heads),
            p90(heads),
            value=f"one head {pct(one, len(heads))}",
            source=f"{src}: SHAs with a pull_request run, merged code PRs",
        )
    )

    docs = sum(1 for p in in_window if p["docs_only"])
    rows.append(
        row(
            "Docs-PR share",
            len(in_window),
            value=f"{docs} docs-only, {pct(docs, len(in_window))}",
            source=f"{src}: merged in the window + open opened in it",
        )
    )

    reviews: dict = defaultdict(list)
    for p in in_window:
        names = defaultdict(int)
        for h in p["heads"]:
            for s in h["runs"]:
                name = ((s.get("workflowRun") or {}).get("workflow") or {}).get("name") or ""
                if re.search(review_match, name, re.IGNORECASE):
                    names[name] += 1 if s.get("conclusion") in RED else 0
        for name, red in names.items():
            reviews[name].append(red)
    if not reviews:
        rows.append(
            row("Review red per PR", 0, value=f"no workflow matching /{review_match}/", source=src)
        )
    for name in sorted(reviews):
        reds = reviews[name]
        hit = sum(1 for r in reds if r)
        rows.append(
            row(
                f"Review red per PR: {name}",
                len(reds),
                med(reds),
                p90(reds),
                value=f"red on {pct(hit, len(reds))} of PRs",
                source=f"{src}: red runs per PR",
            )
        )

    runs = cancelled = newer = 0
    for p in in_window:
        last = p["heads"][-1]["oid"] if p["heads"] else None
        for h in p["heads"]:
            for s in h["runs"]:
                if s.get("status") != "COMPLETED" or s.get("conclusion") == "SKIPPED":
                    continue
                runs += 1
                if s.get("conclusion") == "CANCELLED":
                    cancelled += 1
                    newer += 1 if h["oid"] != last else 0
    rows.append(
        row(
            "CI cancelled share",
            runs,
            value=f"{cancelled} cancelled ({pct(cancelled, runs)}), newer push {pct(newer, cancelled)} of them",
            source=f"{src}: completed non-skipped runs; newer push = a later head exists",
        )
    )

    classes = Counter(risk_class(p["labels"]) for p in merged_code)
    labelled = sum(v for k, v in classes.items() if k)
    rows.append(
        row(
            "Code PRs by risk class",
            labelled,
            value=", ".join(
                f"{k} {v}" for k, v in sorted((k, v) for k, v in classes.items() if k) if k
            )
            or "no class label",
            source=f"{src}: labels T0-T3, one-way, risk*",
        )
    )

    lines = [p["tests"] for p in merged_code if p.get("tests")]
    funcs = [f for f, _ in lines]
    cases = [c for _, c in lines if c is not None]
    rows.append(
        row(
            "New tests per code PR",
            len(funcs),
            med(funcs),
            p90(funcs),
            unit="functions",
            value=f"cases median {_num(med(cases))}, p90 {_num(p90(cases))} (n {len(cases)})",
            source=f"{src}: the Tests: line of merged code PRs (test-delta.py)",
        )
    )
    return rows


CONSTRUCTION_ROW = "Required checks: red by construction"


def construction_checks(root: Path | None) -> list:
    """`flow.construction_checks` of the repo's `.weside/config.json` (default empty): required
    checks that are red by construction until a release commit."""
    if root is None:
        return []
    try:
        config = json.loads((root / ".weside" / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    flow = config.get("flow") if isinstance(config, dict) else None
    names = flow.get("construction_checks") if isinstance(flow, dict) else None
    if not isinstance(names, list):
        return []
    return [n for n in names if isinstance(n, str) and n]


def red_head_rows(
    prs: list,
    required: list | None,
    since: datetime,
    src: str,
    construction: list = (),
    why: str | None = None,
) -> list:
    """`Required checks: red heads` over the required checks outside `construction`, and with
    a construction check among the required ones the row `Required checks: red by construction`
    (its heads red by construction, outside the totals); `n/a (<why>)` when `required` is None."""
    if required is None:
        return [na("Required checks: red heads", why or "required checks not read")]
    built = [c for c in required if c in construction]
    rest = [c for c in required if c not in built]
    out = [
        red_head_row(prs, rest, since, src)
        if rest or not built
        else row(
            "Required checks: red heads",
            0,
            value="every required check is in flow.construction_checks",
            source=f"{src}: required checks, PR heads in the window",
        )
    ]
    if built:
        counts = red_head_row(prs, built, since, src)["checks"]
        out.append(
            row(
                CONSTRUCTION_ROW,
                sum(sum(c.values()) for c in counts.values()),
                value=" · ".join(
                    f"{check} {sum(c.values())} by construction" for check, c in counts.items()
                ),
                source=f"{src}: flow.construction_checks, PR heads in the window",
            )
        )
    return out


def red_head_row(prs: list, required: list, since: datetime, src: str) -> dict:
    """`Required checks: red heads`: per required check, the heads of the window's PRs on which
    it concluded red, by outcome (`rerun green`, `fixed`, `open`; module docstring)."""
    name = "Required checks: red heads"
    if not required:
        return na(name, "no required checks on the default branch")
    in_window = [
        p
        for p in prs
        if (p["merged"] and p["merged"] >= since) or (p["created"] and p["created"] >= since)
    ]
    counts = {c: Counter() for c in required}
    for p in in_window:
        heads = p["heads"]
        for i, h in enumerate(heads):
            for check in required:
                runs = (h.get("checks") or {}).get(check) or []
                reds = [t for t, c in runs if c in RED]
                if not reds:
                    continue
                first_red = reds[0]
                if any(
                    c in GREEN and (t is None or first_red is None or t > first_red)
                    for t, c in runs
                ):
                    counts[check]["rerun green"] += 1
                elif any(
                    c in GREEN
                    for later in heads[i + 1 :]
                    for _, c in (later.get("checks") or {}).get(check) or []
                ):
                    counts[check]["fixed"] += 1
                else:
                    counts[check]["open"] += 1
    total = sum(sum(c.values()) for c in counts.values())
    parts = [
        f"{check} {sum(c.values())} (fixed {c['fixed']}, rerun green {c['rerun green']}, open {c['open']})"
        for check, c in counts.items()
    ]
    out = row(
        name,
        total,
        value=" · ".join(parts),
        source=f"{src}: required checks, PR heads in the window",
    )
    out["checks"] = {check: dict(c) for check, c in counts.items()}
    return out


def story_class(key: str, prs: list, pattern: str) -> str:
    """The risk class of a story from its merged code PRs: one-way wins, else the first class
    label, else `routine`."""
    found = [
        risk_class(p["labels"])
        for p in prs
        if p["merged"] and not p["docs_only"] and story_key(p, pattern) == key
    ]
    found = [c for c in found if c]
    one_way = [c for c in found if "one-way" in c.lower()]
    return (one_way or found or ["routine"])[0]


def escape_row(transitions: list, prs: list, pattern: str, since, until, src: str) -> dict:
    """Stories moved out of Done in the window (an escape), per risk class, over the stories
    that reached Done in it: a rise on routine paths means the test rule is too tight."""
    by_key: dict = defaultdict(list)
    for r in transitions:
        ts = parse_ts(r.get("ts"))
        if isinstance(r.get("key"), str) and ts and isinstance(r.get("to"), str):
            by_key[r["key"]].append((ts, r["to"]))
    escapes: Counter = Counter()
    done: Counter = Counter()
    for key, items in by_key.items():
        items.sort(key=lambda x: x[0])
        cls = None
        for i, (ts, to) in enumerate(items):
            if not (since <= ts <= until):
                continue
            cls = cls or story_class(key, prs, pattern)
            if to == "done":
                done[cls] += 1
            elif i and items[i - 1][1] == "done":
                escapes[cls] += 1
    order = sorted(set(done) | set(escapes), key=lambda c: (c == "routine", c))
    return row(
        "Escapes after Done by risk class",
        sum(escapes.values()),
        value=" · ".join(f"{c} {escapes[c]}/{done[c]}" for c in order) or "no Done in the window",
        source=f"{src}: moves out of Done / Done, class from the key's merged code PRs",
    )


def prs_per_story(prs: list, since: datetime, pattern: str, src: str) -> dict:
    code, every = defaultdict(int), defaultdict(int)
    for p in prs:
        if not (p["merged"] and p["merged"] >= since):
            continue
        key = story_key(p, pattern)
        if not key:
            continue
        every[key] += 1
        if not p["docs_only"]:
            code[key] += 1
    counts = list(code.values())
    mean_all = sum(every.values()) / len(every) if every else 0
    return row(
        "PRs per story",
        len(counts),
        med(counts),
        p90(counts),
        value=f"code PRs per key; mean with docs PRs {mean_all:.2f}",
        source=f"{src}: key /{pattern}/ in title or branch, merged PRs",
    )


# --- board rows ---------------------------------------------------------------------------------


def story_spans(rows: list, since: datetime, until: datetime) -> list:
    """Per story done in the window: `(key, start, done, segments)` from its first entry into
    Selected since the key's previous done (a step back to Selected restarts no clock); `segments` are `(state, from, to)` in log order."""
    by_key: dict = defaultdict(list)
    for r in rows:
        ts = parse_ts(r.get("ts"))
        if isinstance(r.get("key"), str) and ts and isinstance(r.get("to"), str):
            by_key[r["key"]].append((ts, r["to"]))
    out = []
    for key, items in by_key.items():
        items.sort(key=lambda x: x[0])
        for i, (ts, to) in enumerate(items):
            if to != "done" or not (since <= ts <= until):
                continue
            start = None
            for j in range(i - 1, -1, -1):
                if items[j][1] == "done":
                    break
                if items[j][1] == "selected":
                    start = j
            if start is None:
                continue
            segs = [(items[k][1], items[k][0], items[k + 1][0]) for k in range(start, i)]
            out.append((key, items[start][0], ts, segs))
    return out


def board_rows(
    transitions: list,
    prs: list | None,
    pattern: str,
    since: datetime,
    until: datetime,
    src: str,
    gh_why: str | None,
) -> list:
    spans = story_spans(transitions, since, until)
    lead = [hours(s, d) for _, s, d, _ in spans]
    rows = [
        row(
            "Lead time Selected → Done",
            len(lead),
            med(lead),
            p90(lead),
            unit="h",
            source=f"{src}: first Selected since the previous Done, per Done in the window",
        )
    ]

    rows += share_rows(spans, prs, pattern, src, gh_why)
    stock, last = stock_row(transitions, until, src)
    rows.append(stock)
    rows += mismatch_rows(last, prs, pattern, since, src, gh_why)
    return [*rows, in_review_writers(transitions, since, src)]


CLOSER = "we-worker close"  # the one writer of In Review (`worker_close.py`)


def in_review_writers(transitions: list, since: datetime, src: str) -> dict:
    """`Transition writers: In Review`: the moves to In Review in the window and who wrote them;
    the script is the one writer, every other `by` bypassed it."""
    by = Counter(
        r.get("by") or "(no by)"
        for r in transitions
        if r.get("to") == "in_review" and (parse_ts(r.get("ts")) or since - timedelta(1)) >= since
    )
    total = sum(by.values())
    others = [f"{k} {v}" for k, v in by.most_common() if k != CLOSER]
    return row(
        "Transition writers: In Review",
        total,
        value=f"{CLOSER} {by.get(CLOSER, 0)} of {total}"
        + (f"; bypassed by {', '.join(others)}" if others else ""),
        source=f"{src}: `by` of rows to in_review, expected one writer",
    )


def share_rows(spans: list, prs: list | None, pattern: str, src: str, gh_why: str | None) -> list:
    """Per state its share of each story's lead time; In Progress split at the key's first code
    PR when GitHub answered."""
    rows = []
    first_pr: dict = {}
    for p in prs or []:
        key = story_key(p, pattern)
        if key and p["created"] and not p["docs_only"]:
            first_pr[key] = min(first_pr.get(key, p["created"]), p["created"])
    names = {"selected": "Selected", "in_review": "In Review", "in_test": "In Test"}
    shares: dict = defaultdict(list)
    totals: dict = defaultdict(float)
    for key, start, done, segs in spans:
        total = hours(start, done)
        if total <= 0:
            continue
        per: dict = defaultdict(float)
        for state, a, b in segs:
            if state == "in_progress" and prs is not None:
                cut = min(max(first_pr.get(key, b), a), b)
                per["in_progress_no_pr"] += hours(a, cut)
                per["in_progress_pr"] += hours(cut, b)
            elif state == "in_progress":
                per["in_progress_no_pr"] += hours(a, b)
            else:
                per[state] += hours(a, b)
        for state in ("selected", "in_progress_no_pr", "in_progress_pr", "in_review", "in_test"):
            shares[state].append(100 * per[state] / total)
            totals[state] += per[state]
    whole = sum(totals.values())
    labels = {
        "in_progress_no_pr": "In Progress (no PR)" if prs is not None else "In Progress",
        "in_progress_pr": "In Progress (PR open)",
        **names,
    }
    for state in ("selected", "in_progress_no_pr", "in_progress_pr", "in_review", "in_test"):
        name = f"Share of lead time: {labels[state]}"
        if state == "in_progress_pr" and prs is None:
            rows.append(na(name, gh_why or "gh not found"))
            continue
        if state == "in_test" and not totals[state]:
            continue
        vals = shares[state]
        rows.append(
            row(
                name,
                len(vals),
                med(vals),
                p90(vals),
                unit="%",
                value=f"of all lead time {pct(totals[state], whole)}",
                source=f"{src}" + (" + first code PR per key" if "pr" in state and prs else ""),
            )
        )
    return rows


def stock_row(transitions: list, until: datetime, src: str) -> tuple:
    """The stock per state from each key's last row, and that last row per key."""
    last = {}
    for r in transitions:
        if isinstance(r.get("key"), str) and isinstance(r.get("to"), str):
            last[r["key"]] = r
    stock = Counter(r["to"] for r in last.values())
    ages = [
        (until - parse_ts(r.get("ts"))).total_seconds() / 86400
        for r in last.values()
        if r["to"] == "in_review" and parse_ts(r.get("ts"))
    ]
    order = [s for s in crew_mod.STATES if stock.get(s)] + sorted(
        set(stock) - set(crew_mod.STATES)
    )
    stock_line = row(
        "Stock now (age of In Review)",
        sum(v for k, v in stock.items() if k != "done"),
        med(ages),
        p90(ages),
        unit="d",
        value=" · ".join(f"{s} {stock[s]}" for s in order),
        source=f"{src}: last row per key",
    )
    return stock_line, last


def mismatch_rows(
    last: dict, prs: list | None, pattern: str, since: datetime, src: str, gh_why: str | None
) -> list:
    """A merged code PR whose story is not In Review or later; a story In Progress without an
    open code PR in this repo."""
    if prs is None:
        return [
            na("Mismatch: merged PR, story before In Review", gh_why or "gh not found"),
            na("Mismatch: In Progress without open PR", gh_why or "gh not found"),
        ]
    rows = []
    wrong, absent = [], set()
    for p in prs:
        if not (p["merged"] and p["merged"] >= since) or p["docs_only"]:
            continue
        key = story_key(p, pattern)
        if not key:
            continue
        if key not in last:
            absent.add(key)
        elif last[key]["to"] not in DONE_LIKE:
            wrong.append(f"{key} #{p['number']} ({last[key]['to']})")
    rows.append(
        row(
            "Mismatch: merged PR, story before In Review",
            len(wrong),
            value=", ".join(wrong[:5])
            + (" …" if len(wrong) > 5 else "")
            + (f"; {len(absent)} keys not in the log" if absent else ""),
            source=f"{src} + merged code PRs",
        )
    )
    open_keys = {story_key(p, pattern) for p in prs if p["state"] == "OPEN" and not p["docs_only"]}
    idle = sorted(k for k, r in last.items() if r["to"] == "in_progress" and k not in open_keys)
    rows.append(
        row(
            "Mismatch: In Progress without open PR",
            len(idle),
            value=", ".join(idle[:5]) + (" …" if len(idle) > 5 else ""),
            source=f"{src} + open code PRs of this repo only",
        )
    )
    return rows


def writers(transitions: list, since: datetime) -> dict:
    out: dict = defaultdict(Counter)
    for r in transitions:
        ts = parse_ts(r.get("ts"))
        if ts and ts >= since and isinstance(r.get("to"), str):
            out[f"{r.get('from') or '-'}→{r['to']}"][r.get("by") or "(no by)"] += 1
    return {k: dict(v.most_common()) for k, v in sorted(out.items())}


def per_day(items: list, since: datetime, until: datetime, kind: Callable) -> tuple:
    days = max(1, math.ceil((until - since).total_seconds() / 86400))
    daily = Counter()
    kinds = Counter()
    for item in items:
        daily[((item[0] - since).total_seconds() // 86400)] += 1
        kinds[kind(item[1])] += 1
    counts = [daily.get(i, 0) for i in range(days)]
    text = " · ".join(f"{k} {v / days:.1f}/d" for k, v in kinds.most_common())
    return counts, text


def question_rows(
    questions: list, answers: list, since: datetime, until: datetime, src: str
) -> list:
    posted = [
        (parse_ts(q.get("ts")), q)
        for q in questions
        if q.get("outcome") == "posted"
        and parse_ts(q.get("ts"))
        and parse_ts(q.get("ts")) >= since
    ]
    counts, text = per_day(posted, since, until, lambda q: q.get("cause") or "(none)")
    rows = [
        row(
            "Questions to the human per day",
            len(posted),
            med(counts),
            p90(counts),
            value=text,
            source=f"{src}: posted lines by cause",
        )
    ]
    waits = [
        hours(ts, answered)
        for ts, _q, answered in question_waits(questions, answers)
        if ts >= since and answered is not None
    ]
    rows.append(
        row(
            "Question answer time",
            len(waits),
            med(waits),
            p90(waits),
            unit="h",
            value=f"{len(posted) - len(waits)} unanswered",
            source=f"{src} + answers log: first answer that is not `read`",
        )
    )
    return rows


def brake_rows(brakes: list, since: datetime, until: datetime, src: str) -> list:
    items = [
        (parse_ts(b.get("ts")), b)
        for b in brakes
        if parse_ts(b.get("ts"))
        and parse_ts(b.get("ts")) >= since
        and b.get("type") != "outcome"  # a later judgment of a line, not a brake of its own
    ]
    counts, text = per_day(
        items,
        since,
        until,
        lambda b: (
            f"{b.get('type')}"
            + (f" {b['gate']}" if b.get("type") == "deny" and b.get("gate") else "")
        ),
    )
    return [
        row(
            "Brakes per day",
            len(items),
            med(counts),
            p90(counts),
            value=text,
            source=f"{src}: lines by type",
        ),
        outcome_row(brakes, since, until, src),
    ]


def outcome_row(brakes: list, since: datetime, until: datetime, src: str) -> dict:
    """``Brake outcomes``: per brake type in the window, how many of its lines a later ``outcome``
    line judged ``danger: yes`` (the danger was there) or ``no`` (a false alarm), and how many no
    one judged. An outcome counts in the window of its own ``ts``; ``n`` is the judged count."""
    in_window = [b for b in brakes if (t := parse_ts(b.get("ts"))) and since <= t <= until]
    brakes_by = Counter(b.get("type") for b in in_window if b.get("type") != "outcome")
    judged: dict = {}
    for b in in_window:
        if b.get("type") == "outcome" and b.get("danger") in ("yes", "no"):
            judged.setdefault(b.get("kind"), Counter())[b["danger"]] += 1
    parts = []
    for kind in sorted(set(brakes_by) | set(judged), key=str):
        c = judged.get(kind, Counter())
        rest = max(0, brakes_by.get(kind, 0) - c["yes"] - c["no"])
        parts.append(f"{kind}: {c['yes']} danger · {c['no']} false alarm · {rest} unjudged")
    return row(
        "Brake outcomes",
        sum(sum(c.values()) for c in judged.values()),
        value="; ".join(parts) or "no brake in the window",
        source=f"{src}: outcome lines by kind",
    )


def ready_rows(root: Path | None, since: datetime, src_missing: str | None) -> list:
    name = "Ready rounds"
    if root is None:
        return [na(name, src_missing or "git repo not found")]
    try:
        vdir = lens_verdict.verdict_dir(root)
    except Exception:
        return [na(name, "lens verdict directory not found")]
    log = vdir / "samples.jsonl"
    if not log.is_file():
        return [na(name, "lens severity log not found")]
    keys = sorted(
        {
            str(x["id"])[len("ready-") :]
            for x in read_jsonl(log)
            if x.get("kind") == lens_verdict.SEVERITY_KIND
            and str(x.get("id", "")).startswith("ready-")
        }
    )
    per_key, red, warn_only = [], 0, 0
    for key in keys:
        try:
            rounds = lens_verdict.rounds(root, key)
        except Exception:
            continue
        recent = [
            r
            for r in rounds
            if any(
                (parse_ts(x.get("ran_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= since
                for x in r["lenses"].values()
            )
        ]
        if not recent:
            continue
        per_key.append(max(r["round"] for r in recent))
        for r in recent:
            for x in r["lenses"].values():
                if x.get("verdict") == "red":
                    red += 1
                    if not x.get("blocking") and x.get("warning") and not x.get("failure"):
                        warn_only += 1
    return [
        row(
            name,
            len(per_key),
            med(per_key),
            p90(per_key),
            value=f"red on WARNING only: {warn_only} of {red} red lens verdicts ({pct(warn_only, red)})",
            source="lens_verdict.rounds over the severity log",
        )
    ]


# --- assembly -----------------------------------------------------------------------------------


def git(cwd: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def norm_slug(value: object) -> str | None:
    """`owner/repo` from a slug, `HOST/OWNER/REPO` or a GitHub URL (lower case, no `.git`), else
    None: a bare name or anything else names no repo."""
    text = str(value or "").strip().lower()
    text = text.split("://", 1)[-1].split("#", 1)[0].split("?", 1)[0].rstrip("/")
    text = text.removesuffix(".git")
    parts = [p for p in text.replace(":", "/").split("/") if p]
    if "pull" in parts:
        parts = parts[: parts.index("pull")]
    if len(parts) < 2:
        return None
    return f"{parts[-2]}/{parts[-1]}"


def build(
    args,
    now: datetime,
    cwd: Path,
    run: Runner | None = None,
    required: Callable[[str], list] | None = None,
) -> dict:
    since = args.since if isinstance(args.since, datetime) else parse_since(args.since, now)
    root_text = git(cwd, "rev-parse", "--show-toplevel")
    root = Path(root_text) if root_text else None
    repo = args.repo or norm_slug(git(cwd, "remote", "get-url", "origin"))
    try:
        crew_path, crew = crew_mod.find_and_load(cwd)
    except crew_mod.CrewError:
        crew_path, crew = None, None
    pattern = ((crew or {}).get("naming") or {}).get("key") or DEFAULT_KEY

    names, req_why = read_required(repo, required)
    prs, gh_why = fetch_github(args, repo, since, now, run, bool(names))
    src = f"gh {repo}"
    board, state = locate_board(args, cwd, crew_path, crew)

    rows: list = []
    transitions = None
    if board is None:
        board_why = "board log not found: no crew file"
    else:
        tpath = board.with_name(f"{board.stem}-transitions.jsonl")
        if tpath.is_file():
            transitions = read_jsonl(tpath)
            board_why = None
        else:
            board_why = f"{tpath.name} not found"
    if transitions is not None:
        rows += board_rows(transitions, prs, pattern, since, now, tpath.name, gh_why)
        rows.append(
            escape_row(transitions, prs, pattern, since, now, f"{tpath.name} + {src}")
            if prs is not None
            else na("Escapes after Done by risk class", gh_why or "gh not found")
        )
    else:
        for name in (
            "Lead time Selected → Done",
            "Share of lead time",
            "Stock now (age of In Review)",
            "Mismatch: merged PR, story before In Review",
            "Mismatch: In Progress without open PR",
            "Transition writers: In Review",
            "Escapes after Done by risk class",
        ):
            rows.append(na(name, board_why))

    if prs is not None:
        rows += github_rows(prs, since, args.review_match, src)
        rows += red_head_rows(prs, names, since, src, construction_checks(root), req_why)
        rows.append(prs_per_story(prs, since, pattern, src))
    else:
        for name in (
            "PR open → merge",
            "Heads per code PR",
            "Docs-PR share",
            "Review red per PR",
            "CI cancelled share",
            "Code PRs by risk class",
            "New tests per code PR",
            "Required checks: red heads",
            "PRs per story",
        ):
            rows.append(na(name, gh_why))

    rows += ready_rows(root, since, None)
    rows += log_rows(board, state, board_why, since, now)
    flow, summary = flow_rows(
        board,
        crew,
        since,
        now,
        getattr(args, "from_", None) or [],
        board_why,
        flow_intervals.resolve_project(board, crew_path),
    )
    return {
        "repo": repo,
        "since": since.strftime("%Y-%m-%dT%H:%MZ"),
        "until": now.strftime("%Y-%m-%dT%H:%MZ"),
        "rows": rows,
        "writers": writers(transitions, since) if transitions is not None else None,
        "flow_efficiency": {"rows": flow, "summary": summary},
    }


FLOW_SRC = "flow_intervals: sampler + board logs + worker markers"


def flow_rows(board, crew, since, until, foreign: list, board_why, project=None) -> tuple:
    """`(rows, formatted summary or None)` of the section `Flow efficiency`: the strings of
    `flow_intervals.format_summary`, the formatter the flow page prints too; only the rows of
    `project` (`flow_intervals.py` § Project), its drops as `Flow gap: project` lines."""
    if board is None and not foreign:
        return [na("Flow efficiency", board_why or "board log not found: no crew file")], None
    log_dir, tz = flow_intervals.settings_for(crew)
    built = flow_intervals.build(
        board, worker_supervisor.state_dir(), log_dir, tz, crew, since, until, foreign, project
    )
    fmt = flow_intervals.format_summary(flow_intervals.summary(built))
    att = built["attribution"]
    rows = [
        row(
            "Flow project",
            value=(
                f"{project or flow_intervals.NO_PROJECT}: {att['kept_rows']} sampler rows of "
                f"{att['kept_sessions']} sessions kept, {att['dropped_rows']} rows of "
                f"{att['dropped_sessions']} sessions dropped"
            ),
            source="board sessions + crew + worker markers",
        )
    ]
    for name, part, label in (
        ("stories", fmt["stories"], "Story efficiency"),
        ("masters", fmt["masters"], "Master efficiency"),
        ("workers", fmt["workers"], "Worker efficiency"),
    ):
        rows.append(
            row(
                f"{label} (ratio)",
                part["n"],
                part["median"],
                part["p90"],
                value=part["window"],
                source=FLOW_SRC,
            )
        )
        for x in part["rows"]:
            if name == "stories":
                rows.append(
                    row(
                        f"{label}: {x['key']}",
                        value=(
                            f"{x['ratio']} = working {x['working_h']} h / lead {x['lead_h']} h, {x['sessions']} sessions"
                        ),
                        source="transitions + sampler",
                    )
                )
            elif name == "masters":
                rows.append(
                    row(
                        f"{label}: {x['who']}",
                        value=(
                            f"{x['ratio']} = working {x['working_h']} h / alive {x['alive_h']} h; "
                            f"others wait on it {x['waited_on_h']} h"
                        ),
                        source="sampler + waits",
                    )
                )
            else:
                rows.append(
                    row(
                        f"{label}: {x['who']}",
                        value=(
                            f"{x['ratio']} = working {x['working_h']} h / {x['span_h']} h ({x['start']}, "
                            f"stop = last probe, ±5 min); blocked {x['blocked_h']} h; "
                            f"idle after end {x['idle_after_end_h']} h; starter {x['starter']}"
                        ),
                        source="sampler + marker",
                    )
                )
    for kind, v in fmt["waiting"].items():
        if v["n"] == "n/a":
            rows.append(na(f"Waiting by kind: {kind}", "no source yet"))
            continue
        rows.append(
            row(
                f"Waiting by kind: {kind}",
                v["n"],
                v["median"],
                v["p90"],
                unit="h",
                value=f"{v['hours']} h",
                source=FLOW_SRC,
            )
        )
    for x in fmt["locks"]:
        rows.append(
            row(
                f"Lock held: {x['lock']} by {x['holder']}",
                x["n"],
                value=f"{x['hours']} h, in no ratio",
                source="sampler locks",
            )
        )
    for g in built["gaps"]:
        rows.append(na(f"Flow gap: {g['source']}", g["reason"]))
    return rows, fmt


def read_required(repo: str | None, reader: Callable[[str], list] | None) -> tuple:
    """`(sorted names, None)`, or `(None, why)` when the required checks cannot be read."""
    if not repo:
        return None, "GitHub repo not found"
    try:
        return sorted((reader or required_checks)(repo)), None
    except SourceMissingError as exc:
        return None, str(exc)


def fetch_github(
    args,
    repo: str | None,
    since: datetime,
    now: datetime,
    run: Runner | None,
    checks: bool = False,
):
    """`(prs, None)`, or `(None, why)` when GitHub cannot answer."""
    if not repo:
        return None, "GitHub repo not found"
    try:
        return fetch_prs(
            run or gh_runner(args.gh_cache, f"{_iso(since)}..{_iso(now)}"),
            repo,
            since,
            now,
            checks,
        ), None
    except SourceMissingError as exc:
        return None, str(exc)
    except (KeyError, TypeError, ValueError) as exc:
        return None, f"gh: unexpected answer ({exc})"


def log_rows(board: Path | None, state: Path | None, board_why, since, now) -> list:
    """The question and brake rows from the logs beside the board and in the state dir."""
    rows = []
    if board is not None and board.with_name(f"{board.stem}-questions.jsonl").is_file():
        qpath = board.with_name(f"{board.stem}-questions.jsonl")
        apath = board.with_name(f"{board.stem}-answers.jsonl")
        rows += question_rows(
            read_jsonl(qpath), read_jsonl(apath) if apath.is_file() else [], since, now, qpath.name
        )
    else:
        why = board_why if board is None else "questions log not found"
        rows += [na("Questions to the human per day", why), na("Question answer time", why)]

    brakes = state / "brakes.jsonl" if state is not None else None
    if brakes is not None and brakes.is_file():
        rows += brake_rows(read_jsonl(brakes), since, now, "brakes.jsonl")
    else:
        why = "brakes.jsonl not found" if state else "no crew file"
        rows += [na("Brakes per day", why), na("Brake outcomes", why)]
    return rows


def _num(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:.1f}"
    return f"{value:g}" if isinstance(value, float) else str(value)


def cells(r: dict) -> list:
    if r["value"].startswith("n/a"):
        return [r["row"], "", "", "", r["value"], r["source"]]
    unit = f" {r['unit']}" if r["unit"] and r["median"] is not None else ""
    return [
        r["row"],
        _num(r["n"]),
        _num(r["median"]) + unit,
        _num(r["p90"]) + unit,
        r["value"],
        r["source"],
    ]


HEAD = ["Row", "n", "median", "p90", "value", "source"]


def render_text(report: dict) -> str:
    table = [HEAD] + [cells(r) for r in report["rows"]]
    widths = [max(len(line[i]) for line in table) for i in range(len(HEAD) - 1)]
    out = [
        f"flow report {report['repo'] or '(no repo)'} · {report['since']} → {report['until']}",
        "",
    ]
    for line in table:
        out.append("  ".join(c.ljust(w) for c, w in zip(line, widths)) + "  " + line[-1])
    out += _writer_lines(report, "")
    flow = [HEAD] + [cells(r) for r in report["flow_efficiency"]["rows"]]
    widths = [max(len(line[i]) for line in flow) for i in range(len(HEAD) - 1)]
    out += ["", "Flow efficiency", ""]
    for line in flow:
        out.append("  ".join(c.ljust(w) for c, w in zip(line, widths)) + "  " + line[-1])
    return "\n".join(line.rstrip() for line in out) + "\n"


def render_md(report: dict) -> str:
    esc = lambda s: s.replace("|", "\\|")  # noqa: E731
    out = [
        f"# Flow report {report['repo'] or '(no repo)'}",
        "",
        f"Window {report['since']} → {report['until']} (UTC).",
        "",
        "| " + " | ".join(HEAD) + " |",
        "|" + "---|" * len(HEAD),
    ]
    out += ["| " + " | ".join(esc(c) for c in cells(r)) + " |" for r in report["rows"]]
    out += _writer_lines(report, "- ")
    out += ["", "## Flow efficiency", "", "| " + " | ".join(HEAD) + " |", "|" + "---|" * len(HEAD)]
    out += [
        "| " + " | ".join(esc(c) for c in cells(r)) + " |"
        for r in report["flow_efficiency"]["rows"]
    ]
    return "\n".join(out) + "\n"


def _writer_lines(report: dict, bullet: str) -> list:
    if report["writers"] is None:
        return []
    out = [
        "",
        "Writers per transition (window):" if not bullet else "## Writers per transition",
        "",
    ]
    for kind, by in report["writers"].items():
        flag = "" if len(by) == 1 else f"  ({len(by)} writers)"
        out.append(
            f"{bullet or '  '}{kind}: " + ", ".join(f"{k} {v}" for k, v in by.items()) + flag
        )
    return out


def main(
    argv: list | None = None,
    now: datetime | None = None,
    cwd: Path | None = None,
    run: Runner | None = None,
    required: Callable[[str], list] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="flow_report.py", description=__doc__.split("\n")[0])
    parser.add_argument("--since", default="10d")
    parser.add_argument("--repo")
    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true")
    fmt.add_argument("--md", action="store_true")
    parser.add_argument("--board", help="board file whose logs to read (default: the crew's)")
    parser.add_argument(
        "--gh-cache", type=Path, help="keep and reuse gh answers in this directory"
    )
    parser.add_argument(
        "--review-match", default="review", help="regex for the review workflows (default: review)"
    )
    parser.add_argument("--until", help="the window's end, UTC YYYY-MM-DDTHH:MM (default: now)")
    parser.add_argument(
        "--from",
        dest="from_",
        action="append",
        default=[],
        help="a JSONL file of foreign interval rows",
    )
    args = parser.parse_args(argv)
    if args.until:
        now = parse_ts(args.until if args.until.endswith("Z") else args.until + "Z")
        if now is None:
            parser.error(f"--until {args.until!r}: expected YYYY-MM-DDTHH:MM")
    now = now or datetime.now(timezone.utc).replace(microsecond=0)
    cwd = cwd or Path.cwd()
    try:
        args.since = parse_since(args.since, now)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    report = build(args, now, cwd, run, required)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0
    if not args.md:
        sys.stdout.write(render_text(report))
        return 0
    text = render_md(report)
    sys.stdout.write(text)
    top = git(cwd, "rev-parse", "--show-toplevel")
    store = Path(top) / ".weside" / "optimization" if top else None
    if store is None or not store.is_dir():
        print(
            "flow_report: no optimization store (.weside/optimization/); nothing written",
            file=sys.stderr,
        )
        return 0
    target = store / "reports" / f"flow-{crew_mod.today(top, now)}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print(f"flow_report: wrote {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
