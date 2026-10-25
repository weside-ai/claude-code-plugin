#!/usr/bin/env python3
"""SessionStart: a pin titles the session and asks for /we:materialize; unpinned runs as before.

Run with: python3 -m pytest -q we/hooks/test_materialize_on_start.py
The hook runs as a subprocess with a temporary HOME, as Claude Code runs it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "materialize_on_start.py"
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


class MaterializeOnStartTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        (self.home / ".claude").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def settings(self, options):
        settings = {"pluginConfigs": {"we@weside-ai": {"options": options}}}
        (self.home / ".claude" / "settings.json").write_text(json.dumps(settings))

    def run_hook(self, pin=None, hook_input=None):
        env = {
            k: v for k, v in os.environ.items() if k not in ("WESIDE_COMPANION", "WE_SESSION_DIR")
        }
        env["HOME"] = str(self.home)
        if pin is not None:
            env["WESIDE_COMPANION"] = pin
        stdin = json.dumps(hook_input or {"session_id": "s1", "source": "startup"})
        done = subprocess.run(
            [sys.executable, str(HOOK)],
            input=stdin,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr, "")
        return json.loads(done.stdout) if done.stdout.strip() else None

    def bind(self, session, name):
        env = dict(os.environ, HOME=str(self.home))
        env.pop("WESIDE_COMPANION", None)
        env.pop("WE_SESSION_DIR", None)
        subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "identity_cache.py"),
                "bind",
                "--session",
                session,
                "--companion",
                name,
            ],
            env=env,
            check=True,
            capture_output=True,
        )

    def test_pin_titles_the_session_and_asks_to_materialize_that_companion(self):
        self.settings({"companion": "Nox", "autoMaterialize": True})
        out = self.run_hook(pin="Vyra")["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        self.assertEqual(out["sessionTitle"], "Vyra")
        self.assertIn("we:materialize", out["additionalContext"])
        self.assertIn("WESIDE_COMPANION=Vyra", out["additionalContext"])
        self.assertNotIn("Nox", out["additionalContext"])

    def test_pin_with_a_binding_to_it_titles_only(self):
        self.bind("s1", "Vyra")
        out = self.run_hook(pin="Vyra", hook_input={"session_id": "s1", "source": "resume"})
        self.assertEqual(out["hookSpecificOutput"]["sessionTitle"], "Vyra")
        self.assertNotIn("additionalContext", out["hookSpecificOutput"])

    def test_title_output_has_the_documented_shape(self):
        # Claude Code reads hookSpecificOutput.sessionTitle with hookEventName "SessionStart"
        # (hooks docs, SessionStart decision control); it applies on startup, resume and fork.
        self.bind("s1", "Vyra")
        for source in ("startup", "resume", "fork"):
            out = self.run_hook(pin="Vyra", hook_input={"session_id": "s1", "source": source})
            self.assertEqual(
                out,
                {"hookSpecificOutput": {"hookEventName": "SessionStart", "sessionTitle": "Vyra"}},
            )

    def test_pin_after_clear_asks_again(self):
        self.bind("s1", "Vyra")
        out = self.run_hook(pin="Vyra", hook_input={"session_id": "s2", "source": "clear"})
        self.assertIn("we:materialize", out["hookSpecificOutput"]["additionalContext"])

    def test_agent_session_is_never_the_companion(self):
        out = self.run_hook(
            pin="Vyra", hook_input={"session_id": "s1", "source": "startup", "agent_type": "w"}
        )
        self.assertIsNone(out)

    def test_empty_pin_is_no_pin(self):
        self.settings({"autoMaterialize": False})
        self.assertIsNone(self.run_hook(pin="  "))

    def test_unpinned_with_auto_materialize_asks_as_before(self):
        self.settings({"companion": "Nox", "autoMaterialize": True})
        out = self.run_hook()["hookSpecificOutput"]
        self.assertIn("autoMaterialize", out["additionalContext"])
        self.assertNotIn("sessionTitle", out)

    def test_unpinned_without_auto_materialize_prints_nothing(self):
        self.settings({"companion": "Nox"})
        self.assertIsNone(self.run_hook())

    def test_unpinned_without_settings_prints_nothing(self):
        self.assertIsNone(self.run_hook())


if __name__ == "__main__":
    unittest.main()
