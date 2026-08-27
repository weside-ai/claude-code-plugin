#!/usr/bin/env python3
"""PreToolUse hook: a PR may not be opened without a verification receipt.

Green tests share the blind spots of whoever wrote the code. The receipt is the
one artefact that says something other than the author's own model confirmed the
behaviour — so it gates the moment the claim becomes public: `gh pr create`.

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

Contract: `references/verification.md`. Repo recipes: `.weside/verify.md`.
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
    r"<<-?[ \t]*(['\"]?)([^\s'\"]+)\1[^\n]*\n(.*?)^\t*\2[ \t]*$", re.MULTILINE | re.DOTALL
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
    )


# The receipt: a heading, an oracle line naming what was driven (the four-way menu
# from a template is not a choice), and — unless the oracle is `not-applicable` — a
# seed and an assertion that are filled in. A heading over a template is the same
# silence the gate exists to catch.
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*verification\b", re.IGNORECASE | re.MULTILINE)
_ORACLES = ("cli", "ui", "substitute", "not-applicable")
_PLACEHOLDERS = frozenset({"", "-", "tbd", "todo", "n/a", "na", "none", "…", "..."})


def _line(body: str, name: str) -> str | None:
    """The value on a `**Name:** value` line, or None when there is no such line."""
    found = re.search(
        rf"^[ \t]*(?:[-*+|][ \t]*)?\**[ \t]*{name}\**[ \t]*:(?P<v>[^\n]*)$",
        body,
        re.IGNORECASE | re.MULTILINE,
    )
    return found.group("v") if found else None


def _filled(body: str, name: str) -> bool:
    value = _line(body, name)
    if value is None:
        return False
    value = value.strip().strip("*_`| ").strip()
    if re.fullmatch(r"<[^<>]*>", value):
        return False
    return value.strip("_ ").lower() not in _PLACEHOLDERS


def _oracles(body: str) -> set[str] | None:
    """The oracles named on the Oracle line — None when the line is a menu of all of them."""
    value = _line(body, "oracle")
    if value is None:
        return None
    named = {o for o in _ORACLES if re.search(rf"\b{o}\b", value, re.IGNORECASE)}
    return None if len(named) == len(_ORACLES) or not named else named


_WHERE = (
    "The receipt is not authored here: copy the `## Verification` block verbatim from the story "
    "plan (`docs/plans/<TICKET>-story.md` § Verification) into the PR body, and pass the body as "
    "`--body-file` so it can be read. It needs one `**Oracle:**` — cli | ui | substitute | "
    "not-applicable — and, unless that oracle is not-applicable, a filled `**Seed:**`, "
    "`**Asserted:**` and `**Not proven:**`.\n\n"
    "If the plan carries no such block, verification did not happen. Say so and stop; do not "
    "write a receipt for a run that did not take place.\n\n"
    "Contract: the `we` plugin's references/verification.md. Repo recipes: .weside/verify.md."
)


def _strip_heredocs(command: str) -> tuple[str, list[str]]:
    bodies: list[str] = []

    def take(match: re.Match[str]) -> str:
        bodies.append(match.group(3))
        return f"<<HEREDOC:{len(bodies) - 1}"

    return _HEREDOC.sub(take, command), bodies


def _written_here(argv: list[str], path: str, bodies: list[str]) -> str | None:
    """The heredoc this command redirects into `path` — a body written and used in one call."""
    for i, tok in enumerate(argv):
        if tok not in (">", ">>") or i + 1 >= len(argv):
            continue
        if os.path.basename(argv[i + 1]) != os.path.basename(path):
            continue
        for later in argv[i + 2 :]:
            found = re.fullmatch(r"<<HEREDOC:(\d+)", later)
            if found:
                return bodies[int(found.group(1))]
    return None


def _cwd_after_cd(argv: list[str], cwd: str | None) -> str | None:
    """Where a relative body-file actually lives after this command's own `cd`."""
    for i, tok in enumerate(argv):
        if tok.rstrip(";&|") in ("cd", "pushd") and i + 1 < len(argv):
            cwd = os.path.join(cwd or "", argv[i + 1].rstrip(";&|"))
    return cwd


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
    if tok in ("--body", "-b") and j + 1 < len(rest):
        return (rest[j + 1], False)
    if tok.startswith("--body="):
        return (tok.split("=", 1)[1], False)
    if tok in ("--body-file", "-F") and j + 1 < len(rest):
        return (rest[j + 1], True)
    if tok.startswith("--body-file="):
        return (tok.split("=", 1)[1], True)
    return None


def _pr_verb(argv: list[str]) -> tuple[str, list[str]] | None:
    """The `create`/`edit` verb and its remaining args — command position only."""
    for i, tok in enumerate(argv):
        bare = tok.lstrip("({")
        if (bare != "gh" and not bare.endswith("/gh")) or not (
            tok != bare or _starts_a_command(argv, i)
        ):
            continue
        if argv[i + 1 : i + 3] in (["pr", "create"], ["pr", "edit"]):
            return (argv[i + 2], argv[i + 3 :])
    return None


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
    verb, rest = found
    cwd = _cwd_after_cd(argv, cwd)
    if "--web" in rest:
        return (verb, None, True)

    seen = False
    body: str | None = None
    for j in range(len(rest)):
        arg = _body_arg(rest, j)
        if arg is None:
            continue
        value, is_file = arg
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


def _section(body: str) -> str | None:
    """The `## Verification` block itself — a template quoted elsewhere is not a receipt."""
    body = _FENCE.sub("", body)
    found = _HEADING.search(body)
    if not found:
        return None
    rest = body[found.end() :]
    nxt = re.search(r"^\s{0,3}#{1,6}\s", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def _receipt_problem(full: str) -> str | None:
    """What is wrong with this PR body, in the words the author needs."""
    body = _section(full)
    named = _oracles(body) if body else None
    if body is None or named is None:
        return (
            "This PR claims work is done without saying how that was observed. Unit tests "
            "do not count — they share the blind spots of whoever wrote the code."
        )
    if named == {"not-applicable"}:
        reason = re.sub(
            r"not[-\s]applicable", "", _line(body, "oracle") or "", flags=re.IGNORECASE
        )
        if len(reason.strip(" *_`—-:")) >= 3:
            return None
        return (
            "`not-applicable` is a legitimate answer and it carries its reason — say what "
            "about this change has no runtime behaviour to observe."
        )
    if not (_filled(body, "seed") and _filled(body, "asserted")):
        return (
            "This PR carries a `## Verification` heading over an unfilled receipt — the "
            "seed and the assertion are still the template's placeholders."
        )
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

    root = _repo_root(cwd)
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
