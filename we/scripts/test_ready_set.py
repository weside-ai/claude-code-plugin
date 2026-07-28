#!/usr/bin/env python3
"""Standalone unittest for compute_ready_set (WA-1231 Phase 1).

Run with: python3 we/scripts/test_ready_set.py
No pytest required.
"""

import tempfile
import unittest
from pathlib import Path

from orchestration import (
    _is_built_status,
    _load_epic_stories,
    _mirror_story_rows,
    _resolve_epic_identifiers,
    compute_ready_set,
)


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


_EPIC_WITH_MIRROR = """---
type: epic-plan
epic: demo
ticket: PROJ-1
---

# Epic: Demo

<!-- mirror:start (auto-generated) -->

| Key | Title | Status | Plan | Last activity |
|---|---|---|---|---|
| PROJ-10 | Shipped one | **Done** | \u2713 | 2026-07-01 |
| PROJ-11 | Not started | Backlog | \u2014 | 2026-07-01 |
| PROJ-12 | Also open | Backlog | \u2014 | 2026-07-01 |

<!-- mirror:end -->
"""

_REFINED_BODY = """---
type: story-plan
story: PROJ-11
epic: demo
status: draft
---

## Context

A context section long enough to clear the fifty-character floor the scan wants.

## Acceptance Criteria
1. **Given** a thing **When** it happens **Then** it works

### Phase 1: Do it
"""


class BuiltStatusTest(unittest.TestCase):
    """`built` is read from two vocabularies that must both work.

    A story plan writes `status: built`; a mirror row writes `**Done**`. Until
    2026-07-28 only the ticketing words were listed while the value came from
    plan frontmatter, so the comparison could never be true.
    """

    def test_plan_lifecycle_vocabulary(self):
        self.assertTrue(_is_built_status("built"))
        self.assertTrue(_is_built_status("shipped"))

    def test_ticketing_vocabulary_and_mirror_emphasis(self):
        self.assertTrue(_is_built_status("Done"))
        self.assertTrue(_is_built_status("  **Done** "))
        self.assertTrue(_is_built_status("In Review"))

    def test_open_statuses_are_not_built(self):
        for value in ("draft", "approved", "Backlog", "", None, 3):
            self.assertFalse(_is_built_status(value), value)


class MirrorRosterTest(unittest.TestCase):
    """A story with no plan file is UNREFINED, not absent.

    Globbing plan files alone returned `refinable: []` on every epic whose
    children had not been refined yet — so `--refine-ahead` had no producer
    queue and could never start.
    """

    def _plans(self, tmp):
        path = Path(tmp)
        (path / "demo-epic.md").write_text(_EPIC_WITH_MIRROR, encoding="utf-8")
        return path

    def test_mirror_rows_are_parsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = _mirror_story_rows("demo", self._plans(tmp))
        self.assertEqual(set(rows), {"PROJ-10", "PROJ-11", "PROJ-12"})
        self.assertTrue(_is_built_status(rows["PROJ-10"]))

    def test_planless_stories_become_refinable(self):
        with tempfile.TemporaryDirectory() as tmp:
            stories = _load_epic_stories("demo", str(self._plans(tmp)))
        by_key = {s["key"]: s for s in stories}
        self.assertEqual(set(by_key), {"PROJ-10", "PROJ-11", "PROJ-12"})
        self.assertTrue(by_key["PROJ-10"]["built"])
        self.assertFalse(by_key["PROJ-11"]["refined"])
        ready = compute_ready_set(stories)
        self.assertEqual(ready["refinable"], ["PROJ-11", "PROJ-12"])

    def test_a_plan_file_wins_over_its_mirror_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._plans(tmp)
            (path / "PROJ-11-story.md").write_text(_REFINED_BODY, encoding="utf-8")
            stories = _load_epic_stories("demo", str(path))
        by_key = {s["key"]: s for s in stories}
        self.assertEqual(len(stories), 3, "the mirror must not duplicate a story")
        self.assertTrue(by_key["PROJ-11"]["refined"])

    def test_no_epic_plan_leaves_the_roster_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_mirror_story_rows("demo", Path(tmp)), {})
