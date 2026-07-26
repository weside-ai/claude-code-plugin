#!/usr/bin/env python3
"""PreToolUse hook: a PR may not be opened without a verification receipt.

Green tests share the blind spots of whoever wrote the code. The receipt is the
one artefact that says something other than the author's own model confirmed the
behaviour — so it gates the moment the claim becomes public: `gh pr create`.

Deliberately narrow:
  * Only fires on `gh pr create` (and `gh pr edit --body*`), nothing else.
  * Only when the repo opted in — `.weside/config.json` → verification.required.
  * Blocks on ABSENCE, which is the observed failure mode. Anything it cannot
    parse it lets through: a hook that guesses wrong is worse than no hook.

Contract: `references/verification.md`. Repo recipes: `.weside/verify.md`.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

# `## Verification` … then a line naming the oracle. Both are required: a heading
# with nothing under it is the same silence the gate exists to catch.
_HEADING = re.compile(r"^\s{0,3}#{1,4}\s*verification\b", re.IGNORECASE | re.MULTILINE)
_ORACLE = re.compile(
    r"\b(oracle|verified\s+via|walked|substitut\w*|not[-\s]applicable)\b",
    re.IGNORECASE,
)

_HINT = """Add a `## Verification` block to the PR body, then retry:

## Verification

**Oracle:** cli | ui | substitute | not-applicable
**Seed:** <copy-pasteable command that puts the system in the asserted state>
**Asserted:** <endpoint + status + field, or route + label + ref>
**Not proven:** <what this oracle cannot show, and who owes it>

`not-applicable` is a legitimate answer — it just has to be said, with its
reason. What is not allowed is silence.

Contract: the `we` plugin's references/verification.md.
Repo recipes: .weside/verify.md."""


def _repo_root() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
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


def _body_of(command: str) -> tuple[bool, str | None]:
    """(is_pr_write, body_text_or_None).

    `--body-file` is read from disk; `--body` is taken inline. A body we cannot
    resolve returns None → the caller lets it through rather than guessing.
    """
    try:
        argv = shlex.split(command)
    except ValueError:
        return (False, None)

    # Find the `gh pr create|edit` head; a compound command may have prefixes.
    for i, tok in enumerate(argv):
        if tok == "gh" and argv[i + 1 : i + 3] in (["pr", "create"], ["pr", "edit"]):
            rest = argv[i + 3 :]
            break
    else:
        return (False, None)

    body: str | None = None
    for j, tok in enumerate(rest):
        if tok in ("--body", "-b") and j + 1 < len(rest):
            body = rest[j + 1]
        elif tok.startswith("--body="):
            body = tok.split("=", 1)[1]
        elif tok in ("--body-file", "-F") and j + 1 < len(rest):
            try:
                with open(rest[j + 1]) as fh:
                    body = fh.read()
            except Exception:
                return (True, None)
        elif tok.startswith("--body-file="):
            try:
                with open(tok.split("=", 1)[1]) as fh:
                    body = fh.read()
            except Exception:
                return (True, None)

    return (True, body)


def _receipt_missing(payload: dict) -> bool:
    """True only when this really is an armed PR write with no receipt."""
    if payload.get("tool_name") != "Bash":
        return False
    command = (payload.get("tool_input") or {}).get("command", "")
    if "gh" not in command or "pr" not in command:
        return False

    is_pr_write, body = _body_of(command)
    # A body we could not resolve, or an edit that carries none, is not a claim.
    if not is_pr_write or body is None:
        return False

    root = _repo_root()
    if not root or not _required(root):
        return False

    return not (_HEADING.search(body) and _ORACLE.search(body))


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    if not _receipt_missing(payload):
        return

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        "This PR claims work is done without saying how that was "
                        "observed. Unit tests do not count — they share the blind "
                        "spots of whoever wrote the code.\n\n" + _HINT
                    ),
                }
            }
        )
    )


if __name__ == "__main__":
    main()
