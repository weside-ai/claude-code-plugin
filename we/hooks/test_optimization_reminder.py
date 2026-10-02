#!/usr/bin/env python3
"""The reminder speaks only when the store has open entries and /we:optimize is overdue.

Run with: python3 -m pytest -q we/hooks/test_optimization_reminder.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import optimization_reminder as rem

TODAY = dt.date(2026, 10, 2)


class ReminderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = self.root / ".weside" / "optimization"
        (self.store / "inbox").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def entry(self, name: str) -> None:
        (self.store / "inbox" / name).write_text("---\nkey: x\n---\n")

    def charter(self, date: str) -> None:
        (self.store / "CHARTER.md").write_text(f"---\nlast_optimize: {date}\n---\n# Charter\n")

    def test_overdue_with_open_entries_reminds(self):
        self.entry("2026-09-01-g2-volatile--agents-md.md")
        self.charter("2026-09-01")
        text = rem.message(self.root, TODAY)
        self.assertIn("1 open instruction finding(s), last /we:optimize 31 days ago", text)

    def test_two_files_with_one_key_count_once(self):
        self.entry("2026-09-01-gap--agents-md.md")
        self.entry("2026-09-03-gap--agents-md.md")
        self.assertIn("1 open instruction finding(s)", rem.message(self.root, TODAY))

    def test_never_optimized_reminds(self):
        self.entry("2026-09-30-gap--agents-md.md")
        self.assertIn("last /we:optimize never", rem.message(self.root, TODAY))

    def test_recent_optimize_is_silent(self):
        self.entry("2026-09-30-gap--agents-md.md")
        self.charter("2026-09-28")
        self.assertIsNone(rem.message(self.root, TODAY))

    def test_empty_inbox_is_silent(self):
        self.assertIsNone(rem.message(self.root, TODAY))

    def test_switched_off_is_silent(self):
        self.entry("2026-09-01-gap--agents-md.md")
        (self.root / ".weside" / "config.json").write_text(
            json.dumps({"optimization": {"reminder": False}})
        )
        self.assertIsNone(rem.message(self.root, TODAY))

    def test_staged_entries_count(self):
        staged = self.root / "staged"
        staged.mkdir()
        (staged / "2026-09-01-gap--readme-md.md").write_text("---\nkey: y\n---\n")
        self.assertIn("1 open instruction finding(s)", rem.message(self.root, TODAY, staged))

    def test_no_store_is_silent(self):
        self.assertIsNone(rem.message(self.root / "elsewhere", TODAY))


if __name__ == "__main__":
    unittest.main()
