#!/usr/bin/env python3
"""PreToolUse hook: a PR may not be opened without a verification receipt.

Green tests share the blind spots of whoever wrote the code. The receipt says how
the behaviour was observed, or that it was not — so it gates the moment the claim
becomes public: `gh pr create`.

Deliberately narrow:
  * Fires only on a `gh pr create` / `gh pr edit` in **command position**, after
    heredoc bodies have been lifted out. A document that merely quotes the
    command is not a PR — that false positive is what made this hook expensive.
  * Only when the repo opted in — `.weside/config.json` → verification.required.
  * A body it cannot resolve (a command substitution with no heredoc behind it,
    an unreadable `--body-file`) it lets through: a hook that guesses wrong is
    worse than no hook. A `create` carrying **no** body flag at all (`--fill`)
    is not unresolvable — it is a claim with no receipt, and it blocks.
  * One transport. A PR opened through an MCP tool never reaches this code, and
    `--web` types its body in a browser we cannot read — the gate is armed against
    one spelling of the action.

The gate checks a declaration, not an observation: a `## Verification` heading and an
`**Oracle:**` line that picks cli | ui | substitute, or declines with a reason (`not-applicable`,
`not-observed`). Its worth is that every PR says in public how — or whether — it was observed.

Contract: `skills/story/references/plan-format.md` § Verification and
`references/worker-dispatch.md` § Finish sequence. Repo recipes: `.weside/verify.md`.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

# `<<TAG` … `TAG` — lifted out before parsing, and kept: the idiomatic inline body
# (`--body "$(cat <<'EOF' … EOF)"`) is a heredoc, and everything else that reaches
# `shlex` unquoted is prose.
_HEREDOC = re.compile(
    r"<<-?[ \t]*(['\"]?)([^\s'\"]+)\1(?P<rest>[^\n]*)\n(?P<body>.*?)^\t*\2[ \t]*$",
    re.MULTILINE | re.DOTALL,
)

# Tokens after which the next word starts a new command. `shlex` glues a trailing
# `;` onto the word before it, so the trailing character counts too.
_SEPARATORS = frozenset({"&&", "||", ";", "|", "&", "(", ")", "{", "}", "then", "do", "else", "!"})
# Words that precede a command without being one.
_PREFIXES = frozenset({"command", "env", "exec", "sudo", "nohup", "time", "timeout"})
_NEWLINE = re.compile(r"\n(?=(?:[^'\"]|'[^']*'|\"[^\"]*\")*$)")


def _starts_a_command(argv: list[str], i: int) -> bool:
    if i == 0:
        return True
    prev = argv[i - 1]
    return (
        prev in _SEPARATORS
        or prev[-1:] in (";", "&", "|")
        or prev in _PREFIXES
        or ("=" in prev and not prev.startswith("-"))
        or (i >= 2 and argv[i - 2] == "timeout")  # `timeout 30 gh …`: the duration is no command
    )


# The receipt: a heading and an oracle line that says how the change was observed — or, with a
# reason, that it was not. The gate reads that declaration, it cannot check the observation; what
# it catches is the silent PR: no heading, no choice (a template menu), no reason for a decline.
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*verification\b", re.IGNORECASE | re.MULTILINE)
_OBSERVED = ("cli", "ui", "substitute")
_DECLINES = ("not-applicable", "not-observed")
_ORACLES = _OBSERVED + _DECLINES
_MENU = " | ".join(_ORACLES)


def _line(body: str, name: str) -> str | None:
    """The value on a `**Name:** value` line, or None when there is no such line."""
    found = re.search(
        rf"^[ \t]*(?:[-*+|][ \t]*)?\**[ \t]*{name}\**[ \t]*:(?P<v>[^\n]*)$",
        body,
        re.IGNORECASE | re.MULTILINE,
    )
    return found.group("v") if found else None


def _word(oracle: str) -> str:
    """`not-observed` also as `not observed`."""
    return r"\b" + oracle.replace("-", r"[-\s]") + r"\b"


def _named(value: str) -> set[str]:
    """The oracle words in the choice part — before the reason (`not-observed — unit tests only`).
    A comma ends the choice too: `not-observed, no UI here` names one oracle, not two."""
    choice = re.split(r"\s[\u2014\u2013-]\s|[:(,;]", value, maxsplit=1)[0]
    return {o for o in _ORACLES if re.search(_word(o), choice, re.IGNORECASE)}


def _is_menu(named: set[str]) -> bool:
    """A template line lists the options; a decline next to any other word is no choice either.
    `cli | ui` is a choice (both driven); the old four-word menu still counts as a menu."""
    return bool(named & set(_DECLINES)) and len(named) > 1


_RECEIPT_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "pr-body-receipt.py"
)
_WHERE = (
    "Write the block into the PR body yourself; no ticket and no story plan are needed. Pass the "
    "body as `--body-file` so the gate can read it:\n\n"
    "    ## Verification\n\n"
    "    **Oracle:** <one of " + _MENU + ">\n\n"
    "cli | ui | substitute: name what you drove and what you saw (`**Seed:**`, `**Asserted:**`, "
    "`**Not proven:**` are recommended, not checked). Nothing observed beyond tests: "
    "`**Oracle:** not-observed — <reason, e.g. unit tests only, staging RC follows>`. No runtime "
    "behaviour at all: `**Oracle:** not-applicable — <reason>`.\n\n"
    "A story plan with a `## Verification` block can be spliced in instead: `python3 "
    + _RECEIPT_SCRIPT
    + " <TICKET> <body-in> <body-out>`. Contract: the `we` plugin's "
    "skills/story/references/plan-format.md § Verification."
)


def _strip_heredocs(command: str) -> tuple[str, list[str]]:
    bodies: list[str] = []

    def take(match: re.Match[str]) -> str:
        # The rest of the opening line stays: `cat <<'EOF' > pr-body.md` keeps its redirect.
        bodies.append(match.group("body"))
        return f"<<HEREDOC:{len(bodies) - 1}" + match.group("rest")

    return _HEREDOC.sub(take, command), bodies


def _same_command(argv: list[str], i: int) -> list[str]:
    """The tokens of the simple command containing argv[i] — up to the separators around it."""
    lo = i
    while lo > 0 and argv[lo - 1] not in _SEPARATORS and argv[lo - 1][-1:] not in (";", "&", "|"):
        lo -= 1
    hi = i
    while (
        hi + 1 < len(argv)
        and argv[hi + 1] not in _SEPARATORS
        and argv[hi][-1:] not in (";", "&", "|")
    ):
        hi += 1
    return argv[lo : hi + 1]


def _args_from(argv: list[str], k: int) -> list[str]:
    """argv[k:] up to the end of that simple command — a prefix before `gh` (`GH_REPO=x gh …`,
    `timeout 30 gh …`) does not shift it. Pinned by test_automerge_gate.py::test_auto_in_any_position_is_seen."""
    out: list[str] = []
    for tok in argv[k:]:
        if tok in _SEPARATORS:
            break
        out.append(tok)
        if tok[-1:] in (";", "&", "|"):
            break
    return out


def _written_here(argv: list[str], path: str, bodies: list[str]) -> str | None:
    """The heredoc this command redirects into `path` — a body written and used in one call.

    `cat <<'EOF' > f` and `cat > f <<'EOF'` are the same write; the heredoc token may sit on
    either side of the redirect, so the whole simple command is searched.
    """
    for i, tok in enumerate(argv):
        if tok in (">", ">>") and i + 1 < len(argv):
            target, near = argv[i + 1], _same_command(argv, i)
        elif tok == "tee" and i + 1 < len(argv) and i > 0 and argv[i - 1] == "|":
            # `cat <<'EOF' | tee f` — the heredoc sits in the command before the pipe.
            target, near = argv[i + 1].lstrip("-a "), _same_command(argv, i - 2)
        else:
            continue
        if os.path.normpath(target) != os.path.normpath(path):
            continue
        for tok2 in near:
            found = re.fullmatch(r"<<HEREDOC:(\d+)", tok2)
            if found:
                return bodies[int(found.group(1))]
    return None


def _cwd_after_cd(argv: list[str], cwd: str | None, stop: int | None = None) -> str | None:
    """Where a relative body-file actually lives after this command's own `cd` — a `cd` after the
    `gh` call has not happened yet when `gh` runs."""
    for i, tok in enumerate(argv[:stop]):
        if tok.rstrip(";&|") in ("cd", "pushd") and i + 1 < len(argv):
            cwd = os.path.join(cwd or "", argv[i + 1].rstrip(";&|"))
    return cwd


def _argv_or_none(command: str) -> list[str]:
    stripped, _ = _strip_heredocs(command)
    try:
        return shlex.split(_NEWLINE.sub(" ; ", stripped))
    except ValueError:
        return []


def _repo_root(cwd: str | None) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            cwd=cwd or None,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _required(root: str) -> bool:
    """Opt-in per repo. Unreadable or absent config → not armed."""
    try:
        with open(os.path.join(root, ".weside", "config.json")) as fh:
            cfg = json.load(fh)
    except Exception:
        return False
    block = cfg.get("verification")
    return isinstance(block, dict) and block.get("required") is True


def _body_arg(rest: list[str], j: int) -> tuple[str, bool] | None:
    """(value, it_is_a_path) for the body flag at `rest[j]`, or None."""
    tok = rest[j]
    for long, short, is_file in (("--body", "-b", False), ("--body-file", "-F", True)):
        if tok in (long, short) and j + 1 < len(rest):
            return (rest[j + 1], is_file)
        if tok.startswith(f"{long}="):
            return (tok.split("=", 1)[1], is_file)
    return None


def _pr_verb(argv: list[str]) -> tuple[int, str, list[str]] | None:
    """(index of `gh`, the `create`/`edit` verb, its remaining args) — command position only.

    Global flags before the verb (`gh -R o/r pr create`, `gh --repo=o/r pr create`) are skipped.
    """
    first: tuple[int, str, list[str]] | None = None
    for i, tok in enumerate(argv):
        bare = tok.lstrip("({$")
        if bare != "gh" and not bare.endswith("/gh"):
            continue
        # A `(`/`{` on the token IS the command position; anything else has to earn it.
        if tok == bare and not _starts_a_command(argv, i):
            continue
        j = i + 1
        while j < len(argv) and argv[j].startswith("-"):
            j += 1 if "=" in argv[j] or argv[j] not in ("-R", "--repo") else 2
        if argv[j : j + 2] in (["pr", "create"], ["pr", "edit"]):
            # Only this simple command's own args: a later `gh pr comment --body` is not
            # this PR's body, and a `create` after an `edit` is the one that claims.
            hit = (i, argv[j + 1], _args_from(argv, j + 2))
            if argv[j + 1] == "create":
                return hit
            if first is None:
                first = hit
    return first


def _body_of(command: str, cwd: str | None) -> tuple[str | None, str | None, bool]:
    """(verb, body_text, a_body_flag_was_present).

    `verb` is `create`, `edit`, or None when this command opens no PR. A body that
    cannot be resolved comes back as None with the flag True — the caller lets that
    through rather than guessing.
    """
    stripped, heredocs = _strip_heredocs(command)
    stripped = _NEWLINE.sub(" ; ", stripped)
    try:
        argv = shlex.split(stripped)
    except ValueError:
        return (None, None, False)

    found = _pr_verb(argv)
    if found is None:
        return (None, None, False)
    at, verb, rest = found
    cwd = _cwd_after_cd(argv, cwd, stop=at)
    if "--web" in rest:
        return (verb, None, True)

    seen = False
    body: str | None = None
    for j in range(len(rest)):
        arg = _body_arg(rest, j)
        if arg is None:
            continue
        value, is_file = arg
        value = value.rstrip(";&|")
        seen = True
        if value == "-":
            return (verb, None, True)
        if is_file:
            # A body this same command writes wins over whatever is on disk: the
            # heredoc has not run yet, so the file is absent or stale.
            body = _written_here(argv, value, heredocs)
            if body is None:
                try:
                    with open(os.path.join(cwd or "", value)) as fh:
                        body = fh.read()
                except Exception:
                    body = None
        elif re.search(r"\$\(|^\s*[\"']?\$", value) or value.count("`") % 2:
            # Unexpanded — PreToolUse runs before the shell, so a substitution or a
            # variable is not the body. A balanced backtick pair is a code span, not
            # a substitution, and stays readable. The one unexpanded shape we can
            # still read is the heredoc it was fed from.
            marker = re.search(r"<<HEREDOC:(\d+)", value)
            body = heredocs[int(marker.group(1))] if marker else None
        else:
            body = value

    return (verb, body, seen)


_FENCE = re.compile(r"^\s{0,3}(```|~~~).*?^\s{0,3}\1", re.MULTILINE | re.DOTALL)
_ANY_HEADING = re.compile(r"^\s{0,3}#{1,6}\s", re.MULTILINE)


def _masked(body: str) -> str:
    r"""`body` with every fenced block blanked to the same length, newlines kept.

    A heading inside a fence is a quotation (a template) or a shell comment in a fenced seed
    (`  # measurements: …`), never the start or the end of the receipt. The mask character is
    not whitespace, so `^\s{0,3}` cannot reach across a blanked line. Pinned by
    test_fenced_shell_comment_does_not_end_the_section.
    """
    return _FENCE.sub(lambda m: re.sub(r"[^\n]", "x", m.group(0)), body)


def _section_span(body: str) -> tuple[int, int, int] | None:
    """(heading start, heading end, section end) of the `## Verification` block in `body`."""
    masked = _masked(body)
    found = _HEADING.search(masked)
    if not found:
        return None
    nxt = _ANY_HEADING.search(masked, found.end())
    return (found.start(), found.end(), nxt.start() if nxt else len(body))


def _section(body: str) -> str | None:
    """The `## Verification` block itself — a template quoted in a fence is not a receipt."""
    span = _section_span(body)
    return body[span[1] : span[2]] if span else None


def _receipt_problem(full: str) -> str | None:
    """What is wrong with this PR body, in the words the author needs."""
    body = _section(full)
    value = _line(body, "oracle") if body is not None else None
    if value is None:
        return (
            "This PR does not say how the change was observed: its body has no `## Verification` "
            "block with an `**Oracle:**` line."
        )
    named = _named(value)
    if not named:
        return (
            "The `**Oracle:**` line names no oracle the gate can read. Its value has to start with "
            f"one of {_MENU}: the gate reads only the text before the first ` — `, `:`, `,` or `(` "
            "(`**Oracle:** not-observed — unit tests only`)."
        )
    if _is_menu(named):
        return "The `**Oracle:**` line lists the options instead of picking one."
    decline = named & set(_DECLINES)
    if decline:
        reason = value
        for word in _DECLINES:
            reason = re.sub(_word(word), "", reason, flags=re.IGNORECASE)
        if len(reason.strip(" *_`\u2014\u2013-:")) < 3:
            return f"`{decline.pop()}` is a legitimate answer and it carries its reason."
    return None


def _refusal(payload: dict) -> str | None:
    """The denial reason, or None when this call may proceed."""
    if payload.get("tool_name") != "Bash":
        return None
    command = (payload.get("tool_input") or {}).get("command", "")
    if "gh" not in command or "pr" not in command:
        return None

    cwd = payload.get("cwd")
    verb, body, seen = _body_of(command, cwd)
    # An edit that touches no body is not a new claim; a body we could not resolve
    # is not evidence of absence.
    if verb is None or (seen and body is None) or (not seen and verb != "create"):
        return None

    root = _repo_root(_cwd_after_cd(_argv_or_none(command), cwd))
    if not root or not _required(root):
        return None

    if body is None:
        problem = (
            "This PR is opened with no body at all, so it claims work is done and says "
            "nothing about how that was observed."
        )
    else:
        problem = _receipt_problem(body)
    return problem + "\n\n" + _WHERE if problem else None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    reason = _refusal(payload)
    if reason is None:
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
