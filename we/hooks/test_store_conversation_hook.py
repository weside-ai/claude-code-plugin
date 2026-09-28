#!/usr/bin/env python3
"""Standalone unittest for store_conversation_hook session tags (PROJ-1720).

Run with: python3 -m pytest we/hooks/test_store_conversation_hook.py
No pytest required.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from store_conversation_hook import (
    _MAX_SOURCE_DETAIL_LEN,
    _build_source_detail,
    _derive_session_tag,
    redact,
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
        self.assertEqual(_build_source_detail("example-repo", None), "example-repo")

    def test_tag_appended_with_hash(self):
        self.assertEqual(_build_source_detail("example-repo", "3f9a21c4"), "example-repo#3f9a21c4")

    def test_long_project_name_never_clips_the_tag(self):
        # A repo dirname long enough that "<project>#<tag>" alone would blow
        # past the backend's 200-char cap -- the tag must survive intact.
        long_project = "x" * 195
        result = _build_source_detail(long_project, "3f9a21c4")
        self.assertTrue(result.endswith("#3f9a21c4"))
        self.assertLessEqual(len(result), _MAX_SOURCE_DETAIL_LEN)


class RedactTest(unittest.TestCase):
    def test_provider_tokens_are_replaced(self):
        samples = [
            "sk-" + "a" * 32,
            "sk-ant-" + "b" * 40,
            "ghp_" + "c" * 36,
            "github_pat_" + "d" * 40,
            "sbp_" + "e" * 40,
            "AKIA" + "F" * 16,
            "eyJ" + "g" * 20 + "." + "h" * 20 + "." + "i" * 20,
        ]
        for s in samples:
            self.assertEqual(redact(f"value {s} end"), "value [REDACTED] end", s)

    def test_key_value_assignment_is_replaced(self):
        self.assertNotIn("hunter2hunter2", redact("password=hunter2hunter2xyz"))

    def test_private_key_block_is_replaced(self):
        block = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----"
        self.assertEqual(redact(block), "[REDACTED]")

    def test_ordinary_text_is_untouched(self):
        text = "Der Backfill hat 9799 Zeilen gefüllt, sha256 f93e8c0c3310 stimmt."
        self.assertEqual(redact(text), text)


if __name__ == "__main__":
    unittest.main()
