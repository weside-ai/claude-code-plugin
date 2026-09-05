#!/usr/bin/env python3
"""Standalone unittest for the evidence-based epic state model.

Two halves, deliberately separate:

* ``ComputeEpicStateTest`` — the pure function. No git, no DB, no files.
* ``GitStoryStateTest`` / ``LoadEpicStateTest`` — the evidence gatherers, against
  a real temporary git repo, because the whole point of this model is that git
  is consulted rather than trusted bookkeeping.

Run with: python3 we/scripts/test_epic_state.py
No pytest required.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from orchestration import (
    _branches_for_key,
    _git_branch_index,
    _git_story_state,
    _is_built_status,
    _load_epic_state,
    _resolve_base,
    compute_epic_state,
)


def _story(key, **evidence):
    base = {
        "key": key,
        "shipped": False,
        "merged": False,
        "branch": None,
        "ahead": False,
        "refined": True,
        "plan_exists": True,
        "deps": [],
        "signals": [],
    }
    base.update(evidence)
    return base


def _states(result):
    return {row["key"]: row["state"] for row in result["stories"]}


def _actions(result):
    return {row["key"]: row["next_action"] for row in result["stories"]}


class ComputeEpicStateTest(unittest.TestCase):
    """The ladder, the actions, the caps."""

    def test_refined_story_develops(self):
        result = compute_epic_state([_story("PROJ-1")])
        self.assertEqual(_states(result), {"PROJ-1": "refined"})
        self.assertEqual(result["dispatch"]["develop"], ["PROJ-1"])

    def test_no_plan_is_an_idea_and_refines(self):
        result = compute_epic_state([_story("PROJ-1", refined=False, plan_exists=False)])
        self.assertEqual(_states(result), {"PROJ-1": "idea"})
        self.assertEqual(result["dispatch"]["refine"], ["PROJ-1"])

    def test_plan_that_fails_dor_is_a_draft_and_still_refines(self):
        result = compute_epic_state([_story("PROJ-1", refined=False, plan_exists=True)])
        self.assertEqual(_states(result), {"PROJ-1": "draft"})
        self.assertEqual(result["dispatch"]["refine"], ["PROJ-1"])

    def test_branch_with_commits_integrates(self):
        result = compute_epic_state([_story("PROJ-1", branch="feat/PROJ-1-work", ahead=True)])
        self.assertEqual(_states(result), {"PROJ-1": "built"})
        self.assertEqual(result["dispatch"]["integrate"], ["PROJ-1"])

    def test_branch_without_commits_is_not_built(self):
        # A worktree was created and nothing was written yet — that is not work.
        result = compute_epic_state([_story("PROJ-1", branch="feat/PROJ-1-work", ahead=False)])
        self.assertEqual(_states(result), {"PROJ-1": "refined"})

    def test_merged_branch_outranks_built(self):
        result = compute_epic_state(
            [_story("PROJ-1", branch="feat/PROJ-1-work", ahead=True, merged=True)]
        )
        self.assertEqual(_states(result), {"PROJ-1": "integrated"})
        self.assertIsNone(_actions(result)["PROJ-1"])

    def test_shipped_outranks_everything(self):
        result = compute_epic_state(
            [_story("PROJ-1", shipped=True, merged=True, branch="feat/PROJ-1-work", ahead=True)]
        )
        self.assertEqual(_states(result), {"PROJ-1": "shipped"})

    def test_built_without_a_plan_is_signalled_not_swallowed(self):
        # The regression this signal exists for: nothing to check the integration
        # gate's acceptance criteria against.
        result = compute_epic_state(
            [_story("PROJ-1", refined=False, plan_exists=False, branch="b", ahead=True)]
        )
        self.assertEqual(_states(result), {"PROJ-1": "built"})
        self.assertIn("built-without-plan", result["stories"][0]["signals"])

    def test_a_refined_story_is_never_re_refined(self):
        result = compute_epic_state([_story("PROJ-1", refined=True)])
        self.assertEqual(result["dispatch"]["refine"], [])

    def test_refine_and_develop_dispatch_in_the_same_pass(self):
        # The whole reason for the redesign: one epic, two kinds of story, one run.
        result = compute_epic_state(
            [_story("PROJ-1", refined=True), _story("PROJ-2", refined=False, plan_exists=False)]
        )
        self.assertEqual(result["dispatch"]["develop"], ["PROJ-1"])
        self.assertEqual(result["dispatch"]["refine"], ["PROJ-2"])

    def test_develop_waits_for_an_unbuilt_dependency(self):
        result = compute_epic_state(
            [_story("PROJ-1", refined=False, plan_exists=False), _story("PROJ-2", deps=["PROJ-1"])]
        )
        self.assertIsNone(_actions(result)["PROJ-2"])
        self.assertEqual(
            next(w for w in result["waiting"] if w["key"] == "PROJ-2")["reason"],
            "waiting on PROJ-1 (idea)",
        )

    def test_develop_dependency_is_met_once_the_branch_exists(self):
        # Not `integrated`: the Lead merges finished branches as they arrive, so
        # waiting for the merge would serialise every chain.
        result = compute_epic_state(
            [_story("PROJ-1", branch="b", ahead=True), _story("PROJ-2", deps=["PROJ-1"])]
        )
        self.assertEqual(_actions(result)["PROJ-2"], "DEVELOP")

    def test_refine_may_run_against_a_refined_dependency(self):
        result = compute_epic_state(
            [
                _story("PROJ-1", refined=True),
                _story("PROJ-2", refined=False, plan_exists=False, deps=["PROJ-1"]),
            ]
        )
        self.assertEqual(_actions(result)["PROJ-2"], "REFINE")

    def test_refine_waits_for_an_unplanned_dependency(self):
        result = compute_epic_state(
            [
                _story("PROJ-1", refined=False, plan_exists=False),
                _story("PROJ-2", refined=False, plan_exists=False, deps=["PROJ-1"]),
            ]
        )
        self.assertEqual(_actions(result)["PROJ-1"], "REFINE")
        self.assertIsNone(_actions(result)["PROJ-2"])

    def test_human_signal_routes_to_the_decision_queue(self):
        result = compute_epic_state(
            [
                _story(
                    "PROJ-1", refined=False, plan_exists=False, signals=["open question in ticket"]
                )
            ]
        )
        self.assertEqual(result["dispatch"]["refine"], [])
        self.assertEqual(
            result["decisions"], [{"key": "PROJ-1", "reason": "open question in ticket"}]
        )

    def test_in_flight_stories_are_not_offered_again(self):
        # The evidence cannot know this — a dispatch is not an outcome.
        result = compute_epic_state([_story("PROJ-1")], in_flight=["PROJ-1"])
        self.assertEqual(result["dispatch"]["develop"], [])
        self.assertEqual(result["waiting"], [{"key": "PROJ-1", "reason": "in flight"}])
        self.assertEqual(result["in_flight"], ["PROJ-1"])

    def test_caps_hold_the_overflow_with_a_reason(self):
        stories = [_story(f"PROJ-{i}") for i in range(1, 5)]
        result = compute_epic_state(stories, caps={"develop": 2})
        self.assertEqual(result["dispatch"]["develop"], ["PROJ-1", "PROJ-2"])
        self.assertEqual(
            [w["reason"] for w in result["waiting"]],
            ["develop cap reached", "develop cap reached"],
        )

    def test_refine_cap_is_wider_than_develop(self):
        stories = [_story(f"PROJ-{i}", refined=False, plan_exists=False) for i in range(1, 6)]
        result = compute_epic_state(stories)
        self.assertEqual(len(result["dispatch"]["refine"]), 3)

    def test_integrate_is_serial(self):
        stories = [_story(f"PROJ-{i}", branch=f"b{i}", ahead=True) for i in range(1, 4)]
        result = compute_epic_state(stories)
        self.assertEqual(len(result["dispatch"]["integrate"]), 1)

    def test_stories_are_processed_in_key_order(self):
        result = compute_epic_state([_story("PROJ-9"), _story("PROJ-2")], caps={"develop": 1})
        self.assertEqual(result["dispatch"]["develop"], ["PROJ-2"])


class BuiltStatusVocabularyTest(unittest.TestCase):
    """Carried over from test_ready_set.py — the 2026-07-28 regression.

    `_BUILT_STATUSES` once listed only ticketing words while the value read came
    from plan frontmatter, so the comparison could never be true. It is still on
    the fallback path here, so the guard travels with it.
    """

    def test_plan_lifecycle_vocabulary(self):
        for status in ("built", "shipped", "Built"):
            self.assertTrue(_is_built_status(status), status)

    def test_ticketing_vocabulary_and_mirror_emphasis(self):
        for status in ("Done", "**Done**", " in review ", "`Merged`"):
            self.assertTrue(_is_built_status(status), status)

    def test_open_statuses_are_not_built(self):
        for status in ("To Do", "In Progress", "", None, 42):
            self.assertFalse(_is_built_status(status), status)


class BranchMatchingTest(unittest.TestCase):
    def test_key_matches_on_a_boundary_not_a_prefix(self):
        branches = ["feat/PROJ-12-thing", "feat/PROJ-123-other", "main"]
        self.assertEqual(_branches_for_key("PROJ-12", branches, None), ["feat/PROJ-12-thing"])

    def test_every_branch_shape_the_plugin_documents_matches(self):
        branches = ["feat/PROJ-1-add-login", "feat/PROJ-1-work", "fix/PROJ-1", "PROJ-1"]
        self.assertEqual(len(_branches_for_key("PROJ-1", branches, None)), 4)

    def test_the_integration_branch_is_excluded(self):
        # It carries every story's commits; matching it would make them all built.
        branches = [
            "feat/PROJ-1-work",
            "feat/PROJ-1-integration",
            "origin/feat/PROJ-1-integration",
        ]
        self.assertEqual(
            _branches_for_key("PROJ-1", branches, "feat/PROJ-1-integration"), ["feat/PROJ-1-work"]
        )


class _GitFixture(unittest.TestCase):
    """A real repo — the git helpers are shelling out, so mock nothing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@test.local")
        self.git("config", "user.name", "test")
        (self.repo / "README.md").write_text("base\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=False)

    def commit_on(self, branch, filename):
        self.git("checkout", "-q", "-b", branch)
        (self.repo / filename).write_text("work\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"work on {branch}")
        self.git("checkout", "-q", "main")


class GitStoryStateTest(_GitFixture):
    def test_no_branch_at_all(self):
        branches = _git_branch_index(self.repo)
        state = _git_story_state(
            "PROJ-1", branches, base="main", integration_branch=None, cwd=self.repo
        )
        self.assertEqual(state, {"branch": None, "ahead": False, "merged": False})

    def test_branch_without_commits_is_not_ahead(self):
        self.git("branch", "feat/PROJ-1-work")
        branches = _git_branch_index(self.repo)
        state = _git_story_state(
            "PROJ-1", branches, base="main", integration_branch=None, cwd=self.repo
        )
        self.assertEqual(state["branch"], "feat/PROJ-1-work")
        self.assertFalse(state["ahead"])

    def test_branch_with_commits_is_ahead(self):
        self.commit_on("feat/PROJ-1-work", "a.txt")
        branches = _git_branch_index(self.repo)
        state = _git_story_state(
            "PROJ-1", branches, base="main", integration_branch=None, cwd=self.repo
        )
        self.assertTrue(state["ahead"])

    def test_a_merged_branch_reads_as_merged(self):
        self.commit_on("feat/PROJ-1-work", "a.txt")
        self.git("checkout", "-q", "-b", "feat/epic-integration")
        self.git("merge", "-q", "--no-ff", "-m", "integrate", "feat/PROJ-1-work")
        self.git("checkout", "-q", "main")
        branches = _git_branch_index(self.repo)
        state = _git_story_state(
            "PROJ-1",
            branches,
            base="main",
            integration_branch="feat/epic-integration",
            cwd=self.repo,
        )
        self.assertTrue(state["merged"])

    def test_an_unmerged_branch_does_not_read_as_merged(self):
        self.commit_on("feat/PROJ-1-work", "a.txt")
        self.git("branch", "feat/epic-integration")
        branches = _git_branch_index(self.repo)
        state = _git_story_state(
            "PROJ-1",
            branches,
            base="main",
            integration_branch="feat/epic-integration",
            cwd=self.repo,
        )
        self.assertFalse(state["merged"])

    def test_outside_a_repo_git_answers_nothing(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(_git_branch_index(Path(empty)), [])

    def test_base_resolution_falls_back_to_main(self):
        self.assertEqual(_resolve_base(None, self.repo), "main")

    def test_an_unresolvable_base_yields_no_evidence(self):
        branches = _git_branch_index(self.repo)
        self.assertEqual(
            _git_story_state(
                "PROJ-1", branches, base=None, integration_branch=None, cwd=self.repo
            ),
            {},
        )


class LoadEpicStateTest(_GitFixture):
    """The gatherer, end to end: plan files + mirror rows + git."""

    PLAN = """---
story: {key}
epic: demo
status: {status}
---

# {key}

## Context

{context}

## Acceptance Criteria

1. **Given** a thing, **When** it happens, **Then** it works.

### Phase 1: do it

- **Files:** `a.py`
"""

    def write_plan(self, key, *, refined=True, status="To Do"):
        plans = self.repo / "docs" / "plans"
        plans.mkdir(parents=True, exist_ok=True)
        context = "x" * 80 if refined else "short"
        text = self.PLAN.format(key=key, status=status, context=context)
        if not refined:
            text = text.replace("### Phase 1: do it", "Phase one, informally")
        (plans / f"{key}-story.md").write_text(text)
        # Commit it on main: an untracked plan would be swept onto the first
        # story branch by commit_on's `git add -A` and vanish on checkout back.
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"plan {key}")

    def load(self, **kwargs):
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            return _load_epic_state("demo", "docs/plans", repo=str(self.repo), **kwargs)
        finally:
            os.chdir(cwd)

    def test_a_merged_branch_beats_a_missing_checkpoint(self):
        # The failure this model exists for: the work is merged, nobody wrote a
        # checkpoint, and the old derivation therefore offered it as ready again.
        self.write_plan("PROJ-1")
        self.commit_on("feat/PROJ-1-work", "a.txt")
        self.git("checkout", "-q", "-b", "feat/demo-integration")
        self.git("merge", "-q", "--no-ff", "-m", "integrate", "feat/PROJ-1-work")
        self.git("checkout", "-q", "main")
        stories = self.load(base="main", integration_branch="feat/demo-integration")
        result = compute_epic_state(stories)
        self.assertEqual(_states(result), {"PROJ-1": "integrated"})

    def test_a_pushed_branch_reads_as_built(self):
        self.write_plan("PROJ-1")
        self.commit_on("feat/PROJ-1-work", "a.txt")
        result = compute_epic_state(self.load(base="main"))
        self.assertEqual(_states(result), {"PROJ-1": "built"})
        self.assertEqual(result["dispatch"]["integrate"], ["PROJ-1"])

    def test_a_refined_plan_without_a_branch_develops(self):
        self.write_plan("PROJ-1")
        result = compute_epic_state(self.load(base="main"))
        self.assertEqual(_states(result), {"PROJ-1": "refined"})

    def test_an_unrefined_plan_is_a_draft(self):
        self.write_plan("PROJ-1", refined=False)
        result = compute_epic_state(self.load(base="main"))
        self.assertEqual(_states(result), {"PROJ-1": "draft"})

    def test_a_done_status_ships_the_story(self):
        self.write_plan("PROJ-1", status="Done")
        result = compute_epic_state(self.load(base="main"))
        self.assertEqual(_states(result), {"PROJ-1": "shipped"})

    def test_planless_mirror_rows_join_the_roster_as_ideas(self):
        plans = self.repo / "docs" / "plans"
        plans.mkdir(parents=True, exist_ok=True)
        (plans / "demo-epic.md").write_text(
            "---\nepic: demo\n---\n\n<!-- mirror:start -->\n\n"
            "| Key | Title | Status |\n|---|---|---|\n"
            "| PROJ-7 | Something | To Do |\n"
            "| PROJ-8 | Shipped thing | **Done** |\n\n<!-- mirror:end -->\n"
        )
        result = compute_epic_state(self.load(base="main"))
        self.assertEqual(_states(result), {"PROJ-7": "idea", "PROJ-8": "shipped"})
        self.assertEqual(result["dispatch"]["refine"], ["PROJ-7"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
