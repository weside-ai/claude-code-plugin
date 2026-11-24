#!/usr/bin/env python3
"""The one reader and writer of lens verdicts: a panel of fresh lens agents judging a plan
(Ready) or a PR diff (T2), recorded per subject and checked against today's plan subject or PR
head.

Usage:
  lens_verdict.py plan ready KEY [--plan PATH]   start a Ready panel on the story plan
                                                 docs/plans/KEY-story.md (or PATH, inside the
                                                 repo; the panel stays bound to it); prints one
                                                 dispatch entry per Ready lens as JSON
                                                 refused (exit 1) by the Ready gate, and while
                                                 a ``depends_on`` key has no story plan on
                                                 origin/main (the lenses would only say so); a
                                                 key with a repo prefix (``repo/KEY``) lives in
                                                 another repo: one warning, no refusal; refused
                                                 too on the same subject while the panel has
                                                 some but not every lens (no restart mid-round),
                                                 and above the round cap (see Round cap)
                                                 (``ready_panel.lenses_when_t2`` joins the
                                                 lenses when a plan file is on a risk path:
                                                 ``ready_lenses_for``, the hit as ``t2_hit``)
  lens_verdict.py plan t2 PR                     start a T2 panel on the PR's head (``gh``)
  lens_verdict.py arm [COMMAND]                  exit 0 when COMMAND (else stdin) is a red arm in
                                                 test form (the skill may run it), else 1 with why
  lens_verdict.py write ID LENS < ANSWER         record the lens agent's answer (its last JSON
                                                 object); exit 1 naming what is refused; the
                                                 write that completes the panel prints ``check``
                                                 after its line (the exit stays 0)
  lens_verdict.py write ID LENS --failed REASON  record the lens red without findings
  lens_verdict.py decide ID LENS --by ROLE TEXT  the lens holder's one-sentence decision on a
                                                 panel above the round cap (see Round cap)
  lens_verdict.py check ID                       one line per lens and the panel; exit 0 only green
                                                 (a Ready plan neither here nor on origin/main
                                                 is read on every branch and worktree holding
                                                 it; any differing state is stale, none is red:
                                                 ``binding_elsewhere``)
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

Schema, version 2, closed: an unknown key anywhere refuses the file or the answer, naming the key.
Every write is version 2; a version-1 file is read as before (see Subject). File: ``version``,
``kind`` (ready|t2), ``subject``, ``bound_to`` (ready: ``plan_blob``, the output of ``git
hash-object`` on the plan, and ``plan_subject``, its subject hash; t2: ``head``, the PR's head
SHA), ``capped_from`` (ready only, see Round cap: ``round`` and ``plan_blob`` of the round whose
verdicts the capped panel keeps), ``expected`` (the
lenses copied from the crew when the panel started, so a crew edit cannot shrink a running panel),
optional ``plan`` (ready only: the plan's path relative to the repo root when ``--plan`` named
one, so ``write`` and ``check`` re-hash that file), ``round`` (ready only: the panel's round, 1 for
the first plan version; ``plan ready`` on a new subject writes the stored round plus one, on the
same subject it keeps it, so a restart is no round; a file without ``round`` takes its round from
evidence, see Derived round), ``round_derived`` (ready only: where the round's base came from when
it was derived, e.g. ``base: round 2 derived: 2 plan blobs with logged lens verdicts: e82588a3,
e0d2159d``) and ``verdicts.<lens>``: ``verdict``
(green|red), ``agent``, ``ran_at``, ``sample``, ``sampled``, ``findings``, ``failure`` (why a
lens was recorded red without findings) and ``decision`` (ready only: ``by``, a role key,
``sentence``, ``subject``, the subject hash it was given on, ``at``). A finding:
``severity`` (BLOCKING|WARNING|NOTE), ``claim``, ``where``, ``question`` (the question-file line it
answers; required on Ready), ``red_arm`` (``command``, ``exit``, ``run``) and ``status``
(standing|refuted). An answer is ``{"findings": [...]}`` whose findings carry only ``severity``,
``claim``, ``where``, ``question`` and ``red_arm`` (``command``, plus ``exit`` once the skill ran
it); strings are capped at ``TEXT_CHARS`` with control characters stripped.

Green rule (Vyra 04.11.): a lens is red when a BLOCKING or WARNING finding stands, else green; a
NOTE is listed and never red; a ``refuted`` finding does not count. The panel is green only when
every expected lens has a verdict, every verdict is green, and the binding is today's plan subject
or PR head; a missing lens, a red lens and a stale binding each print a line and count red. The
verdict and the status are computed here from the findings, never taken from the caller, and
``check`` recomputes them from the stored findings.

Subject (Ready): a panel judges the plan without the sections ``## Updates Log``, ``## Documentation
Impact`` and ``## Code Guidance`` (a level-2 heading outside a code fence, up to the next one) and
the frontmatter keys ``status``, ``created`` and ``comments_read_through`` (with their indented
continuation lines); everything else counts, trailing whitespace dropped. Code Guidance is left
out on purpose: its DO/DON'T lines are the refiner's hints to the builder, while the ACs, phases,
fence and out of scope that a lens judges are what the build is accepted against. ``subject_hash`` is the
one normalisation (sha256 of ``subject_text``); ``plan``, ``write``, ``decide``, ``check`` and the
round compare it, never the blob, so a status flip or an updates-log line keeps the panel and a
changed AC makes it stale. A moved blob with the same subject prints ``panel <ID>: plan blob <a> ->
<b>, subject unchanged``. A binding without ``plan_subject`` (a version-1 file, or ``board.py
select``'s blob on main) takes the hash of its blob, read from the copy beside the verdict files
(``<we-lens>/plans/<blob>.md``), else from the object store; a blob in neither compares by blob.
So an open version-1 panel survives the upgrade without a new round when only excluded parts
changed.

Round cap (Ready only, crew ``ready_panel.max_rounds`` = M, default 2, null = off): ``plan ready``
whose next round lies above M starts no lens. In the measured runs a third round on the same plan
moved wording, not the verdict, so the holder's decision is the cheaper step. It rebinds the file to today's subject with every
verdict kept, writes the round and ``capped_from`` (the round and blob those verdicts were given
on, kept by every later capped round), prints the standing findings and the line ``round cap: the
lens holder decides`` (or, when every lens was green, ``round cap: changed after the last round;
one holder confirms``) and exits 1. ``decide ID LENS --by ROLE "<one sentence>"`` records the
holder's decision on that lens for today's subject hash: ``ROLE`` is a role key, the lens's own
when the lens key is one (a crew member's name stands for the one role it holds); refused within the cap, on a stale panel, on a lens without a verdict
(record it with ``write --failed``), and on a green lens while another is red. A decided lens
prints ``lens <lens>: green (decided by <role>: <sentence>)`` (``confirmed`` on a green one); a
lens green from the earlier round prints ``green (judged round N @ <blob>, round cap)``. A capped
panel is green only when at least one decision names today's subject hash; a decision never holds
for a later subject, so the next plan change makes the panel stale and, after ``plan ready``, red
until a holder decides again. ``decide`` appends ``kind: "decision"`` to ``samples.jsonl`` (``id``,
``lens``, ``bound``, ``subject``, ``round``, ``by``, ``sentence``, ``at``); ``rounds`` lists it,
and ``check_ready`` returns the decisions for the board's Selected row (``decided``).

Carried warnings (Ready only, crew ``ready_panel.warning_ok_after_rounds`` = N; an N above
``ready_panel.max_rounds`` never carries, since no lens runs there and the holder decides, see
Round cap): from round N on, a lens that is red only through standing WARNINGs (no BLOCKING, no ``failure``) prints ``lens
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
``merge-base(<rules ref>, new)..new`` by ``risk_runner`` (the one runner, rules and
rules ref); class ``T0`` carries, every other class (one-way too) only when the delta's files (``git diff --name-only old
new``) must miss every hit line's file, and so must the files the default branch changed between
the PR's bases (``merge-base(<rules ref>, old)..merge-base(<rules ref>, new)``): a merge that keeps
the branch's side of a hit file leaves it out of ``old..new`` while the PR's diff on it now undoes the
default branch's change. A class without hit lines carries nothing. A clean merge of the
default branch therefore carries when it moves no hit file; a delta on a risk path, a head outside the PR's history, a red
panel, no panel and any git or classifier failure do not. ``check`` prints ``panel <ID>: carried
from <old> to <new> (<why>)`` in place of the stale line, or the stale line plus ``panel <ID>: not
carried (<why>)``; ``check_t2`` returns the carried head. ``post`` posts a carried panel on the new head. The carry is
computed on every ``check``; nothing is written.

No skip, no override: no field can skip, confirm, waive or lift anything; ``skip``, ``override``,
``one_way``, ``go`` and every other unknown key are refused. A red panel turns green only through a
fresh panel on a new subject or head, or above the round cap through a holder's recorded
decision bound to the subject hash; a green T2 panel is carried only as above. Any session
can write this file, so it gates only the move to Selected; no merge reads it.

Panel comment (T2): ``post`` puts the panel's state on GitHub as the owner's input on a one-way PR,
in the form pinned by ``fixtures/brake-self-merge/judge.json``::

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
winning, plus the round's decision lines. Every other reader of the file (sample counter, ``samples``, the derived round) reads
only lines without ``kind``: a severity or decision line counts no sample and no round. The
derived round stays the count of 8.10.0's green lines on purpose: it rebuilds rounds of files
written before ``round`` existed, and a severity line is only ever written next to a file that
already stores its round.

Sample: every ``lenses.<k>.sample``-th green verdict of a lens is marked ``sample: true`` and listed
by ``samples`` until ``sampled`` marks it read; nobody waits on a sample. The verdict file is
written first (temp file plus ``os.replace``), the sample line after it: a crash between the two
loses one count, never a verdict.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ``python3 -I`` leaves this directory off sys.path (``-I`` implies ``-P``)
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import crew as crew_mod  # noqa: E402
import ready_gate  # noqa: E402
import risk_runner  # noqa: E402

VERSION = 2
READ_VERSIONS = (1, 2)
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
    "capped_from",
)
VERDICT_KEYS = (
    "verdict",
    "agent",
    "ran_at",
    "sample",
    "sampled",
    "findings",
    "failure",
    "decision",
)
DECISION_KEYS = ("by", "sentence", "subject", "at")
CAPPED_KEYS = ("round", "plan_blob")
DECISION_KIND = "decision"
CAP_LINE = "round cap: the lens holder decides"
CONFIRM_LINE = "round cap: changed after the last round; one holder confirms"
# what a Ready panel's subject leaves out (see Subject)
SUBJECT_SECTIONS = ("Updates Log", "Documentation Impact", "Code Guidance")
SUBJECT_KEYS = ("status", "created", "comments_read_through")
_HEX = re.compile(r"[0-9a-f]{40,64}")
FINDING_KEYS = ("severity", "claim", "where", "question", "red_arm", "status")
ANSWER_FINDING_KEYS = ("severity", "claim", "where", "question", "red_arm")
ARM_KEYS = ("command", "exit", "run")
ANSWER_ARM_KEYS = ("command", "exit")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class RefusedError(Exception):
    """Exit 1: a red answer or file, with the line to print."""


class PlanMissingError(RefusedError):
    """A Ready plan neither in this checkout nor on ``PLAN_FALLBACK_REF``."""


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


def _git_ok(root: Path, *args: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, check=False
        ).returncode
        == 0
    )


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


PLAN_FALLBACK_REF = "origin/main"


def _origin_blob(root: Path, rel: str) -> str | None:
    """The blob of ``rel`` on ``PLAN_FALLBACK_REF``, or None: a checkout behind main (the plan PR
    just merged) still binds the plan main carries."""
    out = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "-q", f"{PLAN_FALLBACK_REF}:{rel}"],
        capture_output=True,
        text=True,
        check=False,
    )
    blob = out.stdout.strip()
    return blob if out.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", blob) else None


def plan_source(root: Path, subject: str, rel: str | None, blob: str) -> tuple[Path, str]:
    """(the file a lens reads, the ref it came from): the plan in this checkout, else the bound
    blob written beside the verdict files (``<we-lens>/plans/<blob>.md``) from ``origin/main``."""
    path = plan_path(root, subject, rel)
    if path.is_file():
        return path, "worktree"
    copy = verdict_dir(root) / "plans" / f"{blob}.md"
    if not copy.is_file():
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text(_git(root, "cat-file", "blob", blob) + "\n", encoding="utf-8")
    return copy, PLAN_FALLBACK_REF


def subject_text(text: str) -> str:
    """The part of a plan a Ready panel judges (see Subject): the plan without the sections
    ``SUBJECT_SECTIONS`` and the frontmatter keys ``SUBJECT_KEYS``, trailing whitespace dropped."""
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    start = 0
    if lines and lines[0].strip() == "---":
        out.append(lines[0])
        start, dropping = 1, False
        while start < len(lines):
            line = lines[start]
            start += 1
            if line.strip() == "---":
                out.append(line)
                break
            if line[:1] not in (" ", "\t"):
                key, sep, _value = line.partition(":")
                dropping = bool(sep) and key.strip() in SUBJECT_KEYS
            if not dropping:
                out.append(line)
    fenced = dropping = False
    for line in lines[start:]:
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            dropping = line[3:].strip() in SUBJECT_SECTIONS
        if not dropping:
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def subject_hash(text: str) -> str:
    """The one normalisation of a Ready panel's subject: sha256 of ``subject_text``."""
    return hashlib.sha256(subject_text(text).encode("utf-8")).hexdigest()


def _blob_text(root: Path, blob: str) -> str | None:
    """A plan blob's text: the copy beside the verdict files (``<we-lens>/plans/<blob>.md``),
    else the object store; None when neither holds it."""
    try:
        copy = verdict_dir(root) / "plans" / f"{blob}.md"
        if copy.is_file():
            return copy.read_text(encoding="utf-8")
    except (OSError, UnusableError):
        pass
    out = subprocess.run(
        ["git", "-C", str(root), "cat-file", "blob", blob],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout if out.returncode == 0 else None


def bound_subject(root: Path, bound: dict[str, str]) -> str | None:
    """The subject hash of a Ready binding: stored (schema 2), else computed from the bound blob
    (a schema-1 file, or a caller that passes only the blob); None when the blob is unreadable."""
    if bound.get("plan_subject"):
        return bound["plan_subject"]
    blob = bound.get("plan_blob")
    text = _blob_text(root, blob) if blob else None
    return subject_hash(text) if text is not None else None


def same_subject(root: Path, kind: str, a: dict[str, str], b: dict[str, str]) -> bool:
    """Whether two bindings name the same subject: the subject hash on Ready (the blob when a
    hash cannot be computed), the head on T2."""
    if kind != "ready":
        return a == b
    sa, sb = bound_subject(root, a), bound_subject(root, b)
    if sa is None or sb is None:
        return a.get("plan_blob") == b.get("plan_blob")
    return sa == sb


def current_binding(
    root: Path, kind: str, subject: str, plan: str | None = None
) -> dict[str, str]:
    if kind == "ready":
        path = plan_path(root, subject, plan)
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            return {
                "plan_blob": _git(root, "hash-object", str(path)),
                "plan_subject": subject_hash(text),
            }
        blob = _origin_blob(root, path.relative_to(root).as_posix())
        text = _blob_text(root, blob) if blob else None
        if blob is None or text is None:
            raise PlanMissingError(
                f"plan {path.relative_to(root)}: missing (here and on {PLAN_FALLBACK_REF})"
            )
        return {"plan_blob": blob, "plan_subject": subject_hash(text)}
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


def _plan_states(root: Path, rel: str) -> list[tuple[str, str, str]]:
    """Every state of ``rel`` the repo holds outside this checkout, as (where, blob, text): the
    blob on each local and remote branch (two ``git`` calls for all refs), then the file in each
    other worktree of the repo, committed or not (``git worktree list --porcelain``)."""
    states: list[tuple[str, str, str]] = []
    refs = [
        ref
        for ref in subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "for-each-ref",
                "--format=%(refname)",
                "refs/heads",
                "refs/remotes",
            ],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.split()
        if not ref.endswith("/HEAD")
    ]
    if refs:
        out = subprocess.run(
            ["git", "-C", str(root), "cat-file", "--batch"],
            input="".join(f"{ref}:{rel}\n" for ref in refs).encode("utf-8"),
            capture_output=True,
            check=False,
        ).stdout
        pos = 0
        for ref in refs:
            end = out.find(b"\n", pos)
            if end < 0:
                break
            head = out[pos:end].split()
            pos = end + 1
            if len(head) != 3 or not head[2].isdigit():
                continue  # "<ref>:<rel> missing": this branch does not hold the plan
            size = int(head[2])
            body, pos = out[pos : pos + size], pos + size + 1
            if head[1] == b"blob":
                states.append((ref, head[0].decode(), body.decode("utf-8", errors="replace")))
    trees = [
        Path(line[len("worktree ") :])
        for line in subprocess.run(
            ["git", "-C", str(root), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.splitlines()
        if line.startswith("worktree ")
    ]
    files = [t / rel for t in trees if t.resolve() != root.resolve() and (t / rel).is_file()]
    if files:
        blobs = subprocess.run(
            ["git", "-C", str(root), "hash-object", "--stdin-paths"],
            input="".join(f"{f}\n" for f in files),
            capture_output=True,
            text=True,
            check=False,
        ).stdout.split()
        for path, blob in zip(files, blobs):
            states.append((f"worktree {path.parent}", blob, path.read_text(encoding="utf-8")))
    return states


def binding_elsewhere(
    root: Path, vid: str, subject: str, plan: str | None, bound: dict[str, str]
) -> tuple[dict[str, str] | None, str]:
    """A Ready check where the plan is neither in this checkout nor on ``origin/main`` (it lives
    only on its plan branch or in its worktree): (the binding, the line that says where it came
    from). Every state ``_plan_states`` finds counts: when any one's subject differs from the
    bound one, that state is the binding and the panel is stale; a newer commit date never hides
    an edit. (None, the refusal) when no branch and no worktree holds the plan: a stored blob alone
    is no current plan."""
    rel = plan_path(root, subject, plan).relative_to(root).as_posix()
    states = _plan_states(root, rel)
    if not states:
        return None, (
            f"plan {rel}: missing (here, on {PLAN_FALLBACK_REF}, on every branch and in every"
            " worktree)"
        )
    want = bound_subject(root, bound)
    found = [
        (where, {"plan_blob": blob, "plan_subject": subject_hash(text)})
        for where, blob, text in states
    ]
    where, now = next(((w, b) for w, b in found if b["plan_subject"] != want), found[0])
    more = f" (of {len(found)} states)" if len(found) > 1 else ""
    return (
        now,
        f"panel {vid}: plan not in this checkout nor on {PLAN_FALLBACK_REF}, read on {where}{more}",
    )


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
            None if _empty_arm(f.get("red_arm")) else f.get("red_arm"),
            f"{where}.red_arm",
            ARM_KEYS if stored else ANSWER_ARM_KEYS,
        ),
    }
    out["status"] = _status(out, where, kind, stored)
    return out


def _empty_arm(value: Any) -> bool:
    """`""`, `{}` or an arm with a blank command and no exit: no arm at all. A lens that writes
    one beside a NOTE or a Ready finding (which need none) is not refused for it; a T2 BLOCKING
    or WARNING still needs a real one."""
    if value in ("", {}):
        return True
    return (
        isinstance(value, dict)
        and set(value) <= {"command", "exit"}
        and not str(value.get("command") or "").strip()
        and value.get("exit") is None
    )


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
    if (
        doc.get("version") not in READ_VERSIONS
        or doc.get("kind") != kind
        or doc.get("subject") != subject
    ):
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
        doc.get("bound_to"),
        ("plan_blob", "plan_subject") if kind == "ready" else ("head",),
        "bound_to",
    )
    _subject_fields(path.stem, kind, bound, doc.get("capped_from"))
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
        if v.get("decision") is not None:
            clean[lens]["decision"] = _decision(v["decision"], f"verdicts.{lens}.decision", kind)
    return {**doc, "bound_to": dict(bound), "verdicts": clean}


def _subject_fields(stem: str, kind: str, bound: dict[str, Any], capped: Any) -> None:
    """``bound_to.plan_subject`` and ``capped_from`` of a stored panel; RefusedError otherwise."""
    if "plan_subject" in bound and not (
        isinstance(bound["plan_subject"], str) and _HEX.fullmatch(bound["plan_subject"])
    ):
        raise RefusedError(f"panel {stem}: bound_to.plan_subject needs a hex hash")
    if capped is None:
        return
    capped = _closed(capped, CAPPED_KEYS, "capped_from")
    if kind != "ready" or not (
        isinstance(capped.get("round"), int)
        and not isinstance(capped.get("round"), bool)
        and isinstance(capped.get("plan_blob"), str)
    ):
        raise RefusedError(f"panel {stem}: capped_from needs a round and a plan blob (ready only)")


def _decision(raw: Any, where: str, kind: str) -> dict[str, Any]:
    d = _closed(raw, DECISION_KEYS, where)
    if kind != "ready" or d.get("by") not in crew_mod.ROLE_KEYS:
        raise RefusedError(f"{where}: needs a role key in by (ready only)")
    if not (isinstance(d.get("subject"), str) and _HEX.fullmatch(d["subject"])):
        raise RefusedError(f"{where}.subject: needs a hex hash")
    return {
        "by": d["by"],
        "sentence": _text(d.get("sentence"), f"{where}.sentence", required=True),
        "subject": d["subject"],
        "at": _text(d.get("at"), f"{where}.at"),
    }


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
    t2 = None
    if kind == "ready":
        text = _blob_text(root, bound["plan_blob"])
        if text is None:
            text = plan_path(root, subject, rel).read_text(encoding="utf-8")
        chosen, t2 = ready_lenses_for(root, crew_path, crew, text)
        _no_restart_mid_round(root, path, vid, bound)
        _ready_gate_first(root, subject, rel, bound["plan_blob"])
        _depends_on_main(root, subject, rel, bound["plan_blob"])
        _round_cap(root, path, vid, bound, crew)
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
        doc["round"], origin = next_round(root, path, bound)
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
            source, ref = plan_source(root, subject, rel, bound["plan_blob"])
            entry["plan"] = str(source)
            entry["plan_blob"] = bound["plan_blob"]
            entry["ref"] = ref  # read the epic plan and every named file at this ref
        else:
            entry["pr"] = int(subject)
            entry["head"] = bound["head"]
        entries.append(entry)
    out: dict[str, Any] = {"id": vid, "kind": kind, "bound_to": bound, "entries": entries}
    if t2 is not None:
        out["t2_hit"] = {"path": t2[0], "rule": t2[1]}
    return out


def t2_hit(root: Path, crew: dict[str, Any], text: str) -> tuple[str, str] | None:
    """(path, glob) of the first file the plan names (every phase's ``**Files:**``, the short
    form's ``## Files``; another repo's paths left out) that lies on a ``path`` rule of
    ``.weside/risk-paths`` on ``risk.rules_from``, read like the Ready gate's short-form check;
    None when no file hits or the ref holds no rules file."""
    ref = str((crew.get("risk") or {}).get("rules_from") or PLAN_FALLBACK_REF)
    done = subprocess.run(
        ["git", "-C", str(root), "show", f"{ref}:{ready_gate.RISK_RULES}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        return None
    globs = ready_gate.risk_globs(done.stdout)
    named = [*ready_gate.phases(text), ready_gate.short_files(text)]
    for phase in named:
        for path, other in phase.paths:
            hit = None if other else next((g for g, rx in globs if rx.match(path)), None)
            if hit is not None:
                return path, hit
    return None


def ready_lenses_for(
    root: Path, crew_path: Path, crew: dict[str, Any], text: str
) -> tuple[list[dict[str, Any]], tuple[str, str] | None]:
    """The Ready panel's lenses: ``ready_lenses``, plus ``ready_panel.lenses_when_t2`` (in its
    order, each once) when ``t2_hit`` finds a plan file on a risk path; and that hit."""
    chosen = crew_mod.lenses(crew_path, crew, "ready")
    extra = (crew.get("ready_panel") or {}).get("lenses_when_t2") or []
    if not extra:
        return chosen, None
    hit = t2_hit(root, crew, text)
    if hit is None:
        return chosen, None
    have = {lens["lens"] for lens in chosen}
    every = {lens["lens"]: lens for lens in crew_mod.lenses(crew_path, crew)}
    for key in extra:
        if key not in have and key in every:
            chosen.append(every[key])
            have.add(key)
    return chosen, hit


def _no_restart_mid_round(root: Path, path: Path, vid: str, bound: dict[str, str]) -> None:
    """A Ready panel on the same subject with some but not every lens written is mid-round: a
    restart would drop those verdicts and run the lenses again on the same plan. RefusedError
    names the missing lenses. A panel above the round cap is left to ``_round_cap``."""
    try:
        old = read_file(path)
    except (RefusedError, UnusableError):
        return
    missing = [lens for lens in old["expected"] if lens not in old["verdicts"]]
    if (
        "capped_from" in old
        or not same_subject(root, "ready", old["bound_to"], bound)
        or not old["verdicts"]
        or not missing
    ):
        return
    round_, _origin = panel_round(path.parent, old)
    raise RefusedError(
        f"panel {vid}: round {round_} on this plan blob is open (missing: {', '.join(missing)}),"
        " no restart: dispatch the missing lenses, record a lens that died with"
        f" `lens_verdict.py write {vid} <lens> --failed <why>`, or edit the plan for a new round"
    )


def _ready_gate_first(root: Path, subject: str, rel: str | None, blob: str) -> None:
    """The Ready gate's checks (``ready_gate.story_failures``) before any lens runs: a plan the
    gate refuses would only send the lenses after the same gaps. RefusedError names them."""
    source, _ref = plan_source(root, subject, rel, blob)
    plan = plan_path(root, subject, rel)
    if source != plan:  # the gate finds the crew from the plan's own folder
        made = [d for d in reversed(plan.parents) if not d.exists()]
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            failures, _warnings = ready_gate.story_failures(plan)
        finally:
            plan.unlink()
            for d in reversed(made):  # the folders it made go too, deepest first, when still empty
                try:
                    d.rmdir()
                except OSError:
                    break
    else:
        failures, _warnings = ready_gate.story_failures(plan)
    if failures:
        lines = "\n".join(f"  {f}" for f in failures)
        raise RefusedError(
            f"plan {plan.relative_to(root)}: the Ready gate refuses it, no lens runs:\n{lines}"
        )


def _depends_on_main(root: Path, subject: str, rel: str | None, blob: str) -> None:
    """Each ``depends_on`` key's story plan on ``PLAN_FALLBACK_REF`` before any lens runs: a lens
    reads the plan it builds on there, and a missing one is a BLOCKING it can only repeat. A key
    with a repo prefix (``repo/KEY``) names a story in another repo whose plan this repo never
    holds: it is warned on stderr, not checked."""
    source, _ref = plan_source(root, subject, rel, blob)
    meta = ready_gate.frontmatter(source.read_text(encoding="utf-8"))
    keys = [k for k in ready_gate.inline_list(meta.get("depends_on")) if k != subject]
    external = [k for k in keys if "/" in k]
    if external:
        print(
            f"lens_verdict: depends_on {', '.join(external)} lives in another repo, not checked"
            " here: confirm it is built before the story is dispatched",
            file=sys.stderr,
        )
    missing = [
        key
        for key in keys
        if "/" not in key and _origin_blob(root, f"docs/plans/{key}-story.md") is None
    ]
    if missing:
        names = ", ".join(f"docs/plans/{k}-story.md" for k in missing)
        raise RefusedError(
            f"plan {plan_path(root, subject, rel).relative_to(root)}: depends_on {', '.join(missing)}"
            f" has no plan on {PLAN_FALLBACK_REF} ({names}), no lens runs: merge that plan first"
            " (a key from another repo carries its repo: `repo/KEY`)"
        )


def next_round(root: Path, path: Path, bound: dict[str, str]) -> tuple[int, str | None]:
    """The round of a Ready panel started on ``bound`` and, when its base was derived, where it
    came from: 1 without a readable earlier panel, the stored round on the same subject (a
    restart), the stored round plus one on a new subject."""
    try:
        old = read_file(path)
    except (RefusedError, UnusableError):
        return 1, None
    stored, origin = panel_round(path.parent, old)
    if origin is not None and "round" not in old:
        origin = f"base: round {stored} {origin}"
    same = same_subject(root, "ready", old["bound_to"], bound)
    return (stored if same else stored + 1), origin


def max_rounds(crew: dict[str, Any]) -> int | None:
    """``ready_panel.max_rounds``: the last round lenses run in; None turns the cap off."""
    cap = (crew.get("ready_panel") or {}).get("max_rounds")
    return cap if isinstance(cap, int) and not isinstance(cap, bool) else None


def _round_cap(
    root: Path, path: Path, vid: str, bound: dict[str, str], crew: dict[str, Any]
) -> None:
    """A Ready panel whose next round lies above ``ready_panel.max_rounds`` starts no lens (see
    Round cap): the file is rebound to today's subject with every verdict kept, and RefusedError
    prints the standing findings and the cap line."""
    cap = max_rounds(crew)
    if cap is None or not path.is_file():
        return
    with _locked(path):
        round_, origin = next_round(root, path, bound)
        if round_ <= cap:
            return
        old = read_file(path)
        old_round = panel_round(path.parent, old)[0]
        doc = {**old, "version": VERSION, "bound_to": bound, "round": round_}
        doc.setdefault(
            "capped_from", {"round": old_round, "plan_blob": old["bound_to"]["plan_blob"]}
        )
        if origin is not None:
            doc["round_derived"] = origin
        _write_atomic(path, doc)
    lines = [f"panel {vid}: round {round_} is above the round cap of {cap}, no lens runs"]
    red = False
    for lens in doc["expected"]:
        v = doc["verdicts"].get(lens)
        if v is None:
            red = True
            lines.append(
                f"  lens {lens}: missing (record it: lens_verdict.py write {vid} {lens} --failed"
                ' "<why>")'
            )
        elif v["verdict"] == "red":
            red = True
            lines.append(f"  lens {lens}: red" + (f" ({v['failure']})" if v["failure"] else ""))
            lines += [
                f"    {f['severity']} {f['where'] or '-'}: {f['claim']}"
                for f in v["findings"]
                if f["severity"] in COUNTING and f["status"] == "standing"
            ]
        else:
            capped = doc["capped_from"]
            lines.append(
                f"  lens {lens}: green (judged round {capped['round']} @"
                f" {capped['plan_blob'][:8]}, round cap)"
            )
    lines.append(CAP_LINE if red else CONFIRM_LINE)
    lines.append(f'  lens_verdict.py decide {vid} <lens> --by <role> "<one sentence>"')
    raise RefusedError("\n".join(lines))


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
    with _locked(path):
        return _write_locked(root, vid, lens, kind, subject, vdir, path, answer, failed, now)


def _write_locked(
    root: Path,
    vid: str,
    lens: str,
    kind: str,
    subject: str,
    vdir: Path,
    path: Path,
    answer: str | None,
    failed: str | None,
    now: str | None,
) -> dict[str, Any]:
    """`write`'s read-modify-write, run under the panel's lock (two lenses recorded at once)."""
    doc = read_file(path)
    if lens not in doc["expected"]:
        raise RefusedError(f"lens {lens}: not expected in panel {vid}")
    try:
        now_bound = current_binding(root, kind, subject, doc.get("plan"))
    except RefusedError:
        # the plan's worktree may be gone by the time a lens answers: the blob the panel is
        # bound to is still in the object store, and `check` re-hashes the plan anyway
        blob = doc["bound_to"].get("plan_blob")
        if kind != "ready" or not blob or _git_ok(root, "cat-file", "-e", blob) is False:
            raise
        now_bound = doc["bound_to"]
    if not same_subject(root, kind, now_bound, doc["bound_to"]):
        raise RefusedError(f"panel {vid}: stale (start a fresh panel with plan)")
    _upgrade(root, kind, doc)
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


def _upgrade(root: Path, kind: str, doc: dict[str, Any]) -> None:
    """Every write is schema 2: a Ready binding gains its subject hash, computed from the bound
    blob, when the blob is readable."""
    doc["version"] = VERSION
    if kind == "ready" and "plan_subject" not in doc["bound_to"]:
        found = bound_subject(root, doc["bound_to"])
        if found is not None:
            doc["bound_to"]["plan_subject"] = found


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


def _role_key(root: Path, by: str) -> str:
    """`by` as a role key: a member's slug or name (a companion's name included) becomes the role
    it holds in the crew (a session knows its name, not its key); anything else stays as given."""
    if by in crew_mod.ROLE_KEYS:
        return by
    try:
        _path, crew = crew_mod.find_and_load(root)
    except crew_mod.CrewError:
        return by
    found = crew_mod.member(crew or {}, by)
    held = [
        r for r, slug in ((crew or {}).get("roles") or {}).items() if found and slug == found[0]
    ]
    return held[0] if len(held) == 1 else by


def decide(
    root: Path, vid: str, lens: str, by: str, sentence: str, now: str | None = None
) -> dict[str, Any]:
    """Record the lens holder's decision on a panel above the round cap (see Round cap)."""
    kind, subject = parse_id(vid)
    if kind != "ready":
        raise UnusableError(f"decide: {vid} is no Ready panel (ready-<KEY>)")
    by = _role_key(root, by)
    if by not in crew_mod.ROLE_KEYS:
        raise RefusedError(f"decide: --by {by!r} is no role key ({', '.join(crew_mod.ROLE_KEYS)})")
    if lens in crew_mod.ROLE_KEYS and by != lens:
        raise RefusedError(f"decide: lens {lens} is held by the role {lens}, not {by}")
    text = _text(sentence, "decide: the sentence", required=True)
    vdir = verdict_dir(root)
    path = vdir / f"{vid}.json"
    with _locked(path):
        doc = read_file(path)
        if lens not in doc["expected"]:
            raise RefusedError(f"lens {lens}: not expected in panel {vid}")
        if "capped_from" not in doc:
            round_ = panel_round(vdir, doc)[0]
            raise RefusedError(
                f"decide: panel {vid} is in round {round_}, within the round cap: the lenses judge"
            )
        now_bound = current_binding(root, kind, subject, doc.get("plan"))
        if not same_subject(root, kind, now_bound, doc["bound_to"]):
            raise RefusedError(
                f"decide: panel {vid} is stale (the plan changed): run plan ready {subject} first"
            )
        v = doc["verdicts"].get(lens)
        if v is None:
            raise RefusedError(
                f"decide: lens {lens} has no verdict: record it first"
                f' (lens_verdict.py write {vid} {lens} --failed "<why>")'
            )
        red = [k for k in doc["expected"] if doc["verdicts"].get(k, {}).get("verdict") != "green"]
        if v["verdict"] == "green" and red:
            raise RefusedError(
                f"decide: lens {lens} is green; the red lenses decide: {', '.join(red)}"
            )
        _upgrade(root, kind, doc)
        doc["bound_to"] = now_bound
        subject_now = now_bound["plan_subject"]
        at = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        v["decision"] = {"by": by, "sentence": text, "subject": subject_now, "at": at}
        _write_atomic(path, doc)
        _append(
            vdir / "samples.jsonl",
            {
                "kind": DECISION_KIND,
                "id": vid,
                "lens": lens,
                "bound": now_bound["plan_blob"],
                "subject": subject_now,
                "round": panel_round(vdir, doc)[0],
                "by": by,
                "sentence": text,
                "at": at,
            },
        )
    return v["decision"]


def rounds(root: Path, key: str) -> list[dict[str, Any]]:
    """The story's Ready rounds from the severity log, oldest first: ``round``, ``bound``,
    ``lenses`` (lens -> its last severity line on that blob) and ``decided`` (lens -> its last
    decision line in that round)."""
    vid = f"ready-{key}"
    parse_id(vid)
    out: dict[tuple[int, str], dict[str, Any]] = {}
    for x in _log_lines(verdict_dir(root)):
        if x.get("kind") not in (SEVERITY_KIND, DECISION_KIND) or x.get("id") != vid:
            continue
        r, bound, lens = x.get("round"), x.get("bound"), x.get("lens")
        if not (isinstance(r, int) and isinstance(bound, str) and isinstance(lens, str)):
            continue
        row = out.setdefault((r, bound), {"round": r, "bound": bound, "lenses": {}, "decided": {}})
        row["lenses" if x["kind"] == SEVERITY_KIND else "decided"][lens] = x
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
        for lens, x in row["decided"].items():
            parts.append(f"{lens} decided by {x.get('by')}: {x.get('sentence')}")
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


LOCK_WAIT_S = 10.0


@contextlib.contextmanager
def _locked(path: Path):
    """An exclusive flock on `<verdict file>.lock`, waiting at most `LOCK_WAIT_S`."""
    try:
        fd = os.open(str(path.with_name(path.name + ".lock")), os.O_RDWR | os.O_CREAT, 0o644)
    except OSError as exc:
        raise UnusableError(f"{path}.lock: {exc.strerror}") from exc
    try:
        deadline = time.monotonic() + LOCK_WAIT_S
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise UnusableError(
                        f"{path}.lock: held longer than {LOCK_WAIT_S:g} s"
                    ) from None
                time.sleep(0.05)
        yield
    finally:
        os.close(fd)


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


def check_panel(
    root: Path, vid: str, binding: dict[str, str] | None = None
) -> tuple[bool, list[str], list[dict[str, Any]]]:
    """``check`` plus the warnings a green Ready panel carries (``lens``, ``claim``, ``where``);
    the list is empty whenever the panel is red. ``binding`` replaces today's binding read from
    the checkout (``board.py select`` passes the plan blob on main; the subject hash is computed
    from it)."""
    green, lines, carried, _decided = check_ready(root, vid, binding)
    return green, lines, carried


def check_ready(
    root: Path, vid: str, binding: dict[str, str] | None = None
) -> tuple[bool, list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """``check_panel`` plus the holders' decisions a green panel stands on (``lens``, ``by``,
    ``sentence``; see Round cap), empty whenever the panel is red."""
    green, lines, carried, _from, decided = _check(root, vid, binding=binding)
    return green, lines, carried, decided


def check_t2(
    root: Path, vid: str, git: risk_runner.Git | None = None, timeout: float | None = None
) -> tuple[bool, list[str], str | None]:
    """``check`` plus the head a green T2 panel was carried from (see Carried panel), else None.
    ``git`` and ``timeout`` are the caller's, so a caller can keep the carry inside a time budget."""
    green, lines, _carried, carried_from, _decided = _check(root, vid, git, timeout)
    return green, lines, carried_from


def _check(  # noqa: PLR0912, PLR0915
    root: Path,
    vid: str,
    git: risk_runner.Git | None = None,
    timeout: float | None = None,
    binding: dict[str, str] | None = None,
) -> tuple[bool, list[str], list[dict[str, Any]], str | None, list[dict[str, Any]]]:
    kind, subject = parse_id(vid)
    try:
        doc = read_file(verdict_dir(root) / f"{vid}.json")
    except RefusedError as exc:
        return False, [str(exc), f"panel {vid}: red"], [], None, []
    lines, green, carried, decided = [], True, [], []
    carry_after: int | None = None
    round_, origin = panel_round(verdict_dir(root), doc)
    if origin is not None:
        lines.append(f"panel {vid}: round {round_} ({origin})")
    try:
        now = binding or current_binding(root, kind, subject, doc.get("plan"))
    except RefusedError as exc:
        now, where = None, str(exc)
        if isinstance(exc, PlanMissingError):
            now, where = binding_elsewhere(root, vid, subject, doc.get("plan"), doc["bound_to"])
        green = green and now is not None
        lines.append(where)
    stale_at = len(lines)
    stale = now is not None and not same_subject(root, kind, now, doc["bound_to"])
    now_subject = bound_subject(root, now) if kind == "ready" and now is not None else None
    if kind == "ready" and now is not None and not stale and now != doc["bound_to"]:
        was, is_ = doc["bound_to"]["plan_blob"], now["plan_blob"]
        if was != is_:
            lines.append(f"panel {vid}: plan blob {was[:8]} -> {is_[:8]}, subject unchanged")
    capped = doc.get("capped_from")
    red_lenses = []
    for lens in doc["expected"]:
        v = doc["verdicts"].get(lens)
        if v is None:
            green = False
            red_lenses.append(lens)
            lines.append(f"lens {lens}: missing")
            continue
        decision = v.get("decision")
        if decision is not None and (now_subject is None or decision["subject"] != now_subject):
            decision = None  # a decision holds for the subject it was given on, never later
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
        if decision is not None:
            decided.append({"lens": lens, "by": decision["by"], "sentence": decision["sentence"]})
            word = "decided" if v["verdict"] == "red" else "confirmed"
            lines.append(
                f"lens {lens}: green ({word} by {decision['by']}: {decision['sentence']})"
            )
        elif only_warnings and carry_after and round_ >= carry_after:
            carried += [{"lens": lens, "claim": f["claim"], "where": f["where"]} for f in standing]
            why = ", ".join(f"WARNING {f['where'] or ''}".strip() for f in standing)
            lines.append(f"lens {lens}: green (warnings carried: {why})")
        elif v["verdict"] == "red":
            green = False
            red_lenses.append(lens)
            why = v["failure"] or ", ".join(
                f"{f['severity']} {f['where'] or ''}".strip() for f in standing
            )
            lines.append(f"lens {lens}: red ({why})")
        else:
            notes = sum(1 for f in v["findings"] if f["severity"] == "NOTE")
            extra = [f"{notes} note"] if notes else []
            if capped is not None:
                extra.append(
                    f"judged round {capped['round']} @ {capped['plan_blob'][:8]}, round cap"
                )
            lines.append(f"lens {lens}: green" + (f" ({'; '.join(extra)})" if extra else ""))
    if capped is not None and not stale and not decided:
        green = False  # a capped subject stands on at least one holder's decision for it
        lines.append(f"panel {vid}: {CAP_LINE if red_lenses else CONFIRM_LINE}")
    carried_from = None
    if stale:
        rows, carried_from = _stale_rows(
            root, vid, doc["bound_to"], now, kind == "t2" and green, git, timeout
        )
        green = green and carried_from is not None
        lines[stale_at:stale_at] = rows
    if not green:
        carried, decided = [], []
    marks = [m for m, on in (("warnings carried", carried), ("decided", decided)) if on]
    state = "red" if not green else "green" + (f" ({', '.join(marks)})" if marks else "")
    lines.append(f"panel {vid}: {state}")
    return green, lines, carried, carried_from, decided


# --- the carried T2 panel --------------------------------------------------------------------


def _stale_rows(
    root: Path,
    vid: str,
    bound: dict[str, str],
    now: dict[str, str],
    may_carry: bool,
    git: risk_runner.Git | None = None,
    timeout: float | None = None,
) -> tuple[list[str], str | None]:
    """The lines of a moved binding and the head a green T2 panel was carried from, else None."""
    was, is_ = next(iter(bound.values())), next(iter(now.values()))
    stale = f"panel {vid}: stale (bound to {was[:8]}, now {is_[:8]})"
    if not may_carry:
        return [stale], None
    carries, why = carry(
        root,
        was,
        is_,
        git or risk_runner.plain_git,
        risk_runner.CLASSIFY_TIMEOUT if timeout is None else timeout,
    )
    if carries:
        return [f"panel {vid}: carried from {was[:8]} to {is_[:8]} ({why})"], was
    return [stale, f"panel {vid}: not carried ({why})"], None


def carry(  # noqa: PLR0911
    root: Path,
    old: str,
    new: str,
    git: risk_runner.Git = risk_runner.plain_git,
    timeout: float = risk_runner.CLASSIFY_TIMEOUT,
) -> tuple[bool, str]:
    """(carries, why): whether a green T2 panel on head ``old`` holds for head ``new`` (see
    Carried panel). Any failure carries nothing. ``git`` and ``timeout`` are the caller's."""
    r = str(root)
    found = risk_runner.rules(r, git)
    if isinstance(found, str):
        return False, f"the rules are not readable: {found}"
    if git(r, "cat-file", "-e", f"{new}^{{commit}}") is None:
        git(r, "fetch", "-q", "--no-tags", "origin", new, timeout=60)
    if git(r, "merge-base", "--is-ancestor", old, new) is None:
        return False, f"{old[:8]} is no ancestor of {new[:8]}"
    if found is None:
        return True, f"delta {old[:8]}..{new[:8]}: no risk rules here, T0"
    rules_from = found[2]
    if rules_from != risk_runner.RULES_FROM and not risk_runner.fetch_rules(r, rules_from, git):
        return False, f"{rules_from} could not be fetched"
    base = (git(r, "merge-base", rules_from, new) or "").strip()
    delta = git(r, "diff", "--name-only", "--no-renames", old, new)
    if not base or delta is None:
        return False, f"no merge base or diff for {old[:8]}..{new[:8]}"
    lines, why = risk_runner.run(r, git, found, new, base, timeout)
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
    # a merge that keeps the branch's side of a hit file leaves it out of old..new, yet the PR's
    # diff on it now undoes main's change: a hit file main changed between the bases carries nothing
    old_base = (git(r, "merge-base", rules_from, old) or "").strip()
    moved = git(r, "diff", "--name-only", "--no-renames", old_base, base) if old_base else None
    if moved is None:
        return False, f"no merge base or diff for {old[:8]}"
    under = sorted(hits & {f for f in moved.splitlines() if f.strip()})
    if under:
        more = f" and {len(under) - 3} more" if len(under) > 3 else ""
        return False, (
            f"main changed {', '.join(under[:3])}{more} between the PR's bases "
            f"{old_base[:8]}..{base[:8]}"
        )
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
        with _locked(path):
            doc = read_file(path)
            verdict = doc["verdicts"].get(lens)
            if verdict is not None and verdict.get("sample"):
                verdict["sampled"] = True
                _upgrade(root, doc["kind"], doc)
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
    args = _positional(rest, ("--failed", "--keeper", "--plan", "--by"))
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
        doc = read_file(verdict_dir(root) / f"{args[0]}.json")
        if all(lens in doc["verdicts"] for lens in doc["expected"]):
            print("\n".join(check(root, args[0])[1]))
        return 0
    if verb in ("check", "post", "decide") and len(args) == (3 if verb == "decide" else 1):
        green, lines = _verdict_verb(root, verb, args, rest)
        print("\n".join(lines))
        return 0 if green or verb == "decide" else 1
    if (verb == "samples" and not args) or (verb == "rounds" and len(args) == 1):
        for line in _listing(root, verb, args, rest):
            print(line)
        return 0
    if verb == "sampled" and len(args) == 2:
        sampled(root, args[0], args[1])
        print(f"sample {args[0]} {args[1]}: read")
        return 0
    raise UnusableError(f"{verb or '(no verb)'}: wrong arguments\n{_usage()}")


def _verdict_verb(
    root: Path, verb: str, args: list[str], rest: list[str]
) -> tuple[bool, list[str]]:
    """``check``, ``post`` and ``decide`` (which prints its line and the ``check`` after it)."""
    if verb != "decide":
        return (check if verb == "check" else post)(root, args[0])
    by = _opt(rest, "--by")
    if not by:
        raise UnusableError(f"decide: --by ROLE is required\n{_usage()}")
    d = decide(root, args[0], args[1], by, args[2])
    green, lines = check(root, args[0])
    return green, [f"lens {args[1]}: decided by {d['by']} for subject {d['subject'][:12]}", *lines]


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
