#!/usr/bin/env python3
"""The ``events:`` block of ``.weside/config.json``: its schema, its validation, the line text.

Schema (this docstring owns it)::

    "events": {
      "poll_interval_s": 300,      round interval of the poller (int >= 30)
      "deliver_timeout_s": 180,    an addressed event without a ledger row after this many seconds
                                   lands in the coordinator's delta (the tail died)
      "fold_s": 600,               a tail folds the same kind and object within this window
      "local_checks": ["..."],     host commands, one event per stdout line (event_sources.py)
      "sources": {...},            per source its repos, names and patterns (event_sources.py);
                                   "sessions": {"interval_s": 60, "waiting": [...]} runs on its
                                   own interval (int >= 30), the waiting states plain words
      "push": {                    the poller's push to the human (push_notify.py)
        "url_env": "NAME",         the environment variable holding the webhook URL
        "wrapper": ["cmd", ...],   the command that sets it: the poller runs
                                   <wrapper...> -- python3 push_notify.py --env NAME
        "body_key": "text"         the JSON key of the message (default text)
      },
      "routes": {
        "<kind>": {"to": ["<role key or member slug>", ...], "mode": "line" | "digest",
                   "damage": true | false, "push": true | false}
      }
    }

``push: true`` on a route: the poller posts the event's line once to the webhook when it routes
the event, and the line ends ``· push`` when the post went out, else ``· no push: <reason>``
(not configured, ``HTTP <code>``, timeout, unreachable, ``wrapper exit <n>``), loud, and the
event also becomes a board news item: the human learns of it on the board instead.

Validation (``validate``, called by the poller on every reload and by ``crew.py validate
--strict``) refuses by name: a kind outside ``event_sources.KINDS`` (``events: unknown event
'x'``), a target that is neither a key of the crew's ``roles`` nor a member slug (``events:
unknown role 'x'``), a ``mode`` other than ``line``/``digest``, a non-boolean ``damage``, an
unknown key of the block or of a route, a non-boolean ``push`` (``events: route 'x': push must be
true or false``), a ``push`` block without ``url_env`` and ``wrapper``, a source repo that is
no ``owner/name``, and a ``sources.prod_release`` with an unknown key, no workflow file name, a
``tag_pattern`` that does not compile or takes a pre-release tag of ``RC_SAMPLES``, a ``wait_min``
below 1, an empty ``gate_job`` or no ``repo``.

The target ``epic_master`` names no role: it is the master session of the event's epic, found
over the board (``epic_owner.py``); every crew may name it. Without a running master the event
lands in the coordinator's delta with the epic (``event_poller.py``).

Routing (``targets``): a kind goes to the targets of its route; ``poll_error`` and
``config_error`` go to ``machinery`` when no route names them; ``pr_run_queued_long`` without a
route of its own goes to ``epic_master`` as a digest (``FALLBACK``, ``DIGEST_FALLBACK``): the
pull request's master acts on its own queue, like the other ``pr_*`` kinds; one without a story
(a fork, a branch without a key) takes the ``run_queued_long`` route instead (``route_kind``). ``damage`` is true for a kind of
``event_sources.DAMAGE_KINDS`` or a route that says so: a damage event reaches a parked session
too and, without any running receiver, the coordinator at once (``event_poller.py``).

The line (``render``) is built from fixed words, integers, validated tags, workflow, check, job
and deployment names and GitHub URLs built from ids; a PR or issue title never enters it (the
line lands in a session as a user turn). The one exception is a local check's own line, written
by a host command its owner configured. A ``main_red`` addressed to ``epic_master`` ends with the
receiving sessions (``· owner <session>``, board names validated as tokens) or ``· owner delta:
coordinator · <epic>``; a dispatched run's line ends ``· by <token>`` when the poller read the
requester from the run's title (``requested_by``).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from event_sources import (
    _KEY,
    _NODE_ID,
    _SESSION_NAME,
    DAMAGE_KINDS,
    GH,
    KINDS,
    PROD_TAG,
    SESSIONS_INTERVAL_S,
    repo_ok,
    run_url,
    session_label,
    tool_label,
    window_label,
)

_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")
_BODY_KEY = re.compile(r"^[A-Za-z_]{1,32}$")
_WAITING = re.compile(r"^[a-z]+( [a-z]+){0,3}$")
_PUSH_REASON = re.compile(r"^[A-Za-z0-9 ]{1,40}$")
_WORKFLOW = re.compile(r"^[A-Za-z0-9._-]{1,100}\.ya?ml$")
RC_SAMPLES = ("v1.2.3-rc.1", "v1.2.3-rc1", "v1.2.3rc1", "1.2.3-rc.1", "v1.2.3-beta.1")
PROD_RELEASE_KEYS = ("repo", "workflow", "tag_pattern", "wait_min", "gate_job")

BLOCK_KEYS = (
    "poll_interval_s",
    "deliver_timeout_s",
    "fold_s",
    "local_checks",
    "sources",
    "push",
    "routes",
)
ROUTE_KEYS = ("to", "mode", "damage", "push")
PUSH_KEYS = ("url_env", "wrapper", "body_key")
MODES = ("line", "digest")
EPIC_MASTER = "epic_master"  # a target every crew may name: the epic's master session
_BY = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
DEFAULTS = {"poll_interval_s": 300, "deliver_timeout_s": 180, "fold_s": 600}
FALLBACK = {
    "poll_error": ["machinery"],
    "config_error": ["machinery"],
    "pr_run_queued_long": [EPIC_MASTER],
}
DIGEST_FALLBACK = ("pr_run_queued_long",)  # without a route of its own: the fallback, as digest


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
        elif key in ("issues", "pulls") and isinstance(value, dict):
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
    _validate_sessions(sources.get("sessions"))
    _validate_prod_release(sources.get("prod_release"))
    out["push"] = _validate_push(out.get("push"))
    routes = out.get("routes") or {}
    if not isinstance(routes, dict):
        raise EventsError("events: routes must be an object")
    known = crew_targets(crew) | {EPIC_MASTER}
    _validate_owner_sources(sources)
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
        if not isinstance(route.get("push", False), bool):
            raise EventsError(f"events: route '{kind}': push must be true or false")
    out["sources"], out["routes"], out["local_checks"] = sources, routes, checks
    return out


def _validate_owner_sources(sources: dict[str, Any]) -> None:
    """``pulls``, ``rc.trusted_authors`` and every ``requested_by_rx``."""
    _validate_pulls(sources.get("pulls"))
    rc = sources.get("rc") if isinstance(sources.get("rc"), dict) else {}
    authors = rc.get("trusted_authors", [])
    if not isinstance(authors, list) or not all(isinstance(a, str) and a for a in authors):
        raise EventsError("events: sources.rc.trusted_authors must be a list of logins")
    for key, cfg in sources.items():
        rx = cfg.get("requested_by_rx") if isinstance(cfg, dict) else None
        if rx is None:
            continue
        try:
            ok = isinstance(rx, str) and re.compile(rx).groups >= 1
        except re.error:
            ok = False
        if not ok:
            raise EventsError(
                f"events: sources.{key}.requested_by_rx must be a regex with a group"
            )


def _validate_pulls(cfg: Any) -> None:
    if cfg is None:
        return
    where = "events: sources.pulls"
    if not isinstance(cfg, dict):
        raise EventsError(f"{where} must be an object")
    for key in cfg:
        if key not in ("repos", "review_rx", "merged_window"):
            raise EventsError(f"{where} has unknown key '{key}'")
    if not isinstance(cfg.get("repos"), list) or not cfg["repos"]:
        raise EventsError(f"{where}.repos must be a list of owner/name")
    try:
        re.compile(cfg.get("review_rx", "review"))
    except (re.error, TypeError):
        raise EventsError(f"{where}.review_rx must be a regular expression") from None
    window = cfg.get("merged_window", 2)
    if not isinstance(window, (int, float)) or isinstance(window, bool) or window <= 0:
        raise EventsError(f"{where}.merged_window must be hours > 0")


def _validate_sessions(cfg: Any) -> None:
    if cfg is None or cfg is True or cfg is False:
        return
    if not isinstance(cfg, dict):
        raise EventsError("events: sources.sessions must be an object")
    for key in cfg:
        if key not in ("interval_s", "waiting"):
            raise EventsError(f"events: sources.sessions has unknown key '{key}'")
    value = cfg.get("interval_s", SESSIONS_INTERVAL_S)
    if not isinstance(value, int) or isinstance(value, bool) or value < 30:
        raise EventsError("events: sources.sessions.interval_s must be a whole number >= 30")
    waiting = cfg.get("waiting", [])
    if not isinstance(waiting, list) or not all(
        isinstance(w, str) and _WAITING.match(w) for w in waiting
    ):
        raise EventsError("events: sources.sessions.waiting must be a list of waiting states")


def _validate_prod_release(cfg: Any) -> None:
    if cfg is None:
        return
    where = "events: sources.prod_release"
    if not isinstance(cfg, dict):
        raise EventsError(f"{where} must be an object")
    for key in cfg:
        if key not in PROD_RELEASE_KEYS:
            raise EventsError(f"{where} has unknown key '{key}'")
    if "repo" not in cfg:
        raise EventsError(f"{where}.repo must be owner/name")
    if not isinstance(cfg.get("workflow"), str) or not _WORKFLOW.match(cfg["workflow"]):
        raise EventsError(f"{where}.workflow must be the workflow's file name")
    pattern = cfg.get("tag_pattern", PROD_TAG)
    try:
        tag_re = re.compile(pattern) if isinstance(pattern, str) and pattern else None
    except re.error:
        tag_re = None
    if tag_re is None:
        raise EventsError(f"{where}.tag_pattern must be a regular expression")
    for rc in RC_SAMPLES:
        if tag_re.fullmatch(rc):
            raise EventsError(f"{where}.tag_pattern takes the RC tag '{rc}'")
    wait = cfg.get("wait_min", 30)
    if not isinstance(wait, int) or isinstance(wait, bool) or wait < 1:
        raise EventsError(f"{where}.wait_min must be a whole number >= 1")
    if "gate_job" in cfg and not (isinstance(cfg["gate_job"], str) and cfg["gate_job"].strip()):
        raise EventsError(f"{where}.gate_job must be a job name")


def _validate_push(cfg: Any) -> dict[str, Any] | None:
    if cfg is None:
        return None
    if not isinstance(cfg, dict):
        raise EventsError("events: push must be an object")
    for key in cfg:
        if key not in PUSH_KEYS:
            raise EventsError(f"events: push has unknown key '{key}'")
    if not isinstance(cfg.get("url_env"), str) or not _ENV_NAME.match(cfg["url_env"]):
        raise EventsError("events: push.url_env must name an environment variable")
    wrapper = cfg.get("wrapper")
    if (
        not isinstance(wrapper, list)
        or not wrapper
        or not all(isinstance(w, str) and w for w in wrapper)
    ):
        raise EventsError("events: push.wrapper must be a command as a list")
    if not _BODY_KEY.match(str(cfg.get("body_key", "text"))):
        raise EventsError("events: push.body_key must be a plain key")
    return {"body_key": "text", **cfg}


def sessions_interval(block: dict[str, Any]) -> int | None:
    """The sessions source's interval, None when the block has no such source."""
    cfg = (block.get("sources") or {}).get("sessions")
    if cfg is None or cfg is False:
        return None
    return (
        int(cfg.get("interval_s", SESSIONS_INTERVAL_S))
        if isinstance(cfg, dict)
        else SESSIONS_INTERVAL_S
    )


def push(block: dict[str, Any], kind: str) -> bool:
    return bool(((block.get("routes") or {}).get(kind) or {}).get("push"))


def route_kind(block: dict[str, Any], kind: str, fields: dict[str, Any] | None = None) -> str:
    """The kind whose route an event takes: a ``pr_run_queued_long`` without a route of its own
    and without a story (a fork, a branch without a key) has no epic to find, so it takes the
    ``run_queued_long`` route; ``fields`` None (a kind alone) keeps the kind."""
    if (
        kind == "pr_run_queued_long"
        and fields is not None
        and not fields.get("story")
        and not (block.get("routes") or {}).get(kind)
    ):
        return "run_queued_long"
    return kind


def targets(block: dict[str, Any], kind: str, fields: dict[str, Any] | None = None) -> list[str]:
    kind = route_kind(block, kind, fields)
    routes = block.get("routes") or {}
    route = routes.get(kind)
    if route:
        return list(route.get("to") or [])
    return list(FALLBACK.get(kind, []))


def mode(block: dict[str, Any], kind: str, fields: dict[str, Any] | None = None) -> str:
    kind = route_kind(block, kind, fields)
    route = (block.get("routes") or {}).get(kind)
    if not route and kind in DIGEST_FALLBACK:
        return "digest"
    return (route or {}).get("mode", "line")


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


def render(row: dict[str, Any]) -> str:
    """The one line of an event row (``events.jsonl``): its text, its owner, and, for a route with
    ``push``, the push's outcome."""
    return line(row) + owner_suffix(row) + push_suffix(row)


def owner_suffix(row: dict[str, Any]) -> str:
    """`` · owner <session>`` of a ``main_red`` routed to its epic's master, or the delta's epic."""
    if row.get("kind") != "main_red" or "owner" not in row:
        return ""
    names = [n for n in row.get("owner") or [] if isinstance(n, str) and _SESSION_NAME.match(n)]
    if names:
        return " · owner " + ", ".join(names)
    epics = [e for e in str(row.get("owner_epic") or "").split(", ") if _KEY.match(e)]
    return " · owner delta: coordinator · " + (", ".join(epics) or "epic unknown")


def _by(f: dict[str, Any]) -> str:
    by = f.get("by")
    return f" · by {by}" if isinstance(by, str) and _BY.match(by) else ""


PR_WORDS = {
    "pr_checks_red": "checks red",
    "pr_conflict": "conflict with the base",
    "pr_green": "green",
    "pr_merged": "merged",
}


def pr_line(k: str, f: dict[str, Any]) -> str:
    """``PR #<n> <repo> · <kind words> · <check name> · <url>``: ids, validated names, URLs."""
    repo, n = _repo(f.get("repo")), _int(f.get("number"))
    pr_url = f"{GH}/{repo}/pull/{n}"
    check_url = f"{GH}/{repo}/runs/{_int(f.get('check_id'))}" if f.get("check_id") else pr_url
    sha = str(f.get("sha") or "")
    sha = sha if re.match(r"^[0-9a-f]{7}$", sha) else "?"
    if k == "pr_review_verdict":
        word = "pass" if f.get("verdict") == "pass" else "red"
        return f"PR #{n} {repo} · review {word} · {f.get('check')} · {check_url}"
    if k == "pr_checks_red":
        return f"PR #{n} {repo} · checks red · {f.get('check')} · {check_url}"
    if k == "pr_merged":
        return f"PR #{n} {repo} · merged · merge commit {sha} · {pr_url}"
    return f"PR #{n} {repo} · {PR_WORDS.get(k, k)} · head {sha} · {pr_url}"


def line(row: dict[str, Any]) -> str:  # noqa: PLR0911, PLR0912
    """The line's text without the push suffix: also the text a push posts."""
    k, f = row.get("kind"), row.get("fields") or {}
    repo = _repo(f.get("repo"))
    run = run_url(repo, _int(f.get("run_id"))) if "run_id" in f else ""
    if k == "rc_verdict_green":
        return f"RC {f.get('tag')} green · run {run}{_by(f)}"
    if k == "rc_verdict_red":
        if f.get("issue"):
            cause = f"{GH}/{repo}/issues/{_int(f.get('issue'))}"
        else:
            cause = ", ".join(str(j) for j in f.get("jobs") or []) or "unknown"
        unread = " · plan log unreadable" if f.get("unread") else ""
        return f"RC {f.get('tag')} {f.get('verdict')} · run {run} · cause: {cause}{unread}{_by(f)}"
    if k == "prod_gate_blocked" and "run_id" in f:
        what = (
            f"waiting {_int(f.get('mins'))} min ({f.get('status')})"
            if "mins" in f
            else f"{f.get('conclusion')}"
            + (f" · gate refused: {f.get('gate')}" if f.get("gate") else "")
            + " · cause: "
            + (", ".join(str(j) for j in f.get("jobs") or []) or "unknown")
        )
        return f"prod gate blocked · release {f.get('tag')} {what} · run {run}"
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
        return f"RC cut waiting {_int(f.get('mins'))} min · {run}{_by(f)}"
    if k == "rollout_stuck":
        if f.get("what") == "job":
            return f"rollout stuck · job {f.get('name')} failed: {f.get('reason')}"
        return f"rollout stuck · deployment {f.get('name')} past its progress deadline since {f.get('since')}"
    if k == "main_red" and f.get("origin") == "marker":
        ids = [i for i in f.get("failing") or [] if isinstance(i, str) and _NODE_ID.match(i)]
        failing = ", ".join(ids) if ids else "ids unreadable"
        return f"main red {repo} · {f.get('sha')} · failing: {failing} · run {run}"
    if k == "main_red":
        return f"main red {repo} · {f.get('workflow')} ({f.get('event')}, {f.get('sha')}, {f.get('why')}) · run {run}"
    if k in PR_WORDS or k == "pr_review_verdict":
        return pr_line(k, f)
    if k in ("run_queued_long", "pr_run_queued_long"):
        return (
            f"run queued {_int(f.get('mins'))} min · {repo} {f.get('workflow')} "
            f"({f.get('event')}, {f.get('branch')}) · run {run}{_by(f)}"
        )
    if k == "dispatch_superseded":
        why = (
            "newer one queued" if f.get("why") == "newer" else f"> {_int(f.get('hours'))} h queued"
        )
        return f"dispatch superseded ({f.get('branch')}, {why}) · run {run}{_by(f)}"
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
    if k == "permission_prompt":
        return prompt_line(row)
    return f"event {k}"


def prompt_line(row: dict[str, Any]) -> str:
    """The line of an open prompt without its push suffix (the push's text): fixed words, the
    waiting state, plain-token names and the time; a tool's input never."""
    f = row.get("fields") or {}
    what = (
        f.get("waiting")
        if isinstance(f.get("waiting"), str) and _WAITING.match(f["waiting"])
        else "prompt"
    )
    window = window_label(f.get("window"))
    since = str(row.get("source_at") or "")
    hhmm = since[11:16] if len(since) >= 16 else "?"
    return (
        f"{what} · session {session_label(f.get('session'), f.get('sid'))}"
        + (f" · window {window}" if window else "")
        + f" · tool {tool_label(f.get('tool'))} · open since {hhmm}Z"
    )


def push_suffix(row: dict[str, Any]) -> str:
    status = row.get("push")
    if status is None:
        return ""
    if status == "sent":
        return " · push"
    reason = status if isinstance(status, str) and _PUSH_REASON.match(status) else "error"
    return f" · no push: {reason}"


def digest(lines: list[str]) -> str:
    return f"digest ({len(lines)}): " + " · ".join(lines)
