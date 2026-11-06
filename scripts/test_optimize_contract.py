#!/usr/bin/env python3
"""Contract lines of /we:optimize that a later edit must not quietly reverse."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

WE = Path(__file__).resolve().parent.parent / "we"
SKILL = WE / "skills" / "optimize" / "SKILL.md"
STORE = WE / "references" / "optimization-store.md"


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
        for fragment in ("no `remove` candidate", "ablation", "`review_by` moves forward"):
            self.assertIn(fragment, unmeasured, f"Unmeasured bullet lacks {fragment}")

    def test_skill_keeps_unmeasured_changes(self):
        self.check(SKILL.read_text(encoding="utf-8"))


class NothingIsPutOffTest(unittest.TestCase):
    """Every candidate ends applied or rejected: a put-off entry comes back every run (owner,
    2026-10-12). Not presented or not chosen is rejected."""

    def test_no_deferred_decision(self):
        for path in (SKILL, STORE):
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r"\bdefer", text, re.IGNORECASE),
                f"{path.name} still offers to defer a candidate",
            )

    def test_unchosen_is_rejected(self):
        text = " ".join(SKILL.read_text(encoding="utf-8").split())
        self.assertIn("not chosen → `rejected`", text)


if __name__ == "__main__":
    unittest.main()


class FeedbackSourcesContractTest(unittest.TestCase):
    """Other repos that run the plugin are named sources: plugin findings only, no foreign text."""

    def test_skill_reads_the_listed_repos_read_only(self):
        text = " ".join(SKILL.read_text(encoding="utf-8").split())
        self.assertIn("feedback-sources.md", text)
        self.assertIn("read-only, key, target and fact only", text)

    def test_store_filters_plugin_findings_under_the_privacy_guard(self):
        text = " ".join(STORE.read_text(encoding="utf-8").split())
        for fragment in (
            "`target_repo: plugin` only",
            "never a quote, a diff or a transcript",
            "references/privacy-guard.md",
            "read, never written",
        ):
            self.assertIn(fragment, text)
