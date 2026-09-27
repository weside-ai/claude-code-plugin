#!/usr/bin/env python3
"""Standalone unittest for the statusline installer's settings surgery.

Covers only what can silently damage a user's setup: the merge must preserve
unrelated settings keys, a foreign statusLine must survive without --force, and
--revert must put back exactly what was there. The rendering of statusline.js is
not tested here — that is observed by running it with mock input.

Run with: python3 we/scripts/test_install_statusline.py
No pytest required.
"""

import json
import tempfile
import unittest
from pathlib import Path

import install_statusline as ins


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        home = Path(self._tmp.name)
        (home / ".claude").mkdir()
        self._orig = (ins.SETTINGS, ins.TARGET, ins.BACKUP)
        ins.SETTINGS = home / ".claude" / "settings.json"
        ins.TARGET = home / ".claude" / "we-statusline.js"
        ins.BACKUP = home / ".claude" / "we-statusline-backup.json"
        self._had_node = ins.has_node
        ins.has_node = lambda: True

    def tearDown(self):
        ins.SETTINGS, ins.TARGET, ins.BACKUP = self._orig
        ins.has_node = self._had_node
        self._tmp.cleanup()

    def write(self, data):
        ins.SETTINGS.write_text(json.dumps(data))

    def read(self):
        return json.loads(ins.SETTINGS.read_text())

    def test_apply_preserves_unrelated_keys(self):
        self.write({"env": {"FOO": "1"}, "permissions": {"allow": ["Bash"]}})
        self.assertEqual(ins.cmd_apply(ins.load_settings(), force=False), 0)
        out = self.read()
        self.assertEqual(out["env"], {"FOO": "1"})
        self.assertEqual(out["permissions"], {"allow": ["Bash"]})
        self.assertEqual(out["statusLine"], {"type": "command", "command": ins.COMMAND})
        self.assertTrue(ins.TARGET.exists())

    def test_apply_creates_settings_when_absent(self):
        self.assertEqual(ins.cmd_apply(ins.load_settings(), force=False), 0)
        self.assertEqual(self.read()["statusLine"]["command"], ins.COMMAND)

    def test_foreign_statusline_survives_without_force(self):
        foreign = {"type": "command", "command": "~/.claude/mine.sh"}
        self.write({"statusLine": foreign})
        self.assertEqual(ins.cmd_apply(ins.load_settings(), force=False), 1)
        self.assertEqual(self.read()["statusLine"], foreign)
        self.assertFalse(ins.TARGET.exists())

    def test_force_replaces_and_backs_up(self):
        foreign = {"type": "command", "command": "~/.claude/mine.sh"}
        self.write({"statusLine": foreign})
        self.assertEqual(ins.cmd_apply(ins.load_settings(), force=True), 0)
        self.assertEqual(self.read()["statusLine"]["command"], ins.COMMAND)
        self.assertEqual(json.loads(ins.BACKUP.read_text()), foreign)

    def test_revert_restores_the_backup(self):
        foreign = {"type": "command", "command": "~/.claude/mine.sh"}
        self.write({"statusLine": foreign, "env": {"FOO": "1"}})
        ins.cmd_apply(ins.load_settings(), force=True)
        self.assertEqual(ins.cmd_revert(ins.load_settings()), 0)
        out = self.read()
        self.assertEqual(out["statusLine"], foreign)
        self.assertEqual(out["env"], {"FOO": "1"})
        self.assertFalse(ins.TARGET.exists())
        # A consumed backup must not survive — a later install/revert cycle
        # would otherwise resurrect a statusline the user removed long ago.
        self.assertFalse(ins.BACKUP.exists())

    def test_a_consumed_backup_is_not_resurrected(self):
        """Install → revert → (user drops their own line) → install → revert.

        The second revert must remove the key, not restore the statusline the
        first cycle backed up.
        """
        foreign = {"type": "command", "command": "~/.claude/mine.sh"}
        self.write({"statusLine": foreign})
        ins.cmd_apply(ins.load_settings(), force=True)
        ins.cmd_revert(ins.load_settings())
        self.write({})  # user removed their own statusline in the meantime
        ins.cmd_apply(ins.load_settings(), force=False)
        self.assertEqual(ins.cmd_revert(ins.load_settings()), 0)
        self.assertNotIn("statusLine", self.read())

    def test_revert_without_backup_removes_the_key(self):
        ins.cmd_apply(ins.load_settings(), force=False)
        self.assertEqual(ins.cmd_revert(ins.load_settings()), 0)
        self.assertNotIn("statusLine", self.read())

    def test_revert_leaves_a_foreign_statusline_alone(self):
        foreign = {"type": "command", "command": "~/.claude/mine.sh"}
        self.write({"statusLine": foreign})
        self.assertEqual(ins.cmd_revert(ins.load_settings()), 0)
        self.assertEqual(self.read()["statusLine"], foreign)

    def test_apply_without_node_changes_nothing(self):
        ins.has_node = lambda: False
        self.write({"env": {"FOO": "1"}})
        self.assertEqual(ins.cmd_apply(ins.load_settings(), force=False), 1)
        self.assertNotIn("statusLine", self.read())
        self.assertFalse(ins.TARGET.exists())

    def test_stale_copy_is_refreshed(self):
        ins.cmd_apply(ins.load_settings(), force=False)
        ins.TARGET.write_text("// outdated\n")
        self.assertEqual(ins.installed_state(), "stale")
        self.assertEqual(ins.cmd_apply(ins.load_settings(), force=False), 0)
        self.assertEqual(ins.installed_state(), "current")


if __name__ == "__main__":
    unittest.main()
