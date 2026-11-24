#!/usr/bin/env python3
"""The one closing step after a merge: `we-worker close <KEY> [--pr <ref>]`.

One writer for "this story's build is over". In the order it runs:

1. **PRs, derived.** The story's PRs come live from GitHub, never from a file: per repo of the
   plan (the checkout's `origin` plus every `**Repo:**` of `docs/plans/<KEY>-story.md` on
   `origin/<default>`, a bare name taking `origin`'s owner) one `gh pr list --search <KEY>` and
   one list of the newest PRs, kept when `flow_report.story_key` finds the key in title or head
   branch (the matcher of the flow report's "PRs per story"). `--pr` names one more by ref; it
   must be merged and carry the key, else close stops before anything. A repo `gh` cannot read
   refuses In Review and is named; nothing is guessed. No merged PR at all stops before anything.
2. **In Review.** Only when no open PR carries the key and every repo of the plan has a merged
   one: `board.py move <KEY> in_review --pr <url>…` in process, its row `by: we-worker close`
   with the session as `caller`; its `carry:` line is this script's last stdout line (the session
   carries it, `references/ticketing.md`). A repo without a merged PR still counts as landed when it
   is a submodule of the checkout (`.gitmodules` on `origin/<default>`) and a merged PR of the
   story moved its gitlink to a commit on that repo's default branch: a two-repo cadence lands the
   submodule by fast-forward, without a PR of its own. Otherwise it names the open PRs and the
   repos without a merged PR, and moves nothing. A key already In Review or later moves nothing again; its
   merged PRs after that row print as follow-ups. Without a crew file there is no transitions
   log: it says so, and the session moves the ticket with its ticketing tool.
   Two holds on top, each moving nothing and recording nothing while the teardown still runs:
   **a living worker on the key** (`holders`: a living session whose name carries the key or
   whose launcher marker names it, or a queued start with a living waiter; the caller's own
   session and, with `--pr`, the worker whose tree has that PR's head branch do not count), since
   only existing PRs are visible and a worker may not have opened its PR yet; it prints
   `held: <names> still work on <KEY>; run close again when they end`, and `claude agents`
   unreadable holds too. **No story plan on `origin/<default>`**, since then nothing names the
   repos that must land (a repo whose PR titles never carry the key stays invisible): the session
   moves the ticket itself (with a crew file by the printed `board.py move`, a hand move in the
   transitions log).
3. **Teardown** (`--keep-worktrees` skips it). A worktree is the story's when its launcher marker
   names the key, or its branch is the head branch of one of the story's PRs or carries the key
   as a whole token. Each one stays, named, when it is the caller's own tree, a living session
   works there (the marker's name in `claude agents --json`, or a session's process with its cwd
   inside), it is dirty (anything but an untracked `WORKER-REPORT.md`), or its branch is
   unmerged (its head neither the head of a merged PR of the story nor in `origin/<default>`);
   when `claude agents` cannot be read every tree stays. Else: other processes with their cwd
   inside get SIGTERM and are named, the tree goes with the repo's command
   (`workers.remove_worktree`, else `git worktree remove`), the local branch is deleted, the remote
   branch too unless an open PR has it as head, and the worker's settings and timer files in the
   launcher's state dir go when no living session holds its name.
4. **Rules news.** Each merged PR of the story that changes `.claude/`, `.weside/` or
   `.github/workflows/` gets its one board news line (`board.py news merged`, `rules_news`).
5. **Epic line.** On the move to In Review (or when the key is In Review and the line is
   missing): one `## Updates Log` line in the story's epic plan, `updated:` set, a leftover mirror
   block dropped (`references/epic-plan.md` § Upkeep after a merge), naming every merged PR of the
   story and `--learning` (default `none`). Under `plans.land: push` it lands from a detached scratch worktree through
   `plan_push.py`; otherwise, or when the push is refused, it prints the file and the line for the
   session to land per `references/plan-commit.md`.

A second call prints what is already done. Exit 0: the story is In Review (or later) and nothing
was refused; 1: something was refused, each line names it; 2: usage error.

`sweep [--apply]`: every worktree whose launcher marker names a key and no living session and
whose branch has a merged PR (`gh pr list --head`); prints the close call per key (with the
`held:` line when another worker still works on the key), and with `--apply` runs it, under the
same two holds. The coordinator's sweep runs it when a starter is gone.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board  # noqa: E402
import crew as crew_mod  # noqa: E402
import epic_state  # noqa: E402
import flow_report  # noqa: E402
import ready_gate  # noqa: E402
import worker_launch as wl  # noqa: E402
import worker_supervisor as ws  # noqa: E402

WRITER = "we-worker close"
GH_TIMEOUT_S = 60
RECENT = 100
PR_FIELDS = "number,state,title,headRefName,headRefOid,url,mergedAt,mergeCommit"
LATER = ("in_review", "in_test", "done")
REPORT = "WORKER-REPORT.md"
MIRROR = re.compile(r"\n?<!-- mirror:start.*?<!-- mirror:end -->\n?", re.DOTALL)

# the seam the tests replace: the living sessions (`claude agents --json`)
sessions = wl.sessions


def _git(cwd: Path, *args: str) -> str | None:
    return wl._git(cwd, *args)


def _run(argv: list[str], cwd: Path, timeout: int = GH_TIMEOUT_S) -> tuple[int, str, str]:
    try:
        done = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, check=False, timeout=timeout
        )
    except FileNotFoundError:
        return 127, "", f"{argv[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"{argv[0]} ran past {timeout} s"
    return done.returncode, done.stdout, done.stderr


def _gh(argv: list[str], cwd: Path) -> tuple[object, str | None]:
    rc, out, err = _run(["gh", *argv], cwd)
    if rc != 0:
        return None, (err.strip().splitlines() or [f"exit {rc}"])[-1]
    try:
        return json.loads(out), None
    except ValueError:
        return None, "gh printed no JSON"


def repo_top(cwd: Path) -> Path | None:
    """The main checkout of the repo `cwd` lies in, also from a linked worktree."""
    common = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common:
        return None
    top = Path(common)
    return top.parent if top.name == ".git" else None


def plan_text(top: Path, base: str, key: str) -> str:
    rel = f"docs/plans/{key}-story.md"
    text = _git(top, "show", f"origin/{base}:{rel}")
    if text is None:
        with contextlib.suppress(OSError):
            text = (top / rel).read_text(encoding="utf-8")
    return text or ""


def has_plan(top: Path, base: str, key: str) -> bool:
    """The story plan lies on `origin/<base>` (a local copy names nothing that must land)."""
    return _git(top, "cat-file", "-e", f"origin/{base}:docs/plans/{key}-story.md") is not None


def plan_repos(own: str, text: str) -> list[str]:
    """`origin` first, then each `**Repo:**` of the plan; a bare name takes `origin`'s owner."""
    repos = [own]
    owner = own.split("/", maxsplit=1)[0]
    for phase in ready_gate.phases(text):
        if not phase.repo:
            continue
        slug = phase.repo.lower() if "/" in phase.repo else f"{owner}/{phase.repo.lower()}"
        if slug not in repos:
            repos.append(slug)
    return repos


def _shape(pr: dict, repo: str) -> dict:
    return {
        "repo": repo,
        "number": pr.get("number"),
        "state": pr.get("state"),
        "title": str(pr.get("title") or ""),
        "branch": str(pr.get("headRefName") or ""),
        "oid": pr.get("headRefOid"),
        "url": pr.get("url") or f"https://github.com/{repo}/pull/{pr.get('number')}",
        "merged": pr.get("mergedAt"),
        "merge": (pr.get("mergeCommit") or {}).get("oid"),
    }


def story_prs(key: str, repos: list[str], top: Path, pattern: str) -> tuple[list, list]:
    """(the story's PRs over `repos`, the repos gh could not read with why)."""
    found: dict = {}
    failed = []
    for repo in repos:
        calls = (
            ["pr", "list", "-R", repo, "--state", "all", "--search", key],
            ["pr", "list", "-R", repo, "--state", "all", "--limit", str(RECENT)],
        )
        for argv in calls:
            data, why = _gh([*argv, "--json", PR_FIELDS], top)
            if why or not isinstance(data, list):
                failed.append(f"{repo} ({why or 'no list'})")
                break
            for pr in data:
                shaped = _shape(pr, repo)
                if flow_report.story_key(shaped, pattern) == key:
                    found[(repo, shaped["number"])] = shaped
    return sorted(found.values(), key=lambda p: (p["repo"], p["number"] or 0)), failed


def view_pr(ref: str, own: str, top: Path) -> tuple[dict | None, str | None]:
    argv = ["pr", "view", *board._gh_argv(ref), "--json", PR_FIELDS]
    data, why = _gh(argv, top)
    if why or not isinstance(data, dict):
        return None, f"PR {ref}: gh pr view failed: {why or 'no object'}"
    repo = flow_report.norm_slug(data.get("url")) or own
    return _shape(data, repo), None


def submodule_paths(top: Path, base: str, own: str) -> dict:
    """{owner/repo: path} of every submodule `.gitmodules` on `origin/<base>` names; a relative
    URL (`../lib.git`) resolves against `own`'s owner."""
    text = _git(
        top, "config", "--blob", f"origin/{base}:.gitmodules", "--get-regexp", r"^submodule\."
    )
    fields: dict = {}
    for line in (text or "").splitlines():
        name, _, value = line.partition(" ")
        sub, _, field = name[len("submodule.") :].rpartition(".")
        fields.setdefault(sub, {})[field] = value.strip()
    return {
        slug: f["path"]
        for f in fields.values()
        if f.get("path") and (slug := flow_report.norm_slug(_absolute(f.get("url"), own)))
    }


def _absolute(url: object, own: str) -> object:
    text = str(url or "")
    if text.startswith("../"):
        return own.split("/", maxsplit=1)[0] + "/" + text[3:]
    return url


def _gitlink(top: Path, commit: str, path: str) -> str | None:
    line = _git(top, "ls-tree", commit, "--", path) or ""
    parts = line.split()
    return parts[2] if len(parts) >= 3 and parts[1] == "commit" else None


def landed_by_gitlink(ctx: dict, repo: str, merged: list) -> str | None:
    """The commit of submodule `repo` a merged PR of the checkout moved its gitlink to, when that
    commit lies on `repo`'s default branch; else None (gh unreadable guesses nothing)."""
    top, own = ctx["top"], ctx["own"]
    path = submodule_paths(top, ctx["base"], own).get(repo)
    if not path:
        return None
    info, why = _gh(["api", f"repos/{repo}"], top)
    default = info.get("default_branch") if isinstance(info, dict) and not why else None
    if not default:
        return None
    for pr in merged:
        if pr["repo"] != own or not pr.get("merge"):
            continue
        new = _gitlink(top, pr["merge"], path)
        if not new or new == _gitlink(top, pr["merge"] + "^", path):
            continue
        cmp, why = _gh(["api", f"repos/{repo}/compare/{default}...{new}"], top)
        if not why and isinstance(cmp, dict) and cmp.get("status") in ("behind", "identical"):
            return new
    return None


def label(pr: dict, own: str) -> str:
    return f"#{pr['number']}" if pr["repo"] == own else f"{pr['repo']}#{pr['number']}"


# --- transition ---------------------------------------------------------------------------------


def _board_state(top: Path):
    try:
        crew_path, crew = crew_mod.find_and_load(top)
    except crew_mod.CrewError as exc:
        return None, None, f"crew file unreadable ({exc})"
    if crew_path is None:
        return None, None, "no crew file"
    return crew, board.StateDir(board.default_board(top)), None


def move_in_review(key: str, urls: list[str], extra: list[str]) -> tuple[int, str, str]:
    """`board.py move <KEY> in_review` in process; (exit, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    argv = ["move", key, "in_review", *[a for u in urls for a in ("--pr", u)], *extra]
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = board.main(argv, writer=WRITER)
    return code, out.getvalue(), err.getvalue()


# --- holders ------------------------------------------------------------------------------------


def _carries(name: object, key: str, pattern: str) -> bool:
    try:
        return wl.check_name(str(name or ""), pattern) == key
    except wl.LaunchError:
        return False


def holders(top: Path, key: str, pattern: str, closed: set) -> list[str]:
    """The workers that still work on `key`: living sessions whose name carries the key or whose
    launcher marker names it, and queued starts with a living waiter. The caller's own session
    and the names in `closed` do not count. `wl.LaunchError` when `claude agents` is unreadable."""
    me = os.environ.get("CLAUDE_CODE_SESSION_ID")
    own = (wl.read_marker(Path.cwd()) or {}).get("name")
    skip = {n for n in (*closed, own) if n}
    marked = {
        m.get("name")
        for m in (wl.read_marker(t.get("path")) or {} for t in ws._worktrees(top))
        if m.get("key") == key
    }
    found = []
    for row in sessions():
        name = row.get("name")
        if not name or (me and row.get("sessionId") == me) or name in skip:
            continue
        if not wl._pid_lives(row.get("pid", "-")):
            continue
        if (name in marked or _carries(name, key, pattern)) and name not in found:
            found.append(str(name))
    for doc in ws.queued(ws.state_dir()):
        name = doc["name"]
        if name in skip or name in found or not ws.waiter_lives(doc):
            continue
        if _carries(name, key, pattern):
            found.append(f"{name} (queued)")
    return found


def held_line(key: str, names: list[str]) -> str:
    return f"held: {', '.join(names)} still work on {key}; run close again when they end"


def closed_names(top: Path, given: dict | None) -> set:
    """The marker name of the tree whose branch is the head of the `--pr` PR: the worker being
    closed."""
    if not given:
        return set()
    return {
        name
        for t in ws._worktrees(top)
        if t.get("branch") == given["branch"]
        and (name := (wl.read_marker(t.get("path")) or {}).get("name"))
    }


# --- teardown -----------------------------------------------------------------------------------


def procs_in(path: Path) -> list[tuple[int, str]]:
    """(pid, command) of every process whose cwd lies in `path`, this one and its parent left out."""
    mine = {os.getpid(), os.getppid()}
    root = str(path.resolve())
    found = []
    proc = Path("/proc")
    if proc.is_dir():
        for entry in proc.iterdir():
            if not entry.name.isdigit() or int(entry.name) in mine:
                continue
            try:
                cwd = os.readlink(entry / "cwd").removesuffix(" (deleted)")
                comm = (entry / "comm").read_text().strip()
            except OSError:
                continue
            if cwd == root or cwd.startswith(root + "/"):
                found.append((int(entry.name), comm))
        return found
    rc, out, _ = _run(["lsof", "-a", "-d", "cwd", "-Fpc", "+D", root], path)
    pid = None
    for line in out.splitlines() if rc in (0, 1) else []:
        if line.startswith("p"):
            pid = int(line[1:])
        elif line.startswith("c") and pid is not None and pid not in mine:
            found.append((pid, line[1:]))
    return found


def _token(key: str, text: str) -> bool:
    return re.search(r"(?<![A-Za-z0-9-])" + re.escape(key) + r"(?![0-9])", text, re.I) is not None


def trees_of(top: Path, key: str, branches: set) -> list[dict]:
    out = []
    for tree in ws._worktrees(top):
        path, branch = tree.get("path"), tree.get("branch") or ""
        marker = wl.read_marker(path) or {}
        if marker.get("key") == key or branch in branches or _token(key, branch):
            out.append({"path": path, "branch": branch, "marker": marker})
    return out


def _dirty(path: Path) -> list[str]:
    rc, status, _err = _run(["git", "status", "--porcelain"], path)
    if rc != 0:
        return ["(git status failed)"]
    return [ln.strip() for ln in status.splitlines() if ln.strip() and ln != f"?? {REPORT}"]


def _merged(top: Path, branch: str, base: str, merged_oids: set) -> bool:
    head = _git(top, "rev-parse", f"refs/heads/{branch}")
    if not head:
        return False
    if head in merged_oids:
        return True
    return _git(top, "merge-base", "--is-ancestor", head, f"origin/{base}") is not None


def _keep_reason(top, tree, living, session_pids, procs, base, merged_oids) -> str | None:
    path, branch, name = Path(tree["path"]), tree["branch"], tree["marker"].get("name")
    here = Path.cwd().resolve()
    if here == path.resolve() or path.resolve() in here.parents:
        return "the caller stands in it; run close from the main checkout"
    if name and name in living:
        return f"{name} still runs there"
    if any(pid in session_pids for pid, _ in procs):
        return "a session works there"
    dirty = _dirty(path)
    if dirty:
        return "uncommitted changes: " + "; ".join(dirty[:3])
    if not branch or not _merged(top, branch, base, merged_oids):
        return f"{branch or 'detached HEAD'} is not merged (commits after the merged head?)"
    return None


def _remove_tree(
    top: Path, tree: dict, procs: list, living: set, out: list, base: str, merged_oids: set
) -> bool:
    path, branch, name = Path(tree["path"]), tree["branch"], tree["marker"].get("name")
    ended = []
    for pid, comm in procs:
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)
            ended.append(f"{pid} {comm}")
    tokens = shlex.split(wl.remove_command(top, str(path)))
    rc, _out, err = _run(tokens, top, wl.TREE_TIMEOUT_S)
    if rc != 0:
        out.append(f"keep {path}: {' '.join(tokens[:3])} failed: {err.strip()[-200:]}")
        return False
    _git(top, "worktree", "prune")
    out.append(f"removed {path}" + (f"; ended {', '.join(ended)}" if ended else ""))
    if _git(top, "branch", "-D", branch) is not None:
        out.append(f"deleted branch {branch}")
    out.append(remote_branch(top, branch, base, merged_oids))
    if name and name not in living:
        gone = ws._remove_files(ws.state_dir(), name)
        if gone:
            out.append(f"removed {', '.join(gone)}")
    return True


def teardown(top: Path, key: str, prs: list, base: str, out: list) -> bool:
    """Remove the story's trees, branches and worker files; False when one stayed."""
    merged_oids = {p["oid"] for p in prs if p["state"] == "MERGED" and p["oid"]}
    own_branches = {p["branch"] for p in prs if p["repo"] == own_slug(top)}
    trees = trees_of(top, key, own_branches)
    if not trees:
        out.append("trees: none left")
        return True
    try:
        rows = sessions()
    except wl.LaunchError as exc:
        out += [
            f"keep {t['path']}: claude agents unreadable ({exc}); nothing judged dead"
            for t in trees
        ]
        return False
    living = {
        str(r.get("name")) for r in rows if r.get("name") and wl._pid_lives(r.get("pid", "-"))
    }
    session_pids = {int(r["pid"]) for r in rows if str(r.get("pid", "")).isdigit()}
    ok = True
    for tree in trees:
        procs = procs_in(Path(tree["path"]))
        why = _keep_reason(top, tree, living, session_pids, procs, base, merged_oids)
        if why:
            out.append(f"keep {tree['path']}: {why}")
            ok = False
        elif not _remove_tree(top, tree, procs, living, out, base, merged_oids):
            ok = False
    return ok


def remote_branch(top: Path, branch: str, base: str, merged_oids: set) -> str:
    """Delete origin/<branch> when no PR is open on it and its head is in the merged history.

    A commit pushed to the branch after the merge is in no PR: deleting the branch would lose it.
    The delete carries the head it judged as a lease, so a push between the check and the delete
    makes the delete fail instead of taking that push along.
    """
    data, why = _gh(["pr", "list", "--head", branch, "--state", "open", "--json", "url"], top)
    if why or not isinstance(data, list):
        return f"keep origin/{branch}: open PRs unreadable ({why})"
    if data:
        return f"keep origin/{branch}: open PR {data[0].get('url')}"
    rc, out, err = _run(["git", "ls-remote", "origin", f"refs/heads/{branch}"], top)
    if rc != 0:
        why = (err.strip().splitlines() or [f"exit {rc}"])[-1]
        return f"keep origin/{branch}: remote head unreadable ({why})"
    head = out.split()[0] if out.strip() else ""  # empty: the branch is gone already
    after = _after_merge(top, branch, base, merged_oids, head) if head else None
    if after:
        return f"keep origin/{branch}: {after} after the merged head ({head[:7]})"
    if head:
        lease = f"--force-with-lease=refs/heads/{branch}:{head}"
        rc, _o, err = _run(["git", "push", "-q", "origin", "--delete", lease, branch], top)
        if rc != 0 and "remote ref does not exist" not in err:
            return f"keep origin/{branch}: push --delete failed: {err.strip()[-200:]}"
    return f"deleted origin/{branch}"


def _after_merge(top: Path, branch: str, base: str, merged_oids: set, head: str) -> str | None:
    """None when the remote head `head` is merged, else "<n> commit(s)" pushed after the merge."""
    if head in merged_oids:
        return None
    _run(["git", "fetch", "-q", "origin", base, f"refs/heads/{branch}"], top)
    if _git(top, "merge-base", "--is-ancestor", head, f"origin/{base}") is not None:
        return None
    known = [o for o in merged_oids if _git(top, "cat-file", "-e", f"{o}^{{commit}}") is not None]
    count = _git(top, "rev-list", "--count", head, "--not", f"origin/{base}", *known)
    n = count.strip() if count and count.strip().isdigit() else "?"
    return f"{n} commit(s)"


def own_slug(top: Path) -> str:
    return flow_report.norm_slug(_git(top, "remote", "get-url", "origin")) or ""


# --- epic line ----------------------------------------------------------------------------------


def epic_file(top: Path, base: str, story: str) -> tuple[str | None, str | None]:
    """(path relative to the repo, text on origin/<base>) of the story's epic plan."""
    epic = str(epic_state.frontmatter(story).get("epic") or "").strip()
    if not epic or epic == "null":
        return None, None
    names = _git(top, "ls-tree", "--name-only", f"origin/{base}", "docs/plans/") or ""
    for rel in names.splitlines():
        if not rel.endswith("-epic.md"):
            continue
        text = _git(top, "show", f"origin/{base}:{rel}") or ""
        meta = epic_state.frontmatter(text)
        if Path(rel).stem == epic or str(meta.get("ticket") or "") == epic:
            return rel, text
    return None, None


def epic_line(key, merged, own, text, last, today, learning="none") -> str:
    names = ", ".join(label(p, own) for p in merged)
    parts = [f"{key} merged ({'PRs' if len(merged) > 1 else 'PR'} {names})"]
    line = epic_state.finish_line(text, last, today)
    if line is not None:
        parts.append(epic_state.line_summary(line))
    parts.append(learning or "none")
    return f"- {today.isoformat()} — " + "; ".join(parts)


def with_line(text: str, entry: str, today: dt.date) -> str:
    """The epic text with `entry` in its Updates Log (newest-first logs get it on top),
    `updated:` set and a mirror block dropped."""
    text = MIRROR.sub("\n", text)
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is not None:
            hit = next((i for i in range(1, end) if lines[i].startswith("updated:")), None)
            if hit is None:
                lines.insert(end, f"updated: {today.isoformat()}")
            else:
                lines[hit] = f"updated: {today.isoformat()}"
    start = next((i for i, ln in enumerate(lines) if ln.strip() == "## Updates Log"), None)
    if start is None:
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join([*lines, "", "## Updates Log", "", entry, ""])
    stop = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines)
    )
    entries = [i for i in range(start + 1, stop) if epic_state.ENTRY.match(lines[i])]
    dates = [epic_state.ENTRY.match(lines[i]).group(1) for i in entries]
    if len(dates) >= 2 and dates[0] > dates[-1]:
        lines.insert(entries[0], entry)
    elif entries:
        at = entries[-1] + 1
        while at < stop and lines[at].startswith("  ") and lines[at].strip():
            at += 1
        lines.insert(at, entry)
    else:
        lines.insert(start + 1, "")
        lines.insert(start + 2, entry)
    return "\n".join(lines)


def land_mode(top: Path, base: str) -> str:
    raw = _git(top, "show", f"origin/{base}:.weside/config.json")
    try:
        return str(((json.loads(raw or "{}").get("plans")) or {}).get("land") or "pr")
    except (ValueError, AttributeError):
        return "pr"


def write_epic(top, base, key, merged, own, last, today, out, learning="none") -> bool:
    story = plan_text(top, base, key)
    rel, text = epic_file(top, base, story)
    if rel is None:
        out.append("epic: none (the story names no epic plan on the default branch)")
        return True
    if any(f"{key} merged" in e for _d, e in epic_state.updates_log(text)):
        out.append(f"epic: the line is already in {rel}")
        return True
    entry = epic_line(key, merged, own, text, last, today, learning)
    if land_mode(top, base) != "push":
        out.append(
            f"epic: add to {rel} § Updates Log and set updated: {today.isoformat()}, then land per "
            f"references/plan-commit.md: {entry}"
        )
        return True
    scratch = Path(tempfile.mkdtemp(prefix="we-close-")) / "tree"
    try:
        if (
            _git(
                top,
                "-c",
                "core.hooksPath=/dev/null",
                "worktree",
                "add",
                "--detach",
                str(scratch),
                f"origin/{base}",
            )
            is None
        ):
            out.append(f"epic: scratch tree failed; land per references/plan-commit.md: {entry}")
            return False
        (scratch / rel).write_text(with_line(text, entry, today).rstrip("\n") + "\n", "utf-8")
        rc, _o, err = _run(
            [
                "git",
                "commit",
                "-q",
                "-m",
                f"docs({key}): epic updates log after the merge",
                "--",
                rel,
            ],
            scratch,
        )
        if rc == 0:
            rc, _out, err = _run([sys.executable, str(HERE / "plan_push.py")], scratch, 300)
        if rc != 0:
            why = (err.strip().splitlines() or [f"exit {rc}"])[-1]
            out.append(f"epic: not landed ({why}); land per references/plan-commit.md: {entry}")
            return False
        out.append(f"epic: landed in {rel}: {entry}")
        return True
    finally:
        _git(top, "worktree", "remove", "--force", str(scratch))
        _git(top, "worktree", "prune")


# --- close --------------------------------------------------------------------------------------


class CloseError(Exception):
    """close stops before anything: the message for stderr and the exit code."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def _context(key: str) -> dict:
    top = repo_top(Path.cwd())
    if top is None:
        raise CloseError("we-worker close: not inside a git repository", 2)
    own = own_slug(top)
    if not own:
        raise CloseError("we-worker close: the checkout has no GitHub origin", 2)
    crew, state, no_board = _board_state(top)
    pattern = ((crew or {}).get("naming") or {}).get("key") or crew_mod.DEFAULTS["naming"]["key"]
    if not re.fullmatch(pattern, key):
        raise CloseError(f"we-worker close: {key!r} does not match naming.key {pattern}", 2)
    if _git(top, "fetch", "-q", "origin") is None:
        print(
            "we-worker close: warning: git fetch origin failed; origin may be stale",
            file=sys.stderr,
        )
    base = wl.default_branch(top)
    return {
        "top": top,
        "own": own,
        "state": state,
        "no_board": no_board,
        "pattern": pattern,
        "base": base,
        "repos": plan_repos(own, plan_text(top, base, key)),
        "plan": has_plan(top, base, key),
    }


def _given(key: str, ref: str, ctx: dict) -> dict:
    given, why = view_pr(ref, ctx["own"], ctx["top"])
    if why:
        raise CloseError(f"we-worker close {key}: refused: {why}")
    if given["state"] != "MERGED":
        raise CloseError(
            f"we-worker close {key}: refused: PR {ref} is {given['state']}, not merged; "
            "nothing is torn down"
        )
    if flow_report.story_key(given, ctx["pattern"]) != key:
        raise CloseError(
            f"we-worker close {key}: refused: PR {ref} does not carry {key} in its title "
            "or head branch"
        )
    return given


def _hold(
    key: str, ctx: dict, given: dict | None, urls: list[str], fast: bool = False
) -> str | None:
    """Why In Review waits although every PR the key shows is merged, or None. A fast-lane story
    (`fast`: its row came `via: fast`) has no plan by definition and one PR in one repo: the
    merged PR is all that must land."""
    try:
        names = holders(ctx["top"], key, ctx["pattern"], closed_names(ctx["top"], given))
    except wl.LaunchError as exc:
        return f"held: claude agents unreadable ({exc}); no worker on {key} judged ended"
    if names:
        return held_line(key, names)
    if not ctx["plan"] and not fast:
        how = (
            f"once every repo landed: python3 {HERE / 'board.py'} move {key} in_review "
            + " ".join(f"--pr {u}" for u in urls)
            + " (a hand move in the transitions log)"
            if ctx["state"] is not None
            else "with your ticketing tool (references/ticketing.md)"
        )
        return (
            f"held: no story plan for {key} on origin/{ctx['base']} names the repos that must "
            f"land; move {key} to In Review yourself {how}"
        )
    return None


def _in_review(
    key: str, ctx: dict, prs: list, unreadable: list, extra: list, given: dict | None = None
) -> dict:
    """The move to In Review, or why not: {out, refused, carry, closed, last, held}."""
    own, state = ctx["own"], ctx["state"]
    merged = [p for p in prs if p["state"] == "MERGED"]
    opened = [p["url"] for p in prs if p["state"] == "OPEN"]
    missing = [r for r in ctx["repos"] if not any(p["repo"] == r for p in merged)]
    last = state.last_rows() if state else {}
    was = (last.get(key) or {}).get("to")
    res = {"out": [], "refused": [], "carry": [], "closed": False, "last": last, "held": None}
    for repo in list(missing):
        oid = landed_by_gitlink(ctx, repo, merged)
        if oid:
            missing.remove(repo)
            res["out"].append(f"in_review: {repo} landed by fast-forward at {oid[:7]} (gitlink)")
    if unreadable:
        res["refused"].append(
            f"in_review: gh unreadable for {', '.join(unreadable)}; nothing guessed"
        )
    if opened:
        res["refused"].append("in_review: open PR carries the key: " + ", ".join(opened))
    if missing:
        res["refused"].append("in_review: no merged PR in " + ", ".join(missing))
    if res["refused"]:
        res["out"].append(f"in_review: {key} stays {was or 'unmoved'}")
        return res
    res["closed"] = True
    if was in LATER:
        row_prs = set((last.get(key) or {}).get("pr") or [])
        after = [label(p, own) for p in merged if p["url"] not in row_prs]
        res["out"].append(
            f"in_review: {key} is {was} already"
            + (f"; follow-up PRs: {', '.join(after)}" if after else "")
        )
        return res
    fast = (last.get(key) or {}).get("via") == "fast"
    res["held"] = _hold(key, ctx, given, [p["url"] for p in merged], fast)
    if res["held"]:
        res["closed"] = False
        res["out"] += [res["held"], f"in_review: {key} stays {was or 'unmoved'}"]
        return res
    if state is None:
        res["out"].append(
            f"in_review: {ctx['no_board']}, no transitions log: move {key} to In "
            "Review with your ticketing tool (references/ticketing.md)"
        )
        return res
    code, text, err = move_in_review(key, [p["url"] for p in merged], extra)
    if code != 0:
        res["closed"] = False
        res["refused"] += [ln for ln in err.strip().splitlines() if ln] or [
            f"board.py exit {code}"
        ]
        return res
    rows = [ln for ln in text.splitlines() if ln.startswith("{")]
    res["out"].append(f"in_review: {key} moved" + (f" {rows[-1]}" if rows else ""))
    res["carry"] = [ln for ln in text.splitlines() if ln.startswith("carry:")]
    sys.stderr.write("".join(ln + "\n" for ln in err.splitlines() if ln))
    res["last"] = state.last_rows()
    return res


def rules_news(ctx: dict, merged: list) -> list[str]:
    """`board.rules_news` per merged PR: a rule change gets its one board news line; a line per
    item added or per read that failed."""
    if ctx["state"] is None:
        return []
    out = []
    for pr in merged:
        outcome, what = board.rules_news(ctx["state"], pr["url"], board._now())
        if outcome == "added":
            out.append(f"news: {what['id']} {what['title']}")
        elif outcome == "failed":
            out.append(f"news: {pr['url']} unread for the rules line ({what})")
    return out


def close(key, pr_ref, keep, extra, today, learning="none") -> int:
    try:
        ctx = _context(key)
        prs, unreadable = story_prs(key, ctx["repos"], ctx["top"], ctx["pattern"])
        given = None
        if pr_ref:
            given = _given(key, pr_ref, ctx)
            prs = [*[p for p in prs if p["url"] != given["url"]], given]
        merged = [p for p in prs if p["state"] == "MERGED"]
        if not merged:
            why = f"; gh unreadable for {', '.join(unreadable)}" if unreadable else ""
            raise CloseError(f"we-worker close {key}: refused: no merged PR carries {key}{why}")
    except CloseError as stop:
        print(str(stop), file=sys.stderr)
        return stop.code
    top, own = ctx["top"], ctx["own"]
    res = _in_review(key, ctx, prs, unreadable, extra, given)
    out = ["prs: " + ", ".join(f"{label(p, own)} {p['state'].lower()}" for p in prs), *res["out"]]
    out += rules_news(ctx, merged)
    tidy = True if keep else teardown(top, key, prs, ctx["base"], out)
    epic_ok = True
    if res["closed"]:
        states = {k: r.get("to") for k, r in res["last"].items()}
        epic_ok = write_epic(top, ctx["base"], key, merged, own, states, today, out, learning)
    print("\n".join([*out, *[f"refused: {line}" for line in res["refused"]]]))
    ok = not res["refused"] and not res["held"] and tidy and epic_ok
    print(f"close {key}: {'done' if ok else 'open items above'}")
    for line in res["carry"]:
        print(line)
    return 0 if ok else 1


def sweep(apply: bool, today: dt.date) -> int:
    top = repo_top(Path.cwd())
    if top is None:
        print("we-worker close --sweep: not inside a git repository", file=sys.stderr)
        return 2
    try:
        rows = sessions()
    except wl.LaunchError as exc:
        print(
            f"we-worker close --sweep: claude agents unreadable ({exc}); nothing judged dead",
            file=sys.stderr,
        )
        return 1
    living = {
        str(r.get("name")) for r in rows if r.get("name") and wl._pid_lives(r.get("pid", "-"))
    }
    todo = {}
    for tree in ws._worktrees(top):
        marker = wl.read_marker(tree.get("path")) or {}
        key, branch = marker.get("key"), tree.get("branch")
        if not key or not branch or marker.get("name") in living:
            continue
        data, why = _gh(
            ["pr", "list", "--head", branch, "--state", "merged", "--json", "url"], top
        )
        if why or not data:
            continue
        todo.setdefault(key, data[0]["url"])
        print(f"close {key} --pr {data[0]['url']} ({tree['path']}, {marker.get('name')} gone)")
        with contextlib.suppress(wl.LaunchError):
            names = holders(top, key, wl.key_pattern(top), set())
            if names:
                print(f"  {held_line(key, names)}")
    if not todo:
        print("sweep: no merged PR with a marker left")
        return 0
    if not apply:
        return 0
    code = 0
    for key, url in todo.items():
        code = max(code, close(key, url, False, [], today))
    return code


def main(argv: list[str] | None = None, today: dt.date | None = None) -> int:
    parser = argparse.ArgumentParser(prog="we-worker close", description=__doc__.split("\n")[0])
    parser.add_argument("key", nargs="?")
    parser.add_argument("--pr", help="a merged PR of the story (number, <owner>/<repo>#n or URL)")
    parser.add_argument("--keep-worktrees", action="store_true", help="skip the teardown")
    parser.add_argument("--learning", default="none", help="the epic line's learning (one line)")
    parser.add_argument("--input", help="board.py's ticket reads (several humans), passed through")
    parser.add_argument("--sweep", action="store_true", help="list merged PRs whose marker lies")
    parser.add_argument("--apply", action="store_true", help="with --sweep: close each one")
    args = parser.parse_args(argv)
    today = today or dt.datetime.now(dt.timezone.utc).date()
    if args.sweep:
        if args.key:
            parser.error("--sweep takes no key")
        return sweep(args.apply, today)
    if not args.key or args.apply:
        parser.error("close needs <KEY> (--apply belongs to --sweep)")
    extra = ["--input", args.input] if args.input else []
    return close(args.key, args.pr, args.keep_worktrees, extra, today, args.learning)


if __name__ == "__main__":
    sys.exit(main())
