#!/usr/bin/env python3
"""Standalone unittest for store_conversation_hook: session tags, redaction, bound sessions only.

Run with: python3 -m pytest we/hooks/test_store_conversation_hook.py
No pytest required.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import store_conversation_hook as hook
from store_conversation_hook import (
    _MAX_SOURCE_DETAIL_LEN,
    _build_source_detail,
    _derive_session_tag,
    redact,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import identity_cache


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


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b'event: message\ndata: {"result": {"isError": false}}\n'


class BoundSessionOnlyTest(unittest.TestCase):
    """A session stores only when /we:materialize bound it, and under the bound companion."""

    USER = "Please explain how the session binding decides which companion stores this turn."
    ASSISTANT = "The Stop hook reads the binding file of this session id and stores under it."

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.sessions = root / "sessions"
        self.transcript = root / "3f9a21c4-1234-5678-9abc-def012345678.jsonl"
        self.transcript.write_text(
            json.dumps({"type": "user", "message": {"content": self.USER}}) + "\n"
        )
        self.cwd = root / "example-repo"
        (self.cwd / ".weside").mkdir(parents=True)
        (self.cwd / ".weside" / "config.json").write_text(
            json.dumps({"repo_id": "github.com/example/example-repo"})
        )
        self._env = mock.patch.dict(os.environ, {"WE_SESSION_DIR": str(self.sessions)})
        self._env.start()
        os.environ.pop("WESIDE_COMPANION", None)

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def run_main(self, session_id, options, token="tok"):
        stdin = json.dumps(
            {
                "session_id": session_id,
                "transcript_path": str(self.transcript),
                "last_assistant_message": self.ASSISTANT,
                "cwd": str(self.cwd),
            }
        )
        stderr = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(hook, "get_plugin_config", return_value=options))
            self.token = stack.enter_context(
                mock.patch.object(hook, "_get_valid_token", return_value=token)
            )
            op = stack.enter_context(
                mock.patch.object(hook.urllib.request, "urlopen", return_value=_FakeResponse())
            )
            stack.enter_context(mock.patch.object(sys, "stdin", io.StringIO(stdin)))
            stack.enter_context(contextlib.redirect_stderr(stderr))
            hook.main()
        return op, stderr.getvalue()

    def test_bound_session_stores_under_the_bound_name(self):
        self.assertEqual(identity_cache.bind("s1", "Vyra"), 0)
        op, err = self.run_main("s1", {"autoStoreConversations": True, "companion": "Nox"})
        self.assertEqual(op.call_count, 1)
        request = op.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/mcp/?companion=Vyra"), request.full_url)
        args = json.loads(request.data)["params"]["arguments"]
        self.assertEqual(args["repo_id"], "github.com/example/example-repo")
        self.assertEqual(args["source"], "claude_code")
        self.assertIn("session binding", json.loads(args["conversations"])[0]["user_message"])
        self.assertEqual(err, "")

    def test_unbound_session_makes_no_call_and_prints_nothing(self):
        identity_cache.bind("other", "Vyra")
        op, err = self.run_main("s2", {"autoStoreConversations": True, "companion": "Nox"})
        self.assertEqual(op.call_count, 0)
        self.assertEqual(err, "")

    def test_unbound_session_without_token_stays_silent(self):
        options = {"autoStoreConversations": True, "companion": "Nox"}
        op, err = self.run_main("s3", options, token=None)
        self.assertEqual(op.call_count, 0)
        self.assertEqual(err, "")
        self.token.assert_not_called()

    def test_bound_session_without_token_warns(self):
        identity_cache.bind("s1", "Vyra")
        op, err = self.run_main("s1", {"autoStoreConversations": True}, token=None)
        self.assertEqual(op.call_count, 0)
        self.assertIn("NOT stored", err)

    def test_auto_store_off_stores_nothing_even_when_bound(self):
        identity_cache.bind("s1", "Vyra")
        op, _ = self.run_main("s1", {"autoStoreConversations": False})
        self.assertEqual(op.call_count, 0)


if __name__ == "__main__":
    unittest.main()
