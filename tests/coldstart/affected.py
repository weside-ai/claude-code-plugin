#!/usr/bin/env python3
"""Which cold-start scenarios a diff affects, and the digest of their inputs.

``affected(base)`` reads ``git diff --name-only --no-renames <base>...HEAD`` and maps each changed
path by ``MAPPING`` (one row per kind of input):

- a global input (the L0 under ``we/process/``, the SessionStart hooks that render it or the card,
  ``hooks.json``, ``render_process.py``, ``crew.py``, the harness files ``tests/coldstart/*.py``
  and ``schema.json``, whose ``run.py`` holds the model pin) or the crew fixture of any scenario:
  every scenario;
- ``we/roles/<r>.md``: the scenarios of role ``<r>``;
- a ``we/skills/<s>/SKILL.md`` whose frontmatter ``description`` changed: the routing scenarios
  (``routing: true``);
- a scenario file: that scenario.

``digest(ids)`` is the SHA-256 (first 16 hex digits) over the sorted ``<path> <blob id at HEAD>``
lines of every input of those scenarios: the global inputs and crew fixtures, the role cards of
their roles, their own files, and every ``SKILL.md`` when one of them routes; plus the model pin.
Blob ids instead of the commit SHA: a receipt survives a merge of the base that touches no input,
and still refuses one written for other inputs. Only top-level scenario keys are read, by regex,
so the receipt gate needs no PyYAML.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SUITE_DIR = "tests/coldstart"
MODEL_PIN = "claude-opus-5-5 medium"  # run.MODEL, run.EFFORT; a test keeps them equal

# (kind, pattern): the one table of what a changed path affects.
MAPPING = (
    ("global", re.compile(r"^we/process/")),
    (
        "global",
        re.compile(
            r"^we/hooks/(process_on_start|role_on_start|compact_on_start)\.py$"
            r"|^we/hooks/hooks\.json$"
        ),
    ),
    ("global", re.compile(r"^we/scripts/(render_process|crew)\.py$")),
    ("global", re.compile(r"^tests/coldstart/([^/]+\.py|schema\.json)$")),
    ("role", re.compile(r"^we/roles/([a-z_]+)\.md$")),
    ("routing", re.compile(r"^we/skills/[^/]+/SKILL\.md$")),
    ("scenario", re.compile(r"^tests/coldstart/[^/]+/[^/]+\.yaml$")),
)
TOP = re.compile(r"^([a-z_]+):[ \t]*(.*?)[ \t]*$", re.MULTILINE)


class GitError(Exception):
    """git failed; the message names the command."""


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def scenarios(root: Path = REPO) -> dict[str, dict]:
    """``{<dir>/<name>: {path, role, crew, routing}}`` of the working tree."""
    out = {}
    for path in sorted((root / SUITE_DIR).glob("*/*.yaml")):
        top = dict(TOP.findall(path.read_text(encoding="utf-8")))
        out[f"{path.parent.name}/{path.stem}"] = {
            "path": path.relative_to(root).as_posix(),
            "role": top.get("role", ""),
            "crew": top.get("crew", ""),
            "routing": top.get("routing") == "true",
        }
    return out


def _description(root: Path, rev: str, path: str) -> str | None:
    try:
        text = git(root, "show", f"{rev}:{path}")
    except GitError:
        return None
    if not text.startswith("---\n"):
        return ""
    head = text[4:].split("\n---\n", 1)[0]
    match = re.search(r"^description:(.*(?:\n[ \t]+.*)*)", head, re.MULTILINE)
    return " ".join(match.group(1).split()) if match else ""


def changed(base: str, root: Path = REPO) -> list[str]:
    return git(root, "diff", "--name-only", "--no-renames", f"{base}...HEAD").split()


def affected(base: str, root: Path = REPO) -> set[str]:
    """The ids of the scenarios the diff ``base...HEAD`` affects."""
    suite = scenarios(root)
    crews = {s["crew"] for s in suite.values()}
    merge_base = git(root, "merge-base", base, "HEAD").strip()
    out: set[str] = set()
    for path in changed(base, root):
        if path in crews:
            return set(suite)
        for kind, pattern in MAPPING:
            match = pattern.search(path)
            if not match:
                continue
            if kind == "global":
                return set(suite)
            if kind == "role":
                out |= {i for i, s in suite.items() if s["role"] == match.group(1)}
            elif kind == "routing":
                if _description(root, merge_base, path) != _description(root, "HEAD", path):
                    out |= {i for i, s in suite.items() if s["routing"]}
            elif kind == "scenario":
                sid = "/".join(Path(path).with_suffix("").parts[-2:])
                if sid in suite:
                    out.add(sid)
    return out


def inputs(ids: set[str], root: Path = REPO) -> list[str]:
    """The input paths of ``ids`` that exist at HEAD, sorted."""
    suite = scenarios(root)
    tracked = git(root, "ls-tree", "-r", "--name-only", "HEAD").split()
    picked = set()
    for path in tracked:
        for kind, pattern in MAPPING:
            if kind == "global" and pattern.search(path):
                picked.add(path)
    picked |= {s["crew"] for s in suite.values()}
    for sid in ids:
        if sid in suite:
            picked.add(suite[sid]["path"])
            picked.add(f"we/roles/{suite[sid]['role']}.md")
    if any(suite[i]["routing"] for i in ids if i in suite):
        picked |= {p for p in tracked if re.search(r"^we/skills/[^/]+/SKILL\.md$", p)}
    return sorted(p for p in picked if p in set(tracked))


def digest(ids: set[str], root: Path = REPO) -> str:
    paths = inputs(ids, root)
    blobs = {}
    for line in git(root, "ls-tree", "-r", "HEAD", "--", *paths).splitlines() if paths else []:
        meta, path = line.split("\t", 1)
        blobs[path] = meta.split()[2]
    h = hashlib.sha256()
    for path in paths:
        h.update(f"{path} {blobs[path]}\n".encode())
    h.update(f"model {MODEL_PIN}\n".encode())
    h.update(("ids " + " ".join(sorted(ids)) + "\n").encode())
    return h.hexdigest()[:16]


def dirty_inputs(root: Path = REPO) -> list[str]:
    """Changed or untracked suite inputs: the digest reads HEAD, a run on them would not match."""
    crews = {s["crew"] for s in scenarios(root).values()}
    lines = git(root, "status", "--porcelain", "--untracked-files=all").splitlines()
    paths = [line[3:] for line in lines]
    return [p for p in paths if p in crews or any(pat.search(p) for _, pat in MAPPING)]
