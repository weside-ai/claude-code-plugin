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


if __name__ == "__main__":
    unittest.main()
