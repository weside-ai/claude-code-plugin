"""install_launcher.py: install, refresh, foreign-file refusal, backup and revert."""

import os
import tempfile
import unittest
from pathlib import Path

import install_launcher as ins


class LauncherInstallerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        home = Path(self._tmp.name)
        self._orig = (ins.BIN_DIR, ins.TARGET, ins.BACKUP)
        ins.BIN_DIR = home / ".local" / "bin"
        ins.TARGET = ins.BIN_DIR / "wclaude"
        ins.BACKUP = home / ".claude" / "we-wclaude-backup"
        self._path = os.environ.get("PATH", "")

    def tearDown(self):
        ins.BIN_DIR, ins.TARGET, ins.BACKUP = self._orig
        os.environ["PATH"] = self._path
        self._tmp.cleanup()

    def test_shipped_script_carries_the_marker(self):
        self.assertIn(ins.MARKER, ins.SOURCE.read_bytes())

    def test_apply_installs_executable_copy(self):
        self.assertEqual(ins.state(), "missing")
        self.assertEqual(ins.cmd_apply(force=False), 0)
        self.assertEqual(ins.TARGET.read_bytes(), ins.SOURCE.read_bytes())
        self.assertTrue(os.access(ins.TARGET, os.X_OK))
        self.assertEqual(ins.state(), "current")

    def test_stale_copy_is_refreshed(self):
        ins.cmd_apply(force=False)
        ins.TARGET.write_bytes(ins.SOURCE.read_bytes() + b"\n# local edit\n")
        self.assertEqual(ins.state(), "stale")
        self.assertEqual(ins.cmd_apply(force=False), 0)
        self.assertEqual(ins.state(), "current")

    def test_foreign_file_refused_without_force(self):
        ins.BIN_DIR.mkdir(parents=True)
        ins.TARGET.write_text("#!/bin/sh\necho mine\n")
        self.assertEqual(ins.state(), "foreign")
        self.assertEqual(ins.cmd_apply(force=False), 1)
        self.assertEqual(ins.TARGET.read_text(), "#!/bin/sh\necho mine\n")

    def test_force_backs_up_and_revert_restores(self):
        ins.BIN_DIR.mkdir(parents=True)
        ins.TARGET.write_text("#!/bin/sh\necho mine\n")
        self.assertEqual(ins.cmd_apply(force=True), 0)
        self.assertEqual(ins.state(), "current")
        self.assertEqual(ins.BACKUP.read_text(), "#!/bin/sh\necho mine\n")
        self.assertEqual(ins.cmd_revert(), 0)
        self.assertEqual(ins.TARGET.read_text(), "#!/bin/sh\necho mine\n")
        self.assertFalse(ins.BACKUP.exists())

    def test_revert_removes_ours_and_leaves_foreign(self):
        ins.cmd_apply(force=False)
        self.assertEqual(ins.cmd_revert(), 0)
        self.assertFalse(ins.TARGET.exists())
        ins.BIN_DIR.mkdir(parents=True, exist_ok=True)
        ins.TARGET.write_text("foreign")
        self.assertEqual(ins.cmd_revert(), 0)
        self.assertEqual(ins.TARGET.read_text(), "foreign")

    def test_on_path(self):
        ins.BIN_DIR.mkdir(parents=True)
        os.environ["PATH"] = os.pathsep.join(["/usr/bin", str(ins.BIN_DIR)])
        self.assertTrue(ins.on_path())
        os.environ["PATH"] = "/usr/bin"
        self.assertFalse(ins.on_path())


if __name__ == "__main__":
    unittest.main()
