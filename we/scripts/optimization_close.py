#!/usr/bin/env python3
"""Close the optimization inbox entries that settled themselves: the first step of `/we:optimize`.

Usage: optimization_close.py [--store <dir>] [--config <file>] [--prs-json <file>] [--today YYYY-MM-DD]
                             [--expire-all-before YYYY-MM-DD] [--plugin-prs-json <file>]

For every open entry in `<store>/inbox/` (default `.weside/optimization`; format:
`references/optimization-store.md` § Inbox entry), in this order:

  applied  a merged PR whose title or body names the entry's key (a whole token, any case) and that
           merged on or after the entry's first-seen date carried it (an older PR cannot have: the
           entry is a recurrence after an earlier apply); a PR that changes a file under
           `.weside/optimization/` never counts (a retro, an audit or an optimize run lists keys it
           did not apply, and `/we:optimize` closes its own applies itself): a ledger row `applied` with that PR as `change`, metric `recurrence`, `before` the
           entry's `retro` evidence lines, `after` pending, `review_by` today plus
           `optimization.review_days` (default 30)
  expired  the entry has fewer than two evidence lines and its first-seen date (the file name's) is
           `optimization.expire_days` (default 14) or more days old; with `--expire-all-before`,
           also every entry first seen before that date, whatever its evidence (the old stock in
           one run, no review): a ledger row `expired`
  open     anything else: left for the decider

A closed entry's row goes on top of `LEDGER.md`'s table (created with its header when absent). An
applied entry's inbox file is deleted; an expired one moves to `inbox/expired/`, where it stays
readable and `retro_write.py` revives it (back to `inbox/`, open) on a new evidence line under its
key. The caller commits all of it with the rest of the run. Merged PRs come from
`gh pr list --state merged --limit 200 --json number,title,body,url,mergedAt,files` run in the store's repo, or
from `--prs-json` (the same JSON). Prints one line per closed entry (`applied <key> · <url>`,
`expired <key> · <n> days, <m> evidence line(s)`) and a final `closed <a> applied, <e> expired,
<o> open`. Exit 0; 2 when the store, the config or the PR list cannot be read.

Then the `LEDGER.md` rows whose `decision` is `upstream` (a finding handed to the plugin's
maintainers). None → nothing more is read or printed. Otherwise the plugin's merged PRs come from one
`gh pr list -R <owner/name> --state merged --search "merged:>=<oldest upstream date>" --limit 500`
(the repository from `plugin.json` beside this script), cached in
`~/.cache/we/plugin-prs/<owner>-<name>.json` and reused while it was fetched today and covers the
oldest row date (at most one search a day); `--plugin-prs-json` replaces search and cache. Per row,
the newest PR merged on or after the row's date whose title or body names its key decides by the
first line naming it: the whole word `rejected` → `rejected`, `deferred` → stays `upstream`, else
`applied` (`change` the PR, `review_by` merge date plus `review_days`). A row with no such PR (a
`deferred` one included) whose date is `review_days` or more old → `expired`. The row is rewritten
in place, its evidence gains the PR or the age. Prints one line per closed row (`upstream applied
<key> · <url>`, `upstream rejected <key> · <url>`, `upstream expired <key> · <n> days`) after the
`closed …` line, then `upstream: <a> applied, <r> rejected, <e> expired, <o> open`. A failed search
or an unreadable `plugin.json` prints `upstream: not checked (<reason>)` and keeps exit 0.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

HEADER = (
    "| date | key | target | decision | evidence | metric | before → after | review_by | change |\n"
    "|---|---|---|---|---|---|---|---|---|\n"
)
EXPIRE_DAYS = 14
REVIEW_DAYS = 30
EXPIRED = "expired"  # the inbox subfolder of expired entries; retro_write.py revives from it
_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$")
_CELL_SPLIT = re.compile(r"(?<!\\)\|")
_REPO = re.compile(r"github\.com[/:]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")
_FIELD = re.compile(r"^(?P<k>[a-z_]+):\s*(?P<v>.*?)\s*(?:#.*)?$")


class CloseError(Exception):
    pass


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    head = text[3:].split("\n---", 1)[0]
    out = {}
    for line in head.splitlines():
        found = _FIELD.match(line.strip())
        if found:
            out[found.group("k")] = found.group("v")
    return out


def evidence(text: str) -> list[str]:
    """The `- …` lines under `## Evidence`, up to the next level-2 heading."""
    out, inside = [], False
    for line in text.split("\n"):
        if line.startswith("## "):
            inside = line.strip() == "## Evidence"
            continue
        if inside and line.startswith("- "):
            out.append(line.rstrip())
    return out


def names_key(key: str, text: str) -> bool:
    return (
        re.search(rf"(?<![a-z0-9:-]){re.escape(key)}(?![a-z0-9:-])", text, re.IGNORECASE)
        is not None
    )


def carried(pr: dict, key: str, seen: datetime.date | None) -> bool:
    """The PR names the key, changes no store file and did not merge before the entry was seen."""
    files = pr.get("files") or []
    if any(str((f or {}).get("path", "")).startswith(".weside/optimization/") for f in files):
        return False
    if not names_key(key, f"{pr.get('title') or ''}\n{pr.get('body') or ''}"):
        return False
    merged_at = str(pr.get("mergedAt") or "")[:10]
    try:
        return seen is None or not merged_at or datetime.date.fromisoformat(merged_at) >= seen
    except ValueError:
        return True


def merged_prs(store: Path, prs_json: Path | None) -> list[dict]:
    try:
        if prs_json is not None:
            raw = prs_json.read_text()
        else:
            raw = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--state",
                    "merged",
                    "--limit",
                    "200",
                    "--json",
                    "number,title,body,url,mergedAt,files",
                ],
                cwd=store,
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            ).stdout
        prs = json.loads(raw)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise CloseError(f"merged PRs: {exc}") from exc
    if not isinstance(prs, list):
        raise CloseError("merged PRs: not a JSON list")
    return [p for p in prs if isinstance(p, dict)]


def settings(config: Path) -> tuple[int, int]:
    if not config.exists():
        return EXPIRE_DAYS, REVIEW_DAYS
    try:
        section = json.loads(config.read_text()).get("optimization") or {}
        return int(section.get("expire_days", EXPIRE_DAYS)), int(
            section.get("review_days", REVIEW_DAYS)
        )
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise CloseError(f"{config}: {exc}") from exc


def cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def row(*cells: object) -> str:
    return "| " + " | ".join(cell(c) for c in cells) + " |\n"


def add_rows(ledger: Path, rows: list[str]) -> None:
    text = ledger.read_text() if ledger.exists() else ""
    lines = text.splitlines(keepends=True)
    sep = next(
        (i for i, line in enumerate(lines) if re.match(r"^\|(\s*:?-+:?\s*\|)+\s*$", line)), None
    )
    if sep is None:
        text = (text.rstrip("\n") + "\n\n" if text.strip() else "") + HEADER + "".join(rows)
    else:
        text = "".join(lines[: sep + 1]) + "".join(rows) + "".join(lines[sep + 1 :])
    ledger.write_text(text)


def close(
    store: Path,
    prs: list[dict],
    today: datetime.date,
    expire_days: int,
    review_days: int,
    expire_before: datetime.date | None = None,
) -> list[str]:
    inbox = store / "inbox"
    if not inbox.is_dir():
        raise CloseError(f"{inbox}: no inbox")
    out, rows, counts = [], [], {"applied": 0, "expired": 0, "open": 0}
    for path in sorted(inbox.glob("*.md")):
        found = _NAME.match(path.name)
        text = path.read_text()
        meta = frontmatter(text)
        key = meta.get("key") or (found.group(2) if found else path.stem)
        target = meta.get("target", "—")
        lines = evidence(text)
        try:
            seen = datetime.date.fromisoformat(found.group(1)) if found else None
        except ValueError:
            seen = None
        pr = next((p for p in prs if carried(p, key, seen)), None)
        if pr is not None:
            url = pr.get("url") or f"#{pr.get('number')}"
            retro = sum(1 for line in lines if " retro " in f" {line} ")
            review_by = (today + datetime.timedelta(days=review_days)).isoformat()
            rows.append(
                row(
                    today,
                    key,
                    target,
                    "applied",
                    f"merged PR {url}",
                    "recurrence",
                    f"{retro} → pending",
                    review_by,
                    url,
                )
            )
            out.append(f"applied {key} · {url}")
            counts["applied"] += 1
            path.unlink()
            continue
        age = (today - seen).days if seen else None
        stock = seen is not None and expire_before is not None and seen < expire_before
        if stock or (seen is not None and len(lines) < 2 and age >= expire_days):
            rows.append(
                row(
                    today,
                    key,
                    target,
                    "expired",
                    f"{len(lines)} evidence line(s) in {age} days",
                    "—",
                    "—",
                    "—",
                    "—",
                )
            )
            out.append(f"expired {key} · {age} days, {len(lines)} evidence line(s)")
            counts["expired"] += 1
            (inbox / EXPIRED).mkdir(exist_ok=True)
            path.replace(inbox / EXPIRED / path.name)
            continue
        counts["open"] += 1
    if rows:
        add_rows(store / "LEDGER.md", rows)
    out.append(
        f"closed {counts['applied']} applied, {counts['expired']} expired, {counts['open']} open"
    )
    return out


def _cells(line: str) -> list[str] | None:
    """The raw cells of a ledger table row (escapes kept), or None for any other line."""
    if not line.startswith("|") or re.match(r"^\|(\s*:?-+:?\s*\|)+\s*$", line):
        return None
    parts = _CELL_SPLIT.split(line.rstrip("\n"))
    cells = [c.strip() for c in parts[1:-1]]
    return cells if len(cells) == 9 else None


def _date(text: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def plugin_prs(since: datetime.date, today: datetime.date, prs_json: Path | None) -> list[dict]:
    """The plugin repository's merged PRs since `since`: one search a day, cached."""
    if prs_json is not None:
        prs = json.loads(prs_json.read_text())
    else:
        manifest = Path(__file__).resolve().parents[1] / ".claude-plugin" / "plugin.json"
        found = _REPO.search(str(json.loads(manifest.read_text()).get("repository") or ""))
        if not found:
            raise ValueError("plugin.json names no GitHub repository")
        owner, name = found.groups()
        cache = Path.home() / ".cache" / "we" / "plugin-prs" / f"{owner}-{name}.json"
        try:
            cached = json.loads(cache.read_text())
            if (
                cached.get("fetched") == today.isoformat()
                and str(cached.get("since")) <= since.isoformat()
            ):
                return [p for p in cached.get("prs") or [] if isinstance(p, dict)]
        except (OSError, json.JSONDecodeError, AttributeError):
            pass  # absent or corrupt: search again
        prs = json.loads(
            subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "-R",
                    f"{owner}/{name}",
                    "--state",
                    "merged",
                    "--search",
                    f"merged:>={since.isoformat()}",
                    "--limit",
                    "500",
                    "--json",
                    "number,title,body,url,mergedAt",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            ).stdout
        )
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps({"fetched": today.isoformat(), "since": since.isoformat(), "prs": prs})
        )
    if not isinstance(prs, list):
        raise ValueError("plugin PRs: not a JSON list")
    return [p for p in prs if isinstance(p, dict)]


def _verdict(pr: dict, key: str) -> str:
    """`rejected`, `deferred` or `applied`: the first line of title or body that names the key."""
    for line in f"{pr.get('title') or ''}\n{pr.get('body') or ''}".splitlines():
        if names_key(key, line):
            for word in ("rejected", "deferred"):
                if re.search(rf"\b{word}\b", line, re.IGNORECASE):
                    return word
            return "applied"
    return "applied"


def close_upstream(
    ledger: Path, today: datetime.date, review_days: int, prs_json: Path | None
) -> list[str]:
    """Close the ledger's `upstream` rows by the plugin's merged PRs; [] when there is none."""
    if not ledger.exists():
        return []
    lines = ledger.read_text().splitlines(keepends=True)
    rows = [
        (i, cells)
        for i, cells in ((i, _cells(line)) for i, line in enumerate(lines))
        if cells and cells[3] == "upstream" and _date(cells[0])
    ]
    if not rows:
        return []
    since = min(_date(cells[0]) for _, cells in rows)
    try:
        prs = plugin_prs(since, today, prs_json)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
        return [
            f"upstream: not checked ({str(exc).splitlines()[0] if str(exc) else type(exc).__name__})"
        ]
    prs = sorted(prs, key=lambda p: str(p.get("mergedAt") or ""), reverse=True)
    out, counts = [], {"applied": 0, "rejected": 0, "expired": 0, "open": 0}
    for i, cells in rows:
        key, born = cells[1].replace("\\|", "|"), _date(cells[0])
        pr = next(
            (
                p
                for p in prs
                if (_date(p.get("mergedAt") or "") or born) >= born
                and names_key(key, f"{p.get('title') or ''}\n{p.get('body') or ''}")
            ),
            None,
        )
        verdict = _verdict(pr, key) if pr is not None else None
        age = (today - born).days
        if verdict in ("applied", "rejected"):
            url = pr.get("url") or f"#{pr.get('number')}"
            merged = _date(pr.get("mergedAt") or "") or today
            cells[3] = verdict
            cells[4] += f"; plugin PR {cell(url)}"
            cells[7] = (
                (merged + datetime.timedelta(days=review_days)).isoformat()
                if verdict == "applied"
                else "—"
            )
            cells[8] = cell(url)
            out.append(f"upstream {verdict} {key} · {url}")
        elif age >= review_days:
            verdict = "expired"
            cells[3] = verdict
            cells[4] += f"; no plugin PR in {age} days"
            cells[7] = cells[8] = "—"
            out.append(f"upstream expired {key} · {age} days")
        else:
            counts["open"] += 1
            continue
        counts[verdict] += 1
        lines[i] = "| " + " | ".join(cells) + " |\n"
    ledger.write_text("".join(lines))
    out.append(
        f"upstream: {counts['applied']} applied, {counts['rejected']} rejected,"
        f" {counts['expired']} expired, {counts['open']} open"
    )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", type=Path, default=Path(".weside/optimization"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--prs-json", type=Path)
    parser.add_argument("--today")
    parser.add_argument("--expire-all-before", metavar="YYYY-MM-DD")
    parser.add_argument("--plugin-prs-json", type=Path)
    args = parser.parse_args(argv)
    try:
        today = (
            datetime.date.fromisoformat(args.today)
            if args.today
            else datetime.datetime.now(datetime.timezone.utc).date()
        )
        config = args.config or args.store.resolve().parent / "config.json"
        expire_days, review_days = settings(config)
        if not (args.store / "inbox").is_dir():
            raise CloseError(f"{args.store / 'inbox'}: no inbox")
        prs = merged_prs(args.store, args.prs_json)
        before = (
            datetime.date.fromisoformat(args.expire_all_before) if args.expire_all_before else None
        )
        for line in close(args.store, prs, today, expire_days, review_days, before):
            print(line)
        for line in close_upstream(
            args.store / "LEDGER.md", today, review_days, args.plugin_prs_json
        ):
            print(line)
    except (CloseError, ValueError, OSError) as exc:
        print(f"optimization_close: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
