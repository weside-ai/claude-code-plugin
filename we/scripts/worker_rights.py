#!/usr/bin/env python3
"""The worker rights and the never-list of a process worker: one owner of the rules, read by
`hooks/worker_rights_gate.py` (the brake) and by `worker_launch.py settings` (the record).

No boundary. This is a brake against a misguided worker (a wrong brief, a prompt injection in a PR
comment), not a barrier against one that goes around it on purpose: a script file it writes and runs,
another `gh` binary, `curl` with the token all pass every text check. The boundaries are server-side
(branch rules, the merge gate, the app rights of the token).

Rights (crew `worker_rights`, opt-in per repo, all off by default): in a repo whose `origin` is one
of `worker_rights.repos`, a worker with a story key, on a branch that is not the default branch and
carries that key, may run without asking
  `gh pr ready` (`pr_ready`) and `gh pr comment` (`pr_comment`), with no selector or one naming the PR
  whose head is its branch in its repo (`gh pr view --json` resolves it; a `gh` failure denies);
  the crew's `branch_rc` command prefix (a branch RC: the repo's pre-push guard holds the receipt).
A held right in a command of its own is allowed outright; in a compound command it only passes this
gate. A right whose conditions fail is denied with the reason.

Never (every process worker, whatever its key; `never` names the item): secrets (`gh secret`,
`gh variable`, a `gh api` write on a `/secrets`, `/variables` or `/environments` path, the crew's
`deny_commands`); delete (`gh <noun> delete…`, `--delete-branch`, `gh pr comment --delete-last`,
`gh api` with method DELETE, `git push --delete|-d`, a `:<ref>` refspec); main (a `git push` whose
destination is the default branch, `main` or `master`, also a bare push from it, `--all`, `--mirror`;
`ALLOW_COMMIT_TO_MAIN`); guard bypass (a `git push` of a tag, `ALLOW_PUSH_WITHOUT_MAIN`,
`--no-verify`, `git commit -n`, `core.hooksPath`); the crew's `deny_text` anywhere in the command.
Merges stay `automerge_gate.py`'s.

Parse depth: compound commands, `bash|sh -c '…'`, `$( … )`, backticks, `<( … )`, `eval` of a literal
and heredocs fed to a shell are split into simple commands; inline code of `python -c`, `node -e`,
`perl -e`, `ruby -e` and heredocs fed to them are checked as text; `eval`, `source` or `.` of a
non-literal argument, a nesting deeper than `MAX_DEPTH` and an unparsable command are refused.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
INLINE = {"python": "-c", "python3": "-c", "node": "-e", "perl": "-e", "ruby": "-e"}
PREFIXES = {"command", "exec", "nohup", "time", "builtin", "nice", "stdbuf"}
KEYWORDS = {"if", "then", "do", "else", "elif", "while", "until", "!", "{", "}", "fi", "done"}
FLAG_PREFIXES = {"sudo", "env", "timeout", "xargs"}
MAX_DEPTH = 4
GIT_TIMEOUT_S = 10
GH_TIMEOUT_S = 30
MAIN_NAMES = ("main", "master")
GUARD_WORDS = ("ALLOW_PUSH_WITHOUT_MAIN", "--no-verify", "core.hooksPath")
WRITE_FIELDS = ("-f", "-F", "--field", "--raw-field", "--input")
SECRET_PATH = re.compile(r"(^|/)(secrets|variables|environments)(/|$|\?)")
HEREDOC = re.compile(
    r"<<-?[ \t]*(['\"]?)([^\s'\"]+)\1(?P<rest>[^\n]*)\n(?P<body>.*?)^\t*\2[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


@dataclass
class Parsed:
    """A command split into simple commands (argv lists), inline code texts and refusals."""

    commands: list[list[str]] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    compound: bool = False


def _substitutions(text: str) -> list[str]:
    """The bodies of `$( … )`, `<( … )`, `>( … )` and backticks in `text`, outermost first."""
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "`":
            j = text.find("`", i + 1)
            if j < 0:
                break
            out.append(text[i + 1 : j])
            i = j + 1
            continue
        if text[i] in "$<>" and text[i + 1 : i + 2] == "(" and text[i + 2 : i + 3] != "(":
            depth, j = 1, i + 2
            while j < len(text) and depth:
                depth += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            out.append(text[i + 2 : j - 1])
            i = j
            continue
        i += 1
    return out


def _tokens(text: str) -> list[str]:
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _is_op(tok: str) -> bool:
    return bool(tok) and all(c in "();|&" for c in tok)


def _is_redirect(tok: str) -> bool:
    return bool(tok) and all(c in "<>&" for c in tok) and ("<" in tok or ">" in tok)


def _strip_prefixes(argv: list[str]) -> list[str]:
    """`argv` without leading assignments, keywords and wrappers (`env X=1`, `timeout 30`, `sudo -u x`)."""
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in KEYWORDS or tok in PREFIXES or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tok):
            i += 1
        elif tok in FLAG_PREFIXES:
            i += 1
            while i < len(argv) and (argv[i].startswith("-") or "=" in argv[i]):
                i += 2 if argv[i] in ("-u", "-g", "-s", "-k", "-I", "-n", "-P", "-d") else 1
            if tok == "timeout" and i < len(argv) and re.fullmatch(r"[\d.]+[smhd]?", argv[i]):
                i += 1
        else:
            break
    return argv[i:]


def parse(command: str, depth: int = 0) -> Parsed:
    """Split `command` (see the module docstring); recursion stops at `MAX_DEPTH` with a refusal."""
    out = Parsed()
    if depth > MAX_DEPTH:
        out.problems.append(f"nested deeper than {MAX_DEPTH} levels")
        return out
    bodies: list[str] = []

    def take(match: re.Match[str]) -> str:
        bodies.append(match.group("body"))
        return f"<<HEREDOC{len(bodies) - 1} " + match.group("rest")

    stripped = HEREDOC.sub(take, command)
    for inner in _substitutions(stripped):
        out.compound = True
        _merge(out, parse(inner, depth + 1))
    try:
        tokens = _tokens(stripped.replace("\n", " ; "))
    except ValueError as exc:
        out.problems.append(f"unparsable ({exc})")
        return out
    simple: list[list[str]] = [[]]
    heredoc_of: dict[int, int] = {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if _is_op(tok):
            simple.append([])
        elif tok in ("<<", "<<-") and i + 1 < len(tokens) and tokens[i + 1].startswith("HEREDOC"):
            heredoc_of[len(simple) - 1] = int(tokens[i + 1][7:])
            i += 1
        elif _is_redirect(tok):
            if simple[-1] and simple[-1][-1].isdigit():
                simple[-1].pop()
            i += 1  # its target
        else:
            simple[-1].append(tok)
        i += 1
    commands = [(n, c) for n, c in enumerate(simple) if c]
    if len(commands) > 1:
        out.compound = True
    for n, argv in commands:
        body = bodies[heredoc_of[n]] if n in heredoc_of else None
        _descend(out, _strip_prefixes(argv), body, depth)
    return out


def _merge(out: Parsed, inner: Parsed) -> None:
    out.commands += inner.commands
    out.texts += inner.texts
    out.problems += inner.problems


def _descend(out: Parsed, argv: list[str], heredoc: str | None, depth: int) -> None:  # noqa: PLR0912
    if not argv:
        return
    out.commands.append(argv)
    name = os.path.basename(argv[0])
    if name in SHELLS:
        out.compound = True
        for k, tok in enumerate(argv[1:], 1):
            if re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", tok) and k + 1 < len(argv):
                _merge(out, parse(argv[k + 1], depth + 1))
                break
        else:
            if heredoc is not None:
                _merge(out, parse(heredoc, depth + 1))
                out.texts.append(heredoc)
    elif re.fullmatch(r"python3?(\.\d+)?|node|perl|ruby", name):
        out.compound = True
        flag = INLINE.get(re.sub(r"\.\d+$", "", name), "-c")
        for k, tok in enumerate(argv[1:], 1):
            if tok == flag and k + 1 < len(argv):
                out.texts.append(argv[k + 1])
                break
        if heredoc is not None:
            out.texts.append(heredoc)
    elif name == "eval":
        out.compound = True
        code = " ".join(argv[1:])
        if "$" in code or "`" in code:
            out.problems.append("eval of a non-literal argument")
        else:
            _merge(out, parse(code, depth + 1))
    elif name in ("source", ".") and len(argv) > 1 and ("$" in argv[1] or "`" in argv[1]):
        out.problems.append(f"{name} of a non-literal argument")


# ---------------------------------------------------------------- the repo a command runs in


def _git(cwd: str | Path | None, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd or "."), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_S,
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


def origin_slug(cwd: str | Path | None) -> str | None:
    return slug_of(_git(cwd, "remote", "get-url", "origin"))


def default_branch(cwd: str | Path | None) -> str:
    head = _git(cwd, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    return head.split("/", 1)[1] if head and "/" in head else "main"


def protected_branches(cwd: str | Path | None) -> set[str]:
    return {default_branch(cwd), *MAIN_NAMES}


def current_branch(cwd: str | Path | None) -> str:
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


def _api_never(args: list[str]) -> str | None:
    method, path, writes = None, None, False
    k = 1
    while k < len(args):
        tok = args[k]
        if tok in ("-X", "--method") and k + 1 < len(args):
            method, k = args[k + 1].upper(), k + 2
            continue
        if tok.startswith("--method="):
            method = tok.split("=", 1)[1].upper()
        elif re.fullmatch(r"-X[A-Za-z]+", tok):
            method = tok[2:].upper()
        elif tok in WRITE_FIELDS or tok.startswith(
            tuple(f"{f}=" for f in WRITE_FIELDS if f[1] == "-")
        ):
            writes = True
            k += 2 if "=" not in tok else 1
            continue
        elif tok in (
            "-H",
            "--header",
            "-q",
            "--jq",
            "-t",
            "--template",
            "--hostname",
            "--cache",
            "-p",
            "--preview",
        ):
            k += 2
            continue
        elif not tok.startswith("-") and path is None:
            path = tok
        k += 1
    if method == "DELETE":
        return "delete (gh api with method DELETE)"
    if path and SECRET_PATH.search(path.split("?")[0]) and (writes or method not in (None, "GET")):
        return f"secrets (gh api write on {path})"
    return None


def _gh_never(argv: list[str]) -> str | None:  # noqa: PLR0911
    args, _repo = _gh_split(argv)
    if not args:
        return None
    noun, verb = args[0], args[1] if len(args) > 1 else ""
    if noun in ("secret", "variable"):
        return f"secrets (gh {noun})"
    if noun == "api":
        return _api_never(args)
    if verb.startswith("delete"):
        return f"delete (gh {noun} {verb})"
    if "--delete-branch" in args or (noun == "pr" and verb == "close" and "-d" in args):
        return "delete (--delete-branch)"
    if noun == "pr" and verb == "comment" and "--delete-last" in args:
        return "delete (gh pr comment --delete-last)"
    return None


def _git_split(argv: list[str]) -> tuple[list[str], str | None, list[str]]:
    """(args from the subcommand on, the `-C` dir, the `-c` settings) of a `git` command."""
    cdir, confs, i = None, [], 1
    while i < len(argv) and argv[i].startswith("-"):
        if argv[i] == "-C" and i + 1 < len(argv):
            cdir, i = argv[i + 1], i + 2
        elif argv[i] == "-c" and i + 1 < len(argv):
            confs.append(argv[i + 1])
            i += 2
        else:
            i += 1
    return argv[i:], cdir, confs


PUSH_VALUE_FLAGS = ("-o", "--push-option", "--receive-pack", "--exec", "--repo")


def _push_never(args: list[str], cwd: str | None) -> str | None:  # noqa: PLR0911, PLR0912
    positional: list[str] = []
    k = 1
    while k < len(args):
        tok = args[k]
        if tok in ("--delete",) or re.fullmatch(r"-[a-zA-Z]*d[a-zA-Z]*", tok):
            return "delete (git push --delete)"
        if tok in ("--tags", "--follow-tags"):
            return f"guard bypass (git push {tok}: a tag)"
        if tok in ("--all", "--mirror", "--branches"):
            return f"main (git push {tok})"
        if tok in PUSH_VALUE_FLAGS:
            k += 2
            continue
        if not tok.startswith("-"):
            positional.append(tok)
        k += 1
    protected = protected_branches(cwd)
    refspecs = positional[1:]
    if not refspecs:
        branch = current_branch(cwd)
        return f"main (a bare git push from {branch})" if branch in protected else None
    for n, raw in enumerate(refspecs):
        spec = raw.lstrip("+")
        if spec == "tag" or (n and refspecs[n - 1] == "tag"):
            return "guard bypass (git push of a tag)"
        if spec.startswith(":"):
            return f"delete (git push {spec})"
        src, _, dst = spec.partition(":")
        dst = dst or src
        if dst.startswith("refs/tags/") or (
            not dst.startswith("refs/")
            and _git(cwd, "rev-parse", "-q", "--verify", f"refs/tags/{dst}")
        ):
            return f"guard bypass (git push of the tag {dst})"
        name = dst.removeprefix("refs/heads/")
        if name == "HEAD":
            name = current_branch(cwd)
        if name in protected:
            return f"main (git push to {name})"
    return None


def _git_never(argv: list[str], cwd: str | None) -> str | None:
    args, cdir, confs = _git_split(argv)
    if any(c.split("=", 1)[0].lower() == "core.hookspath" for c in confs):
        return "guard bypass (core.hooksPath)"
    where = os.path.join(cwd or ".", cdir) if cdir else cwd
    if not args:
        return None
    if args[0] == "push":
        return _push_never(args, where)
    if args[0] == "commit" and any(
        t == "-n" or re.fullmatch(r"-[a-mo-zA-Z]*n[a-zA-Z]*", t)
        for t in args[1:]
        if not t.startswith("--")
    ):
        return "guard bypass (git commit -n)"
    return None


def _runs(argv: list[str]) -> list[list[str]]:
    """The command itself, and the script a shell or interpreter runs (`bash x.sh`)."""
    out = [argv]
    if len(argv) > 1 and re.fullmatch(
        r"(ba|z|da|k)?sh|python3?(\.\d+)?", os.path.basename(argv[0])
    ):
        rest = [t for t in argv[1:] if not t.startswith("-")]
        if rest:
            out.append(rest)
    return out


def _starts_with(argv: list[str], entry: str) -> bool:
    words = entry.split()
    if not words or len(argv) < len(words):
        return False
    head = os.path.basename(argv[0])
    return (head == words[0] or argv[0] == words[0]) and argv[1 : len(words)] == words[1:]


def _word_hit(text: str, entry: str) -> bool:
    tail = r"(?![\w-])" if re.match(r"\w", entry[-1:]) else ""
    return re.search(r"(?<![\w-])" + re.escape(entry) + tail, text) is not None


TEXT_RULES = (
    (re.compile(r"\bgh\s+(secret|variable)\b"), "secrets (gh {1} in inline code)"),
    (
        re.compile(r"\bgh\s+api\b[^\n]*?/(secrets|variables|environments)\b"),
        "secrets (gh api on /{1} in inline code)",
    ),
    (re.compile(r"\bgh\s+[\w-]+\s+delete"), "delete (gh … delete in inline code)"),
    (re.compile(r"(-X\s*|--method[\s=]+)DELETE\b"), "delete (method DELETE in inline code)"),
    (
        re.compile(r"\bgit\s+push\b[^\n;|&]*(\s--delete\b|\s-d\b|\s\+?:\S)"),
        "delete (git push --delete in inline code)",
    ),
    (
        re.compile(r"\bgit\s+push\b[^\n;|&]*(--tags|--follow-tags|refs/tags/|\stag\s)"),
        "guard bypass (git push of a tag in inline code)",
    ),
    (
        re.compile(r"\bgit\s+push\b[^\n;|&]*[\s:](refs/heads/)?(main|master)\b(?![\w/-])"),
        "main (git push to {2} in inline code)",
    ),
)


def _normalized(text: str) -> str:
    """Inline code with list-of-strings argv joined (`["gh", "secret"]` → `gh secret`)."""
    return re.sub(r"""['"]\s*,\s*['"]""", " ", text)


def never(  # noqa: PLR0911, PLR0912
    command: str, cwd: str | None, rights: dict | None = None, parsed: Parsed | None = None
) -> str | None:
    """The never-list item `command` hits for a worker in `cwd`, else None."""
    rights = rights or {}
    parsed = parsed or parse(command)
    if parsed.problems:
        return f"unreadable command: {parsed.problems[0]}"
    seen = [HEREDOC.sub("", command), *parsed.texts]  # a heredoc is data unless a shell runs it
    if any("ALLOW_COMMIT_TO_MAIN" in t for t in seen):
        return "main (ALLOW_COMMIT_TO_MAIN)"
    for word in GUARD_WORDS:
        if any(word in t for t in seen):
            return f"guard bypass ({word})"
    for text in rights.get("deny_text") or []:
        if text and any(text in t for t in seen):
            return f"crew deny_text ({text})"
    for argv in parsed.commands:
        name = os.path.basename(argv[0])
        hit = _gh_never(argv) if name == "gh" else _git_never(argv, cwd) if name == "git" else None
        if hit:
            return hit
        for run in _runs(argv):
            for entry in rights.get("deny_commands") or []:
                if entry and _starts_with(run, entry):
                    return f"secrets (crew deny_commands: {entry})"
    for raw in parsed.texts:
        text = _normalized(raw)
        for rx, label in TEXT_RULES:
            found = rx.search(text)
            if found:
                return label.format(found.group(0), *found.groups())
        for entry in rights.get("deny_commands") or []:
            if entry and _word_hit(text, entry):
                return f"secrets (crew deny_commands: {entry} in inline code)"
    return None


# ---------------------------------------------------------------- the rights


RIGHT_NAMES = ("pr_ready", "pr_comment", "branch_rc")


def crew_rights(cwd: str | Path | None) -> dict:
    """The crew's `worker_rights` for `cwd` (defaults when there is no crew)."""
    import crew as crew_mod  # noqa: PLC0415

    _path, crew = crew_mod.find_and_load(cwd or Path.cwd())
    rights = (crew or crew_mod.DEFAULTS).get("worker_rights") or {}
    return {**crew_mod.DEFAULTS["worker_rights"], **rights}


def opted_in(rights: dict, slug: str | None) -> bool:
    return bool(slug) and slug.lower() in {str(r).lower() for r in rights.get("repos") or []}


def right_of(argv: list[str], rights: dict) -> str | None:
    """Which right a simple command asks for, else None."""
    name = os.path.basename(argv[0])
    if name == "gh":
        args, _repo = _gh_split(argv)
        if args[:2] == ["pr", "ready"]:
            return "pr_ready"
        if args[:2] == ["pr", "comment"]:
            return "pr_comment"
    rc = rights.get("branch_rc")
    if rc and _starts_with(argv, rc):
        return "branch_rc"
    return None


PR_VALUE_FLAGS = ("-b", "--body", "-F", "--body-file", "-R", "--repo")


def _selector(args: list[str]) -> str | None:
    k = 2
    while k < len(args):
        tok = args[k]
        if tok in PR_VALUE_FLAGS:
            k += 2
            continue
        if not tok.startswith("-"):
            return tok
        k += 1
    return None


def _gh_pr_head(selector: str, slug: str, cwd: str | None) -> dict:
    """`gh pr view <selector> --json headRefName,headRepository,headRepositoryOwner`; raises on failure."""
    out = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            selector,
            "--repo",
            slug,
            "--json",
            "headRefName,headRepository,headRepositoryOwner",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=GH_TIMEOUT_S,
        cwd=cwd or None,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or f"gh exited {out.returncode}")
    data = json.loads(out.stdout)
    if not isinstance(data, dict):
        raise RuntimeError("gh printed no object")
    return data


def right_refusal(  # noqa: PLR0911
    argv: list[str], right: str, rights: dict, key: str | None, cwd: str | None
) -> str | None:
    """Why a worker may not use `right` with this command here, else None (it holds)."""
    slug = origin_slug(cwd)
    if not opted_in(rights, slug):
        return f"{slug or 'this repo'} grants no worker rights (crew worker_rights.repos)"
    if not rights.get(right):
        return f"{right} is not granted in {slug} (crew worker_rights.{right})"
    if not key:
        return "this worker was started without a story key"
    branch = current_branch(cwd)
    if not branch or branch in protected_branches(cwd):
        return f"{branch or 'a detached HEAD'} is the default branch, not the worker's own"
    if key not in branch:
        return f"branch {branch} does not carry the key {key}"
    if right == "branch_rc":
        return None
    args, global_repo = _gh_split(argv)
    named = global_repo or _repo_flag(args)
    if named and slug_of(named) != slug:
        return f"{named} is another repo than {slug}"
    selector = _selector(args)
    if selector is None:
        return None
    try:
        head = _gh_pr_head(selector, slug, cwd)
    except Exception as exc:  # fail closed: an unresolved PR is no own PR
        return f"PR {selector} could not be resolved ({exc})"
    owner = ((head.get("headRepositoryOwner") or {}).get("login") or "").lower()
    repo = ((head.get("headRepository") or {}).get("name") or "").lower()
    if head.get("headRefName") != branch:
        return f"PR {selector} is not this branch's PR (its head is {head.get('headRefName')})"
    if owner and repo and f"{owner}/{repo}" != slug:
        return f"PR {selector} comes from {owner}/{repo}"
    return None


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
    rules += ["Bash(*git push*--delete*)", "Bash(*git push* -d *)", "Bash(*git push* :*)"]
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
    rules += [
        "Bash(*ALLOW_PUSH_WITHOUT_MAIN*)",
        "Bash(*ALLOW_COMMIT_TO_MAIN*)",
        "Bash(*--no-verify*)",
        "Bash(*core.hooksPath*)",
    ]
    return rules


def settings(repo: str | Path, key: str) -> dict:
    """The `--settings` document of a worker with `key` in `repo`: allow = the granted rights,
    deny = the never-list (and the crew's `deny_commands`, `deny_text`; a `deny_text` path also as a
    Read rule)."""
    rights = crew_rights(repo)
    allow: list[str] = []
    if opted_in(rights, origin_slug(repo)):
        if rights.get("pr_ready"):
            allow.append("Bash(gh pr ready*)")
        if rights.get("pr_comment"):
            allow.append("Bash(gh pr comment*)")
        if rights.get("branch_rc"):
            allow.append(f"Bash({rights['branch_rc']}*)")
    deny = never_rules(protected_branches(repo))
    deny += [f"Bash(*{c}*)" for c in rights.get("deny_commands") or [] if c]
    for text in rights.get("deny_text") or []:
        if text:
            deny.append(f"Bash(*{text}*)")
            if text.startswith("/"):
                deny.append(f"Read(/{text}**)")
    # `env` too: a `claude --bg` session runs in the daemon's environment, not the launcher's
    return {
        "permissions": {"allow": allow, "deny": deny},
        "env": {"WE_ROLE": "worker", "WE_STORY_KEY": key},
    }
