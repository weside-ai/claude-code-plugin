#!/usr/bin/env python3
"""The decisions of `.github/workflows/claude-code-review.yml`, testable outside Actions.

  require-token   exit 1 with an `::error::` naming the admin step when the OAuth secret is empty
  verdict         read this run's review comment on stdin; exit 1 on a BLOCKING or WARNING
                  verdict or when the comment carries no verdict marker
  classify FILE   name why the review action ended without a verdict, from its execution file
                  (the SDK message list): auth, quota or other; always exit 1

Stdlib only, Python 3.9+.
"""

from __future__ import annotations

import argparse
import json
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


AUTH_RE = re.compile(r"\b401\b|invalid (api key|bearer|x-api-key)|oauth|/login|authenticat", re.I)
QUOTA_RE = re.compile(r"\b429\b|usage limit|rate.?limit|quota|overloaded|credit balance", re.I)
REASONS = {
    "auth": "token invalid: regenerate with `claude setup-token` and update CLAUDE_CODE_OAUTH_TOKEN",
    "quota": "subscription quota/rate limit: re-run later, nothing to fix",
    "other": "action error: see the run log",
}


def classify(messages: object) -> str:
    """`auth`, `quota` or `other` for a run that produced no verdict.

    The SDK marks an API failure on the assistant message (`error`); the CLI puts its text in
    the result. A run that ended in under 5 s with zero cost and no model usage never reached
    the model: the subscription refused it (run 37133981476: 540 ms, $0, `modelUsage: {}`).
    """
    if not isinstance(messages, list):
        return "other"
    dicts = [m for m in messages if isinstance(m, dict)]
    errors = {str(m.get("error", "")) for m in dicts if m.get("type") == "assistant"}
    text = " ".join(
        json.dumps(m.get("result", "")) + json.dumps(m.get("message", ""))
        for m in dicts
        if m.get("type") in ("result", "assistant")
    )
    if "authentication_failed" in errors or AUTH_RE.search(text):
        return "auth"
    if errors & {"rate_limit", "billing_error"} or QUOTA_RE.search(text):
        return "quota"
    result = next((m for m in reversed(dicts) if m.get("type") == "result"), None)
    if (
        result
        and result.get("is_error")
        and not result.get("total_cost_usd")
        and not result.get("modelUsage")
        and int(result.get("duration_ms") or 0) < 5000
    ):
        return "quota"
    return "other"


def classify_file(path: str) -> tuple[int, str]:
    try:
        with open(path, encoding="utf-8") as fh:
            messages = json.load(fh)
    except (OSError, ValueError):
        messages = None
    kind = classify(messages)
    return 1, f"Claude review produced no verdict ({kind}): {REASONS[kind]}."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["require-token", "verdict", "classify"])
    parser.add_argument("file", nargs="?", default="")
    args = parser.parse_args(argv)
    if args.command == "classify":
        code, message = classify_file(args.file)
    elif args.command == "require-token":
        code, message = require_token(dict(os.environ))
    else:
        code, message = verdict(sys.stdin.read())
    print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
