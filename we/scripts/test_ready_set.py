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

    def test_unrefined_no_deps_is_refinable(self):
        # Was test_no_refined_plan_held. With the refine lane, an unrefined story
        # with no unmet deps is the producer queue, not a dead held entry.
        result = compute_ready_set([_story("WA-1", refined=False)])
        self.assertEqual(result["ready"], [])
        self.assertEqual(result["refinable"], ["WA-1"])
        self.assertEqual(result["held"], [])

    def test_already_built_held(self):
        result = compute_ready_set([_story("WA-1", built=True)])
        self.assertEqual(result["ready"], [])
        self.assertEqual(result["refinable"], [])
        self.assertEqual(result["held"], [{"key": "WA-1", "reason": "already built"}])

    def test_built_is_checked_before_refined_split(self):
        # A built-but-unrefined story is "already built", never refinable
        # (built is evaluated before the refined/refinable carve-out).
        result = compute_ready_set([_story("WA-1", refined=False, built=True)])
        self.assertEqual(result["refinable"], [])
        self.assertEqual(result["held"], [{"key": "WA-1", "reason": "already built"}])

    def test_unrefined_with_refined_dep_is_refinable(self):
        # deps-refined mode: refine WA-2 against WA-1's plan/seam while WA-1 builds.
        # WA-1 is refined+not-built (ready); WA-2 is unrefined with dep WA-1 (refined) -> refinable.
        stories = [
            _story("WA-1", refined=True),
            _story("WA-2", refined=False, deps=["WA-1"]),
        ]
        result = compute_ready_set(stories)
        self.assertEqual(result["ready"], ["WA-1"])
        self.assertEqual(result["refinable"], ["WA-2"])
        self.assertEqual(result["held"], [])

    def test_unrefined_with_built_dep_is_refinable(self):
        # A built dep also satisfies the refine-dependency.
        stories = [
            _story("WA-1", built=True),
            _story("WA-2", refined=False, deps=["WA-1"]),
        ]
        result = compute_ready_set(stories)
        self.assertEqual(result["refinable"], ["WA-2"])
        self.assertEqual(result["held"], [{"key": "WA-1", "reason": "already built"}])

    def test_unrefined_with_unmet_dep_is_held_not_refinable(self):
        # WA-2 is unrefined and its dep WA-3 is neither refined nor built -> held,
        # NOT refinable (don't refine ahead of an unmet dep).
        stories = [
            _story("WA-2", refined=False, deps=["WA-3"]),
            _story("WA-3", refined=False),
        ]
        result = compute_ready_set(stories)
        self.assertEqual(result["ready"], [])
        # WA-3 has no deps -> refinable; WA-2 waits on WA-3.
        self.assertEqual(result["refinable"], ["WA-3"])
        self.assertEqual(result["held"], [{"key": "WA-2", "reason": "waiting on WA-3"}])

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
