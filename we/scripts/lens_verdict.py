#!/usr/bin/env python3
"""The one reader and writer of lens verdicts: a panel of fresh lens agents judging a plan
(Ready) or a PR diff (T2), recorded per subject and checked against today's plan blob or PR head.

Usage:
  lens_verdict.py plan ready KEY [--plan PATH]   start a Ready panel on the story plan
                                                 docs/plans/KEY-story.md (or PATH, inside the
                                                 repo; the panel stays bound to it); prints one
                                                 dispatch entry per Ready lens as JSON
  lens_verdict.py plan t2 PR                     start a T2 panel on the PR's head (``gh``)
  lens_verdict.py arm [COMMAND]                  exit 0 when COMMAND (else stdin) is a red arm in
                                                 test form (the skill may run it), else 1 with why
  lens_verdict.py write ID LENS < ANSWER         record the lens agent's answer (its last JSON
                                                 object); exit 1 naming what is refused
  lens_verdict.py write ID LENS --failed REASON  record the lens red without findings
  lens_verdict.py check ID                       one line per lens and the panel; exit 0 only green
  lens_verdict.py post t2-prN                    post the panel comment on the PR's head (PASS or
                                                 FAIL); exit 0 only for a posted PASS
  lens_verdict.py samples [--keeper SLUG]        the sampled green verdicts nobody has read
  lens_verdict.py sampled ID LENS                mark a sample read
  lens_verdict.py rounds KEY                     the story's Ready rounds: per round and lens
                                                 the verdict and its BLOCKING/WARNING/NOTE count

ID is ``ready-<KEY>`` or ``t2-pr<N>``. Exit 2: a usage error, the verdict directory unusable, or
the crew file unusable.

Where: one JSON file per subject in ``<git common dir>/we-lens/`` (shared by every worktree of the
repo, never in the tree, so a PR cannot carry its own verdict), plus ``samples.jsonl`` there.

Schema, version 1, closed: an unknown key anywhere refuses the file or the answer, naming the key.
File: ``version``, ``kind`` (ready|t2), ``subject``, ``bound_to`` (``plan_blob`` for ready, the
output of ``git hash-object`` on the plan; ``head`` for t2, the PR's head SHA), ``expected`` (the
lenses copied from the crew when the panel started, so a crew edit cannot shrink a running panel),
optional ``plan`` (ready only: the plan's path relative to the repo root when ``--plan`` named
one, so ``write`` and ``check`` re-hash that file), ``round`` (ready only: the panel's round, 1 for
the first plan version; ``plan ready`` on a new plan blob writes the stored round plus one, on the
same blob it keeps it, so a restart is no round; a file without ``round`` takes its round from
evidence, see Derived round), ``round_derived`` (ready only: where the round's base came from when
it was derived, e.g. ``base: round 2 derived: 2 plan blobs with logged lens verdicts: e82588a3,
e0d2159d``) and ``verdicts.<lens>``: ``verdict``
(green|red), ``agent``, ``ran_at``, ``sample``, ``sampled``, ``findings``, and ``failure`` (why a
lens was recorded red without findings). A finding:
``severity`` (BLOCKING|WARNING|NOTE), ``claim``, ``where``, ``question`` (the question-file line it
answers; required on Ready), ``red_arm`` (``command``, ``exit``, ``run``) and ``status``
(standing|refuted). An answer is ``{"findings": [...]}`` whose findings carry only ``severity``,
``claim``, ``where``, ``question`` and ``red_arm`` (``command``, plus ``exit`` once the skill ran
it); strings are capped at ``TEXT_CHARS`` with control characters stripped.

Green rule (Vyra 04.11.): a lens is red when a BLOCKING or WARNING finding stands, else green; a
NOTE is listed and never red; a ``refuted`` finding does not count. The panel is green only when
every expected lens has a verdict, every verdict is green, and the binding is today's plan blob or
PR head; a missing lens, a red lens and a stale binding each print a line and count red. The
verdict and the status are computed here from the findings, never taken from the caller, and
``check`` recomputes them from the stored findings.

Carried warnings (Ready only, crew ``ready_panel.warning_ok_after_rounds`` = N): from round N on,
a lens that is red only through standing WARNINGs (no BLOCKING, no ``failure``) prints ``lens
<lens>: green (warnings carried: …)`` and counts green; the panel line then reads ``green
(warnings carried)`` and ``check_panel`` returns the warnings (lens, claim, where) for the board's
Selected row. A BLOCKING stays red in every round; without the key, and on every T2 panel, a
WARNING stays red. The verdict file keeps the lens ``red``: carrying is decided by ``check``.

Derived round (Ready, a file without ``round``, i.e. written by 8.10.0 or older): the round is the
number of distinct plan blobs that provably had a Ready panel: the blobs of this panel's lines in
``samples.jsonl`` (every green lens verdict of 8.10.0 and older appended one, ``bound`` = plan blob)
plus the blob the file is bound to. A plan version without a logged run (a draft commit, a panel
whose lenses were all red) never counts, a restart on the same blob counts once; without a line the
round stays 1. ``check`` prints ``panel <ID>: round N (derived: …)``, ``plan ready`` on a new blob
writes N + 1 with ``round_derived`` (``base: round N derived: …``, kept by every later round), and the verdicts are never in git, so git history is no
source. The log is as writable as the verdict file: deriving loosens nothing a session could not
already write.

Red arm (T2): a BLOCKING or WARNING finding needs ``red_arm.command`` and ``red_arm.exit``, or the
answer is refused naming the finding. The skill runs the arm (never this script: lens output is
foreign text) only when ``arm`` accepts its form; ``exit`` 0 means the finding is ``refuted``; a
non-zero exit means ``standing``; 124 (``timeout``), 126, 127 or above 128 (a signal) mean the arm
proved nothing and the answer is refused as a finding without red arm (Kiska 04.11.). A command not
in test form is never run: the finding stays ``standing`` with ``run: false``, whatever exit the
caller recorded.

Carried panel (T2 only): a panel bound to an older head ``old`` stays green on the PR's current
head ``new`` when every expected lens is green on ``old``, ``old`` is an ancestor of ``new``, and
the change ``old..new`` touches no file the PR's class hit: the PR is classified on
``merge-base(origin/main, new)..new`` by ``risk_runner.classify`` (the merge hook's own runner and
rules); class ``T0`` carries, otherwise the delta's files (``git diff --name-only old new``) must
miss every hit line's file, and a class without hit lines carries nothing. A clean merge of the
default branch therefore carries; a delta on a risk path, a head outside the PR's history, a red
panel, no panel and any git or classifier failure do not. ``check`` prints ``panel <ID>: carried
from <old> to <new> (<why>)`` in place of the stale line, or the stale line plus ``panel <ID>: not
carried (<why>)``; ``check_t2`` returns the carried head, which the merge hook reads to take the
security card from that head too. ``post`` posts a carried panel on the new head. The carry is
computed on every ``check``; nothing is written.

No skip, no override: no field can skip, confirm, waive or lift anything; ``skip``, ``override``,
``one_way``, ``go`` and every other unknown key are refused. A red panel turns green only through a
fresh panel on a new plan blob or head; a green T2 panel is carried only as above. Any session
can write this file, so it gates only a two-way T2 merge and the move to Selected; the one-way brake never reads it.

Panel comment (T2): ``post`` puts the panel's state on GitHub, where a repo's self-merge judge reads
it (a one-way PR outside the brake's core merges itself 2 h after a green panel on its head). The
format is that judge's contract, pinned by ``fixtures/brake-self-merge/judge.json``::

    <!-- t2-panel -->
    ## T2 panel — #<N> @ `<head sha, 40 hex>`
    **Overall: PASS**

``Overall: FAIL`` when ``check`` is red, so a red rerun on the same head voids an earlier PASS (the
last comment on the head decides). Nothing is posted while the binding is stale or the head unknown:
the comment always names the head the verdicts were given on. Posted through ``gh pr comment`` as
the session's GitHub identity; like the file, any session could post one, so it is a process
signal, not a lock.

Severity log (Ready only): every ``write`` on a Ready panel appends one line with ``kind:
"severity"`` to ``samples.jsonl``: ``id``, ``lens``, ``bound`` (the plan blob), ``round``,
``verdict``, ``failure`` (true when recorded with ``--failed``), ``ran_at`` and the counts
``blocking``, ``warning``, ``note`` (every finding, refuted ones too; a Ready finding is never
refuted). ``rounds KEY`` reads them: one line per round and lens, the last write on that blob
winning. Every other reader of the file (sample counter, ``samples``, the derived round) reads
only lines without ``kind``: a severity line, red or green, counts no sample and no round. The
derived round stays the count of 8.10.0's green lines on purpose: it rebuilds rounds of files
written before ``round`` existed, and a severity line is only ever written next to a file that
already stores its round.

Sample: every ``lenses.<k>.sample``-th green verdict of a lens is marked ``sample: true`` and listed
by ``samples`` until ``sampled`` marks it read; nobody waits on a sample. The verdict file is
written first (temp file plus ``os.replace``), the sample line after it: a crash between the two
loses one count, never a verdict.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ``python3 -I`` leaves this directory off sys.path (``-I`` implies ``-P``)
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import crew as crew_mod  # noqa: E402
import risk_runner  # noqa: E402

VERSION = 1
TEXT_CHARS = 500
SEVERITIES = ("BLOCKING", "WARNING", "NOTE")
COUNTING = ("BLOCKING", "WARNING")
SEVERITY_KIND = "severity"
NO_PROOF_EXITS = (124, 126, 127)
ARM_FORMS = ("pytest ", "python3 -m pytest ", "bash scripts/", "python3 scripts/")
ARM_FORBIDDEN = (";", "|", "&", "$(", "`", ">", "<", "\n", "\r")
ID_RE = re.compile(r"\A(?:ready-(?P<key>[A-Za-z][A-Za-z0-9_]*-\d+)|t2-pr(?P<pr>\d+))\Z")
FILE_KEYS = (
    "version",
    "kind",
    "subject",
    "bound_to",
    "expected",
    "verdicts",
    "plan",
    "round",
    "round_derived",
)
VERDICT_KEYS = ("verdict", "agent", "ran_at", "sample", "sampled", "findings", "failure")
FINDING_KEYS = ("severity", "claim", "where", "question", "red_arm", "status")
ANSWER_FINDING_KEYS = ("severity", "claim", "where", "question", "red_arm")
ARM_KEYS = ("command", "exit", "run")
ANSWER_ARM_KEYS = ("command", "exit")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class RefusedError(Exception):
    """Exit 1: a red answer or file, with the line to print."""


class UnusableError(Exception):
    """Exit 2: the verdict directory, the crew file or the usage."""


# --- git and the subject ---------------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        raise UnusableError(f"git {' '.join(args)}: {out.stderr.strip() or 'failed'}")
    return out.stdout.strip()


def repo_root(start: Path) -> Path:
    return Path(_git(start, "rev-parse", "--show-toplevel"))


def verdict_dir(root: Path) -> Path:
    common = Path(_git(root, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = (root / common).resolve()
    return common / "we-lens"


def parse_id(vid: str) -> tuple[str, str]:
    """(kind, subject) of a verdict id; UnusableError for anything else (it becomes a file name)."""
    found = ID_RE.match(vid)
    if not found:
        raise UnusableError(f"verdict id {vid!r}: expected ready-<KEY> or t2-pr<N>")
    return ("ready", found.group("key")) if found.group("key") else ("t2", found.group("pr"))


def plan_path(root: Path, key: str, rel: str | None = None) -> Path:
    return root / rel if rel else root / "docs" / "plans" / f"{key}-story.md"


def plan_rel(root: Path, given: str) -> str:
    """``--plan`` as a path relative to the repo root; UnusableError outside the repo."""
    path = Path(given)
    path = (path if path.is_absolute() else Path.cwd() / path).resolve()
    try:
        return path.relative_to(root.resolve()).as_posix()
    except ValueError:
        raise UnusableError(f"--plan {given}: not inside the repo {root}") from None


def current_binding(
    root: Path, kind: str, subject: str, plan: str | None = None
) -> dict[str, str]:
    if kind == "ready":
        path = plan_path(root, subject, plan)
        if not path.is_file():
            raise RefusedError(f"plan {path.relative_to(root)}: missing")
        return {"plan_blob": _git(root, "hash-object", str(path))}
    gh = shutil.which("gh")
    out = (
        subprocess.run(
            [gh, "pr", "view", subject, "--json", "headRefOid", "-q", ".headRefOid"],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(root),
        )
        if gh
        else None
    )
    head = out.stdout.strip() if out is not None and out.returncode == 0 else ""
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise RefusedError(f"panel t2-pr{subject}: head unknown")
    return {"head": head}


# --- crew ------------------------------------------------------------------------------------


def load_crew(root: Path) -> tuple[Path, dict[str, Any]]:
    """The crew in force, or the defaults (generic questions) when the repo has none."""
    try:
        path, crew = crew_mod.find_and_load(root)
    except crew_mod.CrewError as exc:
        raise UnusableError(f"crew: {exc}") from exc
    if path is None:
        return root / ".weside" / "crew.json", crew_mod._merge({"roles": {}, "members": {}})
    return path, crew


# --- the verdict file ------------------------------------------------------------------------


def _closed(value: Any, allowed: tuple[str, ...], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RefusedError(f"{where}: needs an object")
    for key in value:
        if key not in allowed:
            raise RefusedError(
                f"{where}: key {key!r} refused (no such field; nothing can be skipped)"
            )
    return value


def _text(value: Any, where: str, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value.strip()):
        raise RefusedError(f"{where}: needs text")
    return _CONTROL.sub("", value)[:TEXT_CHARS]


def _arm(value: Any, where: str, keys: tuple[str, ...]) -> dict[str, Any] | None:
    if value is None:
        return None
    arm = _closed(value, keys, where)
    command = _text(arm.get("command"), f"{where}.command", required=True)
    code = arm.get("exit")
    if code is not None and (isinstance(code, bool) or not isinstance(code, int)):
        raise RefusedError(f"{where}.exit: needs an integer")
    out: dict[str, Any] = {"command": command, "exit": code}
    if "run" in keys:
        out["run"] = arm.get("run") is True
    return out


def arm_form(command: str) -> str | None:
    """None when the skill may run ``command`` as a red arm, else why it may not."""
    for bad in ARM_FORBIDDEN:
        if bad in command:
            return f"contains {bad!r}"
    if not command.startswith(ARM_FORMS):
        return "not a test command (pytest, bash scripts/…, python3 scripts/…)"
    for word in command.split()[1:]:
        if any(_leaves_repo(part) for part in _path_parts(word)):
            return f"leaves the repo ({word})"
    return None


def _path_parts(word: str) -> list[str]:
    """The word, the word after its leading dashes and each part after an ``=``."""
    parts = [word, word.lstrip("-")]
    parts += word.split("=")[1:]
    return parts


def _leaves_repo(part: str) -> bool:
    return part.startswith(("/", "~")) or ".." in part.split("/")


def _finding(raw: Any, where: str, kind: str, stored: bool) -> dict[str, Any]:
    f = _closed(raw, FINDING_KEYS if stored else ANSWER_FINDING_KEYS, where)
    severity = f.get("severity")
    if severity not in SEVERITIES:
        raise RefusedError(f"{where}.severity: {severity!r} is none of {', '.join(SEVERITIES)}")
    out = {
        "severity": severity,
        "claim": _text(f.get("claim"), f"{where}.claim", required=True),
        "where": _text(f.get("where"), f"{where}.where"),
        "question": _text(f.get("question"), f"{where}.question", required=kind == "ready"),
        "red_arm": _arm(
            f.get("red_arm"), f"{where}.red_arm", ARM_KEYS if stored else ANSWER_ARM_KEYS
        ),
    }
    out["status"] = _status(out, where, kind, stored)
    return out


def _status(f: dict[str, Any], where: str, kind: str, stored: bool) -> str:
    """standing or refuted, computed; RefusedError for a counting T2 finding without a red arm."""
    arm = f["red_arm"]
    if kind != "t2" or f["severity"] not in COUNTING:
        return "standing"
    claim = f"{where} ({f['severity']}: {f['claim'][:80]})"
    if arm is None or (arm["exit"] is None and arm_form(arm["command"]) is None):
        raise RefusedError(f"{claim}: finding without red arm")
    if arm_form(arm["command"]) is not None:
        arm["exit"], arm["run"] = None, False
        return "standing"
    code = arm["exit"]
    if code in NO_PROOF_EXITS or code > 128 or code < 0:
        raise RefusedError(f"{claim}: finding without red arm (arm exit {code} proves nothing)")
    if not stored:
        arm["run"] = True
    return "refuted" if code == 0 else "standing"


def lens_verdict(findings: list[dict[str, Any]], failure: str | None) -> str:
    standing = [f for f in findings if f["severity"] in COUNTING and f["status"] == "standing"]
    return "red" if failure or standing else "green"


def read_file(path: Path) -> dict[str, Any]:
    """The stored panel, validated; RefusedError when unreadable or not the closed schema."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RefusedError(f"panel {path.stem}: not started (run plan)") from None
    except OSError as exc:
        raise UnusableError(f"{path}: {exc.strerror}") from exc
    except json.JSONDecodeError:
        raise RefusedError(f"panel {path.stem}: verdict file unreadable") from None
    doc = _closed(data, FILE_KEYS, path.stem)
    kind, subject = parse_id(path.stem)
    if doc.get("version") != VERSION or doc.get("kind") != kind or doc.get("subject") != subject:
        raise RefusedError(f"panel {path.stem}: version, kind or subject does not match")
    rel = doc.get("plan")
    if rel is not None and (
        kind != "ready"
        or not isinstance(rel, str)
        or Path(rel).is_absolute()
        or ".." in Path(rel).parts
    ):
        raise RefusedError(f"panel {path.stem}: plan needs a path inside the repo (ready only)")
    bound = _closed(
        doc.get("bound_to"), ("plan_blob",) if kind == "ready" else ("head",), "bound_to"
    )
    round_ = doc.get("round", 1)
    if (kind != "ready" and "round" in doc) or not (
        isinstance(round_, int) and not isinstance(round_, bool) and round_ >= 1
    ):
        raise RefusedError(f"panel {path.stem}: round needs a number of at least 1 (ready only)")
    if "round_derived" in doc and (kind != "ready" or not isinstance(doc["round_derived"], str)):
        raise RefusedError(f"panel {path.stem}: round_derived needs a string (ready only)")
    expected = doc.get("expected")
    if not isinstance(expected, list) or not all(isinstance(x, str) for x in expected):
        raise RefusedError(f"panel {path.stem}: expected needs a list of lenses")
    verdicts = _closed(doc.get("verdicts"), tuple(expected), "verdicts")
    clean = {}
    for lens, raw in verdicts.items():
        v = _closed(raw, VERDICT_KEYS, f"verdicts.{lens}")
        findings = v.get("findings")
        if not isinstance(findings, list):
            raise RefusedError(f"verdicts.{lens}.findings: needs a list")
        stored = [
            _finding(f, f"verdicts.{lens}.findings[{i}]", kind, stored=True)
            for i, f in enumerate(findings)
        ]
        failure = _text(v.get("failure"), f"verdicts.{lens}.failure")
        clean[lens] = {
            **v,
            "findings": stored,
            "failure": failure,
            "verdict": lens_verdict(stored, failure),
        }
    return {**doc, "bound_to": dict(bound), "verdicts": clean}


def _write_atomic(path: Path, doc: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(doc, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        raise UnusableError(f"{path.parent}: {exc.strerror}") from exc


# --- verbs -----------------------------------------------------------------------------------


def plan(root: Path, kind: str, subject: str, plan_arg: str | None = None) -> dict[str, Any]:
    """Start a panel: write the empty verdict file bound to today's subject, return the entries."""
    vid = f"ready-{subject}" if kind == "ready" else f"t2-pr{subject}"
    parse_id(vid)
    if plan_arg is not None and kind != "ready":
        raise UnusableError("--plan: only for plan ready")
    rel = plan_rel(root, plan_arg) if plan_arg is not None else None
    crew_path, crew = load_crew(root)
    try:
        chosen = crew_mod.lenses(crew_path, crew, kind)
    except crew_mod.CrewError as exc:
        raise UnusableError(f"crew: {exc}") from exc
    bound = current_binding(root, kind, subject, rel)
    path = verdict_dir(root) / f"{vid}.json"
    doc: dict[str, Any] = {
        "version": VERSION,
        "kind": kind,
        "subject": subject,
        "bound_to": bound,
        "expected": [lens["lens"] for lens in chosen],
        "verdicts": {},
    }
    if rel is not None:
        doc["plan"] = rel
    if kind == "ready":
        doc["round"], origin = next_round(path, bound)
        if origin is not None:
            doc["round_derived"] = origin
    _write_atomic(path, doc)
    entries = []
    for lens in chosen:
        entry = {
            "id": vid,
            "lens": lens["lens"],
            "agent": lens["agent"],
            "questions": lens["questions"] if kind == "ready" else lens["t2_questions"],
            "registry": lens["registry"],
        }
        if kind == "ready":
            entry["plan"] = str(plan_path(root, subject, rel))
            entry["plan_blob"] = bound["plan_blob"]
        else:
            entry["pr"] = int(subject)
            entry["head"] = bound["head"]
        entries.append(entry)
    return {"id": vid, "kind": kind, "bound_to": bound, "entries": entries}


def next_round(path: Path, bound: dict[str, str]) -> tuple[int, str | None]:
    """The round of a Ready panel started on ``bound`` and, when its base was derived, where it
    came from: 1 without a readable earlier panel, the stored round on the same plan blob (a
    restart), the stored round plus one on a new blob."""
    try:
        old = read_file(path)
    except (RefusedError, UnusableError):
        return 1, None
    stored, origin = panel_round(path.parent, old)
    if origin is not None and "round" not in old:
        origin = f"base: round {stored} {origin}"
    return (stored if old["bound_to"] == bound else stored + 1), origin


def panel_round(vdir: Path, doc: dict[str, Any]) -> tuple[int, str | None]:
    """The stored round with its stored ``round_derived``, or for a file without a round the
    derived round and its origin (see Derived round); the origin is None when nothing was
    derived."""
    if "round" in doc or doc["kind"] != "ready":
        return doc.get("round", 1), doc.get("round_derived")
    vid = f"ready-{doc['subject']}"
    blobs = [
        x["bound"]
        for x in _sample_lines(vdir)
        if x.get("id") == vid and isinstance(x.get("bound"), str) and not x.get("read")
    ]
    blobs.append(doc["bound_to"]["plan_blob"])
    distinct = list(dict.fromkeys(blobs))
    if len(distinct) < 2:
        return 1, None
    names = ", ".join(b[:8] for b in distinct)
    return len(distinct), f"derived: {len(distinct)} plan blobs with logged lens verdicts: {names}"


def parse_answer(text: str) -> dict[str, Any]:
    """The last top-level JSON object in the agent's answer, fenced or bare (an object nested
    in it never counts on its own)."""
    decoder = json.JSONDecoder()
    found, i = None, text.find("{")
    while i != -1:
        try:
            obj, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            i = text.find("{", i + 1)
            continue
        if isinstance(obj, dict):
            found = obj
        i = text.find("{", end)
    if found is None:
        raise RefusedError("no parseable answer: the lens stays missing")
    return found


def write(
    root: Path,
    vid: str,
    lens: str,
    answer: str | None = None,
    failed: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    kind, subject = parse_id(vid)
    vdir = verdict_dir(root)
    path = vdir / f"{vid}.json"
    doc = read_file(path)
    if lens not in doc["expected"]:
        raise RefusedError(f"lens {lens}: not expected in panel {vid}")
    if current_binding(root, kind, subject, doc.get("plan")) != doc["bound_to"]:
        raise RefusedError(f"panel {vid}: stale (start a fresh panel with plan)")
    if failed is not None:
        findings: list[dict[str, Any]] = []
        failure = _text(failed, "--failed", required=True)
    else:
        body = _closed(parse_answer(answer or ""), ("findings",), "answer")
        raw = body.get("findings")
        if not isinstance(raw, list):
            raise RefusedError("answer.findings: needs a list")
        findings = [_finding(f, f"findings[{i}]", kind, stored=False) for i, f in enumerate(raw)]
        failure = None
    verdict = lens_verdict(findings, failure)
    _crew_path, crew = load_crew(root)
    entry = crew["lenses"].get(lens, crew_mod._lens(lens))
    binding = next(iter(doc["bound_to"].values()))
    slot = _sample_slot(vdir, lens, vid, binding, entry.get("sample"))
    sample = verdict == "green" and slot is True
    doc["verdicts"][lens] = {
        "verdict": verdict,
        "agent": entry.get("agent"),
        "ran_at": now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample": sample,
        "sampled": False,
        "findings": findings,
        "failure": failure,
    }
    _write_atomic(path, doc)
    if verdict == "green" and slot is not None:
        _append(
            vdir / "samples.jsonl", {"lens": lens, "id": vid, "bound": binding, "sample": sample}
        )
    if kind == "ready":
        _append(vdir / "samples.jsonl", severity_line(vdir, doc, vid, lens, binding))
    return doc["verdicts"][lens]


def severity_line(
    vdir: Path, doc: dict[str, Any], vid: str, lens: str, binding: str
) -> dict[str, Any]:
    """The severity log line of one Ready lens verdict (see Severity log)."""
    v = doc["verdicts"][lens]
    count = {s: sum(1 for f in v["findings"] if f["severity"] == s) for s in SEVERITIES}
    return {
        "kind": SEVERITY_KIND,
        "id": vid,
        "lens": lens,
        "bound": binding,
        "round": panel_round(vdir, doc)[0],
        "verdict": v["verdict"],
        "failure": v["failure"] is not None,
        "ran_at": v["ran_at"],
        "blocking": count["BLOCKING"],
        "warning": count["WARNING"],
        "note": count["NOTE"],
    }


def rounds(root: Path, key: str) -> list[dict[str, Any]]:
    """The story's Ready rounds from the severity log, oldest first: ``round``, ``bound`` and
    ``lenses`` (lens -> its last severity line on that blob)."""
    vid = f"ready-{key}"
    parse_id(vid)
    out: dict[tuple[int, str], dict[str, Any]] = {}
    for x in _log_lines(verdict_dir(root)):
        if x.get("kind") != SEVERITY_KIND or x.get("id") != vid:
            continue
        r, bound, lens = x.get("round"), x.get("bound"), x.get("lens")
        if not (isinstance(r, int) and isinstance(bound, str) and isinstance(lens, str)):
            continue
        row = out.setdefault((r, bound), {"round": r, "bound": bound, "lenses": {}})
        row["lenses"][lens] = x
    return [out[k] for k in sorted(out, key=lambda k: k[0])]


def rounds_lines(rows: list[dict[str, Any]]) -> list[str]:
    lines = []
    for row in rows:
        parts = []
        for lens, x in row["lenses"].items():
            n = f"B{x.get('blocking', 0)} W{x.get('warning', 0)} N{x.get('note', 0)}"
            parts.append(
                f"{lens} {x.get('verdict')} {n}" + (" failed" if x.get("failure") else "")
            )
        lines.append(f"round {row['round']} @ {row['bound'][:8]}: " + "; ".join(parts))
    return lines


def _sample_lines(vdir: Path) -> list[dict[str, Any]]:
    """The sample counter's lines: every line without ``kind`` (a severity line counts no
    sample and no derived round)."""
    return [x for x in _log_lines(vdir) if "kind" not in x]


def _log_lines(vdir: Path) -> list[dict[str, Any]]:
    try:
        text = (vdir / "samples.jsonl").read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise UnusableError(f"{vdir / 'samples.jsonl'}: {exc.strerror}") from exc
    lines = []
    for line in text.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            lines.append(obj)
    return lines


def _sample_slot(vdir: Path, lens: str, vid: str, binding: str, every: Any) -> bool | None:
    """Whether the next green verdict of this lens is a sample; None when this panel's lens
    was counted already (a rewrite after asking the agent once more counts once)."""
    greens = [x for x in _sample_lines(vdir) if x.get("lens") == lens and not x.get("read")]
    if any(x.get("id") == vid and x.get("bound") == binding for x in greens):
        return None
    return isinstance(every, int) and every > 0 and (len(greens) + 1) % every == 0


def _append(path: Path, obj: dict[str, Any]) -> None:
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise UnusableError(f"{path}: {exc.strerror}") from exc


def round_of(root: Path, vid: str) -> tuple[int, str | None]:
    """The panel's round and, when it was derived, its origin (see Derived round)."""
    return panel_round(verdict_dir(root), read_file(verdict_dir(root) / f"{vid}.json"))


def check(root: Path, vid: str) -> tuple[bool, list[str]]:
    """(green, lines): one line per lens, a stale line when the binding moved, the panel line."""
    green, lines, _carried = check_panel(root, vid)
    return green, lines


def _carry_after(root: Path) -> int | None:
    _path, crew = load_crew(root)
    rounds = (crew.get("ready_panel") or {}).get("warning_ok_after_rounds")
    return rounds if isinstance(rounds, int) and not isinstance(rounds, bool) else None


def check_panel(root: Path, vid: str) -> tuple[bool, list[str], list[dict[str, Any]]]:
    """``check`` plus the warnings a green Ready panel carries (``lens``, ``claim``, ``where``);
    the list is empty whenever the panel is red."""
    green, lines, carried, _from = _check(root, vid)
    return green, lines, carried


def check_t2(root: Path, vid: str) -> tuple[bool, list[str], str | None]:
    """``check`` plus the head a green T2 panel was carried from (see Carried panel), else None.
    The merge hook reads it to take the security card from that head too."""
    green, lines, _carried, carried_from = _check(root, vid)
    return green, lines, carried_from


def _check(root: Path, vid: str) -> tuple[bool, list[str], list[dict[str, Any]], str | None]:
    kind, subject = parse_id(vid)
    try:
        doc = read_file(verdict_dir(root) / f"{vid}.json")
    except RefusedError as exc:
        return False, [str(exc), f"panel {vid}: red"], [], None
    lines, green, carried = [], True, []
    carry_after: int | None = None
    round_, origin = panel_round(verdict_dir(root), doc)
    if origin is not None:
        lines.append(f"panel {vid}: round {round_} ({origin})")
    try:
        now = current_binding(root, kind, subject, doc.get("plan"))
    except RefusedError as exc:
        now, green = None, False
        lines.append(str(exc))
    stale_at, stale = len(lines), now is not None and now != doc["bound_to"]
    for lens in doc["expected"]:
        v = doc["verdicts"].get(lens)
        if v is None:
            green = False
            lines.append(f"lens {lens}: missing")
            continue
        standing = [
            f for f in v["findings"] if f["severity"] in COUNTING and f["status"] == "standing"
        ]
        only_warnings = (
            kind == "ready"
            and v["verdict"] == "red"
            and not v["failure"]
            and all(f["severity"] == "WARNING" for f in standing)
        )
        if only_warnings and carry_after is None:
            carry_after = _carry_after(root) or 0
        if only_warnings and carry_after and round_ >= carry_after:
            carried += [{"lens": lens, "claim": f["claim"], "where": f["where"]} for f in standing]
            why = ", ".join(f"WARNING {f['where'] or ''}".strip() for f in standing)
            lines.append(f"lens {lens}: green (warnings carried: {why})")
        elif v["verdict"] == "red":
            green = False
            why = v["failure"] or ", ".join(
                f"{f['severity']} {f['where'] or ''}".strip() for f in standing
            )
            lines.append(f"lens {lens}: red ({why})")
        else:
            notes = sum(1 for f in v["findings"] if f["severity"] == "NOTE")
            lines.append(f"lens {lens}: green" + (f" ({notes} note)" if notes else ""))
    carried_from = None
    if stale:
        rows, carried_from = _stale_rows(root, vid, doc["bound_to"], now, kind == "t2" and green)
        green = green and carried_from is not None
        lines[stale_at:stale_at] = rows
    if not green:
        carried = []
    state = "red" if not green else "green (warnings carried)" if carried else "green"
    lines.append(f"panel {vid}: {state}")
    return green, lines, carried, carried_from


# --- the carried T2 panel --------------------------------------------------------------------


def _stale_rows(
    root: Path, vid: str, bound: dict[str, str], now: dict[str, str], may_carry: bool
) -> tuple[list[str], str | None]:
    """The lines of a moved binding and the head a green T2 panel was carried from, else None."""
    was, is_ = next(iter(bound.values())), next(iter(now.values()))
    stale = f"panel {vid}: stale (bound to {was[:8]}, now {is_[:8]})"
    if not may_carry:
        return [stale], None
    carries, why = carry(root, was, is_)
    if carries:
        return [f"panel {vid}: carried from {was[:8]} to {is_[:8]} ({why})"], was
    return [stale, f"panel {vid}: not carried ({why})"], None


def carry(root: Path, old: str, new: str) -> tuple[bool, str]:  # noqa: PLR0911
    """(carries, why): whether a green T2 panel on head ``old`` holds for head ``new`` (see
    Carried panel). Any failure carries nothing."""
    r, git = str(root), risk_runner.plain_git
    if not risk_runner.fetch_rules(r, risk_runner.RULES_FROM, git):
        return False, f"{risk_runner.RULES_FROM} could not be fetched"
    if git(r, "cat-file", "-e", f"{new}^{{commit}}") is None:
        git(r, "fetch", "-q", "--no-tags", "origin", new, timeout=60)
    if git(r, "merge-base", "--is-ancestor", old, new) is None:
        return False, f"{old[:8]} is no ancestor of {new[:8]}"
    base = (git(r, "merge-base", risk_runner.RULES_FROM, new) or "").strip()
    delta = git(r, "diff", "--name-only", "--no-renames", old, new)
    if not base or delta is None:
        return False, f"no merge base or diff for {old[:8]}..{new[:8]}"
    lines, why = risk_runner.classify(r, new, base)
    if lines is None:
        return False, f"the PR's class is not computed: {why}"
    if lines[0] == "T0":
        return True, f"delta {old[:8]}..{new[:8]}: the PR is T0"
    hits = {row.split("\t", 1)[0] for row in lines[2:] if "\t" in row}
    if not hits:
        return False, f"the PR is {lines[0]} and names no file it hit"
    touched = sorted(hits & {f for f in delta.splitlines() if f.strip()})
    if touched:
        more = f" and {len(touched) - 3} more" if len(touched) > 3 else ""
        return False, f"delta {old[:8]}..{new[:8]} touches {', '.join(touched[:3])}{more}"
    return True, f"delta {old[:8]}..{new[:8]} touches no risk path, T0"


def samples(root: Path, keeper: str | None = None) -> list[dict[str, Any]]:
    vdir = verdict_dir(root)
    lines = _sample_lines(vdir)
    read = {(x.get("id"), x.get("lens"), x.get("bound")) for x in lines if x.get("read")}
    lenses = None
    if keeper is not None:
        _path, crew = load_crew(root)
        lenses = {k for k, v in crew["lenses"].items() if v.get("keeper") == keeper}
    out = []
    for x in lines:
        if not x.get("sample") or (x.get("id"), x.get("lens"), x.get("bound")) in read:
            continue
        if lenses is not None and x.get("lens") not in lenses:
            continue
        out.append({"id": x["id"], "lens": x["lens"], "bound": x.get("bound")})
    return out


def sampled(root: Path, vid: str, lens: str) -> None:
    parse_id(vid)
    vdir = verdict_dir(root)
    open_ = [x for x in samples(root) if x["id"] == vid and x["lens"] == lens]
    if not open_:
        raise RefusedError(f"sample {vid} {lens}: none open")
    for x in open_:
        _append(vdir / "samples.jsonl", {**x, "read": True})
    path = vdir / f"{vid}.json"
    if path.is_file():
        doc = read_file(path)
        verdict = doc["verdicts"].get(lens)
        if verdict is not None and verdict.get("sample"):
            verdict["sampled"] = True
            _write_atomic(path, doc)


# --- the panel comment ----------------------------------------------------------------------

PANEL_MARKER = "<!-- t2-panel -->"


def panel_comment(number: int, head: str, green: bool, lines: list[str]) -> str:
    """The comment body: the judge's three lines first, then the check lines (one line each)."""
    rows = [" ".join(line.split()) for line in lines]
    return (
        f"{PANEL_MARKER}\n"
        f"## T2 panel — #{number} @ `{head}`\n"
        f"**Overall: {'PASS' if green else 'FAIL'}**\n\n" + "".join(f"- {row}\n" for row in rows)
    )


def post(root: Path, vid: str) -> tuple[bool, list[str]]:
    """Post the T2 panel comment on the bound head; (posted PASS, the lines to print)."""
    kind, subject = parse_id(vid)
    if kind != "t2":
        raise UnusableError(f"post: {vid} is no T2 panel (t2-pr<N>)")
    doc = read_file(verdict_dir(root) / f"{vid}.json")
    bound = doc["bound_to"].get("head", "")
    now = current_binding(root, kind, subject)["head"]
    green, lines, carried_from = check_t2(root, vid)
    if now != bound and carried_from is None:
        raise RefusedError(
            f"post: panel {vid} is stale (bound to {bound[:8]}, now {now[:8]}); nothing posted"
        )
    gh = shutil.which("gh")
    if gh is None:
        raise RefusedError("post: gh not found; nothing posted")
    out = subprocess.run(
        [gh, "pr", "comment", subject, "--body-file", "-"],
        input=panel_comment(int(subject), now, green, lines),
        capture_output=True,
        text=True,
        check=False,
        cwd=str(root),
    )
    if out.returncode != 0:
        why = (out.stderr.strip().splitlines() or [f"exit {out.returncode}"])[-1]
        raise RefusedError(f"post: gh pr comment failed ({why}); nothing posted")
    word = "PASS" if green else "FAIL"
    return green, [f"posted: t2-panel {word} on #{subject} @ {now[:12]}"]


# --- CLI -------------------------------------------------------------------------------------


def _opt(argv: list[str], name: str) -> str | None:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
        raise UnusableError(f"{name} needs a value")
    return None


def _positional(argv: list[str], with_value: tuple[str, ...]) -> list[str]:
    out, skip = [], False
    for arg in argv:
        if skip:
            skip = False
        elif arg in with_value:
            skip = True
        else:
            out.append(arg)
    return out


def main(argv: list[str], stdin: Any = None) -> int:
    try:
        return _main(argv, stdin if stdin is not None else sys.stdin)
    except RefusedError as exc:
        print(f"lens_verdict: {exc}", file=sys.stderr)
        return 1
    except UnusableError as exc:
        print(f"lens_verdict: {exc}", file=sys.stderr)
        return 2


def _main(argv: list[str], stdin: Any) -> int:
    verb = argv[0] if argv else ""
    rest = argv[1:]
    if verb == "arm":
        command = " ".join(rest) if rest else stdin.read().strip()
        reason = arm_form(command) if command else "no command"
        print(f"arm: {'run' if reason is None else 'not run: ' + reason}")
        return 0 if reason is None else 1
    root = repo_root(Path.cwd())
    args = _positional(rest, ("--failed", "--keeper", "--plan"))
    unknown = [a for a in args if a.startswith("--")]
    if "--plan" in rest and not (verb == "plan" and args[:1] == ["ready"]):
        unknown = ["--plan (only for plan ready)"]
    if unknown:
        raise UnusableError(f"{verb or '(no verb)'}: unknown option {unknown[0]}\n{_usage()}")
    if verb == "plan" and len(args) == 2 and args[0] in ("ready", "t2"):
        print(json.dumps(plan(root, args[0], args[1], _opt(rest, "--plan")), indent=2))
        return 0
    if verb == "write" and len(args) == 2:
        failed = _opt(rest, "--failed")
        answer = None if failed is not None else stdin.read()
        result = write(root, args[0], args[1], answer=answer, failed=failed)
        print(f"lens {args[1]}: {result['verdict']}" + (" (sample)" if result["sample"] else ""))
        return 0
    if verb in ("check", "post") and len(args) == 1:
        green, lines = (check if verb == "check" else post)(root, args[0])
        print("\n".join(lines))
        return 0 if green else 1
    if (verb == "samples" and not args) or (verb == "rounds" and len(args) == 1):
        for line in _listing(root, verb, args, rest):
            print(line)
        return 0
    if verb == "sampled" and len(args) == 2:
        sampled(root, args[0], args[1])
        print(f"sample {args[0]} {args[1]}: read")
        return 0
    raise UnusableError(f"{verb or '(no verb)'}: wrong arguments\n{_usage()}")


def _listing(root: Path, verb: str, args: list[str], rest: list[str]) -> list[str]:
    """The read-only verbs' lines: ``samples`` and ``rounds``."""
    if verb == "samples":
        return [f"{x['id']}\t{x['lens']}" for x in samples(root, _opt(rest, "--keeper"))]
    rows = rounds(root, args[0])
    return rounds_lines(rows) if rows else [f"ready-{args[0]}: no logged rounds"]


def _usage() -> str:
    """The Usage block of the module docstring: the message of every usage error."""
    doc = __doc__ or ""
    return doc[doc.index("Usage:") : doc.index("\n\nID is")].rstrip()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
