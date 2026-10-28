"""reply_language_gate.py as Claude Code runs it, with a fake HOME holding the setting."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "reply_language_gate.py"
sys.path.insert(0, str(HOOK.parent))
import reply_language_gate as g  # noqa: E402

GERMAN = (
    "Punkt 1 ist fertig: der Watcher löst `nameWithOwner` einmal auf und läuft dann aus `/`, "
    "deshalb bricht er nicht mehr ab, wenn der Worktree weg ist. Der Codex-Check stoppt bei "
    "WARNING, und auto-merge wird mit `--disable-auto` entschärft. Die Tests sind grün, der "
    "Red-Arm ist rot auf dem alten Skript. Als Nächstes baue ich den Watchdog."
)
ENGLISH = (
    "Item 1 is done: the watcher resolves the repo once and then runs from root, so it no longer "
    "breaks when the worktree is removed. The Codex check stops on a WARNING, and auto-merge is "
    "disarmed with the flag. The tests are green, and the red arm is red on the old script. Next "
    "I will build the watchdog for the workers that are still running."
)


def run(tmp: Path, text: str, setting: str | None = "German", **extra) -> dict | None:
    (tmp / ".claude").mkdir(exist_ok=True)
    if setting is not None:
        (tmp / ".claude" / "settings.json").write_text(json.dumps({"language": setting}))
    payload = {"hook_event_name": "Stop", "last_assistant_message": text, "cwd": str(tmp), **extra}
    res = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(tmp)},
        check=False,
        timeout=20,
    )
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout) if res.stdout.strip() else None


def test_english_reply_under_german_setting_is_sent_back(tmp_path):
    out = run(tmp_path, ENGLISH)
    assert out["decision"] == "block"
    assert out["reason"].startswith("Reply in German: your last message is in English.")


def test_german_with_english_terms_passes(tmp_path):
    assert run(tmp_path, GERMAN) is None


def test_code_tables_and_quotes_do_not_count(tmp_path):
    text = (
        "Kurz: alles grün.\n\n```text\n"
        + ENGLISH
        + "\n```\n\n| a | "
        + ENGLISH
        + " |\n\n> "
        + ENGLISH
    )
    assert run(tmp_path, text) is None


def test_short_replies_are_left_alone(tmp_path):
    assert run(tmp_path, "Done, the PR is merged and the tree is gone.") is None


def test_no_setting_subagent_and_second_stop_are_no_ops(tmp_path):
    assert run(tmp_path, ENGLISH, setting=None) is None
    assert run(tmp_path, ENGLISH, hook_event_name="SubagentStop") is None
    assert run(tmp_path, ENGLISH, agent_id="a1") is None
    assert run(tmp_path, ENGLISH, stop_hook_active=True) is None


def test_unknown_language_is_a_no_op_and_english_setting_catches_german(tmp_path):
    assert run(tmp_path, ENGLISH, setting="Klingon") is None
    out = run(tmp_path, GERMAN + " " + GERMAN, setting="English")
    assert out["reason"].startswith("Reply in English: your last message is in German.")


def test_threshold_numbers():
    assert len(g.prose_words(ENGLISH)) >= g.MIN_WORDS
    assert g.wrong_language(GERMAN, "de") is None
