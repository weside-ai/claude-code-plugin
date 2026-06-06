#!/usr/bin/env python3
"""Standalone unittest for compute_ready_set (WA-1231 Phase 1).

Run with: python3 we/scripts/test_ready_set.py
No pytest required.
"""

import tempfile
import unittest
from pathlib import Path

from orchestration import _resolve_epic_identifiers, compute_ready_set


def _story(key, refined=True, built=False, deps=None):
    return {"key": key, "refined": refined, "built": built, "deps": deps or []}


class ComputeReadySetTest(unittest.TestCase):
    def test_happy_path_one_ready(self):
        result = compute_ready_set([_story("WA-1")])
        self.assertEqual(result["ready"], ["WA-1"])
        self.assertEqual(result["held"], [])

    def test_no_refined_plan_held(self):
        result = compute_ready_set([_story("WA-1", refined=False)])
        self.assertEqual(result["ready"], [])
        self.assertEqual(result["held"], [{"key": "WA-1", "reason": "no refined plan"}])

    def test_already_built_held(self):
        result = compute_ready_set([_story("WA-1", built=True)])
        self.assertEqual(result["ready"], [])
        self.assertEqual(result["held"], [{"key": "WA-1", "reason": "already built"}])

    def test_unmet_dependency_held(self):
        result = compute_ready_set([_story("WA-2", deps=["WA-1"])])
        self.assertEqual(result["ready"], [])
        self.assertEqual(result["held"], [{"key": "WA-2", "reason": "waiting on WA-1"}])

    def test_cap_hit(self):
        stories = [_story("WA-1"), _story("WA-2"), _story("WA-3")]
        result = compute_ready_set(stories, cap=2)
        self.assertEqual(result["ready"], ["WA-1", "WA-2"])
        self.assertEqual(result["held"], [{"key": "WA-3", "reason": "cap reached"}])

    def test_built_dependency_satisfies_dep(self):
        stories = [
            _story("WA-1", built=True),
            _story("WA-2", deps=["WA-1"]),
        ]
        result = compute_ready_set(stories)
        self.assertEqual(result["ready"], ["WA-2"])
        self.assertEqual(result["held"], [{"key": "WA-1", "reason": "already built"}])


class ResolveEpicIdentifiersTest(unittest.TestCase):
    """Regression: an epic plan is named by slug (<slug>-epic.md), so resolving
    by the ticketing KEY must still find it via frontmatter, not just by filename."""

    def _make_epic_plan(self, dir_path, slug, ticket):
        (Path(dir_path) / f"{slug}-epic.md").write_text(
            f"---\nepic: {slug}\nticket: {ticket}\nstatus: draft\n---\n# Epic\n",
            encoding="utf-8",
        )

    def test_resolves_by_key_against_slug_named_file(self):
        with tempfile.TemporaryDirectory() as d:
            self._make_epic_plan(d, "docs-portal", "WA-1263")
            ids = _resolve_epic_identifiers("WA-1263", Path(d))
            # The key must pull in the slug so slug-keyed stories are matched.
            self.assertIn("docs-portal", ids)
            self.assertIn("WA-1263", ids)

    def test_resolves_by_slug(self):
        with tempfile.TemporaryDirectory() as d:
            self._make_epic_plan(d, "docs-portal", "WA-1263")
            ids = _resolve_epic_identifiers("docs-portal", Path(d))
            self.assertIn("docs-portal", ids)
            self.assertIn("WA-1263", ids)

    def test_unrelated_epic_not_pulled_in(self):
        with tempfile.TemporaryDirectory() as d:
            self._make_epic_plan(d, "docs-portal", "WA-1263")
            self._make_epic_plan(d, "billing", "WA-2000")
            ids = _resolve_epic_identifiers("WA-1263", Path(d))
            self.assertNotIn("billing", ids)
            self.assertNotIn("WA-2000", ids)


if __name__ == "__main__":
    unittest.main()
