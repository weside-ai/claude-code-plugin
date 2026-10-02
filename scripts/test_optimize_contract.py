#!/usr/bin/env python3
"""Contract lines of /we:optimize that a later edit must not quietly reverse."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "we" / "skills" / "optimize" / "SKILL.md"


def bullet(text: str, label: str) -> str:
    match = re.search(rf"^- \*\*{label}\.\*\*(.*?)(?=^- |^## )", text, re.MULTILINE | re.DOTALL)
    return " ".join(match.group(1).split()) if match else ""


class SunsetContractTest(unittest.TestCase):
    def check(self, text: str) -> None:
        sunset = bullet(text, "Sunset")
        self.assertIn("becomes a `remove` candidate", sunset, "Sunset bullet missing")
        self.assertNotIn(
            "never recurred",
            sunset,
            "an unrecurred, unmeasured change must not become a `remove` candidate: "
            "the change may be why the failure stopped",
        )
        unmeasured = bullet(text, "Unmeasured")
        for fragment in ("no `remove` candidate", "ablation", "`flag`", '"keep"'):
            self.assertIn(fragment, unmeasured, f"Unmeasured bullet lacks {fragment}")

    def test_skill_keeps_unmeasured_changes(self):
        self.check(SKILL.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
