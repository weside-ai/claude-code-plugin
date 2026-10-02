#!/usr/bin/env python3
"""Red arms for check-instruction-budget.py: one fixture per check that must fail, with
the message asserted, plus a clean fixture that must exit 0.

Run with: python3 -m pytest -q we/scripts/test_check_instruction_budget.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("check-instruction-budget.py")

try:
    import yaml  # noqa: F401

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def lines(n: int, prefix: str = "line") -> str:
    return "".join(f"{prefix} {i}\n" for i in range(n))


class GateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.write("src/app.py", "print('hi')\n")
        self.write("AGENTS.md", "# Repo\n\nShort.\n")

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_gate(self) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode, result.stdout

    def assert_red(self, check: str, fragment: str) -> None:
        code, out = self.run_gate()
        self.assertEqual(code, 1, out)
        self.assertIn(f"[{check}]", out)
        self.assertIn(fragment, out)

    def test_clean_fixture_passes(self):
        self.write(".claude/rules/py.md", '---\npaths:\n  - "src/**/*.{py,pyi}"\n---\n# Py\n')
        self.write(".claude/rules/always.md", "# Always\n\nOne rule.\n")
        self.write(
            ".claude/skills/demo/SKILL.md",
            '---\nname: demo\ndescription: Does a demo. Triggers: "demo".\n---\n'
            "Read [the guide](references/guide.md).\n",
        )
        self.write(".claude/skills/demo/references/guide.md", "# Guide\n" + lines(20))
        self.write(
            ".claude/agents/helper.md", "---\nname: helper\ndescription: Helps.\n---\nBody\n"
        )
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)
        self.assertIn("0 error(s)", out)

    def test_unconditional_rule_over_200_lines(self):
        self.write(".claude/rules/big.md", "# Big\n" + lines(205))
        self.assert_red("rule-lines", "206 lines, unconditional rule max 200")

    def test_unconditional_rules_total_over_budget(self):
        for name in ("a", "b", "c", "d"):
            self.write(f".claude/rules/{name}.md", lines(160))
        self.assert_red("rules-total", "unconditional rules total 640 lines > budget 600")

    def test_budget_override_from_config(self):
        self.write(".claude/rules/mid.md", lines(150))
        self.write(
            ".weside/config.json", json.dumps({"optimization": {"budget": {"rule_lines": 100}}})
        )
        self.assert_red("rule-lines", "150 lines, unconditional rule max 100")

    def test_instruction_file_over_200_lines(self):
        self.write("AGENTS.md", lines(201))
        self.assert_red("instruction-file-lines", "AGENTS.md: 201 lines > 200")

    def test_globs_key_is_flagged(self):
        self.write(".claude/rules/g.md", '---\nglobs: "src/**"\n---\n# G\n')
        self.assert_red("rule-globs", "`globs:` is ignored by Claude Code")

    @unittest.skipUnless(HAS_YAML, "PyYAML not installed")
    def test_rule_with_broken_yaml_is_an_error(self):
        self.write(".claude/rules/y.md", "---\npaths: [src/**\n---\n# Y\n")
        self.assert_red("rule-yaml", "the rule loads unconditionally")

    @unittest.skipUnless(HAS_YAML, "PyYAML not installed")
    def test_skill_with_lenient_yaml_is_only_a_warning(self):
        self.write(
            ".claude/skills/s/SKILL.md",
            '---\nname: s\ndescription: Does s. Triggers: "s".\n---\nBody\n',
        )
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)
        self.assertIn("[skill-yaml]", out)
        self.assertIn("still loads it", out)

    def test_paths_glob_matching_nothing(self):
        self.write(".claude/rules/dead.md", '---\npaths:\n  - "lib/**/*.rb"\n---\n# Dead\n')
        self.assert_red("rule-paths-unmatched", "the rule never loads")

    def test_one_dead_glob_among_live_ones_is_a_warning(self):
        self.write(
            ".claude/rules/mixed.md",
            '---\npaths:\n  - "src/**/*.py"\n  - "lib/**/*.rb"\n---\n# Mixed\n',
        )
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)
        self.assertIn("`paths:` glob matches no file: lib/**/*.rb", out)

    def test_brace_expansion_is_not_flagged(self):
        self.write(".claude/rules/b.md", '---\npaths: "src/*.{py,ts}"\n---\n# B\n')
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)
        self.assertNotIn("rule-paths-unmatched", out)

    def test_pointer_target_rule_without_contents(self):
        self.write(".claude/rules/long.md", '---\npaths:\n  - "src/**"\n---\n' + lines(120))
        self.write("AGENTS.md", "# Repo\n\nDetail: `.claude/rules/long.md`.\n")
        self.assert_red("contents-missing", "pointed at by another instruction file")

    def test_pointer_target_with_contents_passes(self):
        self.write(
            ".claude/rules/long.md",
            '---\npaths:\n  - "src/**"\n---\n# Long\n\n## Contents\n\nA · B\n' + lines(120),
        )
        self.write("AGENTS.md", "# Repo\n\nDetail: `.claude/rules/long.md`.\n")
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)

    def test_skill_over_500_lines(self):
        self.write(
            ".claude/skills/s/SKILL.md", "---\nname: s\ndescription: S.\n---\n" + lines(500)
        )
        self.assert_red("skill-lines", "504 lines > 500")

    def test_skill_listing_over_1536_chars(self):
        desc = "x" * 1500
        self.write(
            ".claude/skills/s/SKILL.md",
            f"---\nname: s\ndescription: {desc}\nwhen_to_use: {'y' * 40}\n---\nBody\n",
        )
        self.assert_red("skill-listing", "description + when_to_use 1540 chars > 1536")

    def test_skill_reference_over_100_lines_without_contents(self):
        self.write(
            ".claude/skills/s/SKILL.md",
            "---\nname: s\ndescription: S.\n---\nSee `references/big.md`.\n",
        )
        self.write(".claude/skills/s/references/big.md", lines(101))
        self.assert_red("contents-missing", "101 lines, read by .claude/skills/s/SKILL.md")

    def test_skill_reference_two_levels_deep(self):
        self.write(
            ".claude/skills/s/SKILL.md",
            "---\nname: s\ndescription: S.\n---\nSee [a](a.md).\n",
        )
        self.write(".claude/skills/s/a.md", "See [b](b.md).\n")
        self.write(".claude/skills/s/b.md", "Deep.\n")
        self.assert_red("skill-nested-ref", "reached only through .claude/skills/s/a.md")

    def test_agent_without_description(self):
        self.write(".claude/agents/x.md", "---\nname: x\n---\nBody\n")
        self.assert_red("agent-frontmatter", "needs `name` and `description`")

    def test_combined_agent_descriptions_over_budget(self):
        for i in range(5):
            self.write(
                f".claude/agents/a{i}.md", f"---\nname: a{i}\ndescription: {'w' * 13000}\n---\n"
            )
        self.assert_red("agent-descriptions", "tokens > 15000")

    def test_configured_exclude_skips_a_tree(self):
        self.write(
            "content/skills/x/SKILL.md", "---\nname: x\ndescription: X.\n---\n" + lines(600)
        )
        self.assert_red("skill-lines", "content/skills/x/SKILL.md")
        self.write(".weside/config.json", json.dumps({"optimization": {"exclude": ["content"]}}))
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
