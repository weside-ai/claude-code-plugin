#!/usr/bin/env python3
"""The ``events:`` block of ``.weside/config.json``: its schema, its validation, the line text.

Schema (this docstring owns it)::

    "events": {
      "poll_interval_s": 300,      round interval of the poller (int >= 30)
      "deliver_timeout_s": 180,    an addressed event without a ledger row after this many seconds
                                   lands in the coordinator's delta (the tail died)
      "fold_s": 600,               a tail folds the same kind and object within this window
      "local_checks": ["..."],     host commands, one event per stdout line (event_sources.py)
      "sources": {...},            per source its repos, names and patterns (event_sources.py)
      "routes": {
        "<kind>": {"to": ["<role key or member slug>", ...], "mode": "line" | "digest",
                   "damage": true | false}
      }
    }

Validation (``validate``, called by the poller on every reload and by ``crew.py validate
--strict``) refuses by name: a kind outside ``event_sources.KINDS`` (``events: unknown event
'x'``), a target that is neither a key of the crew's ``roles`` nor a member slug (``events:
unknown role 'x'``), a ``mode`` other than ``line``/``digest``, a non-boolean ``damage``, an
unknown key of the block or of a route, and a source repo that is no ``owner/name``.

Routing (``targets``): a kind goes to the targets of its route; ``poll_error`` and
``config_error`` go to ``machinery`` when no route names them. ``damage`` is true for a kind of
``event_sources.DAMAGE_KINDS`` or a route that says so: a damage event reaches a parked session
too and, without any running receiver, the coordinator at once (``event_poller.py``).

The line (``render``) is built from fixed words, integers, validated tags, workflow, check, job
and deployment names and GitHub URLs built from ids; a PR or issue title never enters it (the
line lands in a session as a user turn). The one exception is a local check's own line, written
by a host command its owner configured.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from event_sources import DAMAGE_KINDS, GH, KINDS, repo_ok, run_url

BLOCK_KEYS = (
    "poll_interval_s",
    "deliver_timeout_s",
    "fold_s",
    "local_checks",
    "sources",
    "routes",
)
ROUTE_KEYS = ("to", "mode", "damage")
MODES = ("line", "digest")
DEFAULTS = {"poll_interval_s": 300, "deliver_timeout_s": 180, "fold_s": 600}
FALLBACK = {"poll_error": ["machinery"], "config_error": ["machinery"]}


class EventsError(ValueError):
    """An ``events:`` block that cannot be used; the message names the first wrong entry."""


def crew_targets(crew: dict[str, Any] | None) -> set[str]:
    """Role keys of the crew (``roles``) and member slugs: what a route may name."""
    crew = crew or {}
    roles = crew.get("roles") if isinstance(crew.get("roles"), dict) else {}
    members = crew.get("members") if isinstance(crew.get("members"), dict) else {}
    return set(roles) | set(members)


def _repos(sources: dict[str, Any]) -> list[Any]:
    found: list[Any] = []
    for key, value in sources.items():
        if key == "red":
            found += [e.get("repo") if isinstance(e, dict) else e for e in value or []]
        elif key == "issues" and isinstance(value, dict):
            found += list(value.get("repos") or [])
        elif isinstance(value, dict) and "repo" in value:
            found.append(value.get("repo"))
    return found


def validate(block: Any, crew: dict[str, Any] | None) -> dict[str, Any]:  # noqa: PLR0912
    """The block with its defaults, or ``EventsError`` naming what is wrong."""
    if not isinstance(block, dict):
        raise EventsError("events: needs an object")
    for key in block:
        if key not in BLOCK_KEYS:
            raise EventsError(f"events: unknown key '{key}'")
    out = {**DEFAULTS, **block}
    for key in DEFAULTS:
        value = out[key]
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < (30 if key == "poll_interval_s" else 0)
        ):
            raise EventsError(f"events: {key} must be a whole number of seconds")
    checks = out.get("local_checks") or []
    if not isinstance(checks, list) or not all(isinstance(c, str) and c.strip() for c in checks):
        raise EventsError("events: local_checks must be a list of commands")
    sources = out.get("sources") or {}
    if not isinstance(sources, dict):
        raise EventsError("events: sources must be an object")
    for repo in _repos(sources):
        if not repo_ok(repo):
            raise EventsError(f"events: source repo '{repo}' is not owner/name")
    contexts = (
        (sources.get("rc") or {}).get("status_contexts", [])
        if isinstance(sources.get("rc"), dict)
        else []
    )
    if not isinstance(contexts, list) or not all(isinstance(c, str) and c for c in contexts):
        raise EventsError("events: sources.rc.status_contexts must be a list of status contexts")
    routes = out.get("routes") or {}
    if not isinstance(routes, dict):
        raise EventsError("events: routes must be an object")
    known = crew_targets(crew)
    for kind, route in routes.items():
        if kind not in KINDS:
            raise EventsError(f"events: unknown event '{kind}'")
        if not isinstance(route, dict):
            raise EventsError(f"events: route '{kind}' must be an object")
        for key in route:
            if key not in ROUTE_KEYS:
                raise EventsError(f"events: route '{kind}' has unknown key '{key}'")
        to = route.get("to")
        if not isinstance(to, list) or not to or not all(isinstance(t, str) for t in to):
            raise EventsError(f"events: route '{kind}' needs a list 'to'")
        for target in to:
            if target not in known:
                raise EventsError(f"events: unknown role '{target}'")
        if route.get("mode", "line") not in MODES:
            raise EventsError(f"events: route '{kind}' mode must be line or digest")
        if not isinstance(route.get("damage", False), bool):
            raise EventsError(f"events: route '{kind}' damage must be true or false")
    out["sources"], out["routes"], out["local_checks"] = sources, routes, checks
    return out


def targets(block: dict[str, Any], kind: str) -> list[str]:
    route = (block.get("routes") or {}).get(kind)
    if route:
        return list(route.get("to") or [])
    return list(FALLBACK.get(kind, []))


def mode(block: dict[str, Any], kind: str) -> str:
    return ((block.get("routes") or {}).get(kind) or {}).get("mode", "line")


def damage(block: dict[str, Any], kind: str) -> bool:
    return kind in DAMAGE_KINDS or bool(
        ((block.get("routes") or {}).get(kind) or {}).get("damage")
    )


def member_of(crew: dict[str, Any], target: str) -> str | None:
    """The member slug a target (role key or slug) denotes."""
    roles = crew.get("roles") if isinstance(crew.get("roles"), dict) else {}
    members = crew.get("members") if isinstance(crew.get("members"), dict) else {}
    if target in members:
        return target
    slug = roles.get(target)
    return slug if isinstance(slug, str) and slug in members else None


# --- the line --------------------------------------------------------------------------


def _int(value: Any) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _repo(value: Any) -> str:
    return value if repo_ok(value) else "?"


def render(row: dict[str, Any]) -> str:  # noqa: PLR0911, PLR0912
    """The one line of an event row (``events.jsonl``)."""
    k, f = row.get("kind"), row.get("fields") or {}
    repo = _repo(f.get("repo"))
    run = run_url(repo, _int(f.get("run_id"))) if "run_id" in f else ""
    if k == "rc_verdict_green":
        return f"RC {f.get('tag')} green · run {run}"
    if k == "rc_verdict_red":
        if f.get("issue"):
            cause = f"{GH}/{repo}/issues/{_int(f.get('issue'))}"
        else:
            cause = ", ".join(str(j) for j in f.get("jobs") or []) or "unknown"
        unread = " · plan log unreadable" if f.get("unread") else ""
        return f"RC {f.get('tag')} {f.get('verdict')} · run {run} · cause: {cause}{unread}"
    if k in ("release_pr_blocked", "prod_gate_blocked"):
        head = "prod gate blocked · " if k == "prod_gate_blocked" else ""
        n = _int(f.get("number"))
        if f.get("check"):
            return (
                f"{head}release PR #{n} {f.get('tag')} red: {f.get('check')} · "
                f"{GH}/{repo}/runs/{_int(f.get('check_id'))}"
            )
        return f"{head}release PR #{n} {f.get('tag')} waiting {_int(f.get('mins'))} min · {GH}/{repo}/pull/{n}"
    if k == "rc_cut_waiting":
        return f"RC cut waiting {_int(f.get('mins'))} min · {run}"
    if k == "rollout_stuck":
        if f.get("what") == "job":
            return f"rollout stuck · job {f.get('name')} failed: {f.get('reason')}"
        return f"rollout stuck · deployment {f.get('name')} past its progress deadline since {f.get('since')}"
    if k == "main_red":
        return f"main red {repo} · {f.get('workflow')} ({f.get('event')}, {f.get('sha')}, {f.get('why')}) · run {run}"
    if k == "run_queued_long":
        return (
            f"run queued {_int(f.get('mins'))} min · {repo} {f.get('workflow')} "
            f"({f.get('event')}, {f.get('branch')}) · run {run}"
        )
    if k == "dispatch_superseded":
        why = (
            "newer one queued" if f.get("why") == "newer" else f"> {_int(f.get('hours'))} h queued"
        )
        return f"dispatch superseded ({f.get('branch')}, {why}) · run {run}"
    if k == "issue_new":
        n = _int(f.get("number"))
        return f"new issue {repo}#{n} · {GH}/{repo}/issues/{n}"
    if k == "rate_limit":
        return f"rate_limit core remaining {_int(f.get('remaining'))}"
    if k == "poll_error":
        return f"poll error: {_int(f.get('count'))} failures · " + " · ".join(
            str(x) for x in f.get("first") or []
        )
    if k == "config_error":
        return str(f.get("error") or "events: invalid")
    if k in ("disk", "local_check"):
        return str(f.get("text") or "")
    return f"event {k}"


def digest(lines: list[str]) -> str:
    return f"digest ({len(lines)}): " + " · ".join(lines)
