#!/usr/bin/env python3
"""Red and green arms of the Claude review gate (`claude_review_gate.py`)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "claude_review_gate", Path(__file__).with_name("claude_review_gate.py")
)
gate = importlib.util.module_from_spec(_spec)
sys.modules["claude_review_gate"] = gate
_spec.loader.exec_module(gate)


class RequireTokenTest(unittest.TestCase):
    def test_missing_secret_is_red_and_names_the_admin_step(self):
        for environ in ({}, {"CLAUDE_CODE_OAUTH_TOKEN": ""}, {"CLAUDE_CODE_OAUTH_TOKEN": "  "}):
            with self.subTest(environ=environ):
                code, message = gate.require_token(environ)
                self.assertEqual(code, 1)
                self.assertIn("CLAUDE_CODE_OAUTH_TOKEN is not set", message)
                self.assertIn("claude setup-token", message)

    def test_present_secret_passes(self):
        self.assertEqual(gate.require_token({"CLAUDE_CODE_OAUTH_TOKEN": "x"})[0], 0)


class VerdictTest(unittest.TestCase):
    def test_blocking_and_warning_are_red(self):
        for level in ("BLOCKING", "WARNING"):
            with self.subTest(level=level):
                code, message = gate.verdict(f"## Code Review\n...\n<!-- VERDICT:{level} -->\n")
                self.assertEqual(code, 1)
                self.assertIn(f"verdict {level}", message)

    def test_pass_is_green(self):
        self.assertEqual(gate.verdict("## Code Review\nNo issues.\n<!-- VERDICT:PASS -->")[0], 0)

    def test_no_marker_is_red(self):
        code, message = gate.verdict("## Code Review\n**Verdict: ✅ PASS**\n")
        self.assertEqual(code, 1)
        self.assertIn("no `<!-- VERDICT:… -->` marker", message)

    def test_any_red_marker_wins_over_a_pass(self):
        body = "<!-- VERDICT:PASS -->\n...\n<!-- VERDICT:BLOCKING -->"
        self.assertEqual(gate.verdict(body)[0], 1)


QUOTA_SAMPLE = [  # run 37133981476, 2026-10-03: the account was out of quota
    {"type": "system", "subtype": "init"},
    {
        "type": "result",
        "subtype": "success",
        "is_error": True,
        "duration_ms": 540,
        "num_turns": 1,
        "total_cost_usd": 0,
        "modelUsage": {},
    },
]


BAD_TOKEN_SAMPLE = [  # `claude -p` with an invalid OAuth token, 2026-10-03
    {"type": "system", "subtype": "init"},
    {
        "type": "assistant",
        "error": "authentication_failed",
        "message": {
            "content": [
                {
                    "type": "text",
                    "text": "Failed to authenticate. API Error: 401 Invalid bearer token",
                }
            ]
        },
    },
    {
        "type": "result",
        "subtype": "success",
        "is_error": True,
        "duration_ms": 2461,
        "num_turns": 1,
        "total_cost_usd": 0,
        "modelUsage": {},
        "api_error_status": 401,
        "result": "Failed to authenticate. API Error: 401 Invalid bearer token",
    },
]


class ClassifyTest(unittest.TestCase):
    def test_shape_alone_is_refused_not_quota(self):
        self.assertEqual(gate.classify(QUOTA_SAMPLE), "refused")

    def test_probed_bad_token_is_auth(self):
        self.assertEqual(gate.classify(BAD_TOKEN_SAMPLE), "auth")

    def test_review_prose_about_oauth_is_not_auth(self):
        prose = {"type": "assistant", "message": {"content": "this diff touches OAuth /login"}}
        sample = [
            prose,
            {
                "type": "result",
                "is_error": True,
                "duration_ms": 90000,
                "total_cost_usd": 0.8,
                "modelUsage": {"m": {}},
                "result": "crashed",
            },
        ]
        self.assertEqual(gate.classify(sample), "other")

    def test_status_429_is_quota(self):
        self.assertEqual(gate.classify([{"type": "result", "api_error_status": 429}]), "quota")

    def test_auth_error_field_or_text_is_auth(self):
        by_field = [{"type": "assistant", "error": "authentication_failed", "message": {}}]
        by_text = [
            {"type": "result", "is_error": True, "result": "Invalid API key · Please run /login"}
        ]
        for sample in (by_field, by_text, by_text + QUOTA_SAMPLE):  # text beats shape
            with self.subTest(sample=sample):
                self.assertEqual(gate.classify(sample), "auth")

    def test_rate_limit_text_is_quota(self):
        sample = [
            {
                "type": "result",
                "is_error": True,
                "total_cost_usd": 1.2,
                "modelUsage": {"m": {}},
                "result": "Claude AI usage limit reached",
            }
        ]
        self.assertEqual(gate.classify(sample), "quota")

    def test_long_costly_failure_is_other(self):
        sample = [
            {
                "type": "result",
                "is_error": True,
                "duration_ms": 90000,
                "total_cost_usd": 0.8,
                "modelUsage": {"m": {}},
                "result": "tool crashed",
            }
        ]
        self.assertEqual(gate.classify(sample), "other")

    def test_missing_file_is_red_other(self):
        code, message = gate.classify_file("/nonexistent")
        self.assertEqual(code, 1)
        self.assertIn("(other): action error", message)


if __name__ == "__main__":
    unittest.main()
