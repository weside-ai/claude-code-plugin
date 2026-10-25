#!/usr/bin/env python3
"""Standalone unittest for the identity cache.

Covers what can silently break a materialize: the tool-result shape must be
unwrapped, the cache must be keyed per companion (a switch must not serve the
previous companion's file), freshness must flip at the day boundary, and the
file must not be world-readable — it carries the compass and snapshot.

Run with: python3 we/scripts/test_identity_cache.py
No pytest required.
"""

import json
import os
import stat
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import identity_cache as ic


class IdentityCacheTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "cache"
        os.environ["WE_IDENTITY_CACHE_DIR"] = str(self.dir)
        self.src = Path(self._tmp.name) / "tool-result.txt"

    def tearDown(self):
        os.environ.pop("WE_IDENTITY_CACHE_DIR", None)
        self._tmp.cleanup()

    def write_payload(self, text):
        self.src.write_text(json.dumps({"result": text}), encoding="utf-8")

    def test_store_unwraps_tool_result_and_path_reports_fresh(self):
        self.write_payload("You are Nox.\n\n## Your Compass\n…")
        self.assertEqual(ic.main(["store", "--companion", "Nox", "--from", str(self.src)]), 0)
        target = self.dir / "nox.md"
        body = target.read_text(encoding="utf-8")
        self.assertTrue(body.startswith("<!-- weside identity cache · companion: Nox · fetched: "))
        self.assertIn("You are Nox.", body)
        self.assertNotIn('{"result"', body)
        self.assertEqual(ic.main(["path", "--companion", "Nox"]), 0)

    def test_store_accepts_plain_text(self):
        self.src.write_text("You are Mila.", encoding="utf-8")
        self.assertEqual(ic.main(["store", "--companion", "Mila", "--from", str(self.src)]), 0)
        self.assertIn("You are Mila.", (self.dir / "mila.md").read_text(encoding="utf-8"))

    def test_cache_is_keyed_per_companion(self):
        self.write_payload("You are Nox.")
        ic.main(["store", "--companion", "Nox", "--from", str(self.src)])
        # A different companion has no cache of its own yet.
        self.assertEqual(ic.main(["path", "--companion", "Mila"]), 2)

    def test_yesterdays_cache_is_stale(self):
        self.write_payload("You are Nox.")
        ic.main(["store", "--companion", "Nox", "--from", str(self.src)])
        target = self.dir / "nox.md"
        lines = target.read_text(encoding="utf-8").split("\n")
        yesterday = (datetime.now().astimezone() - timedelta(days=1)).replace(microsecond=0)
        lines[0] = (
            f"<!-- weside identity cache · companion: Nox · fetched: {yesterday.isoformat()} -->"
        )
        target.write_text("\n".join(lines), encoding="utf-8")
        self.assertEqual(ic.main(["path", "--companion", "Nox"]), 1)

    def test_headerless_file_counts_as_missing(self):
        self.dir.mkdir(parents=True)
        (self.dir / "nox.md").write_text("You are Nox.", encoding="utf-8")
        self.assertEqual(ic.main(["path", "--companion", "Nox"]), 2)

    def test_cache_file_is_owner_only(self):
        self.write_payload("You are Nox.")
        ic.main(["store", "--companion", "Nox", "--from", str(self.src)])
        mode = stat.S_IMODE((self.dir / "nox.md").stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_empty_payload_is_refused(self):
        self.write_payload("   \n")
        self.assertEqual(ic.main(["store", "--companion", "Nox", "--from", str(self.src)]), 1)
        self.assertFalse((self.dir / "nox.md").exists())

    def test_missing_source_is_refused(self):
        rc = ic.main(["store", "--companion", "Nox", "--from", str(self.src.with_name("nope"))])
        self.assertEqual(rc, 1)


class SessionBindingTest(unittest.TestCase):
    """The binding file is the one record the Stop hook and the statusline read."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "sessions"
        self._saved = {k: os.environ.get(k) for k in ("WE_SESSION_DIR", "WESIDE_COMPANION")}
        os.environ["WE_SESSION_DIR"] = str(self.dir)
        os.environ.pop("WESIDE_COMPANION", None)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def test_bind_writes_one_owner_only_file_per_session(self):
        self.assertEqual(ic.main(["bind", "--session", "s-1", "--companion", "Vyra"]), 0)
        self.assertEqual(ic.main(["bind", "--session", "s-2", "--companion", "Nox"]), 0)
        target = self.dir / "s-1.json"
        self.assertEqual(json.loads(target.read_text())["companion"], "Vyra")
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(ic.read_binding("s-1"), "Vyra")
        self.assertEqual(ic.read_binding("s-2"), "Nox")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["s-1.json", "s-2.json"])

    def test_binding_reports_bound_and_unbound(self):
        ic.main(["bind", "--session", "s-1", "--companion", "Vyra"])
        self.assertEqual(ic.main(["binding", "--session", "s-1"]), 0)
        self.assertEqual(ic.main(["binding", "--session", "s-9"]), 2)
        self.assertIsNone(ic.read_binding("s-9"))

    def test_session_id_cannot_escape_the_directory(self):
        outside = Path(self._tmp.name) / "escaped.json"
        for bad in ("../escaped", "a/b", "", ".", "..", "x" * 129, "s 1"):
            self.assertEqual(ic.main(["bind", "--session", bad, "--companion", "Vyra"]), 1, bad)
            self.assertIsNone(ic.read_binding(bad))
        self.assertFalse(outside.exists())
        self.assertFalse(self.dir.exists() and any(self.dir.iterdir()))

    def test_bind_prunes_bindings_older_than_30_days(self):
        ic.main(["bind", "--session", "old", "--companion", "Vyra"])
        ic.main(["bind", "--session", "recent", "--companion", "Vyra"])
        old = time.time() - 31 * 24 * 3600
        os.utime(self.dir / "old.json", (old, old))
        recent = time.time() - 29 * 24 * 3600
        os.utime(self.dir / "recent.json", (recent, recent))
        ic.main(["bind", "--session", "new", "--companion", "Nox"])
        self.assertFalse((self.dir / "old.json").exists())
        self.assertTrue((self.dir / "recent.json").exists())
        self.assertTrue((self.dir / "new.json").exists())

    def test_a_pinned_session_refuses_another_name(self):
        os.environ["WESIDE_COMPANION"] = "Vyra"
        self.assertEqual(ic.main(["bind", "--session", "s-1", "--companion", "Nox"]), 1)
        self.assertIsNone(ic.read_binding("s-1"))
        self.assertEqual(ic.main(["bind", "--session", "s-1", "--companion", "vyra"]), 0)

    def test_corrupt_binding_reads_as_unbound(self):
        self.dir.mkdir(parents=True)
        (self.dir / "s-1.json").write_text("{not json")
        self.assertIsNone(ic.read_binding("s-1"))


if __name__ == "__main__":
    unittest.main()
