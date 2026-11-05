"""Staging booking and acceptance for board.py (docs/board.md § Staging).

The shared state lives in GitHub issues of the crew's repo, which a scheduled RC job on GitHub
reads too; board.json only mirrors it in its `staging` block for the /board pane. The issue
grammar is the contract with that job and pinned by `fixtures/staging/issues.json`:

- a booking: one open issue, label `release.staging_booking_label`, title
  `staging booked by <session>`, body lines `holder: <session>` and `until: <YYYY-MM-DDTHH:MMZ>`;
- an acceptance: one open issue per RC, label `release.staging_acceptance_label`, title `<rc tag>`,
  body lines `rc: <tag>`, `opened: <UTC>`, `keys: <keys>`; label `release.staging_past_sla_label`
  once `release.staging_sla_hours` passed. A hotfix RC moves title and `rc:`, `opened:` stays, so
  this module follows an acceptance by its issue number.

`book` refuses while an acceptance is open or another booking runs, and opens the booking issue.
`unbook` closes the caller's own booking; `unbook <rc>` closes that RC's acceptance. `sync` reads
both, writes the `staging` block and, once per acceptance issue past the SLA, one `todo` news item
for the coordinator. Every read fails closed: an unreadable list refuses a booking.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

GH_TIMEOUT = 30
MINUTE_FMT = "%Y-%m-%dT%H:%MZ"
ISSUE_FIELDS = "number,title,body,labels,createdAt"
LABEL_COLORS = {"booking": "1d76db", "acceptance": "0e8a16", "past_sla": "d93f0b"}
NEWS_PREFIX = "ST"  # `ST<issue number>`: one past-SLA news item per acceptance issue


class StagingError(Exception):
    """A refusal or a failed read; board.py prints it and exits `code`."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def run_gh(args):
    """`gh <args>` → stdout; a failure raises StagingError with gh's last stderr line."""
    try:
        done = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=GH_TIMEOUT, check=False
        )
    except FileNotFoundError:
        raise StagingError("gh not found") from None
    except subprocess.TimeoutExpired:
        raise StagingError(f"gh ran past {GH_TIMEOUT} s") from None
    if done.returncode != 0:
        why = (done.stderr.strip().splitlines() or [f"exit {done.returncode}"])[-1]
        raise StagingError(why)
    return done.stdout


def settings(crew):
    """Labels and SLA hours from the crew's `release` block (crew.DEFAULTS holds the defaults)."""
    release = crew.get("release") or {}
    return {
        "booking": release.get("staging_booking_label") or "staging-booking",
        "acceptance": release.get("staging_acceptance_label") or "staging-acceptance",
        "past_sla": release.get("staging_past_sla_label") or "past-sla",
        "sla_hours": release.get("staging_sla_hours") or 12,
    }


def repo_of(directory):
    """`owner/name` of the GitHub `origin` of the repo holding `directory`, or None."""
    done = subprocess.run(
        ["git", "-C", str(directory), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    url = done.stdout.strip() if done.returncode == 0 else ""
    found = re.search(r"github\.com[/:]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url)
    return f"{found.group(1)}/{found.group(2)}" if found else None


def minute(ts):
    return ts.astimezone(timezone.utc).strftime(MINUTE_FMT)


def parse_time(text):
    """An aware datetime from `YYYY-MM-DDTHH:MM[:SS]Z` or an ISO time with offset, else None."""
    text = (text or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        return None
    return when if when.tzinfo else None


def body_field(body, name):
    found = re.search(rf"(?m)^{re.escape(name)}:[ \t]*(\S.*?)[ \t]*$", body or "")
    return found.group(1) if found else None


class Staging:
    """One crew repo's staging issues through one `gh` seam."""

    def __init__(self, crew, repo, gh=run_gh):
        self.cfg = settings(crew)
        self.repo = repo
        self.gh = gh

    def issues(self, kind):
        """Open issues of `kind` (`booking`, `acceptance`) by number; a failed read raises."""
        label = self.cfg[kind]
        args = ["issue", "list", "--repo", self.repo, "--label", label, "--state", "open"]
        try:
            out = self.gh([*args, "--limit", "100", "--json", ISSUE_FIELDS])
            items = json.loads(out or "[]")
        except (StagingError, ValueError) as exc:
            raise StagingError(f"cannot read {label} issues ({exc})") from None
        if not isinstance(items, list):
            raise StagingError(f"cannot read {label} issues (no JSON list)")
        return sorted((i for i in items if isinstance(i, dict)), key=lambda i: i.get("number", 0))

    def bookings(self, now):
        """The open bookings that still hold (`until` in the future or unreadable)."""
        out = []
        for issue in self.issues("booking"):
            body = issue.get("body") or ""
            until = parse_time(body_field(body, "until"))
            if until is not None and until <= now:
                continue  # expired: the RC job closes it with `expired <UTC>`
            holder = body_field(body, "holder") or "unknown"
            out.append(
                {
                    "issue": issue.get("number"),
                    "holder": holder,
                    "until": minute(until) if until else None,
                }
            )
        return out

    def acceptances(self, now):
        hours = self.cfg["sla_hours"]
        out = []
        for issue in self.issues("acceptance"):
            body = issue.get("body") or ""
            opened_text = body_field(body, "opened") or issue.get("createdAt") or ""
            opened = parse_time(opened_text)
            labels = {
                label.get("name") for label in issue.get("labels") or [] if isinstance(label, dict)
            }
            past = self.cfg["past_sla"] in labels or (
                opened is not None and now - opened > timedelta(hours=hours)
            )
            out.append(
                {
                    "issue": issue.get("number"),
                    "rc": body_field(body, "rc") or issue.get("title") or "?",
                    "opened": minute(opened) if opened else opened_text or None,
                    "due": minute(opened + timedelta(hours=hours)) if opened else None,
                    "keys": body_field(body, "keys") or "",
                    "past_sla": past,
                }
            )
        return out

    def ensure_label(self, kind):
        label = self.cfg[kind]
        self.gh(
            [
                "label",
                "create",
                label,
                "--repo",
                self.repo,
                "--color",
                LABEL_COLORS[kind],
                "--description",
                f"staging {kind.replace('_', ' ')} (board.py, the RC job)",
                "--force",
            ]
        )

    def close(self, number, comment):
        self.gh(["issue", "close", str(number), "--repo", self.repo, "--comment", comment])


def book(staging, holder, until, now):
    """Open the booking issue; refuses an open acceptance or a running booking. Returns its URL."""
    head = "board.py book: refused:"
    if until <= now:
        raise StagingError(f"{head} --until {minute(until)} is not in the future")
    try:
        accepting = staging.acceptances(now)
        running = staging.bookings(now)
    except StagingError as exc:
        raise StagingError(f"{head} {exc}") from None
    if accepting:
        first = accepting[0]
        raise StagingError(f"{head} {first['rc']} in acceptance since {first['opened']}")
    if running:
        first = running[0]
        until_text = first["until"] or "<unreadable>"
        raise StagingError(
            f"{head} booked by {first['holder']} until {until_text} (issue #{first['issue']})"
        )
    body = f"holder: {holder}\nuntil: {minute(until)}\n"
    try:
        staging.ensure_label("booking")
        url = staging.gh(
            [
                "issue",
                "create",
                "--repo",
                staging.repo,
                "--title",
                f"staging booked by {holder}",
                "--label",
                staging.cfg["booking"],
                "--body",
                body,
            ]
        ).strip()
    except StagingError as exc:
        raise StagingError(f"board.py book: opening the booking failed ({exc})") from None
    return url


def unbook(staging, holder, rc, now):
    """Close the caller's bookings, or with `rc` that RC's acceptance; returns the closed numbers."""
    try:
        if rc:
            found = [a["issue"] for a in staging.acceptances(now) if a["rc"] == rc]
            what = f"no open acceptance for {rc}"
            comment = f"acceptance closed {minute(now)} by {holder}"
        else:
            found = [b["issue"] for b in staging.bookings(now) if b["holder"] == holder]
            what = f"{holder} holds no open booking"
            comment = f"unbooked {minute(now)} by {holder}"
    except StagingError as exc:
        raise StagingError(f"board.py unbook: refused: {exc}") from None
    if not found:
        raise StagingError(f"board.py unbook: refused: {what}")
    for number in found:
        try:
            staging.close(number, comment)
        except StagingError as exc:
            raise StagingError(f"board.py unbook: closing #{number} failed ({exc})") from None
    return found


def snapshot(staging, now):
    """The `staging` block as the issues say it now (raises StagingError on a failed read)."""
    bookings = staging.bookings(now)
    acceptances = staging.acceptances(now)
    return {
        "synced": minute(now),
        "repo": staging.repo,
        "sla_hours": staging.cfg["sla_hours"],
        "booking": bookings[0] if bookings else None,
        "acceptance": acceptances[0] if acceptances else None,
    }


def merge_block(board, block, now, coordinator_role="coordinator"):
    """Write `block` into `board["staging"]` and add the past-SLA news item once per acceptance
    issue; returns the news item written, or None."""
    old = board.get("staging") if isinstance(board.get("staging"), dict) else {}
    old_acc = old.get("acceptance") if isinstance(old.get("acceptance"), dict) else {}
    acc = block.get("acceptance")
    item = None
    if acc:
        news_id = f"{NEWS_PREFIX}{acc['issue']}"
        if old_acc.get("issue") == acc["issue"] and old_acc.get("news"):
            acc["news"] = old_acc["news"]
        news = board.setdefault("news", [])
        known = {n.get("id") for n in news if isinstance(n, dict)}
        if acc["past_sla"] and not acc.get("news"):
            acc["news"] = news_id
            if news_id not in known:
                item = {
                    "id": news_id,
                    "kind": "todo",
                    "for": coordinator_role,
                    "title": f"staging acceptance {acc['rc']} past {block['sla_hours']} h",
                    "body": f"opened {acc['opened']}, issue #{acc['issue']} in {block['repo']}",
                    "ts": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                news.insert(0, item)
    board["staging"] = block
    return item


def status_lines(block):
    lines = []
    booking, acc = block.get("booking"), block.get("acceptance")
    if booking:
        until = booking.get("until") or "<unreadable>"
        lines.append(f"staging: booked by {booking['holder']} until {until} (#{booking['issue']})")
    if acc:
        mark = f", past {block['sla_hours']} h" if acc.get("past_sla") else ""
        lines.append(
            f"staging: {acc['rc']} in acceptance since {acc['opened']} (#{acc['issue']}){mark}"
        )
    return lines or ["staging: free"]


def crew_repo(crew_path, cwd=None):
    """The repo of the crew file (its own git origin), else the cwd's."""
    for where in ([Path(crew_path).parent] if crew_path else []) + [Path(cwd or Path.cwd())]:
        repo = repo_of(where)
        if repo:
            return repo
    return None
