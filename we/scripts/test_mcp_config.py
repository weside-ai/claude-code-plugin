"""we/.mcp.json: the companion pin travels through headersHelper, never through static headers.

Claude Code keys a server's stored OAuth by a hash of its type, url and expanded headers, not of
its headersHelper (2.1.310). A pin in `headers` gives every companion name its own OAuth identity,
so each new name asks for a sign-in again; the helper keeps one identity for every session.
"""

import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

MCP_JSON = Path(__file__).resolve().parents[1] / ".mcp.json"
SHELLS = tuple(s for s in ("/bin/sh", shutil.which("bash"), shutil.which("dash")) if s)


def _server():
    return json.loads(MCP_JSON.read_text(encoding="utf-8"))["mcpServers"]["weside-mcp"]


def _run_helper(shell, value):
    env = {k: v for k, v in os.environ.items() if k != "WESIDE_COMPANION"}
    if value is not None:
        env["WESIDE_COMPANION"] = value
    out = subprocess.run(
        [shell, "-c", _server()["headersHelper"]],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return out.returncode, json.loads(out.stdout.strip())


class McpConfigShapeTest(unittest.TestCase):
    def test_no_static_headers_in_the_oauth_key(self):
        self.assertNotIn("headers", _server())

    def test_identity_fields_stay_fixed(self):
        server = _server()
        self.assertEqual(server["type"], "http")
        self.assertEqual(server["url"], "https://api.weside.ai/mcp/")
        self.assertIn("clientId", server["oauth"])

    def test_helper_is_a_constant_command(self):
        helper = _server()["headersHelper"]
        # No substitution by the loader (${...}, a plugin path, a version) may enter it.
        self.assertNotIn("${", helper)
        self.assertNotIn("CLAUDE_PLUGIN_ROOT", helper)
        # The shape Claude Code 2.1.310 demands of a plugin entry's headersHelper (shown in the
        # install consent UI); held here too so the command stays reviewable on one line.
        self.assertRegex(helper, r"^[\x20-\x7e]+$")
        self.assertIsNone(re.search(" {4}", helper))


class HelperOutputTest(unittest.TestCase):
    def _each_shell(self, value):
        for shell in SHELLS:
            with self.subTest(shell=shell, value=value):
                yield _run_helper(shell, value)

    def test_unset_or_empty_sends_no_header(self):
        for value in (None, ""):
            for code, headers in self._each_shell(value):
                self.assertEqual(code, 0)
                self.assertEqual(headers, {})

    def test_name_is_sent(self):
        for code, headers in self._each_shell("Vyra"):
            self.assertEqual(code, 0)
            self.assertEqual(headers, {"X-Weside-Companion": "Vyra"})

    def test_quote_backslash_and_format_chars_survive_as_json(self):
        for value in ('Ky"ra', "a\\b", "%s%d", "$(id)", "`id`"):
            for code, headers in self._each_shell(value):
                self.assertEqual(code, 0)
                self.assertEqual(headers, {"X-Weside-Companion": value})

    def test_control_characters_are_dropped(self):
        for code, headers in self._each_shell("Vy\nra\r\t"):
            self.assertEqual(code, 0)
            self.assertEqual(headers, {"X-Weside-Companion": "Vyra"})


if __name__ == "__main__":
    unittest.main()
