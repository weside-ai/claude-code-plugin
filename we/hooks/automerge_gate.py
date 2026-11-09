#!/usr/bin/env python3
"""PreToolUse hook: the session-side merge brake. Every merge and every auto-merge arm of a PR passes
here first: the freeze flag, the PR's risk class, the T2 panel verdict, the security card verdict,
the Codex verdict on the head and the pre-merge receipt.

A brake against slips, not a boundary ("Bremse gegen Versehen, keine Grenze"): it sees only
Claude Code's Bash tool calls, and a session can work around it — the bot token used directly
(`curl`, a `gh` binary off `PATH`), a script file or `python3 -c`, a Codex run (no Claude hooks),
an edit to the hook in the plugin cache. The freeze flag and the panel verdict are local files any
session can write or delete, the card verdict a PR comment any crew member or the bot can post: process signals,
not locks. A hook that Claude Code kills on its `hooks.json` timeout is a non-blocking error, so
the command runs (allow); `BUDGET_SECONDS` keeps every call below it. The boundary is the
repository's ruleset (required checks, code owners, no bypass actor for the bot) and the owner's
own merge.

Call forms, every one in a compound command (`gh` in command position):

  * `gh pr merge` with any flags (`--disable-auto` is always allowed; `--auto` is an arm);
  * `gh api` on `repos/<o>/<r>/pulls/<N>/merge` with any method but GET (a merge);
  * `gh api graphql` whose command text, or a `query=@file`/`--input` file, names
    `mergePullRequest` (a merge) or `enablePullRequestAutoMerge` (an arm); the PR node id is
    resolved to its number through `gh api graphql` `node(id:)`, and an unresolvable one is refused.

Refusals, in this order (the first one wins):

  1. In any worker every merge and arm is refused: merging is the Lead's call in the main session
     (`references/worker-dispatch.md` § Dev-only worker contract). A worker is a subagent
     (`agent_id` in the payload) or a process worker (the marker of `scripts/worker_launch.py`).
  2. Freeze: while the freeze flag stands beside the board file (`board_freeze.flag_path`), every
     merge and arm in a repo the flag names (`repos`, `*` for all) is refused, naming its
     reason; an unreadable flag counts as standing.
  3. One-way: the PR's class (`pr_class`) is `T2 one-way <class>`; no session merges or arms it,
     whatever a command or a chat quote says, a green panel included. The brake's core
     (`risk_paths.CORE`) only the owner (`human.name` in the crew) merges, by hand; every other
     one-way class merges itself through the repo's self-merge window (2 h after a green T2 panel
     comment on its head, `lens_verdict.py post`, once the owner got the push line; a `veto` label
     stops it), so the refusal points there. Where `origin/main` carries an approve gate
     (`.github/workflows/one-way-gate.yml` and a `brake_self_merge.py` that knows the state
     `approved`), the owner's GitHub approve on the head is the go for both, and the refusal says
     so: the session asks for an approve, not a merge, and does nothing after it.
  4. T2 two-way without a green panel: when the plugin ships `scripts/lens_verdict.py`, its
     `check(root, "t2-pr<N>")` must be green (missing or red refuses; the verdict file carries no
     skip field). Without the module the check is off with one stderr line. The panel verdict is a
     process signal, not a boundary: any session can write that file, so it never lifts 3.
  5. T2 two-way with a card hit and no security card PASS on the head: a classifier hit line
     (line 3 on, `<file>\t<section>: <why>`) in `trust-loosening`, `money-path` or `brake-review`
     needs, besides the green panel, a PR comment of the security card worker
     (`references/worker-dispatch.md` § Card worker) in this form:

         <!-- security-card-review -->
         ## Security card review — #<N> @ `<head sha, at least 7 hex chars>`
         **Overall: PASS**

     Only comments by a repo OWNER, MEMBER or COLLABORATOR or by an installed GitHub App (user
     type `Bot`, how a worker's bot token posts) count, read through the REST issue comments;
     among them only those whose `@ <sha>` is a prefix of the PR's current head; the last of those
     decides (`PASS` lets it go, any other `Overall:` word refuses). None on the head (missing, or
     only on an older head) refuses, and so does a comment read that fails. 4 runs first, so this
     check holds only once the panel is green or the panel check is off.
  6. An arm before the Codex review on the PR's head has a verdict (`review.codex_check` in
     `.weside/config.json`, default `Codex Review`), unless the base branch requires that check
     itself (rulesets or classic protection); a repo whose workflows name no such job has none.
  7. An arm while the PR body carries a `receipt red` line (outside fenced code) in a repo whose
     `.weside/config.json` names `verification.pre_merge_receipt`.

The class (`pr_class`) comes only from `origin/main`: the crew file `.weside/crew.json` is read as
`origin/main`'s blob (never the local file), its `risk.command` blob (from `risk.rules_from`,
default `origin/main`) is written to a temp file and run on `merge-base..<PR head>` in a
no-checkout worktree of the head; without a `risk.command`, the plugin's `scripts/risk_paths.py`
(`origin/main`'s blob of `we/scripts/risk_paths.py` when the repo carries it) reads `origin/main`'s
`.weside/risk-paths`; with neither the class is `T0`, decided offline, unless `origin/main` carries a
crew file: a crew without rules refuses every merge and arm (a brake that cannot judge must not
stay silently open). A `.weside/risk-paths` without a one-way section brakes nothing on purpose; the
allowed merge then carries one `systemMessage` line saying so. Line 1 must match
`^T[02]( one-way \\S+)?$`.

Before classifying, the hook fetches the rules branch (`origin/main`), so a stale local ref neither
misses a new rule nor drags main's own commits into the diff.

Fail closed on the class, the freeze, the panel and the card verdict: a classifier failure, a `gh`
or fetch failure while classifying, a command that does not parse as shell words, a GraphQL query
piped in from stdin or from an unreadable file, and a repo that uses rules but has no `origin/main` all refuse
with the reason. Where the command starts in a checkout that uses rules (a crew file, or
`.weside/risk-paths` in the tree or on `origin/main`), a PR in a repo other than the local
checkout's (`-R`, a URL selector, an origin that is no plain github.com URL) and a `cd` the hook
cannot resolve (`$(…)`, an unset variable; `~` and `$VAR` are expanded) refuse too; without rules
those merges go on unclassed, as before the class brake. The freeze flag counts beside the board
file of `board_freeze.watched_board_files` (the crew's `board.file`, else `board.json` in the
crew's state directory, `crew.state_dir`) and only
for the repos the flag names (`board_freeze.covers`: `*`, no list or a repo the hook cannot name
count as covered). Any exception while checking a
command that looks like a merge refuses it, and so does a failed import of the hook's own modules
(`_import_failure`). A query piped in from stdin counts as seen only when an `echo`/`printf` right
before that `gh` (`… | gh api graphql --input -`) spells a read-only query and the call redirects
nothing (`_piped_read_only`); a query elsewhere in the command, a `cat` or a `<` stay unseen. The whole hook
shares one budget of `BUDGET_SECONDS` (540 s), below the hook's 600 s `timeout` in `hooks.json`:
each `git`, `gh` and classifier call has its own timeout, cut to what is left of it (`_left`); a call cut short
fails, which refuses on the class path and lets the arm through on the Codex wait. Fail open on the Codex wait and the
receipt read (6, 7) as before: Codex is advisory, an arm is reversible with `--disable-auto`.
Pinned by `test_automerge_gate.py`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

# Defined before the module imports, so a failed import can still judge the command.
_LOOKS_LIKE_MERGE = re.compile(
    r"\bgh\b.*(\bpr\s+merge\b|/merge\b|mergePullRequest|enablePullRequestAutoMerge|graphql)",
    re.DOTALL,
)


def _import_failure(exc: BaseException) -> None:
    """Run as a hook whose imports failed: refuse a merge-like command, let every other one go."""
    try:
        payload = json.load(sys.stdin)
        command = str(((payload or {}).get("tool_input") or {}).get("command", ""))
    except Exception:
        return
    if not _LOOKS_LIKE_MERGE.search(command):
        return
    reason = (
        f"Merge refused: the merge gate cannot load its modules ({type(exc).__name__}: {exc}). "
        "Fix the plugin install (`claude plugins update we@weside-ai`) or run the merge by hand."
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


try:
    import board_freeze
    import crew
    import risk_paths
    import verification_gate as vg
    from worker_launch import worker_marker
except Exception as _exc:  # a brake: a broken import refuses merges instead of opening them
    if __name__ == "__main__":
        _import_failure(_exc)
        sys.exit(0)
    raise

DEFAULT_CHECK = "Codex Review"
# `gh pr merge` flags that take a value — their value is not the PR selector.
_VALUED = frozenset(
    {
        "-b",
        "--body",
        "-F",
        "--body-file",
        "-t",
        "--subject",
        "-A",
        "--author-email",
        "--match-head-commit",
        "-R",
        "--repo",
    }
)
_NO_VERDICT = frozenset({"cancelled", "timed_out", "action_required", "stale", "startup_failure"})
_VERDICT = re.compile(r"VERDICT:([A-Z]+)")
# The Codex workflow's own comment marker: other reviewers post `VERDICT:` markers too.
_MARKER = "<!-- codex-review -->"
_RECEIPT_RED = re.compile(r"^receipt red\b")
_FENCE = re.compile(r"^(`{3,}|~{3,})")
_API_MERGE = re.compile(r"(?:^|/)repos/([^/\s]+/[^/\s]+)/pulls/(\d+)/merge/?(?:\?|$)")
_NODE_ID = re.compile(r"\bPR_[A-Za-z0-9_-]+")
_ONE_WAY_SECTION = re.compile(
    r"^\s*\[\s*(" + "|".join(re.escape(c) for c in risk_paths.ONE_WAY) + r")\s*\]", re.MULTILINE
)
_CLASS_LINE = re.compile(r"^T[02]( one-way (\S+))?$")
_SLUG = re.compile(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$")
_URL_SLUG = re.compile(r"github\.com/([^/]+/[^/]+)/pull/(\d+)")
# The two-way sections whose hit needs a security card verdict besides the panel (brake stage 2).
CARD_SECTIONS = risk_paths.CARD
_CARD_HIT = re.compile(r"(?:^|\t)(" + "|".join(CARD_SECTIONS) + r"):")
CARD_MARKER = "<!-- security-card-review -->"
_CARD_HEAD = re.compile(r"^#+\s*Security card review\b.*?@\s*`?([0-9a-f]{7,40})`?", re.MULTILINE)
_CARD_OVERALL = re.compile(r"\bOverall:\**\s*([A-Z]+)")
_CARD_AUTHORS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
RULES_FROM = "origin/main"
# The whole hook stays inside this many seconds, below hooks.json's 600: a hook Claude Code kills
# on its timeout is a non-blocking error, and the command would run unbraked.
BUDGET_SECONDS = 540
_DEADLINE = [time.monotonic() + BUDGET_SECONDS]
# Lines the session must see on an allowed merge (a deliberately empty brake says so, once per
# call); `main` prints them as `systemMessage`. Reset by `_refusal`.
NOTICES: list[str] = []


def _left(wanted: float) -> float:
    """`wanted` seconds, cut to what is left of the hook's budget (at least 0.1)."""
    return max(0.1, min(wanted, _DEADLINE[0] - time.monotonic()))


CLASSIFY_TIMEOUT = 60
DEFAULT_BOARD = board_freeze.DEFAULT_BOARD
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
LENS_VERDICT = SCRIPTS / "lens_verdict.py"
RISK_PATHS = SCRIPTS / "risk_paths.py"


def _gh(args: list[str], cwd: str | None) -> str | None:
    """stdout of `gh <args>`, or None on any failure (the caller fails open)."""
    try:
        out = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=_left(20),
            check=False,
            cwd=cwd or None,
        )
    except Exception:
        return None
    return out.stdout if out.returncode == 0 else None


@dataclass
class MergeCall:
    """One merge or arm in a command: where its `gh` sits, the PR it names and what it does."""

    at: int
    form: str  # "pr merge" | "api merge" | "graphql"
    arm: bool
    disarm: bool = False
    selector: str | None = None
    repo: str | None = None
    number: int | None = None
    unresolved: str | None = None  # why the PR behind the call is unknown (refused)
    args: list[str] = field(default_factory=list)


def _gh_at(argv: list[str], i: int) -> tuple[str | None, int] | None:
    """(global `-R` value, index after the global flags) for a `gh` in command position."""
    tok = argv[i]
    bare = tok.lstrip("({$")
    if bare != "gh" and not bare.endswith("/gh"):
        return None
    if tok == bare and not vg._starts_a_command(argv, i):
        return None
    repo, j = None, i + 1
    while j < len(argv) and argv[j].startswith("-"):
        if argv[j] in ("-R", "--repo") and j + 1 < len(argv):
            repo, j = argv[j + 1], j + 2
        else:
            if argv[j].startswith("--repo="):
                repo = argv[j].split("=", 1)[1]
            j += 1
    return repo, j


def _api_method(args: list[str]) -> str:
    """The HTTP method `gh api` uses: `-X`/`--method`, else POST with fields, else GET."""
    for k, a in enumerate(args):
        if a in ("-X", "--method") and k + 1 < len(args):
            return args[k + 1].upper()
        if a.startswith("--method="):
            return a.split("=", 1)[1].upper()
        if a.startswith("-X") and len(a) > 2:
            return a[2:].upper()
    fields = ("-f", "-F", "--field", "--raw-field", "--input")
    return "POST" if any(a in fields or a.startswith(fields) for a in args) else "GET"


# A read-only GraphQL document: names a query (`"query":"query {…"`, `"query":"{…"`, `query {`), no mutation.
_READ_ONLY_DOC = re.compile(
    r"^(?!.*\bmutation\b)(?=.*(\"query\"\s*:\s*\"\s*(query\b|\{)|\bquery\s*[({]))", re.DOTALL
)


_LITERAL_WORD = re.compile(r"[A-Za-z0-9 _:{}()\"'.=@]*")


def _piped_read_only(argv: list[str], at: int) -> bool:
    """Whether the stdin of the `gh` at `argv[at]` is an `echo`/`printf` right before it, piped in
    with `|`, whose words the shell cannot change (`_LITERAL_WORD`, no `..`, no flag) and spell a
    read-only query, and the call itself redirects nothing (`<`).

    Only that one segment counts: a query elsewhere in the command says nothing about this stdin.
    """
    if at < 2 or argv[at - 1] != "|":
        return False
    start = at - 2
    while start > 0 and argv[start - 1] not in vg._SEPARATORS:
        start -= 1
    segment = argv[start : at - 1]
    if not segment or segment[0] not in ("echo", "printf"):
        return False
    if any(t.startswith("<") for t in vg._args_from(argv, at)):
        return False
    words = segment[1:]
    # Only words the shell cannot change count: it expands `$(…)`, `$VAR`, backticks, braces
    # (`{mu,}tation`, `{a..b}`), globs and `~`, and printf/`echo -e` decode formats and escapes,
    # all after this check, so any of them could spell a mutation the regex never saw. An
    # allow-list (no `,`, no `..`, no `$ \ % * ? [ ~`) instead of a list of known tricks.
    if any(not _LITERAL_WORD.fullmatch(w) or ".." in w or w.startswith("-") for w in words):
        return False
    return bool(_READ_ONLY_DOC.search(" ".join(words)))


def _graphql_text(
    args: list[str], command: str, cwd: str | None, piped_read_only: bool = False
) -> tuple[str, str | None]:
    """(the command's own text plus every query file it names, why a query is unseen or None).

    A query from stdin (`--input -`, `query=@-`) is in the command only as a heredoc; piped from
    elsewhere the hook cannot read it, nor a file it cannot open: both are reported unseen.
    """
    parts, files, unseen = [command], [], None
    for k, a in enumerate(args):
        value = args[k + 1] if k + 1 < len(args) else ""
        if a in ("-F", "--field", "-f", "--raw-field") and value.startswith("query=@"):
            files.append(value[len("query=@") :])
        if a == "--input" and value:
            files.append(value)
    for name in files:
        if name == "-":
            if "<<" not in command and not piped_read_only:
                unseen = "the GraphQL query comes from stdin, which the hook cannot read"
            continue
        try:
            parts.append(Path(cwd or ".", name).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            unseen = f"the GraphQL query file {name} is not readable from {cwd or '.'}"
    return "\n".join(parts), unseen


def _cwd_at(argv: list[str], cwd: str | None, stop: int) -> tuple[str | None, bool]:
    """(the directory `argv[stop]` runs in after the command's own `cd`s, whether it is known).

    `~` and `$VAR` are expanded as the shell would; a target still holding `$` (a command
    substitution, an unset variable) leaves the directory unknown.
    """
    known = True
    for i, tok in enumerate(argv[:stop]):
        if tok.rstrip(";&|") in ("cd", "pushd") and i + 1 < len(argv):
            target = os.path.expanduser(os.path.expandvars(argv[i + 1].rstrip(";&|")))
            if "$" in target or "`" in target:
                known = False
            cwd = os.path.join(cwd or "", target)
    return cwd, known


def _merge_calls(argv: list[str], command: str, cwd: str | None) -> list[MergeCall]:
    """Every merge or arm in `argv`, in order."""
    calls: list[MergeCall] = []
    for i in range(len(argv)):
        found = _gh_at(argv, i)
        if found is None:
            continue
        repo, j = found
        if argv[j : j + 2] == ["pr", "merge"]:
            args = [a.rstrip(";&|") for a in vg._args_from(argv, j + 2)]
            selector, repo = _selector_and_repo(args, repo)
            calls.append(
                MergeCall(
                    i,
                    "pr merge",
                    "--auto" in args,
                    "--disable-auto" in args,
                    selector,
                    repo,
                    args=args,
                )
            )
            continue
        if argv[j : j + 1] != ["api"]:
            continue
        args = [a.rstrip(";&|") for a in vg._args_from(argv, j + 1)]
        target = next((a for a in args if _API_MERGE.search(a)), None)
        if target is not None and _api_method(args) not in ("GET", "HEAD"):
            m = _API_MERGE.search(target)
            calls.append(MergeCall(i, "api merge", False, repo=m.group(1), number=int(m.group(2))))
            continue
        if "graphql" not in args:
            continue
        text, unseen = _graphql_text(
            args, command, _cwd_at(argv, cwd, i)[0], _piped_read_only(argv, i)
        )
        arm = "enablePullRequestAutoMerge" in text
        if not arm and "mergePullRequest" not in text and unseen is None:
            continue
        call = MergeCall(i, "graphql", arm)
        ids = sorted(set(_NODE_ID.findall(text)))
        if unseen is not None:
            call.unresolved = unseen
        elif len(ids) != 1:
            call.unresolved = f"the mutation names {len(ids)} pull-request node ids, not one"
        else:
            _resolve_node(call, ids[0], cwd)
        calls.append(call)
    return calls


def _resolve_node(call: MergeCall, node: str, cwd: str | None) -> None:
    query = "query($id:ID!){node(id:$id){... on PullRequest{number repository{nameWithOwner}}}}"
    raw = _gh(["api", "graphql", "-f", f"query={query}", "-f", f"id={node}"], cwd)
    try:
        pr = json.loads(raw or "")["data"]["node"]
        call.number, call.repo = int(pr["number"]), pr["repository"]["nameWithOwner"]
    except (ValueError, TypeError, KeyError):
        call.unresolved = f"pull request {node} did not resolve through `gh api graphql`"


def _selector_and_repo(args: list[str], repo: str | None) -> tuple[str | None, str | None]:
    selector, k = None, 0
    while k < len(args):
        a = args[k]
        if a in ("-R", "--repo") and k + 1 < len(args):
            repo = args[k + 1]
        if a.startswith("--repo="):
            repo = a.split("=", 1)[1]
        if a in _VALUED:
            k += 2
            continue
        if not a.startswith("-") and selector is None:
            selector = a
        k += 1
    return selector, repo


def _review_name(root: str, key: str, default: str) -> str:
    try:
        with open(os.path.join(root, ".weside", "config.json")) as fh:
            name = (json.load(fh).get("review") or {}).get(key)
    except Exception:
        name = None
    return name if isinstance(name, str) and name.strip() else default


def _workflow_names(root: str, name: str) -> bool:
    """Some workflow in `root` declares a job (or workflow) named exactly `name`."""
    pattern = re.compile(rf"^\s*name:\s*[\"']?{re.escape(name)}[\"']?\s*(#.*)?$", re.MULTILINE)
    folder = Path(root) / ".github" / "workflows"
    try:
        files = [p for p in folder.iterdir() if p.suffix in (".yml", ".yaml")]
    except OSError:
        return False
    for path in files:
        try:
            if pattern.search(path.read_text(encoding="utf-8", errors="replace")):
                return True
        except OSError:
            continue
    return False


def _check_required(slug: str, base: str, name: str, cwd: str | None) -> bool:
    """The base branch's rulesets or classic protection require the `name` context."""
    branch = quote(base, safe="")
    try:
        rules = json.loads(_gh(["api", f"repos/{slug}/rules/branches/{branch}"], cwd) or "")
        for rule in rules:
            if rule.get("type") != "required_status_checks":
                continue
            checks = (rule.get("parameters") or {}).get("required_status_checks") or []
            if any(c.get("context") == name for c in checks):
                return True
    except Exception:
        pass
    try:
        info = json.loads(_gh(["api", f"repos/{slug}/branches/{branch}"], cwd) or "")
        required = (info.get("protection") or {}).get("required_status_checks") or {}
        contexts = required.get("contexts") or []
        contexts += [c.get("context") for c in required.get("checks") or []]
        return name in contexts
    except Exception:
        return False


def _receipt_armed(root: str) -> bool:
    try:
        with open(os.path.join(root, ".weside", "config.json")) as fh:
            block = json.load(fh).get("verification")
    except Exception:
        return False
    return isinstance(block, dict) and bool(block.get("pre_merge_receipt"))


def _red_receipt_line(body: str) -> str | None:
    """The first `receipt red …` line of a PR body, fenced code skipped."""
    fenced = False
    for raw in body.splitlines():
        line = raw.strip()
        if _FENCE.match(line):
            fenced = not fenced
        elif not fenced and _RECEIPT_RED.match(line):
            return line
    return None


def _receipt_state(selector: str | None, repo: str | None, cwd: str | None) -> str | None:
    """Why the arm must wait for a green receipt, or None (no red line, or gh failed)."""
    view = ["pr", "view", *([selector] if selector else []), *(["-R", repo] if repo else [])]
    try:
        pr = json.loads(_gh([*view, "--json", "number,body"], cwd) or "")
        line = _red_receipt_line(pr.get("body") or "")
        number = pr["number"]
    except Exception:
        return None
    if line is None:
        return None
    return (
        f"receipt red on #{number}: run the pre-merge receipt green, then /we:pr updates the "
        f"body. The PR body says: {line}"
    )


def _codex_state(selector: str | None, repo: str | None, name: str, cwd: str | None) -> str | None:
    """Why the arm must wait, or None when Codex has a verdict on the head, the base branch
    requires the check, or gh failed."""
    view = ["pr", "view", *([selector] if selector else []), *(["-R", repo] if repo else [])]
    raw = _gh([*view, "--json", "headRefOid,number,url,baseRefName"], cwd)
    try:
        pr = json.loads(raw or "")
        sha, number = pr["headRefOid"], pr["number"]
        slug = re.search(r"github\.com/([^/]+/[^/]+)/pull/", pr["url"]).group(1)
    except Exception:
        return None
    if pr.get("baseRefName") and _check_required(slug, pr["baseRefName"], name, cwd):
        return None
    raw = _gh(
        ["api", f"repos/{slug}/commits/{sha}/check-runs?check_name={quote(name)}&per_page=100"],
        cwd,
    )
    try:
        runs = json.loads(raw or "")["check_runs"]
    except Exception:
        return None
    head = f"head {sha[:9]} of PR #{number}"
    if not runs:
        return None if repo else f"no `{name}` check on {head} yet"
    run = max(runs, key=lambda r: r.get("id", 0))
    if run.get("status") != "completed":
        return f"`{name}` is still {run.get('status')} on {head}"
    conclusion = run.get("conclusion")
    if conclusion in _NO_VERDICT:
        return f"`{name}` ended `{conclusion}` on {head}, without a verdict"
    if conclusion == "failure":
        raw = _gh([*view, "--json", "comments"], cwd)
        try:
            comments = json.loads(raw or "")["comments"]
        except Exception:
            return None
        bodies = [c.get("body") or "" for c in comments if _MARKER in (c.get("body") or "")]
        verdicts = [m.group(1) for b in bodies for m in _VERDICT.finditer(b)]
        if verdicts and verdicts[-1] == "ERROR":
            return f"`{name}` on {head} says VERDICT:ERROR (the runner, not a review)"
    return None


@dataclass
class ClassResult:
    """The PR's class line (`T0`, `T2`, `T2 one-way <class>`), or why it was not computed."""

    line: str | None = None
    reason: str | None = None
    number: int | None = None
    url: str | None = None
    notice: str | None = None
    head: str | None = None
    hits: list[str] = field(default_factory=list)  # line 3 on: `<file>\t<section>: <why>`

    @property
    def one_way(self) -> str | None:
        m = _CLASS_LINE.match(self.line or "")
        return m.group(2) if m else None


def _git(root: str, *args: str, timeout: int = 20) -> str | None:
    """stdout of `git <args>` in `root`, or None on any failure."""
    try:
        out = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", *args],
            capture_output=True,
            text=True,
            timeout=_left(timeout),
            check=False,
            cwd=root,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 else None


def _freeze_slug(call: MergeCall, argv: list[str], root: str | None) -> str | None:
    """The repo a merge lands in, for the freeze: the explicit target, else the checkout's
    `origin`; None (frozen when any flag stands) where `gh` may pick another repo: `GH_REPO` in
    the environment or the command, a `gh repo set-default` (`remote.*.gh-resolved`) or an
    `upstream` remote, which `gh` prefers over `origin`."""
    target = _pr_target(call)
    if target:
        return target
    if root is None or os.environ.get("GH_REPO") or any("GH_REPO=" in a for a in argv):
        return None
    if _git(root, "config", "--get-regexp", r"^remote\..*\.gh-resolved$"):
        return None
    if _git(root, "config", "--get", "remote.upstream.url"):
        return None  # gh prefers an `upstream` remote over `origin`
    return _local_slug(root)


def _local_slug(root: str) -> str | None:
    m = _SLUG.search((_git(root, "config", "--get", "remote.origin.url") or "").strip())
    return m.group(1).lower() if m else None


def _crew_present_on_main(root: str, ref: str = RULES_FROM) -> bool:
    """`ref` carries a crew file of its own, parsing or not: a broken crew still uses the crew
    process. A repo that only points at another repo's crew (`.weside/config.json` `crew`) is not
    one: it keeps T0 without rules, as before."""
    return _git(root, "cat-file", "-e", f"{ref}:.weside/crew.json") is not None


def _crew_on_main(root: str) -> dict:
    """`origin/main`'s `.weside/crew.json` as a dict; {} when it has none or it does not parse."""
    raw = _git(root, "show", f"{RULES_FROM}:.weside/crew.json")
    try:
        crew = json.loads(raw or "")
    except ValueError:
        return {}
    return crew if isinstance(crew, dict) else {}


def _fetch_rules(root: str, ref: str) -> bool:
    """Fetch `origin/<branch>` so the rules are current; False when it cannot be fetched (a ref
    outside `origin/` is not fetched and must exist)."""
    remote, _, branch = ref.partition("/")
    if remote == "origin" and branch:
        refspec = f"+refs/heads/{branch}:refs/remotes/origin/{branch}"
        if _git(root, "fetch", "-q", "--no-tags", "origin", refspec, timeout=60) is None:
            return False
    return _git(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}") is not None


def _classifier(root: str) -> tuple[list[str], str | None, str] | None | str:
    """(argv prefix with a {file} slot, blob spec to write there or None, rules ref);
    None when the repo uses no rules (class T0); a str is the reason it cannot be computed."""
    if not _fetch_rules(root, RULES_FROM):
        return (
            f"`git fetch origin {RULES_FROM.split('/', 1)[1]}` failed; the rules must be current"
        )
    crew_doc = _crew_on_main(root)
    risk = crew_doc.get("risk") or {}
    rules_from = risk.get("rules_from") if isinstance(risk.get("rules_from"), str) else RULES_FROM
    command = risk.get("command")
    if isinstance(command, str) and command.strip():
        parts = command.split()
        return ["{file}", *parts[1:]], f"{rules_from}:{parts[0]}", rules_from
    if _git(root, "cat-file", "-e", f"{rules_from}:.weside/risk-paths") is None:
        if crew_doc or _crew_present_on_main(root, rules_from):
            return (
                f"this repo has a crew (`.weside/crew.json` on {rules_from}) but no risk rules: "
                f"neither `risk.command` in the crew nor `.weside/risk-paths` on {rules_from}, "
                "so the hook cannot tell a one-way PR from a two-way one. Land a "
                "`.weside/risk-paths` (`/we:setup` writes a starter; without one-way sections it "
                "brakes nothing, on purpose) or a `risk.command` first; the PR that lands it is "
                "refused here too, so the owner merges that one by hand"
            )
        return None
    own = f"{rules_from}:we/scripts/risk_paths.py"
    blob = own if _git(root, "cat-file", "-e", own) is not None else None
    return [sys.executable, "{file}"], blob, rules_from


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def pr_class(root: str, call: MergeCall, cwd: str | None) -> ClassResult:
    """The class of the PR behind `call`, computed from `origin/main`'s rules and classifier."""
    found = _classifier(root)
    if isinstance(found, str):
        return ClassResult(reason=found)
    if found is None:
        return ClassResult(line="T0")
    prefix, blob, rules_from = found
    selector = str(call.number) if call.number is not None else call.selector
    view = [
        "pr",
        "view",
        *([selector] if selector else []),
        *(["-R", call.repo] if call.repo else []),
    ]
    try:
        pr = json.loads(_gh([*view, "--json", "number,headRefOid,url"], cwd) or "")
        number, head, url = int(pr["number"]), pr["headRefOid"], pr["url"]
    except (ValueError, TypeError, KeyError):
        return ClassResult(reason="`gh pr view` did not name the PR's head")
    result = ClassResult(number=number, url=url, head=head)
    if rules_from != RULES_FROM and not _fetch_rules(root, rules_from):
        result.reason = f"`git fetch` of {rules_from} failed; the rules must be current"
        return result
    if _git(root, "cat-file", "-e", f"{head}^{{commit}}") is None:
        _git(root, "fetch", "-q", "--no-tags", "origin", head, timeout=60)
    base = (_git(root, "merge-base", rules_from, head) or "").strip()
    if not base:
        result.reason = f"no merge base of {head[:9]} and {rules_from} (fetch origin)"
        return result
    lines, result.reason = _run_classifier(root, prefix, blob, head, base)
    if lines:
        result.line, result.hits = lines[0], lines[2:]
    if blob is None or blob.endswith(":we/scripts/risk_paths.py"):
        rules = _git(root, "show", f"{rules_from}:.weside/risk-paths") or ""
        if not _ONE_WAY_SECTION.search(rules):
            result.notice = (
                f"risk-paths: no one-way classes configured (`.weside/risk-paths` on {rules_from}"
                " has no one-way section), so no PR here waits for the owner's merge."
            )
    return result


def _run_classifier(
    root: str, prefix: list[str], blob: str | None, head: str, base: str
) -> tuple[list[str] | None, str | None]:
    """(output lines with the class as line 1, None) or (None, why): the classifier run as a file
    in a no-checkout worktree of `head`, on `base`; the worktree is removed whatever happens."""
    tmp = tempfile.mkdtemp(prefix="we-merge-class.")
    tree = os.path.join(tmp, "head")
    try:
        script = os.path.join(tmp, "classifier")
        if blob is None:
            shutil.copyfile(RISK_PATHS, script)
        else:
            body = _git(root, "show", blob)
            if body is None:
                return None, f"`{blob}` is missing"
            Path(script).write_text(body, encoding="utf-8")
        os.chmod(script, 0o700)
        if (
            _git(root, "worktree", "add", "--no-checkout", "--detach", tree, head, timeout=60)
            is None
        ):
            return None, f"`git worktree add` of {head[:9]} failed"
        argv = [script if a == "{file}" else a for a in prefix] + [base]
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        try:
            out = subprocess.run(
                argv,
                cwd=tree,
                capture_output=True,
                text=True,
                timeout=_left(CLASSIFY_TIMEOUT),
                check=False,
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, f"the classifier did not finish ({type(exc).__name__})"
        lines = out.stdout.splitlines() or [""]
        line = lines[0].strip()
        if out.returncode != 0 or not _CLASS_LINE.match(line):
            last = (out.stderr.strip().splitlines() or [line or "no output"])[-1]
            return None, f"the classifier exited {out.returncode}: {last}"
        return [line, *lines[1:]], None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        _git(root, "worktree", "prune")


def _board_files(root: str | None) -> list[Path]:
    """Every board file a freeze may sit beside (`board_freeze.watched_board_files`)."""
    return (
        board_freeze.watched_board_files(root, DEFAULT_BOARD)
        if root
        else [board_freeze.crew.board_file(None, None, default=DEFAULT_BOARD)]
    )


def _human(root: str) -> str:
    human = _crew_on_main(root).get("human")
    name = human.get("name") if isinstance(human, dict) else None
    return name.strip() if isinstance(name, str) and name.strip() else "The owner"


def _freeze_refusal(root: str | None, slug: str | None = None) -> str | None:
    """The freeze refusal for a merge in repo `slug`, or None. A flag counts only for the repos
    it names (`board_freeze.covers`; fail closed on `*`, no list or an unknown slug)."""
    flag = None
    for board_file in _board_files(root):
        try:
            found = board_freeze.read_flag(board_freeze.flag_path(board_file))
        except board_freeze.FreezeError as exc:
            return (
                f"Merges are frozen: the freeze flag is unreadable ({exc}); it counts as standing."
            )
        if found is not None and board_freeze.covers(found, slug):
            flag = found
            break
    if flag is None:
        return None
    return (
        f"Merges are frozen since {flag.get('since', '?')} by {flag.get('by', '?')}: "
        f"{flag['reason']}. No merge and no arm while the flag stands; `board.py unfreeze` lifts it."
    )


def _panel_refusal(root: str, number: int) -> str | None:
    """Why a two-way T2 PR may not merge yet; None when the panel is green or the check is off."""
    path = LENS_VERDICT
    if not path.exists():
        print(
            "automerge_gate: no lens_verdict.py in the plugin, T2 panel check off", file=sys.stderr
        )
        return None
    vid = f"t2-pr{number}"
    try:
        spec = importlib.util.spec_from_file_location("we_lens_verdict", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        green, lines = module.check(Path(root), vid)
    except Exception as exc:  # a brake: a broken reader counts red, never green
        green, lines = False, [f"the verdict reader failed ({type(exc).__name__}: {exc})"]
    if green:
        return None
    return (
        f"PR #{number} is T2 and its lens panel is not green: {'; '.join(lines)}. "
        f"Run `/we:lens t2 {number}` on this head; a skip never turns a finding green."
    )


def _card_hits(hits: list[str]) -> list[str]:
    """The sections of `CARD_SECTIONS` the hit lines name, in that order."""
    named = {m.group(1) for h in hits for m in [_CARD_HIT.search(h)] if m}
    return [s for s in CARD_SECTIONS if s in named]


def _card_verdict(bodies: list[str], head: str) -> tuple[str | None, str | None]:
    """(the last card verdict word on `head` or None, the head of the last card comment at all)."""
    verdict, last_head = None, None
    for body in bodies:
        if CARD_MARKER not in body:
            continue
        m = _CARD_HEAD.search(body)
        if m is None:
            continue
        last_head = m.group(1)
        if head.startswith(m.group(1)):
            word = _CARD_OVERALL.search(body)
            verdict = word.group(1) if word else "UNREADABLE"
    return verdict, last_head


def _card_bodies(slug: str, number: int, cwd: str | None) -> list[str] | None:
    """Bodies of the PR's issue comments whose author may sign (`_CARD_AUTHORS` or an installed
    App), oldest first; None when the read fails."""
    jq = ".[] | {body, assoc: .author_association, type: .user.type}"
    raw = _gh(["api", f"repos/{slug}/issues/{number}/comments", "--paginate", "--jq", jq], cwd)
    if raw is None:
        return None
    try:
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        return [
            r.get("body") or ""
            for r in rows
            if r.get("assoc") in _CARD_AUTHORS or r.get("type") == "Bot"
        ]
    except (ValueError, AttributeError):
        return None


def _security_skill(root: str) -> str:
    """`/<skill>` of the crew's security holder on `origin/main`, or a placeholder."""
    main = _crew_on_main(root)
    name = crew.holder_name(main, "security")
    skill = crew.skill_name(name, main) if name else None
    return f"/{skill}" if skill else "/<security holder's skill>"


def _card_refusal(root: str, cls: ClassResult, cwd: str | None) -> str | None:
    """Why a two-way T2 PR with a card hit may not merge yet; None when the card verdict on the
    head is PASS or no hit needs one. A failed comment read refuses (fail closed)."""
    sections = _card_hits(cls.hits)
    if not sections or cls.number is None:
        return None
    head = cls.head or ""
    slug = (_URL_SLUG.search(cls.url or "") or [None, None])[1]
    bodies = _card_bodies(slug, cls.number, cwd) if slug else None
    hit = ", ".join(f"`{s}`" for s in sections)
    start = (
        f"PR #{cls.number} is T2 with a {hit} hit and needs a security card verdict PASS on its "
        f"head {head[:10]}"
    )
    how = (
        f'Start a card worker: `we-worker <KEY>-card --bg "{_security_skill(root)} security card '
        f'review of PR #{cls.number} on {head[:10]}"`; its comment carries `{CARD_MARKER}`, '
        f"`@ {head[:10]}` and `Overall: PASS` (worker-dispatch.md § Card worker)."
    )
    if bodies is None:
        return f"{start}: the PR comments could not be read, which counts as no verdict. {how}"
    verdict, last_head = _card_verdict(bodies, head)
    if verdict == "PASS":
        return None
    if verdict is not None:
        why = f"the card verdict on this head is {verdict}"
    elif last_head is not None:
        why = f"the last card verdict is on the older head {last_head}"
    else:
        why = "no card verdict is on the PR"
    return f"{start}: {why}. {how}"


def _pr_target(call: MergeCall) -> str | None:
    """The `owner/repo` a call names explicitly (`-R`, a URL selector, an API path), lower case."""
    if call.repo:
        return call.repo.lower()
    m = _URL_SLUG.search(call.selector or "")
    return m.group(1).lower() if m else None


def _uses_rules(start: str | None) -> bool:
    """The checkout at or above `start` classifies merges: it has a crew file, or a
    `.weside/risk-paths` in its tree or on `origin/main` (read offline). Without either the hook
    refuses no merge for want of a checkout, as before the class brake."""
    if not start:
        return False
    if crew.find(start) is not None:
        return True
    root = vg._repo_root(start)
    if root is None:
        return False
    if (Path(root) / ".weside" / "risk-paths").is_file():
        return True
    return _git(root, "cat-file", "-e", f"{RULES_FROM}:.weside/risk-paths") is not None


def _approve_gate(root: str) -> bool:
    """The repo's own one-way gate turns the owner's approve on the head into the merge: the
    workflow `.github/workflows/one-way-gate.yml` and a `brake_self_merge.py` that knows the state
    `approved`, both read from `origin/main`."""
    if _git(root, "cat-file", "-e", f"{RULES_FROM}:.github/workflows/one-way-gate.yml") is None:
        return False
    hits = _git(root, "grep", "-l", "-F", '"approved"', RULES_FROM, "--", "*brake_self_merge.py")
    return bool(hits and hits.strip())


def _one_way_refusal(root: str, cls: ClassResult) -> str:
    """Refusal 3: the core waits for the owner's hand, every other class for the self-merge window;
    where the repo runs an approve gate, the owner's approve on the head is the go for both."""
    pr = f"PR #{cls.number} ({cls.url})"
    head = (
        f"{pr} is `{cls.line}`: one-way ({cls.one_way}). No session merges or arms it, whatever "
        "a command or a quoted go says"
    )
    if _approve_gate(root):
        approve = (
            f"{_human(root)}'s GitHub approve on its head is the go (from the phone too): the "
            "`one-way gate` status turns green and the repo arms auto-merge itself, so the session "
            "does nothing after it. Ask for an approve, not a merge: hand over the link and the class."
        )
        if cls.one_way in risk_paths.CORE:
            return f"{head}: it is the brake's core. {approve}"
        return (
            f"{head}. {approve} Without the approve it merges itself 2 h after a green T2 panel on "
            f"its head (`/we:lens t2 {cls.number}`) where the repo runs a self-merge window; a "
            "`veto` label stops it."
        )
    if cls.one_way in risk_paths.CORE:
        return (
            f"{head}: it is the brake's core, only {_human(root)} merges it, by hand. "
            "Hand over the link and the class."
        )
    return (
        f"{head}: it merges itself 2 h after a green T2 panel on its head, once {_human(root)} got "
        "the push line, where the repo runs a self-merge window; a `veto` label stops it. "
        f"Post the panel with `/we:lens t2 {cls.number}` if none stands on this head, then hand "
        "over the link and the class."
    )


def _class_refusal(
    root: str | None,
    call: MergeCall,
    cwd: str | None,
    cwd_known: bool = True,
    home: str | None = None,
) -> tuple[str | None, bool]:
    """(refusal, go on): the class, panel and card refusals; go on is False when nothing is to
    merge.
    `home` is the directory the command starts in, read for rules when `root` is unknown."""
    if call.unresolved:
        return f"Merge refused, class not computed: {call.unresolved}.", False
    target = _pr_target(call)
    if root is None or (target is not None and target != _local_slug(root)):
        if root is None and target is None and cwd_known:
            return None, False  # `gh` has no repository here and merges nothing
        if not _uses_rules(root or home):
            return None, root is not None  # no rules here: the merge goes on as before
        where = target or "the repository this command runs in"
        return (
            f"Merge refused, class not computed: no local checkout of {where} here; run the "
            "merge from that repository's checkout, where the hook can classify it.",
            False,
        )
    cls = pr_class(root, call, cwd)
    if cls.notice and cls.notice not in NOTICES:
        NOTICES.append(cls.notice)
    if cls.line is None:
        return f"Merge refused, class not computed: {cls.reason}.", False
    if cls.one_way:
        return _one_way_refusal(root, cls), False
    if cls.line == "T2" and cls.number is not None:
        red = _panel_refusal(root, cls.number) or _card_refusal(root, cls, cwd)
        if red:
            return red, False
    return None, True


def _call_refusal(
    payload: dict, argv: list[str], call: MergeCall, command_cwd: str | None
) -> str | None:
    if call.disarm:
        return None
    if payload.get("agent_id") or worker_marker(payload):
        return (
            "A worker never merges and never arms auto-merge; that is the main session's call "
            "(worker-dispatch.md § Dev-only worker contract). Report the PR; the Lead arms "
            "auto-merge after `/we:ci-review`."
        )
    cwd, cwd_known = _cwd_at(argv, command_cwd, call.at)
    root = vg._repo_root(cwd) if cwd_known else None
    frozen = _freeze_refusal(root, _freeze_slug(call, argv, root))
    if frozen:
        return frozen
    refusal, go_on = _class_refusal(root, call, cwd, cwd_known, command_cwd)
    if refusal or not go_on or not call.arm or root is None:
        return refusal
    # The PR is this checkout's (checked above): read it as the local repo's, so a missing Codex
    # check waits as it does for a bare `gh pr merge`.
    selector = str(call.number) if call.number is not None else call.selector
    repo = None if _pr_target(call) == _local_slug(root) else call.repo
    if _receipt_armed(root):
        red = _receipt_state(selector, repo, cwd)
        if red is not None:
            return f"Auto-merge waits for a green pre-merge receipt: {red}"
    name = _review_name(root, "codex_check", DEFAULT_CHECK)
    if not repo and not _workflow_names(root, name):
        return None
    why = _codex_state(selector, repo, name, cwd)
    if why is None:
        return None
    return (
        f"Auto-merge waits for the Codex verdict: {why}. The base branch does not require "
        f"`{name}`, so an arm now merges its finding unread. Arm once the check on this head "
        "has a verdict (not pending, not ERROR; rerun an ERROR run), after `/we:ci-review` read it."
    )


def _refusal(payload: dict) -> str | None:
    NOTICES.clear()
    if payload.get("tool_name") != "Bash":
        return None
    command = (payload.get("tool_input") or {}).get("command", "")
    lower = command.lower()
    if "gh" not in command or ("merge" not in lower and "graphql" not in lower):
        return None
    argv = vg._argv_or_none(command)
    if not argv and _LOOKS_LIKE_MERGE.search(command):
        return (
            "Merge refused: the command does not parse as shell words (an unbalanced quote?), "
            "so the hook cannot see what it merges. Rewrite it without the stray quote."
        )
    for call in _merge_calls(argv, command, payload.get("cwd")):
        reason = _call_refusal(payload, argv, call, payload.get("cwd"))
        if reason is not None:
            if _edits_body_before(argv, call.at):
                reason += " " + BODY_CHAIN_NOTE
            return reason
    return None


BODY_CHAIN_NOTE = (
    "This command also edits the PR body before the merge, but the hook judged the body as it is "
    "now (it runs before the command): change the body in a command of its own, then arm."
)


def _edits_body_before(argv: list[str], stop: int) -> bool:
    """Whether a `gh pr edit` with a body flag runs before `argv[stop]`."""
    for i in range(min(stop, len(argv))):
        found = _gh_at(argv, i)
        if found is None:
            continue
        _repo, j = found
        if j < stop and argv[j : j + 2] == ["pr", "edit"]:
            args = vg._args_from(argv, j + 2)
            if any(
                a in ("--body", "-b", "--body-file", "-F") or a.startswith("--body") for a in args
            ):
                return True
    return False


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    _DEADLINE[0] = time.monotonic() + BUDGET_SECONDS
    try:
        reason = _refusal(payload)
    except Exception as exc:  # a brake: an error on a merge refuses it, never lets it through
        command = (
            str((payload.get("tool_input") or {}).get("command", ""))
            if isinstance(payload, dict)
            else ""
        )
        if not _LOOKS_LIKE_MERGE.search(command):
            return
        reason = (
            f"Merge refused: the merge gate failed ({type(exc).__name__}: {exc}). "
            "Fix the cause or run the merge by hand."
        )
    if reason is None:
        if NOTICES:
            print(json.dumps({"systemMessage": " ".join(NOTICES)}))
        return
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


if __name__ == "__main__":
    main()
