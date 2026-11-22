"""One redaction, two paths: every pattern of `redaction.PATTERNS` holds in the conversation hook
and in the web view (`command_center/crewd.py`)."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "command_center"))
sys.path.insert(0, str(HERE.parent / "hooks"))
import crewd  # noqa: E402
import redaction  # noqa: E402
import store_conversation_hook as hook  # noqa: E402

# one sample per pattern, in the order of PATTERNS (the count check below binds the two)
SAMPLES = [
    "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----",
    "AGE-SECRET-KEY-1" + "Q" * 40,
    "sk-ant-" + "b" * 40,
    "ghs_" + "c" * 36,
    "github_pat_" + "d" * 40,
    "sbp_" + "e" * 40,
    "xoxb-" + "1" * 20,
    "AKIA" + "F" * 16,
    "AIza" + "g" * 35,
    "eyJ" + "g" * 20 + "." + "h" * 20 + "." + "i" * 20,
    "Bearer " + "t" * 30,
    "Basic Ym90QGV4YW1wbGUuY29tOnRvay0x",
    "password=hunter2hunter2xyz",
    "someone@example.org",
]
MORE = [
    "sk-" + "a" * 32,
    "ghp_" + "c" * 36,
    "gho_" + "c" * 36,
    "ghu_" + "c" * 36,
    "ghr_" + "c" * 36,
]


def test_every_pattern_has_a_sample():
    assert len(SAMPLES) == len(redaction.PATTERNS)
    for pattern, sample in zip(redaction.PATTERNS, SAMPLES):
        assert pattern.search(sample), pattern.pattern


# the patterns the hook gained with the shared list; the older ones stay in its own `RedactTest`
HOOK_NEW = [
    "ghs_" + "c" * 36,
    "gho_" + "c" * 36,
    "ghu_" + "c" * 36,
    "ghr_" + "c" * 36,
    "xoxb-" + "1" * 20,
    "AGE-SECRET-KEY-1" + "Q" * 40,
    "AIza" + "g" * 35,
    "Bearer " + "t" * 30,
    "someone@example.org",
]


def test_the_hook_redacts_the_patterns_it_gained():
    for s in HOOK_NEW:
        assert s not in hook.redact(f"value {s} end"), s
        assert "[REDACTED]" in hook.redact(f"value {s} end"), s


def test_the_web_view_redacts_every_sample():
    for s in SAMPLES + MORE:
        out = crewd.clean(f"value {s} end")
        assert s not in out and "[redacted]" in out, s


def test_ordinary_text_is_untouched():
    text = "Der Backfill hat 9799 Zeilen gefüllt, sha256 f93e8c0c3310 stimmt."
    assert crewd.clean(text) == text


def test_bearer_prose_stays_and_a_bearer_token_goes():
    for prose in (
        "The API uses Bearer authentication for every call.",
        "Send a bearer token in the header.",
        "Authorization: Bearer <token>",
    ):
        assert redaction.redact(prose) == prose, prose
    token = "Bearer eyJhbGciOi.abcDEF123456789_-xyz=="
    assert redaction.redact(f"Authorization: {token} end") == "Authorization: [REDACTED] end"
