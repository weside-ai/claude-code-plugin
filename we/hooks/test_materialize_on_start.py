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
import time
import unittest
from pathlib import Path
from unittest import mock

HOOK = Path(__file__).resolve().parent / "materialize_on_start.py"
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import materialize_on_start as mos  # noqa: E402
import wake_poller  # noqa: E402
from test_wake_poller import TOKEN, FakeInbox, FakeMcp, fake_weside, wait_for  # noqa: E402


class MaterializeOnStartTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        (self.home / ".claude").mkdir()
        self.extra_env = {}

    def tearDown(self):
        self._tmp.cleanup()

    def settings(self, options):
        settings = {"pluginConfigs": {"we@weside-ai": {"options": options}}}
        (self.home / ".claude" / "settings.json").write_text(json.dumps(settings))

    def run_hook(self, pin=None, hook_input=None):
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("WESIDE_COMPANION", "WE_SESSION_DIR", "WE_NEWS_DIR", "CLAUDE_JOB_DIR")
            # never reach the real session's inbox socket from a test
            and not k.startswith("CLAUDE_CODE_MESSAGING_")
        }
        env["HOME"] = str(self.home)
        env.update(self.extra_env)
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
        env.pop("CLAUDE_JOB_DIR", None)
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

    def role_skill(self, root, name="weside-vyra"):
        skill = root / ".claude" / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n")

    def test_role_skill_in_the_project_is_named(self):
        project = self.home / "project"
        self.role_skill(project)
        out = self.run_hook(
            pin="Vyra", hook_input={"session_id": "s1", "source": "startup", "cwd": str(project)}
        )
        self.assertIn(
            "Skill tool with weside-vyra", out["hookSpecificOutput"]["additionalContext"]
        )

    def test_role_skill_comes_before_the_ignore_clause(self):
        self.role_skill(self.home)
        for hook_input in (
            {"session_id": "s1", "source": "startup"},
            {"session_id": "s2", "source": "resume"},
        ):
            if hook_input["session_id"] == "s2":
                self.bind("s2", "Vyra")
            note = self.run_hook(pin="Vyra", hook_input=hook_input)["hookSpecificOutput"][
                "additionalContext"
            ]
            self.assertNotIn("/weside-vyra", note)
            self.assertTrue(note.endswith("you are not Vyra: ignore this note."), note)
            self.assertLess(note.index("weside-vyra"), note.index("ignore this note"))

    def test_role_skill_in_the_user_skills_is_named(self):
        self.role_skill(self.home)
        out = self.run_hook(pin="Vyra")
        self.assertIn(
            "Skill tool with weside-vyra", out["hookSpecificOutput"]["additionalContext"]
        )

    def test_no_role_skill_no_mention(self):
        project = self.home / "project"
        self.role_skill(project, name="weside-other")
        out = self.run_hook(
            pin="Vyra", hook_input={"session_id": "s1", "source": "startup", "cwd": str(project)}
        )
        self.assertNotIn("weside-", out["hookSpecificOutput"]["additionalContext"])

    def test_worker_gets_no_role_skill(self):
        project = self.home / "project"
        self.role_skill(project)
        out = self.run_hook(
            pin="Vyra",
            hook_input={
                "session_id": "s1",
                "source": "startup",
                "cwd": str(project),
                "agent_type": "w",
            },
        )
        self.assertIsNone(out)

    def test_bound_resume_gets_the_role_skill_line_alone(self):
        project = self.home / "project"
        self.role_skill(project)
        self.bind("s1", "Vyra")
        for source in ("startup", "resume"):
            out = self.run_hook(
                pin="Vyra",
                hook_input={"session_id": "s1", "source": source, "cwd": str(project)},
            )["hookSpecificOutput"]
            self.assertEqual(out["sessionTitle"], "Vyra")
            self.assertIn("Skill tool with weside-vyra", out["additionalContext"])
            self.assertNotIn("materialize", out["additionalContext"])

    def crew_workspace(self, skill_text):
        core, biz = self.home / "core", self.home / "biz"
        (core / ".weside").mkdir(parents=True)
        crew = {
            "roles": {"hr": "hana"},
            "members": {
                "hana": {"name": "Hana", "workplace": "../biz"},
                "lex": {"name": "Lex", "workplace": "../biz"},
            },
        }
        (core / ".weside" / "crew.json").write_text(json.dumps(crew))
        skill = biz / ".claude" / "skills" / "weside-lex" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(skill_text)
        return core, skill

    def test_skill_only_in_the_workplace_is_read_not_invoked(self):
        core, skill = self.crew_workspace("---\nname: weside-lex\n---\n")
        note = self.run_hook(
            pin="Lex", hook_input={"session_id": "s1", "source": "startup", "cwd": str(core)}
        )["hookSpecificOutput"]["additionalContext"]
        self.assertIn(f"read {skill.resolve()} with the Read tool", note)
        self.assertNotIn("Skill tool with weside-lex", note)

    def test_stub_asks_to_fill_and_tell_hr(self):
        core, _skill = self.crew_workspace("<!-- we:stub — written by /we:setup -->\n")
        self.bind("s1", "Lex")
        note = self.run_hook(
            pin="Lex", hook_input={"session_id": "s1", "source": "startup", "cwd": str(core)}
        )["hookSpecificOutput"]["additionalContext"]
        self.assertIn("still a stub", note)
        self.assertIn("tell Hana in one line", note)

    def test_bound_compact_or_clear_repeats_no_role_skill(self):
        project = self.home / "project"
        self.role_skill(project)
        self.bind("s1", "Vyra")
        for source in ("compact", "clear"):
            out = self.run_hook(
                pin="Vyra",
                hook_input={"session_id": "s1", "source": source, "cwd": str(project)},
            )
            self.assertEqual(
                out,
                {"hookSpecificOutput": {"hookEventName": "SessionStart", "sessionTitle": "Vyra"}},
            )

    def test_unpinned_gets_no_role_skill(self):
        self.settings({"companion": "Vyra", "autoMaterialize": True})
        project = self.home / "project"
        self.role_skill(project)
        out = self.run_hook(
            hook_input={"session_id": "s1", "source": "startup", "cwd": str(project)}
        )
        self.assertNotIn("weside-", out["hookSpecificOutput"]["additionalContext"])

    def test_empty_pin_is_no_pin(self):
        self.settings({"autoMaterialize": False})
        self.assertIsNone(self.run_hook(pin="  "))

    def test_unpinned_with_auto_materialize_asks_as_before(self):
        self.settings({"companion": "Nox", "autoMaterialize": True})
        out = self.run_hook()["hookSpecificOutput"]
        self.assertIn("autoMaterialize", out["additionalContext"])
        self.assertNotIn("sessionTitle", out)

    def test_unpinned_background_session_is_warned_not_materialized(self):
        # `claude --bg` without the pin is a worker (31.10.: an onboarding worker spoke as Nox)
        self.settings({"companion": "Nox", "autoMaterialize": True})
        self.extra_env = {"CLAUDE_JOB_DIR": str(self.home / "job")}
        out = self.run_hook()
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Do not invoke we:materialize", context)
        self.assertNotIn("Before your first reply", context)
        self.assertIn("WESIDE_COMPANION", out["systemMessage"])

    def test_cleared_pin_background_worker_gets_no_user_warning(self):
        self.settings({"companion": "Nox", "autoMaterialize": True})
        self.extra_env = {"CLAUDE_JOB_DIR": str(self.home / "job")}
        out = self.run_hook(pin="")
        self.assertIn(
            "Do not invoke we:materialize", out["hookSpecificOutput"]["additionalContext"]
        )
        self.assertNotIn("systemMessage", out)

    def test_pinned_background_session_materializes_as_before(self):
        self.settings({"companion": "Nox", "autoMaterialize": True})
        self.extra_env = {"CLAUDE_JOB_DIR": str(self.home / "job")}
        out = self.run_hook(pin="Nox")
        self.assertIn("we:materialize", out["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("systemMessage", out)

    def test_unpinned_background_session_without_auto_materialize_prints_nothing(self):
        self.settings({"companion": "Nox"})
        self.extra_env = {"CLAUDE_JOB_DIR": str(self.home / "job")}
        self.assertIsNone(self.run_hook())

    def test_unpinned_without_auto_materialize_prints_nothing(self):
        self.settings({"companion": "Nox"})
        self.assertIsNone(self.run_hook())

    def test_unpinned_without_settings_prints_nothing(self):
        self.assertIsNone(self.run_hook())


class WakeSpawnTest(unittest.TestCase):
    """The SessionStart hook starts the wake poller only for a session bound to its pin."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"WE_SESSION_DIR": self._tmp.name})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def bind(self, session, name):
        target = Path(self._tmp.name) / f"{session}.json"
        target.write_text(json.dumps({"companion": name, "bound_at": "2026-10-26T12:00:00"}))

    def wake(self, hook_input, pin="Nox"):
        env = {"WESIDE_COMPANION": pin} if pin is not None else {}
        return mos.wake_companion(hook_input, env)

    # AC 8 (resume half)
    def test_a_bound_pinned_session_spawns_on_startup_and_resume(self):
        self.bind("s1", "Nox")
        for source in ("startup", "resume"):
            self.assertEqual(self.wake({"session_id": "s1", "source": source}), "Nox")

    def test_compact_and_clear_spawn_nothing(self):
        self.bind("s1", "Nox")
        for source in ("compact", "clear"):
            self.assertIsNone(self.wake({"session_id": "s1", "source": source}))

    # AC 9
    def test_unpinned_agent_and_unbound_teammate_spawn_nothing(self):
        self.bind("s1", "Nox")
        self.assertIsNone(self.wake({"session_id": "s1", "source": "startup"}, pin=None))
        self.assertIsNone(self.wake({"session_id": "s1", "source": "startup"}, pin=""))
        self.assertIsNone(
            self.wake({"session_id": "s1", "source": "startup", "agent_type": "dev-high"})
        )
        # a teammate pane that inherited the pin but never bound
        self.assertIsNone(self.wake({"session_id": "s2", "source": "startup"}))
        # a session bound to another companion than its pin
        self.bind("s3", "Vyra")
        self.assertIsNone(self.wake({"session_id": "s3", "source": "resume"}))


class WakeSpawnProcessTest(unittest.TestCase):
    """The hook process itself starts one poller against fakes, and none on compact."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir="/tmp", prefix="ws")
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        (self.home / ".claude").mkdir(parents=True)
        self.bin = self.root / "bin"
        fake_weside(self.bin)
        self.mcp = FakeMcp()
        self.inbox = FakeInbox(self.root / f"{os.getpid()}.sock")
        self.news = self.home / ".claude" / "we" / "news"

    def tearDown(self):
        self.inbox.close()
        self.assertTrue(wait_for(lambda: not self.lock_held(), timeout=4))
        self.mcp.close()
        self._tmp.cleanup()

    def lock_held(self):
        with mock.patch.dict(os.environ, {"WE_NEWS_DIR": str(self.news)}):
            return wake_poller.lock_held(self.inbox.path)

    def run_hook(self, source):
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("CLAUDE_CODE_", "WESIDE_", "WE_"))
        }
        env.update(
            {
                "HOME": str(self.home),
                "PATH": f"{self.bin}{os.pathsep}{env.get('PATH', '')}",
                "WESIDE_COMPANION": "Nox",
                "WESIDE_MCP_URL": self.mcp.url,
                "WE_WAKE_INTERVAL_S": "1",
                "CLAUDE_CODE_MESSAGING_SOCKET": self.inbox.path,
                "CLAUDE_CODE_MESSAGING_TOKEN": TOKEN,
            }
        )
        sessions = self.home / ".claude" / "we" / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        (sessions / "s1.json").write_text(json.dumps({"companion": "Nox", "bound_at": "x"}))
        subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({"session_id": "s1", "source": source}),
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

    def test_resume_spawns_one_poller_and_compact_none(self):
        self.run_hook("compact")
        time.sleep(0.5)
        self.assertFalse(self.lock_held())
        self.run_hook("resume")
        self.assertTrue(wait_for(self.lock_held))
        self.assertTrue(wait_for(lambda: len(self.mcp.requests) >= 1))
        self.assertEqual(self.mcp.requests[0]["headers"]["X-Weside-Companion"], "Nox")


if __name__ == "__main__":
    unittest.main()
