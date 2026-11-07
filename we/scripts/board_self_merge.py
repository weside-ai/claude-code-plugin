"""The self-merge notices on the board (docs/board.md § Self-merge window).

A repo that runs a self-merge window (a scheduled workflow that merges a one-way PR outside the
brake's core 2 h after a green T2 panel, unless vetoed) posts one push line per head on the PR, a
comment by `github-actions[bot]` with the marker `<!-- brake-self-merge-notice -->`. The workflow
does not wait on the board; this module mirrors each notice as one board `news` item, so the board
stays the owner's one inbox. The comment grammar is the workflow judge's, pinned by
`fixtures/brake-self-merge/judge.json`.

`sync` lists the open PRs labelled `one-way` per repo, reads their issue comments (REST, so the
author login keeps its `[bot]`), keeps the notices on each PR's current head, and adds one `info`
news item `SM<PR>-<comment id>` per notice the board has not seen (`self_merge.seen`). The mirror is
display: a notice the workflow would not count (another run, a forged one) still shows, the
workflow alone decides. Every read fails loud: a failed list raises SelfMergeError and the board
keeps its last block.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import timezone
from pathlib import Path

GH_TIMEOUT = 30
NEWS_PREFIX = "SM"
SEEN_KEEP = 200  # the newest seen ids the block remembers
_JUDGE = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "brake-self-merge" / "judge.json").read_text(
        encoding="utf-8"
    )
)
MARKER = _JUDGE["notice_marker"]
AUTHOR = _JUDGE["notice_author"]
ONE_WAY_LABEL = _JUDGE["one_way_label"]
_HEAD = re.compile(_JUDGE["notice_head"], re.MULTILINE)
_CLASS = re.compile(r"· one-way (\S+)\s*$", re.MULTILINE)
_AT = re.compile(r"^merges itself at (\S+)", re.MULTILINE)


class SelfMergeError(Exception):
    """A failed read; board.py prints it and exits 1."""


def run_gh(args):
    try:
        done = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=GH_TIMEOUT, check=False
        )
    except FileNotFoundError:
        raise SelfMergeError("gh not found") from None
    except subprocess.TimeoutExpired:
        raise SelfMergeError(f"gh ran past {GH_TIMEOUT} s") from None
    if done.returncode != 0:
        why = (done.stderr.strip().splitlines() or [f"exit {done.returncode}"])[-1]
        raise SelfMergeError(why)
    return done.stdout


def parse_notice(comment, head):
    """The notice in one REST issue comment on a PR whose head is `head`, or None: the marker, the
    workflow's author and the current head, else it is no notice for the board."""
    body = comment.get("body") or ""
    login = (comment.get("user") or {}).get("login")
    if MARKER not in body or login != AUTHOR:
        return None
    found = _HEAD.search(body)
    if not found or found.group(1) != head:
        return None
    cls, at = _CLASS.search(body), _AT.search(body)
    return {
        "comment": comment.get("id"),
        "class": cls.group(1) if cls else "?",
        "merge_at": at.group(1) if at else "?",
        "created_at": comment.get("created_at"),
    }


def read_notices(repo, gh=run_gh):
    """Every notice on the current head of an open `one-way` PR in `repo`."""
    raw = gh(
        [
            "pr",
            "list",
            "-R",
            repo,
            "--label",
            ONE_WAY_LABEL,
            "--state",
            "open",
            "--json",
            "number,url,headRefOid",
            "--limit",
            "100",
        ]
    )
    try:
        prs = json.loads(raw or "[]")
    except ValueError:
        raise SelfMergeError(f"{repo}: the PR list does not parse") from None
    out = []
    for pr in prs:
        comments_raw = gh(
            ["api", "--paginate", "--slurp", f"repos/{repo}/issues/{pr['number']}/comments"]
        )
        try:
            pages = json.loads(comments_raw or "[]")
        except ValueError:
            raise SelfMergeError(f"{repo}#{pr['number']}: the comments do not parse") from None
        comments = [c for page in pages for c in (page if isinstance(page, list) else [page])]
        for comment in comments:
            notice = parse_notice(comment, pr.get("headRefOid") or "")
            if notice:
                out.append(
                    {**notice, "repo": repo, "number": pr["number"], "url": pr.get("url") or ""}
                )
    return out


def news_item(notice):
    return {
        "id": f"{NEWS_PREFIX}{notice['number']}-{notice['comment']}",
        "kind": "info",
        "title": (
            f"self-merge window: #{notice['number']} · one-way {notice['class']} · merges at "
            f"{notice['merge_at']}"
        ),
        "body": (
            f"{notice['url']} ({notice['repo']}). Stop it with the label `veto` and a comment "
            "`veto: <name> · <reason>`."
        ),
        "ts": notice.get("created_at"),
    }


def merge(board, notices, repos, now):
    """Add one news item per unseen notice (newest first) and write the `self_merge` block;
    returns the items added."""
    old = board.get("self_merge") if isinstance(board.get("self_merge"), dict) else {}
    seen = [s for s in old.get("seen") or [] if isinstance(s, str)]
    news = board.setdefault("news", [])
    known = {n.get("id") for n in news if isinstance(n, dict)} | set(seen)
    added = []
    for notice in sorted(notices, key=lambda n: n.get("created_at") or ""):
        item = news_item(notice)
        if item["id"] in known:
            continue
        news.insert(0, item)
        known.add(item["id"])
        seen.append(item["id"])
        added.append(item)
    board["self_merge"] = {
        "synced": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repos": list(repos),
        "seen": seen[-SEEN_KEEP:],
    }
    return added
