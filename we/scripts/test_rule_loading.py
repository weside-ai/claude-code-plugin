#!/usr/bin/env python3
"""`rule_loading.py` against what Claude Code really loads.

`fixtures/rule-loading.json` holds verdicts recorded from real `claude -p` runs by
`probe-rule-loading.py`. When a fixture and the matcher disagree, the matcher is wrong.

Run with: python3 -m pytest -q we/scripts/test_rule_loading.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import rule_loading as rl  # noqa: E402 - the sibling module, found via the line above

FIXTURES = json.loads((HERE / "fixtures" / "rule-loading.json").read_text(encoding="utf-8"))


class GoldenFixtureTest(unittest.TestCase):
    @unittest.skipUnless(rl.yaml is not None, "PyYAML not installed")
    def test_matcher_agrees_with_every_recorded_probe(self):
        self.assertGreaterEqual(len(FIXTURES["cases"]), 30)
        for case in FIXTURES["cases"]:
            with self.subTest(case=case["id"]):
                rule = rl.parse_rule(case["rule"])
                self.assertEqual(rule.applies_to(case["read"]), case["loaded"], case["rule"])

    def test_every_fixture_names_its_claude_code_version(self):
        for case in FIXTURES["cases"]:
            with self.subTest(case=case["id"]):
                self.assertIn("Claude Code", case["claude_code"])
                self.assertRegex(case["recorded"], r"^\d{4}-\d{2}-\d{2}$")


class MatcherTest(unittest.TestCase):
    def test_glob_semantics(self):
        cases = [
            ("*.md", "docs/a.md", True),  # no slash: any depth
            ("src/*.py", "src/deep/mod.py", False),  # a slash anchors at the root
            ("dir/**/*.py", "dir/x.py", True),
            ("src/", "src/a.py", True),  # a directory pattern matches what is inside
            ("src/", "src", False),  # trailing slash: directories only
            ("!src/**", "src/a.py", False),
            ("photos \\[2024/**", "photos [2024/a.png", True),
        ]
        for pattern, path, expected in cases:
            with self.subTest(pattern=pattern, path=path):
                self.assertEqual(rl.pattern_matches(pattern, path), expected)

    def test_brace_expansion_count(self):
        self.assertEqual(len(rl.expand_braces("{a,b}/{c,d}/*.{ts,tsx}")), 8)

    def test_brace_budget_is_shared_across_a_rules_paths(self):
        first = "{a,b,c,d,e,f,g,h,i,j}/{a,b,c,d,e,f,g,h,i,j}/{a,b,c,d,e,f,g,h,i,j}"  # 1,000
        second = "src/*.{ts,tsx}"
        expanded = rl.expand_paths((first, second))
        self.assertEqual(len(expanded[first]), 1000)
        self.assertEqual(expanded[second], (second,))  # over the shared budget: whole
        self.assertFalse(rl.pattern_matches(second, "src/a.ts", (first, second)))
        self.assertTrue(rl.pattern_matches(second, "src/a.ts"))

    def test_many_brace_groups_count_before_expanding(self):
        pattern = "/".join(["{a,b}"] * 24)  # 16.7 million expansions if built
        start = time.perf_counter()
        self.assertEqual(rl.expand_braces(pattern), [pattern])
        self.assertLess(time.perf_counter() - start, 1.0)

    def test_comma_string_and_inline_list(self):
        self.assertEqual(
            rl.parse_rule('---\npaths: "src/*.{ts,tsx}, lib/**"\n---\n').patterns,
            ("src/*.{ts,tsx}", "lib/**"),
        )
        self.assertEqual(
            rl.parse_rule('---\npaths: ["src/**", "lib/*.py"]\n---\n').patterns,
            ("src/**", "lib/*.py"),
        )

    def test_lenient_parse_without_pyyaml_says_so(self):
        saved, rl.yaml = rl.yaml, None
        try:
            rule = rl.parse_rule('---\npaths:\n  - "src/**"\n---\n')
        finally:
            rl.yaml = saved
        self.assertEqual(rule.patterns, ("src/**",))
        self.assertFalse(rule.yaml_checked)


class CliTest(unittest.TestCase):
    def test_load_rules_cli_imports_the_module_from_anywhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude" / "rules").mkdir(parents=True)
            (root / ".claude" / "rules" / "a.md").write_text("# always\n")
            (root / ".claude" / "rules" / "b.md").write_text('---\npaths: "*.py"\n---\n# py\n')
            result = subprocess.run(
                [sys.executable, str(HERE / "load-rules.py"), "--root", tmp, "--list", "x/y.py"],
                capture_output=True,
                text=True,
                check=False,
                cwd=tmp,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ["always\t.claude/rules/a.md", "matched\t.claude/rules/b.md"],
        )


if __name__ == "__main__":
    unittest.main()
