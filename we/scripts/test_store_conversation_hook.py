#!/usr/bin/env python3
"""Standalone unittest for store_conversation_hook session tags (WA-1720).

Run with: python3 we/scripts/test_store_conversation_hook.py
No pytest required.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

from store_conversation_hook import _derive_session_tag


class DeriveSessionTagTest(unittest.TestCase):
    def test_normal_transcript_path(self):
        transcript_path = (
            "/home/user/.claude/projects/some-repo/3f9a21c4-1234-5678-9abc-def012345678.jsonl"
        )
        self.assertEqual(_derive_session_tag(transcript_path), "3f9a21c4")

    def test_empty_path(self):
        self.assertIsNone(_derive_session_tag(""))

    def test_path_without_jsonl_extension(self):
        self.assertIsNone(
            _derive_session_tag(
                "/home/user/.claude/projects/some-repo/3f9a21c4-1234-5678-9abc-def012345678"
            )
        )

    def test_malformed_path(self):
        self.assertIsNone(_derive_session_tag("/tmp/not-a-session.jsonl"))


if __name__ == "__main__":
    unittest.main()
