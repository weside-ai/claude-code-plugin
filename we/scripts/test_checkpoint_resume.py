#!/usr/bin/env python3
"""Regression tests for checkpoint/resume robustness (WA-1231).

Guards the bug where reordering STORY_PHASES silently invalidated the stored
``phase_index`` cache column, making `story resume` map a stale index to the
wrong phase name. The fix recomputes the index from the phase NAME on read.

Run with: python3 we/scripts/test_checkpoint_resume.py
No pytest required.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import orchestration
from orchestration import (
    STORY_PHASES,
    phase_index_of,
    story_checkpoint,
    story_list,
    story_resume,
)


class CheckpointResumeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_db = orchestration.DB_PATH
        orchestration.DB_PATH = Path(self._tmp.name) / "orchestration.db"
        with contextlib.redirect_stdout(io.StringIO()):
            orchestration.init_db()

    def tearDown(self):
        orchestration.DB_PATH = self._orig_db
        self._tmp.cleanup()

    def test_phase_index_of_known_and_unknown(self):
        self.assertEqual(phase_index_of("refined"), 0)
        self.assertEqual(phase_index_of("ci_passed"), len(STORY_PHASES) - 1)
        self.assertEqual(phase_index_of("not-a-phase"), -1)

    def test_resume_next_phase_from_name(self):
        story_checkpoint("WA-1", "implementation_complete")
        result = story_resume("WA-1")
        self.assertTrue(result["success"])
        self.assertEqual(result["checkpoint"]["phase"], "implementation_complete")
        self.assertEqual(result["next_phase"], "ac_verified")

    def test_resume_picks_furthest_phase_not_latest_write(self):
        # ac_verified is further along than git_prepared; later write is the
        # earlier phase, so a naive "latest row" pick would regress here.
        story_checkpoint("WA-1", "ac_verified")
        story_checkpoint("WA-1", "git_prepared")
        result = story_resume("WA-1")
        self.assertEqual(result["checkpoint"]["phase"], "ac_verified")
        self.assertEqual(result["next_phase"], "simplified")

    def test_resume_ignores_stale_stored_phase_index(self):
        # Simulate a row written before a STORY_PHASES reorder: correct phase
        # NAME, but a phase_index that points at a different phase now.
        story_checkpoint("WA-1", "docs_updated")
        conn = orchestration.get_db()
        try:
            conn.execute(
                "UPDATE story_checkpoints SET phase_index = ? WHERE story_key = ?",
                (0, "WA-1"),  # 0 == 'refined' — deliberately wrong
            )
            conn.commit()
        finally:
            conn.close()

        result = story_resume("WA-1")
        # Must trust the NAME, not the poisoned index.
        self.assertEqual(result["checkpoint"]["phase"], "docs_updated")
        self.assertEqual(result["next_phase"], "pr_created")
        self.assertNotIn("refined", result["remaining_phases"])

    def test_resume_last_phase_has_no_next(self):
        story_checkpoint("WA-1", "ci_passed")
        result = story_resume("WA-1")
        self.assertIsNone(result["next_phase"])
        self.assertEqual(result["remaining_phases"], [])

    def test_resume_missing_story(self):
        result = story_resume("WA-404")
        self.assertFalse(result["success"])

    def test_list_recomputes_latest_phase_from_names(self):
        story_checkpoint("WA-1", "git_prepared")
        story_checkpoint("WA-1", "test_passed")
        conn = orchestration.get_db()
        try:
            # Poison both stored indices to prove names win.
            conn.execute("UPDATE story_checkpoints SET phase_index = 0")
            conn.commit()
        finally:
            conn.close()

        stories = {s["story_key"]: s for s in story_list()}
        self.assertEqual(stories["WA-1"]["latest_phase"], "test_passed")
        self.assertFalse(stories["WA-1"]["is_complete"])

    def test_list_marks_complete_at_final_phase(self):
        story_checkpoint("WA-1", "ci_passed")
        stories = {s["story_key"]: s for s in story_list()}
        self.assertTrue(stories["WA-1"]["is_complete"])


if __name__ == "__main__":
    unittest.main()
