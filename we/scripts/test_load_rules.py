#!/usr/bin/env python3
"""The `paths:` matcher shared by load-rules.py and check-instruction-budget.py.

Pins Claude Code's documented glob semantics (memory.md § Path-specific rules): root-anchored
`*`, `**` across directories, brace expansion, the comma-separated string form, and an invalid
`[` that matches nothing.

Run with: python3 -m pytest -q we/scripts/test_load_rules.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "we_load_rules_test", Path(__file__).with_name("load-rules.py")
)
lr = importlib.util.module_from_spec(_spec)
sys.modules["we_load_rules_test"] = lr
_spec.loader.exec_module(lr)


class MatcherTest(unittest.TestCase):
    def test_glob_semantics(self):
        cases = [
            ("*.md", "README.md", True),
            ("*.md", "docs/a.md", False),  # root only, per the docs' table
            ("**/*.ts", "a.ts", True),
            ("**/*.ts", "x/y/a.ts", True),
            ("src/**/*", "src/a/b.py", True),
            ("src/**/*.{ts,tsx}", "src/a.tsx", True),
            ("src/**/*.{ts,tsx}", "src/a.js", False),
            ("{a,b}/{c,d}/*.{ts,tsx}", "b/d/x.ts", True),
            ("photos [2024/**", "photos [2024/a.png", False),
            ("photos \\[2024/**", "photos [2024/a.png", True),
        ]
        for pattern, path, expected in cases:
            with self.subTest(pattern=pattern, path=path):
                self.assertEqual(lr._matches(pattern, path), expected)

    def test_brace_expansion_count(self):
        self.assertEqual(len(lr.expand_braces("{a,b}/{c,d}/*.{ts,tsx}")), 8)

    def test_brace_budget_leaves_pattern_unexpanded(self):
        pattern = "{a,b,c,d,e,f,g,h,i,j}/{a,b,c,d,e,f,g,h,i,j}/{a,b,c,d,e,f,g,h,i,j}/{x,y}"
        self.assertEqual(lr.expand_braces(pattern), [pattern])

    def test_comma_separated_paths_string_is_scoped_not_always_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            rule = Path(tmp) / "r.md"
            rule.write_text('---\npaths: "src/*.{ts,tsx}, lib/**"\n---\n# R\n')
            loaded = lr._load_rule(rule)
        self.assertFalse(loaded.is_always_on)
        self.assertEqual(loaded.patterns, ("src/*.{ts,tsx}", "lib/**"))

    def test_inline_list_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            rule = Path(tmp) / "r.md"
            rule.write_text('---\npaths: ["src/**", "lib/*.py"]\n---\n# R\n')
            loaded = lr._load_rule(rule)
        self.assertEqual(loaded.patterns, ("src/**", "lib/*.py"))


if __name__ == "__main__":
    unittest.main()
