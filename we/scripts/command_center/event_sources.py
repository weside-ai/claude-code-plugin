#!/usr/bin/env python3
"""The event poller's sources: one round over GitHub, the cluster and the local checks.

A round reads only what ``events.sources`` of the project's ``.weside/config.json`` names; this
module names no repo, workflow, job, status context, tag or namespace. Each finding is an event
(``Event``) of one kind of ``KINDS``, deduplicated by its key in the poller's ``state.json``
(``seen``, 14 days). A source absent from the config is off.

Kinds and their config keys (``events.sources.<key>``):

``main_red`` (``red``: a list of ``{repo, relevant, never_red, branch}``)
    Per repo the newest red ``push`` or ``schedule`` run per workflow on the branch (default
    ``main``), younger than 24 h, never a workflow of ``never_red``; it counts when the workflow
    name matches ``relevant`` (a regex, default none), else when one of its red jobs is a required
    check of the branch (``required_checks.sh``, cached 1 h). An older red run of the same workflow
    is marked seen silently.
``run_queued_long`` (``queued``: ``{repo, limit_min, limits}``)
    A run queued longer than ``limit_min`` (default 60) or ``limits[<workflow name>]``; a superseded
    dispatch (below) is not one.
``dispatch_superseded`` (``dispatch``: ``{repo, workflow, stale_h}``)
    A queued ``workflow_dispatch`` run of the workflow file when a newer dispatch of the same ref
    is queued, or when it waited longer than ``stale_h`` (default 6) hours. Read from the same
    queued list as ``run_queued_long`` (one call), so both need the same repo.
``issue_new`` (``issues``: ``{repos, skip_authors}``)
    A new open issue (never a pull request, never one of ``skip_authors``). The first round per
    repo records the open issues silently: only what comes after is news. An issue older than the
    14-day dedupe window is never news (its seen key aged out, the issue did not).
``rc_verdict_red`` / ``rc_verdict_green`` (``rc``: ``{repo, workflow, plan_job, status_context,
tag_pattern, tag_refs, clone, issue_titles: {red, infra}}``)
    Per completed ``workflow_dispatch`` run of the loop workflow on a release candidate: the plan
    job's log names ``"target": "rc"`` and the sha (fallback the ``REF: <sha>`` line); the verdict
    is the ``status_context`` commit status of that run on the sha (``success`` green, ``failure``
    red, ``error`` infra), else the run's conclusion (``cancelled``, ``timed_out``: infra). The tag
    comes from ``git ls-remote --tags origin <tag_refs>`` in ``clone`` (default the project root).
    The cause of a red or infra verdict is the open issue titled ``issue_titles[verdict]``, else
    the run's red job names. The first round records the completed runs silently; a run older than
    24 h is never news; an unreadable plan log is retried two rounds, then reported with tag ``?``.
``release_pr_blocked`` / ``prod_gate_blocked`` (``release_pr``: ``{repo, rc_title, prod_title,
wait_min}``)
    From the open pull request list (one call): an open bot pull request whose title matches ``rc_title`` (group 1 the tag) is blocked when it
    is older than ``wait_min`` (default 30) minutes, and once per red check (a required one; any
    red check when the branch requires none). ``prod_title`` matches a production release: the
    same findings are ``prod_gate_blocked``, damage. The title only matches; it never reaches a
    line (the tag must match ``rc.tag_pattern`` or ``prod_tag_pattern``).
``rc_cut_waiting`` (``rc_cut``: ``{repo, workflow, job, wait_min}``)
    The cut job of an in-progress run of the workflow, running longer than ``wait_min`` (30).
``rollout_stuck`` (``rollout``: ``{namespace, kubeconfig}``)
    ``kubectl get jobs,deployments`` (read only, only when the kubeconfig file exists): a Job not
    owned by a CronJob whose ``Failed`` condition turned true within 24 h, a Deployment whose
    ``Progressing`` condition has reason ``ProgressDeadlineExceeded`` (once per generation).
``rate_limit`` (``rate_limit: true``)
    Hourly, the bot token's ``core.remaining``.
``disk`` / ``local_check`` (``events.local_checks``: a list of commands)
    Each command runs with a 120 s timeout; each stdout line is one event: of the kind its first
    word names, lower-cased, when that word is ``disk``, else ``local_check``. The command is the
    host's own: its line is the one text not built from ids (its owner writes it).
``poll_error``
    A ``gh``, ``git`` or ``kubectl`` failure, at most one per hour (the poller routes it to
    ``machinery`` unless ``routes`` says otherwise).
``config_error``
    An invalid ``events:`` block (the poller emits it, ``event_routes.validate`` names the error).

An event carries only ids, numbers, names of workflows, checks, jobs and deployments, validated
tags, and URLs built from ids (``event_routes.render`` builds the line from them). A PR or issue
title, a body, a log line or a condition message never enters one.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

KINDS = (
    "main_red",
    "run_queued_long",
    "dispatch_superseded",
    "issue_new",
    "rc_verdict_red",
    "rc_verdict_green",
    "release_pr_blocked",
    "prod_gate_blocked",
    "rc_cut_waiting",
    "rollout_stuck",
    "rate_limit",
    "disk",
    "local_check",
    "poll_error",
    "config_error",
)
DAMAGE_KINDS = ("prod_gate_blocked",)  # damage by nature; a route may mark more
HOUR = 3600
KEEP_S = 14 * 86400
RED = ("failure", "timed_out", "cancelled")
VERDICT = {"success": "green", "failure": "red", "error": "infra"}
GH = "https://github.com"
REQUIRED_CHECKS = Path(__file__).resolve().parent.parent / "required_checks.sh"

_SAFE_NAME = re.compile(r"[^\w .:/()+#,@-]")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9._/+-]{1,120}$")
_K8S = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")
_REASON = re.compile(r"^[A-Za-z]{1,64}$")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_REPO = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
PROD_TAG = r"^v\d+\.\d+\.\d+$"


def name_of(value: Any, limit: int = 100) -> str:
    """A workflow, job or check name for a line: one line, no markup, at most ``limit`` chars."""
    text = _SAFE_NAME.sub("", " ".join(str(value or "").split()))
    return text[:limit] or "?"


def token_of(value: Any) -> str:
    """A branch or login: kept when it is one plain token, else ``?``."""
    text = str(value or "")
    return text if _SAFE_TOKEN.match(text) else "?"


def run_url(repo: str, run_id: Any) -> str:
    return f"{GH}/{repo}/actions/runs/{int(run_id)}"


def epoch(ts: Any) -> float | None:
    try:
        return (
            datetime.strptime(str(ts), "%Y-%m-%dT%H:%M:%SZ")
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
    except ValueError:
        return None


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def event_id(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


@dataclass
class Event:
    kind: str
    key: str  # the dedupe key, also the source of ``id``
    object: str  # what folding groups by: same kind and object within fold_s is one line
    source_at: str | None
    fields: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return event_id(self.key)

    def row(self, observed_at: str, damage: bool) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "object": self.object,
            "source_at": self.source_at,
            "observed_at": observed_at,
            "fields": self.fields,
            "damage": damage,
        }


Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class Round:
    """One round of every configured source over ``state`` (mutated in place).

    ``run`` is ``subprocess.run`` (tests keep it and put fake ``gh``, ``git`` and ``kubectl``
    scripts on ``PATH``); ``env`` is the environment the children get (``PATH``, ``HOME``)."""

    def __init__(
        self,
        sources: dict[str, Any],
        state: dict[str, Any],
        now: float,
        *,
        local_checks: list[str] | None = None,
        root: str | None = None,
        env: dict[str, str] | None = None,
        run: Runner = subprocess.run,
    ):
        self.src = sources or {}
        self.st = state
        self.now = now
        self.local_checks = list(local_checks or [])
        self.root = root or os.getcwd()
        self.env = dict(os.environ if env is None else env)
        self.run = run
        self.errors: list[str] = []
        self.events: list[Event] = []
        self.seen = state.setdefault("seen", {})
        self.seeded = state.setdefault("seeded", {})
        self.req = state.setdefault("req", {})
        self.jobs = state.setdefault("jobs", {})
        self._open: dict[str, list] = {}  # repo -> open issues and PRs (one call, shared)
        self._tags: dict[str, str] | None = None

    # --- plumbing -----------------------------------------------------------------------

    def age_s(self, ts: Any) -> float:
        t = epoch(ts)
        return self.now - t if t is not None else 0.0

    def new(self, key: str) -> bool:
        if key in self.seen:
            return False
        self.seen[key] = self.now
        return True

    def emit(self, kind: str, key: str, obj: str, source_at: Any, **fields: Any) -> None:
        self.events.append(
            Event(kind, key, obj, source_at if isinstance(source_at, str) else None, fields)
        )

    def _exec(self, argv: list[str], timeout: int, env: dict | None = None):
        try:
            return self.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=env or self.env,
                stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self.errors.append(f"{argv[0]} {type(exc).__name__}")
            return None

    def gh(self, path: str, raw: bool = False) -> Any:
        argv = ["gh", "api", path]
        out = self._exec(argv, 60)
        where = path.split("?", maxsplit=1)[0]
        if out is None:
            return None
        if out.returncode != 0:
            self.errors.append(f"gh {where}: exit {out.returncode}")
            return None
        if raw:
            return out.stdout
        try:
            return json.loads(out.stdout)
        except ValueError:
            self.errors.append(f"gh {where}: no JSON")
            return None

    def required(self, repo: str, branch: str = "main") -> set[str] | None:
        """The branch's required check names, cached 1 h (``required_checks.sh``); None when the
        script failed and nothing is cached: the caller retries next round, never judges."""
        cache = f"{repo}@{branch}"
        hit = self.req.get(cache)
        if hit and self.now - hit.get("ts", 0) < HOUR:
            return set(hit.get("names") or [])
        out = self._exec(["bash", str(REQUIRED_CHECKS), "--repo", repo, branch], 120)
        if out is None or out.returncode != 0:
            if out is not None:
                self.errors.append(f"required_checks {repo}: exit {out.returncode}")
            return set(hit.get("names") or []) if hit else None
        names = [n for n in out.stdout.splitlines() if n.strip()]
        self.req[cache] = {"ts": self.now, "names": names}
        return set(names)

    def open_items(self, repo: str) -> list | None:
        """Open issues and PRs of ``repo``, newest first; one call per round and repo."""
        if repo not in self._open:
            data = self.gh(
                f"repos/{repo}/issues?state=open&sort=created&direction=desc&per_page=30"
            )
            if data is None:
                return None
            self._open[repo] = data if isinstance(data, list) else []
        return self._open[repo]

    # --- the round ----------------------------------------------------------------------

    def run_all(self) -> list[Event]:
        """Every configured source in turn; one failing source never stops the others."""
        steps = [
            ("red", self.main_red),
            ("queued", self.queued),
            ("issues", self.issues),
            ("rc", self.rc_verdicts),
            ("release_pr", self.release_prs),
            ("rc_cut", self.rc_cut),
            ("rollout", self.rollout),
            ("rate_limit", self.rate_limit),
        ]
        for key, step in steps:
            if self.src.get(key) or (key == "queued" and self.src.get("dispatch")):
                try:
                    step()
                except Exception as exc:
                    self.errors.append(f"source {key}: {type(exc).__name__}")
        if self.local_checks:
            try:
                self.local()
            except Exception as exc:
                self.errors.append(f"local checks: {type(exc).__name__}")
        self.error_event()
        self.prune()
        return self.events

    def main_red(self) -> None:
        for entry in self.src.get("red") or []:
            repo = entry["repo"]
            branch = entry.get("branch") or "main"
            relevant = re.compile(entry["relevant"]) if entry.get("relevant") else None
            never = set(entry.get("never_red") or [])
            data = self.gh(f"repos/{repo}/actions/runs?branch={branch}&status=failure&per_page=5")
            done: set[str] = set()  # the list comes newest first: per workflow only the newest
            for run in (data or {}).get("workflow_runs", []):
                key = f"red:{repo}:{run['id']}"
                if run.get("event") not in ("push", "schedule") or run.get("name") in never:
                    continue
                if run.get("name") in done:
                    self.seen.setdefault(key, self.now)
                    continue
                done.add(run.get("name"))
                if self.age_s(run.get("created_at")) > 24 * HOUR or key in self.seen:
                    continue
                why = "list" if relevant and relevant.match(run.get("name") or "") else None
                if why is None:
                    names = self.required(repo, branch)
                    if names is None:
                        continue  # required checks unreadable: next round judges the run
                    jk = str(run["id"])
                    if jk not in self.jobs:
                        j = self.gh(
                            f"repos/{repo}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100"
                        )
                        if j is None:
                            continue  # next round tries again
                        self.jobs[jk] = {
                            "ts": self.now,
                            "red": [
                                x.get("name")
                                for x in j.get("jobs", [])
                                if x.get("conclusion") in RED
                            ],
                        }
                    hit = sorted(set(self.jobs[jk]["red"]) & names)
                    if not hit:
                        self.seen[key] = self.now
                        continue
                    why = "required: " + ", ".join(name_of(h) for h in hit)
                self.new(key)
                self.emit(
                    "main_red",
                    key,
                    f"run:{run['id']}",
                    run.get("created_at"),
                    repo=repo,
                    workflow=name_of(run.get("name")),
                    event=token_of(run.get("event")),
                    sha=str(run.get("head_sha") or "")[:7],
                    why=why,
                    run_id=int(run["id"]),
                )

    def queued(self) -> None:
        cfg = self.src.get("queued") or {}
        dis = self.src.get("dispatch") or {}
        repo = cfg.get("repo") or dis.get("repo")
        data = self.gh(f"repos/{repo}/actions/runs?status=queued&per_page=100")
        runs = (data or {}).get("workflow_runs", [])
        wf = dis.get("workflow")
        loops = [
            r
            for r in runs
            if wf and (r.get("path") or "").endswith(wf) and r.get("event") == "workflow_dispatch"
        ]
        superseded = {
            r["id"]
            for r in loops
            if any(
                o.get("head_branch") == r.get("head_branch") and o["created_at"] > r["created_at"]
                for o in loops
            )
        }
        if cfg:
            limits = cfg.get("limits") or {}
            for run in runs:
                if run["id"] in superseded:
                    continue  # reported as dispatch_superseded, not as a hang
                mins = int(self.age_s(run.get("created_at")) // 60)
                limit = limits.get(run.get("name"), cfg.get("limit_min", 60))
                key = f"hang:{repo}:{run['id']}"
                if mins > limit and self.new(key):
                    self.emit(
                        "run_queued_long",
                        key,
                        f"run:{run['id']}",
                        run.get("created_at"),
                        repo=repo,
                        workflow=name_of(run.get("name")),
                        mins=mins,
                        event=token_of(run.get("event")),
                        branch=token_of(run.get("head_branch")),
                        run_id=int(run["id"]),
                    )
        if dis:
            stale = float(dis.get("stale_h", 6)) * HOUR
            for run in loops:
                newer = run["id"] in superseded
                old = self.age_s(run.get("created_at")) > stale
                key = f"stale:{repo}:{run['id']}"
                if (newer or old) and self.new(key):
                    self.emit(
                        "dispatch_superseded",
                        key,
                        f"run:{run['id']}",
                        run.get("created_at"),
                        repo=repo,
                        branch=token_of(run.get("head_branch")),
                        why="newer" if newer else "stale",
                        hours=int(float(dis.get("stale_h", 6))),
                        run_id=int(run["id"]),
                    )

    def issues(self) -> None:
        cfg = self.src.get("issues") or {}
        skip = set(cfg.get("skip_authors") or [])
        for repo in cfg.get("repos") or []:
            data = self.open_items(repo)
            if data is None:
                continue
            first = not self.seeded.get(repo)
            for i in data:
                if "pull_request" in i or (i.get("user") or {}).get("login") in skip:
                    continue
                key = f"issue:{repo}#{i['number']}"
                if self.age_s(i.get("created_at")) > KEEP_S - HOUR:
                    self.seen[key] = self.now  # older than the dedupe window: never news again
                    continue
                if self.new(key) and not first:
                    self.emit(
                        "issue_new",
                        key,
                        f"issue:{repo}#{i['number']}",
                        i.get("created_at"),
                        repo=repo,
                        number=int(i["number"]),
                    )
            self.seeded[repo] = True

    # --- release candidates -------------------------------------------------------------

    def rc_tags(self) -> dict[str, str]:
        if self._tags is None:
            cfg = self.src.get("rc") or {}
            self._tags = {}
            clone = os.path.expanduser(cfg.get("clone") or self.root)
            out = self._exec(
                [
                    "git",
                    "-C",
                    clone,
                    "ls-remote",
                    "--tags",
                    "origin",
                    cfg.get("tag_refs") or "refs/tags/*",
                ],
                60,
            )
            if out is None:
                return self._tags
            if out.returncode != 0:
                self.errors.append(f"git ls-remote: exit {out.returncode}")
            for line in out.stdout.splitlines():
                sha, _, ref = line.partition("\t")
                tag = ref[len("refs/tags/") :] if ref.startswith("refs/tags/") else ref
                self._tags[sha] = (
                    tag[:-3] if tag.endswith("^{}") else tag
                )  # ^{} follows the tag object
        return self._tags

    def rc_plan(self, repo: str, run_id: Any, plan_job: str) -> dict | None:
        """``{"target", "sha", "red_jobs"}`` from the plan job's log; None: a gh failure."""
        j = self.gh(f"repos/{repo}/actions/runs/{run_id}/jobs?filter=latest&per_page=30")
        if j is None:
            return None
        jobs = j.get("jobs", [])
        info: dict[str, Any] = {
            "red_jobs": sorted(
                {name_of(x.get("name")) for x in jobs if x.get("conclusion") in RED}
            )
        }
        job = next((x for x in jobs if x.get("name") == plan_job), None)
        if job is None:
            return info
        before = len(self.errors)
        log = self.gh(f"repos/{repo}/actions/jobs/{job['id']}/logs", raw=True)
        if log is None and job.get("conclusion") in ("cancelled", "skipped"):
            del self.errors[before:]  # the plan never ran: no log, no target, silent
            return info
        if log is None:
            return None
        for line in log.splitlines():
            m = re.search(r'(\{"lane".*"target".*\})\s*$', line)
            if m:
                with contextlib.suppress(ValueError):
                    info.update(json.loads(m.group(1)))
            m = re.search(r"\bREF: ([0-9a-f]{40})\s*$", line)
            if m:
                info.setdefault("ref", m.group(1))
        return info

    def rc_verdicts(self) -> None:  # noqa: PLR0912
        cfg = self.src["rc"]
        repo = cfg["repo"]
        tag_re = re.compile(cfg.get("tag_pattern") or r"^v\d+\.\d+\.\d+-rc\.\d+$")
        titles = cfg.get("issue_titles") or {}
        data = self.gh(
            f"repos/{repo}/actions/workflows/{cfg['workflow']}/runs?event=workflow_dispatch&status=completed&per_page=5"
        )
        first = data is not None and not self.seeded.get("rc")  # the first round records silently
        tries = self.st.setdefault("rctry", {})
        for run in (data or {}).get("workflow_runs", []):
            key, rid = f"rc:{repo}:{run['id']}", str(run["id"])
            if key in self.seen:
                continue
            if first or self.age_s(run.get("updated_at") or run.get("created_at")) > 24 * HOUR:
                self.seen[key] = self.now
                continue
            info = self.rc_plan(repo, run["id"], cfg.get("plan_job") or "Suite plan")
            if info is None:
                tries[rid] = tries.get(rid, 0) + 1
                if tries[rid] < 3:
                    continue  # a gh failure: two more rounds, then report with "?"
                info = {"unread": True}
            tries.pop(rid, None)
            sha = info.get("sha") or info.get("ref")
            sha = sha if isinstance(sha, str) and _SHA.match(sha) else None
            tags = self.rc_tags() if sha else {}
            if not info.get("unread") and info.get("target") != "rc" and sha not in tags:
                self.seen[key] = self.now
                continue  # no release candidate
            verdict = None
            if sha:
                sts = self.gh(f"repos/{repo}/commits/{sha}/statuses?per_page=100") or []
                hit = [
                    x
                    for x in sts
                    if x.get("context") == cfg.get("status_context")
                    and f"/runs/{run['id']}/" in (x.get("target_url") or "") + "/"
                ]
                if hit:
                    verdict = VERDICT.get(hit[0].get("state"))
            verdict = verdict or {"success": "green", "failure": "red"}.get(
                run.get("conclusion"), "infra"
            )
            tag = tags.get(sha or "")
            tag = tag if tag and tag_re.match(tag) else (sha[:7] if sha else "?")
            self.seen[key] = self.now
            fields: dict[str, Any] = {
                "repo": repo,
                "tag": tag,
                "verdict": verdict,
                "run_id": int(run["id"]),
            }
            if info.get("unread"):
                fields["unread"] = True
            if verdict != "green":
                issue = self.open_issue(repo, titles.get(verdict))
                if issue:
                    fields["issue"] = issue
                else:
                    fields["jobs"] = info.get("red_jobs") or []
            kind = "rc_verdict_green" if verdict == "green" else "rc_verdict_red"
            self.emit(kind, key, f"run:{run['id']}", run.get("updated_at"), **fields)
        if data is not None:
            self.seeded["rc"] = True
        for k in [k for k in tries if f"rc:{repo}:{k}" in self.seen]:
            del tries[k]

    def open_issue(self, repo: str, title: str | None) -> int | None:
        if not title:
            return None
        for i in self.open_items(repo) or []:
            if "pull_request" not in i and i.get("title") == title:
                return int(i["number"])
        return None

    def release_prs(self) -> None:
        cfg = self.src["release_pr"]
        repo = cfg["repo"]
        wait = int(cfg.get("wait_min", 30))
        rc_tag = re.compile(
            (self.src.get("rc") or {}).get("tag_pattern") or r"^v\d+\.\d+\.\d+-rc\.\d+$"
        )
        prod_tag = re.compile(cfg.get("prod_tag_pattern") or PROD_TAG)
        pats = [
            ("release_pr_blocked", cfg.get("rc_title"), rc_tag),
            ("prod_gate_blocked", cfg.get("prod_title"), prod_tag),
        ]
        # the open PRs on their own (not the shared issue list): a busy repo pushes a release PR
        # past the newest 30 issues; the list carries each head sha, so no call per PR
        pulls = self.gh(f"repos/{repo}/pulls?state=open&per_page=100")
        for pr in pulls if isinstance(pulls, list) else []:
            if not (pr.get("user") or {}).get("login", "").endswith("[bot]"):
                continue
            match = None
            for kind, pat, tag_re in pats:
                m = re.match(pat, pr.get("title") or "") if pat else None
                if m and tag_re.match(m.group(1)):
                    match = (kind, m.group(1))
                    break
            if not match:
                continue
            kind, tag = match
            n = int(pr["number"])
            mins = int(self.age_s(pr.get("created_at")) // 60)
            key = f"rchang:{repo}:pr:{n}:age"
            if mins > KEEP_S // 60 - 60:
                self.seen[key] = self.now  # older than the dedupe window: reported long ago
            if mins > wait and self.new(key):
                self.emit(
                    kind,
                    key,
                    f"pr:{repo}#{n}",
                    pr.get("created_at"),
                    repo=repo,
                    number=n,
                    tag=tag,
                    mins=mins,
                )
            head = (pr.get("head") or {}).get("sha")
            if not head:
                continue
            names = self.required(repo, (pr.get("base") or {}).get("ref") or "main")
            if names is None:
                continue  # required checks unreadable: next round
            cr = self.gh(f"repos/{repo}/commits/{head}/check-runs?filter=latest&per_page=100")
            for c in (cr or {}).get("check_runs", []):
                key = f"rchang:{repo}:pr:{n}:{c.get('id')}"
                if (
                    c.get("conclusion") in RED
                    and (not names or c.get("name") in names)
                    and self.new(key)
                ):
                    self.emit(
                        kind,
                        key,
                        f"pr:{repo}#{n}",
                        c.get("completed_at"),
                        repo=repo,
                        number=n,
                        tag=tag,
                        check=name_of(c.get("name")),
                        check_id=int(c["id"]),
                    )

    def rc_cut(self) -> None:
        cfg = self.src["rc_cut"]
        repo = cfg["repo"]
        wait = int(cfg.get("wait_min", 30))
        data = self.gh(
            f"repos/{repo}/actions/workflows/{cfg['workflow']}/runs?status=in_progress&per_page=3"
        )
        for run in (data or {}).get("workflow_runs", []):
            key = f"rchang:{repo}:cut:{run['id']}"
            if self.age_s(run.get("created_at")) < wait * 60 or key in self.seen:
                continue
            j = self.gh(f"repos/{repo}/actions/runs/{run['id']}/jobs?filter=latest&per_page=30")
            for job in (j or {}).get("jobs", []):
                if (
                    job.get("name") == cfg.get("job")
                    and job.get("status") == "in_progress"
                    and job.get("started_at")
                ):
                    mins = int(self.age_s(job["started_at"]) // 60)
                    if mins > wait and self.new(key):
                        self.emit(
                            "rc_cut_waiting",
                            key,
                            f"run:{run['id']}",
                            job["started_at"],
                            repo=repo,
                            mins=mins,
                            run_id=int(run["id"]),
                        )

    def rollout(self) -> None:  # noqa: PLR0912
        cfg = self.src["rollout"]
        kcfg = os.path.expanduser(cfg.get("kubeconfig") or "")
        if not kcfg or not os.path.isfile(kcfg):
            return
        env = {
            "HOME": self.env.get("HOME", ""),
            "PATH": self.env.get("PATH", ""),
            "KUBECONFIG": kcfg,
        }
        out = self._exec(
            [
                "kubectl",
                "get",
                "jobs,deployments",
                "-n",
                cfg["namespace"],
                "-o",
                "json",
                "--request-timeout=20s",
            ],
            40,
            env,
        )
        if out is None:
            return
        try:
            items = json.loads(out.stdout).get("items", []) if out.returncode == 0 else None
        except ValueError:
            items = None
        if items is None:
            self.errors.append(f"kubectl: exit {out.returncode}")
            return
        for it in items:
            meta, conds = it.get("metadata", {}), (it.get("status") or {}).get("conditions") or []
            name = str(meta.get("name") or "")
            if not _K8S.match(name):
                continue
            if it.get("kind") == "Job":
                if any(o.get("kind") == "CronJob" for o in meta.get("ownerReferences") or []):
                    continue
                for c in conds:
                    when = c.get("lastTransitionTime") or iso(self.now)
                    key = f"stg:job:{meta.get('uid')}"
                    if (
                        c.get("type") == "Failed"
                        and c.get("status") == "True"
                        and self.age_s(when) < 24 * HOUR
                        and self.new(key)
                    ):
                        reason = (
                            c.get("reason") if _REASON.match(str(c.get("reason") or "")) else "?"
                        )
                        self.emit(
                            "rollout_stuck",
                            key,
                            f"job:{name}",
                            when,
                            what="job",
                            name=name,
                            reason=reason,
                        )
            elif it.get("kind") == "Deployment":
                for c in conds:
                    key = f"stg:deploy:{name}:{meta.get('generation')}"
                    if (
                        c.get("type") == "Progressing"
                        and c.get("reason") == "ProgressDeadlineExceeded"
                        and self.new(key)
                    ):
                        since = (
                            c.get("lastUpdateTime")
                            if _ISO.match(str(c.get("lastUpdateTime") or ""))
                            else "?"
                        )
                        self.emit(
                            "rollout_stuck",
                            key,
                            f"deployment:{name}",
                            c.get("lastUpdateTime"),
                            what="deployment",
                            name=name,
                            since=since,
                        )

    def rate_limit(self) -> None:
        if self.now - self.st.get("rate_ts", 0) < HOUR:
            return
        data = self.gh("rate_limit")
        left = ((data or {}).get("resources") or {}).get("core", {}).get("remaining")
        if isinstance(left, int):
            self.st["rate_ts"] = self.now
            self.emit(
                "rate_limit",
                f"rate:{int(self.now // HOUR)}",
                "rate_limit",
                iso(self.now),
                remaining=left,
            )

    def local(self) -> None:
        for command in self.local_checks:
            out = self._exec(["sh", "-c", os.path.expanduser(command)], 120)
            if out is None:
                continue
            if out.returncode != 0:
                self.errors.append(f"local check: exit {out.returncode}")
            for line in out.stdout.splitlines():
                text = " ".join(line.split())[:300]
                if not text:
                    continue
                kind = "disk" if text.split()[0].lower() == "disk" else "local_check"
                key = f"local:{kind}:{int(self.now)}:{event_id(text)}"
                self.new(key)
                # one fold object per command and kind: two checks never fold each other's lines
                self.emit(kind, key, f"{kind}:{event_id(command)}", iso(self.now), text=text)

    def error_event(self) -> None:
        if self.errors and self.now - self.st.get("error_ts", 0) >= HOUR:
            self.st["error_ts"] = self.now
            key = f"error:{int(self.now)}"
            self.emit(
                "poll_error",
                key,
                "poll_error",
                iso(self.now),
                count=len(self.errors),
                first=[name_of(e, 80) for e in self.errors[:3]],
            )

    def prune(self) -> None:
        for k in [k for k, v in self.seen.items() if self.now - v > KEEP_S]:
            del self.seen[k]
        for k in [k for k, v in self.jobs.items() if self.now - v.get("ts", 0) > KEEP_S]:
            del self.jobs[k]


def repo_ok(repo: Any) -> bool:
    return isinstance(repo, str) and bool(_REPO.match(repo))
