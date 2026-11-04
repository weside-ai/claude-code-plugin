#!/usr/bin/env python3
"""The one reader of a repo's crew (``.weside/crew.json``, version 2): who holds which role.

Usage:
  crew.py path [--from DIR]                 the crew file in force, exit 1 without one
  crew.py show [--from DIR]                 the crew as JSON, defaults merged in
  crew.py members [--from DIR]              one line per member: "<name>\\t<title, else held role
                                            key, else specialist>"
  crew.py skill-path NAME [--cwd DIR]       "<path>\\t<loadable|workplace>\\t<skill|stub>", exit 1 if none
  crew.py stubs [--from DIR] [--write]      members without a role skill; --write creates the stubs
  crew.py is-role ROLE [--from DIR] [--session ID]
                                            exit 0 when this session (its environment) is a named
                                            master holding ROLE (roles.<ROLE>), else 1; ID (default
                                            $CLAUDE_CODE_SESSION_ID) excludes a process worker
  crew.py workplace SLUG [--from DIR]       the member's workplace, then each extra repo, absolute
  crew.py lenses [--set ready|t2] [--from DIR]
                                            the lenses as JSON (all, or ready_lenses / t2_panel in order)
  crew.py session-kind [--from DIR] [--session ID]
                                            this session's role (``role_of_session``): worker, master,
                                            a held role key, specialist, or none (with a hint)

Lookup (``find``): from DIR (default the cwd) upwards to the repo root (the first directory with
``.git``), the first ``.weside/crew.json``; a ``.weside/config.json`` whose ``crew`` names another
crew file (relative to that repo's root) counts as that file. A repo never inherits the crew of a
directory above it. The crew is the repo's projection of the account's handbook; the handbook
stays the truth about people. Contract: ``references/companion-session.md`` § Crew.

Schema (this docstring owns it). Required: ``version`` (2), ``roles`` (role key -> member slug;
the role keys are ``ROLE_KEYS``, one per role card) and ``members.<slug>`` (``name`` required;
``title``, ``components`` (backlogs the member orders), ``workplace`` (the repo the member starts
in, relative to the repo holding the crew file), ``extra_repos`` (more repos the member works in,
same base), ``on_call``, ``specialist`` (the field of a member woken on demand)). Every other key
has a default in ``DEFAULTS``; a repo writes only what differs: ``human``, ``question_label``
(opens a question line to the human), ``labels`` (the words of a question line and of the
parking signal in the crew's language: ``recommendation``, ``ready``; each one line of at most
``LABEL_CHARS`` characters), ``skill_prefix`` (role skills are ``<prefix>-<name
lowercased>``), ``weside_account`` (the members are weside companions: a pinned session loads its
identity with ``/we:materialize``), ``lenses`` (per lens ``agent``, ``questions`` (the Ready
question file), ``t2_questions`` (the T2 question file), ``registry``, ``keeper``, ``sample``;
the defaults are the three lenses ``product``, ``architecture``, ``acceptance``, each an agent
``we:lens-<key>``), ``ready_lenses``, ``t2_panel``, ``risk``,
``fallback`` (role key -> role key or ``human_bundle``), ``local_rules``, ``acceptance``,
``oracles``, ``board``, ``sla``, ``limits``, ``naming``, ``launch``, ``release``, ``cadences``,
``files``, ``coldstart``. A key of ``RETIRED_KEYS`` (no reader left) is skipped with one line on
stderr naming the file, never a ``CrewError``, so a crew file written for an older release loads.

``load`` validates on every read and raises ``CrewError`` naming the dotted key: a version other
than 2; an unknown key; a value of the wrong type (a null default takes a string or null); a
``roles`` key outside ``ROLE_KEYS`` or a value, lens ``keeper`` or ``sla.t2_second_reviewer`` that
is no member slug; a ``ready_lenses``/``t2_panel`` entry that is no lens (an undefined
``FORMER_DEFAULT_LENSES`` entry is left out of its set with a line on stderr instead); ``local_rules`` over
``LOCAL_RULES_MAX`` entries or one entry over ``LOCAL_RULE_CHARS`` characters or with a newline; a
path under ``files``, ``lenses.*.questions``, ``lenses.*.t2_questions`` or ``lenses.*.registry``
that does not exist relative to the repo holding the crew file. It then merges the file over ``DEFAULTS`` one level into each
object (each lens over its default lens, ``board.states`` over the default states; a list
replaces), so every reader sees the defaults without knowing them.

Transition (``V7_TRANSITION``): a file may still carry the version-1 keys ``roles.product_owner``,
``roles.orchestrator``, ``roles.tester``, ``members.*.role`` and ``members.*.lens`` while sessions
on the previous major read it. Each role key needs its counterpart ``product``, ``coordinator`` or
``acceptance`` beside it, holding the same member; ``load`` strips them and ``show`` names them on stderr. They and this block end at
the switchover cleanup (``V7_TRANSITION_ENDS``).

Session kind (``session_kind``, read by both SessionStart hooks): ``worker`` (``WE_ROLE=worker``
without a pin, a session started with ``--agent``, or the process worker the worktree's
``we-worker.json`` marker names: its own session id, or none recorded yet), ``consult`` (a pin with ``WE_ROLE=worker``:
the companion answers one request and ends), ``named`` (a pin, ``WE_ROLE`` master or unset),
``unnamed`` (no pin).
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# ``python3 -I`` (the board runs it so) leaves this directory off sys.path (``-I`` implies ``-P``)
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from worker_launch import read_marker  # noqa: E402

ROLE_KEYS = (
    "product",
    "architecture",
    "acceptance",
    "machinery",
    "coordinator",
    "escalation",
    "hr",
)
V7_TRANSITION = {"product_owner": "product", "orchestrator": "coordinator", "tester": "acceptance"}
V7_MEMBER_KEYS = ("role", "lens")
V7_TRANSITION_ENDS = "switchover day + 7"
VERSION = 2
VERSION_1 = (
    "crew.json is version 1: in a worktree, merge the default branch; otherwise run /we:setup"
)
LOCAL_RULES_MAX = 10
LOCAL_RULE_CHARS = 160
LABEL_CHARS = 40
CADENCES = ("rc_train", "bundle", "replenishment", "flow_report", "process_inbox", "goal_file")
STATES = ("on_hold", "backlog", "selected", "in_progress", "in_review", "done")
FALLBACK_TARGETS = (*ROLE_KEYS, "human_bundle")
MEMBER_KEYS = {
    "name": str,
    "title": str,
    "components": list,
    "workplace": str,
    "extra_repos": list,
    "on_call": bool,
    "specialist": str,
}


def _lens(key: str, sample: int | None = None) -> dict[str, Any]:
    return {
        "agent": f"we:lens-{key}",
        "questions": None,
        "t2_questions": None,
        "registry": None,
        "keeper": None,
        "sample": sample,
    }


# Default lenses of 7.56 and earlier. A crew that still names one in ``ready_lenses`` or
# ``t2_panel`` without defining it under ``lenses`` loses it from that set with a stderr line
# instead of failing every reader; any other undefined name stays a load error.
FORMER_DEFAULT_LENSES = ("security", "premise")

DEFAULTS: dict[str, Any] = {
    "human": {"name": "the human", "decides": []},
    "question_label": "QUESTION",
    "labels": {"recommendation": "Recommendation", "ready": "ready"},
    "skill_prefix": "weside",
    "weside_account": False,
    "lenses": {
        "product": _lens("product", 5),
        "architecture": _lens("architecture", 5),
        "acceptance": _lens("acceptance", 5),
    },
    "ready_lenses": ["product", "architecture", "acceptance"],
    "t2_panel": ["product", "architecture", "acceptance"],
    "risk": {
        "command": None,
        "paths": None,
        "one_way": [
            "money",
            "destructive-migration",
            "terraform-secrets",
            "trust-loosening",
            "brake-change",
        ],
        "rules_from": "origin/main",
    },
    "fallback": {},
    "local_rules": [],
    "acceptance": {"mock_persona": None, "mock_preset": None, "boundary_terms": []},
    "oracles": {
        "receipt_dir": None,
        "receipt_schema": None,
        "receipt_check": None,
        "walk_paths": [],
    },
    "board": {
        "file": "~/.claude/we-state/board.json",
        "ticketing": "none",
        "states": {
            "on_hold": "On Hold",
            "backlog": "Backlog",
            "selected": "Selected for Development",
            "in_progress": "In Progress",
            "in_review": "In Review",
            "done": "Done",
        },
    },
    "sla": {"hours": 4, "daytime": "08-20", "tz": "UTC", "t2_second_reviewer": None},
    "limits": {
        "masters": 5,
        "special_slots": [],
        "heavy_workers_per_master": 2,
        "epic_wip": 5,
        "epic_stories": [3, 8],
        "story_days": 1,
    },
    "naming": {"key": "[A-Z]+-\\d+", "master": "<word>-<number>", "worker": "<key>-<chunk>"},
    "launch": {"worker": None},
    "release": {"rc_job": None, "runbook": None, "prod_on": "human"},
    "cadences": {
        "rc_train": "2x daily",
        "bundle": "daily evening",
        "replenishment": "weekly",
        "flow_report": "weekly",
        "process_inbox": "weekly",
        "goal_file": "monthly",
    },
    "files": {"goals": None, "dod": None, "verify": None},
    "coldstart": {"suite": None},
}
# a null default takes a string or null; these take a number or null
NUMBER_OR_NULL = (
    "acceptance.mock_preset",
    "sample",
)
# keys no release reads any more: skipped with a stderr line instead of refused as unknown
RETIRED_KEYS = ("capacity",)
STUB_MARKER = "<!-- we:stub"
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "companion-skill" / "SKILL.md"
_SAFE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


class CrewError(Exception):
    """A crew file that exists but cannot be used."""


def find(start: str | Path | None = None) -> Path | None:
    """The crew file in force for ``start``, or None."""
    d = Path(start or Path.cwd()).resolve()
    for root in (d, *d.parents):
        found = _crew_at(root)
        if found is not False:
            return found
        if (root / ".git").exists():
            return None
    return None


def _crew_at(root: Path) -> Path | None | bool:
    """The crew file ``root`` declares, None for a dangling pointer, False when it declares none."""
    own = root / ".weside" / "crew.json"
    if own.is_file():
        return own
    config = root / ".weside" / "config.json"
    if config.is_file():
        try:
            pointer = json.loads(config.read_text(encoding="utf-8")).get("crew")
        except (OSError, ValueError, AttributeError):
            pointer = None
        if isinstance(pointer, str) and pointer.strip():
            target = (root / pointer.strip()).resolve()
            return target if target.is_file() else None
    return False


def session_kind(
    env: Any, agent_type: object = None, hook_input: dict | None = None
) -> tuple[str, str]:
    """(kind, pin) of a session: ``worker``, ``consult``, ``named`` or ``unnamed``.

    ``hook_input`` (``cwd``, ``session_id``) finds a process worker launched by
    ``worker_launch.py``: a ``claude --bg`` worker carries the daemon's environment, which may hold
    ``WE_ROLE=master`` and a pin, so its worktree's marker decides.
    """
    pin = str(env.get("WESIDE_COMPANION", "")).strip()
    if agent_type or _is_process_worker(hook_input):
        return "worker", ""
    worker = str(env.get("WE_ROLE", "")).strip() == "worker"
    if pin:
        return ("consult" if worker else "named"), pin
    return ("worker" if worker else "unnamed"), ""


NO_ROLE = "no role: ask the coordinator or run `/we:setup`"


def role_of_session(crew: dict[str, Any], env: Any, hook_input: dict | None = None) -> str | None:
    """``worker``; ``master`` (``WE_ROLE=master``, no pin); the role key a pinned member holds
    (``ROLE_KEYS``); ``specialist`` (a pinned member with ``specialist``); else None. A consultation
    (pin + ``WE_ROLE=worker``) counts as its member."""
    kind, pin = session_kind(env, hook_input.get("agent_type") if hook_input else None, hook_input)
    if kind == "worker":
        return "worker"
    if kind == "unnamed":
        return "master" if str(env.get("WE_ROLE", "")).strip() == "master" else None
    found = member(crew, pin)
    if found is None:
        return None
    slug, entry = found
    held = next((r for r in ROLE_KEYS if crew.get("roles", {}).get(r) == slug), None)
    if held:
        return held
    return "specialist" if entry.get("specialist") else None


def holds_role(crew: dict[str, Any], role: str, env: Any, hook_input: dict | None = None) -> bool:
    """Whether the session of ``env`` is a named master whose member holds ``roles.<role>``; a
    process worker (``hook_input``: ``cwd``, ``session_id``) never is."""
    kind, pin = session_kind(env, hook_input=hook_input)
    found = member(crew, pin) if kind == "named" else None
    return bool(found) and crew.get("roles", {}).get(role) == found[0]


def _is_process_worker(hook_input: dict | None) -> bool:
    if not hook_input or not hook_input.get("cwd"):
        return False
    marker = read_marker(hook_input.get("cwd"))
    if not marker:
        return False
    recorded = marker.get("session_id")
    current = hook_input.get("session_id")
    # no id on either side: the marker alone says this worktree runs a process worker
    return not recorded or not current or recorded == current


def load(path: Path, notes: list[str] | None = None) -> dict[str, Any]:
    """The crew at ``path``, validated and merged over ``DEFAULTS``; ``notes`` collects the
    transition keys found (``show`` prints them)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CrewError(f"{path}: unreadable ({type(exc).__name__})") from exc
    if not isinstance(data, dict):
        raise CrewError(f"{path}: needs an object")
    version = data.get("version")
    if version is None or version == 1:
        raise CrewError(VERSION_1)
    if version != VERSION or isinstance(version, bool):
        raise CrewError(f"{path}: version {version!r} is not {VERSION}")
    _drop_retired(path, data)
    _validate(path, data)
    _drop_former_lenses(path, data)
    found = _transition_keys(data)
    if notes is not None and found:
        notes.append(
            f"v7 transition keys present ({', '.join(found)}): remove them at the switchover "
            f"cleanup, {V7_TRANSITION_ENDS}"
        )
    return _merge(data)


def _drop_retired(path: Path, data: dict[str, Any]) -> None:
    for key in RETIRED_KEYS:
        if key in data:
            del data[key]
            print(f"crew: {key} is no longer read; remove it from {path}", file=sys.stderr)


def _drop_former_lenses(path: Path, data: dict[str, Any]) -> None:
    lens_keys = set(DEFAULTS["lenses"]) | set(data.get("lenses", {}))
    for key in ("ready_lenses", "t2_panel"):
        if key not in data:
            continue
        for lens in data[key]:
            if lens not in lens_keys:
                print(
                    f"crew: {path}: {key}: {lens!r} is a former default lens no longer defined; "
                    "left out (define it under lenses or drop the entry)",
                    file=sys.stderr,
                )
        data[key] = [lens for lens in data[key] if lens in lens_keys]


def _fail(path: Path, message: str) -> CrewError:
    return CrewError(f"{path}: {message}")


def _check(path: Path, value: Any, default: Any, dotted: str) -> None:
    """``value`` has the shape of ``default``: the same keys (no new one) and types."""
    if isinstance(default, dict):
        if not isinstance(value, dict):
            raise _fail(path, f"{dotted} must be an object")
        for key, item in value.items():
            if key not in default:
                raise _fail(path, f"unknown key {dotted}.{key}")
            _check(path, item, default[key], f"{dotted}.{key}")
    elif isinstance(default, list):
        _check_list(path, value, default, dotted)
    else:
        _check_scalar(path, value, default, dotted)


def _check_scalar(path: Path, value: Any, default: Any, dotted: str) -> None:
    leaf = dotted.rsplit(".", 1)[-1]
    if default is None:
        number = dotted in NUMBER_OR_NULL or leaf in NUMBER_OR_NULL
        if not (value is None or isinstance(value, str) or (number and _is_int(value))):
            kind = "a number, a string or null" if number else "a string or null"
            raise _fail(path, f"{dotted} must be {kind}")
    elif isinstance(default, bool):
        if not isinstance(value, bool):
            raise _fail(path, f"{dotted} must be true or false")
    elif isinstance(default, int):
        if not _is_int(value):
            raise _fail(path, f"{dotted} must be a number")
    elif isinstance(default, str):
        if not isinstance(value, str):
            raise _fail(path, f"{dotted} must be a string")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_list(path: Path, value: Any, default: list, dotted: str) -> None:
    if not isinstance(value, list):
        raise _fail(path, f"{dotted} must be a list")
    if default and _is_int(default[0]):
        if len(value) != len(default) or not all(_is_int(v) for v in value):
            raise _fail(path, f"{dotted} must be {len(default)} numbers")
    elif not all(isinstance(v, str) for v in value):
        raise _fail(path, f"{dotted} must be a list of strings")


def _validate(path: Path, data: dict[str, Any]) -> None:
    for key in data:
        if key not in DEFAULTS and key not in ("version", "roles", "members"):
            raise _fail(path, f"unknown key {key}")
    for key in ("roles", "members"):
        if not isinstance(data.get(key), dict):
            raise _fail(path, f"{key} must be an object")
    slugs = _validate_members(path, data["members"])
    _validate_roles(path, data["roles"], slugs)
    for key, value in data.items():
        if key in ("lenses", "fallback") or key not in DEFAULTS:
            continue
        _check(path, value, DEFAULTS[key], key)
    _validate_lenses(path, data, slugs)
    _validate_fallback(path, data.get("fallback", {}))
    reviewer = data.get("sla", {}).get("t2_second_reviewer")
    if reviewer is not None and reviewer not in slugs:
        raise _fail(path, f"sla.t2_second_reviewer {reviewer!r} is no member")
    _validate_local_rules(path, data.get("local_rules", []))
    for key, text in data.get("labels", {}).items():
        if not text.strip() or len(text) > LABEL_CHARS or "\n" in text or "\r" in text:
            raise _fail(
                path,
                f"labels.{key} must be one non-empty line of at most {LABEL_CHARS} characters",
            )
    _validate_paths(path, data)


def _validate_lenses(path: Path, data: dict[str, Any], slugs: set[str]) -> None:
    lenses = data.get("lenses", {})
    if not isinstance(lenses, dict):
        raise _fail(path, "lenses must be an object")
    for key, lens in lenses.items():
        _check(path, lens, _lens(key), f"lenses.{key}")
        keeper = lens.get("keeper")
        if keeper is not None and keeper not in slugs:
            raise _fail(path, f"lenses.{key}.keeper {keeper!r} is no member")
    lens_keys = set(DEFAULTS["lenses"]) | set(lenses)
    for key in ("ready_lenses", "t2_panel"):
        for lens in data.get(key, []):
            if lens not in lens_keys and lens not in FORMER_DEFAULT_LENSES:
                raise _fail(path, f"{key}: {lens!r} is no lens")


def _validate_local_rules(path: Path, rules: list[str]) -> None:
    if len(rules) > LOCAL_RULES_MAX:
        raise _fail(path, f"local_rules holds {len(rules)} entries, the cap is {LOCAL_RULES_MAX}")
    for i, rule in enumerate(rules):
        if len(rule) > LOCAL_RULE_CHARS or "\n" in rule or "\r" in rule:
            raise _fail(
                path,
                f"local_rules[{i}] must be one line of at most {LOCAL_RULE_CHARS} characters",
            )


def _validate_members(path: Path, entries: dict[str, Any]) -> set[str]:
    for slug, entry in entries.items():
        if not isinstance(entry, dict):
            raise _fail(path, f"members.{slug} must be an object")
        for key, value in entry.items():
            dotted = f"members.{slug}.{key}"
            if key in V7_MEMBER_KEYS:
                if not isinstance(value, str):
                    raise _fail(path, f"{dotted} must be a string")
                continue
            if key not in MEMBER_KEYS:
                raise _fail(path, f"unknown key {dotted}")
            kind = MEMBER_KEYS[key]
            ok = isinstance(value, kind) and not (kind is not bool and isinstance(value, bool))
            if ok and kind is list:
                ok = all(isinstance(v, str) for v in value)
            if not ok:
                raise _fail(path, f"{dotted} must be {_KIND_NAMES[kind]}")
        if not str(entry.get("name") or "").strip():
            raise _fail(path, f"members.{slug}.name is missing")
    return set(entries)


_KIND_NAMES = {str: "a string", list: "a list of strings", bool: "true or false"}


def _validate_roles(path: Path, roles: dict[str, Any], slugs: set[str]) -> None:
    for key, slug in roles.items():
        if key not in ROLE_KEYS and key not in V7_TRANSITION:
            raise _fail(path, f"roles.{key} is no role key (one of {', '.join(ROLE_KEYS)})")
        if not isinstance(slug, str) or slug not in slugs:
            raise _fail(path, f"roles.{key} {slug!r} is no member")
    for old, new in V7_TRANSITION.items():
        if old not in roles:
            continue
        if new not in roles:
            raise _fail(path, f"roles.{old} needs roles.{new} beside it (its version-2 key)")
        if roles[old] != roles[new]:
            raise _fail(
                path, f"roles.{old} {roles[old]!r} differs from roles.{new} {roles[new]!r}"
            )


def _validate_fallback(path: Path, fallback: Any) -> None:
    if not isinstance(fallback, dict):
        raise _fail(path, "fallback must be an object")
    for key, target in fallback.items():
        if key not in ROLE_KEYS:
            raise _fail(path, f"unknown key fallback.{key}")
        if target not in FALLBACK_TARGETS:
            raise _fail(path, f"fallback.{key} {target!r} is no role key nor human_bundle")


_LENS_PATHS = ("questions", "t2_questions", "registry")


def _validate_paths(path: Path, data: dict[str, Any]) -> None:
    """Fail-closed: every path a reader will open exists now."""
    root = path.parent.parent
    named = [(f"files.{k}", v) for k, v in data.get("files", {}).items()]
    for key, lens in data.get("lenses", {}).items():
        named += [(f"lenses.{key}.{f}", lens.get(f)) for f in _LENS_PATHS]
    for dotted, value in named:
        if value is not None and not (root / value).exists():
            raise _fail(path, f"{dotted} {value!r} does not exist in {root}")


def _transition_keys(data: dict[str, Any]) -> list[str]:
    found = [f"roles.{k}" for k in V7_TRANSITION if k in data["roles"]]
    for key in V7_MEMBER_KEYS:
        if any(key in entry for entry in data["members"].values()):
            found.append(f"members.*.{key}")
    return found


def _merge(data: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(DEFAULTS)
    for key, value in data.items():
        if key == "lenses":
            for lens, fields in value.items():
                merged["lenses"][lens] = {**merged["lenses"].get(lens, _lens(lens)), **fields}
        elif key == "board" and "states" in value:
            states = {**merged["board"]["states"], **value["states"]}
            merged["board"] = {**merged["board"], **value, "states": states}
        elif isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **copy.deepcopy(value)}
        else:
            merged[key] = copy.deepcopy(value)
    merged["roles"] = {k: v for k, v in data["roles"].items() if k not in V7_TRANSITION}
    merged["members"] = {
        slug: {k: v for k, v in entry.items() if k not in V7_MEMBER_KEYS}
        for slug, entry in data["members"].items()
    }
    return merged


def at(root: str | Path) -> Path | None:
    """The crew file ``root`` itself declares (its own file or its config pointer), never one
    above it; None without one."""
    found = _crew_at(Path(root).resolve())
    return found if isinstance(found, Path) else None


def find_and_load(start: str | Path | None = None) -> tuple[Path | None, dict[str, Any] | None]:
    path = find(start)
    if path is None:
        return None, None
    return path, load(path)


def members(crew: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {k: v for k, v in crew.get("members", {}).items() if isinstance(v, dict)}


def member(crew: dict[str, Any], who: str) -> tuple[str, dict[str, Any]] | None:
    """The member whose slug or name is ``who`` (case-insensitive)."""
    key = who.strip().lower()
    for slug, entry in members(crew).items():
        if slug.lower() == key or str(entry.get("name", "")).strip().lower() == key:
            return slug, entry
    return None


def holder(crew: dict[str, Any], role: str) -> dict[str, Any] | None:
    """The member holding a working-mode role (``roles.<role>`` → slug)."""
    slug = crew.get("roles", {}).get(role)
    entry = members(crew).get(slug) if isinstance(slug, str) else None
    return entry


def holder_name(crew: dict[str, Any], role: str) -> str | None:
    entry = holder(crew, role)
    name = str(entry.get("name", "")).strip() if entry else ""
    return name or None


def skill_name(name: str, crew: dict[str, Any] | None = None, strict: bool = False) -> str | None:
    """``<prefix>-<name lowercased>``. Lookup refuses only what could leave the skills folder (a
    separator, ``..``, a control character or space), so ``Zoë`` still finds ``weside-zoë``;
    ``strict`` (a stub to write) keeps to ``[a-z0-9_-]``."""
    prefix = str((crew or {}).get("skill_prefix") or "weside").strip().lower()
    skill = f"{prefix}-{name.strip().lower()}"
    if strict:
        return skill if _SAFE.fullmatch(skill) else None
    unsafe = any(part in skill for part in ("/", "\\", "..", " ")) or not skill.isprintable()
    return None if unsafe or not name.strip() else skill


def workplace(crew_path: Path, entry: dict[str, Any]) -> Path | None:
    value = entry.get("workplace")
    if not isinstance(value, str) or not value.strip():
        return None
    return (crew_path.parent.parent / value.strip()).resolve()


def is_stub(path: Path) -> bool:
    try:
        return STUB_MARKER in path.read_text(encoding="utf-8")
    except OSError:
        return False


def skill_path(name: str, cwd: str | Path, home: Path | None = None) -> tuple[Path, bool] | None:
    """(SKILL.md, loadable) for ``name``'s role skill, or None.

    Loadable: under ``<cwd>/.claude/skills/`` or ``~/.claude/skills/``, where the Skill tool finds
    it. Otherwise the member's ``workplace`` repo (crew in force for ``cwd``): a session reads it.
    """
    try:
        crew_path, crew = find_and_load(cwd)
    except CrewError:
        crew_path, crew = None, None
    skill = skill_name(name, crew)
    if skill is None:
        return None
    for root in (Path(cwd) / ".claude" / "skills", (home or Path.home()) / ".claude" / "skills"):
        if (root / skill / "SKILL.md").is_file():
            return root / skill / "SKILL.md", True
    found = member(crew, name) if crew else None
    place = workplace(crew_path, found[1]) if crew_path and found else None
    if place and (place / ".claude" / "skills" / skill / "SKILL.md").is_file():
        return place / ".claude" / "skills" / skill / "SKILL.md", False
    return None


def render_stub(crew: dict[str, Any], slug: str) -> str:
    entry = members(crew)[slug]
    name = str(entry.get("name") or slug).strip()
    components = ", ".join(str(c) for c in entry.get("components") or []) or "none"
    values = {
        "skill": skill_name(name, crew, strict=True) or slug,
        "name": name,
        "role": label(crew, slug) or "member",
        "components": components,
        "coordinator": holder_name(crew, "coordinator") or "the coordinator",
    }
    text = TEMPLATE.read_text(encoding="utf-8")
    end = text.index("\n---", 3) + 4  # the frontmatter: values go into double-quoted YAML
    head, body = text[:end], text[end:]
    for key, value in values.items():
        plain = " ".join(value.split())
        head = head.replace("{{" + key + "}}", json.dumps(plain, ensure_ascii=False)[1:-1])
        body = body.replace("{{" + key + "}}", plain)
    return head + body


def stubs(crew_path: Path, crew: dict[str, Any], write: bool = False) -> list[str]:
    """One line per member without a role skill in its workplace: the path (written with --write)."""
    lines = []
    for slug, entry in members(crew).items():
        name = str(entry.get("name") or "").strip()
        skill = skill_name(name, crew, strict=True) if name else None
        place = workplace(crew_path, entry)
        if not skill or place is None:
            continue
        target = place / ".claude" / "skills" / skill / "SKILL.md"
        if target.exists():
            continue
        if write:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render_stub(crew, slug), encoding="utf-8")
        lines.append(str(target))
    return lines


def label(crew: dict[str, Any], slug: str) -> str:
    """A member's label: its title, else the role key it holds, else its specialist field."""
    entry = members(crew).get(slug, {})
    held = next((role for role, who in crew.get("roles", {}).items() if who == slug), None)
    text = entry.get("title") or held or entry.get("specialist") or ""
    return " ".join(str(text).split())


def show(crew_path: Path, crew: dict[str, Any]) -> dict[str, Any]:
    return {"path": str(crew_path), **crew}


def _member_places(crew_path: Path, crew: dict[str, Any], who: str) -> list[tuple[str, str, Path]]:
    """(dotted key, value as written, absolute path) for the member's workplace, then each extra
    repo; CrewError for an unknown member."""
    found = member(crew, who)
    if found is None:
        raise CrewError(f"{crew_path}: no member {who!r}")
    slug, entry = found
    root = crew_path.parent.parent
    named = [(f"members.{slug}.workplace", entry.get("workplace") or ".")]
    named += [(f"members.{slug}.extra_repos", repo) for repo in entry.get("extra_repos") or []]
    return [(dotted, value, (root / value.strip()).resolve()) for dotted, value in named]


def workplace_paths(crew_path: Path, crew: dict[str, Any], who: str) -> list[Path]:
    """The member's workplace, then each extra repo, absolute; CrewError for an unknown member or
    a directory that does not exist."""
    paths = []
    for dotted, value, place in _member_places(crew_path, crew, who):
        if not place.is_dir():
            raise CrewError(f"{crew_path}: {dotted} {value!r} is no directory ({place})")
        paths.append(place)
    return paths


def workplace_path(crew_path: Path, crew: dict[str, Any], who: str) -> Path:
    """The member's workplace alone, absolute; CrewError for an unknown member or a workplace that
    does not exist (its extra repos are not looked at)."""
    dotted, value, place = _member_places(crew_path, crew, who)[0]
    if not place.is_dir():
        raise CrewError(f"{crew_path}: {dotted} {value!r} is no directory ({place})")
    return place


def extra_repos(crew_path: Path, crew: dict[str, Any], who: str) -> tuple[list[Path], list[str]]:
    """(the member's extra repos that exist here, absolute; the values of those that do not, as
    written in the crew); CrewError for an unknown member."""
    present, missing = [], []
    for _, value, place in _member_places(crew_path, crew, who)[1:]:
        if place.is_dir():
            present.append(place)
        else:
            missing.append(value)
    return present, missing


def lenses(
    crew_path: Path, crew: dict[str, Any], which: str | None = None
) -> list[dict[str, Any]]:
    """The lenses (all, ``ready`` = ``ready_lenses``, ``t2`` = ``t2_panel``) in order, paths
    absolute, the keeper as slug and name."""
    root = crew_path.parent.parent
    keys = {"ready": crew["ready_lenses"], "t2": crew["t2_panel"]}.get(which or "")
    out = []
    for key in keys if keys is not None else list(crew["lenses"]):
        lens = crew["lenses"][key]
        keeper = lens.get("keeper")
        out.append(
            {
                "lens": key,
                "agent": lens.get("agent"),
                "questions": _absolute(root, lens.get("questions")),
                "t2_questions": _absolute(root, lens.get("t2_questions")),
                "registry": _absolute(root, lens.get("registry")),
                "keeper": keeper,
                "keeper_name": members(crew).get(keeper, {}).get("name") if keeper else None,
                "sample": lens.get("sample"),
            }
        )
    return out


def _absolute(root: Path, value: str | None) -> str | None:
    return str((root / value).resolve()) if value else None


def _positional(args: list[str], flags: tuple[str, ...]) -> str | None:
    """The first argument that is neither a flag nor a flag's value."""
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg in flags:
            skip = True
        elif not arg.startswith("--"):
            return arg
    return None


def _opt(argv: list[str], flag: str) -> str | None:
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def _skill_path_cli(argv: list[str]) -> int:
    found = skill_path(argv[1], _opt(argv, "--cwd") or Path.cwd()) if len(argv) > 1 else None
    if found is None:
        return 1
    path, loadable = found
    kind = "stub" if is_stub(path) else "skill"
    print(f"{path}\t{'loadable' if loadable else 'workplace'}\t{kind}")
    return 0


def _print_members(crew: dict[str, Any]) -> None:
    for slug, entry in members(crew).items():
        name = str(entry.get("name") or "").strip()
        if name:
            print(name + "\t" + label(crew, slug))


def _load_cli(
    argv: list[str], notes: list[str] | None = None
) -> tuple[Path, dict[str, Any]] | None:
    try:
        crew_path = find(_opt(argv, "--from"))
        crew = load(crew_path, notes) if crew_path is not None else None
    except CrewError as exc:
        print(f"crew: {exc}", file=sys.stderr)
        return None
    return (crew_path, crew) if crew_path is not None and crew is not None else None


def _path_cli(argv: list[str]) -> int:
    found = find(_opt(argv, "--from"))
    if found is not None:
        print(found)
    return 0 if found is not None else 1


VERBS = (
    "path",
    "show",
    "members",
    "skill-path",
    "stubs",
    "is-role",
    "workplace",
    "lenses",
    "session-kind",
)


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in VERBS:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    cmd = argv[0]
    if cmd in ("skill-path", "path"):
        return _skill_path_cli(argv) if cmd == "skill-path" else _path_cli(argv)
    notes: list[str] = []
    loaded = _load_cli(argv, notes)
    if loaded is None:
        return 1
    crew_path, crew = loaded
    if cmd == "is-role":
        return _is_role_cli(argv, crew)
    if cmd == "show":
        for note in notes:
            print(f"crew: {note}", file=sys.stderr)
    try:
        return _READERS[cmd](argv, crew_path, crew)
    except CrewError as exc:
        print(f"crew: {exc}", file=sys.stderr)
        return 1


def _show_cli(_argv: list[str], crew_path: Path, crew: dict[str, Any]) -> int:
    print(json.dumps(show(crew_path, crew), ensure_ascii=False, indent=2))
    return 0


def _members_cli(_argv: list[str], _crew_path: Path, crew: dict[str, Any]) -> int:
    _print_members(crew)
    return 0


def _workplace_cli(argv: list[str], crew_path: Path, crew: dict[str, Any]) -> int:
    who = _positional(argv[1:], ("--from",))
    if not who:
        print("crew: workplace needs a member slug", file=sys.stderr)
        return 2
    for place in workplace_paths(crew_path, crew, who):
        print(place)
    return 0


def _lenses_cli(argv: list[str], crew_path: Path, crew: dict[str, Any]) -> int:
    which = _opt(argv, "--set")
    if which not in (None, "ready", "t2"):
        print("crew: --set takes ready or t2", file=sys.stderr)
        return 2
    print(json.dumps(lenses(crew_path, crew, which), ensure_ascii=False, indent=2))
    return 0


def _stubs_cli(argv: list[str], crew_path: Path, crew: dict[str, Any]) -> int:
    for line in stubs(crew_path, crew, write="--write" in argv):
        print(line)
    return 0


def _session_kind_cli(argv: list[str], _crew_path: Path, crew: dict[str, Any]) -> int:
    session = _opt(argv, "--session") or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    role = role_of_session(crew, os.environ, {"cwd": os.getcwd(), "session_id": session})
    print(role or "none")
    if role is None:
        print(NO_ROLE)
    return 0


_READERS = {
    "show": _show_cli,
    "members": _members_cli,
    "workplace": _workplace_cli,
    "lenses": _lenses_cli,
    "stubs": _stubs_cli,
    "session-kind": _session_kind_cli,
}


def _is_role_cli(argv: list[str], crew: dict[str, Any]) -> int:
    session = _opt(argv, "--session") or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    here = {"cwd": os.getcwd(), "session_id": session}
    role = _positional(argv[1:], ("--from", "--session"))
    if role not in ROLE_KEYS:
        print(f"crew: unknown role {role}", file=sys.stderr)
        return 1
    return 0 if holds_role(crew, role, os.environ, here) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
