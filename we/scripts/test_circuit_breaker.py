#!/usr/bin/env python3
"""Regression tests for the circuit breaker + rollback repo-root resolution.

Covers two bugs the showcase sweep fixed:
  1. Circuit breaker state machine (closed → open after max failures → reset).
  2. Rollback must resolve the git repo root from the worktree, not hard-reset
     whatever cwd it runs in (was resetting the plugin install dir).

Run with: python3 we/scripts/test_circuit_breaker.py
No pytest required.
"""

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

import orchestration
from orchestration import (
    CIRCUIT_BREAKER_CONFIG,
    CIRCUIT_STATE_CLOSED,
    CIRCUIT_STATE_OPEN,
    _resolve_repo_root,
    circuit_check,
    circuit_fail,
    circuit_success,
)


class CircuitBreakerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_db = orchestration.DB_PATH
        orchestration.DB_PATH = Path(self._tmp.name) / "orchestration.db"
        with contextlib.redirect_stdout(io.StringIO()):
            orchestration.init_db()

    def tearDown(self):
        orchestration.DB_PATH = self._orig_db
        self._tmp.cleanup()

    def test_fresh_phase_is_closed_and_allowed(self):
        result = circuit_check("WA-1", "git_prepared")
        self.assertTrue(result["allowed"])
        self.assertEqual(result["state"], CIRCUIT_STATE_CLOSED)

    def test_opens_after_max_failures_then_blocks(self):
        max_failures = CIRCUIT_BREAKER_CONFIG["max_failures_per_phase"]
        # No prior checkpoint for this story → rollback is a graceful no-op,
        # so this test never shells out to git.
        for _ in range(max_failures - 1):
            res = circuit_fail("WA-1", "git_prepared", "boom")
            self.assertFalse(res["circuit_opened"])

        opened = circuit_fail("WA-1", "git_prepared", "boom")
        self.assertTrue(opened["circuit_opened"])
        self.assertEqual(opened["state"], CIRCUIT_STATE_OPEN)
        self.assertFalse(opened["rollback_triggered"])  # no checkpoint to roll back to

        blocked = circuit_check("WA-1", "git_prepared")
        self.assertFalse(blocked["allowed"])
        self.assertEqual(blocked["state"], CIRCUIT_STATE_OPEN)

    def test_failures_are_scoped_per_phase(self):
        circuit_fail("WA-1", "git_prepared", "boom")
        other = circuit_check("WA-1", "test_passed")
        self.assertTrue(other["allowed"])

    def test_success_resets_circuit(self):
        circuit_fail("WA-1", "git_prepared", "boom")
        circuit_success("WA-1", "git_prepared")
        result = circuit_check("WA-1", "git_prepared")
        self.assertTrue(result["allowed"])
        self.assertEqual(result["state"], CIRCUIT_STATE_CLOSED)


class ResolveRepoRootTest(unittest.TestCase):
    def test_returns_toplevel_for_real_repo(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            sub = root / "nested" / "dir"
            sub.mkdir(parents=True)
            # Resolving from a nested path must return the repo TOPLEVEL,
            # never the cwd it was invoked from.
            self.assertEqual(_resolve_repo_root(str(sub)), root)

    def test_returns_none_for_non_git_dir(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(_resolve_repo_root(d))


if __name__ == "__main__":
    unittest.main()
