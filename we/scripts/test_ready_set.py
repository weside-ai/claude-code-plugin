#!/usr/bin/env python3
"""Standalone unittest for compute_ready_set (WA-1231 Phase 1).

Run with: python3 we/scripts/test_ready_set.py
No pytest required.
"""

import unittest

from orchestration import compute_ready_set


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


if __name__ == "__main__":
    unittest.main()
