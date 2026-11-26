#!/usr/bin/env python3
"""What a cold start loads, per role of the crew: a report for the hr role, no gate (exit 0).

Usage: context_load.py [--from DIR] [--role R ...] [--home DIR] [--md]

Per session of each role (default: every role of ``render_process.all_roles``) one table: part,
source, characters, estimated tokens (characters ÷ 4) and the delta to the last report. Then the
line ``measured start`` (the tokens of the transcript's first request: input, cache creation and
cache read of its first assistant entry's usage; ``n/a`` without one), the line ``counted vs real``
(what ``check-instruction-budget.py --role-totals`` counts against the measured start, else against
what the table sums), the five largest single files and the duplicate sentences.

Sources:
  disk        the counted parts, from ``render_process.total_rows`` (the gate's own counter): L0,
              plugin hook, card, addendum, extra repos, role skill, every instruction file of the
              chain, the rules without ``paths:``; plus ``MEMORY.md``, the repo's auto-memory index
              (``<config dir>/projects/<repo>/memory/``, the main worktree's slug), counted as
              Claude Code loads it: the first 200 lines, at most 25,000 characters. Its content is
              never shown; only its size. A ``worker`` starts with ``autoMemoryEnabled: false``
              (``worker_launch.write_settings``): its row shows 0 with the source ``off (worker
              settings)``.
  transcript  the newest transcript of a session of that role under ``<config dir>/projects/``
              (the workplace's directory and its worktrees') whose first ``api-request-shape``
              line comes before any assistant entry (a cold start), everything before it: system prompt and tool schemas (that shape), skill
              listing, agent listing, deferred tool names, MCP instructions (the attachments).
              Only sizes leave the file. No transcript: ``n/a (no transcript)``. The tool starts
              no session.
A session's role in a transcript: its title is the holder's name (a named role); else the
SessionStart context carries the worker's short form (``worker``) or the L0 (``master``).

Duplicate sentences: sentences of ``MIN_SENTENCE`` characters or more that stand verbatim in two
loaded files, with both places; never from a memory file. The quote is at most ``QUOTE`` characters
and only when both files lie in the repo or the plugin; otherwise the line names the places alone.

The repo is the one that declares the crew (``crew.declaring_root``): a repo whose
``.weside/config.json`` points at another repo's crew file measures itself, its master and worker
with its own instruction chain, rules, auto-memory and transcripts; a named member working
elsewhere is one line ``<label>: works in <repo>, measured there``.

``--md`` writes ``reports/context-<UTC date>.md`` under ``.weside/optimization/`` of the repo
(``references/optimization-store.md`` § Layout); the report's last line carries its numbers for the
next run's delta. No store: one line on stderr, nothing written.

The disk rows are what would load; the ``measured start`` line is what did (the footer says so).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, NamedTuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import claude_home  # noqa: E402
import crew as crewlib  # noqa: E402
import render_process  # noqa: E402

PLUGIN = HERE.parent
MEMORY_LINES = 200
MEMORY_CHARS = 25_000
MIN_SENTENCE = 60
QUOTE = 80
TOP = 5
HEAD_LINES = 2_000  # a transcript's first request lies within its first lines
SCAN_FILES = 5_000  # transcripts looked at per workplace, newest first
WORKER_MARK = "You are a worker:"  # the first line of process/L0-worker.md
L0_MARK = "The crew process (L0)"  # the heading of process/L0.md
CARD_MARK = re.compile(r"\A\s*# Role card: ([a-z][a-z-]*)")  # the first line of roles/<role>.md
DATA = "<!-- context-load "
NA = "n/a (no transcript)"
MEMORY_OFF = "off (worker settings)"
FOOTER = "disk rows: what would load · measured start: what did"
MEASURED = (
    "measured start"  # the first assistant entry's usage: input + cache creation + cache read
)
TRANSCRIPT_PARTS = (
    "system prompt",
    "tool schemas",
    "skill listing",
    "agent listing",
    "deferred tool names",
    "MCP instructions",
)
COUNTED = ("L0", "plugin-hook", "card", "addendum", "extra-head", "extra-hooks", "role-skill")


class Row(NamedTuple):
    part: str
    source: str  # disk · transcript
    chars: int | None  # None: not measured
    path: str = ""  # a file, for the largest-files list and the duplicates
    counted: bool = False  # in the budget gate's total


class Session(NamedTuple):
    label: str
    rows: list[Row]
    counted: int
    texts: list[tuple[str, str, bool]]  # (place, text, quotable)
    transcript: str  # the transcript's file name, or NA
    measured: int | None = None  # tokens of the first request, from the transcript
    elsewhere: str = ""  # the workplace's name when the member works in another repo


# --- disk ----------------------------------------------------------------------------------


def tokens(chars: int) -> int:
    return round(chars / 4)


def project_slug(path: Path) -> str:
    """Claude Code's directory name for a working directory under ``projects/``."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def main_worktree(path: Path) -> Path:
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return path
    common = Path(out)
    return common.parent if common.name == ".git" else path


def memory_chars(path: Path) -> int:
    """What Claude Code loads of ``MEMORY.md``: its first lines, capped; never shown."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        head = "".join(line for _, line in zip(range(MEMORY_LINES), fh))
    return min(len(head), MEMORY_CHARS)


def inside(path: Path, roots: tuple[Path, ...]) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return any(resolved.is_relative_to(r) for r in roots)


def shown(path: str, repo: Path, home: Path) -> str:
    p = Path(path)
    for root, mark in ((repo, ""), (PLUGIN, "plugin:"), (home, "~/")):
        try:
            return f"{mark}{p.resolve().relative_to(root.resolve())}"
        except (ValueError, OSError):
            continue
    return path


def disk_session(
    crew_path: Path,
    crew: dict[str, Any],
    role: str,
    total: render_process.Total,
    home: Path,
    place: Path | None = None,
) -> tuple[list[Row], list[tuple[str, str, bool]], Path]:
    repo = (place or crew_path.parent.parent).resolve()
    work = render_process._places(crew_path, crew, total.slug, total.label, [], place)
    work_dir = work[0] if work else repo
    roots = (repo, PLUGIN.resolve())
    rows: list[Row] = []
    texts: list[tuple[str, str, bool]] = []
    kind = "worker" if role == "worker" else "full"
    texts.append(("L0", render_process.render_l0(crew, kind), True))
    if role != "worker":
        hook_input = {"source": "startup", "cwd": str(work_dir)}
        card = render_process.session_text(
            crew_path, crew, role, total.slug, hook_input, run_hooks=False
        )
        texts.append(("card", card, True))
    rules = [r for r in total.rows if r[0] == "rules"]
    for part, path, n in total.rows:
        if part == "note" or (part in COUNTED and part not in ("L0", "card") and not n):
            continue
        if part == "rules":
            continue
        if part == "rules-any-file":
            rows.append(Row("rules paths ** (first file read)", "disk", n, path))
            continue
        rows.append(Row(part, "disk", n, path if Path(path).is_file() else "", True))
        if part in ("instructions", "role-skill", "extra") and Path(path).is_file():
            texts.append(
                (
                    path,
                    Path(path).read_text(encoding="utf-8", errors="replace"),
                    inside(Path(path), roots),
                )
            )
    if rules:
        rows.append(
            Row(f"rules without paths ({len(rules)})", "disk", sum(n for *_, n in rules), "", True)
        )
        for _, path, _n in rules:
            texts.append(
                (
                    path,
                    Path(path).read_text(encoding="utf-8", errors="replace"),
                    inside(Path(path), roots),
                )
            )
    rows.append(memory_row(work_dir, role))
    return rows, texts, work_dir


def memory_row(work_dir: Path, role: str) -> Row:
    """The ``MEMORY.md`` row: its size on disk, unless the role's sessions run without it."""
    if role == "worker":
        return Row("MEMORY.md", MEMORY_OFF, 0)
    memory = (
        claude_home.config_dir()
        / "projects"
        / project_slug(main_worktree(work_dir))
        / "memory"
        / "MEMORY.md"
    )
    return Row("MEMORY.md", "disk", memory_chars(memory) if memory.is_file() else 0)


def largest(rows: list[Row], rules: list[tuple[str, str, int]]) -> list[tuple[str, int]]:
    files = [(r.path, r.chars or 0) for r in rows if r.path and r.source == "disk"]
    files += [(path, n) for _, path, n in rules]
    return sorted(files, key=lambda f: -f[1])[:TOP]


# --- transcripts -----------------------------------------------------------------------------


def transcript_files(projects: Path, work: Path) -> list[Path]:
    slug = project_slug(main_worktree(work))
    if not projects.is_dir():
        return []
    dirs = [
        d
        for d in projects.iterdir()
        if d.is_dir() and (d.name == slug or d.name.startswith(slug + "-"))
    ]
    files = [f for d in dirs for f in d.glob("*.jsonl")]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files[:SCAN_FILES]


def _lines(path: Path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for _, line in zip(range(HEAD_LINES), fh):
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                yield entry


def start_contexts(att: Any) -> list[str]:
    """The SessionStart ``additionalContext`` texts a transcript attachment carries: the
    ``hook_additional_context`` list (all hooks of one start), or one ``hook_success`` of a
    SessionStart hook (its ``stdout`` JSON). Both shapes stand in a transcript for one start."""
    if not isinstance(att, dict):
        return []
    if att.get("type") == "hook_additional_context":
        content = att.get("content")
        items = content if isinstance(content, list) else [content]
        return [x for x in items if isinstance(x, str)]
    if att.get("type") == "hook_success" and att.get("hookEvent") == "SessionStart":
        try:
            out = json.loads(att.get("stdout") or "")
        except (TypeError, ValueError):
            return []
        text = (
            (out.get("hookSpecificOutput") or {}).get("additionalContext")
            if isinstance(out, dict)
            else None
        )
        return [text] if isinstance(text, str) else []
    return []


def plugin_file(text: str) -> str | None:
    """The plugin file a SessionStart context is: a role card (its first line), the worker's short
    form or the L0; None for any other hook's output."""
    card = CARD_MARK.match(text)
    if card:
        return f"roles/{card[1]}.md"
    if WORKER_MARK in text:
        return "process/L0-worker.md"
    if L0_MARK in text:
        return "process/L0.md"
    return None


def session_role(path: Path, names: dict[str, str]) -> str | None:
    """The role of the transcript's session: a holder's name as its title, else the short form
    (worker) or the L0 (master) in its SessionStart context."""
    found = None
    for entry in _lines(path):
        title = entry.get("customTitle") or entry.get("agentName")
        if isinstance(title, str) and title.strip().lower() in names:
            return names[title.strip().lower()]
        for text in start_contexts(entry.get("attachment")):
            part = plugin_file(text)
            if part == "process/L0-worker.md":
                found = "worker"
            elif part == "process/L0.md" and found is None:
                found = "master"
        if entry.get("type") == "api-request-shape":
            break
    return found


def transcript_sizes(path: Path) -> dict[str, int] | None:
    """Sizes of the first request's blocks; None without an ``api-request-shape`` line or when
    an assistant entry comes before it (a resumed session, not a cold start)."""
    sizes = dict.fromkeys(TRANSCRIPT_PARTS, 0)
    for entry in _lines(path):
        if entry.get("type") == "assistant":
            return None  # an answer before the first recorded request: no cold start in this file
        att = entry.get("attachment")
        if isinstance(att, dict):
            kind = att.get("type")
            if kind == "skill_listing":
                sizes["skill listing"] += len(str(att.get("content") or ""))
            elif kind == "agent_listing_delta":
                sizes["agent listing"] += sum(len(str(x)) for x in att.get("addedLines") or [])
            elif kind == "deferred_tools_delta":
                sizes["deferred tool names"] += sum(
                    len(str(x)) for x in att.get("addedLines") or []
                )
            elif kind == "mcp_instructions_delta":
                sizes["MCP instructions"] += sum(len(str(x)) for x in att.get("addedBlocks") or [])
        if entry.get("type") == "api-request-shape":
            shape = entry.get("shape") or {}
            sizes["system prompt"] = sum(
                len(str(b.get("text") or ""))
                for b in shape.get("system") or []
                if isinstance(b, dict)
            )
            sizes["tool schemas"] = sum(
                len(json.dumps(t, ensure_ascii=False)) for t in shape.get("tools") or []
            )
            break
    else:
        return None
    for entry in _lines_after(path):
        usage = (
            (entry.get("message") or {}).get("usage") if entry.get("type") == "assistant" else None
        )
        if isinstance(usage, dict):
            sizes[MEASURED] = sum(
                int(usage.get(k) or 0)
                for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
            )
            break
    return sizes


def _lines_after(path: Path):
    """The entries after the first ``api-request-shape`` line."""
    seen = False
    for entry in _lines(path):
        if seen:
            yield entry
        elif entry.get("type") == "api-request-shape":
            seen = True


def newest_transcripts(
    files: list[Path], names: dict[str, str], wanted: set[str]
) -> dict[str, tuple[str, dict[str, int]]]:
    out: dict[str, tuple[str, dict[str, int]]] = {}
    for path in files:
        if wanted <= set(out):
            break
        try:
            role = session_role(path, names)
            if role is None or role in out or role not in wanted:
                continue
            sizes = transcript_sizes(path)
        except OSError:
            continue
        if sizes is not None:
            out[role] = (path.name, sizes)
    return out


# --- duplicates ------------------------------------------------------------------------------

_SPLIT = re.compile(r"(?<=[.!?])\s+|\n\s*\n|\n(?=\s*(?:[-*+|#>]|\d+\.)\s)")
_MARKS = re.compile(r"^\s*(?:[-*+>]|\d+\.|#+)\s+")


def sentences(text: str) -> set[str]:
    out = set()
    for raw in _SPLIT.split(text):
        sentence = " ".join(_MARKS.sub("", raw).split())
        if len(sentence) >= MIN_SENTENCE:
            out.add(sentence)
    return out


def duplicates(texts: list[tuple[str, str, bool]]) -> list[tuple[str, list[str], bool]]:
    """(sentence, places, quotable) for each sentence standing in two or more places."""
    where: dict[str, list[tuple[str, bool]]] = {}
    for place, text, quotable in texts:
        for sentence in sentences(text):
            where.setdefault(sentence, []).append((place, quotable))
    out = []
    for sentence, places in where.items():
        if len({p for p, _ in places}) >= 2:
            out.append((sentence, [p for p, _ in places], all(q for _, q in places)))
    return sorted(out, key=lambda d: (d[1], d[0]))


# --- report ----------------------------------------------------------------------------------


def measure(
    crew_path: Path,
    crew: dict[str, Any],
    roles: list[str],
    home: Path,
    place: Path | None = None,
) -> list[tuple[str, Session, list[tuple[str, int]], list]]:
    """Per session: (role, Session, largest files, duplicates). ``place`` is the repo measured
    (None: the crew repo); a named member working elsewhere is a Session with ``elsewhere``."""
    foreign = place is not None and place.resolve() != crew_path.parent.parent.resolve()
    names = {}
    for role in crewlib.ROLE_KEYS:
        name = crewlib.holder_name(crew, role)
        if name:
            names.setdefault(name.lower(), role)
    for _, entry in render_process.specialist_members(crew):
        if entry.get("name"):
            names.setdefault(str(entry["name"]).lower(), "specialist")
    projects = claude_home.config_dir() / "projects"
    out = []
    cache: dict[Path, dict[str, tuple[str, dict[str, int]]]] = {}
    for role in roles:
        absent: list[str] = []
        for total in render_process.total_rows(crew_path, crew, role, home, absent, place):
            rows, texts, work = disk_session(crew_path, crew, role, total, home, place)
            if foreign and total.slug and work != place.resolve():
                out.append(
                    (role, Session(total.label, [], 0, [], NA, elsewhere=work.name), [], [])
                )
                continue
            if work not in cache:
                files = transcript_files(projects, work)
                cache[work] = newest_transcripts(files, names, set(roles))
            found = cache[work].get(role)
            if found:
                rows += [Row(p, "transcript", found[1][p]) for p in TRANSCRIPT_PARTS]
            else:
                rows += [Row(p, "transcript", None) for p in TRANSCRIPT_PARTS]
            session = Session(
                total.label,
                rows,
                total.total,
                texts,
                found[0] if found else NA,
                found[1].get(MEASURED) if found else None,
            )
            rules = [r for r in total.rows if r[0] == "rules"]
            out.append((role, session, largest(rows, rules), duplicates(texts)))
        out += [(role, Session(label, [], 0, [], NA), [], []) for label in absent]
    return out


def previous(store: Path | None, today: str) -> dict[str, dict[str, int]]:
    if store is None or not (store / "reports").is_dir():
        return {}
    for path in sorted((store / "reports").glob("context-*.md"), reverse=True):
        if path.name == f"context-{today}.md":
            continue
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            if line.startswith(DATA) and line.endswith("-->"):
                try:
                    return json.loads(line[len(DATA) : -3])
                except ValueError:
                    return {}
    return {}


def row_key(row: Row, repo: Path, home: Path) -> str:
    return (
        f"instructions {shown(row.path, repo, home)}" if row.part == "instructions" else row.part
    )


def merged_rows(session: Session, repo: Path, home: Path) -> dict[str, Row]:
    """One row per key: the instruction files each, every other part summed."""
    out: dict[str, Row] = {}
    for row in session.rows:
        key = row_key(row, repo, home)
        if key in out and out[key].chars is not None and row.chars is not None:
            out[key] = out[key]._replace(chars=out[key].chars + row.chars)
        else:
            out.setdefault(key, row)
    return out


def summed(rows: dict[str, Row]) -> tuple[int, bool]:
    """(the table's sum, whether a part is unmeasured); the path-bound rules stay out."""
    real = sum(r.chars or 0 for r in rows.values() if not r.part.startswith("rules paths"))
    return real, any(r.chars is None for r in rows.values())


def numbers(results: list, repo: Path, home: Path) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for _, session, _, _ in results:
        rows = merged_rows(session, repo, home)
        parts = {k: r.chars for k, r in rows.items() if r.chars is not None}
        if rows:
            parts["sum"] = summed(rows)[0]
        out[session.label] = parts
    return out


def fmt(n: int | None) -> str:
    return "n/a" if n is None else f"{n:,}"


def delta(now: int | None, before: int | None) -> str:
    if now is None or before is None:
        return "—"
    return f"{now - before:+,}"


def render(results: list, before: dict, repo: Path, home: Path, md: bool) -> str:
    out = []
    now = numbers(results, repo, home)
    head = "Characters exact from disk and transcript; tokens estimated as characters ÷ 4."
    out.append(f"# Context load\n\n{head}" if md else head)
    for _, session, files, dups in results:
        if session.elsewhere:
            out.append(f"\n{session.label}: works in {session.elsewhere}, measured there")
            continue
        out.append(f"\n## {session.label}\n" if md else f"\n# {session.label}")
        if not session.rows:
            out.append("skipped: its workplace or an extra repo is absent")
            continue
        out.append(
            f"transcript: {session.transcript}\n" if md else f"transcript: {session.transcript}"
        )
        last = before.get(session.label, {})
        rows = merged_rows(session, repo, home)
        table = [("part", "source", "chars", "≈ tokens (chars ÷ 4, low for JSON)", "Δ chars")]
        for key, row in rows.items():
            n = row.chars
            table.append(
                (
                    key,
                    row.source,
                    fmt(n),
                    fmt(None if n is None else tokens(n)),
                    delta(n, last.get(key)),
                )
            )
        real, unknown = summed(rows)
        table.append(("sum", "", fmt(real), fmt(tokens(real)), delta(real, last.get("sum"))))
        out.append(_table(table, md))
        measured = session.measured
        out.append(
            ("\n" if md else "")
            + f"measured start: {fmt(measured)} tokens"
            + ("" if measured is None else f" (estimated sum {tokens(real):,})")
        )
        if measured:
            line = (
                f"the budget gate counts {session.counted:,} chars (≈ {tokens(session.counted):,}"
                f" tokens) of a measured start of {measured:,} tokens"
                f" ({tokens(session.counted) * 100 // measured} % counted)"
            )
        else:
            share = f"{session.counted * 100 // real} %" if real else "—"
            line = (
                f"the budget gate counts {session.counted:,} chars, the table sums "
                f"{'≥ ' if unknown else ''}{real:,} ({share} counted)"
            )
        out.append(f"counted vs real: {line}")
        out.append(
            "largest files: " + "; ".join(f"{shown(p, repo, home)} {n:,}" for p, n in files)
        )
        if not dups:
            out.append("duplicate sentences: none")
            continue
        out.append(f"duplicate sentences ({len(dups)}):")
        for sentence, places, quotable in dups:
            where = " · ".join(p if p in ("L0", "card") else shown(p, repo, home) for p in places)
            digest = hashlib.sha256(sentence.encode()).hexdigest()[:8]
            text = f'"{sentence[:QUOTE]}"' if quotable else f"#{digest}"
            out.append(f"- {text} — {where}")
    out.append("\n" + FOOTER)
    if md:
        out.append("\n" + DATA + json.dumps(now, ensure_ascii=False, sort_keys=True) + " -->")
    return "\n".join(out) + "\n"


def _table(rows: list[tuple[str, ...]], md: bool) -> str:
    if md:
        lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(rows[0])]
        lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
        return "\n".join(lines)
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return "\n".join(
        "  ".join(c.ljust(w) if i < 2 else c.rjust(w) for i, (c, w) in enumerate(zip(r, widths)))
        for r in rows
    )


def store_of(repo: Path) -> Path | None:
    store = repo / ".weside" / "optimization"
    return store if store.is_dir() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="start")
    parser.add_argument("--role", action="append", choices=render_process.all_roles())
    parser.add_argument("--home")
    parser.add_argument("--md", action="store_true")
    args = parser.parse_args(argv)
    try:
        crew_path, crew = crewlib.find_and_load(args.start or Path.cwd())
        if crew_path is None or crew is None:
            print("context_load: no crew file here; nothing measured", file=sys.stderr)
            return 0
        home = Path(args.home) if args.home else Path.home()
        repo = (crewlib.declaring_root(args.start) or crew_path.parent.parent).resolve()
        today = crewlib.today(repo)
        store = store_of(repo)
        roles = args.role or list(render_process.all_roles())
        results = measure(crew_path, crew, roles, home, repo)
        text = render(results, previous(store, today), repo, home, args.md)
        sys.stdout.write(text)
        if args.md:
            if store is None:
                print(
                    "context_load: no optimization store (.weside/optimization/); nothing written",
                    file=sys.stderr,
                )
            else:
                target = store / "reports" / f"context-{today}.md"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
                print(f"context_load: wrote {target}", file=sys.stderr)
    except (crewlib.CrewError, render_process.RenderError, OSError) as exc:
        print(f"context_load: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
