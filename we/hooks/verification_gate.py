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
  * One transport. A PR opened through an MCP tool or `gh pr create --web` never
    reaches this code; the gate is armed against one spelling of the action.

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
    r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)^\t*\2[ \t]*$", re.MULTILINE | re.DOTALL
)

# Tokens after which the next word starts a new command.
_SEPARATORS = frozenset({"&&", "||", ";", "|", "&", "(", ")", "{", "}", "then", "do", "else", "!"})

# The receipt: a heading, ONE named oracle (not the menu of them), and — unless the
# oracle is `not-applicable` — a seed and an assertion that are filled in. A heading
# with a template under it is the same silence the gate exists to catch.
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*verification\b", re.IGNORECASE | re.MULTILINE)
_ORACLE = re.compile(
    r"^[ \t]*\**\s*oracle\**\s*:\s*\**\s*(cli|ui|substitute|not[-\s]applicable)\b[^|\n]*$",
    re.IGNORECASE | re.MULTILINE,
)


def _field(name: str) -> re.Pattern[str]:
    """`**Name:** value`, where value is present and not a `<placeholder>`."""
    return re.compile(
        rf"^[ \t]*\**\s*{name}\**\s*:\s*(?![\s*]*<)(\S.*)$", re.IGNORECASE | re.MULTILINE
    )


_SEED = _field("seed")
_ASSERTED = _field("asserted")

_WHERE = (
    "The receipt is not authored here: copy the `## Verification` block verbatim from the story "
    "plan (`docs/plans/<TICKET>-story.md` § Verification) into the PR body, and pass the body as "
    "`--body-file` so it can be read. It needs one `**Oracle:**` — cli | ui | substitute | "
    "not-applicable — and, unless that oracle is not-applicable, a filled `**Seed:**` and "
    "`**Asserted:**`.\n\n"
    "If the plan carries no such block, verification did not happen. Say so and stop; do not "
    "write a receipt for a run that did not take place.\n\n"
    "Contract: the `we` plugin's references/verification.md. Repo recipes: .weside/verify.md."
)


def _strip_heredocs(command: str) -> tuple[str, list[str]]:
    bodies: list[str] = []

    def take(match: re.Match[str]) -> str:
        bodies.append(match.group(3))
        return "<<HEREDOC"

    return _HEREDOC.sub(take, command), bodies


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
        if tok != "gh" or (i and argv[i - 1] not in _SEPARATORS):
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
    try:
        argv = shlex.split(stripped)
    except ValueError:
        return (None, None, False)

    found = _pr_verb(argv)
    if found is None:
        return (None, None, False)
    verb, rest = found

    seen = False
    body: str | None = None
    for j in range(len(rest)):
        arg = _body_arg(rest, j)
        if arg is None:
            continue
        value, is_file = arg
        seen = True
        if is_file:
            try:
                with open(os.path.join(cwd or "", value)) as fh:
                    body = fh.read()
            except Exception:
                body = None
        elif "$(" in value or "`" in value:
            # An unexpanded substitution — PreToolUse runs before the shell. The
            # one shape we can still read is the heredoc it was fed from.
            body = heredocs[0] if len(heredocs) == 1 else None
        else:
            body = value

    return (verb, body, seen)


def _receipt_problem(body: str) -> str | None:
    """What is wrong with this PR body, in the words the author needs."""
    if not _HEADING.search(body) or not (found := _ORACLE.search(body)):
        return (
            "This PR claims work is done without saying how that was observed. Unit tests "
            "do not count — they share the blind spots of whoever wrote the code."
        )
    if found.group(1).lower().replace(" ", "-") == "not-applicable":
        return None
    if not (_SEED.search(body) and _ASSERTED.search(body)):
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
