#!/usr/bin/env python3
"""The one reader and writer of lens verdicts: a panel of fresh lens agents judging a plan
(Ready) or a PR diff (T2), recorded per subject and checked against today's plan blob or PR head.

Usage:
  lens_verdict.py plan ready KEY                 start a Ready panel on the story plan
                                                 docs/plans/KEY-story.md; prints one dispatch
                                                 entry per Ready lens as JSON
  lens_verdict.py plan t2 PR                     start a T2 panel on the PR's head (``gh``)
  lens_verdict.py arm [COMMAND]                  exit 0 when COMMAND (else stdin) is a red arm in
                                                 test form (the skill may run it), else 1 with why
  lens_verdict.py write ID LENS < ANSWER         record the lens agent's answer (its last JSON
                                                 object); exit 1 naming what is refused
  lens_verdict.py write ID LENS --failed REASON  record the lens red without findings
  lens_verdict.py check ID                       one line per lens and the panel; exit 0 only green
  lens_verdict.py samples [--keeper SLUG]        the sampled green verdicts nobody has read
  lens_verdict.py sampled ID LENS                mark a sample read

ID is ``ready-<KEY>`` or ``t2-pr<N>``. Exit 2: a usage error, the verdict directory unusable, or
the crew file unusable.

Where: one JSON file per subject in ``<git common dir>/we-lens/`` (shared by every worktree of the
repo, never in the tree, so a PR cannot carry its own verdict), plus ``samples.jsonl`` there.

Schema, version 1, closed: an unknown key anywhere refuses the file or the answer, naming the key.
File: ``version``, ``kind`` (ready|t2), ``subject``, ``bound_to`` (``plan_blob`` for ready, the
output of ``git hash-object`` on the plan; ``head`` for t2, the PR's head SHA), ``expected`` (the
lenses copied from the crew when the panel started, so a crew edit cannot shrink a running panel)
and ``verdicts.<lens>``: ``verdict`` (green|red), ``agent``, ``ran_at``, ``sample``, ``sampled``,
``findings``, and ``failure`` (why a lens was recorded red without findings). A finding:
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

Red arm (T2): a BLOCKING or WARNING finding needs ``red_arm.command`` and ``red_arm.exit``, or the
answer is refused naming the finding. The skill runs the arm (never this script: lens output is
foreign text) only when ``arm`` accepts its form; ``exit`` 0 means the finding is ``refuted``; a
non-zero exit means ``standing``; 124 (``timeout``), 126, 127 or above 128 (a signal) mean the arm
proved nothing and the answer is refused as a finding without red arm (Kiska 04.11.). A command not
in test form is never run: the finding stays ``standing`` with ``run: false``, whatever exit the
caller recorded.

No skip, no override: no field can skip, confirm, waive or lift anything; ``skip``, ``override``,
``one_way``, ``go`` and every other unknown key are refused. A red panel turns green only through a
fresh panel on a new plan blob or head. Any session can write this file, so it gates only a two-way
T2 merge and the move to Selected; the one-way brake never reads it.

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

VERSION = 1
TEXT_CHARS = 500
SEVERITIES = ("BLOCKING", "WARNING", "NOTE")
COUNTING = ("BLOCKING", "WARNING")
NO_PROOF_EXITS = (124, 126, 127)
ARM_FORMS = ("pytest ", "python3 -m pytest ", "bash scripts/", "python3 scripts/")
ARM_FORBIDDEN = (";", "|", "&", "$(", "`", ">", "<", "\n", "\r")
ID_RE = re.compile(r"\A(?:ready-(?P<key>[A-Za-z][A-Za-z0-9_]*-\d+)|t2-pr(?P<pr>\d+))\Z")
FILE_KEYS = ("version", "kind", "subject", "bound_to", "expected", "verdicts")
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


def plan_path(root: Path, key: str) -> Path:
    return root / "docs" / "plans" / f"{key}-story.md"


def current_binding(root: Path, kind: str, subject: str) -> dict[str, str]:
    if kind == "ready":
        path = plan_path(root, subject)
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
        return root / ".weside" / "crew.json", crew_mod._merge({})
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
    bound = _closed(
        doc.get("bound_to"), ("plan_blob",) if kind == "ready" else ("head",), "bound_to"
    )
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


def plan(root: Path, kind: str, subject: str) -> dict[str, Any]:
    """Start a panel: write the empty verdict file bound to today's subject, return the entries."""
    vid = f"ready-{subject}" if kind == "ready" else f"t2-pr{subject}"
    parse_id(vid)
    crew_path, crew = load_crew(root)
    try:
        chosen = crew_mod.lenses(crew_path, crew, kind)
    except crew_mod.CrewError as exc:
        raise UnusableError(f"crew: {exc}") from exc
    bound = current_binding(root, kind, subject)
    doc = {
        "version": VERSION,
        "kind": kind,
        "subject": subject,
        "bound_to": bound,
        "expected": [lens["lens"] for lens in chosen],
        "verdicts": {},
    }
    _write_atomic(verdict_dir(root) / f"{vid}.json", doc)
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
            entry["plan"] = str(plan_path(root, subject))
            entry["plan_blob"] = bound["plan_blob"]
        else:
            entry["pr"] = int(subject)
            entry["head"] = bound["head"]
        entries.append(entry)
    return {"id": vid, "kind": kind, "bound_to": bound, "entries": entries}


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
    if current_binding(root, kind, subject) != doc["bound_to"]:
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
    return doc["verdicts"][lens]


def _sample_lines(vdir: Path) -> list[dict[str, Any]]:
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


def check(root: Path, vid: str) -> tuple[bool, list[str]]:
    """(green, lines): one line per lens, a stale line when the binding moved, the panel line."""
    kind, subject = parse_id(vid)
    try:
        doc = read_file(verdict_dir(root) / f"{vid}.json")
    except RefusedError as exc:
        return False, [str(exc), f"panel {vid}: red"]
    lines, green = [], True
    try:
        now = current_binding(root, kind, subject)
    except RefusedError as exc:
        now, green = None, False
        lines.append(str(exc))
    if now is not None and now != doc["bound_to"]:
        green = False
        was, is_ = next(iter(doc["bound_to"].values())), next(iter(now.values()))
        lines.append(f"panel {vid}: stale (bound to {was[:8]}, now {is_[:8]})")
    for lens in doc["expected"]:
        v = doc["verdicts"].get(lens)
        if v is None:
            green = False
            lines.append(f"lens {lens}: missing")
            continue
        standing = [
            f for f in v["findings"] if f["severity"] in COUNTING and f["status"] == "standing"
        ]
        if v["verdict"] == "red":
            green = False
            why = v["failure"] or ", ".join(
                f"{f['severity']} {f['where'] or ''}".strip() for f in standing
            )
            lines.append(f"lens {lens}: red ({why})")
        else:
            notes = sum(1 for f in v["findings"] if f["severity"] == "NOTE")
            lines.append(f"lens {lens}: green" + (f" ({notes} note)" if notes else ""))
    lines.append(f"panel {vid}: {'green' if green else 'red'}")
    return green, lines


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
    args = _positional(rest, ("--failed", "--keeper"))
    if verb == "plan" and len(args) == 2 and args[0] in ("ready", "t2"):
        print(json.dumps(plan(root, args[0], args[1]), indent=2))
        return 0
    if verb == "write" and len(args) == 2:
        failed = _opt(rest, "--failed")
        answer = None if failed is not None else stdin.read()
        result = write(root, args[0], args[1], answer=answer, failed=failed)
        print(f"lens {args[1]}: {result['verdict']}" + (" (sample)" if result["sample"] else ""))
        return 0
    if verb == "check" and len(args) == 1:
        green, lines = check(root, args[0])
        print("\n".join(lines))
        return 0 if green else 1
    if verb == "samples" and not args:
        for x in samples(root, _opt(rest, "--keeper")):
            print(f"{x['id']}\t{x['lens']}")
        return 0
    if verb == "sampled" and len(args) == 2:
        sampled(root, args[0], args[1])
        print(f"sample {args[0]} {args[1]}: read")
        return 0
    raise UnusableError(__doc__.strip().splitlines()[2].strip())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
