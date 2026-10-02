#!/usr/bin/env python3
"""The decisions of `.github/workflows/claude-code-review.yml`, testable outside Actions.

  require-token   exit 1 with an `::error::` naming the admin step when the OAuth secret is empty
  verdict         read this run's review comment on stdin; exit 1 on a BLOCKING or WARNING
                  verdict or when the comment carries no verdict marker

Stdlib only, Python 3.9+.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"
MISSING_TOKEN = (
    "::error::The repository secret CLAUDE_CODE_OAUTH_TOKEN is not set, so no Claude review ran. "
    "A maintainer creates it with `claude setup-token` and stores it under Settings → Secrets "
    "and variables → Actions."
)
VERDICT_RE = re.compile(r"<!--\s*VERDICT:(BLOCKING|WARNING|PASS)\s*-->")


def require_token(environ: dict[str, str]) -> tuple[int, str]:
    if environ.get(TOKEN_ENV, "").strip():
        return 0, "CLAUDE_CODE_OAUTH_TOKEN is set."
    return 1, MISSING_TOKEN


def verdict(body: str) -> tuple[int, str]:
    found = VERDICT_RE.findall(body)
    if not found:
        return 1, (
            "::error::This run's review comment has no `<!-- VERDICT:… -->` marker — "
            "the review is incomplete; re-run the job."
        )
    for level in ("BLOCKING", "WARNING"):  # fail closed: any red marker wins
        if level in found:
            return (
                1,
                f"::error::Claude review verdict {level} — fix the findings, then push again.",
            )
    return 0, "Claude review: PASS."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["require-token", "verdict"])
    args = parser.parse_args(argv)
    if args.command == "require-token":
        code, message = require_token(dict(os.environ))
    else:
        code, message = verdict(sys.stdin.read())
    print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
