#!/usr/bin/env python3
"""Standalone unittest for store_conversation_hook session tags (WA-1720).

Run with: python3 we/scripts/test_store_conversation_hook.py
No pytest required.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

from store_conversation_hook import (
    _MAX_SOURCE_DETAIL_LEN,
    _build_source_detail,
    _derive_session_tag,
)


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


class BuildSourceDetailTest(unittest.TestCase):
    def test_no_tag_returns_project_unchanged(self):
        self.assertEqual(_build_source_detail("weside-core", None), "weside-core")

    def test_tag_appended_with_hash(self):
        self.assertEqual(_build_source_detail("weside-core", "3f9a21c4"), "weside-core#3f9a21c4")

    def test_long_project_name_never_clips_the_tag(self):
        # A repo dirname long enough that "<project>#<tag>" alone would blow
        # past the backend's 200-char cap -- the tag must survive intact.
        long_project = "x" * 195
        result = _build_source_detail(long_project, "3f9a21c4")
        self.assertTrue(result.endswith("#3f9a21c4"))
        self.assertLessEqual(len(result), _MAX_SOURCE_DETAIL_LEN)


if __name__ == "__main__":
    unittest.main()
