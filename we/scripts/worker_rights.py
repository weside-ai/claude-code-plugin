#!/usr/bin/env python3
"""The worker rights and the never-list of a process worker: one owner of the rules, read by
`hooks/worker_rights_gate.py` (the brake) and by `worker_launch.py settings` (the record).

No boundary. This catches a worker's mistake before an action that hurts (secrets, deletion, prod),
not a barrier against one that goes around it on purpose (L0 § Flow first): a script file it writes and runs,
another `gh` binary, `curl` with the token all pass every text check. The boundaries are server-side
(branch rules, the merge gate, the app rights of the token). A row stays only for a PROD, secret,
deletion or one-way accident; its damage is the comment above it.

Never (every process worker, whatever its key; `never` names the item) is a fixed list of patterns
matched on the command text (`NEVER`), not a shell parser: what a pattern finds anywhere in
the text is denied, inside `bash -c '…'`, `$( … )`, a heredoc or inline `python -c` code alike, and
data that only names an item (a heredoc quoting `git push --delete`) is denied too, as the
`--settings` deny rules already deny it. The list: secrets (`gh secret`, `gh variable`, a `gh api`
write on a `/secrets`, `/variables` or `/environments` path, the crew's `deny_commands`); delete
(`gh <noun> delete…`, `--delete-branch`, `gh pr close -d`, `gh api` with method DELETE, `git push
--delete|-d` and a `:<ref>` refspec unless the branches are merged: one plain `git push origin
--delete <branch>…` whose branches are not protected, have their head on origin in
`origin/<default>` and head no open PR, `merged_delete_refusal`); main (a `git push` naming the default branch, `main` or `master`,
a ref pattern, `--all`, `--mirror`, `--branches`, any `git push` from a checkout on one of them,
judged where git runs it: `git -C`, `--git-dir`, `--work-tree` and any `cd` count, and the session's
cwd stays in unless the whole command is one simple `git [-C|--git-dir|--work-tree <p>]… push`
(`simple_push`, `_push_dirs`), so an environment prefix (`GIT_DIR=…`), a second segment, `eval` or
a path `git` keeps it); guard bypass on a commit (`--no-verify`, `-n`, `core.hooksPath` or a `SKIP=`
list naming the secret scan `gitleaks`, each with a `git … commit` in the same span), a `git config`
write of `core.hooksPath` on its own (any scope; it persists in the `.git/config` every worktree
shares; reads and `--unset` pass) and a `git push` of a tag; merge (`gh pr merge --admin` or `--auto`; a `gh pr merge` the text holds but no chain part
shows as `gh pr merge`: in a nested shell, `eval`, a substitution or behind a wrapper); the crew's
`deny_text` anywhere in the command.

Rights: the merge path alone. Every `gh pr merge` part, for every `build.pr_owner`, is judged on its
own (`right_refusal`): its own PR, either `--disable-auto` alone or `--match-head-commit <its
checkout's HEAD>`, the line `arm_pr.sh` prints as `ready`, and only when `arm_pr.sh --check` answers
`ready` on that HEAD, the one owner of those facts (hold labels, one-way class, every required name
green with absent as pending, merge state, review decision); the whole merge-line check (own-PR
read, `arm_pr.sh --check` in its own process group) shares one deadline under the hook's 60 s, and
running past it denies. Under `build.pr_owner: worker` (`.weside/config.json`, read from the
default branch of origin; `pr_owner_on_default`) also `arm_pr.sh` (`arm`: only with `WE_ROLE=worker`
in the environment, the variable `arm_pr.sh` refuses a one-way class by) and `gh pr edit`
(`pr_edit`: never removing a hold label). An arm or an edit behind a wrapper or an assignment (`env`,
`timeout 9`, `GH_X=1`), in a `bash|sh|… -c` string, in `eval` or in a `$( … )` or backtick body is
refused, not judged (`hidden_right`). Otherwise each part of a chain of simple commands
(`segments`, split on `&&`, `||`, `;`, `|`, `&`, parentheses and newlines outside quotes; leading
shell keywords stripped) is judged; a held right is allowed outright only on a command of its own
(`simple_argv`), in a chain it only passes this gate. `gh pr ready`, `gh pr comment`, `pr_ready.sh`,
the crew's `branch_rc`, a push and `gh pr create` are no rights: the gate stays out, `settings`
allows them.
The never patterns run on the text as typed and on it `normalised` (quotes and backslashes removed),
so `git push origin +m"ain"` is denied; a branch named in a variable, an alias or `-c` config is not.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Union

SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
GIT_TIMEOUT_S = 10
GH_TIMEOUT_S = 30
# one deadline for the whole merge-line check (own-PR read, then `arm_pr.sh --check`), under the
# hook's 60 s: a killed hook lets the call through, so the gate must answer first
MERGE_LINE_BUDGET_S = 50
ARM_PR = Path(__file__).with_name("arm_pr.sh")
MAIN_NAMES = ("main", "master")


def _tokens(text: str) -> list[str]:
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def simple_argv(command: str) -> list[str] | None:
    """The argv of `command` when it is one simple command (no operator, redirect, substitution,
    backtick or newline outside an escape), else None; the rights are judged only on such a one."""
    if "\n" in command or "$(" in command or re.search(r"(?<!\\)`", command):
        return None
    try:
        tokens = _tokens(command)
    except ValueError:
        return None
    if not tokens or any(t and all(c in "();|&<>" for c in t) for t in tokens):
        return None
    return tokens


_SEPARATORS = re.compile(r"&&|\|\||[;|&\n()]")


def _split(tokens: list[str]) -> list[list[str]]:
    parts: list[list[str]] = []
    part: list[str] = []
    for token in [*tokens, ";"]:
        if token and all(c in "();|&\n" for c in token):
            if part:
                parts.append(part)
            part = []
        else:
            part.append(token)
    return parts


def segments(command: str) -> list[list[str]]:
    """The argv of each simple command in `command`, split on `&&`, `||`, `;`, `|`, `&`, a
    parenthesis and newlines outside quotes, so a commit message whose quote spans lines is one
    word. Where the whole text does not tokenize, each line on its own; where a line does not
    either, each raw part as `simple_argv` reads it. No descent: a `bash -c` string, an `eval`
    argument or a backtick body stays one word of its part (`hidden_right` looks there)."""
    text = command.replace("\\\n", " ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars="();<>|&\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return _split(list(lexer))
    except ValueError:
        pass
    parts: list[list[str]] = []
    for line in text.split("\n"):
        try:
            parts += _split(_tokens(line))
        except ValueError:
            parts += [a for a in map(simple_argv, _SEPARATORS.split(line)) if a]
    return parts


# shell keywords in front of a simple command: stripped, the command after them is judged as usual
KEYWORDS = {"if", "then", "do", "else", "elif", "while", "until", "!", "{", "}", "fi", "done"}
# commands that run their arguments as a command: a right behind one is refused, not judged
WRAPPERS = {
    "env", "command", "builtin", "exec", "nohup", "timeout", "xargs", "nice", "ionice", "stdbuf",
    "time", "sudo", "doas", "setsid", "flock", "chrt", "taskset", "unbuffer", "watch", "parallel",
}  # fmt: skip
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")
MAX_DEPTH = 4
# the body of a heredoc with a quoted delimiter is data: bash runs no substitution in it
_QUOTED_HEREDOC = re.compile(
    r"<<-?[ \t]*(['\"])(\w+)\1([^\n]*\n)(.*?)(^[ \t]*\2[ \t]*$)", re.S | re.M
)


def strip_keywords(argv: list[str]) -> list[str]:
    """`argv` without the shell keywords in front (`then gh pr ready` reads `gh pr ready`)."""
    i = 0
    while i < len(argv) and argv[i] in KEYWORDS:
        i += 1
    return argv[i:]


def _substitutions(text: str) -> list[str]:
    """The bodies of `$( … )`, `<( … )`, `>( … )` and backticks in `text`, outermost first, as bash
    sees them: nothing inside single quotes, no escaped backtick or `$`."""
    out: list[str] = []
    i, quote = 0, None
    while i < len(text):
        ch = text[i]
        if quote == "'":
            quote = None if ch == "'" else quote
            i += 1
            continue
        if ch == "\\":
            i += 2
            continue
        if ch == "'" and quote is None:
            quote = "'"
        elif ch == '"':
            quote = None if quote == '"' else '"'
        elif ch == "`":
            j = i + 1
            while j < len(text) and text[j] != "`":
                j += 2 if text[j] == "\\" else 1
            if j >= len(text):
                break
            out.append(text[i + 1 : j])
            i = j + 1
            continue
        elif ch in "$<>" and text[i + 1 : i + 2] == "(" and text[i + 2 : i + 3] != "(":
            depth, j = 1, i + 2
            while j < len(text) and depth:
                depth += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            out.append(text[i + 2 : j - 1])
            i = j
            continue
        i += 1
    return out


def _rights_inside(text: str, owner: str, depth: int) -> str | None:
    """The first right anywhere in `text` (a command of its own or hidden), for a text that runs
    nested: every right found there is refused."""
    if depth > MAX_DEPTH:
        return f"nested deeper than {MAX_DEPTH} levels"
    for part in segments(text):
        argv = strip_keywords(part)
        right = argv and right_of(argv, owner)
        if right:
            return right
    return hidden_right(text, owner, depth)


def hidden_right(command: str, owner: str = "master", depth: int = 0) -> str | None:
    """A right (`right_of`) that `command` runs other than as a simple command of its own, as
    `<right> <how>`, else None: behind a wrapper (`WRAPPERS`) or an assignment (`env arm_pr.sh 7`,
    `X=1 arm_pr.sh 7`), in the string of `bash|sh|… -c`, in the arguments of `eval`, or in a
    `$( … )` or backtick body. The gate refuses it instead of judging it (damage: a merge or an arm
    there skips the merge-line check). A heredoc's lines are judged as chain parts; a script file,
    a variable or an alias stay unseen."""
    if depth > MAX_DEPTH:
        return f"nested deeper than {MAX_DEPTH} levels"
    text = _QUOTED_HEREDOC.sub(lambda m: f"<<{m[1]}{m[2]}{m[1]}{m[3]}{m[5]}", command)
    for inner in _substitutions(text):
        found = _rights_inside(inner, owner, depth + 1)
        if found:
            return f"{found} in a command substitution"
    for part in segments(text):
        argv = strip_keywords(part)
        if not argv:
            continue
        head = os.path.basename(argv[0])
        wrapped = head in WRAPPERS or ASSIGNMENT.fullmatch(argv[0])
        # behind a wrapper its flags and values come first (`timeout 9`, `xargs -I{}`): every
        # later word may start the command it runs
        for k in range(len(argv) if wrapped else 1):
            right = k and right_of(argv[k:], owner)
            if right:
                return f"{right} behind {'an assignment' if head not in WRAPPERS else head}"
            found = _nested(argv[k:], owner, depth)
            if found:
                return found
    return None


def _nested(argv: list[str], owner: str, depth: int) -> str | None:
    """A right in the `-c` string of a shell or in the arguments of `eval` that `argv` runs."""
    name = os.path.basename(argv[0])
    if name in SHELLS:
        for j in range(1, len(argv) - 1):
            if re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", argv[j]):
                found = _rights_inside(argv[j + 1], owner, depth + 1)
                return f"{found} in {name} -c" if found else None
    elif name == "eval":
        found = _rights_inside(" ".join(argv[1:]), owner, depth + 1)
        return f"{found} in eval" if found else None
    return None


# ---------------------------------------------------------------- the repo a command runs in

# Where a git command runs: a directory, or a tuple of git's global path options (`-C <dir>`,
# `--git-dir <dir>`, `--work-tree <dir>`) as `git_target` resolves them.
Where = Union[str, Path, tuple[str, ...], None]


def _git(cwd: Where, *args: str, timeout: float = GIT_TIMEOUT_S) -> str | None:
    """`git` run in `cwd`: a directory, or the global path options of a command (`git_target`)."""
    where = list(cwd) if isinstance(cwd, tuple) else ["-C", str(cwd or ".")]
    try:
        out = subprocess.run(
            ["git", *where, *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def slug_of(url: str | None) -> str | None:
    """`owner/name` of a GitHub remote URL or a `[HOST/]OWNER/REPO` argument, lowercased."""
    if not url:
        return None
    found = re.search(r"(?:[:/]|^)([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url.strip())
    return f"{found.group(1)}/{found.group(2)}".lower() if found else None


def origin_slug(cwd: Where) -> str | None:
    return slug_of(_git(cwd, "remote", "get-url", "origin"))


def default_branch(cwd: Where) -> str:
    head = _git(cwd, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    return head.split("/", 1)[1] if head and "/" in head else "main"


def protected_branches(cwd: Where) -> set[str]:
    return {default_branch(cwd), *MAIN_NAMES}


def current_branch(cwd: Where) -> str:
    return _git(cwd, "branch", "--show-current") or ""


# ---------------------------------------------------------------- the never-list


def _gh_split(argv: list[str]) -> tuple[list[str], str | None]:
    """(args after the global flags, the `-R`/`--repo` value) of a `gh` command."""
    repo, i = None, 1
    while i < len(argv) and argv[i].startswith("-"):
        if argv[i] in ("-R", "--repo") and i + 1 < len(argv):
            repo, i = argv[i + 1], i + 2
        elif argv[i].startswith("--repo="):
            repo, i = argv[i].split("=", 1)[1], i + 1
        else:
            i += 1
    return argv[i:], repo


def _repo_flag(args: list[str]) -> str | None:
    for k, tok in enumerate(args):
        if tok in ("-R", "--repo") and k + 1 < len(args):
            return args[k + 1]
        if tok.startswith("--repo="):
            return tok.split("=", 1)[1]
        if re.fullmatch(r"-R\S+", tok):
            return tok[2:]
    return None


# git's global options that take their value as the next word
GIT_PATH_FLAGS = ("--git-dir", "--work-tree")
GIT_VALUE_FLAGS = ("--namespace", "--exec-path", "--config-env", "--super-prefix", *GIT_PATH_FLAGS)


def _git_globals(argv: list[str]) -> tuple[list[str], list[tuple[str, str]], list[str]]:
    """(args from the subcommand on, the path options in order as (`-C`|`--git-dir`|`--work-tree`,
    value), the `-c` settings) of a `git` command."""
    paths: list[tuple[str, str]] = []
    confs: list[str] = []
    i = 1
    while i < len(argv) and argv[i].startswith("-"):
        flag, eq, value = argv[i].partition("=")
        if argv[i] == "-C" and i + 1 < len(argv):
            paths.append(("-C", argv[i + 1]))
            i += 2
        elif argv[i] == "-c" and i + 1 < len(argv):
            confs.append(argv[i + 1])
            i += 2
        elif flag in GIT_PATH_FLAGS and eq:
            paths.append((flag, value))
            i += 1
        elif argv[i] in GIT_VALUE_FLAGS and i + 1 < len(argv):
            if argv[i] in GIT_PATH_FLAGS:
                paths.append((argv[i], argv[i + 1]))
            i += 2
        else:
            i += 1
    return argv[i:], paths, confs


def _git_split(argv: list[str]) -> tuple[list[str], str | None, list[str]]:
    """(args from the subcommand on, the last `-C` dir, the `-c` settings) of a `git` command."""
    args, paths, confs = _git_globals(argv)
    cdirs = [v for f, v in paths if f == "-C"]
    return args, (cdirs[-1] if cdirs else None), confs


def git_target(argv: list[str], cwd: Where) -> Where:
    """Where the `git` command `argv` runs when its global options name a place, else None: the
    `-C` dirs joined onto `cwd` in order (as git joins them), and with `--git-dir` or `--work-tree`
    the tuple of options `_git` runs with, so the repo and branch read are the ones git uses."""
    _args, paths, _confs = _git_globals(argv)
    if not paths:
        return None
    base = str(cwd or ".")
    for flag, value in paths:
        if flag == "-C":
            base = os.path.join(base, os.path.expanduser(value))
    rest = [x for f, v in paths if f != "-C" for x in (f, os.path.expanduser(v))]
    return ("-C", base, *rest) if rest else base


PUSH_VALUE_FLAGS = ("-o", "--push-option", "--receive-pack", "--exec", "--repo")


def _starts_with(argv: list[str], entry: str) -> bool:
    words = entry.split()
    if not words or len(argv) < len(words):
        return False
    head = os.path.basename(argv[0])
    return (head == words[0] or argv[0] == words[0]) and argv[1 : len(words)] == words[1:]


def _word_hit(text: str, entry: str) -> bool:
    tail = r"(?![\w-])" if re.match(r"\w", entry[-1:]) else ""
    return re.search(r"(?<![\w-])" + re.escape(entry) + tail, text) is not None


# A word break inside inline code too: `["gh", "secret"]` reads as `gh secret`.
_SEP = r"""[\s"',\[\]]+"""
# One simple command's rest of line: a pattern for a flag of `git push` looks only this far.
_REST = r"[^\n;|&]*"
_GIT_PUSH = rf"\bgit\b(?:\s+(?:-[Cc]\s+\S+|--(?:git-dir|work-tree)(?:=|\s+)\S+))*{_SEP}push\b"
_GH_PR_MERGE = rf"\bgh\b(?:\s+(?:-R|--repo)[\s=]\S+)?{_SEP}pr{_SEP}merge\b"
# `git [global options] commit` in one span: the guard bypass rows hold only on a commit, the one
# place the pre-commit secret scan runs
_GIT_COMMIT = rf"\bgit\b(?:\s+(?:-[Cc]\s+\S+|--[\w-]+(?:=\S+)?))*{_SEP}commit\b"
_GIT_CONFIG = rf"\bgit\b(?:\s+(?:-[Cc]\s+\S+|--[\w-]+(?:=\S+)?))*{_SEP}config\b"
# a `git config` read or removal: `--get*`, `--list`/`-l`, `--unset*`, `get`, `list`, `unset`
_CONFIG_READ = (
    rf"(?:\s--?(?:get[\w-]*|list|l|unset[\w-]*|show-[\w-]+)(?![\w-])|{_SEP}(?:get|list|unset)\b)"
)
# (item, pattern): the fixed never-list, searched in the command text as typed. `{main}` is the
# protected branch names of the repo the command runs in. The comment above each row is the
# damage it catches; a row without one does not belong here.
NEVER = (
    # an overwritten or printed GitHub secret or variable breaks or leaks the prod credentials
    ("secrets (gh {0})", rf"\bgh\b(?:\s+(?:-R|--repo)[\s=]\S+)?{_SEP}(secret|variable)\b"),
    # the same through the raw API; an environment write changes who may deploy to prod
    (
        "secrets (gh api write on /{0})",
        rf"\bgh{_SEP}api\b(?={_REST}/(secrets|variables|environments)\b)"
        rf"(?={_REST}(?:\s(?:-X\s*|--method[\s=]+)(?!GET\b)\w|\s(?:-f|-F|--field|--raw-field|--input)\b))",
    ),
    # a deleted repo, release, ruleset or workflow is lost for good
    ("delete (gh {0} {1})", rf"\bgh{_SEP}([\w-]+){_SEP}(delete[\w-]*)"),
    ("delete (gh api with method DELETE)", r"(?:-X\s*|--method[\s=]+)DELETE\b"),
    # an unmerged remote branch whose worktree is gone is the only copy of its work
    ("delete (--delete-branch)", r"--delete-branch\b"),
    ("delete (gh pr close -d)", rf"\bgh{_SEP}pr{_SEP}close\b{_REST}\s-d\b"),
    (
        "delete (git push --delete)",
        rf"{_GIT_PUSH}{_REST}\s(?:--de(?:l(?:e(?:te?)?)?)?|-[a-zA-Z]*d[a-zA-Z]*)(?=[\s=]|$)",
    ),
    ("delete (git push {0})", rf"{_GIT_PUSH}{_REST}\s(\+?:[^\s'\"]+)"),
    # the app's bypass on the default branch lands the push unchecked, and a GitOps repo's default
    # branch is what the cluster applies. A quote or a leading `+` may stand before the name
    # (`+main`, `"main"`, `HEAD:"main"`)
    (
        "main (git push to {0})",
        rf"""{_GIT_PUSH}{_REST}[\s:'"][+'"]*(?:refs/heads/)?({{main}})(?![\w/-])""",
    ),
    ("main (git push of a ref pattern)", rf"{_GIT_PUSH}{_REST}\*"),
    (
        "main (git push {0})",
        rf"{_GIT_PUSH}{_REST}\s(--al(?:l)?|--mi(?:r(?:r(?:or?)?)?)?|--br(?:a(?:n(?:c(?:h(?:es?)?)?)?)?)?)(?=[\s=]|$)",
    ),
    # a pushed release tag starts a staging or prod release, which only the release CLI may cut
    (
        "guard bypass (git push of a tag)",
        rf"{_GIT_PUSH}{_REST}(?:--tags|--follow-tags|refs/tags/|\stag\s)",
    ),
    # a commit past the pre-commit secret scan leaks the secret the moment it is pushed
    (
        "guard bypass (git commit --no-verify)",
        rf"{_GIT_COMMIT}{_REST}\s--no-v(?:e(?:r(?:i(?:fy?)?)?)?)?(?![\w-])",
    ),
    ("guard bypass (git commit -n)", rf"{_GIT_COMMIT}{_REST}\s-[a-mo-zA-Z]*n[a-zA-Z]*(?![\w-])"),
    (
        "guard bypass (core.hooksPath on a commit)",
        rf"(?i)\bgit\b{_REST}core\.hookspath{_REST}\scommit\b",
    ),
    # a written core.hooksPath persists in the shared `.git/config`: every later plain commit of every
    # worktree skips the scan. A read or removal counts only between `config` and the key: a value
    # spelled `unset` or `list` is still a write
    (
        "guard bypass (core.hooksPath written to the git config)",
        rf"""(?i){_GIT_CONFIG}(?:(?!{_CONFIG_READ})[^;|&\n])*?core\.hookspath['"]?[ \t=]+[^\s;|&]""",
    ),
    (
        "guard bypass (SKIP=gitleaks)",
        rf"""(?<![\w-])SKIP=['"]?(?:[\w.-]+,)*gitleaks(?![\w-])(?=[\s\S]*{_GIT_COMMIT})""",
    ),
    # `--admin` merges past red required checks, `--auto` right after a push past them by the
    # app's bypass
    ("merge (gh pr merge {0})", rf"{_GH_PR_MERGE}{_REST}(?<![\w-])(--admin|--auto)\b"),
)


# The never-list items a crash of the gate does not open: secrets, deletion and the PROD paths
# (a push to main, a merge past the checks). Everything else fails open on a crash.
HARD = ("secrets", "delete", "main", "merge")


def hard_never(command: str) -> str | None:
    """The `HARD` never-list item `command` hits, judged on the text alone (no git, no crew file,
    `main`/`master` as the protected names): what the gate still denies after it crashed."""
    text = command.replace("\\\n", " ")
    main = "|".join(MAIN_NAMES)
    for item, pattern in NEVER:
        if not item.startswith(HARD):
            continue
        compiled = re.compile(pattern.replace("{main}", main))
        found = compiled.search(text) or compiled.search(normalised(text))
        if found:
            return item.format(*(found.groups() or ("",)))
    return None


def _tags_pushed(text: str, cwd: Where) -> str | None:
    """A word after `git push` that names a tag of the repo (`git push origin v1.2`), else None."""
    words = {
        w.lstrip("+").partition(":")[2] or w.lstrip("+")
        for rest in re.findall(rf"{_GIT_PUSH}({_REST})", text)
        for w in rest.split()
        if not w.startswith("-")
    }
    tags = set((_git(cwd, "tag", "--list") or "").split()) if words else set()
    return next((w for w in sorted(words) if w in tags), None)


# a path value whose place the shell decides, not the text: a variable, a glob, a brace
_SHELL_PLACE = re.compile(r"[$*?\[{]")


def simple_push(text: str) -> list[str] | None:
    """The argv of `text` when the whole text is exactly one `git [-C <p>]… [--git-dir[=]<p>]
    [--work-tree[=]<p>] push …`: one segment, split by `shlex` (`simple_argv`: no operator,
    newline, redirect, substitution or backtick), `git` typed as the first word (no path, wrapper,
    backslash, quote or assignment in front), only those path options before `push`, and no
    path the shell decides (a variable, a glob). Anything else, a `shlex` error included, is None."""
    if not re.match(r"git\s", text):
        return None
    argv = simple_argv(text)
    if not argv or argv[0] != "git":
        return None
    i = 1
    while i < len(argv) and argv[i] != "push":
        flag, eq, value = argv[i].partition("=")
        if argv[i] in ("-C", *GIT_PATH_FLAGS) and i + 1 < len(argv):
            value, i = argv[i + 1], i + 2
        elif flag in GIT_PATH_FLAGS and eq:
            i += 1
        else:
            return None
        if _SHELL_PLACE.search(value):
            return None
    return argv if i < len(argv) else None


def _push_dirs(text: str, cwd: str | None) -> list[Where]:
    """Every place a push in `text` may run. A text that is one simple push (`simple_push`) runs
    only where its path options point, `-C` joined onto the cwd in order and `--git-dir`,
    `--work-tree` with them (`git_target`): the cwd drops out, so a worker started in the main
    checkout pushes its own worktree with `git -C <tree> push`, and a target on the main checkout
    or its `.git` is judged like the cwd. Any other text keeps the cwd, and adds each directory it
    names by `cd <dir>`, `pushd <dir>` or `git -C <dir>` and each push's own target: what the form
    does not match exactly is judged with the cwd, never let through."""
    base = cwd or "."
    argv = simple_push(text)
    if argv is not None:
        target = git_target(argv, base)
        return [base if target is None else target]
    moved = re.findall(r"\b(?:cd|pushd)\s+(['\"]?)([^\s'\";&|]+)\1", text)
    named = re.findall(r"\bgit\s+-C\s+(['\"]?)([^\s'\";&|]+)\1", text)
    dirs: list[Where] = [os.path.join(base, os.path.expanduser(d)) for _q, d in moved + named]
    targets: list[Where] = []
    for part in segments(text):
        argv = strip_keywords(part)
        if argv and os.path.basename(argv[0]) == "git" and _git_globals(argv)[0][:1] == ["push"]:
            target = git_target(argv, base)
            if target is not None:
                targets.append(target)
    return [base, *dirs, *targets]


def normalised(text: str) -> str:
    """`text` with its quotes, backslashes and the `$` of `$'…'` removed, as the shell joins a word:
    `+m"ain"` reads `+main`, `ma\\in` and `mai''n` read `main`. The never patterns run on it as well as on the
    text as typed, so splitting a name with quotes does not hide it."""
    return re.sub(r"""\$(?=['"])|['"\\]""", "", text)


def _never_row(text: str, cwd: str | None) -> tuple[str | None, bool]:
    """(the `NEVER` item `text` hits in `cwd`, else None; whether it is a merged-branch deletion
    that held, `merged_delete_refusal`)."""
    main = "|".join(re.escape(b) for b in sorted(protected_branches(cwd)))
    deletion: str | None = None  # "" once the text is a merged-branch deletion that holds
    for item, pattern in NEVER:
        compiled = re.compile(pattern.replace("{main}", main))
        found = compiled.search(text) or compiled.search(normalised(text))
        if not found:
            continue
        hit = item.format(*(found.groups() or ("",)))
        if item not in BRANCH_DELETE_ITEMS:
            return hit, False
        if deletion is None:
            deletion = merged_delete_refusal(text, cwd) or ""
        if deletion:
            return f"{hit}: {deletion}", False
    return None, deletion == ""


def never(command: str, cwd: str | None, rights: dict | None = None) -> str | None:  # noqa: PLR0911
    """The never-list item `command` hits for a worker in `cwd`, else None."""
    rights = rights or {}
    text = command.replace("\\\n", " ")
    hit, deletion_held = _never_row(text, cwd)
    if hit:
        return hit
    # in the shared main checkout a push sends the default branch with whatever another session
    # committed there, unchecked by the app's bypass; a pushed release tag cuts a release. A
    # merged-branch deletion that held sends no ref, from any checkout
    pushes = re.search(_GIT_PUSH, text) or re.search(_GIT_PUSH, normalised(text))
    if pushes and not deletion_held:
        places = _push_dirs(text, cwd)
        for where in places:
            branch = current_branch(where)
            if branch and branch in protected_branches(where):
                return (
                    f"main (a git push from {branch}: from a {branch} checkout a push runs only as "
                    "one `git -C <own worktree> push …`, without `2>&1`, `&&` or a second segment)"
                )
        for where in [cwd, *places]:
            tag = _tags_pushed(text, where)
            if tag:
                return f"guard bypass (git push of the tag {tag})"
    # the crew's values name secret files and secret tools whose output leaks a secret
    for entry in rights.get("deny_text") or []:
        if entry and entry in text:
            return f"crew deny_text ({entry})"
    for entry in rights.get("deny_commands") or []:
        if entry and _word_hit(text, entry):
            return f"secrets (crew deny_commands: {entry})"
    # a merge the text holds but no part shows skips the merge-line check `decide` runs per part
    if re.search(_GH_PR_MERGE, text) and not _merges_visible(command, text):
        return "merge (gh pr merge only as a visible part of the command)"
    return None


# the two `NEVER` rows a merged branch passes: a branch whose head is in the default branch and
# that no open PR has as head is no longer the only copy of any work
BRANCH_DELETE_ITEMS = ("delete (git push --delete)", "delete (git push {0})")
DELETE_FLAG = re.compile(r"--de(?:l(?:e(?:te?)?)?)?|-d")
DELETE_ONLY = (
    "a remote branch is deleted only as one `git push origin --delete <branch>…` of its own"
)


def _delete_targets(text: str, cwd: str | None) -> tuple[str | None, Where, list[str]]:
    """(why `text` is not one plain deletion of branches on origin, else None; where git runs it;
    the branch names). The form: one simple `git push` (`simple_push`) with `--delete`/`-d` and
    branch names, or with only `:<branch>` refspecs, `-q`/`-v` beside them."""
    argv = simple_push(text)
    if argv is None:
        return DELETE_ONLY, None, []
    args = _git_globals(argv)[0][1:]
    flagged, words = False, []
    for k, word in enumerate(args):
        if word == "--":
            words += args[k + 1 :]
            break
        if DELETE_FLAG.fullmatch(word):
            flagged = True
        elif word.startswith("-") and word not in ("-q", "--quiet", "-v", "--verbose"):
            return f"{DELETE_ONLY}, without {word}", None, []
        elif not word.startswith("-"):
            words.append(word)
    if len(words) < 2 or words[0] != "origin":
        return f"{DELETE_ONLY} (remote origin, then the branches)", None, []
    branches = []
    for ref in words[1:]:
        if not flagged and not ref.startswith(":"):
            return f"{ref} is no deletion: {DELETE_ONLY}", None, []
        name = ref[0 if flagged else 1 :]
        name = name[len("refs/heads/") :] if name.startswith("refs/heads/") else name
        if not name or name.startswith("-") or re.search(r"[:+*?\[\s]", name):
            return f"{ref} names no branch", None, []
        branches.append(name)
    base = cwd or "."
    return None, git_target(argv, base) or base, branches


def _remote_heads(where: Where, branches: list[str], deadline: float) -> dict[str, str] | None:
    """{branch: head sha} of `branches` on origin as `git ls-remote` reads it now, None when it
    fails: a remote-tracking ref may be older than the branch, and the newer commits would go."""
    out = _git(
        where,
        "ls-remote",
        "origin",
        *(f"refs/heads/{b}" for b in branches),
        timeout=max(min(GIT_TIMEOUT_S, _left(deadline)), 0.1),
    )
    if out is None:
        return None
    heads = {}
    for line in out.splitlines():
        sha, _, ref = line.partition("\t")
        if ref.startswith("refs/heads/"):
            heads[ref[len("refs/heads/") :]] = sha
    return heads


def _open_pr_refusal(branch: str, slug: str | None, cwd: Where, deadline: float) -> str | None:
    """Why `branch` may be the head of an open PR (one is, or `gh pr list` failed), else None."""
    argv = ["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number"]
    if slug:
        argv += ["--repo", slug]
    try:
        out = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=max(min(GH_TIMEOUT_S, _left(deadline)), 0.1),
            cwd=str(cwd) if isinstance(cwd, (str, Path)) else None,
        )
        prs = json.loads(out.stdout) if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return f"{branch}: its open PRs could not be read ({exc.__class__.__name__})"
    if not isinstance(prs, list):
        return f"{branch}: its open PRs could not be read (gh exited {out.returncode})"
    if prs:
        return f"{branch} is the head of open PR #{prs[0].get('number')}"
    return None


def merged_delete_refusal(text: str, cwd: str | None) -> str | None:  # noqa: PLR0911
    """Why the branch deletion `text` does not hold, else None. It holds only as one plain deletion
    on origin (`_delete_targets`) where every branch (a) is no protected branch, (b) has a head on
    origin (`git ls-remote`) that is an ancestor of `origin/<default>` (an unknown ref or object
    refuses) and (c) heads no open PR (`gh pr list --head`; gh failing refuses)."""
    deadline = time.monotonic() + MERGE_LINE_BUDGET_S
    problem, where, branches = _delete_targets(text, cwd)
    if problem:
        return problem
    protected = protected_branches(where)
    for branch in branches:
        if branch in protected:
            return f"{branch} is a protected branch"
        if not _git(where, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"):
            return f"{branch}: origin/{branch} is unknown here (fetch first)"
    heads = _remote_heads(where, branches, deadline)
    if heads is None:
        return "git ls-remote origin failed: the branch heads on origin are unknown"
    default = f"origin/{default_branch(where)}"
    slug = origin_slug(where)
    for branch in branches:
        if branch not in heads:
            return f"{branch} is not on origin"
        if (
            _git(where, "merge-base", "--is-ancestor", heads[branch], f"refs/remotes/{default}")
            is None
        ):
            return f"{branch} ({heads[branch][:12]}) is not merged into {default}"
        problem = _open_pr_refusal(branch, slug, where, deadline)
        if problem:
            return problem
    return None


def _merges_visible(command: str, text: str) -> bool:
    """Every merge call the text holds is a chain part of its own (`cd <tree> && gh pr merge …`),
    which `decide` judges like any right. One hidden in a `bash -c` string, behind a wrapper or in
    a substitution counts in the text but in no part."""
    merges = [p for p in map(strip_keywords, segments(command)) if p and _merge_part(p)]
    return len(merges) == len(re.findall(_GH_PR_MERGE, text))


def _merge_part(argv: list[str]) -> bool:
    return os.path.basename(argv[0]) == "gh" and _gh_split(argv)[0][:2] == ["pr", "merge"]


# ---------------------------------------------------------------- the rights


def _on_default(root: Where, rel: str) -> dict | None:
    """The JSON object at `rel` on the default branch of the repo at `root` (origin's), else None.
    `rel` is a path from the repo's top."""
    text = _git(
        root,
        "show",
        f"{_git(root, 'rev-parse', '--abbrev-ref', 'origin/HEAD') or 'origin/main'}:{rel}",
    )
    try:
        data = json.loads(text) if text else None
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _crew_on_default(cwd: str | Path | None) -> dict | None:
    """The crew in force for `cwd` as the default branch holds it: its `.weside/crew.json`, or the
    crew file its `.weside/config.json` points at, each read from that repo's origin/HEAD. A file in
    the worktree never counts: the worker could edit the rules that brake it."""
    root = _git(cwd, "rev-parse", "--show-toplevel")
    if not root:
        return None
    own = _on_default(root, ".weside/crew.json")
    if own is not None:
        return own
    pointer = (_on_default(root, ".weside/config.json") or {}).get("crew")
    if not isinstance(pointer, str) or not pointer.strip():
        return None
    target = (Path(root) / pointer.strip()).resolve()
    other = _git(target.parent, "rev-parse", "--show-toplevel")
    if not other:
        return None
    return _on_default(other, str(target.relative_to(Path(other).resolve())))


def crew_rights(cwd: str | Path | None) -> dict:
    """The crew's `worker_rights` for `cwd` from the default branch, over the defaults; a block of
    the wrong shape counts as the defaults (the built-in never-list still holds)."""
    import crew as crew_mod  # noqa: PLC0415

    defaults = crew_mod.DEFAULTS["worker_rights"]
    block = (_crew_on_default(cwd) or {}).get("worker_rights")
    if not isinstance(block, dict):
        return dict(defaults)
    merged = {**defaults, **{k: v for k, v in block.items() if k in defaults}}
    for key, default in defaults.items():
        value = merged[key]
        ok = (
            isinstance(value, list) and all(isinstance(v, str) for v in value)
            if isinstance(default, list)
            else value is None or isinstance(value, str)
        )
        if not ok:
            print(
                f"worker_rights: crew worker_rights.{key} has the wrong type; the defaults hold",
                file=sys.stderr,
            )
            return dict(defaults)
    return merged


def right_of(argv: list[str], owner: str = "master") -> str | None:
    """Which right a simple command asks for, else None: `merge` for a `gh pr merge` under every
    owner; under `owner` `worker` also `arm` (`arm_pr.sh`) and `pr_edit` (`gh pr edit`)."""
    if os.path.basename(argv[0]) == "gh":
        args, _repo = _gh_split(argv)
        if args[:2] == ["pr", "merge"]:
            return "merge"
        if owner == "worker" and args[:2] == ["pr", "edit"]:
            return "pr_edit"
    if owner == "worker" and _arm_argv(argv):
        return "arm"
    return None


def _gh_pr_head(selector: str, slug: str, cwd: str | None, timeout: float = GH_TIMEOUT_S) -> dict:
    """`gh pr view <selector> --json number,headRefName,headRepository,headRepositoryOwner`; raises
    on failure."""
    out = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            selector,
            "--repo",
            slug,
            "--json",
            "number,headRefName,headRepository,headRepositoryOwner",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        cwd=cwd or None,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or f"gh exited {out.returncode}")
    data = json.loads(out.stdout)
    if not isinstance(data, dict):
        raise RuntimeError("gh printed no object")
    return data


# the value-taking flags of `gh pr merge`: a value read as the PR selector resolves to no own PR
# and is denied, so a flag missing here fails closed
MERGE_VALUE_FLAGS = (
    *("-b", "--body", "-F", "--body-file", "-t", "--subject", "-A", "--author-email"),
    *("--match-head-commit", "-R", "--repo"),
)
MERGE_FLAGS = ("--merge", "--squash", "--rebase", "-m", "-s", "-r", *MERGE_VALUE_FLAGS)
SHA = re.compile(r"[0-9a-f]{7,40}")


def pr_owner_on_default(cwd: Where) -> str:
    """`build.pr_owner` as the default branch of origin holds it (`worker_launch.pr_owner_of`), never
    the worktree's file: the worker could edit the switch that opens its rights. Unreadable or
    another value: `master`, so no PR owner right opens."""
    import worker_launch  # noqa: PLC0415

    root = _git(cwd, "rev-parse", "--show-toplevel")
    if not root:
        return "master"
    try:
        return worker_launch.pr_owner_of(_on_default(root, ".weside/config.json") or {})
    except worker_launch.LaunchError as exc:
        print(f"worker_rights: {exc}; no PR owner rights", file=sys.stderr)
        return "master"


def _flag_value(args: list[str], *names: str) -> str | None:
    for k, tok in enumerate(args):
        word, eq, value = tok.partition("=")
        if word in names:
            return value if eq else (args[k + 1] if k + 1 < len(args) else "")
    return None


def _pr_selector(args: list[str], value_flags: tuple[str, ...]) -> str | None:
    k = 2
    while k < len(args):
        tok = args[k]
        if tok in value_flags:
            k += 2
            continue
        if not tok.startswith("-"):
            return tok
        k += 1
    return None


def _merge_refusal(args: list[str], cwd: str | None) -> str | None:
    """`gh pr merge` holds only as `--disable-auto` alone (a fix round begins with it) or as the
    command `arm_pr.sh` prints with `ready`: `--match-head-commit` on this checkout's HEAD. That
    HEAD is the one `arm_pr.sh` classified, and GitHub refuses the merge when the PR's head moved
    since."""
    flags = [t.split("=", 1)[0] for t in args[2:] if t.startswith("-")]
    if "--disable-auto" in flags:
        extra = [f for f in flags if f not in ("--disable-auto", "-R", "--repo")]
        return f"gh pr merge --disable-auto takes no other flag ({extra[0]})" if extra else None
    sha = _flag_value(args, "--match-head-commit")
    if not sha:
        return "gh pr merge without --match-head-commit: a worker merges only the line arm_pr.sh prints as ready"
    for flag in flags:
        if flag not in MERGE_FLAGS:
            return f"gh pr merge {flag}: not in the line arm_pr.sh prints"
    head = _git(cwd, "rev-parse", "HEAD") or ""
    if not SHA.fullmatch(sha) or not head.startswith(sha):
        return f"gh pr merge --match-head-commit {sha}: not this checkout's HEAD {head[:12] or '(none)'}"
    return None


def _script_argv(argv: list[str], script: str) -> list[str]:
    """`script` and its arguments, run directly or by a shell (`bash arm_pr.sh 7`), else []."""
    for k, tok in enumerate(argv[:2]):
        if os.path.basename(tok) == script and (k == 0 or os.path.basename(argv[0]) in SHELLS):
            return argv[k:]
    return []


def _arm_argv(argv: list[str]) -> list[str]:
    """`arm_pr.sh` and its arguments, run directly or by a shell, else []."""
    return _script_argv(argv, "arm_pr.sh")


def right_refusal(  # noqa: PLR0911
    argv: list[str], right: str, cwd: Where, deadline: float | None = None
) -> str | None:
    """Why a worker may not use `right` with this command here, else None (it holds). `deadline`
    (a `time.monotonic()` value) is the hook's one budget across every command of a call; alone,
    the merge line gets its own."""
    if right == "arm":
        # without the marker variable `arm_pr.sh` arms a one-way class for a worker, which only
        # the human's go may merge
        if os.environ.get("WE_ROLE") != "worker":
            return "arm_pr.sh without WE_ROLE=worker: arm_pr.sh refuses a worker's one-way class by it"
        return None
    args, global_repo = _gh_split(argv)
    if right == "pr_edit":
        # a hold label keeps a merge for the human; removing it lets the merge line land a diff
        # the human was to see
        removed = _hold_removed(args, cwd)
        return (
            f"gh pr edit --remove-label {removed}: a hold label keeps the merge for the human"
            if removed
            else None
        )
    # the merge line: a merge with a red or pending required check, a hold label or a one-way
    # class lands past the checks by the app's bypass
    if deadline is None:
        deadline = time.monotonic() + MERGE_LINE_BUDGET_S
    slug = origin_slug(cwd)
    named = global_repo or _repo_flag(args)
    if named and slug_of(named) != slug:
        return f"{named} is another repo than {slug}"
    problem = _merge_refusal(args, cwd)
    if problem:
        return problem
    branch = current_branch(cwd)
    selector = _pr_selector(args, MERGE_VALUE_FLAGS)
    if "--disable-auto" in args:
        return _own_pr(selector, slug, branch, cwd, deadline)[0] if selector else None
    # one own-PR read gives the number `arm_pr.sh --check` judges
    problem, pr = _own_pr(selector or branch, slug, branch, cwd, deadline)
    return problem or _merge_facts_refusal(pr.get("number"), slug, cwd, deadline)


def _hold_labels(cwd: str | None) -> set[str]:
    """The crew's `merge.hold_labels` as the default branch holds it (`crew.DEFAULTS` without one)."""
    import crew as crew_mod  # noqa: PLC0415

    block = (_crew_on_default(cwd) or {}).get("merge")
    labels = (block if isinstance(block, dict) else {}).get(
        "hold_labels", crew_mod.DEFAULTS["merge"]["hold_labels"]
    )
    return {str(x) for x in labels} if isinstance(labels, list) else set()


def _hold_removed(args: list[str], cwd: str | None) -> str | None:
    values = [
        v
        for k, tok in enumerate(args)
        for v in [
            tok.partition("=")[2] if "=" in tok else (args[k + 1] if k + 1 < len(args) else "")
        ]
        if tok.partition("=")[0] == "--remove-label"
    ]
    hold = _hold_labels(cwd) if values else set()
    return next((x for v in values for x in v.split(",") if x.strip() in hold), None)


def _left(deadline: float) -> float:
    return deadline - time.monotonic()


def _past(deadline: float, what: str) -> str:
    return f"{what} ran past the worker gate's {MERGE_LINE_BUDGET_S} s deadline"


def _merge_facts_refusal(  # noqa: PLR0911
    number: Any, slug: str | None, cwd: str | None, deadline: float
) -> str | None:
    """`arm_pr.sh --check` on this checkout's HEAD, because a worker can type the merge line
    without running the helper: the gate holds exactly the facts `ready` stands on (crew merge
    block, hold labels, one-way class, every required name green with absent as pending, the merge
    state, the review decision), from the one script that owns them, run with `WE_ROLE=worker` so
    a one-way class refuses for a worker known by its marker only too. Only `ready` on that HEAD
    passes; any other line, an unreadable PR, a failed call or the deadline refuses. The script
    runs in its own process group, so a timeout kills its `gh`, `git` and classifier children too."""
    if not isinstance(number, int):
        return "gh pr merge: the PR number could not be read (no number)"
    if _left(deadline) <= 0:
        return _past(deadline, "the own-PR read")
    head = _git(cwd, "rev-parse", "HEAD", timeout=min(GIT_TIMEOUT_S, _left(deadline))) or ""
    if not head:
        return "gh pr merge: the checkout's HEAD could not be read"
    if _left(deadline) <= 0:
        return _past(deadline, "git rev-parse HEAD")
    argv = ["bash", str(ARM_PR), str(number), "--check", "--sha", head, "--repo", slug or ""]
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd or None,
            env={**os.environ, "WE_ROLE": "worker"},  # a one-way class is no `ready` for a worker
            start_new_session=True,
        )
    except OSError as exc:
        return f"gh pr merge: arm_pr.sh --check failed ({exc})"
    try:
        stdout, _ = proc.communicate(timeout=max(_left(deadline), 0.1))
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            os.killpg(proc.pid, signal.SIGKILL)
        # a descendant in a session of its own may still hold the pipe: drain briefly, refuse anyway
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.communicate(timeout=2)
        return _past(deadline, "arm_pr.sh --check")
    lines = stdout.strip().splitlines()
    line = lines[-1] if lines else f"no verdict (exit {proc.returncode})"
    if proc.returncode == 0 and line.startswith(f"ready: all required checks green on {head} "):
        return None
    return f"gh pr merge: arm_pr.sh --check: {line}"


def _own_pr(
    selector: str, slug: str | None, branch: str, cwd: str | None, deadline: float | None = None
) -> tuple[str | None, dict]:
    """(why PR `selector` is not the PR whose head is `branch` in `slug`, else None; the PR read)."""
    timeout = GH_TIMEOUT_S if deadline is None else min(GH_TIMEOUT_S, _left(deadline))
    if timeout <= 0:
        return _past(deadline or 0.0, "the own-PR read"), {}
    try:
        head = _gh_pr_head(selector, slug, cwd, timeout)
    except Exception as exc:  # fail closed: an unresolved PR is no own PR
        spent = isinstance(exc, subprocess.TimeoutExpired) and deadline is not None
        if spent and _left(deadline) <= 0:
            return _past(deadline, "the own-PR read"), {}
        return f"PR {selector} could not be resolved ({exc})", {}
    owner = ((head.get("headRepositoryOwner") or {}).get("login") or "").lower()
    repo = ((head.get("headRepository") or {}).get("name") or "").lower()
    if head.get("headRefName") != branch:
        return (
            f"PR {selector} is not this branch's PR (its head is {head.get('headRefName')})",
            head,
        )
    if owner and repo and f"{owner}/{repo}" != slug:
        return f"PR {selector} comes from {owner}/{repo}", head
    return None, head


# ---------------------------------------------------------------- the brake log


BRAKE_LOG = "brakes.jsonl"


def forbidden_write(out: Path, line: dict) -> bool:
    """A test run's write into a live state directory or one below it (`WE_STATE_FORBIDDEN`,
    `os.pathsep`-separated, set by the repo's `conftest.py`): the line goes to the file named by
    `WE_STATE_LEAKS` instead and True says to write nothing. Shared by `brake_log` and
    `worker_launch.record_launch`."""
    here = os.path.realpath(str(out.parent))
    for d in os.environ.get("WE_STATE_FORBIDDEN", "").split(os.pathsep):
        if not d.strip():
            continue
        live = os.path.realpath(os.path.expanduser(d.strip()))
        if here == live or here.startswith(live.rstrip(os.sep) + os.sep):
            leaks = os.environ.get("WE_STATE_LEAKS", "").strip()
            if leaks:
                with open(leaks, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"path": str(out), **line}, ensure_ascii=False) + "\n")
            return True
    return False


def brake_log(cwd: str | Path | None, record: dict) -> Path | None:
    """Append one JSON line to `<state dir>/brakes.jsonl` (`crew.state_dir`: `WE_STATE_DIR`, else
    the crew's `state_dir`, else `~/.claude/we-state`); best effort, None when nothing was written.

    Line shape (this function owns it): `ts` (UTC ISO, stamped here), `type`, then per type
      `deny`  (the worker rights gate): `gate`, `item` (the never-list item or the failed right),
              `name`, `key`, `session_id`, `argv0` (the first word of the command; never the
              command itself, which may carry a secret value)
      `crash` (the worker rights gate failed open on an exception): `gate`, `error` (the
              exception's class only; its message may quote the command), `name`, `key`,
              `session_id`, `argv0`
      `card`  (a card worker's verdict, written by its starter where it posts it; `main` below):
              `verdict` (`PASS` or `BLOCKING`), `pr`
      `outcome` (added later by the starter): `kind` (the line's type it judges, e.g. `card`),
              `pr`, `danger` (`yes`: the danger it is built against was there; `no`: a false alarm)
    One line per event, so a brake's false alarms can be counted.

    `WE_STATE_FORBIDDEN` (directories, `os.pathsep`-separated; the test run's `conftest.py` sets
    it to the live state directories) refuses a write there: the line goes to the file named by
    `WE_STATE_LEAKS` instead, and the test run turns red on it."""
    import datetime as dt  # noqa: PLC0415

    import crew as crew_mod  # noqa: PLC0415

    with contextlib.suppress(Exception):
        try:
            path, crew = crew_mod.find_and_load(cwd or Path.cwd())
        except crew_mod.CrewError:
            path, crew = None, None
        out = crew_mod.state_dir(path, crew) / BRAKE_LOG
        line = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **record}
        if forbidden_write(out, line):
            return None
        out.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(out), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        return out
    return None


def argv0(command: str) -> str:
    """The first word of `command` (its basename), for a log line that must not carry values."""
    try:
        words = _tokens(command.split("\n", 1)[0])
    except ValueError:
        words = command.split()
    words = [w for w in words if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w)][:1]
    return os.path.basename(words[0]) if words else ""


# ---------------------------------------------------------------- the settings record


DELETE_NOUNS = (
    "repo",
    "release",
    "label",
    "run",
    "cache",
    "gist",
    "ssh-key",
    "gpg-key",
    "project",
    "codespace",
    "ruleset",
    "workflow",
)


def never_rules(protected: set[str]) -> list[str]:
    rules = ["Bash(*gh secret *)", "Bash(*gh variable *)"]
    for path in ("secrets", "variables", "environments"):
        for flag in ("-X", "--method", "-f ", "-F ", "--field", "--raw-field", "--input"):
            rules.append(f"Bash(*gh api*/{path}*{flag}*)")
    rules += [f"Bash(*gh {noun} delete*)" for noun in DELETE_NOUNS]
    rules += [
        "Bash(*--delete-branch*)",
        "Bash(*gh api*-X DELETE*)",
        "Bash(*gh api*-XDELETE*)",
        "Bash(*gh api*--method DELETE*)",
        "Bash(*gh api*--method=DELETE*)",
    ]
    # a branch deletion has no deny rule: a merged branch passes, and only the gate can tell
    for name in sorted(protected):
        rules += [
            f"Bash(*git push* {name})",
            f"Bash(*git push* {name} *)",
            f"Bash(*git push*:{name})",
            f"Bash(*git push*:{name} *)",
            f"Bash(*git push*refs/heads/{name}*)",
        ]
    rules += [
        "Bash(*git push*--tags*)",
        "Bash(*git push*--follow-tags*)",
        "Bash(*git push*refs/tags/*)",
        "Bash(*git push* tag *)",
        "Bash(*git push*--all*)",
        "Bash(*git push*--mirror*)",
    ]
    # a deny rule cannot see a chain's parts: the narrow glob is the closest form, the hook judges
    rules += [
        "Bash(*git*commit*--no-verify*)",
        "Bash(*core.hooksPath*commit*)",
        "Bash(*git*config*core.hooksPath *)",
        "Bash(*SKIP=*gitleaks*commit*)",
    ]
    return rules


# the PR owner's commands as allow rules, so a worker in the default mode is not asked; the gate
# still judges the merge line, the arm's role and a hold label
PR_OWNER_ALLOW = (
    "Bash(git push*)",
    "Bash(gh pr create*)",
    "Bash(gh pr edit*)",
    "Bash(gh pr comment*)",
    "Bash(*arm_pr.sh *)",
    "Bash(gh pr merge *--disable-auto*)",
    "Bash(gh pr merge *--match-head-commit*)",
    "Bash(gh api graphql*resolveReviewThread*)",
)


def settings(
    repo: str | Path,
    key: str,
    starter: str | None = None,
    name: str | None = None,
    lane: str | None = None,
) -> dict:
    """The `--settings` document of a worker with `key` in `repo`: allow = `gh pr ready`,
    `pr_ready.sh`, `gh pr comment` and the crew's `branch_rc` (a comment or a ready flag changes no
    code and no prod; in the background nobody answers a prompt), with `build.pr_owner: worker`
    also `PR_OWNER_ALLOW`; deny = the never-list (and the crew's `deny_commands`, `deny_text`; a
    `deny_text` path also as a Read rule)."""
    rights = crew_rights(repo)
    script = Path(__file__).resolve().with_name("pr_ready.sh")
    allow = [
        "Bash(gh pr ready*)",
        f"Bash({script} *)",
        f"Bash(bash {script} *)",
        "Bash(gh pr comment*)",
    ]
    if rights.get("branch_rc"):
        allow.append(f"Bash({rights['branch_rc']}*)")
    if pr_owner_on_default(repo) == "worker":
        allow += [rule for rule in PR_OWNER_ALLOW if rule not in allow]
    deny = never_rules(protected_branches(repo))
    deny += [f"Bash(*{c}*)" for c in rights.get("deny_commands") or [] if c]
    for text in rights.get("deny_text") or []:
        if text:
            deny.append(f"Bash(*{text}*)")
            if text.startswith("/"):
                deny.append(f"Read(/{text}**)")
    return {
        "permissions": {"allow": allow, "deny": deny},
        "env": worker_env(key, starter=starter, name=name, lane=lane),
    }


def worker_env(
    key: str,
    environ: Any = None,
    starter: str | None = None,
    name: str | None = None,
    lane: str | None = None,
) -> dict:
    """The `env` block of a worker's `--settings`: what `we-worker` sets and clears at its start.

    A `claude --bg` session runs in the daemon's environment, not the launcher's (the daemon may
    carry `WE_ROLE=worker` and another story's key, or a pin), so every variable the start decides
    is stated here; a cleared one is "": readers take it as unset, and an empty `WESIDE_COMPANION`
    also marks a deliberate worker (`materialize_on_start.py` skips its user warning). The
    launcher's own start variables (`WE_START`, `WE_WORKER_STARTER`) are cleared the same way: a
    worker never runs its starter's start check, and its own workers name it, not its starter, as
    theirs. `WE_STARTER` is the starter's session name, the address a worker's question names for
    its answer (`process/L0-worker.md`): the starter outlives the worker, so an answer that arrives
    after the worker ended still lands; "" when the launcher knows no name. `WE_HUMAN` passes on
    when the launcher has it. `WE_WORKER_NAME` is the worker's own name and `WE_WORKER_LANE` the
    lane it started in (`build` or `utility`, `worker_launch.capacity`): the name signs the worker's
    commits and PRs (`references/worker-dispatch.md` § Dev-only worker contract), the lane counts it in its pool.
    Never a credential: this block is written to a file."""
    env = os.environ if environ is None else environ
    doc = {
        "WE_ROLE": "worker",
        "WE_STORY_KEY": key,
        "WESIDE_COMPANION": "",
        "WE_ROLE_ID": "",
        "WE_START": "",
        "WE_WORKER_STARTER": "",
        "WE_STARTER": starter or "",
        "WE_WORKER_NAME": name or "",
        "WE_WORKER_LANE": "utility" if lane == "utility" else "build",
    }
    if env.get("WE_HUMAN"):
        doc["WE_HUMAN"] = env["WE_HUMAN"]
    return doc


# ---------------------------------------------------------------- the brake log CLI

CARD_OVERALL = re.compile(r"^\**Overall:\s*(PASS|BLOCKING)\b", re.MULTILINE)


def main(argv: list[str]) -> int:
    """`worker_rights.py brake card --pr <ref> --file <verdict file>`: one `card` line, the verdict
    read from the file's last `Overall:` line; `worker_rights.py brake outcome --pr <ref> --kind
    <type> --danger yes|no`: one `outcome` line. Prints the log's path; exit 2 on a bad call or a
    file without a verdict, 1 when nothing was written."""
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(prog="worker_rights.py")
    verbs = parser.add_subparsers(dest="noun", required=True)
    brake = verbs.add_parser("brake").add_subparsers(dest="verb", required=True)
    card = brake.add_parser("card")
    card.add_argument("--pr", required=True)
    card.add_argument("--file", required=True, type=Path)
    outcome = brake.add_parser("outcome")
    outcome.add_argument("--pr", required=True)
    outcome.add_argument("--kind", required=True)
    outcome.add_argument("--danger", required=True, choices=("yes", "no"))
    args = parser.parse_args(argv)
    if args.verb == "card":
        try:
            found = CARD_OVERALL.findall(args.file.read_text(encoding="utf-8"))
        except OSError as exc:
            print(f"worker_rights: {exc}", file=sys.stderr)
            return 2
        if not found:
            print(
                f"worker_rights: {args.file} has no `Overall: PASS|BLOCKING` line", file=sys.stderr
            )
            return 2
        record = {"type": "card", "verdict": found[-1], "pr": args.pr}
    else:
        record = {"type": "outcome", "kind": args.kind, "pr": args.pr, "danger": args.danger}
    out = brake_log(None, record)
    if out is None:
        print("worker_rights: no line written", file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
